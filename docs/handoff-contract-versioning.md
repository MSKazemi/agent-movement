# Handoff contract decision: executable 0.1 versus proposed 0.2

**Decision record AMV-ADR-001 · 2026-10-17 · Issue [#96](https://github.com/MSKazemi/agent-movement/issues/96)**

## Decision

**Keep `0.1.0-draft` the only executable local handoff envelope.** The published
`0.2.0-draft` JSON Schema remains a **proposal** for the future canonical envelope.
The Python distribution version `0.2.0` is a package release identifier, not a
wire compatibility guarantee. The separately versioned *peer* preflight and A2A
profile are not an implicit implementation of envelope 0.2.

- No automatic 0.1↔0.2 handshake, transparent rewrite at an HTTP/A2A endpoint, or
  automatic fallback. A received 0.2 envelope **must be rejected** by existing
  0.1 runtime endpoints and the current A2A adapter.
- The *only* current migration is an explicit, **offline**, operator-chosen,
  semantics-preserving delegate projection between the tiny common strict
  subset of 0.1 and 0.2.
- Reject any 0.2-only fields, even apparently harmless ones, because they may
  represent policy constraints, lineage, budgets, checkpoints, signatures,
  private artifacts or identity guarantees. Never silently discard them.
- Origin/destination IDs in either envelope are correlation **claims**, not
  authenticated identities. This adapter does not verify signed grants, approvals,
  a principal, a destination, or integrity references. A live receiver must use
  its separate authorized trust boundary.
- Relocation remains a different typed operation with a separate checkpoint
  contract and no 0.2-to-0.1 projection.

The normative source for accepted local requests remains
[`validate_envelope`](../src/agent_movement/core.py). The future proposal is
[`schemas/handoff-envelope.schema.json`](../schemas/handoff-envelope.schema.json).
See [`contract_compat.py`](../src/agent_movement/contract_compat.py) for the
explicit gates and [contract tests](../tests/test_contract_compat.py) for refused
conversions.

## Negotiation and advertised capability matrix

| Verified remote advertisement | Current choice | Why |
| --- | --- | --- |
| `["0.1.0-draft"]` | `0.1.0-draft` | Only executable local envelope |
| `["0.1.0-draft","0.2.0-draft"]` | `0.1.0-draft` | Draft is not executable |
| `["0.2.0-draft"]` | REFUSE | No mutually executable version |
| `["3.0.0"]`, missing, duplicate, invalid | REFUSE | Unknown or untrusted compatibility data |
| A2A 1.x adapter | 0.1 envelope internally | A2A transport version is independent |
| Peer `PEER_SCHEMA_VERSION` | Signed peer protocol | Not a 0.2 core envelope |
| Python package `0.2.0` | no wire implication | Project metadata ≠ transport negotiation |

`negotiate_wire_version` **assumes the versions were already independently
verified** as part of the peer descriptor/endpoint discovery. A raw agent-provided
`supported_versions` array is not trusted proof; this function does not handle
peer authentication.

## Field-by-field crosswalk

| Area | Executable 0.1 | Proposed 0.2 | Offline projection |
| --- | --- | --- | --- |
| `schema_version` | `0.1.0-draft` | `0.2.0-draft` | Explicit label rewrite only |
| `movement_id`, `logical_task_id` | mandatory IDs | mandatory IDs | identical, validated |
| `operation` | `delegate` only | `delegate`, `relocate` | delegate only; relocate REFUSE |
| `parent_movement_id` | absent | nullable lineage | REFUSE even if null |
| `origin.agent_id` | claimed ID | claimed ID | identical; not authentication |
| `origin.execution_id` | absent | optional / required for relocate | REFUSE |
| `destination.agent_id` | claimed ID | claimed ID | identical; not verified audience |
| `destination.endpoint_id` | absent | optional endpoint | REFUSE |
| `task.kind` | `word_count` / `sha256` | receiver-allowlisted ID | old allowlist only |
| `task.text` | required UTF-8 ≤2048 bytes | optional | required and byte-validated |
| `task.goal`, `task.deadline` | absent | optional intent/time constraint | REFUSE |
| `context.classification` | synthetic / public | also internal / confidential | synthetic/public only |
| `context.purpose`, `artifact_refs` | absent | optional policy/data refs | REFUSE |
| `requirements.*` | absent | capability/runtime/checkpoint | REFUSE, including empty |
| `authority.approval_ref` | mandatory ID | mandatory ID | identical; revalidated by receiver |
| `authority.grant_ref`, `expires_at`, `delegation_depth` | absent | optional authority / limits | REFUSE; never drop |
| `execution.idempotency_key` | mandatory ID | mandatory ID | identical |
| `execution.checkpoint_ref`, `fencing_epoch` | absent | optional/relocate-required | REFUSE |
| `execution.max_runtime_seconds`, `max_network_bytes` | absent | optional limits | REFUSE |
| `observability.trace_id` | mandatory ID | mandatory ID | identical |
| `observability.traceparent` | absent | optional trace context | REFUSE |
| `message.*` | absent | optional routing policy | REFUSE |
| `integrity.envelope_digest`, `signature_ref` | absent | optional integrity | REFUSE; cannot verify detached signature |

**Explicitly absent:** verifier-produced facts such as authenticated actor,
signed destination grant, independent data-owner approval, policy epoch,
revocation tombstones, purpose/retention obligations, and tool-side authority.
These cannot be obtained by renaming envelope fields; use the existing peer,
continuity and guarded-authority layers.

## Reproducible migration example

The offline adapter takes a **validated** local `0.1.0-draft` delegate, copies it
to a documentation-only `0.2.0-draft` proposal, then opts into a lossless
projection back. A complete one-to-one roundtrip is checked for identical
canonical values and SHA-256 fingerprints; none of the inputs are production
tasks or credentials.

```sh
python tools/contract_migration_demo.py --json
python -m pytest -q tests/test_contract_compat.py tests/test_handoff_envelope_schema.py
```

For direct programmatic use:

```python
from agent_movement.contract_compat import (
    negotiate_wire_version, project_draft_to_runtime,
)
version = negotiate_wire_version(["0.1.0-draft", "0.2.0-draft"])
assert version == "0.1.0-draft"
# Operator-reviewed, strict common-subset draft ONLY; never raw untrusted wire input:
# runtime_envelope = project_draft_to_runtime(proposal, allow_projection=True)
```

A draft proposal containing even `parent_movement_id: null`, a zero-depth
`authority.delegation_depth`, `integrity`, a task goal, an internal data class,
or a relocate checkpoint is **not convertible** under this decision.

## Testable evolution / reopening this ADR

Support for actual `0.2.0-draft` runtime ingress requires a future separate
decision, version-typed validation, executable verifiers for every retained
authority/policy field, explicit capability advertisement bound to the
authenticated destination, adversarial tests for downgrade/stripping, and
schema-runtime/A2A conformance tests. No network listener may start advertising
0.2 simply because this proposal schema or offline conversion helper exists.
