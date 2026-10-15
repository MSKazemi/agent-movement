"""Dependency-free mapping between the safe handoff envelope and A2A v1 framing.

This module never imports the A2A SDK. It defines the experimental
``agent-movement`` A2A *extension profile*: which envelope fields travel in
``Message.metadata``, which travel in the single structured ``Part``, and what
the result ``Artifact`` carries. The SDK adapter (``a2a_server`` /
``a2a_client``) turns these plain dictionaries into protobuf objects.

Only fields of an envelope that already passed ``validate_envelope`` are
mapped, by explicit allowlist. Unknown fields (for example provider-private
runtime state, model context, credentials or tool handles) are rejected by the
contract before mapping and are rejected again on the receiving side, so they
are never serialized into A2A messages or artifacts.

This proves *delegation* of one allowlisted pure task, not agent migration.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .core import SCHEMA_VERSION, ContractError, digest, validate_envelope

EXTENSION_URI = "urn:agent-movement:a2a-handoff-profile:0.1.0-draft"
TASK_MEDIA_TYPE = "application/vnd.agent-movement.task+json"
RECEIPT_MEDIA_TYPE = "application/vnd.agent-movement.receipt+json"
RECEIPT_ARTIFACT_NAME = "handoff-receipt"
SKILL_PREFIX = "agent-movement."
KINDS = ("word_count", "sha256")

_METADATA_FIELDS = frozenset({
    "schema_version", "movement_id", "logical_task_id", "operation",
    "origin_agent_id", "destination_agent_id", "classification",
    "approval_ref", "idempotency_key", "trace_id", "envelope_digest",
})
_TASK_FIELDS = frozenset({"kind", "text"})
_RECEIPT_FIELDS = frozenset({
    "status", "movement_id", "logical_task_id", "origin_agent_id",
    "destination_agent_id", "trace_id", "envelope_digest", "artifact",
    "artifact_digest",
})
_ARTIFACT_METADATA_FIELDS = frozenset({
    "movement_id", "trace_id", "envelope_digest", "artifact_digest", "replayed",
})
_SAFE_TOKEN = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z")


class ProfileError(ContractError):
    """A2A framing does not match the experimental handoff profile."""


def skill_id(kind: str) -> str:
    if kind not in KINDS:
        raise ProfileError("unknown task kind")
    return SKILL_PREFIX + kind


def envelope_to_a2a(envelope: Any) -> dict[str, Any]:
    """Return the A2A-bound projection of a *validated* envelope.

    Result keys: ``context_id`` (the logical task ID), ``metadata`` (stored
    under :data:`EXTENSION_URI` in ``Message.metadata``) and ``data`` (the
    content of the single ``Part`` with media type :data:`TASK_MEDIA_TYPE`).
    """
    v = validate_envelope(envelope)
    metadata = {
        "schema_version": v["schema_version"],
        "movement_id": v["movement_id"],
        "logical_task_id": v["logical_task_id"],
        "operation": v["operation"],
        "origin_agent_id": v["origin"]["agent_id"],
        "destination_agent_id": v["destination"]["agent_id"],
        "classification": v["context"]["classification"],
        "approval_ref": v["authority"]["approval_ref"],
        "idempotency_key": v["execution"]["idempotency_key"],
        "trace_id": v["observability"]["trace_id"],
        "envelope_digest": digest(v),
    }
    return {"context_id": v["logical_task_id"], "metadata": metadata,
            "data": {"kind": v["task"]["kind"], "text": v["task"]["text"]}}


def a2a_to_envelope(metadata: Any, data: Any, context_id: str = "") -> dict[str, Any]:
    """Strictly rebuild and validate an envelope from received A2A fields."""
    if not isinstance(metadata, dict) or set(metadata) != _METADATA_FIELDS:
        raise ProfileError("invalid handoff metadata fields")
    if not isinstance(data, dict) or set(data) != _TASK_FIELDS:
        raise ProfileError("invalid handoff task part fields")
    envelope = {
        "schema_version": metadata["schema_version"],
        "movement_id": metadata["movement_id"],
        "logical_task_id": metadata["logical_task_id"],
        "operation": metadata["operation"],
        "origin": {"agent_id": metadata["origin_agent_id"]},
        "destination": {"agent_id": metadata["destination_agent_id"]},
        "task": {"kind": data["kind"], "text": data["text"]},
        "context": {"classification": metadata["classification"]},
        "authority": {"approval_ref": metadata["approval_ref"]},
        "execution": {"idempotency_key": metadata["idempotency_key"]},
        "observability": {"trace_id": metadata["trace_id"]},
    }
    validate_envelope(envelope)
    if metadata["envelope_digest"] != digest(envelope):
        raise ProfileError("envelope digest does not match mapped fields")
    if context_id and context_id != envelope["logical_task_id"]:
        raise ProfileError("A2A context ID does not match logical task ID")
    return envelope


def receipt_to_artifact(receipt: dict[str, Any]) -> dict[str, Any]:
    """Split a core receipt into artifact data and namespaced artifact metadata."""
    data = {name: receipt[name] for name in sorted(_RECEIPT_FIELDS)}
    metadata = {name: receipt[name] for name in sorted(_ARTIFACT_METADATA_FIELDS)}
    return {"artifact_id": "receipt-" + receipt["movement_id"],
            "name": RECEIPT_ARTIFACT_NAME, "data": data, "metadata": metadata}


def _integral(value: Any) -> Any:
    """Undo protobuf ``Value`` number widening (JSON numbers become doubles)."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {key: _integral(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_integral(item) for item in value]
    return value


def verify_receipt(envelope: dict[str, Any], data: Any, metadata: Any) -> dict[str, Any]:
    """Origin-side check that a returned artifact answers *this* envelope."""
    data, metadata = _integral(data), _integral(metadata)
    if not isinstance(data, dict) or set(data) != _RECEIPT_FIELDS:
        raise ProfileError("invalid receipt artifact fields")
    if not isinstance(metadata, dict) or set(metadata) != _ARTIFACT_METADATA_FIELDS:
        raise ProfileError("invalid receipt artifact metadata")
    expected = {
        "status": "completed",
        "movement_id": envelope["movement_id"],
        "logical_task_id": envelope["logical_task_id"],
        "origin_agent_id": envelope["origin"]["agent_id"],
        "destination_agent_id": envelope["destination"]["agent_id"],
        "trace_id": envelope["observability"]["trace_id"],
        "envelope_digest": digest(envelope),
    }
    for name, value in expected.items():
        if data[name] != value:
            raise ProfileError(f"receipt {name} does not match the sent envelope")
    if data["artifact_digest"] != digest(data["artifact"]):
        raise ProfileError("receipt artifact digest mismatch")
    for name in ("movement_id", "trace_id", "envelope_digest", "artifact_digest"):
        if metadata[name] != data[name]:
            raise ProfileError(f"artifact metadata {name} mismatch")
    if not isinstance(metadata["replayed"], bool):
        raise ProfileError("invalid replayed flag")
    return {**data, "replayed": metadata["replayed"]}


def safe_token(value: str) -> str:
    """Store an externally chosen ID verbatim only if it is a short safe token."""
    if isinstance(value, str) and _SAFE_TOKEN.fullmatch(value):
        return value
    return "sha256:" + hashlib.sha256(str(value).encode("utf-8")).hexdigest()


class A2ACorrelationLog:
    """Receiver-side table joining A2A task/message IDs to handoff audit events.

    Lives in the same SQLite file as :class:`agent_movement.core.SQLiteStore`
    but in its own table, so the core schema is unchanged. Rows contain only
    identifiers, outcome codes and digests -- never task text.
    """

    def __init__(self, path: str | Path):
        self.path = str(path)
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS a2a_correlations (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    a2a_task_id TEXT,
                    a2a_context_id TEXT,
                    a2a_message_id TEXT NOT NULL,
                    movement_id TEXT,
                    trace_id TEXT,
                    outcome TEXT NOT NULL,
                    envelope_digest TEXT,
                    artifact_digest TEXT,
                    event_time TEXT NOT NULL
                )""")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)
        db.execute("PRAGMA busy_timeout = 10000")
        return db

    def record(self, *, message_id: str, outcome: str, task_id: str | None = None,
               context_id: str | None = None, envelope: dict[str, Any] | None = None,
               artifact_digest: str | None = None) -> None:
        row = (
            None if task_id is None else safe_token(task_id),
            None if context_id is None else safe_token(context_id),
            safe_token(message_id),
            None if envelope is None else envelope["movement_id"],
            None if envelope is None else envelope["observability"]["trace_id"],
            outcome,
            None if envelope is None else digest(envelope),
            artifact_digest,
            datetime.now(timezone.utc).isoformat(),
        )
        db = self._connect()
        try:
            with db:
                db.execute("INSERT INTO a2a_correlations(a2a_task_id,a2a_context_id,a2a_message_id,"
                           "movement_id,trace_id,outcome,envelope_digest,artifact_digest,event_time) "
                           "VALUES(?,?,?,?,?,?,?,?,?)", row)
        finally:
            db.close()

    def rows(self) -> list[dict[str, Any]]:
        names = ("a2a_task_id", "a2a_context_id", "a2a_message_id", "movement_id", "trace_id",
                 "outcome", "envelope_digest", "artifact_digest", "event_time")
        db = self._connect()
        try:
            found = db.execute(f"SELECT {','.join(names)} FROM a2a_correlations ORDER BY seq").fetchall()
        finally:
            db.close()
        return [dict(zip(names, row)) for row in found]


__all__ = [
    "A2ACorrelationLog", "EXTENSION_URI", "KINDS", "ProfileError", "RECEIPT_ARTIFACT_NAME",
    "RECEIPT_MEDIA_TYPE", "SCHEMA_VERSION", "TASK_MEDIA_TYPE", "a2a_to_envelope",
    "envelope_to_a2a", "receipt_to_artifact", "safe_token", "skill_id", "verify_receipt",
]
