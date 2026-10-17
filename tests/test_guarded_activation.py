"""Signed destination activation and per-effect identity binding (issue #103).

Synthetic single-store experiment; signatures authenticate test principals, not
remote processes, host integrity or liveness.
"""

from __future__ import annotations

import multiprocessing
import os
import subprocess
import sqlite3
import sys

import pytest

from agent_movement.core import Conflict, EffectGateway, PolicyDenied
from agent_movement.trust import HmacKey, Unauthorized, seal
from test_continuity_runtime import NOW, Rig
from test_guarded_authority import (
    activate,
    activation_ack,
    authorized_commit,
    effect_token,
    intent,
    notify,
    service,
)


@pytest.fixture
def fenced(tmp_path):
    rig = Rig(tmp_path)
    rig.install()
    EffectGateway(rig.store).claim("task-1", "agent-a")
    gate = service(rig)
    gate.enroll(intent(rig), rig.grant)
    assert gate.transfer("task-1", "movement-1") == 2
    assert gate.inspect("task-1")["phase"] == "fenced"
    return rig, gate


def state(rig):
    with sqlite3.connect(rig.store.path) as db:
        phase = db.execute("SELECT status FROM guarded_tasks WHERE task_id='task-1'").fetchone()
        owner = db.execute("SELECT agent_id,epoch FROM owners WHERE task_id='task-1'").fetchone()
        effects = db.execute("SELECT effect_id,epoch FROM effects WHERE task_id='task-1'").fetchall()
        budget = db.execute("SELECT budget_used FROM guarded_tasks WHERE task_id='task-1'").fetchone()
        activations = db.execute("SELECT activation_id,nonce FROM guarded_activations").fetchall()
    return {"phase": phase[0], "owner": owner, "effects": effects, "budget": budget[0],
            "activations": activations}


def test_fenced_owner_cannot_commit_with_signed_invocation_before_activation(fenced):
    rig, gate = fenced
    with pytest.raises(PolicyDenied, match="not authenticated and activated"):
        authorized_commit(rig, gate, "task-1", "movement-1", "agent-b", 2, "effect-1", "safe")
    assert state(rig) == {
        "phase": "fenced", "owner": ("agent-b", 2), "effects": [],
        "budget": 0, "activations": [],
    }


def test_successful_signed_activation_replay_and_effect_idempotency(fenced):
    rig, gate = fenced
    ack = activation_ack(rig)
    assert gate.activate(ack) is True
    assert gate.activate(ack) is False
    assert gate.inspect("task-1")["phase"] == "active"
    assert gate.inspect("task-1")["activated"] is True
    assert authorized_commit(rig, gate, "task-1", "movement-1", "agent-b", 2, "effect-1", "safe")
    assert not authorized_commit(rig, gate, "task-1", "movement-1", "agent-b", 2, "effect-1", "safe")
    with pytest.raises(Conflict):
        authorized_commit(rig, gate, "task-1", "movement-1", "agent-b", 2, "effect-1", "different")
    s = state(rig)
    assert s["effects"] == [("effect-1", 2)]
    assert s["budget"] == 1
    assert len(s["activations"]) == 1


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"task": "task-other"}, "not enrolled"),
        ({"movement": "movement-other"}, "binding"),
        ({"destination": "agent-z"}, "binding"),
        ({"epoch": 3}, "epoch"),
        ({"policy_epoch": 5}, "authority"),
        ({"kind": "sha256"}, "authority"),
        ({"scope": "sha256"}, "authority"),
        ({"grant": {"not": "the pinned issuer grant"}}, "authority"),
        ({"expires_at": NOW}, "expired"),
        ({"expires_at": NOW + 121}, "expired"),
    ],
)
def test_misbound_activation_never_transitions_to_active(fenced, overrides, reason):
    rig, gate = fenced
    kwargs = dict(overrides)
    if "kind" in kwargs:
        # The helper signs only the declared word_count kind; modify the signed fields here.
        kind = kwargs.pop("kind")
        raw = activation_ack(rig)
        raw["payload"]["kind"] = kind
        raw = seal("guarded-activation", raw["payload"], rig.dest_key)
    else:
        raw = activation_ack(rig, **kwargs)
    with pytest.raises((Unauthorized, PolicyDenied, Conflict), match=reason):
        gate.activate(raw)
    assert state(rig)["phase"] == "fenced"
    assert state(rig)["effects"] == []


def test_forged_or_unsigned_activation_cannot_clear_fence(fenced):
    rig, gate = fenced
    forged = activation_ack(rig, signer=HmacKey.generate(rig.dest_key.kid))
    with pytest.raises(PolicyDenied):
        gate.activate(forged)
    with pytest.raises((PolicyDenied, ValueError)):
        gate.activate({"type": "guarded-activation", "task_id": "task-1"})
    assert state(rig)["activations"] == []


def test_conflicting_replay_and_nonce_reuse_are_denied(fenced):
    rig, gate = fenced
    ack = activation_ack(rig)
    assert gate.activate(ack)
    changed = activation_ack(rig, nonce="different-nonce")
    with pytest.raises(Conflict, match="activation replay changed"):
        gate.activate(changed)
    assert len(state(rig)["activations"]) == 1


@pytest.mark.parametrize("hold", ["revoke", "cancel", "unknown", "epoch", "expired"])
def test_revocation_holds_and_expiry_block_activation_after_fencing(fenced, hold):
    rig, gate = fenced
    if hold == "revoke":
        rig.revoke("human")
    elif hold == "cancel":
        gate.cancel(notify(rig, "guarded-cancel"))
    elif hold == "unknown":
        gate.mark_unknown(notify(rig, "guarded-unknown"))
    elif hold == "epoch":
        rig.runtime.advance_epoch(5)
    else:
        rig.now = NOW + 1201
    with pytest.raises(PolicyDenied):
        gate.activate(activation_ack(rig))
    assert state(rig)["phase"] == "fenced"


def test_missing_or_forged_per_effect_identity_denied_after_activation(fenced):
    rig, gate = fenced
    assert activate(rig, gate)
    with pytest.raises(PolicyDenied):
        gate.commit("task-1", "movement-1", "agent-b", 2, "effect-1", "safe")
    fake = effect_token(rig, "task-1", "movement-1", "agent-b", 2, "effect-1", "safe",
                        signer=HmacKey.generate(rig.dest_key.kid))
    with pytest.raises(PolicyDenied):
        gate.commit("task-1", "movement-1", "agent-b", 2, "effect-1", "safe",
                    signed_execution=fake)
    assert state(rig)["effects"] == []


@pytest.mark.parametrize("tamper", ["task", "movement", "agent", "epoch", "effect", "payload", "activation"])
def test_valid_signature_must_bind_specific_effect_invocation(fenced, tamper):
    rig, gate = fenced
    assert activate(rig, gate)
    token = effect_token(rig, "task-1", "movement-1", "agent-b", 2, "effect-1", "safe")
    payload = dict(token["payload"])
    if tamper == "task":
        payload["task_id"] = "task-other"
    elif tamper == "movement":
        payload["movement_id"] = "movement-other"
    elif tamper == "agent":
        payload["destination_id"] = "agent-c"
    elif tamper == "epoch":
        payload["owner_epoch"] = 3
    elif tamper == "effect":
        payload["effect_id"] = "effect-other"
    elif tamper == "payload":
        payload["payload_sha256"] = "f" * 64
    else:
        payload["activation_id"] = "other-activation"
    altered = seal("guarded-effect-invocation", payload, rig.dest_key)
    with pytest.raises(PolicyDenied):
        gate.commit("task-1", "movement-1", "agent-b", 2, "effect-1", "safe",
                    signed_execution=altered)
    assert state(rig)["effects"] == []


def test_activation_proof_expires_and_cannot_be_refreshed_by_old_receipt(fenced):
    rig, gate = fenced
    assert activate(rig, gate)
    rig.now = NOW + 110
    with pytest.raises(PolicyDenied, match="activation_expired"):
        authorized_commit(rig, gate, "task-1", "movement-1", "agent-b", 2, "late", "safe")
    with pytest.raises((PolicyDenied, Conflict)):
        gate.activate(activation_ack(rig, expires_at=NOW + 115))
    assert state(rig)["effects"] == []


def test_restarted_gateway_reads_same_signed_activation_and_effect_budget(fenced):
    rig, gate = fenced
    ack = activation_ack(rig)
    assert gate.activate(ack)
    fresh_instance = service(rig)  # new gateway instance, same durable trust/SQLite state
    assert fresh_instance.activate(ack) is False
    assert authorized_commit(rig, fresh_instance, "task-1", "movement-1", "agent-b", 2,
                             "effect-1", "safe")
    assert state(rig)["budget"] == 1


def test_uncooperative_subprocess_signed_actor_spoof_is_denied(fenced):
    rig, gate = fenced
    assert activate(rig, gate)
    # The child receives only public routing identifiers and a synthetic task string.
    # It has no access to the independently pinned destination signing secret.
    root = __import__('pathlib').Path(__file__).resolve().parents[1]
    env = {**os.environ, 'PYTHONPATH': str(root / 'src') + os.pathsep + os.environ.get('PYTHONPATH', '')}
    script = (
        'import json\n'
        'from agent_movement.trust import HmacKey, seal\n'
        'key = HmacKey.generate("b")\n'
        'payload = {"type": "guarded-effect-invocation", "task_id": "task-1", '
        '"movement_id": "movement-1", "destination_id": "agent-b", '
        '"owner_epoch": 2, "activation_id": "activation-1", "effect_id": "effect-1", '
        '"payload_sha256": "f"*64, "nonce": "spoof-1", '
        '"issued_at": 1800000000, "expires_at": 1800000100}\n'
        'print(json.dumps(seal("guarded-effect-invocation", payload, key)))\n'
    )
    child = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True,
                           check=True, timeout=15, env=env)
    forged = json.loads(child.stdout)
    assert forged['kid'] == rig.dest_key.kid
    with pytest.raises(PolicyDenied):
        gate.commit('task-1', 'movement-1', 'agent-b', 2, 'effect-1', 'safe',
                    signed_execution=forged)
    assert state(rig)['effects'] == []

def _revoke_child(rig, start, outcome):
    start.wait(5)
    try:
        rig.revoke("data-owner")
        outcome.put("revoked")
    except Exception as exc:
        outcome.put(type(exc).__name__)


@pytest.mark.skipif(sys.platform != "linux", reason="requires Linux fork semantics")
def test_separate_python_process_revocation_race_is_linearizable(fenced):
    rig, gate = fenced
    ctx = multiprocessing.get_context("fork")
    start = ctx.Event()
    result = ctx.Queue()
    child = ctx.Process(target=_revoke_child, args=(rig, start, result))
    child.start()
    start.set()
    try:
        gate.activate(activation_ack(rig))
    except PolicyDenied:
        pass  # revocation committed first
    child.join(10)
    assert not child.is_alive()
    assert child.exitcode == 0
    assert result.get(timeout=2) == "revoked"
    # Even when activation commits first, future protected effects must fail
    # after the independently signed revocation commits.
    with pytest.raises(PolicyDenied):
        authorized_commit(rig, gate, "task-1", "movement-1", "agent-b", 2, "effect-1", "safe")
    assert state(rig)["effects"] == []
    assert state(rig)["budget"] == 0
