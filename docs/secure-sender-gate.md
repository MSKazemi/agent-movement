# Synthetic peer sender gate: local pre-disclosure enforcement

**Reviewed:** 2026-10-16. **Status:** Experimental, explicitly opt-in. **Issue:** #50. This document describes a narrow improvement for `PeerClient.handoff`, not universal containment or production security.

## What changes

An operator-created `OutboundGate` is checked **before the first discovery request**. It binds:

- exact destination agent ID **and** endpoint to an operator-owned allowlist;
- allowed task capability and data classification;
- a CA-verified origin card and proof that the origin signer actually holds the advertised key (not merely the same key ID);
- a grant validated against pinned issuer keys, actor, audience, task, capability, classification and time;
- a trusted **boolean** grant-revocation callback, with any error or non-boolean value treated as denial;
- an optional requirement that the destination card supports HPKE task delivery; the existing peer client refuses plaintext downgrade if this is enabled.

The caller cannot replace these checks with `authenticated: true`, choose an unlisted destination, or supply a fake grant and still get the opt-in client to issue even a discovery request. All denials use a sanitized sender event with `stage=outbound_gate` and `payload_sent=false`.

This does **not** remove the independent receiver checks. `PeerReceiver` continues to validate the signed peer/grant at preflight and delivery and, for a provisioned continuity runtime, revalidates signed consents, epoch, manifest and revocation inside the same SQLite write transaction as the **simulated effect**.

## Local API boundary

`src/agent_movement/sender_gate.py` provides immutable `OutboundGate`. A trusted supervisor provisions allowed identity/endpoint pairs and a locally trusted revocation checker, then passes it into:

```python
PeerClient(
    origin_card, origin_signing_key, pinned_trust, transport,
    outbound_gate=outbound_gate,
    secure_test_mode=True,
)
```

Construction with `secure_test_mode=True` but no gate fails. Existing non-secure experiments remain backwards-compatible and do **not** implicitly acquire this boundary. The gate must be created by a trusted supervisor, not from task/prompt JSON; the receiver authority must be independently configured. `OutboundGate.require_confidentiality=True` requires an encryption-capable destination; the default is **not confidential** on the synthetic plaintext transport.

The peer `handoff` operation is currently only `delegate`; the gate itself explicitly denies attempted `clone`, `fork`, `relocate`, `replicate` or any other operation.

## Adversarial checks (no real user data)

```sh
python -m pytest -q tests/test_sender_gate.py tests/test_peer.py tests/test_continuity_runtime.py
```

The tests verify a successful synthetic handoff followed by a single receiver-checked simulated effect; blocked unknown destination, disallowed classification/capability, wrong-task/audience/actor, forged issuer, expired/not-yet-valid grant, spoofed origin key with the same `kid`, revoked grant, unavailable revocation source, attempted non-delegation, and a confidentiality refusal. For **pre-disclosure denials**, `RecordingTransport.paths()` is empty and the synthetic canary is absent from `transmitted()`.

A deliberate **red/green control** exercises the same wrong-audience grant through the legacy unguarded `PeerClient` and the guarded client. The legacy client contacts the receiver and transmits signed metadata before the receiver refuses; the guarded client refuses without sending any request. In neither case does the task text leave on the denied path. This is a measurable preflight metadata/privacy improvement, not a bypass-proof guarantee.

## Trust assumptions, remaining work and failure modes

- **Complete mediation is not established.** Only calls to the configured `PeerClient.handoff` are guarded. Direct `build_preflight`, raw network access, legacy HTTP, the independent A2A adapter, checkpoint relocation, other processes/listeners and real tools are not restricted by this Python class. A hostile Python agent running with the same rights can instantiate another client or call sockets directly.
- The operator controls the allowlist, pinned key/verifier trust and revocation callback. The callback must check up-to-date independent authority; a dishonest, stale or misconfigured callback makes sender policy incorrect. Callback failure denies safely. A race after the callback remains possible and is handled only by independent recipient/effect checks.
- A locally verified recipient Agent Card proves key/issuer relationships *under the pinned synthetic trust assumptions*, not remote host integrity, possession of real physical hardware or broad interoperability.
- The receiver's simulated SQLite effect does **not** guarantee exactly-once behavior at uncontrolled third-party services.
- The sender gate cannot undo previously transmitted task data or side effects. Disallowed metadata is withheld **only** if this client is used and its trusted gate is installed **before the call**.
- This experiment uses synthetic/public task text and disposable local keys, and does not assert confidentiality absent HPKE.
- For the next claim about a deliberately malicious *independent process*, use the separate Linux isolation and constrained pipe-broker experiment (PR #87) with explicit syscall/UID/filesystem limitations. Connect that experiment to the sender-gated path when reviewing issue #50.
- Keep Issue #50 **open**: independently controlled egress, direct adapter bypass tests, strong provisioning/role separation, real tool-side enforcement and stronger multi-host claims remain unresolved.

## Acceptance gate for this increment

The scoped claim is satisfied only if sender pre-disclosure negative tests, the unguarded red/green control, receiver continuity tests, full package regressions and CI all pass. Do not describe a green result as formally verified or universally bypass-resistant.
