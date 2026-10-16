"""Bounded runtime-enforcement test matrix. Synthetic keys, tasks and effects only."""

from __future__ import annotations

import json

import pytest

from agent_movement.continuity_guard import Obligations, Policy, Proposal, obligation_ack_digest
from agent_movement.continuity_runtime import ContinuityRuntime
from agent_movement.core import ContractError, SQLiteStore
from agent_movement.peer import (
    DELIVERY_PATH,
    HandoffAborted,
    InProcessTransport,
    PeerClient,
    PeerReceiver,
    RecordingTransport,
)
from agent_movement.trust import (
    HS256,
    TrustStore,
    Unauthorized,
    generate_key,
    issue_card,
    issue_grant,
    seal,
    verify_grant,
)

NOW = 1_800_000_000
DEST = "local://agent-b"
TEXT = "synthetic task SECRET-CANARY-fake-987"


class Rig:
    def __init__(self, path):
        self.now = NOW
        self.manifest = "a" * 64
        self.ca = generate_key(HS256, "ca")
        self.user = generate_key(HS256, "user")
        self.origin_key = generate_key(HS256, "a")
        self.dest_key = generate_key(HS256, "b")
        self.human = generate_key(HS256, "human-consent")
        self.owner = generate_key(HS256, "data-owner-consent")
        self.sensor = generate_key(HS256, "source-sensor")
        self.untrusted = generate_key(HS256, "data-owner-consent")
        self.trust = TrustStore.build([self.ca], [self.user], [self.origin_key, self.dest_key])
        self.card_a = issue_card(
            self.ca, agent_id="agent-a", endpoint_url="local://agent-a",
            capabilities=["word_count"], agent_key=self.origin_key,
            not_before=NOW - 10, expires_at=NOW + 3600,
        )
        self.card_b = issue_card(
            self.ca, agent_id="agent-b", endpoint_url=DEST,
            capabilities=["word_count"], agent_key=self.dest_key,
            not_before=NOW - 10, expires_at=NOW + 3600,
        )
        self.store = SQLiteStore(path / "receiver.sqlite")
        self.policy = Policy(
            required_principals=frozenset({"human", "data-owner"}),
            allowed_destinations=frozenset({"agent-b"}),
            allowed_scopes=frozenset({"word_count"}),
            policy_epoch=4,
            required_obligations=Obligations(
                retain_until=NOW + 2000, allow_onward=False,
                audit_required=True, notify_user=False,
            ),
            approved_manifest_digest="a" * 64,
            required_observations=frozenset({"sensor"}),
        )
        self.runtime = ContinuityRuntime(
            self.store, "agent-b", self.policy,
            principal_verifiers={"human": self.human, "data-owner": self.owner},
            observation_verifiers={"sensor": self.sensor},
            recipient_verifier=self.dest_key,
            measure_manifest=lambda: self.manifest,
        )
        self.receiver = PeerReceiver(
            self.card_b, self.dest_key, self.trust, self.store,
            ["word_count"], clock=self.clock, continuity=self.runtime,
            secure_test_mode=True,
        )
        self.wire = RecordingTransport(InProcessTransport({DEST: self.receiver}))
        self.client = PeerClient(
            self.card_a, self.origin_key, self.trust, self.wire,
            clock=self.clock,
        )
        self.grant = issue_grant(
            self.user, grant_id="grant-1", subject="synthetic-user",
            actor="agent-a", audience="agent-b", task_id="task-1",
            capabilities=["word_count"], not_before=NOW - 10, expires_at=NOW + 1200,
        )

    def clock(self):
        return self.now

    def consent(self, principal, *, movement="movement-1", task="task-1",
                destination="agent-b", scopes=None, expires=None, signer=None):
        payload = {
            "type": "continuity-consent", "principal": principal,
            "destination": destination, "task_id": task, "movement_id": movement,
            "scopes": ["word_count"] if scopes is None else scopes,
            "policy_epoch": self.policy.policy_epoch,
            "expires_at": NOW + 1200 if expires is None else expires,
        }
        key = self.human if principal == "human" else self.owner
        return seal("continuity-consent", payload, signer or key)

    def install(self, *, human=True, owner=True, sensor=True, ack=True, state=True):
        if human:
            self.runtime.install_consent("human", self.consent("human"))
        if owner:
            self.runtime.install_consent("data-owner", self.consent("data-owner"))
        if sensor:
            self.runtime.install_observation("sensor", self.observation())
        if ack:
            self.runtime.install_recipient_ack("movement-1", "task-1", "word_count", self.acknowledgment())
        if state:
            self.runtime.set_admission_state("eligible")

    def observation(self, *, observed=None, valid_until=None):
        return seal("continuity-observation", {
            "type": "continuity-observation", "name": "sensor",
            "task_id": "task-1", "movement_id": "movement-1",
            "observed_at": NOW - 10 if observed is None else observed,
            "valid_until": NOW + 300 if valid_until is None else valid_until,
        }, self.sensor)

    def acknowledgment(self):
        p = Proposal(
            "agent-b", frozenset({"word_count"}), self.policy.policy_epoch,
            self.policy.approved_manifest_digest, self.policy.required_obligations,
        )
        return seal("continuity-ack", {
            "type": "continuity-ack", "destination": "agent-b",
            "kind": "word_count", "task_id": "task-1", "movement_id": "movement-1",
            "policy_epoch": self.policy.policy_epoch,
            "ack_digest": obligation_ack_digest(p),
        }, self.dest_key)

    def revoke(self, principal="data-owner"):
        key = self.owner if principal == "data-owner" else self.human
        token = seal("continuity-revocation", {
            "type": "continuity-revocation", "principal": principal,
            "task_id": "task-1", "movement_id": "movement-1",
        }, key)
        self.runtime.apply_consent_revocation(principal, token)

    def handoff(self):
        return self.client.handoff(
            url=DEST, destination_id="agent-b", movement_id="movement-1",
            task_id="task-1", kind="word_count", text=TEXT, grant=self.grant,
            idempotency_key="retry-1", trace_id="trace-1",
        )


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


def assert_no_disclosure(rig, *, stage="preflight"):
    with pytest.raises(HandoffAborted) as exc:
        rig.handoff()
    assert exc.value.stage == stage
    assert not exc.value.payload_sent
    assert TEXT.encode() not in rig.wire.transmitted()
    assert rig.receiver.ledger.effects() == []


def test_positive_signed_multi_principal_handoff_and_idempotent_effect(rig):
    rig.install()
    first = rig.handoff()
    assert first["effect"] == "committed"
    second = rig.handoff()
    assert second["effect"] == "replayed"
    assert len(rig.receiver.ledger.effects()) == 1
    assert rig.receiver.ledger.effects()[0]["grant_id"] == "grant-1"


@pytest.mark.parametrize("missing", ["human", "owner", "sensor", "ack", "state"])
def test_missing_required_signed_fact_blocks_before_disclosure(rig, missing):
    fields = {"human": True, "owner": True, "sensor": True, "ack": True, "state": True}
    fields[missing] = False
    rig.install(**fields)
    assert_no_disclosure(rig)


def test_unsigned_or_forged_principal_cannot_install_authority(rig):
    with pytest.raises(Unauthorized):
        rig.runtime.install_consent(
            "data-owner", rig.consent("data-owner", signer=rig.untrusted),
        )
    rig.install(owner=False)
    assert_no_disclosure(rig)


def test_cross_task_consent_cannot_substitute_for_required_permission(rig):
    rig.install(owner=False)
    rig.runtime.install_consent("data-owner", rig.consent("data-owner", task="task-other"))
    assert_no_disclosure(rig)


def test_consent_wrong_scope_does_not_expand_grant(rig):
    rig.install(owner=False)
    rig.runtime.install_consent("data-owner", rig.consent("data-owner", scopes=["sha256"]))
    assert_no_disclosure(rig)


def test_consent_expired_before_preflight(rig):
    rig.install(owner=False)
    rig.runtime.install_consent("data-owner", rig.consent("data-owner", expires=NOW))
    assert_no_disclosure(rig)


def test_invalid_recipient_acceptance_is_rejected(rig):
    token = rig.acknowledgment()
    token["sig"] = "not-a-signature"
    with pytest.raises(Unauthorized):
        rig.runtime.install_recipient_ack("movement-1", "task-1", "word_count", token)
    rig.install(ack=False)
    assert_no_disclosure(rig)


def test_stale_or_future_observation_fails_before_disclosure(rig):
    rig.install(sensor=False)
    rig.runtime.install_observation("sensor", rig.observation(valid_until=NOW))
    assert_no_disclosure(rig)


def test_measurement_changed_between_provision_and_preflight(rig):
    rig.install()
    rig.manifest = "b" * 64
    assert_no_disclosure(rig)


def test_quarantined_receiver_refuses_preflight(rig):
    rig.install()
    rig.runtime.set_admission_state("quarantined")
    assert_no_disclosure(rig)


def test_policy_epoch_change_blocks_new_preflight(rig):
    rig.install()
    rig.runtime.advance_epoch(rig.policy.policy_epoch + 1)
    assert_no_disclosure(rig)


def test_revocation_after_preflight_but_before_delivery_blocks_effect(rig):
    rig.install()
    transport = rig.client.transport

    class RevokeBeforeDelivery:
        def request(self, method, url, path, body):
            if path == DELIVERY_PATH:
                rig.revoke()
            return transport.request(method, url, path, body)

    rig.client.transport = RevokeBeforeDelivery()
    with pytest.raises(HandoffAborted) as exc:
        rig.handoff()
    assert exc.value.stage == "delivery"
    assert exc.value.payload_sent
    assert rig.receiver.ledger.effects() == []


def test_revocation_at_effect_commit_prevents_simulated_side_effect(rig):
    rig.install()
    rig.receiver.before_effect_commit = lambda _record: rig.revoke()
    with pytest.raises(HandoffAborted) as exc:
        rig.handoff()
    assert exc.value.stage == "delivery"  # task bytes already crossed the wire
    assert rig.receiver.ledger.effects() == []


def test_manifest_change_at_effect_commit_is_rechecked(rig):
    rig.install()
    rig.receiver.before_effect_commit = lambda _record: setattr(rig, "manifest", "b" * 64)
    with pytest.raises(HandoffAborted):
        rig.handoff()
    assert rig.receiver.ledger.effects() == []


def test_policy_epoch_change_at_effect_commit_is_fenced(rig):
    rig.install()
    rig.receiver.before_effect_commit = lambda _record: rig.runtime.advance_epoch(5)
    with pytest.raises(HandoffAborted):
        rig.handoff()
    assert rig.receiver.ledger.effects() == []


def test_expired_observation_at_effect_commit_is_fenced(rig):
    rig.install()
    rig.receiver.before_effect_commit = lambda _record: setattr(rig, "now", NOW + 500)
    with pytest.raises(HandoffAborted):
        rig.handoff()
    assert rig.receiver.ledger.effects() == []


def test_guarded_gateway_rejects_direct_unadmitted_or_wrong_effect_routes(rig):
    rig.install()
    grant = verify_grant(rig.grant, rig.trust)
    with pytest.raises(Unauthorized):
        rig.receiver.effects.commit(grant, "agent-b", "task-1", "movement-1.result", "fake")
    with pytest.raises(Unauthorized):
        rig.receiver.effects.commit(
            grant, "agent-b", "task-1", "wrong-effect", "fake", movement_id="movement-1",
        )
    with pytest.raises(Unauthorized):
        rig.receiver.effects.commit(
            grant, "agent-b", "task-1", "movement-1.result", "fake", movement_id="movement-1",
        )
    assert rig.receiver.ledger.effects() == []


def test_gateway_requires_original_admission_and_grant_binding(rig):
    rig.install()
    rig.handoff()
    other_grant = issue_grant(
        rig.user, grant_id="grant-other", subject="synthetic-user",
        actor="agent-a", audience="agent-b", task_id="task-1",
        capabilities=["word_count"], not_before=NOW - 10, expires_at=NOW + 1200,
    )
    with pytest.raises(Unauthorized):
        rig.receiver.effects.commit(
            verify_grant(other_grant, rig.trust), "agent-b", "task-1",
            "movement-1.result", "fake", movement_id="movement-1",
        )


def test_signed_revocation_cannot_be_forged(rig):
    rig.install()
    fake = seal("continuity-revocation", {
        "type": "continuity-revocation", "principal": "data-owner",
        "task_id": "task-1", "movement_id": "movement-1",
    }, rig.untrusted)
    with pytest.raises(Unauthorized):
        rig.runtime.apply_consent_revocation("data-owner", fake)
    assert rig.handoff()["effect"] == "committed"


def test_revocation_tombstone_blocks_reinstall(rig):
    rig.install()
    rig.revoke()
    with pytest.raises(Unauthorized):
        rig.runtime.install_consent("data-owner", rig.consent("data-owner"))
    assert_no_disclosure(rig)


def test_secure_profile_fails_closed_when_not_provisioned(rig):
    with pytest.raises(ContractError):
        PeerReceiver(
            rig.card_b, rig.dest_key, rig.trust, rig.store, ["word_count"],
            clock=rig.clock, secure_test_mode=True,
        )


def test_secure_profile_unknown_route_and_direct_delivery_denied(rig):
    rig.install()
    assert rig.receiver.handle("POST", "/v0/legacy", b"{}")[0] == 404
    status, body = rig.receiver.handle("POST", DELIVERY_PATH, b"{}")
    assert status in {400, 401, 403}
    assert "receipt" not in json.dumps(body)
    assert rig.receiver.ledger.effects() == []


def test_receiver_evidence_table_tamper_is_not_promoted_to_verified(rig):
    rig.install()
    with rig.store._connection() as db:
        db.execute("UPDATE continuity_consents SET sealed_json='{}' WHERE principal='data-owner'")
    assert_no_disclosure(rig)


def test_profile_digest_mismatch_on_existing_store_fails_closed(rig):
    rig.install()
    with rig.store._connection() as db:
        db.execute("UPDATE continuity_control SET policy_digest='aaaaaaaa' WHERE singleton=1")
    assert_no_disclosure(rig)
