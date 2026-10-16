"""Opt-in authenticated activation + protected synthetic effect protocol.

A descendant of GuardedAuthority using one authoritative SQLite transaction per
fence, activation and synthetic effect. The base commit route rejects activated
tasks even when constructed with another GuardedAuthority instance. A signed
destination proof is NOT proof of OS process liveness, hardware identity, or
semantic continuation. The operator must protect destination signing keys.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from collections.abc import Callable, Mapping
from typing import Any

from .continuity_runtime import ContinuityRuntime
from .core import Conflict, ContractError, PolicyDenied, SQLiteStore, _id, digest
from .guarded_authority import GuardedAuthority
from .trust import TrustStore, Unauthorized, unseal

_ACTIVATION_FIELDS = frozenset({
    "type", "task_id", "movement_id", "destination_id", "epoch",
    "policy_epoch", "grant_digest", "activation_id", "expires_at",
})
_EFFECT_FIELDS = frozenset({
    "type", "task_id", "movement_id", "destination_id", "epoch",
    "policy_epoch", "activation_id", "effect_id", "payload_sha256", "expires_at",
})


class ActivatedGuardedAuthority(GuardedAuthority):
    """Protected opt-in profile. Requires destination signatures on BOTH steps."""

    def __init__(
        self, store: SQLiteStore, continuity: ContinuityRuntime, trust: TrustStore, *,
        origin_verifiers: Mapping[str, Any], cancel_verifier: Any,
        incident_verifier: Any, budget_limit: int = 2,
        clock: Callable[[], float] = time.time,
    ) -> None:
        verifier = continuity.recipient_verifier
        if not hasattr(verifier, "verify") or not hasattr(verifier, "kid"):
            raise ContractError("pinned destination signature verifier required")
        super().__init__(
            store, continuity, trust,
            origin_verifiers=origin_verifiers, cancel_verifier=cancel_verifier,
            incident_verifier=incident_verifier, budget_limit=budget_limit,
            clock=clock, require_activation=True,
        )
        self.destination_verifier = verifier

    def _signed(self, purpose: str, signed: Any, fields: frozenset[str]) -> dict[str, Any]:
        """No request-provided key, verified booleans or trusted principal IDs."""
        payload = unseal(purpose, signed, self.destination_verifier)
        if set(payload) != fields or payload.get("type") != purpose:
            raise ContractError("invalid signed destination instruction")
        for name in ("task_id", "movement_id", "destination_id"):
            _id(payload[name], name)
        if type(payload["epoch"]) is not int or payload["epoch"] < 2:
            raise ContractError("invalid transferred execution epoch")
        if type(payload["policy_epoch"]) is not int or payload["policy_epoch"] < 1:
            raise ContractError("invalid signed policy epoch")
        if type(payload["expires_at"]) is not int or payload["expires_at"] < 1:
            raise ContractError("invalid signed expiry")
        if "activation_id" in payload:
            _id(payload["activation_id"], "activation_id")
        if purpose == "guarded-activation":
            if not isinstance(payload["grant_digest"], str) or len(payload["grant_digest"]) != 64:
                raise ContractError("invalid signed grant digest")
        else:
            _id(payload["effect_id"], "effect_id")
            if not isinstance(payload["payload_sha256"], str) or len(payload["payload_sha256"]) != 64:
                raise ContractError("invalid payload digest")
        return payload

    @staticmethod
    def _txn_owner(db: sqlite3.Connection, task_id: str) -> tuple[str, int] | None:
        owner = db.execute(
            "SELECT agent_id,epoch FROM owners WHERE task_id=?", (task_id,)
        ).fetchone()
        return (str(owner[0]), int(owner[1])) if owner else None

    def activate(self, signed_ack: Any) -> bool:
        """FENCED -> ACTIVE. Returns False only for identical authorized replay."""
        p = self._signed("guarded-activation", signed_ack, _ACTIVATION_FIELDS)
        with self.store._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._row(db, p["task_id"])
            if row["status"] not in ("fenced", "active"):
                raise PolicyDenied("task has not been fenced for activation")
            now = self._now()
            self._check(db, row, now)
            if (
                p["task_id"] != row["task_id"] or p["movement_id"] != row["movement_id"]
                or p["destination_id"] != row["destination_id"]
                or p["policy_epoch"] != row["policy_epoch"]
            ):
                raise Unauthorized("signed_activation_scope_mismatch")
            if p["grant_digest"] != digest(json.loads(row["grant_json"])):
                raise Unauthorized("signed_activation_grant_mismatch")
            if now >= p["expires_at"]:
                raise Unauthorized("signed_activation_expired")
            if self._txn_owner(db, p["task_id"]) != (row["destination_id"], p["epoch"]):
                raise Unauthorized("signed_activation_stale_epoch")
            prior = db.execute(
                "SELECT activation_id,activation_digest,epoch FROM guarded_activations WHERE task_id=?",
                (p["task_id"],),
            ).fetchone()
            if prior is None:
                raise PolicyDenied("task was not enrolled as activation-required")
            signed_digest = digest(signed_ack)
            if row["status"] == "active":
                if prior == (p["activation_id"], signed_digest, p["epoch"]):
                    db.commit()
                    return False
                raise Conflict("activation already established with different proof")
            if prior[0] is not None:
                raise Conflict("activation state inconsistent")
            updated = db.execute(
                "UPDATE guarded_activations SET activation_id=?,activation_digest=?,epoch=? "
                "WHERE task_id=? AND activation_id IS NULL",
                (p["activation_id"], signed_digest, p["epoch"], p["task_id"]),
            )
            if updated.rowcount != 1:
                raise Conflict("concurrent activation")
            db.execute(
                "UPDATE guarded_tasks SET status='active' WHERE task_id=? AND status='fenced'",
                (p["task_id"],),
            )
            db.commit()
            return True

    def commit_signed(self, signed_instruction: Any, payload: str) -> bool:
        """Target-side authenticated, fenced, budget-limited SYNTHETIC effect."""
        p = self._signed("guarded-effect-intent", signed_instruction, _EFFECT_FIELDS)
        if not isinstance(payload, str):
            raise ContractError("synthetic effect payload must be text")
        try:
            encoded = payload.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ContractError("invalid synthetic effect UTF-8") from exc
        if len(encoded) > 2048:
            raise ContractError("synthetic effect exceeds 2048 bytes")
        plain_digest = hashlib.sha256(encoded).hexdigest()
        if p["payload_sha256"] != plain_digest:
            raise Unauthorized("signed_effect_payload_mismatch")
        keyed_digest = self.store.keyed_digest(plain_digest)
        with self.store._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._row(db, p["task_id"])
            if row["status"] != "active":
                raise PolicyDenied("destination has not authenticated activation")
            now = self._now()
            self._check(db, row, now)
            if (
                p["movement_id"] != row["movement_id"]
                or p["destination_id"] != row["destination_id"]
                or p["policy_epoch"] != row["policy_epoch"]
            ):
                raise Unauthorized("signed_effect_wrong_scope_or_policy")
            if now >= p["expires_at"]:
                raise Unauthorized("signed_effect_expired")
            if self._txn_owner(db, p["task_id"]) != (row["destination_id"], p["epoch"]):
                raise Unauthorized("signed_effect_stale_executor_epoch")
            act = db.execute(
                "SELECT activation_id,epoch FROM guarded_activations WHERE task_id=?", (p["task_id"],)
            ).fetchone()
            if act != (p["activation_id"], p["epoch"]):
                raise Unauthorized("signed_effect_wrong_activation")
            prior = db.execute(
                "SELECT payload_digest FROM effects WHERE task_id=? AND effect_id=?",
                (p["task_id"], p["effect_id"]),
            ).fetchone()
            if prior is not None:
                if prior[0] != keyed_digest:
                    raise Conflict("stable effect ID reused with altered payload")
                db.commit()
                return False
            if row["budget_used"] >= row["budget_limit"]:
                raise PolicyDenied("shared protected effect budget exhausted")
            db.execute(
                "INSERT INTO effects(task_id,effect_id,payload_digest,epoch) VALUES(?,?,?,?)",
                (p["task_id"], p["effect_id"], keyed_digest, p["epoch"]),
            )
            db.execute(
                "UPDATE guarded_tasks SET budget_used=budget_used+1 WHERE task_id=?", (p["task_id"],)
            )
            db.commit()
            return True
