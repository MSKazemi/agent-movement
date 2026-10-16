"""Opt-in, synthetic single-store protected transfer/effect lane.

All authority is verified from pinned signing keys and receiver-owned continuity
facts. The ONLY atomicity claim is about SQLite owner rows, guard state, revocation,
budget and simulated effect rows in ONE authority store. Legacy routes for a guarded
task are rejected by core.EffectGateway. This is not an OS sandbox or external PEP.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import time
from collections.abc import Callable, Mapping
from typing import Any

from .continuity_runtime import ContinuityRuntime
from .core import Conflict, ContractError, PolicyDenied, SQLiteStore, _id, canonical, digest
from .peer import PeerLedger
from .trust import (
    TrustStore,
    Unauthorized,
    check_grant_live,
    check_grant_scope,
    sealed_parts,
    unseal,
    verify_grant,
)

_INTENT_FIELDS = frozenset({
    "type", "movement_id", "task_id", "origin_id", "destination_id",
    "expected_epoch", "kind", "classification", "policy_epoch", "grant_digest",
})
_NOTICE_FIELDS = frozenset({"type", "task_id", "movement_id"})
_STATES = frozenset({"prepared", "fenced", "active"})
_ACTIVATION_FIELDS = frozenset({
    "type", "task_id", "movement_id", "destination_id", "owner_epoch",
    "kind", "scope", "grant_digest", "policy_epoch", "activation_id",
    "nonce", "issued_at", "expires_at",
})
_EFFECT_FIELDS = frozenset({
    "type", "task_id", "movement_id", "destination_id", "owner_epoch",
    "activation_id", "effect_id", "payload_sha256", "nonce", "issued_at", "expires_at",
})
_MAX_PROOF_LIFETIME = 120  # seconds; signed, single-task synthetic evidence only


class GuardedAuthority:
    """Opt-in authority lane: enroll, fenced transfer, guarded synthetic effect.

    Provision every key, budget, store and trusted clock separately from untrusted
    agent requests. Caller-supplied IDs never count as authenticated identities.
    """

    def __init__(
        self, store: SQLiteStore, continuity: ContinuityRuntime, trust: TrustStore, *,
        origin_verifiers: Mapping[str, Any], destination_verifiers: Mapping[str, Any],
        cancel_verifier: Any, incident_verifier: Any, budget_limit: int = 2,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(store, SQLiteStore) or not isinstance(continuity, ContinuityRuntime):
            raise ContractError("trusted store and continuity authority required")
        if continuity.store.path != store.path or not isinstance(trust, TrustStore):
            raise ContractError("all authority checks must use the same SQLite store")
        if continuity.grant_trust is not trust:
            raise ContractError("grant trust roots must agree")
        if not origin_verifiers or not destination_verifiers or not callable(clock):
            raise ContractError("trusted origin/destination verifiers and clock required")
        if set(destination_verifiers) != {continuity.recipient_id}:
            raise ContractError("destination signer must be independently pinned")
        for key in destination_verifiers.values():
            if not hasattr(key, "verify") or not hasattr(key, "kid"):
                raise ContractError("destination identity verifier required")
        if not (type(budget_limit) is int and 1 <= budget_limit <= 100):
            raise ContractError("invalid operator-provisioned effect budget")
        if not (hasattr(cancel_verifier, "verify") and hasattr(incident_verifier, "verify")):
            raise ContractError("pinned operator verifiers required")
        self.store = store
        self.continuity = continuity
        self.trust = trust
        self.origin_verifiers = dict(origin_verifiers)
        self.destination_verifiers = dict(destination_verifiers)
        self.cancel_verifier = cancel_verifier
        self.incident_verifier = incident_verifier
        self.budget_limit = budget_limit
        self.clock = clock
        # Also ensures that receiver-grant revocations are in this authority store.
        PeerLedger(store)
        with store._connection() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS guarded_tasks (
                    task_id TEXT PRIMARY KEY,
                    movement_id TEXT NOT NULL UNIQUE,
                    origin_id TEXT NOT NULL,
                    origin_epoch INTEGER NOT NULL,
                    destination_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    classification TEXT NOT NULL,
                    grant_json TEXT NOT NULL,
                    policy_epoch INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    budget_limit INTEGER NOT NULL,
                    budget_used INTEGER NOT NULL DEFAULT 0,
                    cancelled INTEGER NOT NULL DEFAULT 0,
                    unknown_effect INTEGER NOT NULL DEFAULT 0
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS guarded_activations(
                    task_id TEXT PRIMARY KEY,
                    movement_id TEXT NOT NULL,
                    destination_id TEXT NOT NULL,
                    owner_epoch INTEGER NOT NULL,
                    activation_id TEXT NOT NULL UNIQUE,
                    nonce TEXT NOT NULL UNIQUE,
                    receipt_digest TEXT NOT NULL,
                    expires_at INTEGER NOT NULL)
            """)

    def _now(self) -> int:
        try:
            now = self.clock()
        except Exception as exc:
            raise PolicyDenied("trusted clock unavailable") from exc
        if type(now) not in (int, float) or not float("-inf") < float(now) < float("inf"):
            raise PolicyDenied("invalid trusted time")
        return int(now)

    def _verify_intent(self, intent: Any, signed_grant: Any) -> dict[str, Any]:
        wrapped = sealed_parts(intent, "guarded-transfer-intent")
        claimed = wrapped["payload"]
        actor = claimed.get("origin_id")
        if not isinstance(actor, str):
            raise Unauthorized("untrusted_movement_origin")
        key = self.origin_verifiers.get(actor)
        if key is None:
            raise Unauthorized("untrusted_movement_origin")
        payload = unseal("guarded-transfer-intent", intent, key)
        if set(payload) != _INTENT_FIELDS or payload["type"] != "guarded-transfer-intent":
            raise ContractError("invalid transfer intent")
        for field in ("movement_id", "task_id", "origin_id", "destination_id", "kind"):
            _id(payload[field], field)
        if (type(payload["expected_epoch"]) is not int or payload["expected_epoch"] < 1
                or type(payload["policy_epoch"]) is not int or payload["policy_epoch"] < 1):
            raise ContractError("invalid epoch in signed intent")
        if payload["origin_id"] == payload["destination_id"]:
            raise ContractError("destination must differ from source")
        if payload["classification"] not in ("synthetic", "public"):
            raise ContractError("unsupported synthetic classification")
        if payload["grant_digest"] != digest(signed_grant):
            raise Unauthorized("signed_intent_grant_mismatch")
        return payload

    @staticmethod
    def _row(db: sqlite3.Connection, task_id: str) -> dict[str, Any]:
        names = ("task_id", "movement_id", "origin_id", "origin_epoch", "destination_id", "kind",
                 "classification", "grant_json", "policy_epoch", "status",
                 "budget_limit", "budget_used", "cancelled", "unknown_effect")
        r = db.execute(
            "SELECT task_id,movement_id,origin_id,origin_epoch,destination_id,kind,"
            "classification,grant_json,policy_epoch,status,budget_limit,budget_used,"
            "cancelled,unknown_effect FROM guarded_tasks WHERE task_id=?", (task_id,)
        ).fetchone()
        if r is None:
            raise PolicyDenied("task not enrolled in guarded authority")
        return dict(zip(names, r, strict=True))

    def _check(self, db: sqlite3.Connection, row: dict[str, Any], now: int) -> dict[str, Any]:
        grant = verify_grant(json.loads(row["grant_json"]), self.trust)
        check_grant_scope(
            grant, actor=row["origin_id"], audience=row["destination_id"],
            task_id=row["task_id"], kind=row["kind"], classification=row["classification"],
        )
        check_grant_live(grant, now=now, revoked=PeerLedger.is_revoked(db, grant["grant_id"]))
        if row["cancelled"]:
            raise PolicyDenied("guarded task cancelled")
        if row["unknown_effect"]:
            raise PolicyDenied("unknown external outcome requires reconciliation")
        self.continuity.require(
            db, kind=row["kind"], movement_id=row["movement_id"],
            task_id=row["task_id"], policy_epoch=row["policy_epoch"], now=now,
        )
        return grant

    def enroll(self, intent: Any, signed_grant: Any) -> None:
        """Enroll BEFORE exposing this task to legacy effect routes.

        Caller cannot choose budget, policy, approvers or signing keys.
        Enrollment is deliberately not recovery of an already-effectful task.
        """
        p = self._verify_intent(intent, signed_grant)
        grant = verify_grant(signed_grant, self.trust)
        check_grant_scope(
            grant, actor=p["origin_id"], audience=p["destination_id"],
            task_id=p["task_id"], kind=p["kind"], classification=p["classification"],
        )
        if p["destination_id"] != self.continuity.recipient_id:
            raise Unauthorized("continuity destination mismatch")
        with self.store._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM guarded_tasks WHERE task_id=?", (p["task_id"],)).fetchone():
                raise Conflict("task already enrolled")
            owner = db.execute("SELECT agent_id,epoch FROM owners WHERE task_id=?", (p["task_id"],)).fetchone()
            if owner != (p["origin_id"], p["expected_epoch"]):
                raise Conflict("stale or absent source owner")
            if db.execute("SELECT 1 FROM effects WHERE task_id=?", (p["task_id"],)).fetchone():
                raise PolicyDenied("existing effects require separate reconciliation")
            row = {
                "task_id": p["task_id"], "movement_id": p["movement_id"],
                "origin_id": p["origin_id"], "origin_epoch": p["expected_epoch"],
                "destination_id": p["destination_id"],
                "kind": p["kind"], "classification": p["classification"],
                "grant_json": canonical(signed_grant), "policy_epoch": p["policy_epoch"],
                "cancelled": 0, "unknown_effect": 0,
            }
            self._check(db, row, self._now())
            db.execute(
                "INSERT INTO guarded_tasks (task_id,movement_id,origin_id,origin_epoch,destination_id,"
                "kind,classification,grant_json,policy_epoch,status,budget_limit,budget_used)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,0)",
                (p["task_id"], p["movement_id"], p["origin_id"], p["expected_epoch"],
                 p["destination_id"], p["kind"], p["classification"], canonical(signed_grant),
                 p["policy_epoch"], "prepared", self.budget_limit),
            )
            db.commit()

    def transfer(self, task_id: str, movement_id: str) -> int:
        """Check signed authority AND fence the old owner in the same write txn."""
        task_id, movement_id = _id(task_id, "task_id"), _id(movement_id, "movement_id")
        with self.store._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._row(db, task_id)
            if row["movement_id"] != movement_id or row["status"] != "prepared":
                raise Conflict("unexpected guarded movement or phase")
            self._check(db, row, self._now())
            owner = db.execute("SELECT agent_id,epoch FROM owners WHERE task_id=?", (task_id,)).fetchone()
            if owner != (row["origin_id"], row["origin_epoch"]):
                raise Conflict("source owner/epoch changed since signed intent")
            if type(row["origin_epoch"]) is not int:
                raise Conflict("invalid stored source epoch")
            next_epoch = int(row["origin_epoch"]) + 1
            modified = db.execute(
                "UPDATE owners SET agent_id=?,epoch=? WHERE task_id=? AND agent_id=? AND epoch=?",
                (row["destination_id"], next_epoch, task_id, owner[0], owner[1]),
            )
            if modified.rowcount != 1:
                raise Conflict("concurrent transfer or stale epoch")
            db.execute("UPDATE guarded_tasks SET status='fenced' WHERE task_id=?", (task_id,))
            db.commit()
            return next_epoch


    @staticmethod
    def _proof_window(p: dict[str, Any], now: int) -> None:
        """Check a bounded signed window against trusted clock, rejecting bool-as-int."""
        start, end = p["issued_at"], p["expires_at"]
        if (type(start) is not int or type(end) is not int or start < 0
                or end <= start or end - start > _MAX_PROOF_LIFETIME
                or start > now or now >= end):
            raise Unauthorized("guarded_signature_expired_or_not_current")

    def _destination_proof(
        self, token: Any, purpose: str, row: dict[str, Any],
        *, now: int, fields: frozenset[str],
    ) -> dict[str, Any]:
        key = self.destination_verifiers.get(row["destination_id"])
        if key is None:
            raise Unauthorized("guarded_destination_untrusted")
        p = unseal(purpose, token, key)
        if set(p) != fields or p["type"] != purpose:
            raise ContractError("invalid signed destination proof")
        for name in ("task_id", "movement_id", "destination_id", "activation_id", "nonce"):
            _id(p[name], name)
        if (p["task_id"] != row["task_id"] or p["movement_id"] != row["movement_id"]
                or p["destination_id"] != row["destination_id"]):
            raise Unauthorized("guarded_destination_proof_binding_mismatch")
        if type(p["owner_epoch"]) is not int or p["owner_epoch"] != row["origin_epoch"] + 1:
            raise Unauthorized("guarded_destination_epoch_mismatch")
        self._proof_window(p, now)
        return p

    def activate(self, signed_ack: Any) -> bool:
        """FENCED -> ACTIVE only on verified, fresh destination readiness.

        The receipt is verified using a pinned destination identity, not the
        caller's destination_id. Identical replay is idempotent but cannot
        revive a revoked, cancelled, expired or otherwise held task.
        """
        wrapped = sealed_parts(signed_ack, "guarded-activation")
        claimed = wrapped["payload"]
        if not isinstance(claimed.get("task_id"), str):
            raise ContractError("missing activation task")
        task_id = _id(claimed["task_id"], "task_id")
        with self.store._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._row(db, task_id)
            if row["status"] not in {"fenced", "active"}:
                raise PolicyDenied("destination not fenced for activation")
            now = self._now()
            grant = self._check(db, row, now)
            owner = db.execute("SELECT agent_id,epoch FROM owners WHERE task_id=?", (task_id,)).fetchone()
            if owner != (row["destination_id"], row["origin_epoch"] + 1):
                raise PolicyDenied("destination ownership changed before activation")
            p = self._destination_proof(
                signed_ack, "guarded-activation", row, now=now, fields=_ACTIVATION_FIELDS,
            )
            if (p["kind"] != row["kind"] or p["scope"] != row["kind"]
                    or p["policy_epoch"] != row["policy_epoch"]
                    or p["grant_digest"] != digest(json.loads(row["grant_json"]))
                    or p["expires_at"] > grant["expires_at"]):
                raise Unauthorized("guarded_activation_authority_mismatch")
            _id(p["activation_id"], "activation_id")
            token_digest = digest(signed_ack)
            existing = db.execute(
                "SELECT activation_id,nonce,receipt_digest,expires_at FROM guarded_activations WHERE task_id=?",
                (task_id,),
            ).fetchone()
            if existing is not None:
                if (row["status"] != "active" or existing !=
                        (p["activation_id"], p["nonce"], token_digest, p["expires_at"])):
                    raise Conflict("activation replay changed identity or payload")
                db.commit()
                return False
            if row["status"] != "fenced":
                raise Conflict("active phase without matching activation")
            try:
                db.execute(
                    "INSERT INTO guarded_activations VALUES(?,?,?,?,?,?,?,?)",
                    (task_id, row["movement_id"], row["destination_id"], p["owner_epoch"],
                     p["activation_id"], p["nonce"], token_digest, p["expires_at"]),
                )
            except sqlite3.IntegrityError as exc:
                raise Conflict("activation ID or nonce already used") from exc
            db.execute("UPDATE guarded_tasks SET status='active' WHERE task_id=?", (task_id,))
            db.commit()
            return True

    def _verify_effect_proof(
        self, token: Any, row: dict[str, Any], effect_id: str,
        content_sha256: str, epoch: int, db: sqlite3.Connection, now: int,
    ) -> None:
        activation = db.execute(
            "SELECT activation_id,destination_id,owner_epoch,expires_at "
            "FROM guarded_activations WHERE task_id=?", (row["task_id"],),
        ).fetchone()
        if activation is None or activation[1] != row["destination_id"] or activation[2] != epoch:
            raise Unauthorized("guarded_activation_missing_or_misbound")
        if now >= activation[3]:
            raise Unauthorized("guarded_activation_expired")
        p = self._destination_proof(
            token, "guarded-effect-invocation", row, now=now, fields=_EFFECT_FIELDS,
        )
        _id(p["effect_id"], "effect_id")
        if (p["activation_id"] != activation[0] or p["owner_epoch"] != epoch
                or p["effect_id"] != effect_id or not isinstance(p["payload_sha256"], str)
                or not hmac.compare_digest(p["payload_sha256"], content_sha256)):
            raise Unauthorized("guarded_effect_invocation_misbound")

    def commit(
        self, task_id: str, movement_id: str, agent_id: str,
        epoch: int, effect_id: str, payload: str, *, signed_execution: Any = None,
    ) -> bool:
        """Atomic receiver-bound simulated effect, with a shared effect budget."""
        for value, label in ((task_id, "task_id"), (movement_id, "movement_id"),
                             (agent_id, "agent_id"), (effect_id, "effect_id")):
            _id(value, label)
        if type(epoch) is not int or epoch < 1:
            raise ContractError("invalid execution epoch")
        if not isinstance(payload, str):
            raise ContractError("synthetic effect payload must be text")
        try:
            encoded = payload.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ContractError("invalid effect payload encoding") from exc
        if len(encoded) > 2048:
            raise ContractError("synthetic effect payload too large")
        content_sha256 = hashlib.sha256(encoded).hexdigest()
        fingerprint = self.store.keyed_digest(content_sha256)
        with self.store._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._row(db, task_id)
            if row["movement_id"] != movement_id or row["status"] != "active":
                raise PolicyDenied("destination not authenticated and activated")
            if agent_id != row["destination_id"]:
                raise PolicyDenied("effect caller is not destination")
            owner = db.execute("SELECT agent_id,epoch FROM owners WHERE task_id=?", (task_id,)).fetchone()
            if owner != (agent_id, epoch):
                raise PolicyDenied("stale or unauthorized effect owner")
            now = self._now()
            self._check(db, row, now)
            self._verify_effect_proof(
                signed_execution, row, effect_id, content_sha256, epoch, db, now,
            )
            prior = db.execute(
                "SELECT payload_digest FROM effects WHERE task_id=? AND effect_id=?", (task_id, effect_id)
            ).fetchone()
            if prior is not None:
                if prior[0] != fingerprint:
                    raise Conflict("effect identifier reused with altered payload")
                db.commit()
                return False
            if row["budget_used"] >= row["budget_limit"]:
                raise PolicyDenied("shared protected effect budget exhausted")
            db.execute(
                "INSERT INTO effects(task_id,effect_id,payload_digest,epoch) VALUES(?,?,?,?)",
                (task_id, effect_id, fingerprint, epoch),
            )
            db.execute("UPDATE guarded_tasks SET budget_used=budget_used+1 WHERE task_id=?", (task_id,))
            db.commit()
            return True

    def _operator_notice(self, sealed: Any, verifier: Any, purpose: str) -> dict[str, Any]:
        p = unseal(purpose, sealed, verifier)
        if set(p) != _NOTICE_FIELDS or p["type"] != purpose:
            raise ContractError("invalid operator notice")
        _id(p["task_id"], "task_id")
        _id(p["movement_id"], "movement_id")
        return p

    def _mark(self, sealed: Any, verifier: Any, purpose: str, column: str) -> None:
        p = self._operator_notice(sealed, verifier, purpose)
        with self.store._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._row(db, p["task_id"])
            if row["movement_id"] != p["movement_id"]:
                raise Unauthorized("operator notice wrong movement")
            if column == "cancelled":
                db.execute("UPDATE guarded_tasks SET cancelled=1 WHERE task_id=?", (p["task_id"],))
            elif column == "unknown_effect":
                db.execute("UPDATE guarded_tasks SET unknown_effect=1 WHERE task_id=?", (p["task_id"],))
            else:
                raise ContractError("unsupported protected state flag")
            db.commit()

    def cancel(self, sealed_notice: Any) -> None:
        """Operator-authenticated irreversible cancellation, atomic with effects."""
        self._mark(sealed_notice, self.cancel_verifier, "guarded-cancel", "cancelled")

    def mark_unknown(self, sealed_notice: Any) -> None:
        """Operator-authenticated conservative hold for an opaque external outcome."""
        self._mark(sealed_notice, self.incident_verifier, "guarded-unknown", "unknown_effect")

    def inspect(self, task_id: str) -> dict[str, Any]:
        """Safe metadata-only inspection; no private task payload or tokens."""
        task_id = _id(task_id, "task_id")
        with self.store._connection() as db:
            r = self._row(db, task_id)
            o = db.execute("SELECT agent_id,epoch FROM owners WHERE task_id=?", (task_id,)).fetchone()
        return {
            "task_id": task_id, "movement_id": r["movement_id"],
            "owner": o[0] if o else None, "epoch": o[1] if o else None,
            "phase": r["status"], "used": r["budget_used"], "limit": r["budget_limit"],
            "cancelled": bool(r["cancelled"]), "unknown_effect": bool(r["unknown_effect"]),
            "activated": r["status"] == "active",
        }
