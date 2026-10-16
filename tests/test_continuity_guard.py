"""Synthetic no-credential conformance checks for continuity_guard.

These tests validate a pure decision function, not actual PEP integration.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from agent_movement.continuity_guard import (
    ConsentGrant,
    Obligations,
    Observation,
    ObservedFacts,
    Policy,
    Proposal,
    evaluate,
    obligation_ack_digest,
    approval_preview,
)

TIME = 1_750_000_000
MANIFEST = "1" * 64
ALT_MANIFEST = "2" * 64
REQUIRED = Obligations(retain_until=TIME + 3600, allow_onward=False,
                       audit_required=True, notify_user=True)
PRINCIPALS = frozenset({"task_owner", "data_owner", "device_owner"})


def valid_case():
    proposal = Proposal(destination="worker_b", scopes=frozenset({"summarize"}),
                        policy_epoch=7, manifest_digest=MANIFEST, obligations=REQUIRED)
    policy = Policy(required_principals=PRINCIPALS,
                    allowed_destinations=frozenset({"worker_b"}),
                    allowed_scopes=frozenset({"summarize", "read_synthetic"}),
                    policy_epoch=7, required_obligations=REQUIRED,
                    approved_manifest_digest=MANIFEST,
                    required_observations=frozenset({"data_version", "tool_status"}))
    grants = tuple(ConsentGrant(principal=x, destination="worker_b",
                                scopes=frozenset({"summarize", "read_synthetic"}),
                                policy_epoch=7, expires_at=TIME + 900, verified=True)
                   for x in sorted(PRINCIPALS))
    facts = ObservedFacts(grants=grants, recipient_ack_digest=obligation_ack_digest(proposal),
                          measured_manifest_digest=MANIFEST, admission_state="eligible",
                          observations=(Observation("data_version", TIME - 10, TIME + 60, True),
                                        Observation("tool_status", TIME - 30, TIME + 20, True)))
    return proposal, policy, facts


def denied(reason, proposal=None, policy=None, facts=None, *, now=TIME):
    p, pol, f = valid_case()
    d = evaluate(proposal or p, policy or pol, facts or f, now=now)
    assert d.allowed is False
    assert reason in d.reasons


def test_all_three_principals_and_ack_pass():
    assert evaluate(*valid_case(), now=TIME).allowed is True


def test_decision_contains_no_task_or_sensitive_context():
    d = evaluate(*valid_case(), now=TIME)
    assert d.reasons == ()
    assert not hasattr(d, "context")


def test_missing_data_owner_denied():
    p, pol, f = valid_case()
    denied("principal_missing", facts=replace(f, grants=f.grants[:1] + f.grants[2:]))


def test_explicit_denial_overrides_other_grants():
    _, _, f = valid_case()
    g = replace(f.grants[0], revoked=True)
    denied("principal_denied", facts=replace(f, grants=(g,) + f.grants[1:]))


@pytest.mark.parametrize("change", [
    {"verified": False}, {"expires_at": TIME}, {"policy_epoch": 6},
    {"destination": "worker_c"}, {"scopes": frozenset({"read_synthetic"})},
])
def test_invalid_grant_not_accepted(change):
    _, _, f = valid_case()
    denied("principal_denied", facts=replace(f, grants=(replace(f.grants[0], **change),) + f.grants[1:]))


def test_duplicate_grant_refused_even_when_last_one_is_valid():
    _, _, f = valid_case()
    denied("ambiguous_grants", facts=replace(f, grants=(replace(f.grants[0], revoked=True),) + f.grants))


@pytest.mark.parametrize("change,reason", [
    ({"destination": "worker_c"}, "destination_denied"),
    ({"policy_epoch": 6}, "epoch_stale"),
    ({"scopes": frozenset({"summarize", "external_delete"})}, "scope_denied"),
    ({"manifest_digest": ALT_MANIFEST}, "configuration_drift"),
])
def test_unauthorized_proposal(change, reason):
    p, _, _ = valid_case()
    denied(reason, proposal=replace(p, **change))


@pytest.mark.parametrize("change", [
    {"retain_until": TIME + 3601}, {"allow_onward": True},
    {"audit_required": False}, {"notify_user": False},
])
def test_obligation_weakened(change):
    p, _, _ = valid_case()
    denied("obligations_relaxed", proposal=replace(p, obligations=replace(p.obligations, **change)))


def test_stricter_obligation_requires_new_ack():
    p, pol, f = valid_case()
    tighter = replace(p, obligations=replace(p.obligations, retain_until=TIME + 5))
    d = evaluate(tighter, pol, f, now=TIME)
    assert d.reasons == ("obligations_unacknowledged",)
    ok = replace(f, recipient_ack_digest=obligation_ack_digest(tighter))
    assert evaluate(tighter, pol, ok, now=TIME).allowed


def test_ack_cannot_replay_for_different_manifest_or_epoch():
    p, pol, f = valid_case()
    changed = replace(p, policy_epoch=8)
    assert obligation_ack_digest(changed) != f.recipient_ack_digest
    changed = replace(p, manifest_digest=ALT_MANIFEST)
    assert obligation_ack_digest(changed) != f.recipient_ack_digest


def test_configuration_change_measured_out_of_band():
    _, _, f = valid_case()
    denied("configuration_drift", facts=replace(f, measured_manifest_digest=ALT_MANIFEST))


@pytest.mark.parametrize("state", ["suspect", "quarantined", "unknown"])
def test_quarantine_or_unknown_refuses(state):
    _, _, f = valid_case()
    denied("state_not_cleared", facts=replace(f, admission_state=state))


@pytest.mark.parametrize("obs_change", [
    {"verified": False}, {"observed_at": TIME + 1},
    {"valid_until": TIME}, {"valid_until": TIME - 11},
])
def test_missing_valid_sensor_freshness(obs_change):
    _, _, f = valid_case()
    changed = replace(f.observations[0], **obs_change)
    denied("evidence_stale", facts=replace(f, observations=(changed,) + f.observations[1:]))


def test_missing_observation():
    _, _, f = valid_case()
    denied("evidence_missing", facts=replace(f, observations=f.observations[:1]))


def test_repeated_observation_refused():
    _, _, f = valid_case()
    denied("ambiguous_observations", facts=replace(f, observations=f.observations + (f.observations[0],)))


def test_deferred_effect_must_recheck_against_new_time_and_revocation():
    p, pol, f = valid_case()
    assert evaluate(p, pol, f, now=TIME).allowed
    assert "evidence_stale" in evaluate(p, pol, f, now=TIME + 100).reasons
    updated = replace(f, grants=(replace(f.grants[0], revoked=True),) + f.grants[1:])
    assert "principal_denied" in evaluate(p, pol, updated, now=TIME + 1).reasons


@pytest.mark.parametrize("change", [
    {"policy_epoch": True}, {"scopes": frozenset()},
    {"manifest_digest": "not-a-digest"}, {"destination": ""},
    {"obligations": replace(REQUIRED, notify_user=1)},
])
def test_malformed_proposal_fails_closed(change):
    p, pol, f = valid_case()
    assert evaluate(replace(p, **change), pol, f, now=TIME).reasons == ("invalid_inputs",)


def test_missing_mandatory_principal_policy_fails_closed():
    p, pol, f = valid_case()
    assert evaluate(p, replace(pol, required_principals=frozenset()), f, now=TIME).reasons == ("invalid_inputs",)


def test_bad_clock_fails_closed():
    p, pol, f = valid_case()
    assert evaluate(p, pol, f, now=True).reasons == ("invalid_inputs",)


def test_unverified_recipient_ack_mismatch_refuses():
    _, _, f = valid_case()
    denied("obligations_unacknowledged", facts=replace(f, recipient_ack_digest="0" * 64))


def test_malformed_verified_facts_denied():
    p, pol, f = valid_case()
    bad = replace(f, grants=(replace(f.grants[0], expires_at=-5),) + f.grants[1:])
    assert evaluate(p, pol, bad, now=TIME).reasons == ("invalid_inputs",)


def test_extra_consents_cannot_replace_required_one():
    _, _, f = valid_case()
    unrelated = ConsentGrant("unrelated_admin", "worker_b", frozenset({"summarize"}),
                             7, TIME + 500, True)
    denied("principal_missing", facts=replace(f, grants=f.grants[:1] + f.grants[2:] + (unrelated,)))


def test_obligations_ack_binds_requested_scopes():
    p, _, f = valid_case()
    assert obligation_ack_digest(replace(p, scopes=frozenset({"read_synthetic"}))) != f.recipient_ack_digest


def test_policy_scope_intersection_not_grant_union():
    p, _, f = valid_case()
    enlarged = replace(p, scopes=frozenset({"summarize", "read_synthetic"}))
    facts = replace(f, grants=(replace(f.grants[0], scopes=frozenset({"summarize"})),) + f.grants[1:],
                    recipient_ack_digest=obligation_ack_digest(enlarged))
    denied("principal_denied", proposal=enlarged, facts=facts)


def test_expired_data_retention_blocks_new_movement():
    p, pol, f = valid_case()
    too_late = TIME + 3600
    assert "retention_expired" in evaluate(p, pol, f, now=too_late).reasons


def test_approval_preview_has_required_approvers_and_no_fake_consent():
    p, pol, _ = valid_case()
    preview = approval_preview(p, pol)
    assert preview["mandatory_approvers"] == sorted(PRINCIPALS)
    assert preview["status"] == "preview_only_not_authorized"
    assert "does not undo" in preview["warning"]
    assert "grant" not in preview


def test_preview_fails_closed_on_invalid_policy():
    p, pol, _ = valid_case()
    with pytest.raises(ValueError, match="invalid proposal"):
        approval_preview(p, replace(pol, required_principals=frozenset()))


def test_deterministic_example_oracle():
    from agent_movement.continuity_guard_demo import run

    report = run()
    assert report["cases"] == 10
    assert report["matched"] == 10
    assert report["unexpected"] == 0
    assert sum(int(row["allowed"]) for row in report["results"]) == 1
