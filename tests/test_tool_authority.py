"""Black-box and mutation tests for the independent synthetic tool-side gateway."""
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
from typing import Any

import pytest

pytest.importorskip("cryptography")

from agent_movement.core import digest
from agent_movement.tool_authority import (ACTION, RESOURCE, VERSION,
                                           IndependentTool, sign, verified)
from agent_movement.trust import Ed25519Key

NOW = 1800000000
CANARY = "SYNTHETIC_CANARY_MUST_NOT_LEAK_47"


@pytest.fixture
def rig(tmp_path):
    operator = Ed25519Key.generate("operator")
    issuer = Ed25519Key.generate("issuer")
    a = Ed25519Key.generate("worker-a")
    b = Ed25519Key.generate("worker-b")
    tool = Ed25519Key.generate("tool")
    keys = {"operator": operator, "issuer": issuer, "a": a, "b": b, "tool": tool}
    path = tmp_path / "tool.sqlite"
    service = IndependentTool(path, operator=operator.verifier(), issuer=issuer.verifier(),
                              workers={"agent-a": a.verifier(), "agent-b": b.verifier()},
                              signer=tool, clock=lambda: NOW)
    grant = sign("grant", {"version": VERSION, "grant_id": "grant-1",
                           "actor": "agent-b", "audience": "independent-tool",
                           "movement_id": "move-1", "task_id": "task-1",
                           "action": ACTION, "resource": RESOURCE,
                           "classification": "synthetic", "policy_epoch": 1,
                           "max_units": 3, "not_before": NOW - 100,
                           "expires_at": NOW + 100}, issuer)
    return service, keys, grant, path


def send(rig, channel: str, body: dict[str, Any], *, signer: str = "b"):
    service, keys, _, _ = rig
    raw = sign(channel, body, keys[signer])
    status, result = service.handle(channel, raw)
    assert "receipt" in result
    receipt = verified("receipt", result["receipt"], keys["tool"].verifier())
    assert receipt["version"] == VERSION
    assert receipt["decision"] != "denied" or status != 200
    return status, receipt


def ctrl(rig, event_type: str, suffix: str, **kwargs):
    service, keys, _, _ = rig
    payload = {"version": VERSION, "type": event_type, "event_id": f"event-{suffix}", **kwargs}
    signed = sign("revoke" if event_type == "revoke" else "control", payload,
                  keys["issuer"] if event_type == "revoke" else keys["operator"])
    status, result = service.handle("control", signed)
    receipt = verified("receipt", result["receipt"], keys["tool"].verifier())
    return status, receipt


def enroll(rig):
    _, _, grant, _ = rig
    assert ctrl(rig, "enroll", "enroll", task_id="task-1", movement_id="move-1",
                owner="agent-a", epoch=1, policy_epoch=1,
                grant_digest=digest(grant), max_units=3)[0] == 200


def transfer(rig):
    return ctrl(rig, "transfer", "transfer", task_id="task-1", movement_id="move-1",
                expected_owner="agent-a", expected_epoch=1,
                new_owner="agent-b", policy_epoch=1)


def activate(rig, *, epoch=2, **changes):
    _, _, grant, _ = rig
    data = {"version": VERSION, "actor": "agent-b", "movement_id": "move-1",
            "task_id": "task-1", "epoch": epoch, "grant": grant,
            "activation_id": "activation-1", "expires_at": NOW + 50}
    data.update(changes)
    return send(rig, "activate", data)


def effect(rig, *, effect_id="effect-1", epoch=2, units=1, grant=None, **changes):
    _, _, original, _ = rig
    data = {"version": VERSION, "actor": "agent-b", "movement_id": "move-1",
            "task_id": "task-1", "epoch": epoch,
            "grant": grant if grant is not None else original,
            "effect_id": effect_id, "action": ACTION, "resource": RESOURCE, "units": units}
    data.update(changes)
    return send(rig, "effect", data)


def ready(rig):
    enroll(rig)
    assert transfer(rig)[0] == 200
    assert activate(rig)[0] == 200


def independent_effects(path):
    with sqlite3.connect(path) as db:
        return db.execute("SELECT task_id,effect_id,actor,epoch,units FROM effects ORDER BY effect_id").fetchall()


def test_happy_path_activation_effect_replay_and_reconcile(rig):
    service, _, grant, path = rig
    enroll(rig)
    assert effect(rig)[0] == 403  # pre-transfer old owner is not recipient
    assert transfer(rig)[1]["decision"] == "accepted"
    assert effect(rig)[1]["reason"] == "destination_not_active"
    assert activate(rig)[1]["decision"] == "activated"
    assert activate(rig)[1]["decision"] == "replayed"
    assert effect(rig)[1]["decision"] == "committed"
    assert effect(rig)[1]["decision"] == "replayed"
    body = {"version": VERSION, "actor": "agent-b", "movement_id": "move-1",
            "task_id": "task-1", "epoch": 2, "grant": grant, "effect_id": "effect-1"}
    assert send(rig, "reconcile", body)[1]["decision"] == "committed"
    body["effect_id"] = "absent-effect"
    assert send(rig, "reconcile", body)[1]["decision"] == "unknown"
    assert independent_effects(path) == [("task-1", "effect-1", "agent-b", 2, 1)]
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT used_units FROM tasks").fetchone() == (1,)
        assert db.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] >= 9
        # No user-controlled payload or private token is stored as a receipt.
        assert CANARY not in "".join(row[0] for row in db.execute("SELECT signed_receipt FROM decisions"))


def test_wrong_signer_and_forged_grant_cannot_commit(rig):
    ready(rig)
    service, keys, grant, path = rig
    valid = {"version": VERSION, "actor": "agent-b", "movement_id": "move-1",
             "task_id": "task-1", "epoch": 2, "grant": grant,
             "effect_id": "forged", "action": ACTION, "resource": RESOURCE, "units": 1}
    raw = sign("effect", valid, Ed25519Key.generate("worker-b"))
    assert service.handle("effect", raw)[0] == 401
    attacker_grant = sign("grant", grant["payload"], Ed25519Key.generate("issuer"))
    assert effect(rig, grant=attacker_grant)[0] == 401
    assert effect(rig, actor="agent-a")[0] == 401  # b signature cannot claim a
    assert effect(rig, action="delete")[0] == 403
    assert effect(rig, resource="different-resource")[0] == 403
    assert effect(rig, task_id="wrong-task")[0] == 403
    assert effect(rig, movement_id="wrong-move")[0] == 403
    assert effect(rig, epoch=3)[0] == 403
    assert effect(rig, units=999)[0] == 403
    assert independent_effects(path) == []


def test_revocation_cancellation_expiry_and_policy_change_at_sink(rig):
    ready(rig)
    _, keys, grant, path = rig
    assert ctrl(rig, "revoke", "revoked", grant_id="grant-1")[0] == 200
    assert effect(rig)[1]["reason"] == "grant_revoked"
    assert independent_effects(path) == []
    # Fresh, separate task lanes exercise cancellation, policy change and expiry.
    for control in ("cancel", "unknown", "policy_change"):
        fresh = make_fresh(rig, control)
        ready(fresh)
        if control == "policy_change":
            assert ctrl(fresh, "policy_change", "change", task_id="task-1",
                        movement_id="move-1", new_policy_epoch=2)[0] == 200
        else:
            assert ctrl(fresh, control, control, task_id="task-1", movement_id="move-1")[0] == 200
        assert effect(fresh)[0] == 403
        assert independent_effects(fresh[3]) == []
    fresh = make_fresh(rig, "expired")
    service, keys, grant, _ = fresh
    ready(fresh)
    service.clock = lambda: NOW + 200
    assert effect(fresh)[1]["reason"] == "grant_not_live"


def make_fresh(rig, suffix):
    service, keys, grant, path = rig
    other_path = path.with_name(f"tool-{suffix}.sqlite")
    new_tool = IndependentTool(other_path, operator=keys["operator"].verifier(),
                               issuer=keys["issuer"].verifier(),
                               workers={"agent-a": keys["a"].verifier(),
                                        "agent-b": keys["b"].verifier()},
                               signer=keys["tool"], clock=lambda: NOW)
    return new_tool, keys, grant, other_path


def test_activation_expiry_checked_again_at_effect_commit(rig):
    fresh = make_fresh(rig, "activation-expiry")
    ready(fresh)
    service = fresh[0]
    service.clock = lambda: NOW + 60  # activation expires at NOW + 50; grant at NOW + 100
    assert effect(fresh)[1]["reason"] == "activation_expired"
    assert independent_effects(fresh[3]) == []


def test_stale_activation_replay_collision_and_late_notice(rig):
    enroll(rig)
    assert activate(rig)[0] == 403
    assert transfer(rig)[0] == 200
    assert activate(rig, epoch=999)[0] == 403
    assert activate(rig, activation_id="activation-1", expires_at=NOW + 200)[0] == 403
    assert activate(rig)[0] == 200
    assert activate(rig, activation_id="activation-1", expires_at=NOW + 45)[0] == 403
    assert ctrl(rig, "cancel", "cancel", task_id="task-1", movement_id="move-1")[0] == 200
    assert activate(rig)[0] == 403
    assert effect(rig)[0] == 403


def test_duplicate_effects_races_budget_and_conflict(rig):
    ready(rig)
    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(lambda _: effect(rig)[1]["decision"], range(20)))
    assert results.count("committed") == 1
    assert results.count("replayed") == 19
    assert effect(rig, effect_id="effect-1", units=2)[0] == 409
    assert effect(rig, effect_id="effect-2", units=2)[0] == 200
    assert effect(rig, effect_id="effect-3", units=1)[1]["reason"] == "effect_budget_exhausted"
    assert len(independent_effects(rig[3])) == 2
    with sqlite3.connect(rig[3]) as db:
        assert db.execute("SELECT used_units FROM tasks").fetchone() == (3,)


def test_mutation_control_proves_epoch_gate_is_exercised(rig, monkeypatch):
    ready(rig)
    service, _, _, path = rig
    assert effect(rig, effect_id="mutant", epoch=99)[0] == 403
    assert independent_effects(path) == []
    # RED MUTANT: deliberately remove the tool's authoritative epoch comparison.
    monkeypatch.setattr(service, "_require_current", lambda p, row: None)
    assert effect(rig, effect_id="mutant", epoch=99)[1]["decision"] == "committed"
    assert independent_effects(path)[0][3] == 99
    # The red control MUST be accepted, or the test would not detect a missing gate.


def test_replayed_and_tampered_control_commands(rig):
    enroll(rig)
    assert ctrl(rig, "enroll", "enroll", task_id="task-1", movement_id="move-1",
                owner="agent-a", epoch=1, policy_epoch=1,
                grant_digest=digest(rig[2]),
                max_units=3)[1]["decision"] == "replayed"
    assert ctrl(rig, "transfer", "enroll", task_id="task-1", movement_id="move-1",
                expected_owner="agent-a", expected_epoch=1,
                new_owner="agent-b", policy_epoch=1)[0] == 409
    assert transfer(rig)[0] == 200
    assert transfer(rig)[1]["decision"] == "replayed"


def test_denied_request_does_not_record_raw_canary(rig):
    service, keys, grant, path = rig
    forged = {"version": VERSION, "actor": "agent-b", "movement_id": "move-1",
              "task_id": CANARY, "epoch": 2, "grant": grant,
              "effect_id": CANARY, "action": ACTION, "resource": RESOURCE, "units": 1}
    assert send(rig, "effect", forged)[0] == 403
    with sqlite3.connect(path) as db:
        rows = db.execute("SELECT task_id,effect_id,signed_receipt FROM decisions").fetchall()
    assert CANARY not in json.dumps(rows)


def post(port: int, channel: str, data: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/v0/tool/{channel}", data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=4) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as err:
        return err.code, json.load(err)


def test_real_tool_server_process_and_hostile_raw_client(rig, tmp_path):
    _, keys, grant, path = rig
    now = int(time.time())
    live_payload = {**grant["payload"], "not_before": now - 60, "expires_at": now + 120}
    live_grant = sign("grant", live_payload, keys["issuer"])
    config = tmp_path / "tool-config.json"
    cfg = {"db": str(path), "operator_public": keys["operator"].export(private=False),
           "issuer_public": keys["issuer"].export(private=False),
           "workers_public": {"agent-a": keys["a"].export(private=False),
                              "agent-b": keys["b"].export(private=False)},
           "tool_signer": keys["tool"].export(private=True)}
    config.write_text(json.dumps(cfg), encoding="utf-8")
    os.chmod(config, 0o600)
    env = os.environ.copy()
    root = Path(__file__).resolve().parents[1]
    env["PYTHONPATH"] = str(root / "src") + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.Popen([sys.executable, "-m", "agent_movement.tool_authority",
                             "--config", str(config)], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, env=env)
    try:
        assert proc.stdout is not None
        assert select.select([proc.stdout], [], [], 10)[0], "tool service failed to start"
        announcement = json.loads(proc.stdout.readline())
        assert announcement["service"] == "independent-tool"
        port = announcement["port"]
        # Hostile client is a third process. It has neither the authority signing
        # key nor the destination worker key, but calls the endpoint directly.
        attack = (
            "import json,sys,urllib.request,urllib.error\n"
            "port=int(sys.argv[1]);"
            "data=json.dumps({'kid':'worker-b','payload':{'actor':'agent-b'},'sig':'bad'}).encode()\n"
            "req=urllib.request.Request(f'http://127.0.0.1:{port}/v0/tool/effect',"
            "data=data,headers={'Content-Type':'application/json'})\n"
            "try:\n"
            " urllib.request.urlopen(req,timeout=5)\n"
            " print('UNAUTHORIZED_SUCCESS')\n"
            "except urllib.error.HTTPError as exc:\n"
            " print('DENIED',exc.code)\n"
        )
        hostile = subprocess.run([sys.executable, "-c", attack, str(port)],
                                 capture_output=True, text=True, timeout=15, check=True, env=env)
        assert hostile.stdout.strip() == "DENIED 401"
        assert independent_effects(path) == []

        controls = [
            ("enroll", {"owner": "agent-a", "epoch": 1, "policy_epoch": 1,
                        "grant_digest": digest(live_grant), "max_units": 3}),
            ("transfer", {"expected_owner": "agent-a", "expected_epoch": 1,
                          "new_owner": "agent-b", "policy_epoch": 1}),
        ]
        for tag, fields in controls:
            body = {"version": VERSION, "type": tag, "event_id": f"http-{tag}",
                    "movement_id": "move-1", "task_id": "task-1", **fields}
            code, response = post(port, "control", sign("control", body, keys["operator"]))
            assert code == 200
            assert verified("receipt", response["receipt"], keys["tool"].verifier())["decision"] == "accepted"

        req = {"version": VERSION, "actor": "agent-b", "movement_id": "move-1",
               "task_id": "task-1", "epoch": 2, "grant": live_grant,
               "effect_id": "http-effect", "action": ACTION, "resource": RESOURCE, "units": 1}
        signed = sign("effect", req, keys["b"])
        assert post(port, "effect", signed)[0] == 403  # not activated
        active = {"version": VERSION, "actor": "agent-b", "movement_id": "move-1",
                  "task_id": "task-1", "epoch": 2, "grant": live_grant,
                  "activation_id": "http-activation", "expires_at": now + 60}
        code, reply = post(port, "activate", sign("activate", active, keys["b"]))
        assert code == 200
        assert verified("receipt", reply["receipt"], keys["tool"].verifier())["decision"] == "activated"
        # Deliberately ignore the first reply: it could have been lost after commit.
        assert post(port, "effect", signed)[0] == 200
        code, reply = post(port, "effect", signed)
        assert code == 200
        assert verified("receipt", reply["receipt"], keys["tool"].verifier())["decision"] == "replayed"
        assert independent_effects(path) == [("task-1", "http-effect", "agent-b", 2, 1)]

        query = {k: req[k] for k in ("version", "actor", "movement_id",
                                    "task_id", "epoch", "grant", "effect_id")}
        status, reply = post(port, "reconcile", sign("reconcile", query, keys["b"]))
        assert status == 200
        assert verified("receipt", reply["receipt"], keys["tool"].verifier())["decision"] == "committed"
        query["effect_id"] = "missing-acknowledgement"
        _, reply = post(port, "reconcile", sign("reconcile", query, keys["b"]))
        assert verified("receipt", reply["receipt"], keys["tool"].verifier())["decision"] == "unknown"

        # Simulate a hard tool-process crash AFTER committing a local synthetic
        # effect and discard the first acknowledgement. The restarted tool has
        # the same *tool-owned* durable SQLite effect ledger.
        proc.kill()
        proc.wait(timeout=5)
        proc = subprocess.Popen([sys.executable, "-m", "agent_movement.tool_authority",
                                 "--config", str(config)], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, env=env)
        assert proc.stdout is not None
        assert select.select([proc.stdout], [], [], 10)[0], "tool restart failed"
        port = json.loads(proc.stdout.readline())["port"]
        code, response = post(port, "effect", signed)
        assert code == 200
        assert verified("receipt", response["receipt"], keys["tool"].verifier())["decision"] == "replayed"
        assert independent_effects(path) == [("task-1", "http-effect", "agent-b", 2, 1)]

        revocation = {"version": VERSION, "type": "revoke", "event_id": "http-revocation",
                      "grant_id": "grant-1"}
        status, reply = post(port, "control", sign("revoke", revocation, keys["issuer"]))
        assert status == 200
        assert verified("receipt", reply["receipt"], keys["tool"].verifier())["decision"] == "accepted"
        req["effect_id"] = "blocked-after-revoke"
        status, reply = post(port, "effect", sign("effect", req, keys["b"]))
        assert status == 403
        assert verified("receipt", reply["receipt"], keys["tool"].verifier())["reason"] == "grant_revoked"
        assert len(independent_effects(path)) == 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def test_distinct_trust_roles_are_required(rig, tmp_path):
    _, keys, _, _ = rig
    with pytest.raises(ValueError, match="distinct"):
        IndependentTool(tmp_path / "misconfigured.sqlite",
                        operator=keys["a"], issuer=keys["issuer"],
                        workers={"agent-a": keys["a"], "agent-b": keys["b"]},
                        signer=keys["tool"], clock=lambda: NOW)
