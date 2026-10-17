"""Broker-only operator profile against real legacy listener and trusted peer effects.

Limited synthetic lab: exact route inventory, root-owned manifest, different UID,
kernel-denied sockets and one operator-controlled callback. Not complete mediation.
"""

from __future__ import annotations

import json
import os
import threading
import urllib.request
from pathlib import Path

import pytest

from agent_movement.core import Approval, ContractError, HandoffReceiver, SQLiteStore
from agent_movement.egress_sandbox import supported
from agent_movement.http import make_server
from agent_movement.secure_profile import (
    BrokerOnlyProfile,
    _ROOT,
    _source_route_inventory,
    load_operator_profile,
)
from agent_movement.trust import HS256
from test_core import fixture
from test_peer import World
from test_sender_gate import client, policy

PROBE = _ROOT / "src/agent_movement/uid_worker_probe.py"
ROUTES = ["egress_child", "peer_card", "peer_preflight", "peer_delivery"]
ROOT_ONLY = pytest.mark.skipif(
    not supported() or not hasattr(os, "geteuid") or os.geteuid() != 0,
    reason="requires Linux x86_64 container-root supervisor; no same-UID fallback",
)


def manifest(path: Path, **changes):
    data = {
        "schema": "amv-broker-only-secure-test-v1",
        "worker_uid": 65534, "worker_gid": 65534,
        "allowed_task_ids": ["task-1"], "enabled_routes": ROUTES,
    }
    data.update(changes)
    path.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
    path.chmod(0o600)
    return path


def save_evidence(name: str, data: dict):
    directory = os.environ.get("AMV_PROFILE_EVIDENCE_DIR")
    if directory is not None:
        (Path(directory) / f"{name}.json").write_text(
            json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8",
        )


def test_explicit_operator_profile_loads_exact_only_allowed_routes(tmp_path):
    profile = load_operator_profile(manifest(tmp_path / "operator.json"))
    assert profile.task_ids == {"task-1"}
    assert profile.enabled_routes == frozenset(ROUTES)
    assert profile.worker_uid == profile.worker_gid == 65534


@pytest.mark.parametrize("override", [
    {"schema": "missing-version"}, {"worker_uid": 0}, {"worker_uid": True},
    {"worker_gid": 0}, {"allowed_task_ids": []},
    {"allowed_task_ids": ["task-1", "task-1"]},
    {"allowed_task_ids": ["../escape"]},
    {"enabled_routes": [*ROUTES, "legacy_handoff_http"]},
    {"enabled_routes": [*ROUTES, "a2a_jsonrpc"]},
    {"enabled_routes": [*ROUTES, "independent_tool_pilot"]},
    {"enabled_routes": ["egress_child"]},
    {"enabled_routes": [*ROUTES, {"bad": "shape"}]},
])
def test_operator_cannot_enable_unreviewed_routes(tmp_path, override):
    with pytest.raises(ContractError):
        load_operator_profile(manifest(tmp_path / "operator.json", **override))


def test_direct_profile_constructor_cannot_expand_routes_or_reuse_root_uid():
    with pytest.raises(ContractError, match="unreviewed broker"):
        BrokerOnlyProfile(65534, 65534, frozenset({"task-1"}),
                          frozenset({*ROUTES, "legacy_handoff_http"}))
    with pytest.raises(ContractError, match="unreviewed broker"):
        BrokerOnlyProfile(0, 0, frozenset({"task-1"}), frozenset(ROUTES))


def test_operator_manifest_must_be_private_regular_file_and_not_symlink(tmp_path):
    path = manifest(tmp_path / "operator.json")
    path.chmod(0o644)
    with pytest.raises(ContractError, match="owner-only"):
        load_operator_profile(path)
    path.chmod(0o600)
    alias = tmp_path / "operator-link.json"
    alias.symlink_to(path)
    with pytest.raises(ContractError, match="unsafe"):
        load_operator_profile(alias)


def test_operator_manifest_rejects_duplicate_json_keys(tmp_path):
    path = tmp_path / "operator.json"
    path.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
    path.chmod(0o600)
    with pytest.raises(ContractError):
        load_operator_profile(path)


def test_inventory_mutation_cannot_silently_activate_legacy(tmp_path):
    original = (_ROOT / "data/secure-route-inventory.csv").read_text(encoding="utf-8")
    good = tmp_path / "inventory.csv"
    good.write_text(original, encoding="utf-8")
    _source_route_inventory(good)
    for changed in (original.replace('"must_disable"', '"gated_candidate"', 1),
                    original.replace('"gated_candidate"', '"must_disable"', 1),
                    original.replace('"legacy_handoff_http"', '"unknown_route"', 1)):
        good.write_text(changed, encoding="utf-8")
        # Every change to the original reviewed 16-route map, including
        # a promotion of even one legacy endpoint, must be refused.
        with pytest.raises(ContractError):
            _source_route_inventory(good)


def test_operator_callback_allowlist_exact_and_fails_before_launch(tmp_path):
    profile = load_operator_profile(manifest(tmp_path / "operator.json"))
    with pytest.raises(ContractError, match="exactly match"):
        profile.run(PROBE, {"task-other": lambda: "committed"}, probe_port=1)
    with pytest.raises(ContractError, match="exactly match"):
        profile.run(PROBE, {}, probe_port=1)
    with pytest.raises(ContractError, match="invalid loopback"):
        profile.run(PROBE, {"task-1": lambda: "committed"}, probe_port=0)


@ROOT_ONLY
def test_operator_only_broker_with_actual_unmediated_listener(tmp_path):
    profile = load_operator_profile(manifest(tmp_path / "operator.json"))
    world = World(HS256, tmp_path)
    legacy = SQLiteStore(tmp_path / "legacy.sqlite")
    server = make_server(HandoffReceiver("agent-b", legacy, [
        Approval("approval-1", "task-1", "agent-a", "agent-b", "word_count"),
    ]))
    listener = threading.Thread(target=server.serve_forever, daemon=True)
    listener.start()
    try:
        # RED: an actual unmediated legacy handler still accepts the test
        # request from the trusted/unfenced host, and is not globally disabled.
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/v0/handoffs",
            data=json.dumps(fixture()).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            assert response.status == 200
        legacy_before = legacy.audit()
        assert any(r["event_type"] == "handoff.accepted" for r in legacy_before)

        result = profile.run(
            PROBE, {"task-1": lambda: world.handoff(client=client(world))["effect"]},
            probe_port=server.server_port,
        )
        assert result.exit_code == 0, result.stderr
        assert result.broker_status == "committed"
        observation = json.loads(result.stdout)
        assert observation["broker"] == "committed"
        assert observation["uid"] == observation["gid"] == 65534
        for route in ("legacy_http", "a2a_jsonrpc", "a2a_rest",
                      "peer_preflight", "tool_service", "tcp", "udp", "unix", "spawn"):
            assert observation[route] == "blocked"
        assert legacy.audit() == legacy_before
        assert len(world.receiver.ledger.effects()) == 1
        save_evidence("profile-allow", {
            "profile": "broker-only-v1", "direct_legacy_blocked": True,
            "trusted_broker_effect_count": 1,
            "legacy_unmediated_positive_control": True,
            "worker_uid": observation["uid"],
        })
    finally:
        server.shutdown()
        server.server_close()
        listener.join(timeout=5)


@ROOT_ONLY
def test_operator_profile_wrong_destination_and_unsupported_operation_fail(tmp_path):
    profile = load_operator_profile(manifest(tmp_path / "operator.json"))
    world = World(HS256, tmp_path)
    refused = policy(world, destinations={("agent-b", "local://not-approved")})
    denied = profile.run(
        PROBE, {"task-1": lambda: world.handoff(client=client(world, gate=refused))["effect"]},
        probe_port=1,
    )
    assert denied.exit_code == 0, denied.stderr
    assert denied.broker_status == "denied"
    assert world.wire.paths() == []
    assert world.receiver.ledger.effects() == []
    wrong_operation = profile.run(
        PROBE, {"task-1": lambda: world.handoff(client=client(world))["effect"]},
        probe_port=1, operation="replicate",
    )
    assert wrong_operation.exit_code == 0, wrong_operation.stderr
    assert wrong_operation.broker_status == "denied"
    assert world.receiver.ledger.effects() == []
    save_evidence("profile-deny", {
        "profile": "broker-only-v1",
        "wrong_destination": denied.broker_status,
        "unsupported_operation": wrong_operation.broker_status,
        "pre_disclosure_wire_calls": len(world.wire.paths()),
        "independent_effects": len(world.receiver.ledger.effects()),
    })
