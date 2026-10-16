"""Bounded exhaustive explorer for a *toy*, protected agent relocation protocol.

This is an abstract model, not a proof about the production interfaces.  The
single gateway is the linearization point for epoch and effect commits.  All
records are synthetic, and the intentionally unsafe variant is a negative
control for the checker.
"""

from __future__ import annotations

import argparse
import json
from collections import deque
from dataclasses import dataclass, replace
from typing import NamedTuple

EFFECT_IDS = ("effect-1", "effect-2")


@dataclass(frozen=True)
class Effect:
    effect_id: str
    worker: str
    token_epoch: int
    owner_at_commit: str
    epoch_at_commit: int
    grant_live: bool
    gateway_up: bool
    revoked_at_commit: bool


@dataclass(frozen=True)
class State:
    phase: str = "origin"
    owner: str = "A"
    epoch: int = 1
    destination_granted: bool = False
    a_running: bool = True
    b_running: bool = False
    gateway_up: bool = True
    revoked: bool = False
    effects: tuple[Effect, ...] = ()


class Transition(NamedTuple):
    name: str
    state: State


class Counterexample(NamedTuple):
    property_name: str
    trace: tuple[str, ...]
    state: State


class Exploration(NamedTuple):
    states: int
    transitions: int
    exhausted: bool
    counterexample: Counterexample | None


def violations(state: State) -> tuple[str, ...]:
    """Safety assertions over the current state and historical effect facts."""
    failures: list[str] = []
    expected_owner = "A" if state.phase in {"origin", "prepared"} else "B"
    expected_epoch = 1 if expected_owner == "A" else 2
    if (state.owner, state.epoch) != (expected_owner, expected_epoch):
        failures.append("CoherentAuthority")
    if state.b_running and state.phase != "running":
        failures.append("DestinationActivationOrder")
    if state.phase in {"fenced", "running"} and not state.destination_granted:
        failures.append("SeparateDestinationGrant")
    ids = [record.effect_id for record in state.effects]
    if len(ids) != len(set(ids)):
        failures.append("IdempotentProtectedEffect")
    for record in state.effects:
        if (record.worker, record.token_epoch) != (record.owner_at_commit, record.epoch_at_commit):
            failures.append("CurrentEpochAtCommit")
        if not record.grant_live or record.revoked_at_commit:
            failures.append("AuthorizedAtCommit")
        if not record.gateway_up:
            failures.append("FailClosedGateway")
    return tuple(dict.fromkeys(failures))


def transitions(state: State, *, unsafe_stale_writer: bool = False) -> tuple[Transition, ...]:
    """Every enabled atomic transition; stuttering actions are omitted."""
    options: list[Transition] = []
    def add(name: str, **updates: object) -> None:
        options.append(Transition(name, replace(state, **updates)))

    if state.phase == "origin":
        add("prepare_destination", phase="prepared")
    if state.phase == "prepared" and not state.destination_granted and not state.revoked:
        add("issue_separate_destination_grant", destination_granted=True)
    if state.phase == "prepared" and state.destination_granted and state.gateway_up and not state.revoked:
        # A single linearizable gateway owns the epoch register and effect ledger.
        add("atomic_fence_and_transfer", phase="fenced", owner="B", epoch=2)
    if state.phase == "fenced" and state.destination_granted and not state.revoked:
        add("resume_destination", phase="running", b_running=True)
    if state.a_running:
        add("crash_A", a_running=False)
    else:
        # Restarting an old process does NOT refresh its epoch token.
        add("restart_stale_A", a_running=True)
    if state.b_running:
        add("crash_B", b_running=False)
    elif state.phase == "running":
        add("restart_B", b_running=True)
    add("partition_gateway" if state.gateway_up else "heal_gateway", gateway_up=not state.gateway_up)
    if not state.revoked:
        add("revoke_authority", revoked=True)

    committed = {effect.effect_id for effect in state.effects}
    for worker, running, token_epoch, has_grant in (
        ("A", state.a_running, 1, True),
        ("B", state.b_running, 2, state.destination_granted),
    ):
        if not (running and has_grant and state.gateway_up and not state.revoked):
            continue
        # The protected effect is emitted only if owner and token still match
        # the gateway's authoritative, durable fencing record.
        current = worker == state.owner and token_epoch == state.epoch
        if worker == "B" and state.phase != "running":
            current = False
        for effect_id in EFFECT_IDS:
            if effect_id in committed:
                continue  # Replays are deduplicated by the stable logical effect ID.
            if current or (unsafe_stale_writer and worker == "A" and state.owner == "B"):
                effect = Effect(
                    effect_id=effect_id,
                    worker=worker,
                    token_epoch=token_epoch,
                    owner_at_commit=state.owner,
                    epoch_at_commit=state.epoch,
                    grant_live=has_grant,
                    gateway_up=state.gateway_up,
                    revoked_at_commit=state.revoked,
                )
                label = "unsafe_stale_A_effect" if not current else f"commit_{worker}_{effect_id}"
                add(label, effects=(*state.effects, effect))
    return tuple(options)


def explore(max_depth: int = 12, *, unsafe_stale_writer: bool = False) -> Exploration:
    """BFS over all schedules up to max_depth (not a universal proof)."""
    if max_depth < 0:
        raise ValueError("max_depth must be nonnegative")
    initial = State()
    queue = deque([(initial, ())])
    seen = {initial}
    edge_count = 0
    truncated = False
    while queue:
        state, history = queue.popleft()
        broken = violations(state)
        if broken:
            return Exploration(len(seen), edge_count, False, Counterexample(broken[0], history, state))
        if len(history) >= max_depth:
            if any(t.state not in seen for t in transitions(state, unsafe_stale_writer=unsafe_stale_writer)):
                truncated = True
            continue
        for transition in transitions(state, unsafe_stale_writer=unsafe_stale_writer):
            edge_count += 1
            if transition.state not in seen:
                seen.add(transition.state)
                queue.append((transition.state, (*history, transition.name)))
    return Exploration(len(seen), edge_count, not truncated, None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--depth", type=int, default=12, help="maximum transition depth (default 12)")
    parser.add_argument(
        "--unsafe-stale-writer", action="store_true",
        help="negative control: remove stale-owner gateway check (expected failure)",
    )
    args = parser.parse_args()
    outcome = explore(args.depth, unsafe_stale_writer=args.unsafe_stale_writer)
    report = {
        "model": "two-workers-one-authoritative-gateway",
        "depth_bound": args.depth,
        "unsafe_negative_control": args.unsafe_stale_writer,
        "visited_states": outcome.states,
        "explored_transitions": outcome.transitions,
        "exhausted_finite_state_space": outcome.exhausted,
        "status": "counterexample" if outcome.counterexample else "no_violation_within_bound",
        "violated_property": outcome.counterexample.property_name if outcome.counterexample else None,
        "counterexample_trace": list(outcome.counterexample.trace) if outcome.counterexample else [],
    }
    print(json.dumps(report, sort_keys=True))
    return 1 if outcome.counterexample else 0


if __name__ == "__main__":
    raise SystemExit(main())
