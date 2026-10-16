"""Finite, synthetic Movement Authority State Machine (MASM-0.1).

This is an executable *specification*, NOT the runtime's authorization service.
It proves nothing about arbitrary external effects or transport/OS bypasses.
The trusted, single gateway is the linearization point for authority and
protected effects. Model inputs are verifier facts, not client assertions.
"""

from __future__ import annotations

import argparse
import json
from collections import deque
from dataclasses import dataclass, replace
from typing import Literal, NamedTuple

Worker = Literal["A", "B"]
Phase = Literal["origin", "prepared", "fenced", "running"]
Opaque = Literal["none", "unknown", "operator_claim_done", "operator_claim_absent"]
Mutation = Literal["none", "skip_epoch", "skip_principals", "skip_dedup", "skip_policy"]
EFFECTS = ("publish-1", "publish-2")
ROOT_SCOPES = frozenset(("read", "publish"))
CHILD_SCOPES = frozenset(("publish",))
EXPIRES_AT = 1  # abstract, bounded clock ticks; not UTC seconds
MAX_BUDGET = 2


@dataclass(frozen=True)
class Commit:
    """Historical facts frozen at the instant of a protected effect commit."""

    effect_id: str
    executor: Worker
    presented_epoch: int
    owner_at_commit: Worker
    owner_epoch_at_commit: int
    user_valid: bool
    data_owner_valid: bool
    policy_epoch: int
    grant_policy_epoch: int
    grant_scope: frozenset[str]
    grant_audience: Worker | None
    grant_for_task: str | None
    gateway_available: bool
    cancelled_at_commit: bool
    clock_at_commit: int
    expires_at: int
    budget_before: int
    budget_after: int


@dataclass(frozen=True)
class State:
    phase: Phase = "origin"
    owner: Worker = "A"
    epoch: int = 1
    destination_granted: bool = False
    child_policy_epoch: int = 0
    child_scopes: frozenset[str] = frozenset()
    child_audience: Worker | None = None
    child_task_id: str | None = None
    a_running: bool = True
    b_running: bool = False
    gateway_up: bool = True
    user_approved: bool = True
    data_owner_approved: bool = True
    policy_epoch: int = 1
    clock: int = 0
    cancelled: bool = False
    budget_left: int = MAX_BUDGET
    opaque: Opaque = "none"
    commits: tuple[Commit, ...] = ()


class Decision(NamedTuple):
    allowed: bool
    reason: str


class Edge(NamedTuple):
    name: str
    state: State


class Violation(NamedTuple):
    invariant: str
    trace: tuple[str, ...]
    state: State


class Result(NamedTuple):
    states: int
    transitions: int
    depth: int
    exhausted: bool
    counterexample: Violation | None


def _grant_policy_epoch(s: State, worker: Worker) -> int:
    return 1 if worker == "A" else s.child_policy_epoch


def _grant_scope(s: State, worker: Worker) -> frozenset[str]:
    return ROOT_SCOPES if worker == "A" else s.child_scopes


def authorize_child_grant(
    s: State, *, task_id: str, audience: Worker, scopes: frozenset[str],
) -> Decision:
    """Issuance must be attenuated, version-bound and independently approved."""
    if s.phase != "prepared" or s.destination_granted or s.cancelled:
        return Decision(False, "not_prepared")
    if not s.user_approved or not s.data_owner_approved:
        return Decision(False, "mandatory_principal_revoked")
    if s.policy_epoch != 1 or s.clock > EXPIRES_AT:
        return Decision(False, "parent_grant_not_live")
    if task_id != "task-1" or audience != "B":
        return Decision(False, "incorrect_task_or_audience")
    if not scopes or not scopes <= ROOT_SCOPES:
        return Decision(False, "scope_escalation")
    return Decision(True, "authorized")


def authorize_effect(
    s: State, worker: Worker, effect_id: str,
    *, mutation: Mutation = "none",
) -> Decision:
    """The fail-closed commit predicate; evaluated at the gateway, not by the agent."""
    if s.cancelled:
        return Decision(False, "cancelled")
    if not s.gateway_up:
        return Decision(False, "gateway_unavailable")
    if not (s.a_running if worker == "A" else s.b_running):
        return Decision(False, "executor_unavailable")
    if s.opaque == "unknown":
        return Decision(False, "unknown_effect_requires_reconciliation")
    if not s.user_approved or not s.data_owner_approved:
        if mutation != "skip_principals":
            return Decision(False, "mandatory_principal_revoked")
    if worker == "B":
        if not s.destination_granted or s.phase != "running":
            return Decision(False, "destination_not_authorized_or_active")
        if s.child_audience != "B" or s.child_task_id != "task-1":
            return Decision(False, "child_grant_wrong_audience_or_task")
        if not s.child_scopes or not s.child_scopes <= ROOT_SCOPES:
            return Decision(False, "child_grant_not_attenuated")
    token_epoch = 1 if worker == "A" else 2
    if (worker, token_epoch) != (s.owner, s.epoch) and mutation != "skip_epoch":
        return Decision(False, "stale_owner_or_epoch")
    if _grant_policy_epoch(s, worker) != s.policy_epoch and mutation != "skip_policy":
        return Decision(False, "policy_epoch_mismatch")
    if s.clock > EXPIRES_AT:
        return Decision(False, "expired_grant")
    if "publish" not in _grant_scope(s, worker):
        return Decision(False, "missing_action_scope")
    if s.budget_left <= 0:
        return Decision(False, "budget_exhausted")
    if any(c.effect_id == effect_id for c in s.commits) and mutation != "skip_dedup":
        return Decision(False, "already_committed")
    if effect_id not in EFFECTS:
        return Decision(False, "unsupported_effect")
    return Decision(True, "authorized")


def authorize_transfer(s: State) -> Decision:
    """High-level movement decision; stronger than a low-level ownership CAS."""
    if s.phase != "prepared" or s.owner != "A" or s.epoch != 1:
        return Decision(False, "not_prepared_or_stale")
    if s.cancelled or not s.user_approved or not s.data_owner_approved:
        return Decision(False, "authority_revoked_or_cancelled")
    if not s.gateway_up:
        return Decision(False, "gateway_unavailable")
    if not s.destination_granted or s.child_policy_epoch != s.policy_epoch:
        return Decision(False, "destination_grant_missing_or_stale")
    if (s.child_audience != "B" or s.child_task_id != "task-1"
            or not s.child_scopes or not s.child_scopes <= ROOT_SCOPES):
        return Decision(False, "destination_grant_binding_or_scope")
    if s.policy_epoch != 1 or s.clock > EXPIRES_AT:
        return Decision(False, "root_authority_expired_or_changed")
    if not CHILD_SCOPES <= ROOT_SCOPES:
        return Decision(False, "scope_escalation")
    if s.opaque == "unknown":
        return Decision(False, "external_effect_unknown")
    return Decision(True, "authorized")


def violations(s: State) -> tuple[str, ...]:
    """Historical, not present-tense, invariants (revocation is not retroactive)."""
    errors: list[str] = []
    expected_owner: Worker = "A" if s.phase in ("origin", "prepared") else "B"
    if (s.owner, s.epoch) != (expected_owner, 1 if expected_owner == "A" else 2):
        errors.append("UniqueMonotonicOwnership")
    if s.b_running and s.phase != "running":
        errors.append("DestinationActivationOrder")
    if s.phase in ("fenced", "running") and not s.destination_granted:
        errors.append("SeparateAttenuatedGrant")
    if s.destination_granted:
        if s.child_policy_epoch != 1:
            errors.append("InitialPolicyBoundGrant")
        if s.child_audience != "B" or s.child_task_id != "task-1":
            errors.append("DestinationGrantBinding")
        if not s.child_scopes or not s.child_scopes <= ROOT_SCOPES:
            errors.append("NoPrivilegeEscalation")
    ids = [c.effect_id for c in s.commits]
    if len(ids) != len(set(ids)):
        errors.append("NoDuplicateProtectedEffect")
    if s.budget_left != MAX_BUDGET - len(s.commits) or s.budget_left < 0:
        errors.append("SharedBudgetConservation")
    for commit in s.commits:
        if (commit.executor, commit.presented_epoch) != (
            commit.owner_at_commit, commit.owner_epoch_at_commit,
        ):
            errors.append("EffectRequiresCurrentFencingEpoch")
        if not commit.user_valid or not commit.data_owner_valid or commit.cancelled_at_commit:
            errors.append("AllPrincipalsAtEffectCommit")
        if commit.grant_policy_epoch != commit.policy_epoch:
            errors.append("PolicyEpochAtEffectCommit")
        if "publish" not in commit.grant_scope or commit.grant_audience != commit.executor:
            errors.append("EffectGrantScopeAudience")
        if commit.grant_for_task != "task-1":
            errors.append("EffectGrantTaskBinding")
        if commit.clock_at_commit > commit.expires_at or not commit.gateway_available:
            errors.append("FreshGrantAndAvailableGateway")
        if commit.budget_before <= 0 or commit.budget_after != commit.budget_before - 1:
            errors.append("AtomicBudgetAccounting")
    return tuple(dict.fromkeys(errors))


def transitions(s: State, *, mutation: Mutation = "none") -> tuple[Edge, ...]:
    """All enabled, non-stuttering atomic steps; no external tool is invoked."""
    edges: list[Edge] = []

    def add(name: str, **kwargs: object) -> None:
        edges.append(Edge(name, replace(s, **kwargs)))

    if s.phase == "origin" and not s.cancelled:
        add("prepare_destination", phase="prepared")
    if authorize_child_grant(s, task_id="task-1", audience="B", scopes=CHILD_SCOPES).allowed:
        add("issue_attenuated_grant_B", destination_granted=True,
            child_policy_epoch=s.policy_epoch, child_scopes=CHILD_SCOPES,
            child_task_id="task-1", child_audience="B")
    if authorize_transfer(s).allowed:
        add("fence_and_transfer", phase="fenced", owner="B", epoch=2)
    if s.phase == "fenced" and not s.cancelled and s.destination_granted:
        add("resume_destination", phase="running", b_running=True)
    if s.a_running:
        add("crash_A", a_running=False)
    else:
        add("restart_stale_A", a_running=True)  # restart preserves old token (epoch=1)
    if s.b_running:
        add("crash_B", b_running=False)
    elif s.phase == "running" and not s.cancelled:
        add("restart_B", b_running=True)
    add("partition_gateway" if s.gateway_up else "heal_gateway", gateway_up=not s.gateway_up)
    if s.user_approved:
        add("revoke_user", user_approved=False)
    if s.data_owner_approved:
        add("revoke_data_owner", data_owner_approved=False)
    if not s.cancelled:
        add("cancel_task", cancelled=True)
    if s.policy_epoch == 1:
        add("bump_policy_epoch", policy_epoch=2)
    if s.clock < 2:
        add("advance_clock", clock=s.clock + 1)
    if s.opaque == "unknown":
        # Operator claims are not evidence of the real external tool outcome.
        add("operator_claim_done", opaque="operator_claim_done")
        add("operator_claim_absent", opaque="operator_claim_absent")
    elif s.opaque == "none" and not s.cancelled and s.gateway_up and s.clock <= EXPIRES_AT:
        if (s.user_approved and s.data_owner_approved and s.policy_epoch == 1
                and ((s.owner == "A" and s.a_running) or
                     (s.owner == "B" and s.b_running and s.child_policy_epoch == 1))):
            add("dispatch_opaque_effect_unknown", opaque="unknown")
    for worker in ("A", "B"):
        for effect_id in EFFECTS:
            decision = authorize_effect(s, worker, effect_id, mutation=mutation)
            if not decision.allowed:
                continue
            record = Commit(
                effect_id=effect_id, executor=worker,
                presented_epoch=1 if worker == "A" else 2,
                owner_at_commit=s.owner, owner_epoch_at_commit=s.epoch,
                user_valid=s.user_approved, data_owner_valid=s.data_owner_approved,
                policy_epoch=s.policy_epoch, grant_policy_epoch=_grant_policy_epoch(s, worker),
                grant_scope=_grant_scope(s, worker),
                grant_audience="A" if worker == "A" else s.child_audience,
                grant_for_task="task-1" if worker == "A" else s.child_task_id,
                gateway_available=s.gateway_up,
                cancelled_at_commit=s.cancelled, clock_at_commit=s.clock,
                expires_at=EXPIRES_AT, budget_before=s.budget_left,
                budget_after=s.budget_left - 1,
            )
            add(f"commit_{worker}_{effect_id}",
                commits=(*s.commits, record), budget_left=s.budget_left - 1)
    return tuple(edges)


def apply(s: State, action: str, *, mutation: Mutation = "none") -> State:
    found = [edge.state for edge in transitions(s, mutation=mutation) if edge.name == action]
    if len(found) != 1:
        raise ValueError(f"event not enabled or ambiguous: {action}")
    return found[0]


def explore(max_depth: int = 9, *, mutation: Mutation = "none", max_states: int = 200_000) -> Result:
    """Breadth-first exploration; shortest counterexample under explicit finite bounds."""
    if max_depth < 0 or max_states < 1:
        raise ValueError("max_depth must be >= 0 and max_states >= 1")
    if mutation not in ("none", "skip_epoch", "skip_principals", "skip_dedup", "skip_policy"):
        raise ValueError("unknown mutation")
    queue: deque[tuple[State, tuple[str, ...]]] = deque([(State(), ())])
    seen = {State()}
    edges = 0
    truncated = False
    while queue:
        state, path = queue.popleft()
        broken = violations(state)
        if broken:
            return Result(len(seen), edges, max_depth, False, Violation(broken[0], path, state))
        nxt = transitions(state, mutation=mutation)
        if len(path) >= max_depth:
            if any(edge.state not in seen for edge in nxt):
                truncated = True
            continue
        for edge in nxt:
            edges += 1
            if edge.state in seen:
                continue
            if len(seen) >= max_states:
                truncated = True
                continue
            seen.add(edge.state)
            queue.append((edge.state, (*path, edge.name)))
    return Result(len(seen), edges, max_depth, not truncated, None)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--depth", type=int, default=9)
    p.add_argument("--max-states", type=int, default=200_000)
    p.add_argument("--mutation", choices=("none", "skip_epoch", "skip_principals", "skip_dedup", "skip_policy"), default="none")
    args = p.parse_args()
    result = explore(args.depth, mutation=args.mutation, max_states=args.max_states)
    report = {
        "model": "MASM-0.1",
        "assumption": "one trusted atomic gateway and independently verified issuer facts",
        "depth": result.depth,
        "visited_states": result.states,
        "transitions": result.transitions,
        "complete_finite_state_space": result.exhausted,
        "status": "counterexample" if result.counterexample else "no_violation_within_bound",
        "violated_invariant": result.counterexample.invariant if result.counterexample else None,
        "counterexample": list(result.counterexample.trace) if result.counterexample else [],
        "mutation": args.mutation,
    }
    print(json.dumps(report, sort_keys=True))
    return 1 if result.counterexample else 0


if __name__ == "__main__":
    raise SystemExit(main())
