# Hardware/device binding and agent mobility: security research

**Status:** Research proposal; one [software-only synthetic experiment](device-binding-experiment.md) now runs, but no real hardware binding, attestation, audit or production certification has been implemented. **Date:** 2026-10-16.  
**Related:** [security and trust](security-and-trust.md), [how movement works](how-it-works.md), [open questions](open-questions.md), [forensics](agent-forensics-and-fingerprints.md).

## Decision

Bind **privileged capabilities and protected data**, not necessarily all portable agent code or tasks, to a specified device, verified runtime or authorized fleet. Use a risk-adaptive policy; hard-pinning all agents causes lock-in, poor disaster recovery and inability to migrate. Every destination must obtain fresh authorization, not automatically inherit its origin's authority.

Agent definition, logical task, running process, workload identity, device identity, protected state, permissions and user consent are *separate objects*. A moved task does not imply that the same process or identity moved. A clone must have a different instance identity and **no implicitly inherited grants**.

No hardware mechanism can guarantee that plaintext previously available to a process, public weights, prompts, source or behavioral capabilities cannot be copied. Hardware protection primarily constrains operations with hardware-held keys, state decryption, and access to resources protected by cooperating enforcement points. Attestation is evidence about a bounded environment **not proof that a model is safe**.

## Binding spectrum

| Profile | Example | Binding and movement rule |
|---|---|---|
| B0: portable | Synthetic/public summarizer | Approved, authenticated executor + policy; move non-sensitive task envelope freely between approved workers. |
| B1: managed fleet | Corporate private assistant | Reissue least-privilege scoped credentials on trusted managed endpoints; enforce data classification and tenant policy. |
| B2: attested protected | Highly sensitive confidential work | Verify fresh destination attestation and workload key binding before KMS releases synthetic/test secrets or encrypted checkpoint to that endpoint. |
| B3: physical/site restricted | Robot, industrial controller or significant payment tool | Keep actuator/settlement capability hardware/site-bound with independent safety interlocks and approvals; analysis may move, authority does not automatically move. |

**Never use just MAC/IP/hostname/serial/device fingerprint as authorization.** They are spoofable or unstable and raise privacy concerns. A software key/digest can identify a declared build, not a unique physical device. Hardware-backed non-exportable keys (TPM, HSM, Secure Enclave, Android hardware keystore) protect key operations under assumptions, but a compromised authorized operating system might still invoke permitted operations. Secure/measured boot and attestation certify measured properties only; a boot quote by itself does not prove application integrity. SPIFFE/SPIRE may attest nodes and workloads, but not every SPIFFE credential is inherently hardware rooted. TEE/confidential-VM protection and cloud attestation require explicit root-of-trust, measured component coverage, verifier policy, and vendor threat-model evaluation.

## Proposed movement security architecture (not implemented)

1. Identify **delegate / relocate / clone / fork**; create unique movement ID, stable logical task ID, fresh execution ID, intended target, region and data classifications. Explicitly mark side-effect risk.
2. Independent policy engine checks authorized owner, user/tenant approval where needed, allowed destination, purpose, time, budgets, and scope. No agent self-approval of privilege escalation.
3. Verify destination **workload identity and attestation** when required: issuer chain, endorsed roots, fresh nonce, measurements, intended destination/audience, bound ephemeral key and revocation posture. Self-reported Agent Cards do not suffice.
4. Establish destination-bound secure transport, mutually authenticate and verify protocol and checkpoint compatibility. Filter portable state fields; encrypt sensitive checkpoint and release/decrypt only after verified policy and independent KMS checks. Do not transfer raw OAuth tokens, cookies, API keys or private model chain-of-thought.
5. For true *relocation*, durably fence source side-effect authority using a new monotonically increasing epoch checked by **each effectful service**; never treat an application-only lock as sufficient. Where services do not cooperate, no universal single-owner guarantee is possible. Use UNKNOWN/RECONCILE for uncertain external operations.
6. Issue a **new audience-bound, scoped, short-lived** destination grant, never ambient origin credentials. Tool gateways enforce every action, not just the agent's instructions.
7. Record authenticated source/destination receipts, new instance/lineage IDs and tool-side evidence independently; redact sensitive fields. Revocation blocks future cooperating actions but cannot reliably recall plaintext already exposed or undo physical effects.
8. On destination, attestation, verifier, KMS or network failure, **fail closed for high-impact work**; explicitly configure any read-only recovery. Require separate owner recovery/rebinding process for stolen/replaced/upgraded devices.

## Required safety invariants

- **HB-S01:** Default deny movement to unauthenticated or unauthorized destinations; agent-provided metadata is untrusted.
- **HB-S02:** Device attestation is not a claim of correct LLM reasoning. Use a separate policy enforcement point for tools and data release.
- **HB-S03:** A copied envelope, ciphertext or checkpoint must not itself confer privileged credentials or key release.
- **HB-S04:** New host = fresh authorization. Origin privileges never silently transfer; child agents and replicas start without effect authority unless explicitly granted.
- **HB-S05:** For side-effectful relocation, stale epochs are rejected *at the target service*. Without this enforcement, exclusivity is not guaranteed.
- **HB-S06:** Fresh attestations and key releases must be bound to intended recipient, ephemeral key, nonce, audience and task/movement where platform supports it; test relay and replay.
- **HB-S07:** Secret/state sharing follows classification, residency, consent, purpose and least-disclosure policy; telemetry must not leak private context.
- **HB-S08:** Restrict hop count, destinations, concurrency, egress, tokens, time and spending; high-impact or irreversible actions require a separate approval route.
- **HB-S09:** Treat offline, revocation, device loss, stale grants, upgrade mismatch and ambiguous external effects as explicit states; no fail-open downgrade.
- **HB-S10:** Physical actions need independent actuators/interlocks and human emergency stops. Security attestation alone is not functional safety.
- **HB-S11:** Never claim non-exportable keys make an entire agent impossible to copy, or that deleting/revoking credentials erases old plaintext.
- **HB-S12:** Minimize persistent device IDs; log verifiable scoped attestations and signed action receipts with limited retention, not indiscriminate user/device surveillance.

## Example policy (illustrative; not deployable YAML)

```yaml
operation: relocate
profile: B2
allow_destinations: [spiffe://example.test/worker/approved]
state_classification: synthetic
attestation: {required: true, fresh_challenge: true, approved_measurement: DEMO_ONLY}
authorization:
  reissue_short_lived_grant: true
  inheritable: false
  allowed_actions: [read_synthetic_fixture]
  irreversible_actions: deny
  require_fencing_epoch: true
  maximum_hops: 1
failure:
  verifier_unreachable: deny
  stale_epoch: deny
  prior_effect_unknown: reconcile
```

This example does not implement or prove any enforcement; an independent tool/KMS verifier is necessary.

## Important scientific questions and falsifiable tests

| ID | Priority | Question / experiment |
|---|---|---|
| HB-01 | P0 | **What exactly is bound?** Attempt to copy code, encrypted memory, checkpoint, credentials and tool grant separately. Report which copied items retain useful authority. |
| HB-02 | P0 | **Can attestation be relayed/replayed?** Reuse a valid report with an invalid nonce, wrong session/key or destination. Expect independent verifier rejection. |
| HB-03 | P0 | **Can source and destination both act after a partition?** Delay stale worker, advance epoch and require tool-side stale rejection, not simply coordinator logs. |
| HB-04 | P0 | **What is the real software measurement coverage?** Compare platform boot quote, workload attestation and application/TEE measurements for gaps. |
| HB-05 | P0 | **Can a compromised approved host misuse its hardware key?** Exercise permitted key operations from a compromised-but-authorized test harness and define limits. |
| HB-06 | P0 | **Can a revoked offline agent still perform effects?** Test grants, epoch expiry and effect-gateway behavior without network; record bounded stale window. |
| HB-07 | P0 | **Does hardware key binding prevent *code* copying?** Demonstrate distinct properties of key-usage restrictions and copyability of agent definition. |
| HB-08 | P0 | **What happens to decrypted state?** Test snapshots, logs, swaps, backups and copied plaintext; do not promise remote erasure. |
| HB-09 | P1 | **Do different devices share a useful trust vocabulary?** Compare TPM, phone keystore, cloud TEE and HSM claims; reject absent claims rather than assume parity. |
| HB-10 | P1 | **How are updates and device replacement safe?** Simulate key rotation, signed measurements, recovery quorum and forced patching. |
| HB-11 | P1 | **What is the mobility vs lock-in tradeoff?** Benchmark cost, latency, false rejection, recovery, availability and actual blocked unauthorized effects across B0–B2. |
| HB-12 | P1 | **Can delegated consent and budget remain constrained through a chain of hops/clones?** Test descendants for unauthorized scope expansion. |
| HB-13 | P1 | **Can independent, privacy-preserving receipts prove the authorized path?** Compare scoped pseudonyms to permanent tracking identifiers. |
| HB-14 | P1 | **Where do GPU, model API, tool proxy and storage leave the attested boundary?** Trace all plaintext and effects, not only CPU workload. |
| HB-15 | P2 | **Is a standard 'mobility passport' useful?** Prototype a signed receipt linking task, destination, approval, evidence, fencing epoch and scoped actions; make claims about authorized operations only. |
| HB-16 | P2 | **Which end-to-end safety guarantees can be formally checked?** Model-check state machine under bounded crashes/partitions; specify assumptions and uncovered real-world effects. |

## Test roadmap

**E0 (now):** Two local sandbox agents, mock verifier clearly labeled **non-cryptographic test evidence**, synthetic task/state and fake tool. Deny forged destination, stale grant, replayed movement, clone with inherited grant, disallowed region and wrong audience. Record independently enforced tool effects.

**E1:** On available hardware, compare software-held vs non-exportable hardware key. Test copying to another host, while documenting compromised authorized-host limitations.

**E2:** On one chosen attested platform, independently verify fresh evidence and bind a synthetic secret release to destination ephemeral key and policy. Negative tests: stale evidence, incompatible measurements, relay, wrong key and revoked permission.

**E3:** Introduce epochs, tool-side fence, crash/partition at every transition, recovery/replace/patch and cross-platform measurement interoperability. Publish failures, not just successes.

**Metrics:** false accept/deny; unauthorized key releases and target-side effects (target zero in defined attack suite, **not a proof of zero risk**); time-to-revoke; p95 mobility latency; recovery; attestation overhead; privacy leakage and energy/cost.

## Sources and status of claims

The following cover **building blocks**, not an off-the-shelf secure agent-mobility standard. The B0–B3 profiles, invariants and tests are **project proposals**.

- [IETF RFC 9334: Remote ATtestation procedureS (RATS) Architecture](https://www.rfc-editor.org/rfc/rfc9334.html).
- [NIST SP 800-207 Zero Trust Architecture](https://csrc.nist.gov/pubs/sp/800/207/final).
- [SPIRE node/workload attestation](https://spiffe.io/docs/latest/spire-about/spire-concepts/).
- [Microsoft TPM overview](https://learn.microsoft.com/en-us/windows/security/hardware-security/tpm/trusted-platform-module-overview).
- [Android hardware-backed key attestation](https://source.android.com/docs/security/features/keystore/attestation).
- [Apple Secure Enclave protected keys](https://developer.apple.com/documentation/security/protecting-keys-with-the-secure-enclave).
- [AWS Nitro Enclaves KMS attestation](https://docs.aws.amazon.com/enclaves/latest/user/kms.html).
- [OAuth 2.0 Token Exchange, RFC 8693](https://www.rfc-editor.org/rfc/rfc8693).
