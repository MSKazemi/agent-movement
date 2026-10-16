"""Synthetic receiver-owned continuity admission and effect-side policy enforcement.

All optional continuity controls are receiver-provisioned. Verified principal approvals,
observations and recipient acknowledgments are signed by separately pinned issuers,
never accepted as caller-set verified booleans. The profile is checked in the SAME
SQLite write transaction as the simulated effect. Not a host sandbox or external PEP.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Mapping
from typing import Any, Literal

from .continuity_guard import (
    ConsentGrant,
    ObservedFacts,
    Observation,
    Policy,
    Proposal,
    _valid_policy,
    evaluate,
    obligation_ack_digest,
)
from .core import ContractError, SQLiteStore, _id, canonical, digest
from .trust import TrustDenied, Unauthorized, unseal

_ADMISSION_STATE = Literal["eligible", "suspect", "quarantined", "unknown"]
_SHA64 = frozenset("0123456789abcdef")
_CONSENT_FIELDS = frozenset(
    {"type", "principal", "destination", "scopes", "policy_epoch", "expires_at", "task_id", "movement_id"}
)
_OBSERVATION_FIELDS = frozenset(
    {"type", "name", "observed_at", "valid_until", "task_id", "movement_id"}
)
_ACK_FIELDS = frozenset(
    {"type", "destination", "kind", "policy_epoch", "ack_digest", "task_id", "movement_id"}
)


def _hex64(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= _SHA64


def _natural(value: object) -> bool:
    return type(value) is int and value >= 0


def _scope_list(value: object) -> frozenset[str]:
    if not isinstance(value, list) or not value or len(value) > 32:
        raise ContractError("invalid continuity scopes")
    scopes: set[str] = set()
    for item in value:
        scopes.add(_id(item, "continuity scope"))
    if len(scopes) != len(value):
        raise ContractError("duplicate continuity scope")
    return frozenset(scopes)


def _profile_digest(policy: Policy) -> str:
    o = policy.required_obligations
    return digest({
        "domain": "agent-movement/continuity-runtime/v1",
        "required_principals": sorted(policy.required_principals),
        "allowed_destinations": sorted(policy.allowed_destinations),
        "allowed_scopes": sorted(policy.allowed_scopes),
        "policy_epoch": policy.policy_epoch,
        "required_obligations": {
            "retain_until": o.retain_until, "allow_onward": o.allow_onward,
            "audit_required": o.audit_required, "notify_user": o.notify_user,
        },
        "approved_manifest_digest": policy.approved_manifest_digest,
        "required_observations": sorted(policy.required_observations),
    })


class ContinuityRuntime:
    """Receiver-side continuity authority for one explicitly opted-in synthetic peer.

    This object is provisioned by the operator with pinned verifier keys, a trusted
    manifest measurer and policy. No HTTP handler exposes its mutation methods.
    Signed consents/observations/acknowledgments bind a specific movement and task.

    The operator and SQLite host are trusted. An attacker with arbitrary code execution
    in the receiver or write access to its SQLite file can bypass this experiment.
    """

    def __init__(
        self,
        store: SQLiteStore,
        recipient_id: str,
        policy: Policy,
        *,
        principal_verifiers: Mapping[str, Any],
        observation_verifiers: Mapping[str, Any],
        recipient_verifier: Any,
        measure_manifest: Callable[[], str],
    ) -> None:
        if not _valid_policy(policy):
            raise ContractError("invalid continuity policy")
        self.recipient_id = _id(recipient_id, "recipient_id")
        if self.recipient_id not in policy.allowed_destinations:
            raise ContractError("continuity destination not allowed")
        if set(principal_verifiers) != set(policy.required_principals):
            raise ContractError("all required principals need independently pinned keys")
        if set(observation_verifiers) != set(policy.required_observations):
            raise ContractError("all required observations need independently pinned keys")
        if len({key.kid for key in principal_verifiers.values()}) != len(principal_verifiers):
            raise ContractError("principals must use distinct issuer key identifiers")
        if not callable(measure_manifest):
            raise ContractError("trusted manifest measurer required")
        self.store = store
        self.policy = policy
        self.profile_digest = _profile_digest(policy)
        self.principal_verifiers = dict(principal_verifiers)
        self.observation_verifiers = dict(observation_verifiers)
        self.recipient_verifier = recipient_verifier
        self.measure_manifest = measure_manifest
        with store._connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS continuity_control(
                    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                    policy_digest TEXT NOT NULL,
                    epoch INTEGER NOT NULL,
                    admission_state TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS continuity_consents(
                    principal TEXT NOT NULL, movement_id TEXT NOT NULL, task_id TEXT NOT NULL,
                    sealed_json TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(principal, movement_id, task_id));
                CREATE TABLE IF NOT EXISTS continuity_observations(
                    name TEXT NOT NULL, movement_id TEXT NOT NULL, task_id TEXT NOT NULL,
                    sealed_json TEXT NOT NULL, PRIMARY KEY(name, movement_id, task_id));
                CREATE TABLE IF NOT EXISTS continuity_acknowledgments(
                    movement_id TEXT NOT NULL, task_id TEXT NOT NULL, kind TEXT NOT NULL,
                    sealed_json TEXT NOT NULL, PRIMARY KEY(movement_id, task_id, kind));
            """)
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR IGNORE INTO continuity_control VALUES(1,?,?,?)",
                       (self.profile_digest, policy.policy_epoch, "unknown"))
            db.commit()

    @staticmethod
    def _verified(purpose: str, token: Any, verifier: Any) -> dict[str, Any]:
        try:
            return unseal(purpose, token, verifier)
        except (ContractError, TrustDenied, ValueError, TypeError) as exc:
            raise Unauthorized("invalid_continuity_signature") from exc

    @staticmethod
    def _ids(payload: dict[str, Any]) -> tuple[str, str]:
        return _id(payload["movement_id"], "movement_id"), _id(payload["task_id"], "task_id")

    def install_consent(self, principal: str, token: Any) -> None:
        """Install one *independently signed*, task- and movement-bound principal consent.

        This method is an operator/provisioning API, not a receiver HTTP endpoint.
        """
        key = self.principal_verifiers.get(principal)
        if key is None:
            raise Unauthorized("untrusted_continuity_principal")
        p = self._verified("continuity-consent", token, key)
        if set(p) != _CONSENT_FIELDS or p["type"] != "continuity-consent" or p["principal"] != principal:
            raise ContractError("invalid continuity consent")
        movement_id, task_id = self._ids(p)
        _id(p["destination"], "destination")
        _scope_list(p["scopes"])
        if not _natural(p["policy_epoch"]) or not _natural(p["expires_at"]):
            raise ContractError("invalid continuity consent time or epoch")
        with self.store._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            # A revoked entry cannot be revived with an old or newly replayed token.
            old = db.execute("SELECT revoked FROM continuity_consents WHERE principal=? AND movement_id=? "
                             "AND task_id=?", (principal, movement_id, task_id)).fetchone()
            if old is not None and old[0]:
                raise Unauthorized("consent_revoked")
            db.execute("INSERT OR REPLACE INTO continuity_consents VALUES(?,?,?,?,0)",
                       (principal, movement_id, task_id, canonical(token)))
            db.commit()

    def apply_consent_revocation(self, principal: str, token: Any) -> None:
        """A separately signed revocation is serialized with simulated effect commits."""
        key = self.principal_verifiers.get(principal)
        if key is None:
            raise Unauthorized("untrusted_continuity_principal")
        p = self._verified("continuity-revocation", token, key)
        if (set(p) != {"type", "principal", "movement_id", "task_id"}
                or p["type"] != "continuity-revocation" or p["principal"] != principal):
            raise ContractError("invalid continuity revocation")
        movement_id, task_id = self._ids(p)
        with self.store._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            # Tombstones also revoke any consent presented after this notice.
            db.execute("INSERT INTO continuity_consents VALUES(?,?,?,?,1) "
                       "ON CONFLICT(principal,movement_id,task_id) DO UPDATE SET revoked=1",
                       (principal, movement_id, task_id, "{}"))
            db.commit()

    def install_observation(self, name: str, token: Any) -> None:
        key = self.observation_verifiers.get(name)
        if key is None:
            raise Unauthorized("untrusted_continuity_sensor")
        p = self._verified("continuity-observation", token, key)
        if set(p) != _OBSERVATION_FIELDS or p["type"] != "continuity-observation" or p["name"] != name:
            raise ContractError("invalid continuity observation")
        movement_id, task_id = self._ids(p)
        if not _natural(p["observed_at"]) or not _natural(p["valid_until"]):
            raise ContractError("invalid continuity observation time")
        with self.store._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR REPLACE INTO continuity_observations VALUES(?,?,?,?)",
                       (name, movement_id, task_id, canonical(token)))
            db.commit()

    def _proposal(self, kind: str, epoch: int) -> Proposal:
        return Proposal(
            destination=self.recipient_id,
            scopes=frozenset({_id(kind, "task kind")}),
            policy_epoch=epoch,
            manifest_digest=self.policy.approved_manifest_digest,
            obligations=self.policy.required_obligations,
        )

    def install_recipient_ack(self, movement_id: str, task_id: str, kind: str, token: Any) -> None:
        movement_id, task_id = _id(movement_id, "movement_id"), _id(task_id, "task_id")
        p = self._verified("continuity-ack", token, self.recipient_verifier)
        if (set(p) != _ACK_FIELDS or p["type"] != "continuity-ack"
                or p["destination"] != self.recipient_id or p["movement_id"] != movement_id
                or p["task_id"] != task_id or p["kind"] != kind
                or p["policy_epoch"] != self.policy.policy_epoch
                or p["ack_digest"] != obligation_ack_digest(self._proposal(kind, self.policy.policy_epoch))):
            raise Unauthorized("invalid_continuity_acknowledgment")
        with self.store._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR REPLACE INTO continuity_acknowledgments VALUES(?,?,?,?)",
                       (movement_id, task_id, kind, canonical(token)))
            db.commit()

    def set_admission_state(self, state: _ADMISSION_STATE) -> None:
        """Receiver operator's local-only state; never derived from a peer request."""
        if state not in ("eligible", "suspect", "quarantined", "unknown"):
            raise ContractError("invalid admission state")
        with self.store._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE continuity_control SET admission_state=? WHERE singleton=1", (state,))
            db.commit()

    def advance_epoch(self, epoch: int) -> None:
        """Operator-only monotonically advancing policy fence; old profiles fail closed."""
        if not _natural(epoch):
            raise ContractError("invalid new epoch")
        with self.store._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT epoch FROM continuity_control WHERE singleton=1").fetchone()
            if old is None or epoch <= old[0]:
                raise ContractError("continuity epoch must advance")
            db.execute("UPDATE continuity_control SET epoch=? WHERE singleton=1", (epoch,))
            db.commit()

    def _load_facts(
        self, db: sqlite3.Connection, proposal: Proposal, movement_id: str, task_id: str,
        kind: str, admission_state: _ADMISSION_STATE,
    ) -> ObservedFacts:
        grants: list[ConsentGrant] = []
        for principal, encoded, revoked in db.execute(
            "SELECT principal,sealed_json,revoked FROM continuity_consents "
            "WHERE movement_id=? AND task_id=?", (movement_id, task_id)
        ):
            key = self.principal_verifiers.get(principal)
            if key is None or revoked:
                continue
            p = self._verified("continuity-consent", json.loads(encoded), key)
            if (set(p) != _CONSENT_FIELDS or p["principal"] != principal
                    or p["movement_id"] != movement_id or p["task_id"] != task_id):
                raise Unauthorized("invalid_continuity_consent_binding")
            grants.append(ConsentGrant(
                principal=principal, destination=p["destination"], scopes=_scope_list(p["scopes"]),
                policy_epoch=p["policy_epoch"], expires_at=p["expires_at"], verified=True,
            ))

        observations: list[Observation] = []
        for name, encoded in db.execute(
            "SELECT name,sealed_json FROM continuity_observations WHERE movement_id=? AND task_id=?",
            (movement_id, task_id)
        ):
            key = self.observation_verifiers.get(name)
            if key is None:
                continue
            p = self._verified("continuity-observation", json.loads(encoded), key)
            if (set(p) != _OBSERVATION_FIELDS or p["name"] != name
                    or p["movement_id"] != movement_id or p["task_id"] != task_id):
                raise Unauthorized("invalid_continuity_observation_binding")
            observations.append(Observation(
                name=name, observed_at=p["observed_at"], valid_until=p["valid_until"], verified=True,
            ))

        ack_row = db.execute(
            "SELECT sealed_json FROM continuity_acknowledgments WHERE movement_id=? AND task_id=? AND kind=?",
            (movement_id, task_id, kind)
        ).fetchone()
        ack_digest = "0" * 64
        if ack_row is not None:
            a = self._verified("continuity-ack", json.loads(ack_row[0]), self.recipient_verifier)
            if (set(a) != _ACK_FIELDS or a["movement_id"] != movement_id or a["task_id"] != task_id
                    or a["kind"] != kind or a["destination"] != self.recipient_id
                    or a["policy_epoch"] != proposal.policy_epoch):
                raise Unauthorized("invalid_continuity_acknowledgment")
            ack_digest = a["ack_digest"]
        try:
            manifest = self.measure_manifest()
        except Exception as exc:
            raise Unauthorized("manifest_measurement_unavailable") from exc
        if not _hex64(manifest):
            raise Unauthorized("invalid_manifest_measurement")
        return ObservedFacts(
            grants=tuple(grants), recipient_ack_digest=ack_digest,
            measured_manifest_digest=manifest, admission_state=admission_state,
            observations=tuple(observations),
        )

    def require(
        self, db: sqlite3.Connection, *, kind: str, movement_id: str, task_id: str,
        now: int, policy_epoch: int | None = None,
    ) -> int:
        """Fail closed inside a caller-owned BEGIN IMMEDIATE transaction.

        For every simulated side effect, the caller must serialize this decision
        with its actual insertion on the same SQLite connection.
        """
        if not db.in_transaction:
            raise RuntimeError("continuity enforcement requires an active SQLite write transaction")
        movement_id, task_id = _id(movement_id, "movement_id"), _id(task_id, "task_id")
        row = db.execute(
            "SELECT policy_digest,epoch,admission_state FROM continuity_control WHERE singleton=1"
        ).fetchone()
        if row is None or row[0] != self.profile_digest:
            raise Unauthorized("continuity_profile_unavailable")
        epoch = row[1] if policy_epoch is None else policy_epoch
        proposal = self._proposal(kind, epoch)
        facts = self._load_facts(db, proposal, movement_id, task_id, kind, row[2])
        decision = evaluate(proposal, self.policy, facts, now=now)
        if epoch != row[1]:
            raise Unauthorized("continuity_epoch_changed")
        if not decision.allowed:
            raise Unauthorized("continuity_" + decision.reasons[0])
        return epoch

    def require_effect(
        self, db: sqlite3.Connection, *, grant: dict[str, Any], agent_id: str,
        task_id: str, effect_id: str, movement_id: str | None, now: int,
    ) -> None:
        """Only an admitted, grant-bound result effect can use the guarded gateway."""
        if movement_id is None or effect_id != f"{movement_id}.result" or agent_id != self.recipient_id:
            raise Unauthorized("continuity_invalid_effect_route")
        row = db.execute("SELECT record_json FROM peer_admissions WHERE movement_id=?", (movement_id,)).fetchone()
        if row is None:
            raise Unauthorized("continuity_unadmitted_effect")
        record: dict[str, Any] = json.loads(row[0])
        if (record.get("logical_task_id") != task_id
                or record.get("grant", {}).get("payload", {}).get("grant_id") != grant["grant_id"]
                or record.get("continuity_profile_digest") != self.profile_digest):
            raise Unauthorized("continuity_effect_binding_mismatch")
        epoch = record.get("continuity_policy_epoch")
        if type(epoch) is not int:
            raise Unauthorized("continuity_missing_epoch")
        self.require(db, kind=record["kind"], movement_id=movement_id, task_id=task_id,
                     policy_epoch=epoch, now=now)
