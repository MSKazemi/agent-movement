# Proposed handoff and relocation contract

**Project design sketch; not an IETF, A2A, MCP, or AG-UI specification; no implementation is claimed.**

## Terminology

- **Logical task ID** (`logical_task_id`): logical work item; remains constant across *permitted* resumptions.
- **Movement ID** (`movement_id`): one attempted transfer, unique and auditable.
- **Execution ID** (`origin.execution_id`, formerly run ID): concrete agent execution instance; changes when relocated.
- **Destination identity**: attested/verified service principal; not just a URL. The envelope's `destination.agent_id` is only a claim.
- **Checkpoint** (`execution.checkpoint_ref`): app-defined explicit state, not arbitrary hidden model thinking or OS RAM.
- **Lease / fencing epoch** (`execution.fencing_epoch`): exclusive authority for one active executor; all side-effecting operations must verify the epoch where feasible.
- **Artifact** (`context.artifact_refs[]`): immutable object with digest, classification, size and fetch policy.
- **Delegation grant** (`authority.grant_ref`): least-privilege authorization for requested work, not copied source credentials.

Field names follow the canonical [handoff envelope](../how-it-works.md#canonical-handoff-envelope-020-draft).

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

## Canonical envelope and relocation profile

This guide does **not** define its own envelope. It uses the canonical [handoff envelope `0.2.0-draft`](../how-it-works.md#canonical-handoff-envelope-020-draft) (schema: [`schemas/handoff-envelope.schema.json`](../../schemas/handoff-envelope.schema.json)); the field table, version policy, the list of renamed fields and the divergences from the implemented core are recorded there. The earlier example in this guide used `authorization.approval_id`, `delegation_ref`, `fence_epoch`, `run_id`, `context.artifacts[].uri` and `integrity.manifest_digest`; see [Envelope field naming (2026-10-16)](../how-it-works.md#envelope-field-naming-2026-10-16) for the canonical names.

The contract in this guide adds these constraints on top of the canonical schema (proposal; no implementation is claimed):

- **Delegation D:** `execution.fencing_epoch` is `null` or absent, and `execution.checkpoint_ref` is `null` or absent.
- **Relocation M** (`operation: "relocate"`): the schema already requires `origin.execution_id`, `requirements.checkpoint_format`, `requirements.runtime_version`, a non-null `execution.checkpoint_ref` and an integer `execution.fencing_epoch`. In addition, the destination accepts only after the coordinator has fenced the origin at a lower epoch (lifecycle step 5), and every side-effecting operation re-checks the epoch.
- **Copy C:** not carried by this envelope; a copy mints a new instance identity and is tracked as its own run (see the table below).
- Budgets (`execution.max_runtime_seconds`, `execution.max_network_bytes`) and `authority.expires_at` are set for every dispatched envelope in this guide's topologies.

Example: a relocation from the topology in [network topologies](network-topologies.md), with budgets and an artifact reference. All values are synthetic.

<!-- envelope-example -->
```json
{
  "schema_version": "0.2.0-draft",
  "movement_id": "mov-guide-001",
  "parent_movement_id": null,
  "logical_task_id": "task-guide-001",
  "operation": "relocate",
  "origin": {"agent_id": "urn:example:worker-a", "execution_id": "exec-A"},
  "destination": {"agent_id": "urn:example:worker-b", "endpoint_id": "approved-001"},
  "task": {"kind": "analyze_document", "goal": "Analyze a public test document", "deadline": null},
  "requirements": {
    "capabilities": ["text-analysis"],
    "checkpoint_format": "example-app-checkpoint-v1",
    "runtime_version": "example-runtime-1.0"
  },
  "context": {
    "classification": "public",
    "artifact_refs": [{
      "ref": "artifact:guide-input-001",
      "sha256": "af7688acddc82b568a78f804c84de44631eee954d4c72a0571da1f6e74042854",
      "size_bytes": 34
    }]
  },
  "authority": {
    "approval_ref": "approval-123",
    "grant_ref": "opaque-bound-grant-identifier",
    "expires_at": "2026-10-15T21:00:00Z"
  },
  "execution": {
    "idempotency_key": "random-task-operation-key",
    "checkpoint_ref": "checkpoint:task-guide-001:step-7",
    "fencing_epoch": 3,
    "max_runtime_seconds": 300,
    "max_network_bytes": 10000000
  },
  "observability": {
    "trace_id": "trace-guide-001",
    "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
  }
}
```

The example validates against the schema; that does not make it production input. Define canonical JSON/CBOR serialization, signature coverage and version policy **before** interoperability claims. Never put raw API keys, OAuth bearer tokens, private chain-of-thought, browser cookies or credential-bearing URLs in an envelope. Short-lived authorization references must be independently resolved with audience binding.

## Contracts by movement type

| Contract area | Delegation D | Copy C | Relocation M |
| --- | --- | --- | --- |
| Logical task identity | New child or associated task, provenance link | New independently tracked run/task | Preserved logical task ID |
| Agent instance identity | Destination's identity | **New** instance identity | **New** runtime instance, same work lineage |
| Snapshot required | Filtered task context | Image/config and separately approved data | **Compatible** app checkpoint |
| Credential handling | Recipient obtains restricted own grant | New grants/identities | Reauthorize scoped target credentials |
| Fencing old worker | Not required | Not required | **Required** for safe exclusivity |
| Retry strategy | Idempotent submission + task-status query | Idempotent deployment | Reconcile and `fencing_epoch` check |
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