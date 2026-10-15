# How Agent Movement could work (proposal; not implemented)

## Operational definition

An origin agent transfers a **specific task or resumable boundary** to a destination agent under a bounded authorization grant, and records the resulting artifacts and state transitions. The project should distinguish *delegation* from *checkpoint relocation*. Transfer is an application protocol, not magic migration of a language model.

## Illustrative lifecycle

1. **Describe** goal, data classification, deadline, capabilities and acceptable side effects.
2. **Discover** destination via an authenticated, allowlisted discovery mechanism; A2A Agent Cards can advertise supported capabilities but are not proof of trust.
3. **Negotiate** envelope schema version, runtime support, artifact access and degraded-mode semantics.
4. **Authorize** by policy and, where appropriate, a human approver; never forward the origin's raw credentials.
5. **Checkpoint** only at a safe boundary; persist immutable task snapshot and idempotency keys.
6. **Dispatch** via A2A task communication (or local adapter), with scoped credential exchange and encrypted transport.
7. **Execute** with least-privilege tool access (MCP may expose tools), telemetry and resource/time budgets.
8. **Reconcile** after timeouts: query task status, avoid blind replay of irreversible operations.
9. **Return** artifacts, statuses and sanitized provenance; origin validates contract and acknowledges completion.
10. **Expire/revoke** delegated authority, enforce retention and keep an audit trail.

## Proposed versioned envelope (schema sketch, not a published standard)

~~~json
{
  "schema_version": "0.1.0-draft",
  "movement_id": "generated-uuid",
  "operation": "delegate",
  "origin": {"agent_id": "urn:example:origin", "run_id": "run-123"},
  "destination": {"agent_id": "urn:example:destination"},
  "task": {"id": "task-123", "goal": "Summarize the supplied public document", "deadline": null},
  "context": {"classification": "public", "messages": [], "artifact_refs": []},
  "execution": {"checkpoint_ref": null, "idempotency_key": "opaque-unique-id", "required_capabilities": []},
  "authority": {"approval_ref": "approval-123", "grant_ref": "external-short-lived-token-reference"},
  "observability": {"traceparent": "W3C-trace-context-if-present"},
  "integrity": {"digest": "to-be-defined"}
}
~~~

**Warning:** This is a conceptual schema, not tested code or interoperable wire format. Token references must not reveal reusable credentials. Messages and artifact refs require independent policy filtering and signed/verified integrity as applicable. Avoid storing private chain-of-thought.

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
