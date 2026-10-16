"""Two separate local processes: copied agent state has no inherited device grant.

Dependency-free, synthetic and SOFTWARE-ONLY. Each worker is provisioned with a
DIFFERENT exportable HMAC test key through stdin by a trusted parent harness.
This does not implement TPM/TEE attestation, key non-exportability, OS-process
identity verification, or a real remote privilege gateway.

Run: python -m agent_movement.device_binding_demo
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict
from typing import Any

from .device_binding import (
    BindingDenied,
    Challenge,
    DeviceEffectGateway,
    LocalSoftwareKey,
    PortableAgent,
)


def _worker() -> int:
    """Separate synthetic executor: signs only with the key explicitly provisioned to it."""
    raw = json.load(sys.stdin)
    snapshot = PortableAgent.from_snapshot(raw["snapshot"])
    challenge = Challenge(**raw["challenge"])
    key = LocalSoftwareKey.from_fixture_hex(raw["software_test_key"])
    print(json.dumps({"instance_id": raw["instance_id"], "task_id": snapshot.task_id,
                      "artifact": snapshot.compute(), "worker_pid": os.getpid(),
                      "signature_hex": key.sign(challenge.signed_bytes()).hex()}, sort_keys=True))
    return 0


def _execute_in_process(snapshot: dict[str, str], key: LocalSoftwareKey,
                        instance_id: str, challenge: Challenge) -> dict[str, Any]:
    # The SOFTWARE-only key is passed explicitly to one local process over stdin.
    # Never treat this fixture transport as a hardware security boundary.
    command = [sys.executable, "-m", "agent_movement.device_binding_demo", "--worker"]
    fixture = {"snapshot": snapshot, "instance_id": instance_id,
               "challenge": asdict(challenge), "software_test_key": key.export_fixture_hex()}
    result = subprocess.run(command, input=json.dumps(fixture), capture_output=True,
                            text=True, check=True, timeout=8)
    return json.loads(result.stdout)


def _denial(fn: Any) -> str:
    try:
        fn()
    except BindingDenied as exc:
        return exc.reason
    raise AssertionError("expected denied synthetic operation was allowed")


def run_demo() -> dict[str, str | int | bool]:
    now = 1000  # fixed synthetic clock; results independent of wall-clock timing
    original_key = LocalSoftwareKey.generate()
    clone_key = LocalSoftwareKey.generate()
    snapshot = PortableAgent("demo-task", "word-count-agent-v0", "three synthetic words").snapshot()
    copied_snapshot = dict(snapshot)
    gateway = DeviceEffectGateway()
    gateway.register_device("laptop-a", original_key.verifier())
    gateway.register_device("edge-b", clone_key.verifier())
    gateway.issue_grant("grant-origin", "demo-task", "agent-instance-a", "laptop-a",
                        "synthetic-tool", "record", 1100, now)

    origin_c = gateway.challenge("grant-origin", "agent-instance-a", "laptop-a",
                                 "synthetic-tool", "record", "effect-origin", now)
    origin = _execute_in_process(snapshot, original_key, "agent-instance-a", origin_c)
    origin_effect = gateway.commit(origin_c, bytes.fromhex(origin["signature_hex"]), now + 1)
    denied_clone = _denial(lambda: gateway.challenge(
        "grant-origin", "agent-instance-b", "edge-b", "synthetic-tool", "record", "effect-escape", now + 1))

    # The copy asserts the original identity, but the process has only its OWN device key.
    forged_c = gateway.challenge("grant-origin", "agent-instance-a", "laptop-a",
                                 "synthetic-tool", "record", "effect-escape", now + 1)
    clone = _execute_in_process(copied_snapshot, clone_key, "agent-instance-b", forged_c)
    denied_spoof = _denial(lambda: gateway.commit(
        forged_c, bytes.fromhex(clone["signature_hex"]), now + 2))
    denied_replay = _denial(lambda: gateway.commit(
        origin_c, bytes.fromhex(origin["signature_hex"]), now + 2))

    pending = gateway.challenge("grant-origin", "agent-instance-a", "laptop-a",
                                "synthetic-tool", "record", "effect-after-move", now + 2)
    pending_proof = original_key.sign(pending.signed_bytes())
    next_epoch = gateway.fence("demo-task")
    denied_stale = _denial(lambda: gateway.commit(pending, pending_proof, now + 3))
    gateway.issue_grant("grant-destination", "demo-task", "agent-instance-b", "edge-b",
                        "synthetic-tool", "record", 1100, now + 3)
    dest_c = gateway.challenge("grant-destination", "agent-instance-b", "edge-b",
                               "synthetic-tool", "record", "effect-destination", now + 3)
    destination = _execute_in_process(copied_snapshot, clone_key, "agent-instance-b", dest_c)
    dest_effect = gateway.commit(dest_c, bytes.fromhex(destination["signature_hex"]), now + 4)

    return {
        "security_assurance": "software_only_no_hardware_attestation",
        "separate_worker_processes": origin["worker_pid"] != clone["worker_pid"],
        "portable_snapshot_unchanged": copied_snapshot == snapshot,
        "origin_artifact": origin["artifact"],
        "copied_artifact": clone["artifact"],
        "authorized_origin": origin_effect["status"],
        "copy_without_grant": denied_clone,
        "clone_claims_origin_identity": denied_spoof,
        "replayed_origin_proof": denied_replay,
        "fencing_epoch": next_epoch,
        "old_device_after_fence": denied_stale,
        "authorized_destination_after_rebind": dest_effect["status"],
        "synthetic_effects_committed": gateway.effect_count,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker:
        return _worker()
    report = run_demo()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
