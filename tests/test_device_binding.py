"""Adversarial software-only tests: portable state does not imply privileged authority."""

from __future__ import annotations

from dataclasses import replace

import pytest

from agent_movement.device_binding import (
    BindingDenied,
    DeviceEffectGateway,
    LocalSoftwareKey,
    PortableAgent,
)


def setup_gateway():
    gateway = DeviceEffectGateway(challenge_ttl=10)
    source_key = LocalSoftwareKey.generate()
    other_key = LocalSoftwareKey.generate()
    gateway.register_device("device-a", source_key.verifier())
    gateway.register_device("device-b", other_key.verifier())
    gateway.issue_grant("grant-a", "task-1", "instance-a", "device-a", "fake-tool", "write", 1100, 1000)
    return gateway, source_key, other_key


def test_snapshot_copy_is_authority_free():
    source = PortableAgent("task-1", "definition-1", "safe synthetic example")
    portable = source.snapshot()
    clone = PortableAgent.from_snapshot(dict(portable))
    assert clone.compute() == source.compute() == 3
    assert portable == clone.snapshot()
    assert set(portable) == {"schema", "task_id", "definition_id", "text"}
    assert "key" not in str(portable).lower()


def test_authorized_origin_commits_once_and_proof_is_not_replayable():
    gateway, key, _ = setup_gateway()
    challenge = gateway.challenge("grant-a", "instance-a", "device-a", "fake-tool", "write", "effect-1", 1000)
    proof = key.sign(challenge.signed_bytes())
    assert gateway.commit(challenge, proof, 1001)["status"] == "synthetic_effect_committed"
    assert gateway.effect_count == 1
    with pytest.raises(BindingDenied, match="challenge_unknown_or_modified"):
        gateway.commit(challenge, proof, 1002)
    second = gateway.challenge("grant-a", "instance-a", "device-a", "fake-tool", "write", "effect-1", 1003)
    with pytest.raises(BindingDenied, match="duplicate_effect"):
        gateway.commit(second, key.sign(second.signed_bytes()), 1003)
    assert gateway.effect_count == 1


def test_clone_claiming_its_own_device_is_rejected():
    gateway, _, clone_key = setup_gateway()
    PortableAgent.from_snapshot(PortableAgent("task-1", "definition-1", "two words").snapshot())
    with pytest.raises(BindingDenied, match="binding_mismatch"):
        gateway.challenge("grant-a", "instance-b", "device-b", "fake-tool", "write", "effect-2", 1000)
    # Unrecognized grant cannot be made valid by supplying a working local key.
    with pytest.raises(BindingDenied, match="unknown_grant"):
        gateway.challenge("invented", "instance-b", "device-b", "fake-tool", "write", "effect-2", 1000)
    assert clone_key.sign(b"request")
    assert gateway.effect_count == 0


def test_clone_spoofing_origin_identity_but_signing_with_cloned_device_fails():
    gateway, _, clone_key = setup_gateway()
    challenge = gateway.challenge("grant-a", "instance-a", "device-a", "fake-tool", "write", "effect-1", 1000)
    with pytest.raises(BindingDenied, match="signature_invalid"):
        gateway.commit(challenge, clone_key.sign(challenge.signed_bytes()), 1001)
    assert gateway.effect_count == 0


def test_replaying_other_valid_challenge_signature_is_rejected():
    gateway, source_key, _ = setup_gateway()
    first = gateway.challenge("grant-a", "instance-a", "device-a", "fake-tool", "write", "effect-1", 1000)
    other = gateway.challenge("grant-a", "instance-a", "device-a", "fake-tool", "write", "effect-2", 1000)
    with pytest.raises(BindingDenied, match="signature_invalid"):
        gateway.commit(other, source_key.sign(first.signed_bytes()), 1001)
    assert gateway.effect_count == 0


def test_challenge_tampering_consumes_nonce_without_effect():
    gateway, source_key, _ = setup_gateway()
    challenge = gateway.challenge("grant-a", "instance-a", "device-a", "fake-tool", "write", "effect-1", 1000)
    with pytest.raises(BindingDenied, match="challenge_unknown_or_modified"):
        gateway.commit(replace(challenge, audience="different-tool"), source_key.sign(challenge.signed_bytes()), 1001)
    with pytest.raises(BindingDenied, match="challenge_unknown_or_modified"):
        gateway.commit(challenge, source_key.sign(challenge.signed_bytes()), 1001)
    assert gateway.effect_count == 0


def test_expiration_fails_closed_at_admission_and_commit():
    gateway, source_key, _ = setup_gateway()
    c = gateway.challenge("grant-a", "instance-a", "device-a", "fake-tool", "write", "effect-1", 1000)
    with pytest.raises(BindingDenied, match="expired_challenge"):
        gateway.commit(c, source_key.sign(c.signed_bytes()), 1010)
    with pytest.raises(BindingDenied, match="expired_grant"):
        gateway.challenge("grant-a", "instance-a", "device-a", "fake-tool", "write", "effect-2", 1100)
    assert gateway.effect_count == 0


def test_revocation_blocks_previously_issued_proof():
    gateway, source_key, _ = setup_gateway()
    c = gateway.challenge("grant-a", "instance-a", "device-a", "fake-tool", "write", "effect-1", 1000)
    gateway.revoke("grant-a")
    with pytest.raises(BindingDenied, match="revoked_grant"):
        gateway.commit(c, source_key.sign(c.signed_bytes()), 1001)
    assert gateway.effect_count == 0


def test_fence_blocks_even_valid_source_device_key_and_rebind_allows_destination():
    gateway, source_key, dest_key = setup_gateway()
    proof_before_move = gateway.challenge("grant-a", "instance-a", "device-a", "fake-tool", "write", "effect-1", 1000)
    assert gateway.fence("task-1") == 2
    with pytest.raises(BindingDenied, match="stale_epoch"):
        gateway.commit(proof_before_move, source_key.sign(proof_before_move.signed_bytes()), 1001)
    with pytest.raises(BindingDenied, match="stale_epoch"):
        gateway.challenge("grant-a", "instance-a", "device-a", "fake-tool", "write", "effect-2", 1001)
    gateway.issue_grant("grant-b", "task-1", "instance-b", "device-b", "fake-tool", "write", 1100, 1001)
    c = gateway.challenge("grant-b", "instance-b", "device-b", "fake-tool", "write", "effect-1", 1002)
    assert gateway.commit(c, dest_key.sign(c.signed_bytes()), 1003)["device_id"] == "device-b"
    assert gateway.effect_count == 1


def test_bad_audience_and_action_denied_before_challenge():
    gateway, _, _ = setup_gateway()
    for audience, action in (("other-tool", "write"), ("fake-tool", "delete")):
        with pytest.raises(BindingDenied, match="binding_mismatch"):
            gateway.challenge("grant-a", "instance-a", "device-a", audience, action, "effect-1", 1000)
    assert gateway.effect_count == 0


def test_unregistered_and_duplicate_device_rejected():
    gateway, key, _ = setup_gateway()
    with pytest.raises(BindingDenied, match="unknown_device"):
        gateway.issue_grant("grant-x", "task-1", "instance-x", "device-z", "fake-tool", "write", 1100, 1000)
    with pytest.raises(BindingDenied, match="device_already_registered"):
        gateway.register_device("device-a", key.verifier())


def test_unapproved_clone_never_inherits_grant():
    gateway, source_key, clone_key = setup_gateway()
    assert source_key.export_fixture_hex() != clone_key.export_fixture_hex()
    snapshot = PortableAgent("task-1", "definition-1", "synthetic input").snapshot()
    assert PortableAgent.from_snapshot(snapshot).task_id == "task-1"
    with pytest.raises(BindingDenied):
        gateway.challenge("grant-a", "instance-b", "device-b", "fake-tool", "write", "effect-1", 1000)
    assert gateway.effect_count == 0


def test_invalid_snapshot_rejected():
    snapshot = PortableAgent("task-1", "definition-1", "synthetic").snapshot()
    snapshot["private_key"] = "not-allowed"
    with pytest.raises(BindingDenied, match="invalid_snapshot"):
        PortableAgent.from_snapshot(snapshot)


def test_two_worker_process_demo_explicit_rebind():
    from agent_movement.device_binding_demo import run_demo

    report = run_demo()
    assert report["security_assurance"] == "software_only_no_hardware_attestation"
    assert report["separate_worker_processes"] is True
    assert report["portable_snapshot_unchanged"] is True
    assert report["origin_artifact"] == report["copied_artifact"] == 3
    assert report["authorized_origin"] == "synthetic_effect_committed"
    assert report["copy_without_grant"] == "binding_mismatch"
    assert report["clone_claims_origin_identity"] == "signature_invalid"
    assert report["replayed_origin_proof"] == "challenge_unknown_or_modified"
    assert report["fencing_epoch"] == 2
    assert report["old_device_after_fence"] == "stale_epoch"
    assert report["authorized_destination_after_rebind"] == "synthetic_effect_committed"
    assert report["synthetic_effects_committed"] == 2


def test_extractable_software_key_is_a_successful_counterexample():
    """An attacker who copies the software key CAN impersonate the bound device.

    A real non-exportable hardware key / verifier must address this threat; this
    software-only experiment explicitly does not satisfy it.
    """
    gateway, origin_key, _ = setup_gateway()
    stolen_software_key = LocalSoftwareKey.from_fixture_hex(origin_key.export_fixture_hex())
    challenge = gateway.challenge("grant-a", "instance-a", "device-a", "fake-tool", "write", "effect-1", 1000)
    assert gateway.commit(challenge, stolen_software_key.sign(challenge.signed_bytes()), 1001)["status"] == (
        "synthetic_effect_committed"
    )
    assert gateway.effect_count == 1
