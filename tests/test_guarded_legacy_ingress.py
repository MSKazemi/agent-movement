"""Issue #50: a guarded task cannot be accepted via the legacy handoff path.

The lower-level legacy receiver deliberately permits a self-declared origin for
unmanaged pure tasks. Enrollment into GuardedAuthority MUST close that ingress
under the same SQLite write transaction, not only guard later simulated effects.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import urllib.error
import urllib.request

import pytest

from agent_movement.core import (
    Approval,
    EffectGateway,
    HandoffReceiver,
    PolicyDenied,
    SQLiteStore,
)
from agent_movement.http import make_server
from test_continuity_runtime import Rig
from test_core import fixture
from test_guarded_authority import intent, service


def enrolled(tmp_path):
    rig = Rig(tmp_path)
    rig.install()
    gateway = EffectGateway(rig.store)
    gateway.claim("task-1", "agent-a")
    guarded = service(rig)
    guarded.enroll(intent(rig), rig.grant)
    approval = Approval("approval-1", "task-1", "agent-a", "agent-b", "word_count")
    legacy = HandoffReceiver("agent-b", rig.store, [approval])
    return rig, legacy, guarded


def accepted(rig):
    return [item for item in rig.store.audit() if item["event_type"] == "handoff.accepted"]


def test_same_store_low_level_receive_denies_guarded_task_without_receipt(tmp_path):
    rig, _, guarded = enrolled(tmp_path)
    with pytest.raises(PolicyDenied, match="guarded task"):
        rig.store.receive(fixture(), sender="agent-a")
    assert accepted(rig) == []
    assert guarded.inspect("task-1")["phase"] == "prepared"
    assert rig.receiver.ledger.effects() == []


def test_direct_self_claimed_legacy_receiver_denies_guarded_task_and_audits(tmp_path):
    rig, legacy, guarded = enrolled(tmp_path)
    with pytest.raises(PolicyDenied, match="guarded task"):
        legacy.receive(fixture())
    assert accepted(rig) == []
    audit = rig.store.audit()
    assert [row["event_type"] for row in audit if row["task_id"] == "task-1"] == [
        "handoff.denied",
    ]
    assert guarded.inspect("task-1")["owner"] == "agent-a"


def test_real_legacy_http_direct_subprocess_bypass_is_denied_before_acceptance(tmp_path):
    rig, legacy, guarded = enrolled(tmp_path)
    server = make_server(legacy)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        # Uncooperative direct HTTP client bypasses PeerClient.handoff entirely.
        # In an unguarded test receiver the same syntactically valid envelope
        # succeeds; the only new constraint here is *durable task enrollment*.
        code = """
import sys,urllib.request,urllib.error
req=urllib.request.Request(sys.argv[1],data=sys.stdin.buffer.read(),
                           headers={'Content-Type':'application/json'})
try:
    with urllib.request.urlopen(req, timeout=3) as response:
        print(response.status)
except urllib.error.HTTPError as exc:
    print(exc.code)
"""
        url = f"http://127.0.0.1:{server.server_port}/v0/handoffs"
        result = subprocess.run(
            [sys.executable, "-c", code, url],
            input=json.dumps(fixture()), text=True, capture_output=True,
            check=True, timeout=6,
        )
        assert result.stdout.strip() == "403", result.stderr
        assert accepted(rig) == []
        assert rig.store.audit()[-1]["event_type"] == "handoff.denied"
        assert guarded.inspect("task-1")["phase"] == "prepared"
        assert rig.receiver.ledger.effects() == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_mutation_removing_store_gate_accepts_forbidden_legacy_handoff(tmp_path, monkeypatch):
    rig, legacy, _ = enrolled(tmp_path)
    with pytest.raises(PolicyDenied, match="guarded task"):
        legacy.receive(fixture())
    assert accepted(rig) == []
    # Test-only red mutation proves the new sink-side gate is causal. Never
    # expose a production config that disables the SQLite enrollment check.
    monkeypatch.setattr(EffectGateway, "_deny_guarded", staticmethod(lambda _db, _task: None))
    receipt = legacy.receive(fixture())
    assert receipt["status"] == "completed"
    assert len(accepted(rig)) == 1


def test_unmanaged_legacy_handoff_stays_available(tmp_path):
    store = SQLiteStore(tmp_path / "unmanaged.sqlite")
    receiver = HandoffReceiver(
        "agent-b", store, [Approval("approval-1", "task-1", "agent-a", "agent-b", "word_count")],
    )
    first = receiver.receive(fixture())
    second = receiver.receive(fixture())
    assert first["status"] == "completed"
    assert second["replayed"] is True
    assert len([x for x in store.audit() if x["event_type"] == "handoff.accepted"]) == 1


def test_guarded_legacy_denial_linearizes_against_revocation_and_owner_state(tmp_path):
    rig, legacy, guarded = enrolled(tmp_path)
    # A forged origin has no privileged ability to clear guarded task
    # enrollment via a receiver-local approval or repetitive retries.
    for _ in range(3):
        with pytest.raises(PolicyDenied):
            legacy.receive(fixture())
    assert accepted(rig) == []
    assert guarded.inspect("task-1")["owner"] == "agent-a"
    assert rig.receiver.ledger.effects() == []


def test_cannot_retroactively_enroll_after_untrusted_legacy_acceptance(tmp_path):
    rig = Rig(tmp_path)
    rig.install()
    EffectGateway(rig.store).claim("task-1", "agent-a")
    legacy = HandoffReceiver(
        "agent-b", rig.store,
        [Approval("approval-1", "task-1", "agent-a", "agent-b", "word_count")],
    )
    # Unprotected historical admission is genuine evidence of prior work,
    # even though the simulated effect ledger is still empty.
    assert legacy.receive(fixture())["status"] == "completed"
    with pytest.raises(PolicyDenied, match="prior legacy handoff"):
        service(rig).enroll(intent(rig), rig.grant)
    assert any(x["event_type"] == "handoff.completed" for x in rig.store.audit())
    assert rig.receiver.ledger.effects() == []
