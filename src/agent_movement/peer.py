"""Authenticated, pre-disclosure handoff over the synthetic trust model (issue #8).

Metadata first, payload last:

1. discovery  ``GET  /v0/agent-card``  -> CA-signed descriptor (public metadata only).
2. preflight  ``POST /v0/preflight``   -> origin-signed metadata, user grant, client nonce and a
   *salted commitment* to the task -- **no task text** -> receiver-signed admission that
   echoes the nonce (proves the receiver holds the key its card names).
3. delivery   ``POST /v0/deliveries``  -> origin-signed task text, sent only after 1 and 2
   verified on the sender side.

Delivery confidentiality (issue #19): when the receiver's card carries a CA-signed X25519
``enc_key``, the task text, salt and a fresh response key are sealed with RFC 9180 HPKE to
that key, bound to the preflight transcript (``trust.delivery_info``), and the origin signs
the ciphertext. The receiver verifies the signature, then opens the ciphertext, and returns
its signed receipt encrypted under the response key. An on-path relay that owns the real
endpoint address then sees only ciphertext. Without an ``enc_key`` (the stdlib-only mode)
deliveries are plaintext: **no confidentiality**.

Authority (grant liveness/revocation) is checked at preflight, again at delivery and again
*inside the SQLite transaction* that records the simulated external effect, so a revocation
that commits first always wins. LOCAL/SYNTHETIC ONLY: no TLS, no channel binding, no real
external effects. See docs/peer-authentication.md for assumptions and limitations.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
import sqlite3
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from .core import (
    MAX_TEXT,
    SCHEMA_VERSION,
    Conflict,
    ContractError,
    PolicyDenied,
    SQLiteStore,
    _fields,
    _id,
    canonical,
    digest,
    parse_json,
    validate_envelope,
)
from .continuity_runtime import ContinuityRuntime
from .trust import (
    CLASSIFICATIONS,
    HPKE_SUITE,
    MAX_SEALED_B64,
    PEER_SCHEMA_VERSION,
    TASK_KINDS,
    DisclosureBlocked,
    HpkeKey,
    TrustDenied,
    TrustStore,
    Unauthenticated,
    Unauthorized,
    UnsupportedSchema,
    VerifiedCard,
    b64d,
    b64e,
    check_grant_live,
    check_grant_scope,
    commitment,
    delivery_info,
    endpoint,
    hpke_available,
    open_response,
    safe_id,
    seal,
    seal_response,
    sealed_parts,
    unseal,
    verify_card,
    verify_grant,
    verify_revocation,
)

LOG = logging.getLogger("agent_movement.peer")
CARD_PATH, PREFLIGHT_PATH, DELIVERY_PATH, REVOCATION_PATH = (
    "/v0/agent-card", "/v0/preflight", "/v0/deliveries", "/v0/revocations")
PREFLIGHT_FIELDS = {"type", "schema_version", "movement_id", "logical_task_id", "origin_card",
                    "destination", "task", "grant", "client_nonce", "issued_at", "execution",
                    "observability"}
DELIVERY_FIELDS = {"type", "schema_version", "admission_id", "task", "salt"}  # plaintext mode
SEALED_DELIVERY_FIELDS = {"type", "schema_version", "admission_id", "enc"}   # HPKE mode
SEALED_PLAINTEXT_FIELDS = {"task", "salt", "response_key"}  # inside the HPKE ciphertext
TRACE_FIELDS = ("seq", "at", "stage", "outcome", "reason", "movement_id", "peer",
                "claimed_peer", "admission_id")
_NONCE = re.compile(r"[A-Za-z0-9_-]{22,64}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_ADMISSION = re.compile(r"adm-[0-9a-f]{32}\Z")
# What makes a second preflight a retry of an admitted movement rather than a new one.
# The commitment, nonce and digests differ on every attempt (fresh salt and nonce).
MOVEMENT_BINDING = ("origin_id", "logical_task_id", "grant_id", "kind", "classification",
                    "idempotency_key", "trace_id")
_GRANT_USES_TABLE = """CREATE TABLE grant_uses (
    grant_id TEXT NOT NULL, movement_id TEXT NOT NULL, origin_id TEXT NOT NULL,
    use_number INTEGER NOT NULL CHECK (use_number >= 1), max_uses INTEGER NOT NULL,
    at INTEGER NOT NULL, PRIMARY KEY (grant_id, movement_id), UNIQUE (grant_id, use_number))"""


class HandoffAborted(PolicyDenied):
    """Sender stopped a handoff. ``payload_sent`` says whether task text left the process."""

    def __init__(self, stage: str, reason: str, payload_sent: bool, status: int | None = None):
        super().__init__(f"{stage}: {reason}")
        self.stage, self.reason, self.payload_sent, self.status = stage, reason, payload_sent, status


def _now(clock: Callable[[], float]) -> int:
    return int(clock())


# ------------------------------------------------------------------- ledger


def _binding(record: dict[str, Any]) -> tuple[Any, ...]:
    values = {**record, "grant_id": record["grant"]["payload"]["grant_id"]}
    return tuple(values[name] for name in MOVEMENT_BINDING)


class PeerLedger:
    """Receiver-side nonces, admissions, grant uses, revocations, authorized effects and
    sanitized traces.

    Lives in the same SQLite file as ``SQLiteStore``. Stores IDs, reason codes and digests
    of metadata only -- never task text, salts, signatures or key material; effect payload
    digests are keyed store commitments. ``agent_movement.retention`` purges these tables
    by age (docs/data-retention.md).
    """

    def __init__(self, store: SQLiteStore):
        self.store = store
        with store._connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS peer_nonces (
                    origin_id TEXT NOT NULL, nonce TEXT NOT NULL, seen_at INTEGER NOT NULL,
                    PRIMARY KEY (origin_id, nonce));
                CREATE TABLE IF NOT EXISTS peer_admissions (
                    admission_id TEXT PRIMARY KEY, movement_id TEXT NOT NULL UNIQUE,
                    record_json TEXT NOT NULL, expires_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS authority_log (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, event TEXT NOT NULL,
                    grant_id TEXT NOT NULL, ref TEXT NOT NULL, at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS grant_revocations (
                    grant_id TEXT PRIMARY KEY, revoked_at INTEGER NOT NULL, log_seq INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS authorized_effects (
                    task_id TEXT NOT NULL, effect_id TEXT NOT NULL, grant_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL, payload_digest TEXT NOT NULL, log_seq INTEGER NOT NULL,
                    PRIMARY KEY (task_id, effect_id));
                CREATE TABLE IF NOT EXISTS peer_trace (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, stage TEXT NOT NULL,
                    outcome TEXT NOT NULL, reason TEXT NOT NULL, movement_id TEXT, peer TEXT,
                    claimed_peer TEXT, admission_id TEXT);
            """)
        self._ensure_grant_uses()

    def _ensure_grant_uses(self) -> None:
        """Create ``grant_uses`` (issue #29), backfilled from existing admissions.

        A ledger written before use counting holds admissions but no use rows. Each of those
        admissions counts as one use of its grant, so upgrading never hands a grant extra
        uses. Creation and backfill share one write transaction; concurrent openers re-check
        under the lock.
        """
        exists = "SELECT 1 FROM sqlite_master WHERE type='table' AND name='grant_uses'"
        with self.store._connection() as db:
            if db.execute(exists).fetchone():
                return
            db.execute("BEGIN IMMEDIATE")
            if db.execute(exists).fetchone():
                db.commit()
                return
            db.execute(_GRANT_USES_TABLE)
            used: dict[str, int] = {}
            for (raw,) in db.execute("SELECT record_json FROM peer_admissions ORDER BY rowid").fetchall():
                record = json.loads(raw)
                payload = record["grant"]["payload"]
                grant_id = payload["grant_id"]
                used[grant_id] = used.get(grant_id, 0) + 1
                db.execute("INSERT INTO grant_uses VALUES(?,?,?,?,?,?)",
                           (grant_id, record["movement_id"], record["origin_id"], used[grant_id],
                            payload.get("max_uses", 1), record["expires_at"]))
            db.commit()

    @staticmethod
    def consume_use(db: sqlite3.Connection, grant: dict[str, Any], movement_id: str,
                    origin_id: str, at: int) -> bool:
        """Count one use of ``grant`` for ``movement_id``. Call inside the write transaction
        that records the admission, so the count and the admission commit or roll back
        together and concurrent preflights serialize on the lock.

        True: a new use was recorded. False: this movement already holds a use of this grant
        (a retry), so nothing is consumed. Raises ``Unauthorized("grant_uses_exhausted")``
        when ``max_uses`` distinct movements were already admitted.
        """
        grant_id = grant["grant_id"]
        if db.execute("SELECT 1 FROM grant_uses WHERE grant_id=? AND movement_id=?",
                      (grant_id, movement_id)).fetchone():
            return False
        used = db.execute("SELECT COUNT(*) FROM grant_uses WHERE grant_id=?", (grant_id,)).fetchone()[0]
        if used >= grant["max_uses"]:
            raise Unauthorized("grant_uses_exhausted")
        db.execute("INSERT INTO grant_uses VALUES(?,?,?,?,?,?)",
                   (grant_id, movement_id, origin_id, used + 1, grant["max_uses"], at))
        return True

    def grant_uses(self, grant_id: str | None = None) -> list[dict[str, Any]]:
        names = ("grant_id", "movement_id", "origin_id", "use_number", "max_uses")
        query = f"SELECT {','.join(names)} FROM grant_uses"
        with self.store._connection() as db:
            rows = (db.execute(query + " ORDER BY grant_id, use_number").fetchall() if grant_id is None
                    else db.execute(query + " WHERE grant_id=? ORDER BY use_number", (grant_id,)).fetchall())
        return [dict(zip(names, row, strict=True)) for row in rows]

    @staticmethod
    def is_revoked(db: sqlite3.Connection, grant_id: str) -> bool:
        return db.execute("SELECT 1 FROM grant_revocations WHERE grant_id=?", (grant_id,)).fetchone() is not None

    def revoke(self, grant_id: str, at: int) -> bool:
        """Record a revocation. Serialized with effect commits by BEGIN IMMEDIATE."""
        _id(grant_id, "grant_id")
        with self.store._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if self.is_revoked(db, grant_id):
                db.commit()
                return False
            seq = db.execute("INSERT INTO authority_log(event,grant_id,ref,at) VALUES('revoke',?,?,?)",
                             (grant_id, grant_id, at)).lastrowid
            db.execute("INSERT INTO grant_revocations VALUES(?,?,?)", (grant_id, at, seq))
            db.commit()
            return True

    def trace(self, stage: str, outcome: str, reason: str, ctx: TraceContext) -> None:
        event = {"at": datetime.now(UTC).isoformat(), "stage": stage, "outcome": outcome,
                 "reason": reason, "movement_id": ctx.movement_id, "peer": ctx.peer,
                 "claimed_peer": ctx.claimed_peer, "admission_id": ctx.admission_id}
        with self.store._connection() as db:
            db.execute("INSERT INTO peer_trace(at,stage,outcome,reason,movement_id,peer,claimed_peer,"
                       "admission_id) VALUES(:at,:stage,:outcome,:reason,:movement_id,:peer,"
                       ":claimed_peer,:admission_id)", event)
        LOG.info("peer.%s %s", stage, canonical(event))

    def traces(self) -> list[dict[str, Any]]:
        with self.store._connection() as db:
            rows = db.execute(f"SELECT {','.join(TRACE_FIELDS)} FROM peer_trace ORDER BY seq").fetchall()
        return [dict(zip(TRACE_FIELDS, row, strict=True)) for row in rows]

    def authority_log(self) -> list[dict[str, Any]]:
        with self.store._connection() as db:
            rows = db.execute("SELECT seq,event,grant_id,ref FROM authority_log ORDER BY seq").fetchall()
        return [dict(zip(("seq", "event", "grant_id", "ref"), row, strict=True)) for row in rows]

    def effects(self) -> list[dict[str, Any]]:
        with self.store._connection() as db:
            rows = db.execute("SELECT task_id,effect_id,grant_id,agent_id,log_seq FROM authorized_effects "
                              "ORDER BY log_seq").fetchall()
        names = ("task_id", "effect_id", "grant_id", "agent_id", "log_seq")
        return [dict(zip(names, row, strict=True)) for row in rows]


class AuthorizedEffectGateway:
    """Simulated external effect that re-verifies the user grant at the commit point.

    Closes the PR #6 gap "receiver grant not rechecked at simulated effect commit": the
    revocation lookup, the expiry check (clock read inside the transaction) and the effect
    insert share one ``BEGIN IMMEDIATE`` transaction, and ``PeerLedger.revoke`` takes the same
    write lock, so revocations and commits are linearized. Still simulated: a real tool
    would need the same check on *its* side of the boundary.
    """

    def __init__(self, ledger: PeerLedger, clock: Callable[[], float] = time.time,
                 continuity: ContinuityRuntime | None = None):
        self.ledger = ledger
        self.clock = clock
        self.continuity = continuity

    def commit(self, grant: dict[str, Any], agent_id: str, task_id: str, effect_id: str,
               payload: str, *, movement_id: str | None = None) -> bool:
        """True for a new commit, False for an identical replay; raises Unauthorized."""
        _id(agent_id, "agent_id")
        _id(task_id, "task_id")
        _id(effect_id, "effect_id")
        if not isinstance(payload, str) or len(payload.encode("utf-8")) > MAX_TEXT:
            raise ContractError("invalid payload")
        # Keyed under the store secret (issue #39): the payload is the task result.
        fingerprint = self.ledger.store.keyed_digest(hashlib.sha256(payload.encode("utf-8")).hexdigest())
        with self.ledger.store._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            check_grant_live(grant, now=_now(self.clock),
                             revoked=self.ledger.is_revoked(db, grant["grant_id"]))
            if grant["audience"] != agent_id:
                raise Unauthorized("wrong_audience")
            if grant["task_id"] != task_id:
                raise Unauthorized("wrong_task")
            if self.continuity is not None:
                self.continuity.require_effect(
                    db, grant=grant, agent_id=agent_id, task_id=task_id,
                    effect_id=effect_id, movement_id=movement_id, now=_now(self.clock),
                )
            existing = db.execute("SELECT payload_digest FROM authorized_effects WHERE task_id=? "
                                  "AND effect_id=?", (task_id, effect_id)).fetchone()
            if existing is not None:
                if existing[0] != fingerprint:
                    raise Conflict("same effect ID with different payload")
                db.commit()
                return False
            seq = db.execute("INSERT INTO authority_log(event,grant_id,ref,at) VALUES('effect',?,?,?)",
                             (grant["grant_id"], f"{task_id}/{effect_id}", _now(self.clock))).lastrowid
            db.execute("INSERT INTO authorized_effects VALUES(?,?,?,?,?,?)",
                       (task_id, effect_id, grant["grant_id"], agent_id, fingerprint, seq))
            db.commit()
            return True


# ----------------------------------------------------------------- receiver


@dataclass
class TraceContext:
    movement_id: str | None = None
    peer: str | None = None          # authenticated agent ID (set only after signature check)
    claimed_peer: str | None = None  # unauthenticated claim, kept apart on purpose
    admission_id: str | None = None


def _error_body(exc: Exception) -> tuple[int, dict[str, str]]:
    if isinstance(exc, UnsupportedSchema):
        return 400, {"error": "unsupported_schema"}
    if isinstance(exc, ContractError):
        return 400, {"error": "invalid_contract"}
    if isinstance(exc, Unauthenticated):
        return 401, {"error": "unauthenticated"}
    if isinstance(exc, (Unauthorized, PolicyDenied)):
        return 403, {"error": "forbidden"}
    return 409, {"error": "conflict"}


def _reason(exc: Exception) -> str:
    if isinstance(exc, TrustDenied):
        return exc.reason
    if isinstance(exc, UnsupportedSchema):
        return "unsupported_schema"
    if isinstance(exc, ContractError):
        return "invalid_contract"
    if isinstance(exc, Conflict):
        return "conflict"
    return "denied"


class PeerReceiver:
    """Transport-agnostic receiver. Peers only see coarse errors; reasons stay in the trace."""

    def __init__(self, card: dict[str, Any], key: Any, trust: TrustStore, store: SQLiteStore,
                 capabilities: Iterable[str], *, admission_ttl: int = 60, max_clock_skew: int = 120,
                 clock: Callable[[], float] = time.time,
                 before_effect_commit: Callable[[dict[str, Any]], None] | None = None,
                 enc_key: HpkeKey | None = None,
                 continuity: ContinuityRuntime | None = None,
                 secure_test_mode: bool = False):
        own = verify_card(card, trust, _now(clock))
        if own.key.kid != key.kid:
            raise ContractError("receiver card does not name the receiver key")
        # The private HPKE key must be exactly the one the card advertises, and vice versa:
        # a card that offers encryption with no key to open it (or the reverse) is misconfigured.
        if (own.enc_key is None) != (enc_key is None) or (
                own.enc_key is not None and not own.enc_key.matches(enc_key)):
            raise ContractError("receiver card enc_key does not match the receiver encryption key")
        allow = frozenset(capabilities)
        if not allow or not allow <= TASK_KINDS:
            raise ContractError("capability allowlist must be a non-empty subset of known task kinds")
        if secure_test_mode and continuity is None:
            raise ContractError("secure test mode requires a continuity authority")
        if continuity is not None and (continuity.store is not store or continuity.recipient_id != own.agent_id):
            raise ContractError("continuity authority is not bound to this receiver and store")
        self.continuity, self.secure_test_mode = continuity, secure_test_mode
        self.card, self.key, self.trust, self.store = card, key, trust, store
        self.enc_key, self.card_digest = enc_key, own.digest
        self.agent_id, self.endpoint, self.capabilities = own.agent_id, own.endpoint, allow
        self.admission_ttl, self.max_clock_skew, self.clock = admission_ttl, max_clock_skew, clock
        self.before_effect_commit = before_effect_commit
        self.ledger = PeerLedger(store)
        self.effects = AuthorizedEffectGateway(self.ledger, clock, continuity)

    def handle(self, method: str, path: str, body: bytes) -> tuple[int, dict[str, Any]]:
        if method == "GET" and path == CARD_PATH:
            return 200, self.card  # public metadata only
        routes = {PREFLIGHT_PATH: ("preflight", self._preflight),
                  DELIVERY_PATH: ("delivery", self._deliver),
                  REVOCATION_PATH: ("revocation", self._revoke)}
        if method != "POST" or path not in routes:
            return 404, {"error": "not_found"}
        stage, handler = routes[path]
        ctx = TraceContext()
        try:
            status, response, reason = handler(body, ctx)
        except (ContractError, PolicyDenied, Conflict) as exc:
            self.ledger.trace(stage, "denied", _reason(exc), ctx)
            return _error_body(exc)
        self.ledger.trace(stage, "allowed", reason, ctx)
        return status, response

    # -- phase 2: metadata-only preflight ---------------------------------------------
    def _preflight(self, body: bytes, ctx: TraceContext) -> tuple[int, dict[str, Any], str]:
        sealed = parse_json(body)
        p = sealed_parts(sealed, "preflight")["payload"]
        ctx.movement_id = safe_id(p.get("movement_id"))
        claimed_card = p.get("origin_card")
        if isinstance(claimed_card, dict) and isinstance(claimed_card.get("payload"), dict):
            ctx.claimed_peer = safe_id(claimed_card["payload"].get("agent_id"))
        if p.get("schema_version") != PEER_SCHEMA_VERSION:
            raise UnsupportedSchema("unsupported peer schema")
        _fields(p, PREFLIGHT_FIELDS, "preflight")
        if p["type"] != "preflight":
            raise ContractError("invalid preflight type")
        movement_id = _id(p["movement_id"], "movement_id")
        task_id = _id(p["logical_task_id"], "logical_task_id")
        execution = _fields(p["execution"], {"idempotency_key"}, "execution")
        trace = _fields(p["observability"], {"trace_id"}, "observability")
        _id(execution["idempotency_key"], "idempotency_key")
        _id(trace["trace_id"], "trace_id")
        if not isinstance(p["client_nonce"], str) or not _NONCE.fullmatch(p["client_nonce"]):
            raise ContractError("invalid client nonce")
        task = _fields(p["task"], {"kind", "classification", "commitment"}, "task metadata")
        if task["kind"] not in TASK_KINDS or task["classification"] not in CLASSIFICATIONS:
            raise ContractError("unsupported task kind or classification")
        if not isinstance(task["commitment"], str) or not _HEX64.fullmatch(task["commitment"]):
            raise ContractError("invalid commitment")
        dest = _fields(p["destination"], {"agent_id", "endpoint"}, "destination")
        now = _now(self.clock)
        issued_at = p["issued_at"]
        if type(issued_at) is not int:
            raise ContractError("invalid issued_at")

        # Peer identity: CA-endorsed card + proof of possession of the key it names.
        origin = verify_card(p["origin_card"], self.trust, now)
        unseal("preflight", sealed, origin.key)
        ctx.peer = origin.agent_id
        if abs(now - issued_at) > self.max_clock_skew:
            raise Unauthenticated("stale_request")

        # Destination binding: the sender must have meant *this* agent at *this* endpoint.
        if dest != {"agent_id": self.agent_id, "endpoint": self.endpoint}:
            raise Unauthorized("wrong_destination")
        if task["kind"] not in self.capabilities:
            raise Unauthorized("capability_not_allowlisted")

        grant = verify_grant(p["grant"], self.trust)
        check_grant_scope(grant, actor=origin.agent_id, audience=self.agent_id, task_id=task_id,
                          kind=task["kind"], classification=task["classification"])
        admission_id = "adm-" + secrets.token_hex(16)
        expires_at = min(now + self.admission_ttl, grant["expires_at"], origin.expires_at)
        record = {"movement_id": movement_id, "logical_task_id": task_id, "origin_id": origin.agent_id,
                  "origin_card": p["origin_card"], "grant": p["grant"], "kind": task["kind"],
                  "classification": task["classification"], "commitment": task["commitment"],
                  "idempotency_key": execution["idempotency_key"], "trace_id": trace["trace_id"],
                  "client_nonce": p["client_nonce"], "preflight_digest": digest(sealed),
                  "expires_at": expires_at}
        # One write transaction: liveness/revocation, nonce, grant use and admission commit
        # together or not at all, and concurrent preflights for the same grant serialize.
        with self.store._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            check_grant_live(grant, now=now, revoked=self.ledger.is_revoked(db, grant["grant_id"]))
            if self.continuity is not None:
                epoch = self.continuity.require(db, kind=task["kind"], movement_id=movement_id,
                                                task_id=task_id, now=now)
                record["continuity_policy_epoch"] = epoch
                record["continuity_profile_digest"] = self.continuity.profile_digest
            db.execute("DELETE FROM peer_nonces WHERE seen_at < ?", (now - 2 * self.max_clock_skew,))
            try:
                db.execute("INSERT INTO peer_nonces VALUES(?,?,?)", (origin.agent_id, p["client_nonce"], now))
            except sqlite3.IntegrityError as exc:
                raise Conflict("replayed preflight nonce") from exc
            previous = db.execute("SELECT record_json FROM peer_admissions WHERE movement_id=?",
                                  (movement_id,)).fetchone()
            if previous is not None and _binding(json.loads(previous[0])) != _binding(record):
                raise Conflict("movement ID already admitted")
            self.ledger.consume_use(db, grant, movement_id, origin.agent_id, now)
            if previous is None:
                db.execute("INSERT INTO peer_admissions VALUES(?,?,?,?)",
                           (admission_id, movement_id, canonical(record), expires_at))
            else:
                # A retry of an admitted movement (e.g. the admission reply was lost): the new
                # admission supersedes the old one and consumes no further grant use.
                db.execute("UPDATE peer_admissions SET admission_id=?, record_json=?, expires_at=? "
                           "WHERE movement_id=?", (admission_id, canonical(record), expires_at, movement_id))
            db.commit()
        ctx.admission_id = admission_id
        admission = {"type": "admission", "admission_id": admission_id, "movement_id": movement_id,
                     "destination": {"agent_id": self.agent_id, "endpoint": self.endpoint},
                     "client_nonce": p["client_nonce"], "preflight_digest": record["preflight_digest"],
                     "expires_at": expires_at}
        return 200, seal("admission", admission, self.key), "admitted" if previous is None else "readmitted"

    def delivery_info(self, record: dict[str, Any], admission_id: str) -> bytes:
        """The HPKE ``info`` for an admitted movement, rebuilt from receiver-side state only."""
        if self.enc_key is None:
            raise ContractError("this receiver does not accept sealed deliveries")
        return delivery_info(card_digest=self.card_digest, enc_kid=self.enc_key.kid,
                             movement_id=record["movement_id"], origin_id=record["origin_id"],
                             audience=self.agent_id, endpoint_url=self.endpoint,
                             client_nonce=record["client_nonce"], admission_id=admission_id,
                             preflight_digest=record["preflight_digest"])

    def _open_delivery(self, p: dict[str, Any],
                       record: dict[str, Any]) -> tuple[Any, Any, bytes, bytes]:
        """Open an HPKE-sealed delivery. Called only after the origin signature verified.

        Returns (task, salt, response_key, info). Every failure raises before any decrypted
        byte is returned, parsed, logged or persisted.
        """
        if self.enc_key is None:
            raise ContractError("this receiver does not accept sealed deliveries")
        env = _fields(p["enc"], {"suite", "kid", "ct"}, "sealed delivery")
        if env["suite"] != HPKE_SUITE or env["kid"] != self.enc_key.kid:
            raise Unauthenticated("wrong_enc_key")
        info = self.delivery_info(record, p["admission_id"])
        try:
            ciphertext = b64d(env["ct"], "delivery ciphertext", MAX_SEALED_B64)
        except ContractError as exc:
            raise Unauthenticated("delivery_decrypt_failed") from exc
        inner = _fields(parse_json(self.enc_key.open(ciphertext, info)), SEALED_PLAINTEXT_FIELDS,
                        "sealed delivery plaintext")
        response_key = b64d(inner["response_key"], "response key")
        if len(response_key) != 32:
            raise ContractError("invalid response key")
        return inner["task"], inner["salt"], response_key, info

    # -- phase 3: payload delivery ------------------------------------------------------
    def _deliver(self, body: bytes, ctx: TraceContext) -> tuple[int, dict[str, Any], str]:
        sealed = parse_json(body)
        p = sealed_parts(sealed, "delivery")["payload"]
        if p.get("schema_version") != PEER_SCHEMA_VERSION:
            raise UnsupportedSchema("unsupported peer schema")
        encrypted = "enc" in p
        _fields(p, SEALED_DELIVERY_FIELDS if encrypted else DELIVERY_FIELDS, "delivery")
        if p["type"] != "delivery" or not isinstance(p["admission_id"], str) \
                or not _ADMISSION.fullmatch(p["admission_id"]):
            raise ContractError("invalid delivery")
        with self.store._connection() as db:
            row = db.execute("SELECT record_json FROM peer_admissions WHERE admission_id=?",
                             (p["admission_id"],)).fetchone()
        if row is None:
            raise Unauthorized("unknown_admission")
        record = json.loads(row[0])
        ctx.admission_id, ctx.movement_id = p["admission_id"], record["movement_id"]
        ctx.claimed_peer = record["origin_id"]
        now = _now(self.clock)
        origin = verify_card(record["origin_card"], self.trust, now)  # card may have expired
        unseal("delivery", sealed, origin.key)  # same peer that was admitted; covers the ciphertext
        ctx.peer = origin.agent_id
        if now >= record["expires_at"]:
            raise Unauthorized("admission_expired")
        if encrypted:
            task, salt, response_key, info = self._open_delivery(p, record)
        elif self.enc_key is not None:
            # The text already crossed the wire in clear; refuse to act on it all the same, so a
            # misconfigured or downgraded sender never gets an effect out of a plaintext delivery.
            raise Unauthorized("plaintext_delivery_refused")
        else:
            task, salt = p["task"], p["salt"]
        task = _fields(task, {"kind", "text"}, "task")
        if task["kind"] != record["kind"] or commitment(b64d(salt, "salt"), task) != record["commitment"]:
            raise Unauthorized("commitment_mismatch")
        grant = verify_grant(record["grant"], self.trust)
        with self.store._connection() as db:
            if self.continuity is not None:
                db.execute("BEGIN IMMEDIATE")
            check_grant_live(grant, now=now, revoked=self.ledger.is_revoked(db, grant["grant_id"]))
            if self.continuity is not None:
                epoch = record.get("continuity_policy_epoch")
                if type(epoch) is not int or record.get("continuity_profile_digest") != self.continuity.profile_digest:
                    raise Unauthorized("continuity_admission_binding_missing")
                self.continuity.require(db, kind=record["kind"], movement_id=record["movement_id"],
                                        task_id=record["logical_task_id"], policy_epoch=epoch, now=now)
        envelope = validate_envelope({
            "schema_version": SCHEMA_VERSION, "movement_id": record["movement_id"],
            "logical_task_id": record["logical_task_id"], "operation": "delegate",
            "origin": {"agent_id": origin.agent_id}, "destination": {"agent_id": self.agent_id},
            "task": task, "context": {"classification": record["classification"]},
            "authority": {"approval_ref": grant["grant_id"]},
            "execution": {"idempotency_key": record["idempotency_key"]},
            "observability": {"trace_id": record["trace_id"]}})
        # Pure, idempotent computation; the key is scoped to the *authenticated* origin.
        receipt = self.store.receive(envelope, sender=origin.agent_id)
        if self.before_effect_commit is not None:
            self.before_effect_commit(record)  # test seam: inject races here
        try:
            committed = self.effects.commit(grant, self.agent_id, record["logical_task_id"],
                                            f"{record['movement_id']}.result", canonical(receipt["artifact"]),
                                            movement_id=record["movement_id"])
        except Unauthorized as exc:
            raise Unauthorized(f"effect_{exc.reason}") from exc
        response = {"type": "receipt", "admission_id": p["admission_id"],
                    "movement_id": record["movement_id"], "receipt": receipt,
                    "effect": "committed" if committed else "replayed"}
        signed = seal("receipt", response, self.key)
        if encrypted:  # the receipt carries the result and content digests: encrypt it too
            signed = seal_response(response_key, info, signed)
        return 200, signed, "effect_committed" if committed else "effect_replayed"

    def _revoke(self, body: bytes, ctx: TraceContext) -> tuple[int, dict[str, Any], str]:
        notice = verify_revocation(parse_json(body), self.trust)  # signed by the grant issuer
        ctx.peer = notice["issuer"]
        self.ledger.revoke(notice["grant_id"], _now(self.clock))
        return 200, {"status": "revoked", "grant_id": notice["grant_id"]}, "revoked"


# --------------------------------------------------------------- transports


class InProcessTransport:
    """Routes endpoint strings to in-process handlers (anything with ``handle``)."""

    def __init__(self, routes: dict[str, Any]):
        self.routes = routes

    def request(self, method: str, url: str, path: str, body: bytes | None) -> tuple[int, bytes]:
        target = self.routes.get(url)
        if target is None:
            return 503, b'{"error":"unreachable"}'
        status, obj = target.handle(method, path, body or b"")
        return status, json.dumps(obj, sort_keys=True).encode("utf-8")


class Transport(Protocol):
    """What PeerClient needs from a transport: one request, returning (status, body bytes)."""

    def request(self, method: str, url: str, path: str, body: bytes | None) -> tuple[int, bytes]: ...


class HttpTransport:
    """Loopback-only HTTP client transport."""

    def request(self, method: str, url: str, path: str, body: bytes | None) -> tuple[int, bytes]:
        if not url.startswith("http://127.0.0.1:"):
            raise ContractError("HTTP transport is loopback-only")
        headers = {"Content-Type": "application/json"} if body is not None else {}
        request = urllib.request.Request(url + path, data=body, headers=headers, method=method)  # noqa: S310 (checked above)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()


@dataclass
class RecordingTransport:
    """Captures every byte exchanged so tests can prove what was (not) transmitted."""

    inner: Transport
    on_request: Callable[[str, str, bytes | None], None] | None = None
    exchanges: list[dict[str, Any]] = field(default_factory=list)

    def request(self, method: str, url: str, path: str, body: bytes | None) -> tuple[int, bytes]:
        if self.on_request is not None:
            self.on_request(method, path, body)
        status, response = self.inner.request(method, url, path, body)
        self.exchanges.append({"method": method, "url": url, "path": path, "request": body or b"",
                               "status": status, "response": response})
        return status, response

    def paths(self) -> list[str]:
        return [x["path"] for x in self.exchanges]

    def transmitted(self) -> bytes:
        return b"\n".join(x["request"] + b"\n" + x["response"] for x in self.exchanges)


# ------------------------------------------------------------------- client


@dataclass(frozen=True)
class DeliverySeal:
    """Sender-side HPKE context for one admitted delivery: recipient key, transcript and the
    single-use key the receiver must encrypt its receipt under."""

    key: HpkeKey
    info: bytes = field(repr=False)
    response_key: bytes = field(repr=False)

    def seal(self, plaintext: bytes) -> dict[str, str]:
        ciphertext = self.key.seal(plaintext, self.info)
        return {"suite": HPKE_SUITE, "kid": self.key.kid, "ct": b64e(ciphertext)}

    def open_response(self, obj: Any) -> Any:
        return parse_json(open_response(self.response_key, self.info, obj))


class PeerClient:
    """Origin side. Never transmits task text before discovery and preflight verify.

    If the destination card advertises an ``enc_key`` the delivery is always HPKE-sealed to
    it (never downgraded). ``require_confidentiality=True`` additionally refuses destinations
    whose card offers no ``enc_key``; otherwise such deliveries go out in plaintext and the
    client trace labels them ``plaintext_no_confidentiality``.
    """

    def __init__(self, card: dict[str, Any], key: Any, trust: TrustStore, transport: Transport, *,
                 never_send: Iterable[str | bytes] = (), clock: Callable[[], float] = time.time,
                 schema_version: str = PEER_SCHEMA_VERSION, require_confidentiality: bool = False):
        self.card, self.key, self.trust, self.transport = card, key, trust, transport
        self.clock, self.schema_version = clock, schema_version
        self.require_confidentiality = require_confidentiality
        forms = [s.encode("utf-8") if isinstance(s, str) else s for s in never_send]
        self._never_send = tuple(x for x in [*forms, *key.secret_forms()] if x)
        self.trace: list[dict[str, Any]] = []

    def _event(self, stage: str, outcome: str, reason: str, payload_sent: bool) -> None:
        event = {"stage": stage, "outcome": outcome, "reason": reason, "payload_sent": payload_sent}
        self.trace.append(event)
        LOG.info("client.%s %s", stage, canonical(event))

    def _abort(self, stage: str, reason: str, payload_sent: bool, status: int | None = None) -> HandoffAborted:
        self._event(stage, "aborted", reason, payload_sent)
        return HandoffAborted(stage, reason, payload_sent, status)

    def _send(self, url: str, path: str, body: bytes) -> tuple[int, bytes]:
        for secret in self._never_send:
            if secret in body:
                raise DisclosureBlocked("held_secret_in_outbound_body")
        return self.transport.request("POST", url, path, body)

    def discover(self, url: str, destination_id: str, kind: str) -> Any:
        """Phase 1: fetch and verify the destination card. Sends no task data at all."""
        endpoint(url)
        status, raw = self.transport.request("GET", url, CARD_PATH, None)
        if status != 200:
            raise self._abort("discovery", f"http_{status}", False, status)
        try:
            card = verify_card(parse_json(raw), self.trust, _now(self.clock))
        except TrustDenied as exc:
            raise self._abort("discovery", exc.reason, False) from exc
        except ContractError as exc:
            raise self._abort("discovery", "malformed_card", False) from exc
        if card.agent_id != destination_id:
            raise self._abort("discovery", "wrong_destination_identity", False)
        if card.endpoint != url:
            raise self._abort("discovery", "endpoint_mismatch", False)
        if self.schema_version not in card.schema_versions:
            raise self._abort("discovery", "unsupported_schema", False)
        if kind not in card.capabilities:
            raise self._abort("discovery", "capability_not_advertised", False)
        if card.enc_key is not None and not hpke_available():
            raise self._abort("discovery", "encryption_unavailable", False)  # never downgrade
        if card.enc_key is None and self.require_confidentiality:
            raise self._abort("discovery", "no_confidentiality_key", False)
        self._event("discovery", "verified", "card_verified", False)
        return card

    def delivery_seal(self, card: VerifiedCard, admission: dict[str, Any],
                      preflight: dict[str, Any]) -> DeliverySeal | None:
        """HPKE context for delivering against ``admission``; None if the card has no enc_key."""
        if card.enc_key is None:
            return None
        info = delivery_info(card_digest=card.digest, enc_kid=card.enc_key.kid,
                             movement_id=admission["movement_id"],
                             origin_id=preflight["payload"]["origin_card"]["payload"]["agent_id"],
                             audience=card.agent_id, endpoint_url=card.endpoint,
                             client_nonce=preflight["payload"]["client_nonce"],
                             admission_id=admission["admission_id"], preflight_digest=digest(preflight))
        return DeliverySeal(card.enc_key, info, secrets.token_bytes(32))

    def build_preflight(self, *, url: str, destination_id: str, movement_id: str, task_id: str,
                        kind: str, text: str, grant: dict[str, Any], idempotency_key: str,
                        trace_id: str, classification: str = "synthetic") -> tuple[bytes, dict[str, Any]]:
        salt = secrets.token_bytes(32)
        task = {"kind": kind, "text": text}
        payload = {"type": "preflight", "schema_version": self.schema_version,
                   "movement_id": movement_id, "logical_task_id": task_id, "origin_card": self.card,
                   "destination": {"agent_id": destination_id, "endpoint": url},
                   "task": {"kind": kind, "classification": classification,
                            "commitment": commitment(salt, task)},
                   "grant": grant, "client_nonce": b64e(secrets.token_bytes(24)),
                   "issued_at": _now(self.clock), "execution": {"idempotency_key": idempotency_key},
                   "observability": {"trace_id": trace_id}}
        sealed = seal("preflight", payload, self.key)
        return canonical(sealed).encode("utf-8"), {"sealed": sealed, "salt": salt, "task": task}

    def build_delivery(self, admission_id: str, task: dict[str, Any], salt: bytes,
                       sealed_to: DeliverySeal | None = None) -> bytes:
        """Signed delivery. With ``sealed_to`` the task, salt and response key travel only
        inside the HPKE ciphertext, and the origin signature covers that ciphertext."""
        payload: dict[str, Any] = {"type": "delivery", "schema_version": self.schema_version,
                                   "admission_id": admission_id}
        if sealed_to is None:
            payload.update(task=task, salt=b64e(salt))
        else:
            inner = {"task": task, "salt": b64e(salt), "response_key": b64e(sealed_to.response_key)}
            payload["enc"] = sealed_to.seal(canonical(inner).encode("utf-8"))
        return canonical(seal("delivery", payload, self.key)).encode("utf-8")

    def handoff(self, *, url: str, destination_id: str, movement_id: str, task_id: str, kind: str,
                text: str, grant: dict[str, Any], idempotency_key: str, trace_id: str,
                classification: str = "synthetic") -> dict[str, Any]:
        card = self.discover(url, destination_id, kind)
        body, secret = self.build_preflight(
            url=url, destination_id=destination_id, movement_id=movement_id, task_id=task_id,
            kind=kind, text=text, grant=grant, idempotency_key=idempotency_key, trace_id=trace_id,
            classification=classification)
        # Check the full delivery bytes too, *before* any metadata leaves the process.
        self._send_check(self.build_delivery("adm-" + "0" * 32, secret["task"], secret["salt"]))
        status, raw = self._send(url, PREFLIGHT_PATH, body)
        if status != 200:
            raise self._abort("preflight", _error_code(raw, status), False, status)
        try:
            admission = unseal("admission", parse_json(raw), card.key)
        except TrustDenied as exc:
            raise self._abort("preflight", f"admission_{exc.reason}", False) from exc
        except ContractError as exc:
            raise self._abort("preflight", "malformed_admission", False) from exc
        expected = {"agent_id": destination_id, "endpoint": url}
        if (admission.get("type") != "admission" or admission.get("destination") != expected
                or admission.get("client_nonce") != secret["sealed"]["payload"]["client_nonce"]
                or admission.get("preflight_digest") != digest(secret["sealed"])
                or admission.get("movement_id") != movement_id):
            raise self._abort("preflight", "admission_binding_mismatch", False)
        if type(admission.get("expires_at")) is not int or _now(self.clock) >= admission["expires_at"]:
            raise self._abort("preflight", "admission_expired", False)
        self._event("preflight", "verified", "admission_verified", False)
        try:
            sealed_to = self.delivery_seal(card, admission, secret["sealed"])
            body = self.build_delivery(admission["admission_id"], secret["task"], secret["salt"], sealed_to)
        except (ContractError, ValueError, TypeError) as exc:
            raise self._abort("delivery", "encryption_failed", False) from exc
        self._event("delivery", "sending", "hpke_sealed" if sealed_to else "plaintext_no_confidentiality",
                    False)
        status, raw = self._send(url, DELIVERY_PATH, body)
        if status != 200:
            raise self._abort("delivery", _error_code(raw, status), True, status)
        try:
            response = parse_json(raw)
            if sealed_to is not None:
                response = sealed_to.open_response(response)
            receipt = unseal("receipt", response, card.key)
        except (TrustDenied, ContractError) as exc:
            raise self._abort("delivery", "unverified_receipt", True) from exc
        if receipt.get("admission_id") != admission["admission_id"]:
            raise self._abort("delivery", "receipt_binding_mismatch", True)
        self._event("delivery", "completed", f"effect_{receipt.get('effect')}", True)
        return receipt

    def _send_check(self, body: bytes) -> None:
        for secret in self._never_send:
            if secret in body:
                self._event("guard", "aborted", "held_secret_in_outbound_body", False)
                raise DisclosureBlocked("held_secret_in_outbound_body")


def _error_code(raw: bytes, status: int) -> str:
    try:
        error = json.loads(raw.decode("utf-8")).get("error")
    except (ValueError, AttributeError):
        error = None
    return f"http_{status}_{error}" if isinstance(error, str) and safe_id(error) else f"http_{status}"
