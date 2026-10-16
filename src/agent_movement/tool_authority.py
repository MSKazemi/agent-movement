"""Independent, localhost-only synthetic tool-side authority (issue #102).

The tool process owns its own SQLite effect ledger and Ed25519 receipt key. Callers
have no write access through this API except via independently signed operator
controls. This is NOT a secure OS sandbox, production IAM, a real payment tool,
or an exactly-once guarantee for external effects. Requires the ed25519 extra.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .core import ContractError, _id, canonical, digest, parse_json
from .trust import ED25519, Ed25519Key, b64d, b64e, import_key

VERSION = "0.1.0-tool-lab"
DOMAIN = b"agent-movement/independent-tool/v0.1\x00"
MAX_BODY = 16384
RESOURCE = "synthetic-counter"
ACTION = "increment"


class ToolDenied(Exception):
    def __init__(self, status: int, reason: str):
        super().__init__(reason)
        self.status = status
        self.reason = reason


def _shape(value: Any, fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ToolDenied(400, "invalid_contract")
    return value


def _number(value: Any, *, minimum: int = 0, maximum: int = 2**40) -> int:
    if type(value) is not int or not minimum <= value < maximum:
        raise ToolDenied(400, "invalid_integer")
    return value


def _name(value: Any) -> str:
    try:
        return _id(value, "identifier")
    except ContractError as exc:
        raise ToolDenied(400, "invalid_identifier") from exc


def _version(payload: dict[str, Any]) -> None:
    if payload.get("version") != VERSION:
        raise ToolDenied(400, "unsupported_version")


def _bytes(purpose: str, payload: dict[str, Any]) -> bytes:
    return DOMAIN + purpose.encode("ascii") + b"\x00" + canonical(payload).encode("utf-8")


def sign(purpose: str, payload: dict[str, Any], key: Ed25519Key) -> dict[str, Any]:
    """Sign locally; a verifier receives only a pinned public key, never this signer."""
    if key.alg != ED25519:
        raise ValueError("tool laboratory requires asymmetric Ed25519")
    return {"kid": key.kid, "payload": payload, "sig": b64e(key.sign(_bytes(purpose, payload)))}


def verified(purpose: str, signed: Any, key: Ed25519Key) -> dict[str, Any]:
    try:
        msg = _shape(signed, {"kid", "payload", "sig"})
        if msg["kid"] != key.kid or key.alg != ED25519 or not isinstance(msg["payload"], dict):
            raise ToolDenied(401, "invalid_signature")
        sig = b64d(msg["sig"], "signature", max_len=128)
        if len(sig) != 64 or not key.verify(_bytes(purpose, msg["payload"]), sig):
            raise ToolDenied(401, "invalid_signature")
        return msg["payload"]
    except (ContractError, TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ToolDenied(401, "invalid_signature") from exc


def _pub(key_data: Any) -> Ed25519Key:
    if not isinstance(key_data, dict) or set(key_data) != {"alg", "kid", "public"}:
        raise ValueError("only public Ed25519 verifier keys are allowed")
    key = import_key(key_data)
    if key.alg != ED25519:
        raise ValueError("requires public Ed25519 verification keys")
    return key


class IndependentTool:
    """Authority for one synthetic effect sink.

    The trusted operator controls task enrollment/transfer/cancellation, the issuer
    controls grants/revocations, and worker keys prove effect-actor possession. All
    mutable checks are repeated under BEGIN IMMEDIATE at the simulated commit.
    """

    def __init__(self, db_path: str | Path, *, operator: Ed25519Key,
                 issuer: Ed25519Key, workers: dict[str, Ed25519Key],
                 signer: Ed25519Key, clock: Callable[[], int] | None = None):
        for key in (operator, issuer, signer, *workers.values()):
            if key.alg != ED25519:
                raise ValueError("asymmetric signing required")
        if not workers:
            raise ValueError("at least one pinned worker key required")
        self.db_path = str(db_path)
        self.operator = operator.verifier()
        self.issuer = issuer.verifier()
        self.workers = {k: v.verifier() for k, v in workers.items()}
        self.signer = signer
        self.clock = clock if clock is not None else lambda: int(time.time())
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    movement_id TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    epoch INTEGER NOT NULL,
                    phase TEXT NOT NULL,
                    policy_epoch INTEGER NOT NULL,
                    grant_digest TEXT NOT NULL,
                    max_units INTEGER NOT NULL,
                    used_units INTEGER NOT NULL DEFAULT 0,
                    activation_id TEXT,
                    activation_digest TEXT);
                CREATE TABLE IF NOT EXISTS revocations (grant_id TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS controls (
                    event_id TEXT PRIMARY KEY, event_digest TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS effects (
                    task_id TEXT NOT NULL, effect_id TEXT NOT NULL,
                    actor TEXT NOT NULL, epoch INTEGER NOT NULL,
                    units INTEGER NOT NULL, grant_digest TEXT NOT NULL,
                    PRIMARY KEY (task_id,effect_id));
                CREATE TABLE IF NOT EXISTS decisions (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel TEXT NOT NULL, decision TEXT NOT NULL,
                    reason TEXT NOT NULL, task_id TEXT, effect_id TEXT,
                    signed_receipt TEXT NOT NULL);
            """)

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        try:
            db.execute("PRAGMA busy_timeout=10000")
            yield db
            if db.in_transaction:
                db.commit()
        except BaseException:
            if db.in_transaction:
                db.rollback()
            raise
        finally:
            db.close()

    def _grant(self, signed: Any, now: int, db: sqlite3.Connection) -> dict[str, Any]:
        g = _shape(verified("grant", signed, self.issuer), {
            "version", "grant_id", "actor", "audience", "movement_id", "task_id",
            "action", "resource", "classification", "policy_epoch",
            "max_units", "not_before", "expires_at",
        })
        _version(g)
        for name in ("grant_id", "actor", "audience", "movement_id", "task_id", "action", "resource"):
            _name(g[name])
        if (g["audience"] != "independent-tool" or g["action"] != ACTION
                or g["resource"] != RESOURCE or g["classification"] != "synthetic"):
            raise ToolDenied(403, "grant_scope")
        _number(g["policy_epoch"], minimum=1)
        _number(g["max_units"], minimum=1, maximum=1000000)
        _number(g["not_before"])
        _number(g["expires_at"])
        if now < g["not_before"] or now >= g["expires_at"]:
            raise ToolDenied(403, "grant_not_live")
        if db.execute("SELECT 1 FROM revocations WHERE grant_id=?", (g["grant_id"],)).fetchone():
            raise ToolDenied(403, "grant_revoked")
        return g

    @staticmethod
    def _row(db: sqlite3.Connection, task_id: str) -> tuple[Any, ...]:
        row = db.execute(
            "SELECT movement_id,owner,epoch,phase,policy_epoch,grant_digest,"
            "max_units,used_units,activation_id,activation_digest FROM tasks WHERE task_id=?",
            (task_id,),
        ).fetchone()
        if row is None:
            raise ToolDenied(403, "unknown_task")
        return row

    @staticmethod
    def _current(p: dict[str, Any], row: tuple[Any, ...]) -> None:
        if p["movement_id"] != row[0] or p["actor"] != row[1] or p["epoch"] != row[2]:
            raise ToolDenied(403, "stale_or_wrong_owner")

    def _actor(self, purpose: str, signed: Any) -> dict[str, Any]:
        # Caller-chosen actor strings never supply a trusted verifier key.
        if not isinstance(signed, dict) or not isinstance(signed.get("payload"), dict):
            raise ToolDenied(401, "unverified_actor")
        actor = signed["payload"].get("actor")
        key = self.workers.get(actor) if isinstance(actor, str) else None
        if key is None:
            raise ToolDenied(401, "unverified_actor")
        return verified(purpose, signed, key)

    def _control(self, db: sqlite3.Connection, signed: Any, now: int) -> str:
        if not isinstance(signed, dict) or not isinstance(signed.get("payload"), dict):
            raise ToolDenied(401, "invalid_control")
        event_type = signed["payload"].get("type")
        if event_type == "revoke":
            p = _shape(verified("revoke", signed, self.issuer),
                       {"version", "type", "event_id", "grant_id"})
        else:
            p = verified("control", signed, self.operator)
        _version(p)
        event_id = _name(p.get("event_id"))
        saved = db.execute("SELECT event_digest FROM controls WHERE event_id=?", (event_id,)).fetchone()
        fp = digest(signed)
        if saved is not None:
            if saved[0] != fp:
                raise ToolDenied(409, "control_id_conflict")
            return "replayed"
        if event_type == "revoke":
            _name(p["grant_id"])
            db.execute("INSERT OR IGNORE INTO revocations VALUES(?)", (p["grant_id"],))
        elif event_type == "enroll":
            _shape(p, {"version", "type", "event_id", "task_id", "movement_id",
                       "owner", "epoch", "policy_epoch", "grant_digest", "max_units"})
            task = _name(p["task_id"])
            _name(p["movement_id"])
            _name(p["owner"])
            if p["owner"] not in self.workers or _number(p["epoch"], minimum=1) != 1:
                raise ToolDenied(403, "invalid_initial_owner")
            _number(p["policy_epoch"], minimum=1)
            _number(p["max_units"], minimum=1, maximum=1000000)
            if not isinstance(p["grant_digest"], str) or len(p["grant_digest"]) != 64:
                raise ToolDenied(400, "invalid_grant_digest")
            if db.execute("SELECT 1 FROM tasks WHERE task_id=?", (task,)).fetchone():
                raise ToolDenied(409, "task_exists")
            db.execute("INSERT INTO tasks(task_id,movement_id,owner,epoch,phase,policy_epoch,"
                       "grant_digest,max_units) VALUES(?,?,?,?,?,?,?,?)",
                       (task, p["movement_id"], p["owner"], 1, "prepared",
                        p["policy_epoch"], p["grant_digest"], p["max_units"]))
        elif event_type == "transfer":
            _shape(p, {"version", "type", "event_id", "task_id", "movement_id",
                       "expected_owner", "expected_epoch", "new_owner", "policy_epoch"})
            task = _name(p["task_id"])
            row = self._row(db, task)
            if (row[0] != p["movement_id"] or row[1] != p["expected_owner"]
                    or row[2] != p["expected_epoch"] or row[3] != "prepared"
                    or row[4] != p["policy_epoch"] or p["new_owner"] not in self.workers
                    or p["new_owner"] == row[1]):
                raise ToolDenied(409, "transfer_precondition_failed")
            db.execute("UPDATE tasks SET owner=?,epoch=epoch+1,phase='fenced' WHERE task_id=?",
                       (p["new_owner"], task))
        elif event_type in ("cancel", "unknown"):
            _shape(p, {"version", "type", "event_id", "task_id", "movement_id"})
            task = _name(p["task_id"])
            row = self._row(db, task)
            if row[0] != p["movement_id"]:
                raise ToolDenied(403, "wrong_movement")
            db.execute("UPDATE tasks SET phase=? WHERE task_id=?",
                       ("cancelled" if event_type == "cancel" else "unknown", task))
        elif event_type == "policy_change":
            _shape(p, {"version", "type", "event_id", "task_id", "movement_id", "new_policy_epoch"})
            task = _name(p["task_id"])
            row = self._row(db, task)
            if row[0] != p["movement_id"] or _number(p["new_policy_epoch"], minimum=1) <= row[4]:
                raise ToolDenied(403, "invalid_policy_change")
            db.execute("UPDATE tasks SET phase='fenced',policy_epoch=? WHERE task_id=?",
                       (p["new_policy_epoch"], task))
        else:
            raise ToolDenied(400, "unknown_control")
        db.execute("INSERT INTO controls VALUES(?,?)", (event_id, fp))
        return "accepted"

    def _check_actor_grant(self, p: dict[str, Any], row: tuple[Any, ...],
                           db: sqlite3.Connection, now: int) -> dict[str, Any]:
        grant = self._grant(p["grant"], now, db)
        if (grant["task_id"] != p["task_id"] or grant["movement_id"] != p["movement_id"]
                or grant["actor"] != p["actor"] or grant["policy_epoch"] != row[4]
                or digest(p["grant"]) != row[5]):
            raise ToolDenied(403, "grant_not_bound_to_task")
        return grant

    def _require_current(self, p: dict[str, Any], row: tuple[Any, ...]) -> None:
        """A mutation test removes THIS check and must expose a stale-epoch commit."""
        self._current(p, row)

    def _activate(self, db: sqlite3.Connection, signed: Any, now: int) -> str:
        p = _shape(self._actor("activate", signed), {
            "version", "actor", "movement_id", "task_id", "epoch",
            "grant", "activation_id", "expires_at",
        })
        _version(p)
        task = _name(p["task_id"])
        _name(p["activation_id"])
        _number(p["epoch"], minimum=1)
        _number(p["expires_at"])
        row = self._row(db, task)
        self._require_current(p, row)
        grant = self._check_actor_grant(p, row, db, now)
        if p["expires_at"] <= now or p["expires_at"] > grant["expires_at"]:
            raise ToolDenied(403, "activation_expired")
        fp = digest(signed)
        if row[3] == "active" and row[8] == p["activation_id"] and row[9] == fp:
            return "replayed"
        if row[3] != "fenced":
            raise ToolDenied(403, "not_fenced")
        db.execute("UPDATE tasks SET phase='active',activation_id=?,activation_digest=? WHERE task_id=?",
                   (p["activation_id"], fp, task))
        return "activated"

    def _effect(self, db: sqlite3.Connection, signed: Any, now: int) -> str:
        p = _shape(self._actor("effect", signed), {
            "version", "actor", "movement_id", "task_id", "epoch",
            "grant", "effect_id", "action", "resource", "units",
        })
        _version(p)
        task = _name(p["task_id"])
        effect = _name(p["effect_id"])
        _number(p["epoch"], minimum=1)
        units = _number(p["units"], minimum=1, maximum=1000)
        row = self._row(db, task)
        self._require_current(p, row)
        grant = self._check_actor_grant(p, row, db, now)
        if row[3] != "active":
            raise ToolDenied(403, "destination_not_active")
        if p["action"] != ACTION or p["resource"] != RESOURCE:
            raise ToolDenied(403, "wrong_action_or_resource")
        if units > grant["max_units"]:
            raise ToolDenied(403, "grant_budget")
        previous = db.execute(
            "SELECT actor,epoch,units,grant_digest FROM effects WHERE task_id=? AND effect_id=?",
            (task, effect),
        ).fetchone()
        if previous is not None:
            if previous != (p["actor"], p["epoch"], units, row[5]):
                raise ToolDenied(409, "effect_id_conflict")
            return "replayed"
        if row[7] + units > min(row[6], grant["max_units"]):
            raise ToolDenied(403, "effect_budget_exhausted")
        db.execute("INSERT INTO effects VALUES(?,?,?,?,?,?)",
                   (task, effect, p["actor"], p["epoch"], units, row[5]))
        db.execute("UPDATE tasks SET used_units=used_units+? WHERE task_id=?", (units, task))
        return "committed"

    def _reconcile(self, db: sqlite3.Connection, signed: Any, now: int) -> str:
        p = _shape(self._actor("reconcile", signed), {
            "version", "actor", "movement_id", "task_id", "epoch", "grant", "effect_id",
        })
        _version(p)
        task = _name(p["task_id"])
        effect = _name(p["effect_id"])
        _number(p["epoch"], minimum=1)
        row = self._row(db, task)
        self._require_current(p, row)
        self._check_actor_grant(p, row, db, now)
        found = db.execute("SELECT 1 FROM effects WHERE task_id=? AND effect_id=?",
                           (task, effect)).fetchone()
        return "committed" if found is not None else "unknown"

    def _receipt(self, db: sqlite3.Connection, channel: str, decision: str, reason: str,
                 signed: Any) -> dict[str, Any]:
        payload = signed.get("payload", {}) if isinstance(signed, dict) else {}
        if not isinstance(payload, dict):
            payload = {}
        # No unverified caller fields are retained on denials: an attacker could put
        # sensitive synthetic text in an identifier even when the signature is wrong.
        task = payload.get("task_id") if decision != "denied" else None
        effect = payload.get("effect_id") if decision != "denied" else None
        task = task if isinstance(task, str) and len(task) <= 128 and task.isascii() else None
        effect = effect if isinstance(effect, str) and len(effect) <= 128 and effect.isascii() else None
        db.execute("INSERT INTO decisions(channel,decision,reason,task_id,effect_id,signed_receipt)"
                   " VALUES(?,?,?,?,?,'')", (channel, decision, reason, task, effect))
        seq = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        receipt = sign("receipt", {"version": VERSION, "service": "independent-tool",
                                   "seq": seq, "decision": decision, "reason": reason,
                                   "task_id": task, "effect_id": effect}, self.signer)
        db.execute("UPDATE decisions SET signed_receipt=? WHERE seq=?", (canonical(receipt), seq))
        return receipt

    def handle(self, channel: str, signed: Any) -> tuple[int, dict[str, Any]]:
        if channel not in {"control", "activate", "effect", "reconcile"}:
            return 404, {"error": "unknown_route"}
        try:
            with self._db() as db:
                db.execute("BEGIN IMMEDIATE")
                now = self.clock()  # server-owned time; no caller time is trusted
                if channel == "control":
                    decision = self._control(db, signed, now)
                elif channel == "activate":
                    decision = self._activate(db, signed, now)
                elif channel == "effect":
                    decision = self._effect(db, signed, now)
                else:
                    decision = self._reconcile(db, signed, now)
                receipt = self._receipt(db, channel, decision, "none", signed)
                db.commit()
                return 200, {"receipt": receipt}
        except (ToolDenied, sqlite3.DatabaseError) as exc:
            status = exc.status if isinstance(exc, ToolDenied) else 503
            reason = exc.reason if isinstance(exc, ToolDenied) else "authority_unavailable"
            try:
                with self._db() as db:
                    db.execute("BEGIN IMMEDIATE")
                    receipt = self._receipt(db, channel, "denied", reason, signed)
                    db.commit()
                    return status, {"receipt": receipt}
            except sqlite3.DatabaseError:
                return 503, {"error": "authority_unavailable"}


def make_server(service: IndependentTool, port: int = 0) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return  # raw request paths/payloads are attacker-controlled

        def do_POST(self) -> None:
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                self._send(415, {"error": "content_type_required"})
                return
            try:
                size = int(self.headers.get("Content-Length", ""))
            except ValueError:
                self._send(400, {"error": "invalid_length"})
                return
            if not 0 < size <= MAX_BODY:
                self._send(413, {"error": "body_size"})
                return
            try:
                signed = parse_json(self.rfile.read(size))
            except ContractError:
                self._send(400, {"error": "invalid_json"})
                return
            if self.path not in ("/v0/tool/control", "/v0/tool/activate",
                                 "/v0/tool/effect", "/v0/tool/reconcile"):
                self._send(404, {"error": "unknown_route"})
                return
            status, body = service.handle(self.path.rsplit("/", 1)[-1], signed)
            self._send(status, body)

        def _send(self, status: int, body: dict[str, Any]) -> None:
            encoded = canonical(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server


def load(config_path: Path) -> IndependentTool:
    c = _shape(json.loads(config_path.read_text(encoding="utf-8")), {
        "db", "operator_public", "issuer_public", "workers_public", "tool_signer",
    })
    if not isinstance(c["workers_public"], dict) or not c["workers_public"]:
        raise ValueError("missing workers")
    worker_keys = {_name(agent): _pub(value) for agent, value in c["workers_public"].items()}
    signer = import_key(c["tool_signer"])
    if signer.alg != ED25519 or not signer.secret_forms():
        raise ValueError("tool signer private Ed25519 key required")
    return IndependentTool(c["db"], operator=_pub(c["operator_public"]),
                           issuer=_pub(c["issuer_public"]), workers=worker_keys, signer=signer)


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthetic independent tool effect sink (localhost only)")
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    service = load(args.config)
    server = make_server(service)
    print(canonical({"port": server.server_port, "service": "independent-tool"}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
