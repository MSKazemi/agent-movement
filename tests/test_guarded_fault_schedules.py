"""Issue #93: bounded, reproducible SQLite fault schedules for guarded movement.

This tests a trusted one-store synthetic receiver, NOT network consensus, remote
worker liveness, genuine partitions, or externally irreversible side effects.
"""

from __future__ import annotations

import concurrent.futures
import json
import multiprocessing
import sqlite3
import sys
import time
from pathlib import Path

import pytest

from agent_movement.core import EffectGateway, PolicyDenied
from agent_movement.trust import Unauthorized
from test_continuity_runtime import NOW, Rig
from test_guarded_authority import activation_ack, authorized_commit, intent, notify, service

PLAN = Path(__file__).resolve().parents[1] / "data" / "guarded-fault-schedules-v01.json"
CASES = json.loads(PLAN.read_text(encoding="utf-8"))["cases"]


def _lab(tmp_path):
    rig = Rig(tmp_path)
    rig.install()
    assert EffectGateway(rig.store).claim("task-1", "agent-a") == 1
    return rig, service(rig)


def _snapshot(path: Path) -> dict[str, object]:
    """A fresh, independent SQLite reader, never the gateway's inspect method."""
    with sqlite3.connect(path, timeout=5) as db:
        owner = db.execute(
            "SELECT agent_id,epoch FROM owners WHERE task_id='task-1'"
        ).fetchone()
        guard = db.execute(
            "SELECT status,budget_used,cancelled,unknown_effect "
            "FROM guarded_tasks WHERE task_id='task-1'"
        ).fetchone()
        effects = db.execute(
            "SELECT effect_id,epoch FROM effects WHERE task_id='task-1' ORDER BY effect_id"
        ).fetchall()
        return {
            "owner": tuple(owner) if owner else None,
            "guard": tuple(guard) if guard else None,
            "effects": tuple(tuple(row) for row in effects),
        }


def _execute_step(rig, gate, step: str) -> None:
    if step == "enroll":
        gate.enroll(intent(rig), rig.grant)
    elif step == "transfer":
        assert gate.transfer("task-1", "movement-1") == 2
    elif step == "activate":
        assert gate.activate(activation_ack(rig)) is True
    elif step == "revoke_data_owner":
        rig.revoke("data-owner")
    elif step == "cancel":
        gate.cancel(notify(rig, "guarded-cancel"))
    elif step == "mark_unknown":
        gate.mark_unknown(notify(rig, "guarded-unknown"))
    elif step == "bump_policy_epoch":
        rig.runtime.advance_epoch(5)
    elif step == "advance_expired_clock":
        rig.now = NOW + 1201
    else:
        raise AssertionError("unreviewed fault-schedule operation: " + step)


def test_frozen_fault_plan_declares_only_supported_runtime_events():
    full = json.loads(PLAN.read_text(encoding="utf-8"))
    assert full["schema"] == "amv-guarded-fault-schedule/v0.1"
    assert full["seed"] == "guarded-sqlite-faults-2026-10-17"
    assert len(full["cases"]) == 7
    assert [c["id"] for c in full["cases"]] == [
        "F01-fenced-denial", "F02-revoked-data-owner", "F03-cancelled",
        "F04-unknown-effect-hold", "F05-policy-rollover",
        "F06-expired-grant", "F07-validated-active",
    ]
    assert all(c["steps"][:2] == ["enroll", "transfer"] for c in full["cases"])
    assert all(c["expected"] in {"committed", "denied"} for c in full["cases"])
    assert all(isinstance(text, str) for text in full["unsupported"])
    assert "SECRET-CANARY" not in PLAN.read_text(encoding="utf-8")


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_real_guarded_effect_refines_each_frozen_fault_schedule(tmp_path, case):
    rig, gate = _lab(tmp_path)
    for step in case["steps"]:
        before = _snapshot(rig.store.path)
        _execute_step(rig, gate, step)
        after = _snapshot(rig.store.path)
        assert not after["effects"], (case["id"], step)
        assert before != after or step == "enroll", (case["id"], step)
    prior = _snapshot(rig.store.path)
    if case["expected"] == "committed":
        assert authorized_commit(
            rig, gate, "task-1", "movement-1", "agent-b", 2, "effect-1", "synthetic"
        ) is True
        after = _snapshot(rig.store.path)
        assert after["effects"] == (("effect-1", 2),)
        assert after["guard"][1] == 1
    else:
        with pytest.raises((PolicyDenied, Unauthorized)):
            authorized_commit(
                rig, gate, "task-1", "movement-1", "agent-b", 2, "effect-1", "synthetic"
            )
        assert _snapshot(rig.store.path) == prior, case["id"]


def _lock_writer(path: str, ready, release) -> None:
    with sqlite3.connect(path, timeout=5, isolation_level=None) as db:
        db.execute("BEGIN IMMEDIATE")
        ready.set()
        if not release.wait(8):
            db.rollback()
            raise RuntimeError("trusted fault injector timed out")
        db.commit()


@pytest.mark.skipif(sys.platform != "linux", reason="Linux multiprocessing fork fault schedule")
def test_cross_process_write_partition_keeps_destination_fenced_until_recovery(tmp_path):
    """A separate writer holds the authority lock; no effect may commit during it."""
    rig, gate = _lab(tmp_path)
    gate.enroll(intent(rig), rig.grant)
    gate.transfer("task-1", "movement-1")
    ctx = multiprocessing.get_context("fork")
    ready, release = ctx.Event(), ctx.Event()
    child = ctx.Process(target=_lock_writer, args=(str(rig.store.path), ready, release))
    child.start()
    try:
        assert ready.wait(5), "fault injector did not acquire the SQLite write lock"
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(gate.activate, activation_ack(rig))
            time.sleep(0.15)  # The write lock, not a Python stub, forces serialization.
            assert not future.done()
            assert _snapshot(rig.store.path)["guard"][0] == "fenced"
            assert _snapshot(rig.store.path)["effects"] == ()
            release.set()
            assert future.result(timeout=12) is True
    finally:
        release.set()
        child.join(10)
        if child.is_alive():
            child.terminate()
            child.join(3)
    assert child.exitcode == 0
    assert _snapshot(rig.store.path)["guard"][0] == "active"
    assert authorized_commit(
        rig, gate, "task-1", "movement-1", "agent-b", 2, "effect-1", "synthetic"
    )
    assert _snapshot(rig.store.path)["effects"] == (("effect-1", 2),)


def _revoke_writer(rig, signal, result) -> None:
    if not signal.wait(5):
        result.put("no_signal")
        return
    try:
        rig.revoke("data-owner")  # trusted separately signed principal notice
        result.put("revoked")
    except Exception as exc:
        result.put(type(exc).__name__)


@pytest.mark.skipif(sys.platform != "linux", reason="Linux multiprocessing fork fault schedule")
def test_transfer_races_signed_revocation_without_unauthorized_effect(tmp_path):
    rig, gate = _lab(tmp_path)
    gate.enroll(intent(rig), rig.grant)
    ctx = multiprocessing.get_context("fork")
    go, result = ctx.Event(), ctx.Queue()
    child = ctx.Process(target=_revoke_writer, args=(rig, go, result))
    child.start()
    go.set()
    try:
        try:
            transferred = gate.transfer("task-1", "movement-1") == 2
        except PolicyDenied:
            transferred = False
        child.join(10)
        assert not child.is_alive()
        assert child.exitcode == 0
        assert result.get(timeout=2) == "revoked"
        if transferred:
            assert _snapshot(rig.store.path)["owner"] == ("agent-b", 2)
            with pytest.raises((PolicyDenied, Unauthorized)):
                gate.activate(activation_ack(rig))
        else:
            assert _snapshot(rig.store.path)["owner"] == ("agent-a", 1)
        assert _snapshot(rig.store.path)["effects"] == ()
        assert _snapshot(rig.store.path)["guard"][1] == 0
    finally:
        if child.is_alive():
            child.terminate()
            child.join(3)
