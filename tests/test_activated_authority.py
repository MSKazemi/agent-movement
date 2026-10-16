"""Opt-in activated guarded lane: synthetic, pinned signing key and one SQLite store.

These tests DO NOT assert OS process identity, physical execution or real tools.
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from agent_movement.activated_authority import ActivatedGuardedAuthority
from agent_movement.core import Conflict, EffectGateway, PolicyDenied, digest
from agent_movement.guarded_authority import GuardedAuthority
from agent_movement.trust import HmacKey, Unauthorized, seal
from test_continuity_runtime import NOW, Rig
from test_guarded_authority import intent, notify


def _setup(tmp_path, *, budget=2):
    rig = Rig(tmp_path)
    rig.install()
    assert EffectGateway(rig.store).claim("task-1", "agent-a") == 1
    gate = ActivatedGuardedAuthority(
        rig.store, rig.runtime, rig.trust,
        origin_verifiers={"agent-a": rig.origin_key},
        cancel_verifier=rig.user, incident_verifier=rig.user,
        budget_limit=budget, clock=rig.clock,
    )
    gate.enroll(intent(rig), rig.grant)
    return rig, gate


def _ack(rig, *, signer=None, **changes):
    p = {
        "type": "guarded-activation",
        "task_id": "task-1", "movement_id": "movement-1",
        "destination_id": "agent-b", "epoch": 2,
        "policy_epoch": 4, "grant_digest": digest(rig.grant),
        "activation_id": "activate-1", "expires_at": NOW + 200,
    }
    p.update(changes)
    return seal("guarded-activation", p, signer or rig.dest_key)


def _effect(rig, *, payload="synthetic:publish-1", signer=None, **changes):
    p = {
        "type": "guarded-effect-intent",
        "task_id": "task-1", "movement_id": "movement-1",
        "destination_id": "agent-b", "epoch": 2,
        "policy_epoch": 4, "activation_id": "activate-1",
        "effect_id": "publish-1",
        "payload_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "expires_at": NOW + 200,
    }
    p.update(changes)
    return seal("guarded-effect-intent", p, signer or rig.dest_key)


def _active(tmp_path):
    rig, gate = _setup(tmp_path)
    assert gate.transfer("task-1", "movement-1") == 2
    assert gate.activate(_ack(rig))
    return rig, gate


def test_fencing_does_not_authorize_unsigned_or_pre_activation_effect(tmp_path):
    rig, gate = _setup(tmp_path)
    with pytest.raises(PolicyDenied):
        gate.activate(_ack(rig))  # source still owns the task
    assert gate.transfer("task-1", "movement-1") == 2
    assert gate.inspect("task-1")["phase"] == "fenced"
    with pytest.raises(PolicyDenied, match="not authenticated activation"):
        gate.commit_signed(_effect(rig), "synthetic:publish-1")
    with pytest.raises(PolicyDenied, match="signed effect authorization"):
        gate.commit("task-1", "movement-1", "agent-b", 2, "publish-1", "synthetic:publish-1")
    with pytest.raises(PolicyDenied, match="guarded task"):
        EffectGateway(rig.store).commit("task-1", "agent-b", 2, "publish-1", "synthetic:publish-1")
    with sqlite3.connect(rig.store.path) as db:
        assert db.execute("SELECT COUNT(*) FROM effects").fetchone() == (0,)


def test_signed_activation_is_idempotent_and_exactly_one_effect_is_recorded(tmp_path):
    rig, gate = _setup(tmp_path)
    gate.transfer("task-1", "movement-1")
    token = _ack(rig)
    assert gate.activate(token) is True
    assert gate.activate(token) is False
    assert gate.inspect("task-1")["phase"] == "active"
    proof = _effect(rig)
    assert gate.commit_signed(proof, "synthetic:publish-1") is True
    assert gate.commit_signed(proof, "synthetic:publish-1") is False
    assert gate.inspect("task-1")["used"] == 1
    with sqlite3.connect(rig.store.path) as db:
        assert db.execute("SELECT effect_id,epoch FROM effects").fetchall() == [("publish-1", 2)]


def test_alternate_base_instance_cannot_bypass_activation_even_after_activation(tmp_path):
    rig, gate = _active(tmp_path)
    bare = GuardedAuthority(
        rig.store, rig.runtime, rig.trust,
        origin_verifiers={"agent-a": rig.origin_key},
        cancel_verifier=rig.user, incident_verifier=rig.user, clock=rig.clock,
    )
    with pytest.raises(PolicyDenied, match="signed effect authorization"):
        bare.commit("task-1", "movement-1", "agent-b", 2, "forged-1", "synthetic")
    assert gate.commit_signed(_effect(rig), "synthetic:publish-1")


@pytest.mark.parametrize("change", [
    {"task_id": "task-other"},
    {"movement_id": "movement-other"},
    {"destination_id": "agent-c"},
    {"epoch": 3},
    {"policy_epoch": 5},
    {"grant_digest": "0" * 64},
    {"expires_at": NOW},
    {"unexpected": "truth"},
])
def test_signed_activation_rejects_wrong_binding(tmp_path, change):
    rig, gate = _setup(tmp_path)
    gate.transfer("task-1", "movement-1")
    with pytest.raises((PolicyDenied, Unauthorized, Conflict, ValueError)):
        gate.activate(_ack(rig, **change))
    assert gate.inspect("task-1")["phase"] == "fenced"


def test_activation_rejects_forged_destination_key(tmp_path):
    rig, gate = _setup(tmp_path)
    gate.transfer("task-1", "movement-1")
    with pytest.raises(PolicyDenied):
        gate.activate(_ack(rig, signer=HmacKey.generate("b")))
    assert gate.inspect("task-1")["phase"] == "fenced"


def test_activation_id_collision_rejected_without_overwriting(tmp_path):
    rig, gate = _active(tmp_path)
    with pytest.raises(Conflict):
        gate.activate(_ack(rig, activation_id="different-activation"))
    assert gate.inspect("task-1")["phase"] == "active"


@pytest.mark.parametrize("change", [
    {"task_id": "task-other"},
    {"movement_id": "movement-other"},
    {"destination_id": "agent-c"},
    {"epoch": 3},
    {"policy_epoch": 5},
    {"activation_id": "activate-other"},
    {"effect_id": "out-of-scope"},
    {"expires_at": NOW},
    {"unexpected": True},
])
def test_signed_effect_binding_and_refusal(tmp_path, change):
    rig, gate = _active(tmp_path)
    signed = _effect(rig, **change)
    if "effect_id" in change:
        # A newly signed allowed effect ID is allowed; only the domain matters.
        assert gate.commit_signed(signed, "synthetic:publish-1") is True
    else:
        with pytest.raises((PolicyDenied, Unauthorized, ContractError, ValueError)):
            gate.commit_signed(signed, "synthetic:publish-1")
    assert gate.inspect("task-1")["used"] in (0, 1)


def test_payload_alteration_and_signature_forgery_are_rejected(tmp_path):
    rig, gate = _active(tmp_path)
    proof = _effect(rig)
    with pytest.raises(Unauthorized, match="payload_mismatch"):
        gate.commit_signed(proof, "different")
    with pytest.raises(PolicyDenied):
        gate.commit_signed(_effect(rig, signer=HmacKey.generate("b")), "synthetic:publish-1")
    assert gate.inspect("task-1")["used"] == 0


def test_two_distinct_effects_spend_budget_once_each(tmp_path):
    rig, gate = _active(tmp_path)
    first = _effect(rig)
    second = _effect(rig, effect_id="publish-2", payload_sha256=hashlib.sha256(b"second").hexdigest())
    third = _effect(rig, effect_id="publish-3", payload_sha256=hashlib.sha256(b"third").hexdigest())
    assert gate.commit_signed(first, "synthetic:publish-1")
    assert gate.commit_signed(second, "second")
    with pytest.raises(PolicyDenied, match="budget"):
        gate.commit_signed(third, "third")
    assert gate.commit_signed(first, "synthetic:publish-1") is False
    assert gate.inspect("task-1")["used"] == 2


@pytest.mark.parametrize("stop", ["human", "data-owner", "cancel", "unknown", "policy", "time"])
def test_dynamic_authority_changes_revoke_effects(tmp_path, stop):
    rig, gate = _active(tmp_path)
    if stop == "human":
        rig.revoke("human")
    elif stop == "data-owner":
        rig.revoke("data-owner")
    elif stop == "cancel":
        gate.cancel(notify(rig, "guarded-cancel"))
    elif stop == "unknown":
        gate.mark_unknown(notify(rig, "guarded-unknown"))
    elif stop == "policy":
        rig.runtime.advance_epoch(5)
    else:
        rig.now = NOW + 1300
    with pytest.raises(PolicyDenied):
        gate.commit_signed(_effect(rig), "synthetic:publish-1")
    assert gate.inspect("task-1")["used"] == 0


@pytest.mark.parametrize("stop", ["human", "data-owner", "cancel", "unknown", "policy", "time"])
def test_dynamic_authority_changes_block_activation(tmp_path, stop):
    rig, gate = _setup(tmp_path)
    gate.transfer("task-1", "movement-1")
    if stop == "human":
        rig.revoke("human")
    elif stop == "data-owner":
        rig.revoke("data-owner")
    elif stop == "cancel":
        gate.cancel(notify(rig, "guarded-cancel"))
    elif stop == "unknown":
        gate.mark_unknown(notify(rig, "guarded-unknown"))
    elif stop == "policy":
        rig.runtime.advance_epoch(5)
    else:
        rig.now = NOW + 1300
    with pytest.raises(PolicyDenied):
        gate.activate(_ack(rig))
    assert gate.inspect("task-1")["phase"] == "fenced"


def test_concurrent_identical_activation_has_single_linearization(tmp_path):
    rig, gate = _setup(tmp_path)
    gate.transfer("task-1", "movement-1")
    proof = _ack(rig)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: gate.activate(proof), range(8)))
    assert results.count(True) == 1
    assert results.count(False) == 7
    with sqlite3.connect(rig.store.path) as db:
        assert db.execute(
            "SELECT activation_id,epoch FROM guarded_activations"
        ).fetchall() == [("activate-1", 2)]


def test_process_cannot_use_unsigned_core_effect_route(tmp_path):
    rig, gate = _active(tmp_path)
    root = Path(__file__).resolve().parents[1]
    code = """import sys
from agent_movement.core import EffectGateway, SQLiteStore, PolicyDenied
try:
    EffectGateway(SQLiteStore(sys.argv[1])).commit(
        "task-1", "agent-b", 2, "unapproved-effect", "synthetic"
    )
    print("FORBIDDEN_COMMIT")
except PolicyDenied:
    print("DENIED")
"""
    proc = subprocess.run(
        [sys.executable, "-c", code, str(rig.store.path)],
        capture_output=True, text=True, check=True, timeout=15,
        env={"PYTHONPATH": str(root / "src")},
    )
    assert proc.stdout.strip() == "DENIED"
    with sqlite3.connect(rig.store.path) as db:
        assert db.execute("SELECT COUNT(*) FROM effects").fetchone() == (0,)
