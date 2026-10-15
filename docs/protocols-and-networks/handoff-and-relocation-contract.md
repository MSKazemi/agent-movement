# Proposed handoff and relocation contract

**Project design sketch; not an IETF, A2A, MCP, or AG-UI specification; no implementation is claimed.**

## Terminology

- **Task ID**: logical work item; remains constant across *permitted* resumptions.
- **Movement ID**: one attempted transfer, unique and auditable.
- **Run ID**: concrete agent execution instance; changes when relocated.
- **Destination identity**: attested/verified service principal; not just a URL.
- **Checkpoint**: app-defined explicit state, not arbitrary hidden model thinking or OS RAM.
- **Lease / fencing epoch**: exclusive authority for one active executor; all side-effecting operations must verify the epoch where feasible.
- **Artifact**: immutable object with digest, classification, size and fetch policy.
- **Delegation grant**: least-privilege authorization for requested work, not copied source credentials.

## Lifecycle

1. **DISCOVERED**: authenticated endpoint and capability evidence available.
2. **PROPOSED**: validate request, operation type, destination, capabilities, size and residency.
3. **AUTHORIZED**: user/policy approves; issue independently scoped, time-limited access.
4. **PREPARED**: pin app/runtime versions; persist checkpoint or input manifest; validate hashes.
5. **FENCED** (M only): stop origin from new externally visible actions; revoke its lease.
6. **DISPATCHED**: transmit only signed/integrity-verified envelope or references.
7. **ACCEPTED**: recipient validates permissions and schema; no execution yet implied.
8. **RUNNING**: new agent/tool starts with approved budget and operation ID.
9. **RECONCILING**: query durable outcome of operations after retries/crash/partition.
10. **COMPLETED / FAILED / CANCELED / UNKNOWN**: terminal or needs human intervention; report artifacts and evidence.
11. **EXPIRED / REVOKED**: refuse further actions; retain minimum necessary audit lineage.

For ordinary delegation, skip step 5. For copy, mint a new agent-instance identity and separate run/task ownership. For M, an uncertain fence **blocks continuation**, never silently permits two active owners.

## Illustrative envelope (not a wire standard)

~~~json
{
  "schema_version": "0.1.0-draft",
  "movement_id": "mov-unique-id",
  "operation": "delegate",
  "logical_task_id": "task-unique-id",
  "origin": {"agent_id": "urn:example:origin", "run_id": "run-A"},
  "destination": {"agent_id": "urn:example:recipient", "endpoint_id": "approved-001"},
  "task": {"goal": "Analyze a public test document", "deadline": null},
  "requirements": {
    "capabilities": ["text-analysis"],
    "checkpoint_format": null,
    "runtime_version": null
  },
  "context": {
    "classification": "public",
    "artifacts": [{
      "uri": "opaque-scoped-artifact-reference",
      "sha256": "lowercase-hex-digest-of-example-object",
      "size_bytes": 1000
    }]
  },
  "authorization": {
    "approval_id": "approval-123",
    "delegation_ref": "opaque-bound-grant-identifier",
    "expires_at": "2026-10-15T21:00:00Z"
  },
  "execution": {
    "idempotency_key": "random-task-operation-key",
    "fence_epoch": null,
    "max_runtime_seconds": 300,
    "max_network_bytes": 10000000
  },
  "observability": {"traceparent": "00-00000000000000000000000000000000-0000000000000000-01"},
  "integrity": {"manifest_digest": "to-be-specified", "signature": "detached-signature-reference"}
}
~~~

All identifiers and hash fields above are **placeholders**; the example is not schema-valid production input. Define canonical JSON/CBOR serialization, field-level validation, signature coverage and version policy **before** interoperability claims. Never put raw API keys, OAuth bearer tokens, private chain-of-thought, browser cookies or credential-bearing URLs in an envelope. Short-lived authorization references must be independently resolved with audience binding.

## Contracts by movement type

| Contract area | Delegation D | Copy C | Relocation M |
| --- | --- | --- | --- |
| Logical task identity | New child or associated task, provenance link | New independently tracked run/task | Preserved logical task ID |
| Agent instance identity | Destination's identity | **New** instance identity | **New** runtime instance, same work lineage |
| Snapshot required | Filtered task context | Image/config and separately approved data | **Compatible** app checkpoint |
| Credential handling | Recipient obtains restricted own grant | New grants/identities | Reauthorize scoped target credentials |
| Fencing old worker | Not required | Not required | **Required** for safe exclusivity |
| Retry strategy | Idempotent submission + task-status query | Idempotent deployment | Reconcile and lease-epoch check |
| Successful outcome | Task result and receipt | Independent worker running | Verified exclusive continuation |

## Ambiguous network outcomes

Request timeout does not prove no execution. On a retry, query by **stable idempotency key and task ID** first. If a side-effecting tool has no idempotency/reconciliation facility, do not automate a retry; mark status UNKNOWN and seek operator resolution. Exactly-once delivery in a broker does not imply exactly-once operation in an external system.

## Artifact integrity and garbage collection

Use content-addressed immutable snapshots and minimum necessary plaintext. Encrypt at rest and in transit. Track origin/recipient, owner-approved ACL, digest, expiry, encryption key owner, audit event, legal retention and deletion/erasure. Delete temp data after expiry but preserve non-sensitive lineage needed for audit.

## Minimal endpoint operations (proposal)

- discover_capabilities
- prepare_movement
- request_approval
- create_checkpoint / validate_checkpoint
- acquire_lease / fence_origin / transfer_lease (M only)
- dispatch_task / query_task / cancel_task
- fetch_artifact / publish_result
- reconcile_side_effects
- revoke_grant / record_audit_event

Avoid inventing a custom end-to-end RPC protocol until a two-agent A2A integration demonstrates a concrete gap. Link this conceptual contract to A2A tasks, native runtime persistence and independent policy APIs rather than requiring the whole world to adopt it.

See [how it works](../how-it-works.md), [network topologies](network-topologies.md), [security](security-reliability-and-observability.md).