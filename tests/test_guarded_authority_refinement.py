"""Bounded MASM-to-runtime trace projection, with an independent SQLite oracle.

Generated witnesses are shortest paths *in the supported subgraph only*. We
deliberately do not claim crash, network, cross-runtime or resume conformance.
No real external actions or sensitive data are used.
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from agent_movement.core import Conflict, EffectGateway, PolicyDenied
from agent_movement.trust import Unauthorized
from authority_trace_plan import ABSTRACT_MARKERS, EVENTS, UNMAPPED, report, witnesses
from movement_authority_machine import State, apply, authorize_effect, authorize_transfer
from test_continuity_runtime import NOW, Rig
from test_guarded_authority import intent, notify, service


def _clock(tick: int) -> int:
    """Runtime projection of the abstract 0,1,2 ticks.

    tick 1 stays within the grant/consent/observation validity windows;
    tick 2 is beyond the grant, consent and observation expiry windows.
    This maps the *boundary*, not a shared clock model.
    """
    return (NOW, NOW + 100, NOW + 1300)[tick]


def _sql_snapshot(path: Path) -> dict[str, object]:
    """Read committed data independently, never using GuardedAuthority.inspect."""
    with sqlite3.connect(path) as db:
        owner = db.execute(
            "SELECT agent_id,epoch FROM owners WHERE task_id='task-1'"
        ).fetchone()
        guard = db.execute(
            "SELECT status,budget_limit,budget_used,cancelled,unknown_effect "
            "FROM guarded_tasks WHERE task_id='task-1'"
        ).fetchone()
        effects = db.execute(
            "SELECT effect_id,epoch FROM effects WHERE task_id='task-1' "
            "ORDER BY effect_id"
        ).fetchall()
        policy = db.execute(
            "SELECT epoch FROM continuity_control WHERE singleton=1"
        ).fetchone()
        consents = db.execute(
            "SELECT principal,revoked FROM continuity_consents "
            "WHERE movement_id='movement-1' AND task_id='task-1' ORDER BY principal"
        ).fetchall()
        peer_effects = db.execute(
            "SELECT effect_id FROM authorized_effects WHERE task_id='task-1'"
        ).fetchall()
        return {
            "owner": tuple(owner) if owner else None,
            "guard": tuple(guard) if guard else None,
            "effects": tuple(tuple(row) for row in effects),
            "policy_epoch": policy[0] if policy else None,
            "consents": tuple(tuple(row) for row in consents),
            "peer_effects": tuple(tuple(row) for row in peer_effects),
        }


def _model_projection(s: State) -> dict[str, object]:
    """Only fields that are actually observable in this implementation."""
    guard = None
    if s.destination_granted:
        guard = (
            "prepared" if s.phase == "prepared" else "transferred",
            2, len(s.commits), int(s.cancelled), int(s.opaque == "unknown"),
        )
    return {
        "owner": ("agent-a", 1) if s.owner == "A" else ("agent-b", 2),
        "guard": guard,
        "effects": tuple(sorted((c.effect_id, c.presented_epoch) for c in s.commits)),
        "policy_epoch": 3 + s.policy_epoch,
        "consents": (("data-owner", int(not s.data_owner_approved)),
                     ("human", int(not s.user_approved))),
        "peer_effects": (),
    }


def _new_lab(tmp_path: Path):
    rig = Rig(tmp_path)
    rig.install()
    assert EffectGateway(rig.store).claim("task-1", "agent-a") == 1
    gateway = service(rig)
    return rig, gateway


def _step(rig: Rig, gateway, action: str, state: State) -> None:
    if action == "prepare_destination":
        return  # abstract metadata-only marker
    if action == "issue_attenuated_grant_B":
        gateway.enroll(intent(rig), rig.grant)  # admits an ALREADY signed grant
    elif action == "fence_and_transfer":
        assert gateway.transfer("task-1", "movement-1") == 2
    elif action == "resume_destination":
        return  # IMPORTANT: no runtime activation barrier; known unverified gap
    elif action.startswith("commit_B_"):
        effect_id = action[len("commit_B_"):]
        assert gateway.commit("task-1", "movement-1", "agent-b", 2,
                              effect_id, "synthetic:" + effect_id) is True
    elif action == "revoke_user":
        rig.revoke("human")
    elif action == "revoke_data_owner":
        rig.revoke("data-owner")
    elif action == "cancel_task":
        gateway.cancel(notify(rig, "guarded-cancel"))
    elif action == "bump_policy_epoch":
        rig.runtime.advance_epoch(5)
    elif action == "advance_clock":
        rig.now = _clock(state.clock + 1)
    elif action == "dispatch_opaque_effect_unknown":
        # The runtime only models a signed HOLD. It does not actually dispatch
        # an opaque external effect: this is a conservative status projection.
        gateway.mark_unknown(notify(rig, "guarded-unknown"))
    else:
        raise AssertionError("an unmapped action reached the projector: " + action)


def _replay(tmp_path: Path, events: tuple[str, ...]):
    rig, gateway = _new_lab(tmp_path)
    state = State()
    assert _sql_snapshot(rig.store.path) == _model_projection(state)
    for action in events:
        assert action in EVENTS
        next_state = apply(state, action)
        _step(rig, gateway, action, state)
        observed = _sql_snapshot(rig.store.path)
        projected = _model_projection(next_state)
        assert observed == projected, (
            f"SQL/model mismatch after {action}; prefix={events}; "
            f"observed={observed!r}; projected={projected!r}"
        )
        state = next_state
    return rig, gateway, state


def test_witness_plan_is_deterministic_and_covers_declared_cases():
    a, b = witnesses(), witnesses()
    assert a == b
    assert len(a) == 20
    assert len(set(a.values())) == len(a)
    assert max(map(len, a.values())) <= 9
    assert len(ABSTRACT_MARKERS) == 2
    assert "operator_claim_done/absent" in " ".join(UNMAPPED)
    for trace in a.values():
        s = State()
        for action in trace:
            assert action in EVENTS
            s = apply(s, action)
    assert len(report()["scenarios"]) == len(a)


@pytest.mark.parametrize("name,events", list(witnesses().items()))
def test_generated_shortest_witness_replays_against_independent_sql(tmp_path, name, events):
    rig, gateway, state = _replay(tmp_path, events)
    assert name in witnesses()
    assert not any(c.executor != "B" for c in state.commits)

    # The model and the guarded runtime both refuse a second transfer after
    # fencing or revocation. Do not mutate a successful PREPARED transfer probe.
    if state.destination_granted and not authorize_transfer(state).allowed:
        before = _sql_snapshot(rig.store.path)
        with pytest.raises((Conflict, PolicyDenied, Unauthorized)):
            gateway.transfer("task-1", "movement-1")
        assert _sql_snapshot(rig.store.path) == before

    # Probe an effect without changing the durable projection when the model
    # denies it. A same-ID replay may return False, which is also no new effect.
    if state.destination_granted and state.phase != "fenced":
        decision = authorize_effect(state, "B", "publish-1")
        if not decision.allowed:
            before = _sql_snapshot(rig.store.path)
            try:
                result = gateway.commit(
                    "task-1", "movement-1", "agent-b", 2,
                    "publish-1", "synthetic:publish-1",
                )
                assert result is False, (name, decision.reason)
            except (Conflict, PolicyDenied, Unauthorized):
                pass
            assert _sql_snapshot(rig.store.path) == before


def test_abstract_activation_gap_is_observable_and_not_claimed_safe(tmp_path):
    """MASM requires resume; current guarded effect route has no such barrier.

    This is an intentionally *passing counterexample assertion* to whole-model
    refinement. If implementation adds real authenticated activation, rewrite
    this as a positive enforcement test instead of deleting the evidence.
    """
    events = witnesses()["03_fenced_not_resumed"]
    rig, gateway, state = _replay(tmp_path, events)
    assert state.phase == "fenced"
    assert not authorize_effect(state, "B", "publish-1").allowed
    # Runtime is less restrictive: it can commit immediately after ownership
    # transfer. That is why this suite claims PARTIAL, never FULL refinement.
    assert gateway.commit(
        "task-1", "movement-1", "agent-b", 2,
        "publish-1", "synthetic:publish-1",
    ) is True
    assert _sql_snapshot(rig.store.path)["effects"] == (("publish-1", 2),)


def test_operator_outcome_claim_has_no_supported_resume_mapping(tmp_path):
    _, gateway, state = _replay(
        tmp_path, witnesses()["19_opaque_unknown_after_fence"]
    )
    assert state.opaque == "unknown"
    assert not hasattr(gateway, "clear_unknown")
    # Deliberately no operator_claim_done => no fabricated external evidence.


def test_witness_cli_emits_reproducible_sanitized_plan():
    root = Path(__file__).resolve().parents[1]
    command = [sys.executable, str(root / "tools" / "authority_trace_plan.py"), "--json"]
    first = subprocess.run(command, check=True, capture_output=True, text=True, timeout=20)
    again = subprocess.run(command, check=True, capture_output=True, text=True, timeout=20)
    assert first.stdout == again.stdout
    parsed = json.loads(first.stdout)
    assert parsed["case_count"] == len(witnesses())
    assert parsed["abstract_markers"] == sorted(ABSTRACT_MARKERS)
    assert "SECRET-CANARY" not in first.stdout
    assert "private" not in first.stdout.lower()
