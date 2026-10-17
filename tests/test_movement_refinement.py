"""Bounded empirical model/refinement regression tests. No real-world effects."""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from agent_movement.core import (
    Approval, ApprovalRevoked, EffectGateway, HandoffReceiver, SQLiteStore,
)
from agent_movement.trust import HmacKey, issue_revocation
from movement_modelcheck import State
from movement_refinement import abstract_traces, envelope, expected, observe, replay_trace, run_suite


def test_all_reachable_supported_traces():
    paths = abstract_traces()
    assert len(paths) >= 40
    assert len(paths) == len(set(paths))
    report = run_suite()
    assert report["traces"] == len(paths)
    assert report["covered"]["atomic_fence_and_transfer"]
    assert report["covered"]["protected_effect_commit"]
    assert report["covered"]["signed_revocation"]
    for name in (
        "stale_origin_denied", "stale_transfer_denied", "post_revocation_denied",
        "stable_id_replay_deduplicated", "payload_collision_denied",
    ):
        assert report["negative_probes"][name] > 0
    assert "network partitions and runtime crashes" in report["excluded"]


def test_cross_epoch_effects_revoke_after_commit():
    result = replay_trace((
        "commit_A_effect-1", "prepare_destination",
        "issue_separate_destination_grant", "atomic_fence_and_transfer",
        "resume_destination", "commit_B_effect-2", "revoke_authority",
    ))
    assert result["final"] == (
        "agent-b", 2, (("effect-1", 1), ("effect-2", 2)), True
    )
    assert result["probes"]["revoked_replay_denied"]
    assert result["covered"]["abstract_only:issue_separate_destination_grant"]


@pytest.mark.parametrize("action", ["partition_gateway", "crash_A", "unsafe_stale_A_effect"])
def test_nonmapped_model_actions_refused(action):
    with pytest.raises(ValueError, match="unsupported or non-enabled"):
        replay_trace((action,))


def test_independent_observer_detects_db_tamper(tmp_path):
    path = tmp_path / "tamper.sqlite"
    gateway = EffectGateway(SQLiteStore(path))
    assert gateway.claim("task-1", "agent-a") == 1
    assert observe(path) == expected(State())
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO effects VALUES(?,?,?,?)", (
            "task-1", "unmediated-effect", "0" * 64, 1,
        ))
    assert observe(path) != expected(State())


def test_transfer_revoked_approval_mismatch_is_documented(tmp_path):
    """Core transfer CAS is not a complete policy-mediated movement operation."""
    store = SQLiteStore(tmp_path / "revoked.sqlite")
    issuer = HmacKey.generate("operator")
    receiver = HandoffReceiver(
        "agent-b", store,
        [Approval("approval-1", "task-1", "agent-a", "agent-b", "word_count")],
        revocation_authorities=[issuer],
    )
    assert not receiver.receive(envelope())["replayed"]
    gateway = EffectGateway(store)
    assert gateway.claim("task-1", "agent-a") == 1
    receiver.revoke(issue_revocation(issuer, "approval-1", 1_792_000_000))
    assert gateway.transfer("task-1", "agent-a", 1, "agent-b") == 2
    with pytest.raises(ApprovalRevoked):
        gateway.commit("task-1", "agent-b", 2, "effect-1", "synthetic")
    assert gateway.reconcile("task-1", "effect-1") == "unknown"


def test_stale_worker_fenced_across_process_reopen(tmp_path):
    path = tmp_path / "two-process.sqlite"
    gateway = EffectGateway(SQLiteStore(path))
    assert gateway.claim("task-1", "agent-a") == 1
    assert gateway.transfer("task-1", "agent-a", 1, "agent-b") == 2
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src") + os.pathsep + env.get("PYTHONPATH", "")
    code = (
        "import sys\n"
        "from agent_movement.core import EffectGateway, SQLiteStore, PolicyDenied\n"
        "try:\n"
        " g=EffectGateway(SQLiteStore(sys.argv[1]))\n"
        " x=g.commit('task-1',sys.argv[2],int(sys.argv[3]),'effect-2','synthetic:effect-2')\n"
        " print('committed' if x else 'replayed')\n"
        "except PolicyDenied:\n"
        " print('denied')\n"
    )
    def attempt(agent, epoch):
        process = subprocess.run(
            [sys.executable, "-c", code, str(path), agent, str(epoch)],
            capture_output=True, text=True, check=True, timeout=15, env=env,
        )
        return process.stdout.strip()
    assert attempt("agent-a", 1) == "denied"
    assert gateway.reconcile("task-1", "effect-2") == "unknown"
    assert attempt("agent-b", 2) == "committed"
    assert attempt("agent-b", 2) == "replayed"
    assert observe(path)[2] == (("effect-2", 2),)
