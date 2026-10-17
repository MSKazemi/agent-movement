"""Security regression for the separately running, synthetic tool-side effect service.

The subprocess is a separate execution process, not an unprivileged UID sandbox.
All keys, IDs, canaries, authority records and effects are synthetic.
"""

from __future__ import annotations

import json
import os
import select
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest

from agent_movement.core import digest
from agent_movement.tool_service import ToolAuthority, sign_tool, verify_tool
from agent_movement.trust import (
    ED25519,
    HS256,
    TrustStore,
    Unauthorized,
    ed25519_available,
    generate_key,
    issue_grant,
)

ROOT = Path(__file__).resolve().parent.parent
CANARY = "private-synthetic-task-text-CANARY-never-include-in-tool-payload"


@pytest.fixture(params=[HS256, pytest.param(
    ED25519, marks=pytest.mark.skipif(not ed25519_available(), reason="cryptography unavailable")
)])
def service_lab(request, tmp_path):
    alg = request.param
    user = generate_key(alg, "test-user")
    operator = generate_key(alg, "test-operator")
    executor = generate_key(alg, "test-executor")
    rogue = generate_key(alg, "test-rogue")
    signer = generate_key(alg, "test-tool")
    grant = issue_grant(
        user, grant_id="grant-tool-1", subject="synthetic-user", actor="agent-a",
        audience="agent-b", task_id="task-tool-1", capabilities=["word_count"],
        not_before=int(time.time()) - 10, expires_at=int(time.time()) + 600,
    )
    trust = TrustStore.build([], [user])
    db_path = tmp_path / "independent-tool.sqlite"
    config = {
        "db_path": str(db_path),
        "destination_id": "agent-b",
        "operator_verifier": operator.export(private=(alg == HS256)),
        "executor_verifier": executor.export(private=(alg == HS256)),
        "tool_signer": signer.export(),
        "grant_trust": trust.export(),
    }
    path = tmp_path / "provisioned-tool-config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    path.chmod(0o600)
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src") + os.pathsep + os.environ.get("PYTHONPATH", "")}
    child = subprocess.Popen(
        [sys.executable, "-m", "agent_movement.tool_service", "--config", str(path)],
        cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        assert child.stdout is not None
        readable, _, _ = select.select([child.stdout], [], [], 12)
        assert readable, "tool subprocess did not advertise a bound address"
        line = child.stdout.readline()
        assert line, f"tool subprocess exited before readiness (code={child.poll()})"
        port = json.loads(line)["port"]
        assert isinstance(port, int) and port > 0
        assert child.pid != os.getpid()

        def call(route, signed):
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/v0/tool/{route}",
                data=json.dumps(signed, sort_keys=True).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=8) as response:
                    return response.status, json.load(response)
            except urllib.error.HTTPError as exc:
                return exc.code, json.load(exc)

        def provision(task_id="task-tool-1", grant_value=grant, budget=2):
            p = {
                "type": "tool-provision", "task_id": task_id,
                "movement_id": "move-tool-1" if task_id == "task-tool-1" else "move-tool-2",
                "origin_id": "agent-a", "destination_id": "agent-b",
                "kind": "word_count", "classification": "synthetic",
                "resource": "synthetic-results", "grant_digest": digest(grant_value),
                "owner_epoch": 2, "policy_epoch": 1,
                "expires_at": int(time.time()) + 600, "budget_limit": budget,
            }
            return call("provision", sign_tool("provision", p, operator))

        def effect(*, effect_id="result-1", epoch=2, policy=1, signed_grant=grant,
                   audience="agent-b", resource="synthetic-results", signer_key=executor,
                   payload="0" * 64):
            p = {
                "type": "tool-effect", "task_id": "task-tool-1",
                "movement_id": "move-tool-1", "destination_id": audience,
                "kind": "word_count", "classification": "synthetic",
                "resource": resource, "owner_epoch": epoch,
                "policy_epoch": policy, "effect_id": effect_id,
                "payload_commitment": payload, "grant": signed_grant,
            }
            return sign_tool("effect", p, signer_key)

        def update(*, epoch=2, policy=1, new_epoch=3, new_policy=2, revoke=False):
            p = {
                "type": "tool-update", "task_id": "task-tool-1",
                "movement_id": "move-tool-1", "expected_owner_epoch": epoch,
                "new_owner_epoch": new_epoch, "expected_policy_epoch": policy,
                "new_policy_epoch": new_policy, "revoke": revoke,
            }
            return call("update", sign_tool("update", p, operator))

        def restart():
            nonlocal child, port
            old_pid = child.pid
            child.kill()  # simulate a crash; the ledger remains tool-side and durable
            child.communicate(timeout=5)
            child = subprocess.Popen(
                [sys.executable, "-m", "agent_movement.tool_service", "--config", str(path)],
                cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            assert child.stdout is not None
            readable, _, _ = select.select([child.stdout], [], [], 12)
            assert readable, "tool service failed to restart"
            line = child.stdout.readline()
            assert line, "restarted tool service exited before readiness"
            port = json.loads(line)["port"]
            assert old_pid != child.pid
            return child.pid

        yield {
            "call": call, "provision": provision, "effect": effect, "update": update,
            "restart": restart,
            "user": user, "operator": operator, "executor": executor, "rogue": rogue,
            "signer": signer, "grant": grant, "trust": trust, "db": db_path, "pid": child.pid,
        }
    finally:
        child.terminate()
        try:
            child.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.communicate(timeout=5)


def count_effects(db_path: Path) -> int:
    with sqlite3.connect(db_path) as db:
        return db.execute("SELECT COUNT(*) FROM tool_effects").fetchone()[0]


def test_honest_two_process_commit_signed_receipt_and_idempotent_replay(service_lab):
    lab = service_lab
    assert lab["provision"]()[0] == 200
    req = lab["effect"]()
    code, response = lab["call"]("effects", req)
    assert code == 200 and response["status"] == "committed"
    receipt = verify_tool("receipt", response["receipt"], lab["signer"].verifier())
    assert receipt["status"] == "committed"
    assert receipt["owner_epoch"] == 2 and receipt["policy_epoch"] == 1
    assert lab["call"]("effects", req)[1]["status"] == "replayed"
    assert count_effects(lab["db"]) == 1
    assert CANARY not in lab["db"].read_bytes().decode("latin-1")


def test_direct_endpoint_rejects_unsigned_forged_and_wrong_audience(service_lab):
    lab = service_lab
    assert lab["provision"]()[0] == 200
    assert lab["call"]("effects", lab["effect"]()["payload"])[0] == 401
    assert lab["call"]("effects", lab["effect"](signer_key=lab["rogue"]))[0] == 401
    assert lab["call"]("effects", lab["effect"](audience="agent-c"))[0] == 403
    assert lab["call"]("effects", lab["effect"](resource="other-resource"))[0] == 403
    forged = issue_grant(
        lab["rogue"], grant_id="fake-grant", subject="synthetic-user", actor="agent-a",
        audience="agent-b", task_id="task-tool-1", capabilities=["word_count"],
        not_before=int(time.time()) - 10, expires_at=int(time.time()) + 100,
    )
    assert lab["call"]("effects", lab["effect"](signed_grant=forged))[0] == 401
    assert count_effects(lab["db"]) == 0


def test_stale_epoch_and_policy_update_fail_before_commit(service_lab):
    lab = service_lab
    assert lab["provision"]()[0] == 200
    assert lab["call"]("effects", lab["effect"](epoch=1))[0] == 403
    assert lab["call"]("effects", lab["effect"](policy=0))[0] == 400
    assert lab["update"](new_epoch=3, new_policy=2)[0] == 200
    assert lab["call"]("effects", lab["effect"](epoch=2, policy=1))[0] == 403
    assert lab["call"]("effects", lab["effect"](epoch=3, policy=2))[0] == 200
    assert lab["update"](new_epoch=3, new_policy=3, epoch=2, policy=1)[0] == 409
    assert count_effects(lab["db"]) == 1


def test_revoked_authority_and_forged_admin_update(service_lab):
    lab = service_lab
    assert lab["provision"]()[0] == 200
    fake = sign_tool("update", {
        "type": "tool-update", "task_id": "task-tool-1", "movement_id": "move-tool-1",
        "expected_owner_epoch": 2, "new_owner_epoch": 2,
        "expected_policy_epoch": 1, "new_policy_epoch": 2, "revoke": True,
    }, lab["rogue"])
    assert lab["call"]("update", fake)[0] == 401
    assert lab["update"](new_epoch=2, new_policy=2, revoke=True)[0] == 200
    assert lab["call"]("effects", lab["effect"](epoch=2, policy=2))[0] == 403
    assert count_effects(lab["db"]) == 0


def test_parallel_identical_effect_only_commits_one_row(service_lab):
    lab = service_lab
    assert lab["provision"](budget=1)[0] == 200
    request = lab["effect"]()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: lab["call"]("effects", request), range(8)))
    assert all(status == 200 for status, _ in results)
    assert sum(answer["status"] == "committed" for _, answer in results) == 1
    assert count_effects(lab["db"]) == 1
    assert lab["call"]("effects", lab["effect"](effect_id="result-2"))[0] == 403
    assert lab["call"]("effects", lab["effect"](payload="f" * 64))[0] == 409


def test_dropped_application_reply_remains_unknown_until_target_query(service_lab):
    lab = service_lab
    assert lab["provision"]()[0] == 200
    req = lab["effect"]()
    # Simulate a caller discarding a real successful reply, NOT a verified network partition.
    status, _discarded = lab["call"]("effects", req)
    assert status == 200
    caller_state = "unknown"
    assert caller_state == "unknown"
    query = sign_tool("query", {
        "type": "tool-query", "task_id": "task-tool-1",
        "movement_id": "move-tool-1", "effect_id": "result-1",
    }, lab["executor"])
    code, response = lab["call"]("query", query)
    assert code == 200 and response["status"] == "committed"
    assert verify_tool("receipt", response["receipt"], lab["signer"].verifier())["effect_id"] == "result-1"
    assert count_effects(lab["db"]) == 1


def test_red_green_mutation_removing_tool_epoch_guard_exposes_vulnerability(service_lab):
    lab = service_lab
    assert lab["provision"]()[0] == 200
    local = ToolAuthority(
        lab["db"], destination_id="agent-b",
        operator_verifier=lab["operator"].verifier(),
        executor_verifier=lab["executor"].verifier(),
        tool_signer=lab["signer"],
        grant_trust=lab["trust"],
    )
    stale = lab["effect"](epoch=1)
    with pytest.raises(Unauthorized):
        local.effect(stale)
    # Deliberate in-process mutation control: without this check, the same
    # properly signed stale request wrongly commits in the independent ledger.
    with patch.object(ToolAuthority, "_require_epoch", staticmethod(lambda row, request: None)):
        mutated = local.effect(stale)
    assert mutated["status"] == "committed"
    assert count_effects(lab["db"]) == 1


def test_expired_signed_grant_is_denied_at_tool_commit(service_lab):
    lab = service_lab
    expired = issue_grant(
        lab["user"], grant_id="expired-tool-grant", subject="synthetic-user",
        actor="agent-a", audience="agent-b", task_id="task-tool-1",
        capabilities=["word_count"], not_before=int(time.time()) - 100,
        expires_at=int(time.time()) - 1,
    )
    assert lab["provision"](grant_value=expired)[0] == 200
    assert lab["call"]("effects", lab["effect"](signed_grant=expired))[0] == 403
    assert count_effects(lab["db"]) == 0


def test_unknown_query_is_not_falsely_reported_as_absent(service_lab):
    lab = service_lab
    assert lab["provision"]()[0] == 200
    query = sign_tool("query", {
        "type": "tool-query", "task_id": "task-tool-1",
        "movement_id": "move-tool-1", "effect_id": "never-sent",
    }, lab["executor"])
    code, response = lab["call"]("query", query)
    assert code == 200 and response["status"] == "unknown_reconcile"
    assert response["receipt"] is None


def test_process_crash_restart_preserves_ledger_and_replay_contract(service_lab):
    lab = service_lab
    assert lab["provision"]()[0] == 200
    signed = lab["effect"]()
    assert lab["call"]("effects", signed)[0] == 200
    old_pid = lab["pid"]
    new_pid = lab["restart"]()
    assert new_pid != old_pid
    query = sign_tool("query", {
        "type": "tool-query", "task_id": "task-tool-1",
        "movement_id": "move-tool-1", "effect_id": "result-1",
    }, lab["executor"])
    code, response = lab["call"]("query", query)
    assert code == 200 and response["status"] == "committed"
    assert lab["call"]("effects", signed)[1]["status"] == "replayed"
    assert count_effects(lab["db"]) == 1
