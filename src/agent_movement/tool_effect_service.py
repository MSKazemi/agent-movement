"""Independently provisioned localhost synthetic effect service (research; issue #102).

Only writes its own SQLite ledger; no real tools, no A2A, no global containment.
Operator enrollment/transfer/revocation/unknown state and effect commits serialize
through BEGIN IMMEDIATE. Every requester carries a pinned worker signature and a
separately issued grant; raw task contents are deliberately not accepted.
"""

from __future__ import annotations

import argparse
import hmac
import json
import math
import os
import re
import sqlite3
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import closing, contextmanager, suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .core import ContractError, SQLiteStore, _fields, _id, canonical, digest, parse_json
from .trust import (
    CLASSIFICATIONS,
    TASK_KINDS,
    TrustStore,
    check_grant_live,
    check_grant_scope,
    import_key,
    seal,
    unseal,
    verify_grant,
    verify_revocation,
)

VERSION = 1
_EFFECT_FIELDS = frozenset({
    "type", "movement_id", "task_id", "actor_id", "service_id", "kind",
    "classification", "policy_epoch", "owner_epoch", "effect_id", "effect_tag",
    "cost", "grant_digest",
})
_OPERATOR_COMMON = frozenset({"type", "action", "seq", "task_id", "movement_id"})
_ENROLL_FIELDS = _OPERATOR_COMMON | {
    "origin_id", "destination_id", "kind", "classification", "policy_epoch",
    "owner_epoch", "grant",
}
_TRANSFER_FIELDS = _OPERATOR_COMMON | {"expected_owner", "expected_epoch"}
_REVOKE_FIELDS = _OPERATOR_COMMON | {"notice"}
_POLICY_FIELDS = _OPERATOR_COMMON | {"new_policy_epoch"}
_TAG_RE = re.compile(r"[0-9a-f]{64}\Z")


def _exact(value: Any, keys: frozenset[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ContractError("unsupported or missing fields")
    return value


def _positive(value: Any) -> int:
    if type(value) is not int or not 1 <= value <= 1_000_000:
        raise ContractError("invalid positive integer")
    return value


class ToolEffectService:
    """One independently managed test-sink authority, with its own DB and clock.

    The operator verifier, worker verifiers, grant roots, and signing key are
    provisioned by the trusted launcher, never from untrusted HTTP metadata.
    """

    def __init__(
        self, db_path: str | Path, *, service_id: str, grant_trust: TrustStore,
        worker_verifiers: Mapping[str, Any], operator_verifier: Any,
        receipt_signer: Any, budget: int = 2,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.service_id = _id(service_id, "service_id")
        self.grant_trust = grant_trust
        self.workers = dict(worker_verifiers)
        if not self.workers or not all(isinstance(k, str) and hasattr(v, "verify")
                                       for k, v in self.workers.items()):
            raise ContractError("pinned worker verifiers required")
        if not hasattr(operator_verifier, "verify") or not hasattr(receipt_signer, "sign"):
            raise ContractError("separate operator and receipt keys required")
        self.operator = operator_verifier
        self.signer = receipt_signer
        self.budget = _positive(budget)
        if not callable(clock):
            raise ContractError("trusted clock required")
        self.clock = clock
        self.store = SQLiteStore(db_path)
        with self._transaction() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS tool_tasks (
                    task_id TEXT PRIMARY KEY, movement_id TEXT NOT NULL UNIQUE,
                    origin_id TEXT NOT NULL, destination_id TEXT NOT NULL,
                    kind TEXT NOT NULL, classification TEXT NOT NULL,
                    grant_id TEXT NOT NULL, grant_binding TEXT NOT NULL,
                    owner_id TEXT NOT NULL, owner_epoch INTEGER NOT NULL,
                    policy_epoch INTEGER NOT NULL, seq INTEGER NOT NULL,
                    active INTEGER NOT NULL DEFAULT 0,
                    revoked INTEGER NOT NULL DEFAULT 0, uncertain INTEGER NOT NULL DEFAULT 0,
                    budget INTEGER NOT NULL, used INTEGER NOT NULL DEFAULT 0
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS tool_effects (
                    task_id TEXT NOT NULL, effect_id TEXT NOT NULL,
                    request_binding TEXT NOT NULL, epoch INTEGER NOT NULL,
                    PRIMARY KEY(task_id, effect_id)
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS tool_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT, effect_id TEXT, category TEXT NOT NULL, outcome TEXT NOT NULL
                )
            """)

    def _now(self) -> int:
        try:
            raw = self.clock()
        except Exception as exc:
            raise ContractError("trusted clock unavailable") from exc
        if type(raw) not in (int, float) or not math.isfinite(raw) or raw < 0:
            raise ContractError("invalid trusted clock")
        return int(raw)

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self.store.path, timeout=10)) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    @staticmethod
    def _row(db: sqlite3.Connection, task_id: str) -> dict[str, Any] | None:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM tool_tasks WHERE task_id=?", (task_id,)).fetchone()
        return dict(row) if row is not None else None

    @staticmethod
    def _log(db: sqlite3.Connection, task_id: str | None, effect_id: str | None,
             category: str, outcome: str) -> None:
        db.execute("INSERT INTO tool_events(task_id,effect_id,category,outcome) VALUES(?,?,?,?)",
                   (task_id, effect_id, category, outcome))

    def _reply(self, kind: str, status: str, *, task_id: str | None = None,
               effect_id: str | None = None) -> tuple[int, dict[str, Any]]:
        code = {"committed": 200, "replayed": 200, "applied": 200,
                "denied": 403, "conflict": 409, "unknown": 202}[status]
        payload = {"type": "tool-effect-receipt", "version": VERSION,
                   "service_id": self.service_id, "kind": kind, "status": status,
                   "task_id": task_id, "effect_id": effect_id}
        return code, {"receipt": seal("tool-effect-receipt", payload, self.signer)}

    def operator_event(self, wrapped: Any) -> tuple[int, dict[str, Any]]:
        """Signed, sequence-numbered operator change; cannot be impersonated by a task."""
        try:
            p = unseal("tool-operator-event", wrapped, self.operator)
            action = p.get("action")
            schema = {
                "enroll": _ENROLL_FIELDS, "transfer": _TRANSFER_FIELDS,
                "revoke": _REVOKE_FIELDS, "policy_rollover": _POLICY_FIELDS,
                "mark_unknown": _OPERATOR_COMMON,
            }
            _exact(p, schema[action])
            if p["type"] != "tool-operator-event":
                raise ContractError("invalid operator event type")
            task_id = _id(p["task_id"], "task_id")
            movement_id = _id(p["movement_id"], "movement_id")
            seq = _positive(p["seq"])
            with self._transaction() as db:
                current = self._row(db, task_id)
                if action == "enroll":
                    if current is not None or seq != 1:
                        return self._reply("operator", "conflict", task_id=task_id)
                    for name in ("origin_id", "destination_id", "kind"):
                        _id(p[name], name)
                    if p["origin_id"] == p["destination_id"]:
                        raise ContractError("source and destination must differ")
                    if p["kind"] not in TASK_KINDS or p["classification"] not in CLASSIFICATIONS:
                        raise ContractError("unsupported synthetic capability or classification")
                    owner_epoch, policy_epoch = _positive(p["owner_epoch"]), _positive(p["policy_epoch"])
                    grant = verify_grant(p["grant"], self.grant_trust)
                    check_grant_scope(grant, actor=p["destination_id"], audience=self.service_id,
                                      task_id=task_id, kind=p["kind"], classification=p["classification"])
                    check_grant_live(grant, now=self._now(), revoked=False)
                    db.execute(
                        "INSERT INTO tool_tasks(task_id,movement_id,origin_id,destination_id,kind,"
                        "classification,grant_id,grant_binding,owner_id,owner_epoch,policy_epoch,seq,budget)"
                        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (task_id, movement_id, p["origin_id"], p["destination_id"], p["kind"],
                         p["classification"], grant["grant_id"], self.store.fingerprint(p["grant"]),
                         p["origin_id"], owner_epoch, policy_epoch, seq, self.budget),
                    )
                else:
                    if current is None or current["movement_id"] != movement_id:
                        return self._reply("operator", "denied", task_id=task_id)
                    if seq != current["seq"] + 1:
                        return self._reply("operator", "conflict", task_id=task_id)
                    if action == "transfer":
                        _id(p["expected_owner"], "expected_owner")
                        if (current["active"] or current["revoked"] or current["uncertain"]
                                or current["owner_id"] != p["expected_owner"]
                                or current["owner_id"] != current["origin_id"]
                                or current["owner_epoch"] != _positive(p["expected_epoch"])):
                            return self._reply("operator", "denied", task_id=task_id)
                        db.execute(
                            "UPDATE tool_tasks SET active=1,owner_id=destination_id,"
                            "owner_epoch=owner_epoch+1,seq=? WHERE task_id=?", (seq, task_id),
                        )
                    elif action == "revoke":
                        notice = verify_revocation(p["notice"], self.grant_trust)
                        if notice["grant_id"] != current["grant_id"]:
                            return self._reply("operator", "denied", task_id=task_id)
                        db.execute("UPDATE tool_tasks SET revoked=1,seq=? WHERE task_id=?", (seq, task_id))
                    elif action == "policy_rollover":
                        new_epoch = _positive(p["new_policy_epoch"])
                        if new_epoch <= current["policy_epoch"]:
                            return self._reply("operator", "denied", task_id=task_id)
                        # Fail closed pending a separate re-authorization protocol.
                        db.execute("UPDATE tool_tasks SET policy_epoch=?,uncertain=1,seq=? "
                                   "WHERE task_id=?", (new_epoch, seq, task_id))
                    else:
                        db.execute("UPDATE tool_tasks SET uncertain=1,seq=? WHERE task_id=?",
                                   (seq, task_id))
                self._log(db, task_id, None, "operator", str(action))
            return self._reply("operator", "applied", task_id=task_id)
        except (ValueError, TypeError, KeyError, sqlite3.Error):
            return self._reply("operator", "denied")

    def _effect_fields(self, wrapped: Any, grant_sealed: Any) -> dict[str, Any]:
        if not isinstance(wrapped, dict) or not isinstance(wrapped.get("payload"), dict):
            raise ContractError("invalid worker signature")
        claimed = wrapped["payload"].get("actor_id")
        key = self.workers.get(claimed) if isinstance(claimed, str) else None
        if key is None:
            raise ContractError("untrusted worker")
        p = _exact(unseal("tool-effect-request", wrapped, key), _EFFECT_FIELDS)
        if p["type"] != "tool-effect-request" or p["service_id"] != self.service_id:
            raise ContractError("wrong effect service")
        for name in ("task_id", "movement_id", "actor_id", "service_id", "kind", "effect_id"):
            _id(p[name], name)
        if p["kind"] not in TASK_KINDS or p["classification"] not in CLASSIFICATIONS:
            raise ContractError("unsupported effect profile")
        if not isinstance(p["effect_tag"], str) or not _TAG_RE.fullmatch(p["effect_tag"]):
            raise ContractError("invalid synthetic commitment")
        for name in ("policy_epoch", "owner_epoch", "cost"):
            _positive(p[name])
        if p["cost"] != 1 or p["grant_digest"] != digest(grant_sealed):
            raise ContractError("effect cost/grant binding mismatch")
        return p

    @staticmethod
    def _owner_matches(row: dict[str, Any], p: dict[str, Any]) -> bool:
        """Deliberate mutation target for the red/green epoch and owner test."""
        return row["owner_id"] == p["actor_id"] and row["owner_epoch"] == p["owner_epoch"]

    def effect(self, envelope: Any) -> tuple[int, dict[str, Any]]:
        """Verify independently and commit a simulated effect atomically at the sink."""
        try:
            e = _exact(envelope, frozenset({"version", "operation", "signed", "grant"}))
            if type(e["version"]) is not int or e["version"] != VERSION or e["operation"] != "synthetic_effect":
                raise ContractError("unsupported request")
            p = self._effect_fields(e["signed"], e["grant"])
            grant = verify_grant(e["grant"], self.grant_trust)
            check_grant_scope(
                grant, actor=p["actor_id"], audience=self.service_id,
                task_id=p["task_id"], kind=p["kind"], classification=p["classification"],
            )
            with self._transaction() as db:
                row = self._row(db, p["task_id"])
                status = "denied"
                if row is not None and row["active"] and row["movement_id"] == p["movement_id"] \
                        and row["kind"] == p["kind"] and row["classification"] == p["classification"] \
                        and row["destination_id"] == p["actor_id"] \
                        and self._owner_matches(row, p) \
                        and row["policy_epoch"] == p["policy_epoch"] \
                        and row["grant_id"] == grant["grant_id"] \
                        and hmac.compare_digest(row["grant_binding"], self.store.fingerprint(e["grant"])) \
                        and not row["revoked"]:
                    check_grant_live(grant, now=self._now(), revoked=False)
                    if row["uncertain"]:
                        status = "unknown"
                    else:
                        binding = self.store.fingerprint(p)
                        prior = db.execute(
                            "SELECT request_binding FROM tool_effects WHERE task_id=? AND effect_id=?",
                            (p["task_id"], p["effect_id"]),
                        ).fetchone()
                        if prior is not None:
                            status = "replayed" if hmac.compare_digest(prior[0], binding) else "conflict"
                        elif row["used"] < row["budget"]:
                            db.execute(
                                "INSERT INTO tool_effects(task_id,effect_id,request_binding,epoch)"
                                " VALUES(?,?,?,?)",
                                (p["task_id"], p["effect_id"], binding, p["owner_epoch"]),
                            )
                            db.execute("UPDATE tool_tasks SET used=used+1 WHERE task_id=?", (p["task_id"],))
                            status = "committed"
                self._log(db, p["task_id"], p["effect_id"], "effect", status)
            return self._reply("effect", status, task_id=p["task_id"], effect_id=p["effect_id"])
        except (ValueError, TypeError, KeyError, sqlite3.Error):
            # Cannot trust any unverified identity or echo submitted values.
            return self._reply("effect", "denied")

    def handle(self, path: str, data: Any) -> tuple[int, dict[str, Any]]:
        if path == "/v0/effects":
            return self.effect(data)
        if path == "/v0/operator":
            return self.operator_event(data)
        return 404, {"error": "not_found"}


def make_tool_server(authority: ToolEffectService, port: int = 0) -> ThreadingHTTPServer:
    """Real localhost listener. HTTP is plaintext; no production keys or sensitive data."""
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def do_GET(self) -> None:
            self._send(404, {"error": "not_found"})

        def _send(self, status: int, result: dict[str, Any]) -> None:
            raw = canonical(result).encode("utf-8")
            with suppress(BrokenPipeError, ConnectionResetError):
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        def do_POST(self) -> None:
            self.connection.settimeout(3)
            if self.path not in ("/v0/effects", "/v0/operator"):
                self._send(404, {"error": "not_found"})
                return
            if self.headers.get("Content-Type", "").split(";", 1)[0].lower() != "application/json":
                self._send(415, {"error": "content_type_required"})
                return
            try:
                n = int(self.headers.get("Content-Length", ""))
            except ValueError:
                self._send(400, {"error": "invalid_length"})
                return
            if not 0 < n <= 16384:
                self._send(413, {"error": "bounded_body_required"})
                return
            try:
                status, body = authority.handle(self.path, parse_json(self.rfile.read(n)))
            except (ValueError, TimeoutError, OSError):
                status, body = 400, {"error": "invalid_request"}
            self._send(status, body)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def load_service(config: Path, database: Path) -> ToolEffectService:
    """Configuration created only by the trusted test supervisor; never HTTP-supplied."""
    if os.name == "posix" and config.stat().st_mode & 0o077:
        raise ContractError("tool-service key file must be owner-only")
    value = _fields(parse_json(config.read_bytes()),
                    {"service_id", "grant_trust", "worker_verifiers", "operator_verifier",
                     "receipt_signer", "budget"}, "tool service config")
    if not isinstance(value["worker_verifiers"], dict):
        raise ContractError("invalid worker verifier map")
    return ToolEffectService(
        database, service_id=value["service_id"],
        grant_trust=TrustStore.from_dict(value["grant_trust"]),
        worker_verifiers={k: import_key(v) for k, v in value["worker_verifiers"].items()},
        operator_verifier=import_key(value["operator_verifier"]),
        receipt_signer=import_key(value["receipt_signer"]), budget=value["budget"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthetic localhost tool-effect service (NOT production)")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--port", type=int, default=0)
    options = parser.parse_args()
    authority = load_service(options.config, options.db)
    server = make_tool_server(authority, options.port)
    print(json.dumps({"port": server.server_port, "service": authority.service_id}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
