"""Deterministic MASM witness planner for guarded SQLite runtime refinement.

This module DOES NOT verify a runtime, infer missing states, or call an agent.
It extracts shortest executable-prefix witnesses from MASM-0.1 and explicitly
excludes events with no faithful mapping to the opt-in guarded SQLite lane.
The runtime projector and independent SQL oracle are tested separately.
"""
from __future__ import annotations

import argparse
import json
from collections import deque
from collections.abc import Callable
from typing import Any

from movement_authority_machine import State, transitions

# A deliberately *partial* event refinement. Runtime activation is NOT mapped;
# the resume event below is an abstract marker, not verified execution state.
EVENTS = frozenset({
    "prepare_destination",
    "issue_attenuated_grant_B",
    "fence_and_transfer",
    "resume_destination",
    "commit_B_publish-1",
    "commit_B_publish-2",
    "revoke_user",
    "revoke_data_owner",
    "cancel_task",
    "bump_policy_epoch",
    "advance_clock",
    "dispatch_opaque_effect_unknown",
})
ABSTRACT_MARKERS = frozenset({"prepare_destination", "resume_destination"})
UNMAPPED = (
    "origin-side effects (commit_A_*): guarded enrollment forbids early effects",
    "OS crash/restart, gateway partition/reheal: no equivalent fault injection in this runner",
    "operator_claim_done/absent: a claim cannot resolve an actual unknown effect",
    "physical process liveness and authenticated destination activation",
    "external effects, peer/A2A/relocation transports, consensus and independent data stores",
)
Predicate = Callable[[State], bool]


def _targets() -> dict[str, Predicate]:
    """Each predicate is a distinct research case, not a runtime assertion."""
    return {
        "01_prepared_no_grant": lambda s: s.phase == "prepared" and not s.destination_granted,
        "02_enrolled_prepared": lambda s: s.phase == "prepared" and s.destination_granted
            and s.user_approved and s.data_owner_approved and not s.cancelled,
        "03_fenced_not_resumed": lambda s: s.phase == "fenced" and s.user_approved,
        "04_running": lambda s: s.phase == "running" and not s.commits,
        "05_first_effect": lambda s: s.phase == "running" and len(s.commits) == 1,
        "06_budget_exhausted": lambda s: s.phase == "running" and len(s.commits) == 2,
        "07_user_revoked_before_fence": lambda s: s.phase == "prepared"
            and s.destination_granted and not s.user_approved,
        "08_data_owner_revoked_before_fence": lambda s: s.phase == "prepared"
            and s.destination_granted and not s.data_owner_approved,
        "09_user_revoked_after_fence": lambda s: s.phase == "running" and not s.user_approved,
        "10_data_owner_revoked_after_fence": lambda s: s.phase == "running"
            and not s.data_owner_approved,
        "11_user_revoked_after_effect": lambda s: s.phase == "running"
            and len(s.commits) == 1 and not s.user_approved,
        "12_cancel_before_fence": lambda s: s.phase == "prepared"
            and s.destination_granted and s.cancelled,
        "13_cancel_after_fence": lambda s: s.phase == "running" and s.cancelled,
        "14_policy_rollover_before_fence": lambda s: s.phase == "prepared"
            and s.destination_granted and s.policy_epoch == 2,
        "15_policy_rollover_after_fence": lambda s: s.phase == "running"
            and s.policy_epoch == 2,
        "16_grant_expired_before_fence": lambda s: s.phase == "prepared"
            and s.destination_granted and s.clock == 2,
        "17_grant_expired_after_fence": lambda s: s.phase == "running"
            and s.clock == 2,
        "18_opaque_unknown_before_fence": lambda s: s.phase == "prepared"
            and s.destination_granted and s.opaque == "unknown",
        "19_opaque_unknown_after_fence": lambda s: s.phase == "running"
            and s.opaque == "unknown",
        "20_data_owner_revoked_after_effect": lambda s: s.phase == "running"
            and len(s.commits) == 1 and not s.data_owner_approved,
    }


def witnesses(max_depth: int = 9, max_states: int = 20_000) -> dict[str, tuple[str, ...]]:
    """Return shortest distinct MASM paths for all named cases, or fail closed."""
    if type(max_depth) is not int or max_depth < 0 or max_depth > 20:
        raise ValueError("max_depth must be in 0..20")
    if type(max_states) is not int or max_states < 1:
        raise ValueError("max_states must be positive")
    targets = _targets()
    hits: dict[str, tuple[str, ...]] = {}
    first = State()
    queue = deque([(first, ())])
    seen = {first}
    while queue and len(hits) < len(targets):
        state, path = queue.popleft()
        for name, predicate in targets.items():
            if name not in hits and predicate(state):
                hits[name] = path
        if len(path) >= max_depth:
            continue
        for edge in sorted(transitions(state), key=lambda e: e.name):
            if edge.name not in EVENTS:
                continue
            if edge.name in {"cancel_task", "dispatch_opaque_effect_unknown"} and not state.destination_granted:
                # Runtime cancel/unknown requires enrollment, unlike abstract MASM.
                continue
            if edge.state not in seen:
                seen.add(edge.state)
                if len(seen) > max_states:
                    raise RuntimeError("bounded witness search exceeded state cap")
                queue.append((edge.state, (*path, edge.name)))
    missing = sorted(set(targets) - set(hits))
    if missing:
        raise RuntimeError(f"unreachable within declared bounded profile: {missing}")
    return {key: hits[key] for key in sorted(hits)}


def report() -> dict[str, Any]:
    cases = witnesses()
    return {
        "model": "MASM-0.1-to-single-SQLite-guarded-lane",
        "kind": "shortest-witness-plan; NOT runtime verification",
        "case_count": len(cases),
        "scenarios": [{"case_id": name, "events": list(path)} for name, path in cases.items()],
        "abstract_markers": sorted(ABSTRACT_MARKERS),
        "unmapped": list(UNMAPPED),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="single-line deterministic report")
    args = parser.parse_args()
    obj = report()
    print(json.dumps(obj, sort_keys=True, separators=(",", ":") if args.json else None,
                     indent=None if args.json else 2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
