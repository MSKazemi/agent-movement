"""Independent-process synthetic tool-side policy enforcement experiment (issue #102).

The tool service verifies an operator-provisioned authority row, issuer-signed
grant, destination proof-of-possession and current policy/owner epochs. Only an
opaque result commitment is processed; no task text or real tool is executed.

This is not a network sandbox, OS privilege boundary, or production gateway.
A compromised host, keys, operator, SQLite file or kernel breaks these claims.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import time
from collections.abc import Callable
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .core import Conflict, ContractError, PolicyDenied, _fields, _id, canonical, digest, parse_json
from .trust import (
    TrustStore,
    Unauthenticated,
    Unauthorized,
    b64d,
    b64e,
    check_grant_live,
    check_grant_scope,
    import_key,
    verify_grant,
)

_DOMAIN = b"agent-movement/independent-tool/v0\n"
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_PROVISION = {
    "type", "task_id", "movement_id", "origin_id", "destination_id", "kind",
    "classification", "resource", "grant_digest", "owner_epoch", "policy_epoch",
    "expires_at", "budget_limit",
}
_UPDATE = {
    "type", "task_id", "movement_id", "expected_policy_epoch", "new_policy_epoch",
    "expected_owner_epoch", "new_owner_epoch", "revoke",
}
_EFFECT = {
    "type", "task_id", "movement_id", "destination_id", "kind", "classification",
    "resource", "owner_epoch", "policy_epoch", "effect_id", "payload_commitment", "grant",
}
_QUERY = {"type", "task_id", "movement_id", "effect_id"}
_ROW_FIELDS = (
    "task_id", "movement_id", "origin_id", "destination_id", "kind",
    "classification", "resource", "grant_digest", "owner_epoch", "policy_epoch",
    "expires_at", "budget_limit", "budget_used", "revoked",
)


def sign_tool(purpose: str, payload: dict[str, Any], signer: Any) -> dict[str, Any]:
    """Domain-separated signature for synthetic operator, executor and tool receipts."""
    data = _DOMAIN + purpose.encode("ascii") + b"\n" + canonical(payload).encode("utf-8")
    return {"alg": signer.alg, "kid": signer.kid, "payload": payload,
            "sig": b64e(signer.sign(data))}


def verify_tool(purpose: str, signed: Any, verifier: Any) -> dict[str, Any]:
    try:
        s = _fields(signed, {"alg", "kid", "payload", "sig"}, "signed tool message")
        if s["alg"] != verifier.alg or s["kid"] != verifier.kid or not isinstance(s["payload"], dict):
            raise Unauthenticated("unexpected tool signing principal")
        value = _DOMAIN + purpose.encode("ascii") + b"\n" + canonical(s["payload"]).encode("utf-8")
        if not verifier.verify(value, b64d(s["sig"], "tool signature")):
            raise Unauthenticated("invalid tool signature")
    except (ContractError, ValueError, TypeError, UnicodeError) as exc:
        raise Unauthenticated("malformed signed tool message") from exc
    payload: dict[str, Any] = s["payload"]
    return payload


def _epoch(value: Any, label: str) -> int:
    if type(value) is not int or value < 1:
        raise ContractError(f"invalid {label}")
    return value


def _digest(value: Any) -> str:
    if not isinstance(value, str) or not _HEX64.fullmatch(value):
        raise ContractError("invalid commitment")
    return value


class ToolAuthority:
    """Independent service-owned SQLite authority and synthetic effect ledger.

    The caller has no setter for trusted signing keys or ownership facts.
    Operator controls are signed and applied via transactions; executor effects
    are separately signed and checked at this service's commit boundary.
    """

    def __init__(
        self, path: str | Path, *,
        destination_id: str, operator_verifier: Any, executor_verifier: Any,
        tool_signer: Any, grant_trust: TrustStore,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.path = Path(path)
        self.destination_id = _id(destination_id, "destination_id")
        self.operator = operator_verifier
        self.executor = executor_verifier
        self.signer = tool_signer
        self.trust = grant_trust
        self.clock = clock
        if not grant_trust.grant_issuers or not all(
            hasattr(k, "verify") for k in (self.operator, self.executor, self.signer)
        ):
            raise ContractError("trusted keys and grant issuers required")
        with closing(self._connect()) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS tool_authority (
                    task_id TEXT PRIMARY KEY, movement_id TEXT NOT NULL UNIQUE,
                    origin_id TEXT NOT NULL, destination_id TEXT NOT NULL,
                    kind TEXT NOT NULL, classification TEXT NOT NULL,
                    resource TEXT NOT NULL, grant_digest TEXT NOT NULL,
                    owner_epoch INTEGER NOT NULL, policy_epoch INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL, budget_limit INTEGER NOT NULL,
                    budget_used INTEGER NOT NULL DEFAULT 0, revoked INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS tool_effects (
                    task_id TEXT NOT NULL, effect_id TEXT NOT NULL,
                    request_digest TEXT NOT NULL, decision_json TEXT NOT NULL,
                    owner_epoch INTEGER NOT NULL,
                    PRIMARY KEY (task_id, effect_id));
                CREATE TABLE IF NOT EXISTS tool_decisions (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL, effect_id TEXT NOT NULL,
                    decision TEXT NOT NULL, policy_epoch INTEGER NOT NULL);
            """)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _now(self) -> int:
        try:
            now = self.clock()
            if type(now) not in (int, float) or not float("-inf") < float(now) < float("inf"):
                raise ValueError("invalid time")
            return int(now)
        except Exception as exc:
            raise PolicyDenied("trusted clock unavailable") from exc

    @staticmethod
    def _row(db: sqlite3.Connection, task_id: str) -> dict[str, Any]:
        row = db.execute(
            f"SELECT {','.join(_ROW_FIELDS)} FROM tool_authority WHERE task_id=?", (task_id,)
        ).fetchone()
        if row is None:
            raise Unauthorized("unknown tool authority")
        return dict(zip(_ROW_FIELDS, row, strict=True))

    def provision(self, signed: Any) -> dict[str, Any]:
        p = _fields(verify_tool("provision", signed, self.operator), _PROVISION, "tool provision")
        if p["type"] != "tool-provision":
            raise ContractError("invalid tool provision type")
        for key in ("task_id", "movement_id", "origin_id", "destination_id", "resource"):
            _id(p[key], key)
        if (p["destination_id"] != self.destination_id or
                p["kind"] not in ("word_count", "sha256") or
                p["classification"] not in ("synthetic", "public")):
            raise Unauthorized("unsupported tool authority scope")
        _digest(p["grant_digest"])
        _epoch(p["owner_epoch"], "owner_epoch")
        _epoch(p["policy_epoch"], "policy_epoch")
        if (type(p["expires_at"]) is not int or p["expires_at"] <= self._now()
                or type(p["budget_limit"]) is not int or not 1 <= p["budget_limit"] <= 100):
            raise Unauthorized("invalid tool expiry or effect budget")
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM tool_authority WHERE task_id=?", (p["task_id"],)).fetchone():
                raise Conflict("tool authority already exists")
            db.execute(
                "INSERT INTO tool_authority (task_id,movement_id,origin_id,destination_id,kind,"
                "classification,resource,grant_digest,owner_epoch,policy_epoch,expires_at,budget_limit)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                tuple(p[k] for k in (
                    "task_id", "movement_id", "origin_id", "destination_id", "kind",
                    "classification", "resource", "grant_digest", "owner_epoch",
                    "policy_epoch", "expires_at", "budget_limit",
                )),
            )
            db.commit()
        return {"status": "provisioned", "task_id": p["task_id"]}

    def update(self, signed: Any) -> dict[str, Any]:
        p = _fields(verify_tool("update", signed, self.operator), _UPDATE, "tool update")
        if p["type"] != "tool-update" or type(p["revoke"]) is not bool:
            raise ContractError("invalid tool update type")
        _id(p["task_id"], "task_id")
        _id(p["movement_id"], "movement_id")
        for key in ("expected_policy_epoch", "new_policy_epoch",
                    "expected_owner_epoch", "new_owner_epoch"):
            _epoch(p[key], key)
        if (p["new_policy_epoch"] <= p["expected_policy_epoch"] or
                p["new_owner_epoch"] < p["expected_owner_epoch"]):
            raise ContractError("tool update must be monotonic")
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._row(db, p["task_id"])
            if (row["movement_id"] != p["movement_id"] or
                    row["policy_epoch"] != p["expected_policy_epoch"] or
                    row["owner_epoch"] != p["expected_owner_epoch"]):
                raise Conflict("stale operator update")
            if row["revoked"] and not p["revoke"]:
                raise Unauthorized("cannot un-revoke authority")
            db.execute(
                "UPDATE tool_authority SET policy_epoch=?,owner_epoch=?,revoked=? WHERE task_id=?",
                (p["new_policy_epoch"], p["new_owner_epoch"],
                 int(bool(row["revoked"]) or p["revoke"]), p["task_id"]),
            )
            db.commit()
        return {"status": "updated", "task_id": p["task_id"]}

    def effect(self, signed: Any) -> dict[str, Any]:
        p = _fields(verify_tool("effect", signed, self.executor), _EFFECT, "tool effect")
        if p["type"] != "tool-effect":
            raise ContractError("invalid tool effect type")
        for key in ("task_id", "movement_id", "destination_id", "resource", "effect_id"):
            _id(p[key], key)
        _digest(p["payload_commitment"])
        _epoch(p["owner_epoch"], "owner_epoch")
        _epoch(p["policy_epoch"], "policy_epoch")
        signed_grant = p["grant"]
        grant = verify_grant(signed_grant, self.trust)
        commitment = digest(p)
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._row(db, p["task_id"])
            if any(p[key] != row[key] for key in (
                "movement_id", "destination_id", "kind", "classification", "resource",
                "owner_epoch", "policy_epoch",
            )):
                raise Unauthorized("tool scope or authority snapshot changed")
            if row["destination_id"] != self.destination_id or row["revoked"]:
                raise Unauthorized("revoked or wrong tool recipient")
            if self._now() >= row["expires_at"]:
                raise Unauthorized("tool authority expired")
            if digest(signed_grant) != row["grant_digest"]:
                raise Unauthorized("tool grant was replaced or modified")
            check_grant_scope(
                grant, actor=row["origin_id"], audience=row["destination_id"],
                task_id=row["task_id"], kind=row["kind"], classification=row["classification"],
            )
            check_grant_live(grant, now=self._now(), revoked=bool(row["revoked"]))
            prior = db.execute(
                "SELECT request_digest,decision_json FROM tool_effects WHERE task_id=? AND effect_id=?",
                (p["task_id"], p["effect_id"]),
            ).fetchone()
            if prior is not None:
                if prior[0] != commitment:
                    raise Conflict("conflicting tool effect retry")
                db.commit()
                return {"status": "replayed", "receipt": json.loads(prior[1])}
            if row["budget_used"] >= row["budget_limit"]:
                raise Unauthorized("tool effect budget exhausted")
            seq = db.execute(
                "INSERT INTO tool_decisions (task_id,effect_id,decision,policy_epoch)"
                " VALUES(?,?,?,?)",
                (p["task_id"], p["effect_id"], "committed", row["policy_epoch"]),
            ).lastrowid
            receipt = sign_tool("receipt", {
                "type": "tool-receipt", "status": "committed", "task_id": p["task_id"],
                "movement_id": p["movement_id"], "effect_id": p["effect_id"],
                "owner_epoch": row["owner_epoch"], "policy_epoch": row["policy_epoch"],
                "sequence": seq,
            }, self.signer)
            db.execute(
                "INSERT INTO tool_effects VALUES (?,?,?,?,?)",
                (p["task_id"], p["effect_id"], commitment, canonical(receipt), row["owner_epoch"]),
            )
            db.execute(
                "UPDATE tool_authority SET budget_used=budget_used+1 WHERE task_id=?", (p["task_id"],)
            )
            db.commit()
            return {"status": "committed", "receipt": receipt}

    def query(self, signed: Any) -> dict[str, Any]:
        """A lost HTTP reply is UNKNOWN to the sender until independently reconciled."""
        p = _fields(verify_tool("query", signed, self.executor), _QUERY, "tool query")
        if p["type"] != "tool-query":
            raise ContractError("invalid tool query type")
        for key in ("task_id", "movement_id", "effect_id"):
            _id(p[key], key)
        with closing(self._connect()) as db:
            row = self._row(db, p["task_id"])
            if row["movement_id"] != p["movement_id"]:
                raise Unauthorized("wrong tool movement")
            prior = db.execute(
                "SELECT decision_json FROM tool_effects WHERE task_id=? AND effect_id=?",
                (p["task_id"], p["effect_id"]),
            ).fetchone()
        return {"status": "committed" if prior is not None else "absent",
                "receipt": json.loads(prior[0]) if prior is not None else None}


class LocalToolServer(ThreadingHTTPServer):
    daemon_threads = True


def make_tool_server(authority: ToolAuthority, port: int = 0) -> LocalToolServer:
    """Only localhost-bound, synthetic tool interface. Never a public host listener."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return  # never print task or request contents

        def respond(self, status: int, value: dict[str, Any]) -> None:
            data = canonical(value).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self) -> None:
            routes = {
                "/v0/tool/provision": authority.provision,
                "/v0/tool/update": authority.update,
                "/v0/tool/effects": authority.effect,
                "/v0/tool/query": authority.query,
            }
            route = routes.get(self.path)
            if route is None:
                self.respond(404, {"error": "not_found"})
                return
            if self.headers.get("Content-Type", "").split(";", 1)[0].strip() != "application/json":
                self.respond(415, {"error": "content_type_required"})
                return
            try:
                length = int(self.headers.get("Content-Length", ""))
                if not 0 < length <= 16384:
                    raise ContractError("invalid body size")
                raw = self.rfile.read(length)
                outcome = route(parse_json(raw))
            except Unauthenticated:
                self.respond(401, {"error": "unauthenticated"})
            except (Unauthorized, PolicyDenied):
                self.respond(403, {"error": "forbidden"})
            except Conflict:
                self.respond(409, {"error": "conflict"})
            except (ContractError, ValueError):
                self.respond(400, {"error": "invalid_contract"})
            except Exception:
                self.respond(500, {"error": "internal_error"})
            else:
                self.respond(200, outcome)

    return LocalToolServer(("127.0.0.1", port), Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthetic independent tool authority (loopback only)")
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    # Config with synthetic *tool signing key* is provisioned out of band; never by the agent.
    config = json.loads(args.config.read_text(encoding="utf-8"))
    _fields(config, {"db_path", "destination_id", "operator_verifier", "executor_verifier",
                     "tool_signer", "grant_trust"}, "tool service configuration")
    service = ToolAuthority(
        config["db_path"],
        destination_id=config["destination_id"],
        operator_verifier=import_key(config["operator_verifier"]),
        executor_verifier=import_key(config["executor_verifier"]),
        tool_signer=import_key(config["tool_signer"]),
        grant_trust=TrustStore.from_dict(config["grant_trust"]),
    )
    server = make_tool_server(service)
    print(canonical({"port": server.server_port, "service": "synthetic-tool"}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
