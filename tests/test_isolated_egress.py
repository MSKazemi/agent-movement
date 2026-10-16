"""Independent Linux x86_64 socket/spawn restriction, broker, and peer tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_movement.egress_experiment import build_report
from agent_movement.egress_lab import _interpret_request, run_guarded_agent
from agent_movement.egress_sandbox import supported

pytestmark = pytest.mark.skipif(not supported(), reason="audited seccomp ABI is Linux x86_64")
PROBE = Path(__file__).resolve().parents[1] / "src/agent_movement/egress_probe.py"
NETWORK_CASES = {"tcp", "legacy_http", "a2a_http", "udp", "ipv6", "unix",
                 "spawn", "fork", "raw_syscall"}


def test_linux_kernel_fence_has_observed_unfenced_control_and_no_exfil():
    report = build_report()
    assert report["unexpected"] == 0, report
    rows = {row["case_id"]: row for row in report["cases"]}
    assert NETWORK_CASES <= rows.keys()
    for case in NETWORK_CASES:
        assert rows[case]["observed"] == "blocked"
    assert rows["unfenced_loopback_control"]["observed"] == "received"
    assert rows["isolated_listener_hits"]["observed"] == "0"
    assert rows["simulated_effect_count"]["observed"] == "1"


def test_evidence_matrix_is_reproducible_and_time_independent():
    first = build_report()
    second = build_report()
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


@pytest.mark.parametrize("raw, expected", [
    (b'{"version":1,"operation":"delegate","task_id":"task-1"}\n', "committed"),
    (b'{"version":1,"operation":"clone","task_id":"task-1"}\n', "denied"),
    (b'{"version":1,"operation":"delegate","task_id":"other"}\n', "denied"),
    (b'{"version":1,"operation":"delegate","task_id":"task-1","grant":"forged"}\n', "denied"),
    (b'{"version":true,"operation":"delegate","task_id":"task-1"}\n', "denied"),
    (b'{"version":1,"operation":"delegate","task_id":"task-1","task_id":"task-1"}\n',
     "invalid_request"),
    (b"{}\n", "denied"),
    (b"not-json\n", "invalid_request"),
    (b'{"version":1,"operation":"delegate","task_id":"task-1"}', "invalid_request"),
])
def test_broker_does_not_accept_forged_grants_extra_fields_or_duplicate_keys(raw, expected):
    calls = []

    def approved():
        calls.append("effect")
        return "committed"

    outcome = _interpret_request(raw, {"task-1": approved})
    assert outcome == expected
    assert calls == (["effect"] if expected == "committed" else [])


def test_independent_attacker_process_requires_broker_for_single_authorized_effect():
    called = []

    def approved():
        called.append(True)
        return "committed"

    result = run_guarded_agent(PROBE, {"task-1": approved}, probe_port=1)
    assert result.exit_code == 0, result.stderr
    assert result.broker_status == "committed"
    assert result.request_count == 1
    assert called == [True]
    observations = json.loads(result.stdout)
    assert all(observations[name] == "blocked" for name in NETWORK_CASES)
    assert observations["broker"] == "committed"


def test_broker_cannot_serve_unsupported_operation_even_with_authorized_task():
    called = []
    result = run_guarded_agent(
        PROBE, {"task-1": lambda: called.append(True) or "committed"},
        operation="replicate", probe_port=1,
    )
    assert result.exit_code == 0, result.stderr
    assert result.broker_status == "denied"
    assert not called


def test_broker_denied_on_signed_principal_revocation_in_actual_peer(tmp_path):
    # Peer path and evidence are controlled only by the trusted parent process.
    from test_continuity_runtime import Rig, TEXT

    rig = Rig(tmp_path)
    rig.install()
    rig.revoke()
    result = run_guarded_agent(
        PROBE, {"task-1": lambda: rig.handoff()["effect"]}, probe_port=1,
    )
    assert result.exit_code == 0, result.stderr
    assert result.broker_status == "denied"
    assert rig.receiver.ledger.effects() == []
    assert TEXT.encode() not in rig.wire.transmitted()


def test_trusted_broker_executes_only_peer_authorized_delegation(tmp_path):
    from test_continuity_runtime import Rig, TEXT

    rig = Rig(tmp_path)
    rig.install()
    result = run_guarded_agent(
        PROBE, {"task-1": lambda: rig.handoff()["effect"]}, probe_port=1,
    )
    assert result.exit_code == 0, result.stderr
    assert result.broker_status == "committed"
    assert len(rig.receiver.ledger.effects()) == 1
    # Caller cannot bypass recipient by choosing an unsupported operation.
    denied = run_guarded_agent(
        PROBE, {"task-1": lambda: rig.handoff()["effect"]}, operation="fork", probe_port=1,
    )
    assert denied.broker_status == "denied"
    assert len(rig.receiver.ledger.effects()) == 1


def test_missed_consent_blocks_before_synthetic_payload_disclosure(tmp_path):
    from test_continuity_runtime import Rig, TEXT

    rig = Rig(tmp_path)
    rig.install(owner=False)
    result = run_guarded_agent(
        PROBE, {"task-1": lambda: rig.handoff()["effect"]}, probe_port=1,
    )
    assert result.broker_status == "denied"
    assert rig.receiver.ledger.effects() == []
    assert TEXT.encode() not in rig.wire.transmitted()


def test_commit_time_revocation_denies_even_after_disclosure(tmp_path):
    from test_continuity_runtime import Rig, TEXT

    rig = Rig(tmp_path)
    rig.install()
    rig.receiver.before_effect_commit = lambda _record: rig.revoke()
    result = run_guarded_agent(
        PROBE, {"task-1": lambda: rig.handoff()["effect"]}, probe_port=1,
    )
    assert result.broker_status == "denied"
    assert rig.receiver.ledger.effects() == []
    # Important: the payload was already sent at delivery, despite no effect.
    assert TEXT.encode() in rig.wire.transmitted()
