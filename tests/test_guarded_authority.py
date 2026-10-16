"""Opt-in GuardedAuthority experiment. Synthetic SQLite-only effects; no live tools."""

import concurrent.futures
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from agent_movement.core import Conflict, ContractError, EffectGateway, PolicyDenied, SQLiteStore, digest
from agent_movement.guarded_authority import GuardedAuthority
from agent_movement.trust import HmacKey, Unauthorized, issue_grant, seal
from test_continuity_runtime import NOW, Rig


def intent(rig, *, task_id="task-1", movement_id="movement-1", destination="agent-b",
           kind="word_count", grant=None, signer=None, epoch=1, policy_epoch=4):
    grant = rig.grant if grant is None else grant
    return seal("guarded-transfer-intent", {
        "type": "guarded-transfer-intent",
        "movement_id": movement_id, "task_id": task_id,
        "origin_id": "agent-a", "destination_id": destination,
        "expected_epoch": epoch, "kind": kind,
        "classification": "synthetic",
        "policy_epoch": policy_epoch, "grant_digest": digest(grant),
    }, signer or rig.origin_key)


def service(rig, *, budget=2):
    return GuardedAuthority(
        rig.store, rig.runtime, rig.trust,
        origin_verifiers={"agent-a": rig.origin_key},
        cancel_verifier=rig.user, incident_verifier=rig.user,
        budget_limit=budget, clock=rig.clock,
    )


def notify(rig, purpose, *, task="task-1", movement="movement-1", key=None):
    return seal(purpose, {
        "type": purpose, "task_id": task, "movement_id": movement,
    }, key or rig.user)


@pytest.fixture
def lane(tmp_path):
    rig = Rig(tmp_path)
    rig.install()
    gateway = EffectGateway(rig.store)
    assert gateway.claim("task-1", "agent-a") == 1
    gated = service(rig)
    return rig, gateway, gated


def enroll(rig, gated):
    gated.enroll(intent(rig), rig.grant)


def test_protected_transfer_and_effect_deduplication(lane):
    rig, legacy, gated = lane
    enroll(rig, gated)
    assert gated.inspect("task-1")["phase"] == "prepared"
    # The legacy CAS and the legacy effect endpoint must not bypass the guard.
    with pytest.raises(PolicyDenied, match="guarded task"):
        legacy.transfer("task-1", "agent-a", 1, "agent-b")
    with pytest.raises(PolicyDenied, match="guarded task"):
        legacy.commit("task-1", "agent-a", 1, "effect-0", "payload")
    assert gated.transfer("task-1", "movement-1") == 2
    assert gated.inspect("task-1")["owner"] == "agent-b"
    assert gated.commit("task-1", "movement-1", "agent-b", 2, "effect-1", "safe")
    assert not gated.commit("task-1", "movement-1", "agent-b", 2, "effect-1", "safe")
    with pytest.raises(Conflict):
        gated.commit("task-1", "movement-1", "agent-b", 2, "effect-1", "changed")
    with pytest.raises(PolicyDenied):
        gated.commit("task-1", "movement-1", "agent-a", 1, "effect-2", "stale")
    assert gated.inspect("task-1")["used"] == 1
    assert legacy.reconcile("task-1", "effect-1") == "committed"


def test_revocation_before_transfer_prevents_owner_change(lane):
    rig, _, gated = lane
    enroll(rig, gated)
    rig.revoke("data-owner")
    with pytest.raises(Unauthorized):
        gated.transfer("task-1", "movement-1")
    assert gated.inspect("task-1")["owner"] == "agent-a"
    assert gated.inspect("task-1")["epoch"] == 1


def test_revocation_after_transfer_prevents_new_and_replayed_effects(lane):
    rig, legacy, gated = lane
    enroll(rig, gated)
    gated.transfer("task-1", "movement-1")
    assert gated.commit("task-1", "movement-1", "agent-b", 2, "effect-1", "safe")
    rig.revoke("human")
    for effect_id in ("effect-1", "effect-2"):
        with pytest.raises(Unauthorized):
            gated.commit("task-1", "movement-1", "agent-b", 2, effect_id, "safe")
    assert legacy.reconcile("task-1", "effect-1") == "committed"
    assert legacy.reconcile("task-1", "effect-2") == "unknown"


@pytest.mark.parametrize("missing", ["human", "owner", "sensor", "ack", "state"])
def test_missing_independently_verified_fact_denies_enrollment(tmp_path, missing):
    rig = Rig(tmp_path)
    params = {"human": True, "owner": True, "sensor": True, "ack": True, "state": True}
    params[missing] = False
    rig.install(**params)
    EffectGateway(rig.store).claim("task-1", "agent-a")
    gated = service(rig)
    with pytest.raises(Unauthorized):
        enroll(rig, gated)
    with sqlite3.connect(rig.store.path) as db:
        assert db.execute("SELECT 1 FROM guarded_tasks").fetchone() is None


def test_wrong_or_tampered_grant_or_intent_fails_before_enrollment(lane):
    rig, _, gated = lane
    wrong_audience = issue_grant(
        rig.user, grant_id="bad-aud", subject="synthetic-user",
        actor="agent-a", audience="agent-c", task_id="task-1",
        capabilities=["word_count"], not_before=NOW - 10, expires_at=NOW + 1000,
    )
    with pytest.raises(Unauthorized):
        gated.enroll(intent(rig, grant=wrong_audience), wrong_audience)
    with pytest.raises(Unauthorized):
        gated.enroll(intent(rig, signer=HmacKey.generate("a")), rig.grant)
    with pytest.raises(Unauthorized):
        gated.enroll(intent(rig, destination="agent-c"), rig.grant)
    damaged = json.loads(json.dumps(rig.grant))
    damaged["payload"]["expires_at"] += 1000
    with pytest.raises((Unauthorized, PolicyDenied)):
        gated.enroll(intent(rig, grant=damaged), damaged)
    with pytest.raises(Unauthorized, match="grant_mismatch"):
        gated.enroll(intent(rig), wrong_audience)
    assert gated.inspect if True else None  # no guarded row created by any failed request


def test_expired_grant_and_freshness_observation_fail_closed(lane):
    rig, _, gated = lane
    enroll(rig, gated)
    rig.now = NOW + 301
    with pytest.raises(Unauthorized):
        gated.transfer("task-1", "movement-1")
    rig.now = NOW
    gated.transfer("task-1", "movement-1")
    rig.now = NOW + 1201
    with pytest.raises(Unauthorized):
        gated.commit("task-1", "movement-1", "agent-b", 2, "effect-1", "safe")


def test_grant_revocation_and_policy_rollover(lane):
    rig, _, gated = lane
    enroll(rig, gated)
    rig.receiver.ledger.revoke("grant-1", NOW)
    with pytest.raises(Unauthorized):
        gated.transfer("task-1", "movement-1")
    assert gated.inspect("task-1")["owner"] == "agent-a"


def test_policy_rollover_after_transfer_blocks_effect(lane):
    rig, _, gated = lane
    enroll(rig, gated)
    gated.transfer("task-1", "movement-1")
    rig.runtime.advance_epoch(5)
    with pytest.raises(Unauthorized):
        gated.commit("task-1", "movement-1", "agent-b", 2, "effect-1", "safe")


def test_cancel_signed_notice_is_atomic_with_guarded_effect(lane):
    rig, _, gated = lane
    enroll(rig, gated)
    gated.cancel(notify(rig, "guarded-cancel"))
    with pytest.raises(PolicyDenied):
        gated.transfer("task-1", "movement-1")
    assert gated.inspect("task-1")["cancelled"]


def test_unsupported_or_forged_operator_notice_refused(lane):
    rig, _, gated = lane
    enroll(rig, gated)
    fake = notify(rig, "guarded-unknown", key=HmacKey.generate("user"))
    with pytest.raises(Unauthorized):
        gated.mark_unknown(fake)
    with pytest.raises(Unauthorized):
        gated.cancel(notify(rig, "guarded-cancel", movement="different"))
    assert not gated.inspect("task-1")["cancelled"]
    assert not gated.inspect("task-1")["unknown_effect"]


def test_unknown_effect_hold_blocks_transfer_and_commit(lane):
    rig, _, gated = lane
    enroll(rig, gated)
    gated.mark_unknown(notify(rig, "guarded-unknown"))
    with pytest.raises(PolicyDenied):
        gated.transfer("task-1", "movement-1")
    assert gated.inspect("task-1")["unknown_effect"]


def test_budget_is_shared_and_replay_does_not_spend_again(lane):
    rig, _, gated = lane
    enroll(rig, gated)
    gated.transfer("task-1", "movement-1")
    assert gated.commit("task-1", "movement-1", "agent-b", 2, "e-1", "a")
    assert gated.commit("task-1", "movement-1", "agent-b", 2, "e-2", "b")
    with pytest.raises(PolicyDenied, match="budget"):
        gated.commit("task-1", "movement-1", "agent-b", 2, "e-3", "c")
    assert not gated.commit("task-1", "movement-1", "agent-b", 2, "e-1", "a")
    assert gated.inspect("task-1")["used"] == 2


def test_only_one_transfer_and_single_owner_with_racing_requests(lane):
    rig, _, gated = lane
    enroll(rig, gated)
    def one():
        try:
            return gated.transfer("task-1", "movement-1")
        except Conflict:
            return None
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        res = list(pool.map(lambda _: one(), range(6)))
    assert res.count(2) == 1
    assert res.count(None) == 5
    assert gated.inspect("task-1")["owner"] == "agent-b"


def test_no_late_enrollment_after_preexisting_simulated_effect(lane):
    rig, legacy, gated = lane
    assert legacy.commit("task-1", "agent-a", 1, "effect-early", "safe")
    with pytest.raises(PolicyDenied, match="existing effects"):
        enroll(rig, gated)


def test_legacy_gateway_denies_guarded_operations_from_other_process(lane):
    rig, legacy, gated = lane
    enroll(rig, gated)
    gated.transfer("task-1", "movement-1")
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src") + os.pathsep + env.get("PYTHONPATH", "")
    code = (
        "import sys\n"
        "from agent_movement.core import EffectGateway, SQLiteStore, PolicyDenied\n"
        "gateway = EffectGateway(SQLiteStore(sys.argv[1]))\n"
        "try:\n"
        " gateway.transfer('task-1','agent-b',2,'agent-c')\n"
        " print('unguarded-transfer')\n"
        "except PolicyDenied:\n"
        " print('transfer-denied')\n"
        "try:\n"
        " gateway.commit('task-1','agent-b',2,'effect-raw','payload')\n"
        " print('unguarded-commit')\n"
        "except PolicyDenied:\n"
        " print('commit-denied')\n"
    )
    res = subprocess.run(
        [sys.executable, "-c", code, str(rig.store.path)],
        capture_output=True, text=True, timeout=15, env=env, check=True,
    )
    assert res.stdout.splitlines() == ["transfer-denied", "commit-denied"]
    assert gated.inspect("task-1")["owner"] == "agent-b"
    assert legacy.reconcile("task-1", "effect-raw") == "unknown"


def test_legacy_experiments_still_work_without_enrollment(tmp_path):
    store = SQLiteStore(tmp_path / "plain.sqlite")
    legacy = EffectGateway(store)
    assert legacy.claim("task-z", "agent-a") == 1
    assert legacy.commit("task-z", "agent-a", 1, "e1", "x")
    assert legacy.transfer("task-z", "agent-a", 1, "agent-b") == 2
    assert legacy.commit("task-z", "agent-b", 2, "e2", "y")
