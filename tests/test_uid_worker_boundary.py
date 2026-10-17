"""Linux root-supervised synthetic UID+seccomp worker boundary (issues #98/#50).

Tests run only on audited Linux x86_64 with a root-owned supervisor. The
dedicated CI job invokes them via sudo; missing privileges are not success.
Never run with real user secrets, external tools or non-disposable keys.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

import pytest

from agent_movement.core import Approval, HandoffReceiver, SQLiteStore
from agent_movement.egress_lab import run_guarded_agent
from agent_movement.egress_sandbox import supported
from agent_movement.http import make_server
from agent_movement.trust import HS256
from test_core import fixture
from test_peer import PROVIDER_CANARY, TEXT, World
from test_sender_gate import client, policy

PROBE = Path(__file__).resolve().parents[1] / "src/agent_movement/uid_worker_probe.py"
STALL = Path(__file__).resolve().parents[1] / "src/agent_movement/uid_stall_probe.py"
ROOT_ONLY = pytest.mark.skipif(
    not supported() or not hasattr(os, "geteuid") or os.geteuid() != 0,
    reason="separate-UID seccomp test requires Linux x86_64 and an independent root supervisor",
)


def save_evidence(name: str, details: dict) -> None:
    directory = os.environ.get("AMV_UID_EVIDENCE_DIR")
    if directory is None:
        return
    path = Path(directory) / f"{name}.json"
    path.write_text(json.dumps(details, sort_keys=True, indent=2) + "\n", encoding="utf-8")


DENIED_ROUTES = (
    "legacy_http", "a2a_jsonrpc", "a2a_rest", "peer_preflight", "tool_service",
    "tcp", "udp", "unix", "spawn", "reacquire_root", "protected_file",
    "protected_db", "parent_proc_environ", "parent_private_fd",
)


def test_explicit_distinct_uid_mode_cannot_fall_back_to_same_uid(monkeypatch, tmp_path):
    # This test runs in the regular no-root Python CI matrix too. Mocking the
    # supervisor identity tests early refusal BEFORE the process is launched.
    monkeypatch.setattr(os, "geteuid", lambda: 1000, raising=False)
    with pytest.raises(RuntimeError, match="requires root supervisor"):
        run_guarded_agent(PROBE, {}, probe_port=1, child_uid=65534, child_gid=65534)
    with pytest.raises(ValueError, match="provided together"):
        run_guarded_agent(PROBE, {}, probe_port=1, child_uid=65534)
    with pytest.raises(ValueError, match="protected-resource"):
        run_guarded_agent(PROBE, {}, probe_port=1, protected_file=tmp_path / "secret")


def test_uid_probe_is_not_silently_run_as_unprotected_child():
    if os.name != "posix":
        pytest.skip("POSIX identity checks only")
    # Linux root test below validates that it *does* run when the kernel
    # allows privilege separation; do not count this refusal as an outcome.
    if os.geteuid() != 0:
        with pytest.raises(RuntimeError, match="requires root supervisor"):
            run_guarded_agent(PROBE, {}, probe_port=1, child_uid=65534, child_gid=65534)


@ROOT_ONLY
def test_root_owned_legacy_listener_secrets_and_effects_are_inaccessible(tmp_path):
    # The operator alone provisions the sender/receiver and holds two types
    # of credentials. No private keys, text or unrestricted transports are
    # passed in the untrusted worker environment or the pipe command.
    world = World(HS256, tmp_path)
    private = tmp_path / "operator-only.synthetic"
    private.write_bytes(b"ROOT-ONLY-SYNTHETIC-CANARY-DO-NOT-DISCLOSE")
    private.chmod(0o600)
    root_dir = tmp_path
    root_dir.chmod(0o700)
    world_db = Path(world.store.path)
    world_db.chmod(0o600)

    # Real, intentionally weak legacy listener: unfenced callers can reach
    # and complete a self-claimed handoff. A restricted worker must not.
    legacy = SQLiteStore(tmp_path / "legacy.sqlite")
    server = make_server(HandoffReceiver(
        "agent-b", legacy, [Approval("approval-1", "task-1", "agent-a", "agent-b", "word_count")],
    ))
    listener = threading.Thread(target=server.serve_forever, daemon=True)
    listener.start()
    try:
        # Red control: prove this is an ACTUAL reachable handler, not a name
        # on a dummy TCP observer. The event stays in the LEGACY ledger.
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/v0/handoffs",
            data=json.dumps(fixture()).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            assert response.status == 200
        legacy_before = legacy.audit()
        assert [r["event_type"] for r in legacy_before] == ["handoff.accepted", "handoff.completed"]

        secret_fd = os.open(private, os.O_RDONLY)
        try:
            result = run_guarded_agent(
                PROBE,
                {"task-1": lambda: world.handoff(client=client(world))["effect"]},
                probe_port=server.server_port,
                child_uid=65534, child_gid=65534,
                protected_file=private, protected_db=world_db,
                protected_parent_fd=secret_fd,
            )
        finally:
            os.close(secret_fd)

        assert result.exit_code == 0, result.stderr
        assert result.request_count == 1
        assert result.broker_status == "committed"
        observations = json.loads(result.stdout)
        assert observations["uid"] == 65534
        assert observations["gid"] == 65534
        assert observations["real_saved_uids"] == [65534, 65534, 65534]
        assert observations["real_saved_gids"] == [65534, 65534, 65534]
        assert observations["supplementary_groups"] == []
        assert observations["protected_fd_inherited"] is False
        assert all(observations[k] == "blocked" for k in DENIED_ROUTES), observations

        # Independent source-of-truth observation: same trusted parent DBs,
        # not an untrusted worker's claim of what it did or didn't execute.
        assert legacy.audit() == legacy_before
        assert len(world.receiver.ledger.effects()) == 1
        assert world.wire.paths() == ["/v0/agent-card", "/v0/preflight", "/v0/deliveries"]
        assert private.read_bytes() == b"ROOT-ONLY-SYNTHETIC-CANARY-DO-NOT-DISCLOSE"
        assert b"ROOT-ONLY-SYNTHETIC-CANARY" not in result.stdout.encode()
        assert TEXT.encode() not in result.stdout.encode()
        assert PROVIDER_CANARY.encode() not in result.stderr.encode()
        save_evidence("allow", {
            "profile": "uid-seccomp-pipe-v1", "worker_uid": observations["uid"],
            "worker_gid": observations["gid"], "groups": observations["supplementary_groups"],
            "observations": {k: observations[k] for k in DENIED_ROUTES},
            "private_fd_inherited": observations["protected_fd_inherited"],
            "broker": result.broker_status, "independent_legacy_unchanged": legacy.audit() == legacy_before,
            "independent_peer_effects": len(world.receiver.ledger.effects()),
            "canary_in_worker_output": TEXT.encode() in result.stdout.encode(),
        })
    finally:
        server.shutdown()
        server.server_close()
        listener.join(timeout=5)


@ROOT_ONLY
def test_uid_worker_cannot_mutate_world_writable_synthetic_storage():
    """A real non-root red control can write; seccomp-fenced UID cannot."""
    with tempfile.TemporaryDirectory(prefix="amv-uid-write-") as dirname:
        scratch = Path(dirname)
        scratch.chmod(0o777)
        target = scratch / "owned-target.txt"
        target.write_text("UNCHANGED", encoding="utf-8")
        os.chown(target, 65534, 65534)
        target.chmod(0o666)
        canary = scratch / "must-not-create.txt"
        # Explicit RED control: the exact UID and path can create/write
        # files with ordinary DAC, so a denial is caused by worker fencing.
        red = subprocess.run(
            [sys.executable, "-c", "from pathlib import Path; import sys; "
             "Path(sys.argv[1]).write_text('RED-CONTROL')", str(canary)],
            user=65534, group=65534, extra_groups=(),
            check=True, capture_output=True, text=True, timeout=10,
        )
        assert red.returncode == 0
        assert canary.read_text(encoding="utf-8") == "RED-CONTROL"
        canary.unlink()
        guarded = run_guarded_agent(
            PROBE, {"task-1": lambda: "committed"}, probe_port=1,
            child_uid=65534, child_gid=65534, unapproved_write_dir=scratch,
        )
        assert guarded.exit_code == 0, guarded.stderr
        assert guarded.broker_status == 'committed'
        observations = json.loads(guarded.stdout)
        attempted = ('scratch_write', 'scratch_unlink', 'scratch_mkdir',
                     'scratch_rename', 'scratch_chmod')
        assert all(observations[k] == "blocked" for k in attempted), observations
        assert target.read_text(encoding="utf-8") == "UNCHANGED"
        assert not canary.exists()
        assert not (scratch / "must-not-mkdir").exists()
        assert not (scratch / "renamed").exists()
        save_evidence("storage", {
            "profile": "uid-seccomp-write-deny-v1",
            "dac_positive_control": True,
            "kernel_denials": {k: observations[k] for k in attempted},
            "independent_target_unchanged": True,
            "worker_uid": observations["uid"],
        })

@ROOT_ONLY
def test_denied_trusted_broker_does_not_disclose_or_commit(tmp_path):
    world = World(HS256, tmp_path)
    private = tmp_path / "operator-only.synthetic"
    private.write_bytes(b"SYNTHETIC-SECRET-NOT-AGENT-INPUT")
    private.chmod(0o600)
    bad = policy(world, destinations={("agent-b", "local://wrong")})
    result = run_guarded_agent(
        PROBE, {"task-1": lambda: world.handoff(client=client(world, gate=bad))["effect"]},
        probe_port=1, child_uid=65534, child_gid=65534,
        protected_file=private, protected_db=Path(world.store.path),
    )
    assert result.exit_code == 0, result.stderr
    assert result.broker_status == "denied"
    observed = json.loads(result.stdout)
    assert observed["broker"] == "denied"
    assert all(observed[k] == "blocked" for k in DENIED_ROUTES if k != "parent_private_fd")
    assert world.wire.paths() == []
    assert world.receiver.ledger.effects() == []
    assert TEXT.encode() not in result.stdout.encode()
    assert b"SYNTHETIC-SECRET-NOT-AGENT-INPUT" not in result.stdout.encode()
    save_evidence("deny", {
        "profile": "uid-seccomp-pipe-v1", "broker": result.broker_status,
        "wire_requests": world.wire.paths(), "independent_peer_effects": len(world.receiver.ledger.effects()),
        "observations": {k: observed[k] for k in DENIED_ROUTES if k != "parent_private_fd"},
        "canary_in_worker_output": TEXT.encode() in result.stdout.encode(),
    })


@ROOT_ONLY
def test_operator_timeout_kills_uncooperative_uid_worker_without_effect(tmp_path):
    invoked: list[str] = []
    with pytest.raises(RuntimeError, match="sandboxed attacker did not exit"):
        run_guarded_agent(
            STALL, {"task-1": lambda: invoked.append("effect") or "committed"},
            probe_port=1, child_uid=65534, child_gid=65534, timeout=0.6,
        )
    assert invoked == []
    save_evidence("timeout", {"profile": "uid-seccomp-pipe-v1",
                              "worker_terminated": True, "protected_callback_invocations": len(invoked)})
