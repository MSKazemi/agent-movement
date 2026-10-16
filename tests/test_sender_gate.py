"""Opt-in, operator-pinned sender admission tests for Issue #50.

These exercise PeerClient.handoff only. Generic direct sockets, legacy HTTP and
A2A remain outside this sender-side check and require separate OS/process gates.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_movement.core import ContractError
from agent_movement.egress_sandbox import supported
from agent_movement.peer import CARD_PATH, PREFLIGHT_PATH, HandoffAborted
from agent_movement.sender_gate import OutboundGate
from agent_movement.trust import HS256, Unauthorized
from test_peer import TEXT, World


@pytest.fixture
def world(tmp_path):
    return World(HS256, tmp_path)


def policy(world, *, destinations=None, capabilities=None, classifications=None,
           revoked=None, require_confidentiality=False):
    return OutboundGate(
        allowed_destinations=frozenset(
            {("agent-b", world.b_url)} if destinations is None else destinations
        ),
        allowed_capabilities=frozenset(
            {"word_count"} if capabilities is None else capabilities
        ),
        allowed_classifications=frozenset(
            {"synthetic"} if classifications is None else classifications
        ),
        is_revoked=(lambda _grant_id: False) if revoked is None else revoked,
        require_confidentiality=require_confidentiality,
    )


def client(world, *, gate=None, key=None):
    return world.client(
        key=world.keys["agent-a"] if key is None else key,
        outbound_gate=policy(world) if gate is None else gate,
        secure_test_mode=True,
    )


def assert_denied_without_network(world, action, reason=None):
    with pytest.raises(HandoffAborted) as raised:
        action()
    assert raised.value.stage == "outbound_gate"
    assert raised.value.payload_sent is False
    if reason is not None:
        assert raised.value.reason == reason
    # No discovery call, authorization metadata or sensitive task text.
    assert world.wire.paths() == []
    assert TEXT.encode() not in world.wire.transmitted()
    assert world.receiver.ledger.effects() == []


def test_positive_sender_authorization_retains_receiver_effect_checks(world):
    receipt = world.handoff(client=client(world))
    assert receipt["effect"] == "committed"
    assert world.wire.paths() == [CARD_PATH, PREFLIGHT_PATH, "/v0/deliveries"]
    assert len(world.receiver.ledger.effects()) == 1


@pytest.mark.skipif(not supported(), reason="independent seccomp experiment requires Linux x86_64")
def test_independent_process_broker_obeys_operator_sender_gate(world):
    from agent_movement.egress_lab import run_guarded_agent

    probe = Path(__file__).resolve().parents[1] / "src/agent_movement/egress_probe.py"
    bad = policy(world, destinations={("agent-b", "local://other")})
    result = run_guarded_agent(
        probe, {"task-1": lambda: world.handoff(client=client(world, gate=bad))["effect"]},
        probe_port=1,
    )
    assert result.exit_code == 0, result.stderr
    assert result.broker_status == "denied"
    assert world.wire.paths() == []
    assert world.receiver.ledger.effects() == []
    observations = json.loads(result.stdout)
    assert all(observations[name] == "blocked" for name in (
        "tcp", "legacy_http", "a2a_http", "udp", "ipv6", "unix", "spawn", "fork", "raw_syscall",
    ))

    authorized = run_guarded_agent(
        probe, {"task-1": lambda: world.handoff(client=client(world))["effect"]},
        probe_port=1,
    )
    assert authorized.exit_code == 0, authorized.stderr
    assert authorized.broker_status == "committed"
    assert len(world.receiver.ledger.effects()) == 1


def test_secure_sender_mode_fails_closed_without_operator_gate(world):
    with pytest.raises(ContractError, match="requires an outbound gate"):
        world.client(secure_test_mode=True)
    assert world.wire.paths() == []


@pytest.mark.parametrize("where, kind, classification, reason", [
    ("local://wrong-place", "word_count", "synthetic", "outbound_destination_denied"),
    ("local://agent-b", "sha256", "synthetic", "outbound_capability_denied"),
    ("local://agent-b", "word_count", "public", "outbound_classification_denied"),
])
def test_operator_allowlist_blocks_before_discovery(world, where, kind, classification, reason):
    assert_denied_without_network(
        world,
        lambda: world.handoff(
            client=client(world), url=where, kind=kind, classification=classification,
        ),
        reason=reason,
    )


@pytest.mark.parametrize("variation", [
    "wrong_audience", "wrong_actor", "wrong_task", "capability",
    "classification", "expired", "future", "rogue_issuer",
])
def test_signed_grant_is_verified_locally_before_any_request(world, variation):
    kwargs = {
        "wrong_audience": {"audience": "agent-c"},
        "wrong_actor": {"actor": "agent-c"},
        "wrong_task": {"task_id": "another-task"},
        "capability": {"capabilities": ["sha256"]},
        "classification": {"classification": "public"},
        "expired": {"expires_at": world.clock.t - 1},
        "future": {"not_before": world.clock.t + 10},
        "rogue_issuer": {"issuer": world.rogue_users},
    }[variation]
    if "issuer" in kwargs:
        issuer = kwargs.pop("issuer")
        grant = world.grant(issuer=issuer)
    else:
        grant = world.grant(**kwargs)
    assert_denied_without_network(
        world, lambda: world.handoff(client=client(world), grant=grant),
    )


def test_revocation_change_after_admission_blocks_sender_delivery(world):
    # A trusted operator changes revocation state after metadata admission.
    # The sender rechecks before transmitting any task-text bytes.
    checks = []

    def revoked(_grant_id):
        checks.append(True)
        return len(checks) >= 2

    assert_denied = pytest.raises(HandoffAborted)
    with assert_denied as raised:
        world.handoff(client=client(world, gate=policy(world, revoked=revoked)))
    assert raised.value.stage == "outbound_gate"
    assert raised.value.reason == "grant_revoked"
    assert raised.value.payload_sent is False
    assert len(checks) == 2
    assert world.wire.paths() == [CARD_PATH, PREFLIGHT_PATH]
    assert TEXT.encode() not in world.wire.transmitted()
    assert world.receiver.ledger.effects() == []


def test_key_id_collision_is_not_proof_of_origin_identity(world):
    # The attacker copied the signed card and key *name* but not its key secret.
    assert world.rogue["agent-a"].kid == world.keys["agent-a"].kid
    assert_denied_without_network(
        world,
        lambda: world.handoff(client=client(world, key=world.rogue["agent-a"])),
        reason="outbound_origin_key_mismatch",
    )


def test_revocation_source_must_be_independent_available_and_boolean(world):
    for checker, reason in [
        (lambda _id: True, "grant_revoked"),
        (lambda _id: "false", "outbound_revocation_source_unavailable"),
        (lambda _id: (_ for _ in ()).throw(RuntimeError("offline")),
         "outbound_revocation_source_unavailable"),
    ]:
        gate = policy(world, revoked=checker)
        assert_denied_without_network(
            world, lambda: world.handoff(client=client(world, gate=gate)),
            reason=reason,
        )


def test_outbound_policy_cannot_authorize_non_delegation_operations(world):
    gate = policy(world)
    with pytest.raises(Unauthorized, match="outbound_unsupported_operation"):
        gate.check(
            trust=world.trust, origin_card=world.cards["agent-a"],
            origin_key=world.keys["agent-a"], url=world.b_url,
            destination_id="agent-b", task_id="task-1", kind="word_count",
            classification="synthetic", grant=world.grant(), now=world.clock.t,
            operation="replicate",
        )


def test_operator_can_require_encryption_even_for_locally_allowed_receiver(world):
    c = client(world, gate=policy(world, require_confidentiality=True))
    with pytest.raises(HandoffAborted) as raised:
        world.handoff(client=c)
    assert raised.value.stage == "discovery"
    assert raised.value.reason == "no_confidentiality_key"
    assert raised.value.payload_sent is False
    assert world.wire.paths() == [CARD_PATH]
    assert TEXT.encode() not in world.wire.transmitted()


def test_mutation_red_green_missing_sender_gate_leaks_signed_metadata(world):
    mismatched = world.grant(audience="agent-c")
    # Deliberately unguarded control: receiver still denies, but the sender
    # has already contacted the recipient and sent untrusted grant metadata.
    with pytest.raises(HandoffAborted) as raised:
        world.handoff(client=world.client(), grant=mismatched)
    assert raised.value.stage == "preflight"
    assert world.wire.paths() == [CARD_PATH, PREFLIGHT_PATH]
    assert TEXT.encode() not in world.wire.transmitted()

    world.wire.exchanges.clear()
    assert_denied_without_network(
        world, lambda: world.handoff(client=client(world), grant=mismatched),
        reason="wrong_audience",
    )


@pytest.mark.parametrize("change", [
    {"destinations": frozenset()},
    {"capabilities": frozenset({"unknown"})},
    {"classifications": frozenset({"secret"})},
    {"revoked": None},
])
def test_invalid_trusted_configuration_cannot_be_installed(world, change):
    opts = {
        "destinations": frozenset({("agent-b", world.b_url)}),
        "capabilities": frozenset({"word_count"}),
        "classifications": frozenset({"synthetic"}),
        "revoked": lambda _id: False,
    }
    opts.update(change)
    with pytest.raises(ContractError):
        OutboundGate(
            allowed_destinations=opts["destinations"],
            allowed_capabilities=opts["capabilities"],
            allowed_classifications=opts["classifications"],
            is_revoked=opts["revoked"],
        )
