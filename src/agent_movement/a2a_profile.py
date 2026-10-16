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

The normative description is the extension specification
``docs/a2a-profile-extension.md``; :data:`EXTENSION_URI` is that file's URL on
``main``. The profile 0.1 URN is still accepted as a deprecated alias
(:data:`LEGACY_EXTENSION_URI`) with its original contextId rule.

This proves *delegation* of one allowlisted pure task, not agent migration.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .core import SCHEMA_VERSION, ContractError, SQLiteStore, digest, validate_envelope

PROFILE_VERSION = "0.2.0-draft"
REPOSITORY_URL = "https://github.com/MSKazemi/agent-movement"
SPEC_PATH = "docs/a2a-profile-extension.md"
# Resolvable identifier: the extension specification is hosted at the extension's URI
# (A2A "Extensions" topic). A breaking change MUST get a new URI (A2A v1.0 sec. 4.6.3).
EXTENSION_URI = f"{REPOSITORY_URL}/blob/main/{SPEC_PATH}"
# Deprecated alias, accepted throughout profile 0.2.x and removed in 0.3.0. Requests that use it
# keep the profile 0.1 contextId rule (a client contextId is allowed, bound to logical_task_id).
LEGACY_EXTENSION_URI = "urn:agent-movement:a2a-handoff-profile:0.1.0-draft"
EXTENSION_URIS = (EXTENSION_URI, LEGACY_EXTENSION_URI)
# Policies for a client-supplied Message.contextId (A2A v1.0 sec. 3.4.1). A message without a
# contextId is always accepted and the server generates one.
CLIENT_CONTEXT_REJECTED = "rejected"
CLIENT_CONTEXT_BOUND = "bound-to-logical-task-id"
CLIENT_CONTEXT_POLICIES = (CLIENT_CONTEXT_REJECTED, CLIENT_CONTEXT_BOUND)
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

    Result keys: ``metadata`` (stored under the profile URI in
    ``Message.metadata``) and ``data`` (the content of the single ``Part`` with
    media type :data:`TASK_MEDIA_TYPE`). No contextId is derived here: by
    default the server generates it (see :func:`check_context_id`).
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
    return {"metadata": metadata, "data": {"kind": v["task"]["kind"], "text": v["task"]["text"]}}


def a2a_to_envelope(metadata: Any, data: Any, context_id: str = "") -> dict[str, Any]:
    """Strictly rebuild and validate an envelope from received A2A fields.

    A non-empty ``context_id`` must equal the logical task ID (the binding rule
    of :data:`CLIENT_CONTEXT_BOUND`). Whether a client may supply a contextId at
    all is decided by :func:`check_context_id`, not here.
    """
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
    if context_id:
        check_context_id(context_id, envelope, CLIENT_CONTEXT_BOUND)
    return envelope


def context_policy(extension_uri: str, configured: str) -> str:
    """Effective client-contextId policy for a request that used ``extension_uri``.

    The current URI uses the server's configured policy. The deprecated alias
    keeps its profile 0.1 meaning: a client contextId is accepted when it equals
    the logical task ID.
    """
    if configured not in CLIENT_CONTEXT_POLICIES:
        raise ValueError("client contextId policy must be one of " + ", ".join(CLIENT_CONTEXT_POLICIES))
    if extension_uri == LEGACY_EXTENSION_URI:
        return CLIENT_CONTEXT_BOUND
    if extension_uri != EXTENSION_URI:
        raise ProfileError("unknown handoff profile extension URI")
    return configured


def check_context_id(context_id: str, envelope: dict[str, Any], policy: str) -> None:
    """Apply the profile's contextId rule to the contextId *as the client sent it*.

    An empty contextId is always allowed: the server generates one and returns
    it in the task (A2A v1.0 sec. 3.4.1). A client-supplied contextId is
    accepted only under :data:`CLIENT_CONTEXT_BOUND` and only if it equals the
    envelope's ``logical_task_id``. Anything else must be rejected, because an
    agent that cannot accept a client-provided contextId MUST reject the request.
    """
    if not context_id:
        return
    if policy != CLIENT_CONTEXT_BOUND:
        raise ProfileError("client-supplied contextId is not accepted; omit it and use the "
                           "server-generated contextId")
    if context_id != envelope["logical_task_id"]:
        raise ProfileError("A2A context ID does not match logical task ID")


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
    identifiers, outcome codes and digests -- never task text. The envelope and
    artifact digests are keyed commitments under the store secret
    (:meth:`SQLiteStore.keyed_digest`), not plain SHA-256 (issue #39).
    """

    def __init__(self, path: str | Path, store: SQLiteStore | None = None):
        self.path = str(path)
        self.store = SQLiteStore(path) if store is None else store
        if self.store.path != self.path:
            raise ValueError("the correlation log must share its store's file")
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
            None if envelope is None else self.store.fingerprint(envelope),
            None if artifact_digest is None else self.store.keyed_digest(artifact_digest),
            datetime.now(UTC).isoformat(),
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
        return [dict(zip(names, row, strict=True)) for row in found]


__all__ = [
    "CLIENT_CONTEXT_BOUND",
    "CLIENT_CONTEXT_POLICIES",
    "CLIENT_CONTEXT_REJECTED",
    "EXTENSION_URI",
    "EXTENSION_URIS",
    "KINDS",
    "LEGACY_EXTENSION_URI",
    "PROFILE_VERSION",
    "RECEIPT_ARTIFACT_NAME",
    "RECEIPT_MEDIA_TYPE",
    "REPOSITORY_URL",
    "SCHEMA_VERSION",
    "SPEC_PATH",
    "TASK_MEDIA_TYPE",
    "A2ACorrelationLog",
    "ProfileError",
    "a2a_to_envelope",
    "check_context_id",
    "context_policy",
    "envelope_to_a2a",
    "receipt_to_artifact",
    "safe_token",
    "skill_id",
    "verify_receipt",
]
