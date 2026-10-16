"""Self-describing, digest-verified checkpoint bundle for two-store relocation.

Lower layer of :mod:`agent_movement.relocation` (two-store mode). It knows the
bundle *format* and how to copy raw LangGraph ``SqliteSaver`` rows between two
SQLite files; it knows nothing about owners, epochs or fencing, which stay in
the coordinator and in :mod:`agent_movement.relocation`.

A bundle is ONE canonical-JSON document (``core.canonical``)::

    {"format": BUNDLE_FORMAT,
     "manifest": {... relocation manifest, incl. "bundle": {"sections": {...}}},
     "payload": {"checkpoint": {...}, "writes": [...], "effect_ledger": [...]}}

The manifest names the graph and LangGraph versions, the channel list, a
semantic checkpoint digest, one SHA-256 digest per channel value and one per
payload section. The coordinator records the manifest digest when the export
is requested; that record, not the bundle, is the trust anchor. Bundles are not
signed. Unverified bytes are never deserialized: section digests are checked
against the coordinator-pinned manifest before LangGraph's serializer runs.

Requires the optional extra: ``python -m pip install -e '.[relocation]'``.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from .core import Conflict, ContractError, canonical, digest

BUNDLE_FORMAT = "am-checkpoint-bundle/0.1.0-draft"
MAX_BUNDLE_BYTES = 8 * 1024 * 1024
SECTIONS = ("checkpoint", "writes", "effect_ledger")
# Serializer types this runtime writes for checkpoints and pending writes. Anything
# else (notably "pickle") is refused before deserialization.
CHECKPOINT_TYPES = ("msgpack",)
WRITE_TYPES = ("msgpack", "null")
LEDGER_FIELDS = ("effect_id", "payload_digest", "tool", "status", "execution_id", "epoch", "attempts")
CHECKPOINT_FIELDS = ("thread_id", "checkpoint_ns", "checkpoint_id", "parent_checkpoint_id", "type",
                     "checkpoint_b64", "metadata_b64")
WRITE_FIELDS = ("task_id", "task_path", "idx", "channel", "type", "value_b64")


class BundleRejected(Exception):
    """The bundle cannot be used. ``reason`` is a stable machine-readable code."""

    def __init__(self, reason: str, message: str, **details: Any):
        super().__init__(message)
        self.reason = reason
        self.details = details


def _b64(data: bytes | None) -> str | None:
    return None if data is None else base64.b64encode(data).decode("ascii")


def _unb64(text: str | None, label: str) -> bytes | None:
    if text is None:
        return None
    try:
        return base64.b64decode(text.encode("ascii"), validate=True)
    except (binascii.Error, UnicodeEncodeError, AttributeError) as exc:
        raise BundleRejected("payload_malformed", f"{label} is not valid base64") from exc


# --- export side --------------------------------------------------------------

def read_payload(db: sqlite3.Connection, task_id: str, checkpoint_id: str) -> dict[str, Any]:
    """Raw rows for ONE checkpoint (root namespace), its pending writes and the task's ledger.

    Rows are copied byte for byte (base64), never re-serialized, so the receiver
    stores exactly what the origin's ``SqliteSaver`` wrote.
    """
    row = db.execute("SELECT thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, type, "
                     "checkpoint, metadata FROM checkpoints WHERE thread_id=? AND checkpoint_ns='' "
                     "AND checkpoint_id=?", (task_id, checkpoint_id)).fetchone()
    if row is None:
        raise Conflict("checkpoint to bundle is missing from the source store")
    checkpoint = {"thread_id": row[0], "checkpoint_ns": row[1], "checkpoint_id": row[2],
                  "parent_checkpoint_id": row[3], "type": row[4], "checkpoint_b64": _b64(row[5]),
                  "metadata_b64": _b64(row[6])}
    writes = [{"task_id": w[0], "task_path": w[1], "idx": w[2], "channel": w[3], "type": w[4],
               "value_b64": _b64(w[5])}
              for w in db.execute("SELECT task_id, task_path, idx, channel, type, value FROM writes "
                                  "WHERE thread_id=? AND checkpoint_ns='' AND checkpoint_id=? "
                                  "ORDER BY task_id, idx", (task_id, checkpoint_id))]
    ledger = [dict(zip(LEDGER_FIELDS, r, strict=True)) for r in db.execute(
        "SELECT effect_id, payload_digest, tool, status, execution_id, epoch, attempts "
        "FROM effect_intents WHERE task_id=? ORDER BY effect_id", (task_id,))]
    return {"checkpoint": checkpoint, "writes": writes, "effect_ledger": ledger}


def describe(payload: dict[str, Any], channel_values: dict[str, Any]) -> dict[str, Any]:
    """The manifest's ``bundle`` section: per-section and per-channel SHA-256 digests."""
    return {"format": BUNDLE_FORMAT,
            "sections": {name: digest(payload[name]) for name in SECTIONS},
            "payload_digest": digest(payload),
            "channel_digests": channel_digests(channel_values),
            "pending_writes": len(payload["writes"]),
            "effect_records": len(payload["effect_ledger"])}


def channel_digests(channel_values: dict[str, Any]) -> dict[str, str]:
    return {name: digest(value) for name, value in sorted(channel_values.items())}


def encode(manifest: dict[str, Any], payload: dict[str, Any]) -> bytes:
    data = canonical({"format": BUNDLE_FORMAT, "manifest": manifest, "payload": payload}).encode("utf-8")
    if len(data) > MAX_BUNDLE_BYTES:
        raise ContractError("bundle exceeds the local size limit")
    return data


def write_atomic(path: str | Path, data: bytes) -> str:
    """Write-then-rename so a reader never sees a half-written bundle file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{target.name}.", dir=str(target.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return str(target)


def copy(source: str | Path, destination: str | Path) -> str:
    """The 'transport': copy bundle bytes into the receiver's own inbox."""
    return write_atomic(destination, Path(source).read_bytes())


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# --- import side --------------------------------------------------------------

def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for name, value in pairs:
        if name in obj:
            raise BundleRejected("bundle_unreadable", "duplicate JSON property in bundle")
        obj[name] = value
    return obj


def parse(path: str | Path) -> tuple[dict[str, Any], str]:
    """Read and structurally validate a bundle file. Returns (bundle, sha256 of its bytes)."""
    try:
        with open(path, "rb") as handle:
            raw = handle.read(MAX_BUNDLE_BYTES + 1)
    except OSError as exc:
        raise BundleRejected("bundle_missing", "bundle file is unavailable") from exc
    if len(raw) > MAX_BUNDLE_BYTES:
        raise BundleRejected("bundle_too_large", "bundle exceeds the local size limit")
    try:
        bundle = json.loads(raw.decode("utf-8"), object_pairs_hook=_object,
                            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("constant")))
    except BundleRejected:
        raise
    except (ValueError, RecursionError) as exc:  # JSONDecodeError, UnicodeDecodeError: truncated/garbled
        raise BundleRejected("bundle_unreadable", "bundle is truncated or not JSON") from exc
    if not isinstance(bundle, dict) or set(bundle) != {"format", "manifest", "payload"}:
        raise BundleRejected("bundle_malformed", "bundle has unexpected top-level fields")
    if bundle["format"] != BUNDLE_FORMAT:
        raise BundleRejected("bundle_format", f"unsupported bundle format {bundle['format']!r}")
    if canonical(bundle).encode("utf-8") != raw:
        raise BundleRejected("bundle_not_canonical", "bundle bytes are not in canonical form")
    return bundle, hashlib.sha256(raw).hexdigest()


def _check_shape(payload: Any) -> None:
    if not isinstance(payload, dict) or set(payload) != set(SECTIONS):
        raise BundleRejected("payload_malformed", "payload sections are missing or unexpected")
    if not isinstance(payload["checkpoint"], dict) or set(payload["checkpoint"]) != set(CHECKPOINT_FIELDS):
        raise BundleRejected("payload_malformed", "checkpoint row has unexpected fields")
    for name, fields in (("writes", WRITE_FIELDS), ("effect_ledger", LEDGER_FIELDS)):
        rows = payload[name]
        if not isinstance(rows, list) or any(not isinstance(r, dict) or set(r) != set(fields) for r in rows):
            raise BundleRejected("payload_malformed", f"{name} rows have unexpected fields")


def corrupt_sections(manifest: dict[str, Any], payload: Any) -> list[str]:
    """Sections whose SHA-256 differs from the coordinator-pinned manifest (shape checked first)."""
    _check_shape(payload)
    expected = manifest["bundle"]["sections"]
    return [name for name in SECTIONS if digest(payload[name]) != expected.get(name)]


def decode_checkpoint(payload: dict[str, Any], serde: Any) -> dict[str, Any]:
    """Deserialize the (already digest-verified) checkpoint blob with the pinned serializer."""
    row = payload["checkpoint"]
    if row["type"] not in CHECKPOINT_TYPES or any(w["type"] not in WRITE_TYPES for w in payload["writes"]):
        raise BundleRejected("unsupported_serialization", "bundle uses a refused serializer type")
    blob = _unb64(row["checkpoint_b64"], "checkpoint")
    try:
        checkpoint: dict[str, Any] = serde.loads_typed((row["type"], blob))
        return checkpoint
    except Exception as exc:  # any decoder failure is a refusal, never a partial import
        raise BundleRejected("checkpoint_undecodable", "checkpoint blob does not decode") from exc


def insert_payload(db: sqlite3.Connection, task_id: str, payload: dict[str, Any]) -> dict[str, int]:
    """Insert rows into the receiver's store inside the CALLER's transaction.

    Idempotent and content-addressed: a row that already exists must be byte-identical
    (a previous partial attempt or an earlier import of the same checkpoint), otherwise
    the import is refused. Nothing is ever overwritten or deleted.
    """
    cp = payload["checkpoint"]
    if (cp["thread_id"], cp["checkpoint_ns"]) != (task_id, ""):
        raise Conflict("bundle checkpoint belongs to another task or namespace")
    values = (cp["thread_id"], "", cp["checkpoint_id"], cp["parent_checkpoint_id"], cp["type"],
              _unb64(cp["checkpoint_b64"], "checkpoint"), _unb64(cp["metadata_b64"], "metadata"))
    inserted = {"checkpoints": 0, "writes": 0, "effect_intents": 0}
    existing = db.execute("SELECT thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, type, "
                          "checkpoint, metadata FROM checkpoints WHERE thread_id=? AND checkpoint_ns='' "
                          "AND checkpoint_id=?", (task_id, cp["checkpoint_id"])).fetchone()
    if existing is None:
        db.execute("INSERT INTO checkpoints(thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, "
                   "type, checkpoint, metadata) VALUES(?,?,?,?,?,?,?)", values)
        inserted["checkpoints"] = 1
    elif tuple(existing) != values:
        raise Conflict("destination already holds a different checkpoint with this ID")
    for w in payload["writes"]:
        row = (task_id, "", cp["checkpoint_id"], w["task_id"], w["task_path"], w["idx"], w["channel"],
               w["type"], _unb64(w["value_b64"], "write"))
        found = db.execute("SELECT thread_id, checkpoint_ns, checkpoint_id, task_id, task_path, idx, "
                           "channel, type, value FROM writes WHERE thread_id=? AND checkpoint_ns='' AND "
                           "checkpoint_id=? AND task_id=? AND idx=?",
                           (task_id, cp["checkpoint_id"], w["task_id"], w["idx"])).fetchone()
        if found is None:
            db.execute("INSERT INTO writes(thread_id, checkpoint_ns, checkpoint_id, task_id, task_path, idx, "
                       "channel, type, value) VALUES(?,?,?,?,?,?,?,?,?)", row)
            inserted["writes"] += 1
        elif tuple(found) != row:
            raise Conflict("destination already holds a different pending write")
    local_writes = db.execute("SELECT COUNT(*) FROM writes WHERE thread_id=? AND checkpoint_ns='' AND "
                              "checkpoint_id=?", (task_id, cp["checkpoint_id"])).fetchone()[0]
    if local_writes != len(payload["writes"]):
        raise Conflict("destination holds pending writes the bundle does not describe")
    for e in payload["effect_ledger"]:
        row = tuple(e[f] for f in LEDGER_FIELDS)
        found = db.execute("SELECT effect_id, payload_digest, tool, status, execution_id, epoch, attempts "
                           "FROM effect_intents WHERE task_id=? AND effect_id=?",
                           (task_id, e["effect_id"])).fetchone()
        if found is None:
            db.execute("INSERT INTO effect_intents(task_id, effect_id, payload_digest, tool, status, "
                       "execution_id, epoch, attempts) VALUES(?,?,?,?,?,?,?,?)", (task_id, *row))
            inserted["effect_intents"] += 1
        elif tuple(found) != row:
            raise Conflict("destination already holds a different effect record")
    local_effects = db.execute("SELECT COUNT(*) FROM effect_intents WHERE task_id=?", (task_id,)).fetchone()[0]
    if local_effects != len(payload["effect_ledger"]):
        raise Conflict("destination holds effect records the bundle does not describe")
    return inserted
