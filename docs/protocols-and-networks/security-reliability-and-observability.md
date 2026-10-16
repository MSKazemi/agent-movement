# Security, reliability and observability of networked agent movement

**Design guidance only; not a security audit or certification.**

## Threat surfaces

| Boundary / failure | Attack or fault | Required mitigation / test |
| --- | --- | --- |
| Discovery / registry | Fake Agent Card or poisoned DNS | Signed/verified endpoint ownership, explicit destination allowlist, pinned trust policy |
| Endpoint input | SSRF to loopback/metadata service | Deny private/link-local/reserved destinations unless expressly approved; recheck redirects and DNS resolution |
| Transport | Eavesdropping, relay misuse, downgrade | TLS 1.3 where feasible, mTLS or equally strong workload identity where appropriate; verify peer name |
| Authorization | Confused deputy, overly broad token | Explicit action and audience-bound short-lived grant; OAuth token exchange can help but is not universal authentication |
| Context packaging | Private memory/secrets inadvertently shared | Default-deny classification, field-level minimization, secret scanning, human approval |
| Prompt injection | Tool/page/peer tries to override instructions | Treat untrusted text as data, keep policy and tools outside prompt-only control |
| Code delivery | Unsigned agent image, malicious skill | Signed releases, SBOM/provenance, digest verification, limited runtime sandbox |
| Checkpoint restore | Malicious deserialization / schema mismatch | Use safe formats, strict schema, resource/version compatibility, integrity verification |
| Task duplication | Timeout, broker redelivery, split brain | Stable operation ID, durable inbox/outbox, lease fencing, idempotent effects, reconciliation |
| Cancellation | Origin revokes after destination queues work | Short grant TTL, revocation check at action time, cancellation propagation, failsafe |
| High-impact device | Agent commands unsafe motion or physical actions | Separate local safety controller, owner permission, simulation-first, hard stop and bounded interfaces |
| Auditing | Sensitive logs or missing evidence | Trace redaction, access control, immutable event digests, retention policy |
| Resource exhaustion | Unbounded spawning, giant artifacts | Limits on concurrency, CPU/GPU, messages, bandwidth, tokens, storage and costs |

## Identity is not the same as reachability

mTLS/SPIFFE can attest workload identity, but it cannot prove task-level authorization. OAuth 2.0 and RFC 8693 token exchange can enable delegated scopes, subject to implementation and recipient policy. DPoP (RFC 9449) and OAuth mTLS (RFC 8705) are possible proof-of-possession mechanisms; use only where the relevant systems support them. VPN, WireGuard or a service mesh secures connectivity, but **does not** authorize an agent's behavior.

## Delivery and replay model

1. Origin records intent and stable operation ID in a **durable outbox** before send.
2. Destination durably records received key in an **inbox** before accepting.
3. Destination acknowledges *acceptance*, separate from *completion*.
4. For external operations, log intent, acquire required lease, perform action with supported idempotency key and log observed result.
5. After crash/timeout, reconcile with provider/device before deciding to retry.
6. Relocation requires old worker fenced, new epoch issued and target runtime checkpoint validation.
7. Retention and cleanup expire artifact grants without deleting legitimate audit lineage.

No generic exactly-once guarantee across arbitrarily unreliable networks and arbitrary external systems should be claimed. At-least-once delivery can be useful when deduplication is robust; at-most-once delivery avoids duplicate deliveries but can lose work.

## Observability (minimum event schema, proposal)

This is an audit event, not an envelope. Fields that also occur in the [handoff envelope](../how-it-works.md#canonical-handoff-envelope-020-draft) use its canonical names (`movement_id`, `logical_task_id`, `operation`, `execution_id`, `fencing_epoch`, `trace_id`); `origin_agent_id` and `destination_agent_id` are the names of the implemented receipt (`src/agent_movement/core.py`), and `policy_decision_ref` follows the [glossary](../glossary.md).

~~~json
{
  "timestamp": "2026-10-15T19:00:00Z",
  "movement_id": "mov-123",
  "logical_task_id": "task-123",
  "origin_agent_id": "agent-A",
  "destination_agent_id": "agent-B",
  "event": "dispatch_accepted",
  "operation": "delegate",
  "execution_id": "exec-B",
  "fencing_epoch": null,
  "trace_id": "example-trace-id",
  "transport": "a2a-https",
  "policy_decision_ref": "policy-123",
  "bytes_sent": 2700,
  "outcome": "accepted"
}
~~~

Do not log raw message contents by default. Correlate W3C Trace Context / OpenTelemetry where supported. Track: handoff p50/p95 latency, payload bytes, resumes, compatibility refusal, endpoint failures, duplicate effects, unapproved accesses, audit completeness, checkpoint restore failures, and egress costs.

## Minimum abuse and fault tests

- Destination spoof / malicious redirect / mismatched TLS peer
- Reject unauthorized host and changed DNS resolution
- Expired, revoked, wrong-audience or overscoped delegation grant
- Context leakage and secret-bearing artifact URL rejection
- Payload hash/signature tampering; unsafe checkpoint deserialization
- Invalid/unknown schema and incompatible runtime
- Network lost before send, after acceptance, during execution and after side effect
- Broker duplicate / out-of-order message / stale lease epoch
- Crash immediately before and after every durable state transition
- Long offline partition: explicitly UNKNOWN, not dual executor
- High-risk actuator request denied and local failsafe tested in simulation
- Tenant isolation, retention expiry, telemetry redaction

## Recommended guardrails for initial research

No worm-like self-copying, unsolicited installation or unauthorized scans; no credentials inside migratable state; no bypassing device/app store restrictions; no use of real physical machinery or irreversible tools without separate safety review. Use only enrolled test devices, synthetic data, simulation, scoped identities and public fixtures.

See [existing threat model](../security-and-trust.md) and [primary sources](primary-sources.md).