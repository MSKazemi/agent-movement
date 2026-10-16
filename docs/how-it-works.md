# How Agent Movement could work (proposal; not implemented)

## Operational definition

An origin agent transfers a **specific task or resumable boundary** to a destination agent under a bounded authorization grant, and records the resulting artifacts and state transitions. The project should distinguish *delegation* from *checkpoint relocation*. Transfer is an application protocol, not magic migration of a language model.

## Illustrative lifecycle

1. **Describe** goal, data classification, deadline, capabilities and acceptable side effects.
2. **Discover** destination via an authenticated, allowlisted discovery mechanism; A2A Agent Cards can advertise supported capabilities but are not proof of trust.
3. **Negotiate** the [handoff envelope](#canonical-handoff-envelope-020-draft) schema version, runtime support, artifact access and degraded-mode semantics.
4. **Authorize** by policy and, where appropriate, a human approver; never forward the origin's raw credentials.
5. **Checkpoint** only at a safe boundary; persist immutable task snapshot and idempotency keys.
6. **Dispatch** via A2A task communication (or local adapter), with scoped credential exchange and encrypted transport.
7. **Execute** with least-privilege tool access (MCP may expose tools), telemetry and resource/time budgets.
8. **Reconcile** after timeouts: query task status, avoid blind replay of irreversible operations. (Prototyped for one case in the [checkpoint relocation](checkpoint-relocation.md#operator-reconciliation-of-parked-effects-issue-30) experiment: an effect whose outcome cannot be queried is parked, an operator records `confirmed_done` or `confirmed_absent` at the current ownership epoch, and only then does the owner resume, without re-execution or with one retry under a new effect ID. The decision is audited, not verified.)
9. **Return** artifacts, statuses and sanitized provenance; origin validates contract and acknowledges completion.
10. **Expire/revoke** delegated authority, enforce retention and keep an audit trail.

## Canonical handoff envelope (`0.2.0-draft`)

**Status:** a project proposal, not a published or interoperable wire standard. This section is the **single owner** of the handoff envelope: its name, version, field table and JSON Schema ([`schemas/handoff-envelope.schema.json`](../schemas/handoff-envelope.schema.json)). The [protocol guide's contract](protocols-and-networks/handoff-and-relocation-contract.md#canonical-envelope-and-relocation-profile) and the [communication policy](agent-communication-and-policy.md#envelope-for-delegate-and-move-messages) reference it and add only the constraints listed there; they do not define envelopes of their own. Only a strict subset is implemented (see [Divergences from the implemented contract](#divergences-from-the-implemented-contract)).

**Name.** "Handoff envelope" is the single name. "Task envelope", "versioned envelope", "movement envelope" and "portable handoff envelope" refer to this envelope and are retired as names ([glossary](glossary.md), deferred decision T6 of issue #45).

**Version.** `schema_version` is `"0.2.0-draft"`, and it is the only version string of this envelope. Reasons (ANALYSIS):

- `0.1.0-draft` already named two incompatible shapes: the earlier sketch in this document and the protocol guide's example, and a third shape is the one that `src/agent_movement/core.py::SCHEMA_VERSION` (`"0.1.0-draft"`) enforces. Reusing that string would make one version denote three wire shapes, and a receiver could not tell them apart.
- The renames below are breaking changes. Under SemVer 2.0.0 a `0.y.z` version is for initial development and "Anything MAY change at any time" (§4), so a breaking change bumps the minor number: `0.1` becomes `0.2`.
- The `-draft` pre-release suffix is kept, because a pre-release "indicates that the version is unstable" (§9). Source: [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html), accessed 2026-10-16.
- Other repository schemas keep their own version strings (for example the lifecycle observation, the A2A profile URI and the checkpoint-relocation profile). They are separate contracts, not this envelope.

### Field table

All objects are closed: an unknown member anywhere is rejected (`additionalProperties: false`), as `core.validate_envelope` does. IDs use the syntax of `core.ID`: a letter, then up to 127 of `A-Z a-z 0-9 . _ : -`.

| Field | Type and constraint | Required | Meaning |
| --- | --- | --- | --- |
| `schema_version` | const `"0.2.0-draft"` | yes | Envelope version (see above). |
| `movement_id` | ID | yes | One attempted source-to-destination transfer; new for every attempt. |
| `parent_movement_id` | ID or null | no | Lineage link to the movement this one continues. |
| `logical_task_id` | ID | yes | Stable logical task identity across movements and executions. |
| `operation` | `delegate` or `relocate` | yes | Delegation keeps ownership at the origin; relocation is checkpoint relocation and adds the conditional rules below. |
| `origin.agent_id` | ID | yes | Origin agent. A claim for correlation, not an authenticated identity. |
| `origin.execution_id` | ID | relocate | The origin's concrete execution. |
| `destination.agent_id` | ID | yes | Destination agent. A claim, not an authenticated identity. |
| `destination.endpoint_id` | ID | no | Allowlisted endpoint registration, not a URL. |
| `task.kind` | ID | yes | Requested action, from a receiver-side allowlist. |
| `task.text` | string | no | Inline input. The implemented profile requires it and bounds it to 2048 UTF-8 bytes. |
| `task.goal` | string, min length 1 | no | Human-readable goal. Never credentials or private reasoning. |
| `task.deadline` | RFC 3339 date-time or null | no | Deadline for the result. |
| `context.classification` | `synthetic`, `public`, `internal`, `confidential` | yes | Data class of everything the envelope carries or references. |
| `context.purpose` | ID | no | Declared purpose, for purpose and residency policy. |
| `context.artifact_refs[]` | `{ref, sha256, size_bytes?}` | no | Opaque artifact references with content digests. A `ref` is resolved under a separate ACL and is never a pre-authenticated URL. |
| `requirements.capabilities[]` | ID | no | Capabilities the destination must support. |
| `requirements.checkpoint_format` | ID or null | relocate | Checkpoint format that the destination must restore. |
| `requirements.runtime_version` | ID or null | relocate | Pinned runtime version for the checkpoint. |
| `authority.approval_ref` | ID | yes | Reference to the approval record (policy decision, plus human approval where required) that authorizes this transfer. |
| `authority.grant_ref` | ID | no | Opaque reference to a scoped, short-lived delegation grant. Never a bearer token or a raw credential. In the peer-authentication prototype the grant carries a signed `max_uses` (default 1); idempotent retries do not consume a use (`src/agent_movement/peer.py`). |
| `authority.expires_at` | RFC 3339 date-time | no | Expiry of the authority carried by this envelope. |
| `authority.delegation_depth` | integer ≥ 0 | no | Hops of transitive delegation so far. |
| `execution.idempotency_key` | ID | yes | Deduplication key for retries of this transfer. The implementation scopes it per (sender, key): two senders may use the same key, while `movement_id` stays globally unique (`src/agent_movement/core.py`, store schema v1). |
| `execution.checkpoint_ref` | ID or null | relocate | Reference to the approved application checkpoint. The checkpoint is a separate contract and is never embedded. |
| `execution.fencing_epoch` | integer ≥ 1 or null | relocate | Monotonic coordinator epoch that fences the previous executor. |
| `execution.max_runtime_seconds` | integer ≥ 1 | no | Runtime budget. |
| `execution.max_network_bytes` | integer ≥ 0 | no | Network budget. |
| `observability.trace_id` | ID | yes | Correlation ID. Not a credential and not proof of identity. |
| `observability.traceparent` | W3C `traceparent`, version `00` | no | [W3C Trace Context](https://www.w3.org/TR/trace-context/) header value, if present. |
| `message.message_id` | ID | with `message` | Communication-policy extension: one message that carries this envelope. |
| `message.parent_message_id` | ID or null | no | Reply/causality link between messages. |
| `message.expires_at` | RFC 3339 date-time | no | Delivery TTL of the message; separate from `authority.expires_at`. |
| `integrity.envelope_digest` | 64 lowercase hex | with `integrity` | SHA-256 of `agent_movement.core.canonical` applied to the envelope without its `integrity` member. This is the digest that core already puts in receipts as `envelope_digest`. That canonical form (sorted keys, no whitespace, UTF-8) is not claimed to be RFC 8785; the repository's JCS subset is `agent_movement/jcs.py`. |
| `integrity.signature_ref` | ID | no | Reference to a detached signature over the digest. |

**Conditional rules for `operation: "relocate"`:** `origin.execution_id`, `requirements.checkpoint_format`, `requirements.runtime_version`, `execution.checkpoint_ref` (non-null) and `execution.fencing_epoch` (an integer ≥ 1) are required. An uncertain fence blocks continuation; see [checkpoint relocation](checkpoint-relocation.md).

**Never in an envelope:** raw API keys, OAuth bearer tokens, session cookies, passwords, credential-bearing URLs or private chain-of-thought. Messages and artifacts are separate objects that are policy-filtered on their own; the envelope carries only references to them.

### Examples

The test [`tests/test_handoff_envelope_schema.py`](../tests/test_handoff_envelope_schema.py) extracts every JSON block marked `<!-- envelope-example -->` from `docs/` and validates it against the schema. To check a file by hand: `python3 tools/schema_subset.py schemas/handoff-envelope.schema.json my-envelope.json`. The validator is stdlib-only and supports a documented keyword subset of JSON Schema 2020-12.

Minimal envelope: exactly the implemented profile, with the canonical version string. With `schema_version` set to `0.1.0-draft`, `core.validate_envelope` accepts it unchanged (checked by the test).

<!-- envelope-example -->
```json
{
  "schema_version": "0.2.0-draft",
  "movement_id": "mov-example-001",
  "logical_task_id": "task-example-001",
  "operation": "delegate",
  "origin": {"agent_id": "agent-a"},
  "destination": {"agent_id": "agent-b"},
  "task": {"kind": "word_count", "text": "synthetic agent movement test task"},
  "context": {"classification": "synthetic"},
  "authority": {"approval_ref": "approval-task-example-001"},
  "execution": {"idempotency_key": "op-mov-example-001"},
  "observability": {"trace_id": "trace-mov-example-001"}
}
```

Full delegation, for the example story below. Every value is synthetic. The artifact digest is the SHA-256 of the 34 bytes `synthetic public patch for review\n`, the `traceparent` value is the example from W3C Trace Context §3.2.3, and `envelope_digest` is computed as defined above (the test recomputes it).

<!-- envelope-example -->
```json
{
  "schema_version": "0.2.0-draft",
  "movement_id": "mov-example-002",
  "parent_movement_id": null,
  "logical_task_id": "task-example-002",
  "operation": "delegate",
  "origin": {"agent_id": "urn:example:origin", "execution_id": "exec-origin-1"},
  "destination": {"agent_id": "urn:example:reviewer", "endpoint_id": "endpoint-approved-001"},
  "task": {"kind": "review_patch", "goal": "Review the supplied public code patch", "deadline": "2026-10-16T18:00:00Z"},
  "context": {
    "classification": "public",
    "purpose": "synthetic_research_demo",
    "artifact_refs": [{
      "ref": "artifact:patch-001",
      "sha256": "af7688acddc82b568a78f804c84de44631eee954d4c72a0571da1f6e74042854",
      "size_bytes": 34
    }]
  },
  "requirements": {"capabilities": ["code-review"], "checkpoint_format": null, "runtime_version": null},
  "authority": {
    "approval_ref": "approval-example-002",
    "grant_ref": "grant-opaque-example-002",
    "expires_at": "2026-10-16T18:00:00Z",
    "delegation_depth": 0
  },
  "execution": {
    "idempotency_key": "op-mov-example-002",
    "checkpoint_ref": null,
    "fencing_epoch": null,
    "max_runtime_seconds": 300,
    "max_network_bytes": 10000000
  },
  "observability": {
    "trace_id": "trace-mov-example-002",
    "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
  },
  "integrity": {
    "envelope_digest": "a97b5048cdb1cf3889f9a9430e6989c290f65892c45648a94e6d436cb47095aa",
    "signature_ref": "sig-example-002"
  }
}
```

Checkpoint relocation (proposal; core does not accept `relocate`):

<!-- envelope-example -->
```json
{
  "schema_version": "0.2.0-draft",
  "movement_id": "mov-example-003",
  "parent_movement_id": "mov-example-002",
  "logical_task_id": "task-example-003",
  "operation": "relocate",
  "origin": {"agent_id": "worker-a", "execution_id": "exec-worker-a-1"},
  "destination": {"agent_id": "worker-b"},
  "task": {"kind": "resume_checkpoint"},
  "context": {"classification": "synthetic"},
  "requirements": {"checkpoint_format": "example-app-checkpoint-v1", "runtime_version": "example-runtime-1.0"},
  "authority": {"approval_ref": "approval-example-003"},
  "execution": {
    "idempotency_key": "op-mov-example-003",
    "checkpoint_ref": "checkpoint:task-example-003:step-4",
    "fencing_epoch": 2
  },
  "observability": {"trace_id": "trace-mov-example-003"}
}
```

### Envelope field naming (2026-10-16)

Issue #33 reconciled three envelope definitions. These old names are retired; use the canonical name. The protocol guide and the communication policy now use only the canonical names.

| Old name | Where it was used | Canonical name |
| --- | --- | --- |
| `schema_version: "0.1.0-draft"` (doc sketches), `"agent-communication/0.1-proposal"` | this document, protocol guide, communication policy | `schema_version: "0.2.0-draft"` |
| `task.id`, `task_id` | this document, communication policy | `logical_task_id` |
| `origin.run_id`, `run_id` | this document, protocol guide | `origin.execution_id` |
| `authorization` (block), `delegation` (block) | protocol guide, communication policy | `authority` |
| `approval_id` | protocol guide | `authority.approval_ref` |
| `delegation_ref` | protocol guide | `authority.grant_ref` |
| `delegation.depth` | communication policy | `authority.delegation_depth` |
| `fence_epoch`, `lease_epoch`, "epoch" | protocol guide, observability event | `execution.fencing_epoch` (glossary decision T13 in issue #45) |
| `execution.required_capabilities` | this document | `requirements.capabilities` |
| `context.artifacts[].uri`, `context.artifact_refs` as strings | protocol guide, communication policy | `context.artifact_refs[]` objects `{ref, sha256, size_bytes}` |
| `context.messages`, `context.inline_data` | this document, communication policy | removed: messages are separate policy-filtered objects; inline input is `task.text` |
| `integrity.digest`, `integrity.manifest_digest` | this document, protocol guide | `integrity.envelope_digest` |
| `integrity.signature` | protocol guide | `integrity.signature_ref` |
| `kind: "DELEGATE"` | communication policy | `operation: "delegate"` (`MOVE/CHECKPOINT_TRANSFER` maps to `"relocate"`) |
| `sender_claim`, `recipient_claim` | communication policy | `origin.agent_id`, `destination.agent_id` (still claims, not proofs) |
| `requested_action` | communication policy | `task.kind` |
| `delivery.idempotency_key`, `delivery.trace_id` | communication policy | `execution.idempotency_key`, `observability.trace_id` |
| `message_id`, `parent_message_id`, `delivery.expires_at` | communication policy | `message.message_id`, `message.parent_message_id`, `message.expires_at` |
| `approval_ref: null` | communication policy | `authority.approval_ref` is always required; it references the policy approval even when no human approval is needed |

### Divergences from the implemented contract

Checked on 2026-10-16 against `src/agent_movement/core.py` (`SCHEMA_VERSION`, `ID`, `MAX_TEXT`, `parse_json`, `validate_envelope`, `Approval`, `SQLiteStore.receive`, `EffectGateway`). FACT unless marked. No code was changed by issue #33.

**What matches.** Core requires exactly the 11 required members of this schema, with one required member in each of `origin`, `destination`, `context`, `authority`, `execution` and `observability`. The field names are identical, and the ID syntax is the same (`core.ID` uses `fullmatch` with `\Z`; the schema pattern is anchored the same way, and the validator rewrites `$` to `\Z`). Apart from `schema_version`, every envelope that core accepts is valid against the schema; the test checks this for a core-accepted envelope and for the receipt fixture `tests/fixtures/movement-receipts/01-valid-delegation/subjects/env-mov-valid-1.json`.

| # | Divergence | Canonical envelope | Implemented (`core.py`) |
| --- | --- | --- | --- |
| D1 | Version | `"0.2.0-draft"` | `SCHEMA_VERSION = "0.1.0-draft"`; any other value is rejected |
| D2 | Operations | `delegate`, `relocate` | `delegate` only. Relocation is a separate prototype (`relocation.py`) that does not use this envelope |
| D3 | Optional members | allowed (see the field table) | rejected: `_fields` requires the exact member set, so `parent_movement_id`, `requirements`, `message`, `integrity`, `origin.execution_id` and the other optional members all fail |
| D4 | `task.text` | optional, no length bound in the schema | required; at most `MAX_TEXT` = 2048 UTF-8 bytes; lone surrogates rejected. JSON Schema `maxLength` counts characters, not bytes, so the byte bound is left to the implementation |
| D5 | `task.kind` | any ID | `word_count` or `sha256` only |
| D6 | `context.classification` | 4 values | `synthetic` or `public` only |
| D7 | Wire-level checks | not expressible in JSON Schema | `parse_json` rejects duplicate keys, `NaN`/`Infinity` and bodies over 16384 bytes. A validator that sees parsed JSON cannot detect duplicate keys |
| D8 | Integrity | optional in-envelope `integrity.envelope_digest` | no `integrity` member; the digest is computed by the receiver (`digest(envelope)`) and stored in the receipt as `envelope_digest`. For envelopes without `integrity` both definitions give the same value |
| D9 | Approval and grant | `approval_ref` required, `grant_ref` optional | `approval_ref` is matched against a preconfigured receiver-side `Approval` record (which the docstring calls a grant). `grant_ref` resolution, audience binding and `expires_at` in the envelope are not implemented; expiry lives in `Approval.expires_at` |
| D10 | Fencing name outside the envelope | `fencing_epoch` | `EffectGateway.transfer/commit` take `expected_epoch`/`epoch`, and the SQLite tables `owners`/`effects` have an `epoch` column. These are internal names, not serialized envelope fields. `receipts.py` already serializes `effect.fencing_epoch` |

**Proposed code changes (not made; for the `src/` owner, issues #18–#42).** Each needs its own issue and tests.

1. Move `core.SCHEMA_VERSION` to `"0.2.0-draft"`, or accept both strings during a transition. This changes `envelope_digest` values and therefore the frozen artifacts that embed the version: `tests/fixtures/movement-receipts/*/subjects/env-*.json`, the MobilityBench v0.1 `contract_version`, and the A2A Agent Card `params.schema_version` (`a2a_server.py`). The A2A profile URI (`a2a_profile.py::EXTENSION_URI`) is a separate profile version and can stay as it is.
2. Decide D3: either accept the optional members (validating them as the schema does) or keep the strict profile and document it as the "core profile" of `0.2.0-draft`. A strict profile is the safer default for a receiver; accepting members that are then ignored would be fail-open.
3. If `integrity` is accepted, verify `integrity.envelope_digest` equals `digest(envelope without integrity)` and reject on mismatch.
4. Optionally rename the `EffectGateway` parameters `epoch`/`expected_epoch` to `fencing_epoch`/`expected_fencing_epoch` (Python API only; no wire change).
5. Optionally load `schemas/handoff-envelope.schema.json` in a core test, so the schema and `validate_envelope` cannot drift apart silently.

## Example story

A coding agent on a developer workstation asks an isolated reviewer agent to inspect a *public* code patch. The origin records the requested task and input digest, sends it over A2A, receives a structured review artifact, and links it to its trace. If the reviewer crashes, the origin checks task status before re-issuing. The reviewer never receives the user's local shell credentials.

## Key failure scenarios

- **Recipient unavailable:** retry with bounded backoff or choose new destination, retaining same logical operation.
- **Incompatible checkpoint:** reject checkpoint relocation; permit explicit re-execution as a new task only with approval.
- **Duplicate submission:** idempotency key and reconciliation; cannot assume exactly-once external side effects.
- **Revoked approval:** abort future actions and communicate partial outcomes.
- **Poisoned context/tool output:** validate data provenance and maintain instruction/data boundaries.
- **Data residency conflict:** block destination before transfer.
- **Network partition:** preserve ambiguous status, never claim success without evidence.

## Protocol responsibility mapping

A2A = remote agent task conversations; MCP = tool/data interfaces; AG-UI = user-facing updates; LangGraph/Temporal = runtime-specific durability; OCI/Kubernetes = process deployment; IAM/policy layer = access control; OpenTelemetry = audit correlation.

References: [landscape](research-landscape.md), [security](security-and-trust.md), [sources](sources.md).
