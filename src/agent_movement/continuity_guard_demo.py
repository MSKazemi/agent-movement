"""Reproducible, stdlib-only synthetic demonstrations of continuity admission.

Run: python -m agent_movement.continuity_guard_demo
No external calls, real data, keys, remote agents or actual tool effects.
"""

from __future__ import annotations

import json
from dataclasses import replace

from .continuity_guard import (
    ConsentGrant,
    Obligations,
    Observation,
    ObservedFacts,
    Policy,
    Proposal,
    evaluate,
    obligation_ack_digest,
)

_NOW = 1_750_000_000
_MANIFEST = "a" * 64


def cases() -> list[tuple[str, bool, Proposal, Policy, ObservedFacts, int]]:
    """Frozen, small illustrative oracle; not a statistical benchmark."""
    obligations = Obligations(retain_until=_NOW + 100, allow_onward=False,
                              audit_required=True, notify_user=True)
    proposal = Proposal(destination="receiver", scopes=frozenset({"synthetic_read"}),
                        policy_epoch=2, manifest_digest=_MANIFEST, obligations=obligations)
    policy = Policy(required_principals=frozenset({"requester", "data_owner"}),
                    allowed_destinations=frozenset({"receiver"}),
                    allowed_scopes=frozenset({"synthetic_read"}),
                    policy_epoch=2, required_obligations=obligations,
                    approved_manifest_digest=_MANIFEST,
                    required_observations=frozenset({"dataset_epoch"}))
    grants = tuple(ConsentGrant(principal=x, destination="receiver",
                                scopes=frozenset({"synthetic_read"}), policy_epoch=2,
                                expires_at=_NOW + 60, verified=True)
                   for x in ("requester", "data_owner"))
    facts = ObservedFacts(grants=grants,
                          recipient_ack_digest=obligation_ack_digest(proposal),
                          measured_manifest_digest=_MANIFEST, admission_state="eligible",
                          observations=(Observation("dataset_epoch", _NOW - 5, _NOW + 30, True),))
    changed_obligation = replace(proposal, obligations=replace(obligations, allow_onward=True))
    return [
        ("all_required_approvals", True, proposal, policy, facts, _NOW),
        ("one_owner_missing", False, proposal, policy, replace(facts, grants=grants[:1]), _NOW),
        ("one_owner_revoked", False, proposal, policy,
         replace(facts, grants=(grants[0], replace(grants[1], revoked=True))), _NOW),
        ("obligation_weakened", False, changed_obligation, policy,
         replace(facts, recipient_ack_digest=obligation_ack_digest(changed_obligation)), _NOW),
        ("configuration_changed", False, proposal, policy,
         replace(facts, measured_manifest_digest="b" * 64), _NOW),
        ("recipient_ack_missing", False, proposal, policy,
         replace(facts, recipient_ack_digest="0" * 64), _NOW),
        ("checkpoint_suspect", False, proposal, policy,
         replace(facts, admission_state="suspect"), _NOW),
        ("sensor_fact_stale", False, proposal, policy, facts, _NOW + 31),
        ("retention_expired", False, proposal, policy, facts, _NOW + 100),
        ("unauthorized_destination", False, replace(proposal, destination="untrusted"),
         policy, facts, _NOW),
    ]


def run() -> dict[str, object]:
    results: list[dict[str, object]] = []
    matched = 0
    for case_id, expected_allowed, proposal, policy, facts, now in cases():
        decision = evaluate(proposal, policy, facts, now=now)
        matched += int(decision.allowed == expected_allowed)
        results.append({"case": case_id, "expected_allowed": expected_allowed,
                        "allowed": decision.allowed, "reasons": list(decision.reasons),
                        "matched_oracle": decision.allowed == expected_allowed})
    return {
        "schema_version": "continuity-guard-demo/0.1",
        "scope": "deterministic_synthetic_decisions_only",
        "not_claimed": "runtime_enforcement_or_real_world_security",
        "cases": len(results),
        "matched": matched,
        "unexpected": len(results) - matched,
        "results": results,
    }


def main() -> int:
    report = run()
    print(json.dumps(report, sort_keys=True, indent=2))
    return int(report["unexpected"] != 0)


if __name__ == "__main__":
    raise SystemExit(main())
