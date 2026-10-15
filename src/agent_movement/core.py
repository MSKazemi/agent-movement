"""Strict synthetic handoffs and durable simulated-effect fencing.

This is an application-level experiment. No sender identity authentication, A2A,
remote authorization, external tools, or general checkpoint migration is provided.
"""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "0.1.0-draft"
ID = re.compile(r"[A-Za-z][A-Za-z0-9._:-]{0,127}\Z")
MAX_TEXT = 2048


class ContractError(ValueError):
    """Input failed the narrow experimental transfer contract."""


class PolicyDenied(ValueError):
    """Requested operation is not approved. Not an authentication guarantee."""


class Conflict(ValueError):
    """Idempotency collision, stale authority or incompatible task state."""


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
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
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
    if not isinstance(task["text"], str) or len(task["text"].encode("utf-8")) > MAX_TEXT:
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


@dataclass(frozen=True)
class Approval:
    """Preconfigured receiver-side grant for exactly one synthetic/public task."""

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
        return (envelope["authority"]["approval_ref"] == self.ref
                and envelope["logical_task_id"] == self.task_id
                and envelope["origin"]["agent_id"] == self.origin_id
                and envelope["destination"]["agent_id"] == self.destination_id
                and envelope["task"]["kind"] == self.kind
                and envelope["context"]["classification"] == self.classification)


class SQLiteStore:
    """Transactional synthetic delivery results plus a separate fenced effect ledger."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        with self._connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS deliveries (
                    idempotency_key TEXT PRIMARY KEY,
                    movement_id TEXT NOT NULL UNIQUE,
                    envelope_digest TEXT NOT NULL,
                    receipt_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    movement_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    info_digest TEXT NOT NULL,
                    event_time TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS owners (
                    task_id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    epoch INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS effects (
                    task_id TEXT NOT NULL,
                    effect_id TEXT NOT NULL,
                    payload_digest TEXT NOT NULL,
                    epoch INTEGER NOT NULL,
                    PRIMARY KEY (task_id, effect_id)
                );
            """)

    @contextmanager
    def _connection(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        try:
            db.execute("PRAGMA busy_timeout = 10000")
            db.execute("PRAGMA journal_mode = WAL")
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
        now = datetime.now(timezone.utc).isoformat()
        db.execute("INSERT INTO audit_events(movement_id,task_id,event_type,info_digest,event_time) "
                   "VALUES(?,?,?,?,?)", (movement_id, task_id, event_type, fingerprint, now))

    def denied(self, envelope: dict[str, Any]) -> None:
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self._event(db, envelope["movement_id"], envelope["logical_task_id"],
                        "handoff.denied", digest(envelope))
            db.commit()

    def receive(self, envelope: dict[str, Any]) -> dict[str, Any]:
        """Execute a *pure* preapproved task transactionally, memoizing its receipt."""
        fingerprint = digest(envelope)
        key = envelope["execution"]["idempotency_key"]
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute("SELECT envelope_digest, receipt_json FROM deliveries "
                                  "WHERE idempotency_key = ?", (key,)).fetchone()
            if previous is not None:
                if previous[0] != fingerprint:
                    raise Conflict("idempotency key reused with different envelope")
                db.commit()
                return {**json.loads(previous[1]), "replayed": True}
            if db.execute("SELECT 1 FROM deliveries WHERE movement_id=?",
                          (envelope["movement_id"],)).fetchone():
                raise Conflict("movement ID reused with a new idempotency key")
            task = envelope["task"]
            if task["kind"] == "word_count":
                artifact = {"kind": "word_count", "value": len(task["text"].split())}
            else:
                artifact = {"kind": "sha256", "value": hashlib.sha256(task["text"].encode("utf-8")).hexdigest()}
            receipt = {
                "status": "completed",
                "movement_id": envelope["movement_id"],
                "logical_task_id": envelope["logical_task_id"],
                "origin_agent_id": envelope["origin"]["agent_id"],
                "destination_agent_id": envelope["destination"]["agent_id"],
                "trace_id": envelope["observability"]["trace_id"],
                "envelope_digest": fingerprint,
                "artifact": artifact,
                "artifact_digest": digest(artifact),
            }
            self._event(db, receipt["movement_id"], receipt["logical_task_id"],
                        "handoff.accepted", fingerprint)
            db.execute("INSERT INTO deliveries VALUES(?,?,?,?)",
                       (key, envelope["movement_id"], fingerprint, canonical(receipt)))
            self._event(db, receipt["movement_id"], receipt["logical_task_id"],
                        "handoff.completed", receipt["artifact_digest"])
            db.commit()
            return {**receipt, "replayed": False}

    def audit(self) -> list[dict[str, Any]]:
        with self._connection() as db:
            rows = db.execute("SELECT movement_id,task_id,event_type,info_digest,event_time "
                              "FROM audit_events ORDER BY seq").fetchall()
        return [dict(zip(("movement_id", "task_id", "event_type", "info_digest", "event_time"), row)) for row in rows]


class HandoffReceiver:
    def __init__(self, name: str, store: SQLiteStore, approvals: list[Approval]):
        self.name = name
        self.store = store
        self.approvals = tuple(approvals)

    def receive(self, message: Any) -> dict[str, Any]:
        envelope = validate_envelope(message)
        now = datetime.now(timezone.utc)
        if envelope["destination"]["agent_id"] != self.name or not any(
                a.allows(envelope, now) for a in self.approvals):
            self.store.denied(envelope)
            raise PolicyDenied("receiver-side approval not found, valid or scoped for this transfer")
        return self.store.receive(envelope)


class EffectGateway:
    """No real side effects: only simulated commits to a fenced SQLite table.

    Fencing works only because THIS gateway checks epoch in the SAME transaction
    as a simulated commit. It offers no guarantee for real-world external tools.
    """

    def __init__(self, store: SQLiteStore):
        self.store = store

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
        if not isinstance(payload, str) or len(payload.encode("utf-8")) > MAX_TEXT:
            raise ContractError("invalid payload")
        fingerprint = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        with self.store._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            owner = db.execute("SELECT agent_id,epoch FROM owners WHERE task_id=?", (task_id,)).fetchone()
            if owner != (agent_id, epoch):
                raise PolicyDenied("stale or unauthorized executor")
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
