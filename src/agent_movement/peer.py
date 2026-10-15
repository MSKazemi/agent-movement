"""Authenticated, pre-disclosure handoff over the synthetic trust model (issue #8).

Metadata first, payload last:

1. discovery  ``GET  /v0/agent-card``  -> CA-signed descriptor (public metadata only).
2. preflight  ``POST /v0/preflight``   -> origin-signed metadata, user grant, client nonce and a
   *salted commitment* to the task -- **no task text** -> receiver-signed admission that
   echoes the nonce (proves the receiver holds the key its card names).
3. delivery   ``POST /v0/deliveries``  -> origin-signed task text, sent only after 1 and 2
   verified on the sender side.

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
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from .core import (MAX_TEXT, SCHEMA_VERSION, Conflict, ContractError, PolicyDenied, SQLiteStore,
                   _fields, _id, canonical, digest, parse_json, validate_envelope)
from .trust import (CLASSIFICATIONS, PEER_SCHEMA_VERSION, TASK_KINDS, DisclosureBlocked,
                    TrustDenied, TrustStore, Unauthenticated, Unauthorized, UnsupportedSchema,
                    b64d, b64e, check_grant_live, check_grant_scope, commitment, endpoint,
                    safe_id, seal, sealed_parts, unseal, verify_card, verify_grant,
                    verify_revocation)

LOG = logging.getLogger("agent_movement.peer")
CARD_PATH, PREFLIGHT_PATH, DELIVERY_PATH, REVOCATION_PATH = (
    "/v0/agent-card", "/v0/preflight", "/v0/deliveries", "/v0/revocations")
PREFLIGHT_FIELDS = {"type", "schema_version", "movement_id", "logical_task_id", "origin_card",
                    "destination", "task", "grant", "client_nonce", "issued_at", "execution",
                    "observability"}
DELIVERY_FIELDS = {"type", "schema_version", "admission_id", "task", "salt"}
TRACE_FIELDS = ("seq", "at", "stage", "outcome", "reason", "movement_id", "peer",
                "claimed_peer", "admission_id")
_NONCE = re.compile(r"[A-Za-z0-9_-]{22,64}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_ADMISSION = re.compile(r"adm-[0-9a-f]{32}\Z")


class HandoffAborted(PolicyDenied):
    """Sender stopped a handoff. ``payload_sent`` says whether task text left the process."""

    def __init__(self, stage: str, reason: str, payload_sent: bool, status: int | None = None):
        super().__init__(f"{stage}: {reason}")
        self.stage, self.reason, self.payload_sent, self.status = stage, reason, payload_sent, status


def _now(clock: Callable[[], float]) -> int:
    return int(clock())


# ------------------------------------------------------------------- ledger


class PeerLedger:
    """Receiver-side nonces, admissions, revocations, authorized effects and sanitized traces.

    Lives in the same SQLite file as ``SQLiteStore``. Stores IDs, reason codes and digests
    of metadata only -- never task text, salts, signatures or key material.
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

    def trace(self, stage: str, outcome: str, reason: str, ctx: "TraceContext") -> None:
        event = {"at": datetime.now(timezone.utc).isoformat(), "stage": stage, "outcome": outcome,
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
        return [dict(zip(TRACE_FIELDS, row)) for row in rows]

    def authority_log(self) -> list[dict[str, Any]]:
        with self.store._connection() as db:
            rows = db.execute("SELECT seq,event,grant_id,ref FROM authority_log ORDER BY seq").fetchall()
        return [dict(zip(("seq", "event", "grant_id", "ref"), row)) for row in rows]

    def effects(self) -> list[dict[str, Any]]:
        with self.store._connection() as db:
            rows = db.execute("SELECT task_id,effect_id,grant_id,agent_id,log_seq FROM authorized_effects "
                              "ORDER BY log_seq").fetchall()
        return [dict(zip(("task_id", "effect_id", "grant_id", "agent_id", "log_seq"), row)) for row in rows]


class AuthorizedEffectGateway:
    """Simulated external effect that re-verifies the user grant at the commit point.

    Closes the PR #6 gap "receiver grant not rechecked at simulated effect commit": the
    revocation lookup, the expiry check (clock read inside the transaction) and the effect
    insert share one ``BEGIN IMMEDIATE`` transaction, and ``PeerLedger.revoke`` takes the same
    write lock, so revocations and commits are linearized. Still simulated: a real tool
    would need the same check on *its* side of the boundary.
    """

    def __init__(self, ledger: PeerLedger, clock: Callable[[], float] = time.time):
        self.ledger = ledger
        self.clock = clock

    def commit(self, grant: dict[str, Any], agent_id: str, task_id: str, effect_id: str,
               payload: str) -> bool:
        """True for a new commit, False for an identical replay; raises Unauthorized."""
        _id(agent_id, "agent_id")
        _id(task_id, "task_id")
        _id(effect_id, "effect_id")
        if not isinstance(payload, str) or len(payload.encode("utf-8")) > MAX_TEXT:
            raise ContractError("invalid payload")
        fingerprint = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        with self.ledger.store._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            check_grant_live(grant, now=_now(self.clock),
                             revoked=self.ledger.is_revoked(db, grant["grant_id"]))
            if grant["audience"] != agent_id:
                raise Unauthorized("wrong_audience")
            if grant["task_id"] != task_id:
                raise Unauthorized("wrong_task")
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
                 before_effect_commit: Callable[[dict[str, Any]], None] | None = None):
        own = verify_card(card, trust, _now(clock))
        if own.key.kid != key.kid:
            raise ContractError("receiver card does not name the receiver key")
        allow = frozenset(capabilities)
        if not allow or not allow <= TASK_KINDS:
            raise ContractError("capability allowlist must be a non-empty subset of known task kinds")
        self.card, self.key, self.trust, self.store = card, key, trust, store
        self.agent_id, self.endpoint, self.capabilities = own.agent_id, own.endpoint, allow
        self.admission_ttl, self.max_clock_skew, self.clock = admission_ttl, max_clock_skew, clock
        self.before_effect_commit = before_effect_commit
        self.ledger = PeerLedger(store)
        self.effects = AuthorizedEffectGateway(self.ledger, clock)

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
                  "expires_at": expires_at}
        with self.store._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            check_grant_live(grant, now=now, revoked=self.ledger.is_revoked(db, grant["grant_id"]))
            db.execute("DELETE FROM peer_nonces WHERE seen_at < ?", (now - 2 * self.max_clock_skew,))
            try:
                db.execute("INSERT INTO peer_nonces VALUES(?,?,?)", (origin.agent_id, p["client_nonce"], now))
            except sqlite3.IntegrityError as exc:
                raise Conflict("replayed preflight nonce") from exc
            try:
                db.execute("INSERT INTO peer_admissions VALUES(?,?,?,?)",
                           (admission_id, movement_id, canonical(record), expires_at))
            except sqlite3.IntegrityError as exc:
                raise Conflict("movement ID already admitted") from exc
            db.commit()
        ctx.admission_id = admission_id
        admission = {"type": "admission", "admission_id": admission_id, "movement_id": movement_id,
                     "destination": {"agent_id": self.agent_id, "endpoint": self.endpoint},
                     "client_nonce": p["client_nonce"], "preflight_digest": digest(sealed),
                     "expires_at": expires_at}
        return 200, seal("admission", admission, self.key), "admitted"

    # -- phase 3: payload delivery ------------------------------------------------------
    def _deliver(self, body: bytes, ctx: TraceContext) -> tuple[int, dict[str, Any], str]:
        sealed = parse_json(body)
        p = sealed_parts(sealed, "delivery")["payload"]
        if p.get("schema_version") != PEER_SCHEMA_VERSION:
            raise UnsupportedSchema("unsupported peer schema")
        _fields(p, DELIVERY_FIELDS, "delivery")
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
        unseal("delivery", sealed, origin.key)  # same peer that was admitted
        ctx.peer = origin.agent_id
        if now >= record["expires_at"]:
            raise Unauthorized("admission_expired")
        task = _fields(p["task"], {"kind", "text"}, "task")
        if task["kind"] != record["kind"] or commitment(b64d(p["salt"], "salt"), task) != record["commitment"]:
            raise Unauthorized("commitment_mismatch")
        grant = verify_grant(record["grant"], self.trust)
        with self.store._connection() as db:
            check_grant_live(grant, now=now, revoked=self.ledger.is_revoked(db, grant["grant_id"]))
        envelope = validate_envelope({
            "schema_version": SCHEMA_VERSION, "movement_id": record["movement_id"],
            "logical_task_id": record["logical_task_id"], "operation": "delegate",
            "origin": {"agent_id": origin.agent_id}, "destination": {"agent_id": self.agent_id},
            "task": task, "context": {"classification": record["classification"]},
            "authority": {"approval_ref": grant["grant_id"]},
            "execution": {"idempotency_key": record["idempotency_key"]},
            "observability": {"trace_id": record["trace_id"]}})
        receipt = self.store.receive(envelope)  # pure, idempotent computation
        if self.before_effect_commit is not None:
            self.before_effect_commit(record)  # test seam: inject races here
        try:
            committed = self.effects.commit(grant, self.agent_id, record["logical_task_id"],
                                            f"{record['movement_id']}.result", canonical(receipt["artifact"]))
        except Unauthorized as exc:
            raise Unauthorized(f"effect_{exc.reason}") from exc
        response = {"type": "receipt", "admission_id": p["admission_id"],
                    "movement_id": record["movement_id"], "receipt": receipt,
                    "effect": "committed" if committed else "replayed"}
        return 200, seal("receipt", response, self.key), "effect_committed" if committed else "effect_replayed"

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


class HttpTransport:
    """Loopback-only HTTP client transport."""

    def request(self, method: str, url: str, path: str, body: bytes | None) -> tuple[int, bytes]:
        if not url.startswith("http://127.0.0.1:"):
            raise ContractError("HTTP transport is loopback-only")
        headers = {"Content-Type": "application/json"} if body is not None else {}
        request = urllib.request.Request(url + path, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()


@dataclass
class RecordingTransport:
    """Captures every byte exchanged so tests can prove what was (not) transmitted."""

    inner: Any
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


class PeerClient:
    """Origin side. Never transmits task text before discovery and preflight verify."""

    def __init__(self, card: dict[str, Any], key: Any, trust: TrustStore, transport: Any, *,
                 never_send: Iterable[str | bytes] = (), clock: Callable[[], float] = time.time,
                 schema_version: str = PEER_SCHEMA_VERSION):
        self.card, self.key, self.trust, self.transport = card, key, trust, transport
        self.clock, self.schema_version = clock, schema_version
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
        self._event("discovery", "verified", "card_verified", False)
        return card

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

    def build_delivery(self, admission_id: str, task: dict[str, Any], salt: bytes) -> bytes:
        payload = {"type": "delivery", "schema_version": self.schema_version,
                   "admission_id": admission_id, "task": task, "salt": b64e(salt)}
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
        status, raw = self._send(url, DELIVERY_PATH,
                                 self.build_delivery(admission["admission_id"], secret["task"], secret["salt"]))
        if status != 200:
            raise self._abort("delivery", _error_code(raw, status), True, status)
        try:
            receipt = unseal("receipt", parse_json(raw), card.key)
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
