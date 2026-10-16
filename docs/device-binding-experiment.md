# HB-E0: Does copying an agent copy its device privileges?

**Recorded:** 2026-10-16. **Status:** runnable synthetic software-key experiment; not a hardware-backed or production security result.

This experiment implements the first phase of [device/hardware binding research](device-and-hardware-binding.md) with two separate local Python subprocesses and a synthetic effect gateway. It asks whether transferring the **agent definition and portable task checkpoint** must also transfer authority to use a protected tool.

## Hypothesis and precise adversary model

An unauthorised clone knows the complete allowlisted synthetic task snapshot, may claim any device or instance identity, may replay observed signatures, and has its **own** software test key. It **cannot** obtain the originating device's key, call its signing operation, modify the independent gateway's pinned key material or self-issue a grant. This key-separation assumption is supplied by the trusted test harness, **not** enforced by hardware or operating-system security.

**Result within the model:** task data remains portable, while privileged tool effects require a new instance-and-device-bound grant and a one-time signed challenge at the target gateway. A clone with only the copied snapshot fails to use the original grant. After the coordinator fences the old epoch and explicitly issues a new grant, the destination can act through its own key.

**Essential counterexample:** an attacker able to copy the original **exportable software key** successfully impersonates the original device and commits a fake effect. Therefore this test does not prove strict physical device binding, non-exportability or any general impossibility of copying an agent.

## Run

Python 3.11+ and pytest; no optional cryptography dependency needed:

~~~sh
python -m pip install -e . "pytest>=9.1"
python -m agent_movement.device_binding_demo
python -m pytest -q tests/test_device_binding.py
~~~

For a no-install demo from the repository root, use PYTHONPATH=src with the Python module invocation.

- [device_binding.py](../src/agent_movement/device_binding.py): in-memory independent effect gateway, task/device/instance/tool-scoped grants, challenge nonce, expiry, HMAC verification, replay checks, revocation, fencing epoch and fake effect deduplication.
- [device_binding_demo.py](../src/agent_movement/device_binding_demo.py): invokes two distinct local worker subprocesses, copies the same synthetic word-count task, attempts spoofing, and performs explicit reauthorization.
- [test_device_binding.py](../tests/test_device_binding.py): 15 focused positive/negative tests, including the successful key-theft counterexample.

Both worker keys are **extractable HMAC software keys** sent from the trusted parent to a chosen subprocess through stdin. The parent/gateway also holds shared secret verification material. Neither the keys nor grant refs are in the portable agent snapshot. The code never accesses real credentials, external networks, files beyond its own program, robots or physical actuators.

## Execution flow

1. The coordinator registers test keys for simulated devices laptop-a and edge-b. Each has a different local software key.
2. It issues a grant bound to the original **agent instance**, its device, a single task, synthetic-tool audience, record action and expiry.
3. The origin process receives a gateway-issued nonce challenge that covers the task, grant, instance, device, tool, action, effect ID, fencing epoch and time. Its signature verifies at the independently configured gateway; a fake effect commits.
4. B receives an unchanged copy of the portable task and computes the same result. Requesting A's grant as B gives binding_mismatch. Claiming A's identity but signing with B's key gives signature_invalid. Replaying A's consumed proof gives challenge_unknown_or_modified.
5. The coordinator advances the task epoch; even an unused legitimate proof signed by A is now stale_epoch.
6. Only after separately issuing a new grant for B does its device key authorize a new fake effect. This is not automatic privilege inheritance.

## Observed results

Tests run on 2026-10-16 in a local Python 3.13.5 / pytest 9.0.2 environment: **15 passed**. The demonstration also produced the following results:

| Operation | Observation |
| --- | --- |
| Origin with correct key, grant and resource scope | synthetic_effect_committed |
| Copied snapshot on a different worker | Same word count (3), no secret or grant field in snapshot |
| Clone using its own device ID on origin grant | binding_mismatch |
| Clone spoofing origin's device ID but signing with clone key | signature_invalid |
| Reuse of a consumed valid origin proof | challenge_unknown_or_modified |
| Origin signed proof after coordinator moves fencing epoch to 2 | stale_epoch |
| Clone after issuance of a new, device-specific grant | synthetic_effect_committed |
| **Attacker possesses a copy of the exportable original software key** (separate test) | **Fake effect succeeds; software-bound restriction bypassed** |
| Total successful demo effects | 2 different synthetic effects, one before and one after authorization transfer |

Other tests cover modified challenge, wrong audience/action, duplicate effect, expired challenge, expired/revoked grant, unknown or duplicate device registration, and a disallowed snapshot field. No hardware tests were run.

## What this result does NOT establish

- **No TPM, Secure Enclave, TEE, HSM or device attestation:** source and destination are separate **subprocesses on one computer**, not separate physical devices. The demonstration does not validate hardware identity or platform measurements.
- **No non-exportability:** origin keys and gateway verification keys are software HMAC secrets; the test proves that stealing a key defeats the restriction. HMAC verifiers can themselves sign.
- **No process/transport boundary proof:** a trusted parent provisions keys through stdin. A malicious parent, compromised original worker, or a clone permitted to use the origin's signer as an oracle can invalidate the restricted threat model.
- **No production enforcement:** grant issuance and device registration are callable in-process and not authenticated as administrative APIs. The tool effect, clock, fencing epochs, nonce state and deduplication are all synthetic, in-memory and not crash-durable. Concurrent process safety has not been established for this new gateway.
- **No general-copy guarantee:** copied definition, prompts, public weights and previously released plaintext can still move. An authenticated device proves key possession only, not that an agent's output or action is safe.

This is a falsifiable **application-authorization** test under stated assumptions, not a vendor attestation result or evidence that agents cannot copy themselves.

## HB-E1: real hardware-backed follow-on, not completed

The available execution environment exposed **no /dev/tpm0, /dev/tpmrm0 or tpm2-tools**. It was therefore not possible to produce a hardware attestation or hardware-backed signing measurement here. A software fallback must not be labelled hardware-secure.

For E1, choose an actual TPM 2.0, Secure Enclave, Android hardware-backed keystore, HSM or attested confidential environment. Generate a non-exportable key and independently verify its claimed provenance, issuer/endorsement chain and (where applicable) nonce-bound attestation and measured workload coverage. Implement a signer/verifier adapter using the **same signed challenge bytes** and target gateway. Repeat the copy, replay, wrong-device, key-extraction, revocation, stale-epoch, key loss, firmware-update and explicit recovery tests. In particular, check whether malware on an authorized host can invoke the hardware signing operation without exporting its key; hardware confinement alone does not enforce an agent's high-level action policy.

For the follow-on distributed experiment, also reuse the repository's existing SQLite transactional fencing/effect gateway, persist nonce and grant state, enforce trusted gateway clocks and authenticated coordinator operations, and inject crashes and network partitions. Publish the precise failure model and negative cases.

## Related documents

[Security and trust](security-and-trust.md) · [Agent forensics](agent-forensics-and-fingerprints.md) · [Device compatibility matrix](device-compatibility-and-capability-matrix.md) · [Architecture](architecture.md).
