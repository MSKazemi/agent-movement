"""Strict synthetic handoffs and durable simulated-effect fencing.

This is an application-level experiment. No sender identity authentication, A2A,
remote authorization, external tools, or general checkpoint migration is provided.
Approvals can be revoked at runtime with a notice signed by a pinned synthetic
authority (issue #38, :meth:`HandoffReceiver.revoke`); the revocation is checked at
admission and again inside the simulated effect-commit transaction.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "0.1.0-draft"
ID = re.compile(r"[A-Za-z][A-Za-z0-9._:-]{0,127}\Z")
MAX_TEXT = 2048
# SQLiteStore layout, kept in PRAGMA user_version. 0: unversioned PR #6 layout with
# global idempotency keys. 1: keys scoped to (sender, key); see SQLiteStore._ensure_schema.
# 2: every stored content digest is a keyed commitment under a per-store secret, stored
# receipts carry no content-derived fields, and deliveries record when they were made
# (issue #39; see docs/data-retention.md).
STORE_SCHEMA_VERSION = 2
# Domain separation for SQLiteStore.keyed_digest; change the suffix if the construction changes.
_COMMITMENT_LABEL = b"agent-movement/store-commitment/v1\x00"
# Receipt fields derived from task content. They are recomputed from the presented envelope
# on every (re)delivery -- the tasks are pure -- and are never written to the store.
RECEIPT_CONTENT_FIELDS = ("envelope_digest", "artifact", "artifact_digest")
# The version-1 deliveries layout, frozen for the 0 -> 1 migration.
_DELIVERIES_V1 = """CREATE TABLE IF NOT EXISTS {name} (
        sender_id TEXT NOT NULL,
        idempotency_key TEXT NOT NULL,
        movement_id TEXT NOT NULL UNIQUE,
        envelope_digest TEXT NOT NULL,
        receipt_json TEXT NOT NULL,
        PRIMARY KEY (sender_id, idempotency_key))"""
# The per-store secret. Never part of audit(), receipts or any export; see keyed_digest.
_STORE_SECRET = """CREATE TABLE IF NOT EXISTS store_secret (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        hmac_key BLOB NOT NULL,
        created_at TEXT NOT NULL)"""  # noqa: S105 - table DDL, not a secret
_TABLES = (
    # Index 0 is formatted with a table name so a migration can build a copy first.
    # envelope_digest holds SQLiteStore.fingerprint(envelope), a keyed commitment.
    """CREATE TABLE IF NOT EXISTS {name} (
        sender_id TEXT NOT NULL,
        idempotency_key TEXT NOT NULL,
        movement_id TEXT NOT NULL UNIQUE,
        envelope_digest TEXT NOT NULL,
        receipt_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (sender_id, idempotency_key))""",
    """CREATE TABLE IF NOT EXISTS audit_events (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        movement_id TEXT NOT NULL,
        task_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        info_digest TEXT NOT NULL,
        event_time TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS owners (
        task_id TEXT PRIMARY KEY,
        agent_id TEXT NOT NULL,
        epoch INTEGER NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS effects (
        task_id TEXT NOT NULL,
        effect_id TEXT NOT NULL,
        payload_digest TEXT NOT NULL,
        epoch INTEGER NOT NULL,
        PRIMARY KEY (task_id, effect_id))""",
)
# Runtime approval revocation (issue #38). Created with IF NOT EXISTS beside the versioned
# layout above, like the peer ledger's tables, so a file of any version gains them on open.
_REVOCATION_TABLES = """
    CREATE TABLE IF NOT EXISTS approval_revocations (
        approval_ref TEXT PRIMARY KEY,
        issuer TEXT NOT NULL,
        claimed_revoked_at INTEGER NOT NULL,
        notice_digest TEXT NOT NULL,
        recorded_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS task_approvals (
        task_id TEXT NOT NULL,
        approval_ref TEXT NOT NULL,
        PRIMARY KEY (task_id, approval_ref));
"""
# Digest columns of OTHER modules' tables that can share a store file. The 1 -> 2 migration
# wraps them with the store key as well, so no plain content digest survives the upgrade.
_FOREIGN_DIGEST_COLUMNS = (
    ("authorized_effects", "payload_digest"),  # agent_movement.peer
    ("a2a_correlations", "envelope_digest"),   # agent_movement.a2a_profile
    ("a2a_correlations", "artifact_digest"),
)


class ContractError(ValueError):
    """Input failed the narrow experimental transfer contract."""


class PolicyDenied(ValueError):
    """Requested operation is not approved. Not an authentication guarantee."""


class Conflict(ValueError):
    """Idempotency collision, stale authority or incompatible task state."""


class StoreSchemaError(RuntimeError):
    """The SQLite file has a layout this code cannot use or migrate."""


class ApprovalRevoked(PolicyDenied):
    """The approval was revoked at runtime; checked at admission and at effect commit."""

    def __init__(self, approval_ref: str):
        super().__init__("approval revoked")
        self.approval_ref = approval_ref


class RevocationRejected(PolicyDenied):
    """A revocation notice was not applied. ``reason`` is a machine-readable code.

    ``unknown_approval``: the notice verified but names no approval of this receiver.
    Every other reason means the notice did not verify against a pinned authority.
    """

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for name, value in pairs:
        if name in obj:
            raise ContractError("duplicate JSON property")
        obj[name] = value
    return obj


def parse_json(raw: bytes) -> Any:
    if len(raw) > 16384:
        raise ContractError("JSON body exceeds local limit")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(ContractError("invalid number")))
    except ContractError:
        raise
    # ValueError covers JSONDecodeError, UnicodeDecodeError and the int-digit limit
    # (>4300 digits); RecursionError covers deeply nested arrays/objects.
    except (ValueError, RecursionError) as exc:
        raise ContractError("invalid JSON") from exc


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _fields(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ContractError(f"invalid {label} fields")
    return value


def _id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ContractError(f"invalid {label}")
    return value


def validate_envelope(value: Any) -> dict[str, Any]:
    v = _fields(value, {"schema_version", "movement_id", "logical_task_id", "operation",
                        "origin", "destination", "task", "context", "authority",
                        "execution", "observability"}, "envelope")
    if v["schema_version"] != SCHEMA_VERSION or v["operation"] != "delegate":
        raise ContractError("unsupported schema version or operation")
    _id(v["movement_id"], "movement_id")
    _id(v["logical_task_id"], "logical_task_id")
    origin = _fields(v["origin"], {"agent_id"}, "origin")
    dest = _fields(v["destination"], {"agent_id"}, "destination")
    _id(origin["agent_id"], "origin.agent_id")
    _id(dest["agent_id"], "destination.agent_id")
    task = _fields(v["task"], {"kind", "text"}, "task")
    if task["kind"] not in ("word_count", "sha256"):
        raise ContractError("unsupported task kind")
    try:
        # Lone surrogates (e.g. JSON "\ud800") are valid JSON but not encodable UTF-8.
        text_bytes = task["text"].encode("utf-8") if isinstance(task["text"], str) else None
    except UnicodeEncodeError:
        text_bytes = None
    if text_bytes is None or len(text_bytes) > MAX_TEXT:
        raise ContractError("task text must be UTF-8 and at most 2048 bytes")
    ctx = _fields(v["context"], {"classification"}, "context")
    if ctx["classification"] not in ("synthetic", "public"):
        raise ContractError("unsupported data classification")
    approval = _fields(v["authority"], {"approval_ref"}, "authority")
    exec_ = _fields(v["execution"], {"idempotency_key"}, "execution")
    trace = _fields(v["observability"], {"trace_id"}, "observability")
    _id(approval["approval_ref"], "approval_ref")
    _id(exec_["idempotency_key"], "idempotency_key")
    _id(trace["trace_id"], "trace_id")
    return v


def _artifact(task: dict[str, Any]) -> dict[str, Any]:
    if task["kind"] == "word_count":
        return {"kind": "word_count", "value": len(task["text"].split())}
    return {"kind": "sha256", "value": hashlib.sha256(task["text"].encode("utf-8")).hexdigest()}


def build_receipt(envelope: dict[str, Any]) -> dict[str, Any]:
    """The completion receipt of a validated envelope: a pure function of the envelope."""
    artifact = _artifact(envelope["task"])
    return {
        "status": "completed",
        "movement_id": envelope["movement_id"],
        "logical_task_id": envelope["logical_task_id"],
        "origin_agent_id": envelope["origin"]["agent_id"],
        "destination_agent_id": envelope["destination"]["agent_id"],
        "trace_id": envelope["observability"]["trace_id"],
        "envelope_digest": digest(envelope),
        "artifact": artifact,
        "artifact_digest": digest(artifact),
    }


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class Approval:
    """Preconfigured receiver-side grant for exactly one synthetic/public task.

    ``revoked`` is a static configuration flag fixed at construction. Runtime revocation
    goes through :meth:`HandoffReceiver.revoke` and is persisted in the store.
    """

    ref: str
    task_id: str
    origin_id: str
    destination_id: str
    kind: str
    classification: str = "synthetic"
    expires_at: datetime | None = None
    revoked: bool = False

    def allows(self, envelope: dict[str, Any], now: datetime) -> bool:
        if self.revoked or (self.expires_at is not None and
                            (self.expires_at.tzinfo is None or now >= self.expires_at)):
            return False
        return bool(envelope["authority"]["approval_ref"] == self.ref
                and envelope["logical_task_id"] == self.task_id
                and envelope["origin"]["agent_id"] == self.origin_id
                and envelope["destination"]["agent_id"] == self.destination_id
                and envelope["task"]["kind"] == self.kind
                and envelope["context"]["classification"] == self.classification)


class SQLiteStore:
    """Transactional synthetic delivery results plus a separate fenced effect ledger.

    Content digests (of envelopes, artifacts and effect payloads) are stored only as keyed
    commitments under a random per-store secret (:meth:`keyed_digest`), so the file, its
    audit export and its logs cannot be used to confirm a guess of low-entropy task text
    without that secret. Equal inputs still map to equal commitments within one store,
    which is all that replay and idempotent-retry detection need.
    """

    def __init__(self, path: str | Path):
        self.path = str(path)
        self._enable_wal()
        self._ensure_schema()
        with self._connection() as db:
            self._key = self._read_key(db)
        self._ensure_revocation_tables()

    def _ensure_schema(self) -> None:
        """Create the tables, or migrate an older file in place, in ONE write transaction.

        ``PRAGMA user_version`` records the layout. 0 is the unversioned PR #6 layout,
        whose ``deliveries`` table keyed idempotency keys globally; 1 stored plain SHA-256
        content digests. Concurrent openers serialize on ``BEGIN IMMEDIATE`` and re-read
        the version under the lock, so exactly one of them migrates and the others see
        the result.
        """
        with self._connection() as db:
            if db.execute("PRAGMA user_version").fetchone()[0] == STORE_SCHEMA_VERSION:
                return
            # Overwrite the plain digests the migration replaces instead of leaving them in
            # free pages; the TRUNCATE checkpoint below then clears them from the WAL.
            db.execute("PRAGMA secure_delete = ON")
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > STORE_SCHEMA_VERSION:
                raise StoreSchemaError(f"store schema version {version} is newer than the "
                                       f"supported version {STORE_SCHEMA_VERSION}")
            if version == STORE_SCHEMA_VERSION:  # another opener migrated while we waited
                db.commit()
                return
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            db.execute(_STORE_SECRET)
            if db.execute("SELECT 1 FROM store_secret WHERE id = 1").fetchone() is None:
                db.execute("INSERT INTO store_secret VALUES(1,?,?)", (secrets.token_bytes(32), utc_now_iso()))
            columns = {row[1] for row in db.execute("PRAGMA table_info(deliveries)")}
            if columns and "sender_id" not in columns:
                self._migrate_global_keys(db)
            self._migrate_commitments(db, self._read_key(db), tables)
            for statement in _TABLES:
                db.execute(statement.format(name="deliveries"))
            db.execute(f"PRAGMA user_version = {STORE_SCHEMA_VERSION}")
            db.commit()
            if version > 0 or tables:  # an existing file was rewritten
                db.execute("PRAGMA wal_checkpoint(TRUNCATE)")  # best effort; busy readers delay it

    @staticmethod
    def _read_key(db: sqlite3.Connection) -> bytes:
        try:
            row = db.execute("SELECT hmac_key FROM store_secret WHERE id = 1").fetchone()
        except sqlite3.OperationalError:  # no such table
            row = None
        if row is None or not isinstance(row[0], bytes) or len(row[0]) < 32:
            # Never mint a fresh key here: every stored commitment would silently stop
            # matching, turning exact retries into idempotency conflicts.
            raise StoreSchemaError("store secret is missing or invalid; stored commitments cannot be checked")
        return row[0]

    @staticmethod
    def _keyed(key: bytes, sha256_hex: str) -> str:
        return hmac.new(key, _COMMITMENT_LABEL + str(sha256_hex).encode("utf-8"), hashlib.sha256).hexdigest()

    def keyed_digest(self, sha256_hex: str) -> str:
        """HMAC-SHA256 commitment, under this store's secret, to a plain SHA-256 hex digest.

        Wrapping the digest (rather than the raw value) is what lets the 1 -> 2 migration
        convert stored plain digests without the original content.
        """
        return self._keyed(self._key, sha256_hex)

    def fingerprint(self, value: Any) -> str:
        """Keyed commitment to a JSON value: ``keyed_digest(digest(value))``."""
        return self.keyed_digest(digest(value))

    def _migrate_commitments(self, db: sqlite3.Connection, key: bytes, tables: set[str]) -> None:
        """Version 1 -> 2: replace every stored plain content digest by its keyed commitment.

        ``deliveries`` is rebuilt (SQLite create/copy/drop/rename procedure) to add
        ``created_at`` -- backfilled from the movement's earliest audit event, else the
        migration time -- and its receipts lose the content-derived fields, which
        :meth:`receive` recomputes from the presented envelope. Digest columns elsewhere
        are wrapped in place. Equality is preserved: a retry after the upgrade computes
        ``keyed(sha256(content))``, exactly the wrapped value.
        """
        def keyed(value: Any) -> Any:
            return None if value is None else self._keyed(key, value)

        db.create_function("am_keyed", 1, keyed, deterministic=True)
        if "deliveries" in tables:
            db.execute(_TABLES[0].format(name="deliveries_v2"))
            now = utc_now_iso()
            first_seen = dict(db.execute("SELECT movement_id, event_time FROM audit_events "
                                         "ORDER BY seq DESC").fetchall()) if "audit_events" in tables else {}
            rows = db.execute("SELECT sender_id, idempotency_key, movement_id, envelope_digest, receipt_json "
                              "FROM deliveries ORDER BY rowid").fetchall()
            for sender, key_, movement_id, envelope_digest, receipt_json in rows:
                try:
                    stored = json.loads(receipt_json)
                    stored = {k: v for k, v in stored.items() if k not in RECEIPT_CONTENT_FIELDS}
                except (ValueError, AttributeError) as exc:
                    raise StoreSchemaError(f"cannot migrate delivery {movement_id!r}: "
                                           "stored receipt is not a JSON object") from exc
                db.execute("INSERT INTO deliveries_v2 VALUES(?,?,?,?,?,?)",
                           (sender, key_, movement_id, keyed(envelope_digest), canonical(stored),
                            first_seen.get(movement_id, now)))
            db.execute("DROP TABLE deliveries")
            db.execute("ALTER TABLE deliveries_v2 RENAME TO deliveries")
        for table, column in (("audit_events", "info_digest"), ("effects", "payload_digest"),
                              *_FOREIGN_DIGEST_COLUMNS):
            if table in tables:
                db.execute(f"UPDATE {table} SET {column} = am_keyed({column})")

    @staticmethod
    def _migrate_global_keys(db: sqlite3.Connection) -> None:
        """Version 0 -> 1: scope idempotency keys to their sender.

        Follows the SQLite procedure for schema changes ALTER TABLE cannot express
        (create, copy, drop, rename). Every version-0 receipt names its origin, and on
        both receiver paths the envelope origin *is* the sender the new key is scoped to
        (the peer path builds the envelope from the authenticated origin), so the copy
        is exact. Old global keys stay unique per sender, and ``movement_id`` keeps its
        UNIQUE constraint, so no row can conflict.
        """
        db.execute(_DELIVERIES_V1.format(name="deliveries_v1"))
        rows = db.execute("SELECT idempotency_key, movement_id, envelope_digest, receipt_json "
                          "FROM deliveries ORDER BY rowid").fetchall()
        for key, movement_id, envelope_digest, receipt_json in rows:
            try:
                sender = _id(json.loads(receipt_json)["origin_agent_id"], "origin_agent_id")
            except (ValueError, KeyError, TypeError) as exc:
                raise StoreSchemaError(f"cannot migrate delivery {movement_id!r}: "
                                       "stored receipt names no valid origin") from exc
            db.execute("INSERT INTO deliveries_v1 VALUES(?,?,?,?,?)",
                       (sender, key, movement_id, envelope_digest, receipt_json))
        db.execute("DROP TABLE deliveries")
        db.execute("ALTER TABLE deliveries_v1 RENAME TO deliveries")

    def _enable_wal(self, deadline_s: float = 10.0) -> None:
        """Switch the file to WAL once (the mode is persistent).

        Changing journal_mode needs an exclusive lock and SQLite can return
        SQLITE_BUSY *without* consulting busy_timeout (deadlock avoidance) while
        another connection writes to a fresh rollback-journal file, so retry.
        """
        deadline = time.monotonic() + deadline_s
        while True:
            db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
            try:
                db.execute("PRAGMA busy_timeout = 10000")
                db.execute("PRAGMA journal_mode = WAL")
                return
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc) and "busy" not in str(exc):
                    raise
                if time.monotonic() >= deadline:
                    raise
            finally:
                db.close()
            time.sleep(0.02)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        try:
            db.execute("PRAGMA busy_timeout = 10000")
            yield db
            if db.in_transaction:
                db.commit()
        except BaseException:
            if db.in_transaction:
                db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _event(db: sqlite3.Connection, movement_id: str, task_id: str,
               event_type: str, fingerprint: str) -> None:
        db.execute("INSERT INTO audit_events(movement_id,task_id,event_type,info_digest,event_time) "
                   "VALUES(?,?,?,?,?)", (movement_id, task_id, event_type, fingerprint, utc_now_iso()))

    def denied(self, envelope: dict[str, Any]) -> None:
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self._event(db, envelope["movement_id"], envelope["logical_task_id"],
                        "handoff.denied", self.fingerprint(envelope))
            db.commit()

    def receive(self, envelope: dict[str, Any], sender: str | None = None,
                approval_ref: str | None = None) -> dict[str, Any]:
        """Execute a *pure* preapproved task transactionally, memoizing its receipt.

        Idempotency keys are scoped to ``sender``: the authenticated sender when the
        caller knows it (``PeerReceiver``), else the envelope's *claimed* origin
        (``HandoffReceiver``, which authenticates nobody). Two senders may therefore use
        the same key. Movement IDs stay unique across all senders.

        Any task enrolled in ``GuardedAuthority`` is denied on this
        **legacy/core handoff path** (including replays) under the same SQLite
        write lock as enrollment. This is a bounded store-level ingress fence,
        not sender authentication or an all-adapter network control.

        ``approval_ref`` (``HandoffReceiver``) is the approval that admitted the envelope.
        Inside the same write transaction a runtime revocation of it raises
        ``ApprovalRevoked`` (replays included), and a new delivery binds the task to it, so
        ``EffectGateway.commit`` rechecks that approval for every effect of the task.

        The returned receipt is unchanged by issue #39 (its ``envelope_digest`` and
        ``artifact_digest`` are plain SHA-256, so the sender can check them), but the store
        keeps only a keyed commitment to the envelope and a receipt without its
        content-derived fields; a replay recomputes those from the presented envelope,
        which the commitment check proved equal to the original.
        """
        receipt = build_receipt(envelope)
        fingerprint = self.fingerprint(envelope)
        key = envelope["execution"]["idempotency_key"]
        sender_id = envelope["origin"]["agent_id"] if sender is None else _id(sender, "sender")
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            # An enrolled guarded task must never be accepted through the
            # unauthenticated legacy/core handoff lane, including idempotent
            # replays. Enrollment and admission share the same write lock, so
            # a concurrent enrollment cannot race between this check and
            # durable receipt insertion. Peer/guarded authority has its own
            # separately authenticated ingress.
            EffectGateway._deny_guarded(db, envelope["logical_task_id"])
            if approval_ref is not None and self._approval_revoked(db, approval_ref):
                raise ApprovalRevoked(approval_ref)
            previous = db.execute("SELECT envelope_digest FROM deliveries "
                                  "WHERE sender_id = ? AND idempotency_key = ?",
                                  (sender_id, key)).fetchone()
            if previous is not None:
                if not hmac.compare_digest(previous[0], fingerprint):
                    raise Conflict("idempotency key reused with different envelope")
                db.commit()
                return {**receipt, "replayed": True}
            if db.execute("SELECT 1 FROM deliveries WHERE movement_id=?",
                          (envelope["movement_id"],)).fetchone():
                raise Conflict("movement ID already used under another idempotency key or sender")
            stored = {k: v for k, v in receipt.items() if k not in RECEIPT_CONTENT_FIELDS}
            self._event(db, receipt["movement_id"], receipt["logical_task_id"],
                        "handoff.accepted", fingerprint)
            db.execute("INSERT INTO deliveries(sender_id,idempotency_key,movement_id,envelope_digest,"
                       "receipt_json,created_at) VALUES(?,?,?,?,?,?)",
                       (sender_id, key, envelope["movement_id"], fingerprint, canonical(stored),
                        utc_now_iso()))
            if approval_ref is not None:
                db.execute("INSERT OR IGNORE INTO task_approvals VALUES(?,?)",
                           (envelope["logical_task_id"], approval_ref))
            self._event(db, receipt["movement_id"], receipt["logical_task_id"],
                        "handoff.completed", self.keyed_digest(receipt["artifact_digest"]))
            db.commit()
            return {**receipt, "replayed": False}

    def audit(self) -> list[dict[str, Any]]:
        with self._connection() as db:
            rows = db.execute("SELECT movement_id,task_id,event_type,info_digest,event_time "
                              "FROM audit_events ORDER BY seq").fetchall()
        names = ("movement_id", "task_id", "event_type", "info_digest", "event_time")
        return [dict(zip(names, row, strict=True)) for row in rows]

    # -- runtime approval revocation (issue #38) ---------------------------------------
    # Revocation audit events are not tied to a movement: their movement_id is "". Like every
    # audit digest they are keyed commitments; approval_revocations keeps the plain SHA-256 of
    # the notice, a public signed document, so it can be matched against the notice itself.

    def _ensure_revocation_tables(self) -> None:
        with self._connection() as db:
            db.executescript(_REVOCATION_TABLES)

    @staticmethod
    def _approval_revoked(db: sqlite3.Connection, approval_ref: str) -> bool:
        return db.execute("SELECT 1 FROM approval_revocations WHERE approval_ref=?",
                          (approval_ref,)).fetchone() is not None

    @staticmethod
    def _revoked_task_approval(db: sqlite3.Connection, task_id: str) -> str | None:
        """A revoked approval that a delivery of ``task_id`` was admitted under, if any."""
        row = db.execute("SELECT t.approval_ref FROM task_approvals t JOIN approval_revocations r "
                         "ON r.approval_ref = t.approval_ref WHERE t.task_id=? "
                         "ORDER BY t.approval_ref LIMIT 1", (task_id,)).fetchone()
        return None if row is None else row[0]

    def revoke_approval(self, approval_ref: str, task_id: str, *, issuer: str,
                        claimed_revoked_at: int, notice_digest: str) -> bool:
        """Persist a verified revocation. True if new; False if the approval was already
        revoked (idempotent: the first notice stays the record and no event is added).

        Takes the same write lock as ``receive`` and ``EffectGateway.commit``, so a
        revocation and a delivery or effect commit are linearized: whichever commits
        first wins. ``claimed_revoked_at`` is the issuer's claim, kept for the record; the
        revocation takes effect when this transaction commits.
        """
        _id(approval_ref, "approval_ref")
        _id(task_id, "task_id")
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if self._approval_revoked(db, approval_ref):
                db.commit()
                return False
            db.execute("INSERT INTO approval_revocations VALUES(?,?,?,?,?)",
                       (approval_ref, issuer, claimed_revoked_at, notice_digest, utc_now_iso()))
            self._event(db, "", task_id, "approval.revoked", self.keyed_digest(notice_digest))
            db.commit()
            return True

    def revocation_rejected(self, notice_digest: str) -> None:
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self._event(db, "", "", "approval.revocation_rejected", self.keyed_digest(notice_digest))
            db.commit()

    def revocations(self) -> list[dict[str, Any]]:
        names = ("approval_ref", "issuer", "claimed_revoked_at", "notice_digest", "recorded_at")
        with self._connection() as db:
            rows = db.execute(f"SELECT {','.join(names)} FROM approval_revocations "
                              "ORDER BY recorded_at, approval_ref").fetchall()
        return [dict(zip(names, row, strict=True)) for row in rows]


class HandoffReceiver:
    """Receiver-local admission against preconfigured approvals.

    ``revocation_authorities`` pins the keys (``trust.HmacKey``, or ``trust.Ed25519Key``
    with the optional extra) whose signed notices may revoke this receiver's approvals at
    runtime. With none pinned, :meth:`revoke` rejects every notice.
    """

    def __init__(self, name: str, store: SQLiteStore, approvals: list[Approval],
                 revocation_authorities: Iterable[Any] = ()):
        self.name = name
        self.store = store
        self.approvals = tuple(approvals)
        authorities = tuple(revocation_authorities)
        self._revocation_trust = None
        if authorities:
            from .trust import TrustStore  # trust.py imports this module
            self._revocation_trust = TrustStore.build((), authorities)

    def receive(self, message: Any) -> dict[str, Any]:
        envelope = validate_envelope(message)
        now = datetime.now(UTC)
        if envelope["destination"]["agent_id"] != self.name or not any(
                a.allows(envelope, now) for a in self.approvals):
            self.store.denied(envelope)
            raise PolicyDenied("receiver-side approval not found, valid or scoped for this transfer")
        try:
            return self.store.receive(envelope, approval_ref=envelope["authority"]["approval_ref"])
        except PolicyDenied:
            # The store applies guard enrollment/revocation atomically. Record
            # a sanitized denied handoff outside the rolled-back transaction
            # without accidentally returning a successful legacy receipt.
            self.store.denied(envelope)
            raise

    def revoke(self, notice: Any) -> dict[str, Any]:
        """Apply a signed revocation notice (issue #8 format) to one of this receiver's approvals.

        The notice is ``trust.issue_revocation(authority_key, approval_ref, revoked_at)``:
        its ``grant_id`` names the approval. It must verify against a pinned revocation
        authority; anything else (unsigned, forged, tampered, untrusted issuer, malformed)
        raises ``RevocationRejected`` and is audited as ``approval.revocation_rejected``.
        A verified notice is effective as soon as this call returns: new and replayed
        handoffs under the approval are denied, and so are effect commits for every task a
        delivery was admitted under it. Revoking again is idempotent (``replayed: True``).
        There is no un-revoke.
        """
        try:
            notice_digest = digest(notice)
        except (TypeError, ValueError) as exc:
            raise ContractError("revocation notice is not JSON") from exc
        if self._revocation_trust is None:
            self.store.revocation_rejected(notice_digest)
            raise RevocationRejected("no_revocation_authority")
        from .trust import TrustDenied, verify_revocation
        try:
            payload = verify_revocation(notice, self._revocation_trust)
        except TrustDenied as exc:
            self.store.revocation_rejected(notice_digest)
            raise RevocationRejected(exc.reason) from exc
        approval = next((a for a in self.approvals if a.ref == payload["grant_id"]), None)
        if approval is None:
            self.store.revocation_rejected(notice_digest)
            raise RevocationRejected("unknown_approval")
        new = self.store.revoke_approval(approval.ref, approval.task_id, issuer=payload["issuer"],
                                         claimed_revoked_at=payload["revoked_at"],
                                         notice_digest=notice_digest)
        return {"status": "revoked", "approval_ref": approval.ref, "logical_task_id": approval.task_id,
                "notice_digest": notice_digest, "replayed": not new}


class EffectGateway:
    """No real side effects: only simulated commits to a fenced SQLite table.

    Fencing works only because THIS gateway checks the fencing epoch in the SAME transaction
    as a simulated commit. It offers no guarantee for real-world external tools.

    The same transaction rechecks runtime approval revocation (issue #38): a commit for a
    task that a ``HandoffReceiver`` delivery was admitted under a since-revoked approval
    raises ``ApprovalRevoked`` and is audited as ``effect.denied``. A task that never
    arrived through a delivery carries no approval, so only its epoch is checked. Expiry
    is not rechecked here (the gateway does not hold the approvals).
    """

    def __init__(self, store: SQLiteStore):
        self.store = store

    @staticmethod
    def _deny_guarded(db: sqlite3.Connection, task_id: str) -> None:
        """Guarded tasks cannot fall back to the lower-level legacy authority lane.

        Enrollment and this check share the SQLite write lock. For unguarded
        tasks the original experimental CAS/commit semantics are unchanged.
        """
        exists = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='guarded_tasks'"
        ).fetchone()
        if exists and db.execute(
            "SELECT 1 FROM guarded_tasks WHERE task_id=?", (task_id,)
        ).fetchone():
            raise PolicyDenied("guarded task requires GuardedAuthority")

    def claim(self, task_id: str, agent_id: str) -> int:
        _id(task_id, "task_id")
        _id(agent_id, "agent_id")
        with self.store._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                db.execute("INSERT INTO owners VALUES(?,?,1)", (task_id, agent_id))
            except sqlite3.IntegrityError as exc:
                raise Conflict("task already has an owner") from exc
            db.commit()
            return 1

    def transfer(self, task_id: str, expected_owner: str, expected_epoch: int,
                 new_owner: str) -> int:
        _id(task_id, "task_id")
        _id(new_owner, "new_owner")
        _id(expected_owner, "expected_owner")
        if type(expected_epoch) is not int or expected_epoch < 1:
            raise ContractError("invalid expected epoch")
        if new_owner == expected_owner:
            raise ContractError("new owner must differ")
        with self.store._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self._deny_guarded(db, task_id)
            updated = db.execute("UPDATE owners SET agent_id = ?, epoch = epoch + 1 "
                                 "WHERE task_id = ? AND agent_id = ? AND epoch = ?",
                                 (new_owner, task_id, expected_owner, expected_epoch))
            if updated.rowcount != 1:
                raise Conflict("stale or missing owner/epoch")
            db.commit()
            return expected_epoch + 1

    def commit(self, task_id: str, agent_id: str, epoch: int,
               effect_id: str, payload: str) -> bool:
        """Return True for new simulated commit, False for identical replay."""
        _id(task_id, "task_id")
        _id(agent_id, "agent_id")
        _id(effect_id, "effect_id")
        if type(epoch) is not int or epoch < 1:
            raise ContractError("invalid epoch")
        try:
            payload_bytes = payload.encode("utf-8") if isinstance(payload, str) else None
        except UnicodeEncodeError:
            payload_bytes = None
        if payload_bytes is None or len(payload_bytes) > MAX_TEXT:
            raise ContractError("invalid payload")
        fingerprint = self.store.keyed_digest(hashlib.sha256(payload_bytes).hexdigest())
        with self.store._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self._deny_guarded(db, task_id)
            owner = db.execute("SELECT agent_id,epoch FROM owners WHERE task_id=?", (task_id,)).fetchone()
            if owner != (agent_id, epoch):
                raise PolicyDenied("stale or unauthorized executor")
            revoked = self.store._revoked_task_approval(db, task_id)
            if revoked is not None:  # checked before the replay lookup: replays are refused too
                self.store._event(db, "", task_id, "effect.denied",
                                  self.store.fingerprint({"effect_id": effect_id, "approval_ref": revoked,
                                                          "reason": "approval_revoked"}))
                db.commit()  # keep the audit event; nothing else was written
                raise ApprovalRevoked(revoked)
            existing = db.execute("SELECT payload_digest FROM effects WHERE task_id=? AND effect_id=?",
                                  (task_id, effect_id)).fetchone()
            if existing is not None:
                if existing[0] != fingerprint:
                    raise Conflict("same effect ID with different payload")
                db.commit()
                return False
            db.execute("INSERT INTO effects VALUES(?,?,?,?)", (task_id, effect_id, fingerprint, epoch))
            db.commit()
            return True

    def reconcile(self, task_id: str, effect_id: str) -> str:
        """'unknown' means no *local* commit record, not no external effect."""
        with self.store._connection() as db:
            row = db.execute("SELECT 1 FROM effects WHERE task_id=? AND effect_id=?",
                             (task_id, effect_id)).fetchone()
            return "committed" if row else "unknown"
