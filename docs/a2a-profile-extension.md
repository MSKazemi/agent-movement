# A2A extension: agent-movement handoff profile

| | |
|---|---|
| **Extension URI** | `https://github.com/MSKazemi/agent-movement/blob/main/docs/a2a-profile-extension.md` |
| **Profile version** | `0.2.0-draft` |
| **Envelope schema** | `0.1.0-draft` (the [local handoff envelope](local-implementation.md)) |
| **A2A version** | v1.0 (`A2A-Version: 1.0`) |
| **Deprecated alias** | `urn:agent-movement:a2a-handoff-profile:0.1.0-draft`, accepted in profile 0.2.x and removed in 0.3.0 |
| **Status** | Experimental draft. One implementation: [`a2a_server.py` / `a2a_client.py`](a2a-adapter.md) on the official `a2a-sdk` 1.2.2. Not an official or registered A2A extension |
| **Authentication** | Out of scope. See [issue #8](https://github.com/MSKazemi/agent-movement/issues/8) and [peer authentication](peer-authentication.md) |

The key words MUST, MUST NOT, SHOULD, SHOULD NOT and MAY in this document are requirements of **this profile only**. Where this document quotes a rule from the A2A specification, it gives the section number.

## 1. Purpose

The profile lets an origin agent **delegate** one allowlisted, pure task to a destination agent over A2A v1. The handoff envelope is carried in A2A `Message` and `Artifact` fields, so that:

- only allowlisted envelope fields cross the wire, and provider-private runtime state, model context, credentials and tool handles never do;
- the destination admits or refuses the request **before** an A2A task exists;
- the origin can check that the returned receipt answers exactly the envelope it sent (digests over canonical JSON);
- A2A task, context and message IDs can be joined with the destination's audit log.

The profile covers **delegation, not migration**. No code, memory, checkpoint or ownership moves, and nothing shows that an agent relocated or resumed elsewhere.

## 2. Identifier and versioning

**Identifier.** The extension URI is the URL of this document on the `main` branch. A2A requires a unique URI per extension (§4.4.4, `AgentExtension.uri`), and the A2A [Extensions topic](https://a2a-protocol.org/v1.0.0/topics/extensions/) says the extension specification should be hosted at that URI. This URI resolves to this file once it is on `main`.

**Versioning.** A2A v1.0 §4.6.3 says extensions SHOULD include version information in their URI, and a new URI MUST be created for a breaking change. This profile follows the second rule strictly and puts version information somewhere else:

- The URI has no version segment, because it is the stable path of this document. The profile version is published in `params.profile_version` on the Agent Card and in the table above.
- Under this URI, only backward-compatible changes are allowed: clarifications, new **optional** `params`, and new rejection reasons for requests that were already invalid.
- A breaking change gets a **new URI**, the URL of a new document (for example `docs/a2a-profile-extension-v1.md`). It does not edit the rules here.
- A server MUST NOT automatically fall back to an older profile version (A2A v1.0 §4.6.3).

**Deprecated alias.** Profile 0.1 used the placeholder URN `urn:agent-movement:a2a-handoff-profile:0.1.0-draft`. Profile 0.2 changes the default `contextId` behaviour (§5), which is a breaking change, so it needs the new URI. For one profile version the URN stays an accepted alias with **its profile 0.1 semantics**:

| | Current URI | Deprecated URN alias |
|---|---|---|
| Agent Card entry | `required: true` | `required: false`, `params.deprecated: true`, `params.replaced_by: <current URI>` |
| Client-supplied `contextId` | Server policy (default: rejected; see §5) | Accepted when it equals `logical_task_id` (profile 0.1 rule) |
| Message and artifact metadata key | The current URI | The URN |
| Accepted in | 0.2.x and later | 0.2.x only. **Removed in 0.3.0** |

A request that activates either URI satisfies the required profile. Each message MUST use one URI consistently: in `A2A-Extensions`, in `Message.extensions`, and as the `Message.metadata` key. New clients MUST use the current URI.

## 3. Agent Card declaration

The destination declares the profile in `AgentCard.capabilities.extensions` (A2A v1.0 §4.6.1):

```json
{
  "uri": "https://github.com/MSKazemi/agent-movement/blob/main/docs/a2a-profile-extension.md",
  "required": true,
  "description": "Experimental agent-movement handoff profile: …",
  "params": {
    "profile_version": "0.2.0-draft",
    "schema_version": "0.1.0-draft",
    "operations": ["delegate"],
    "destination_agent_id": "agent-b",
    "context_id": "server-generated",
    "client_context_id": "rejected",
    "deprecated_aliases": ["urn:agent-movement:a2a-handoff-profile:0.1.0-draft"],
    "proves": "delegation-not-migration",
    "authentication": "none-experimental"
  }
}
```

`params` schema (all required unless marked optional):

| Key | Type | Meaning |
|---|---|---|
| `profile_version` | string | Version of this profile implemented by the server |
| `schema_version` | string | Handoff envelope schema accepted. A different `schema_version` in a message is refused |
| `operations` | array of strings | Envelope operations accepted. Only `"delegate"` is defined |
| `destination_agent_id` | string | The agent ID this destination answers to. It is an **unauthenticated claim** |
| `context_id` | string | Always `"server-generated"`: without a client `contextId`, the server generates one |
| `client_context_id` | string | `"rejected"` (default) or `"bound-to-logical-task-id"` (opt-in); see §5 |
| `deprecated_aliases` | array of strings | *Optional.* Older URIs still accepted for this profile |
| `proves` | string | `"delegation-not-migration"` |
| `authentication` | string | `"none-experimental"` until authentication is specified (issue #8) |

Skills are advertised one per enabled task kind, with ID `agent-movement.<kind>` (`word_count`, `sha256`), `inputModes: ["application/vnd.agent-movement.task+json"]` and `outputModes: ["application/vnd.agent-movement.receipt+json"]`.

A client MUST check, before it sends anything, that the card lists the profile URI it will use and the skill for the envelope's task kind. A client that wants to send a `contextId` MUST also check that `client_context_id` is `"bound-to-logical-task-id"` (§5).

## 4. Request: envelope → A2A message

Activation: the client MUST send the URI in the `A2A-Extensions` service parameter (HTTP header) and in `Message.extensions`. A server that marks the profile `required` returns `ExtensionSupportRequiredError` when it is not activated (A2A v1.0 §3.3.4).

| Handoff envelope field | A2A location | Required |
|---|---|---|
| `task.kind`, `task.text` | `Message.parts[0]`: the **only** part, a `data` part with `mediaType: application/vnd.agent-movement.task+json`, containing exactly `{kind, text}`. No `filename` and no part `metadata` | yes |
| `schema_version` | `Message.metadata[<URI>].schema_version` | yes |
| `movement_id` | `Message.metadata[<URI>].movement_id` | yes |
| `logical_task_id` | `Message.metadata[<URI>].logical_task_id` | yes |
| `operation` | `Message.metadata[<URI>].operation` (`"delegate"`) | yes |
| `origin.agent_id` | `Message.metadata[<URI>].origin_agent_id` | yes |
| `destination.agent_id` | `Message.metadata[<URI>].destination_agent_id` | yes |
| `context.classification` | `Message.metadata[<URI>].classification` | yes |
| `authority.approval_ref` | `Message.metadata[<URI>].approval_ref` | yes |
| `execution.idempotency_key` | `Message.metadata[<URI>].idempotency_key` | yes |
| `observability.trace_id` | `Message.metadata[<URI>].trace_id` | yes |
| *(computed)* SHA-256 of the canonical envelope | `Message.metadata[<URI>].envelope_digest` | yes |
| — | `Message.contextId`: **omitted by default**; see §5 | no |
| — | `Message.role`: `ROLE_USER`; `Message.messageId`: a fresh client UUID | yes |

`Message.metadata` MUST contain exactly one key, the profile URI, whose value is a flat object with exactly the 11 keys above. There MUST NOT be request-level `metadata`, `Message.taskId` (no task continuation) or `referenceTaskIds`. The server rebuilds the envelope from these fields, validates it with the strict envelope contract (unknown fields are refused at every level), and recomputes `envelope_digest`.

## 5. contextId policy

A2A v1.0 §3.4.1 says agents MAY generate a `contextId` when a message has none, and MUST return a generated one in the response. Clients SHOULD NOT supply a client-generated `contextId` unless they understand how the server handles it. An agent that cannot accept a client-provided `contextId` MUST reject the request with an error. This profile defines that handling:

1. **Default: server-generated.** The client omits `Message.contextId`. The server generates one and returns it in `Task.contextId`. The client MUST treat it as opaque (§3.4.1). Each A2A task gets its own context, including an exact retry. The logical task is identified by `logical_task_id` in the metadata, not by the context.
2. **Client-supplied `contextId` under the default policy** (`client_context_id: "rejected"`): refused before any task exists, with `InvalidParamsError`.
3. **Opt-in** (`client_context_id: "bound-to-logical-task-id"`, which the reference server enables with `--accept-client-context-id`): a client-supplied `contextId` is accepted only if it is **exactly equal** to the envelope's `logical_task_id`. The server preserves it in `Task.contextId`. Any other value is refused with `InvalidParamsError`. A message without a `contextId` still gets a server-generated one.
4. **Deprecated URN alias**: always uses the opt-in rule from point 3, which was the profile 0.1 behaviour.

The rule is applied to the `contextId` **as the client sent it**, before the SDK assigns one. The client checks that the returned `contextId` is non-empty and, when it supplied one, that it was preserved.

## 6. Result: receipt → A2A artifact

On success the task reaches `TASK_STATE_COMPLETED` (observed with streaming: `SUBMITTED → WORKING → COMPLETED`) and carries exactly one artifact:

| Core receipt field | A2A location |
|---|---|
| `status`, `movement_id`, `logical_task_id`, `origin_agent_id`, `destination_agent_id`, `trace_id`, `envelope_digest`, `artifact`, `artifact_digest` | `Task.artifacts[0]`: `name: "handoff-receipt"`, `artifactId: "receipt-<movement_id>"`, one `data` part with `mediaType: application/vnd.agent-movement.receipt+json` containing exactly these 9 keys |
| `movement_id`, `trace_id`, `envelope_digest`, `artifact_digest`, `replayed` | `Artifact.metadata[<URI>]`, exactly these 5 keys |
| — | `Artifact.extensions = [<URI>]` |

`<URI>` is the URI that the request used (the current URI or the deprecated alias). The origin MUST verify the receipt: every identifier and `envelope_digest` must match the envelope it sent, `artifact_digest` must equal the digest of `artifact`, and the metadata copies must equal the data. Protobuf `Value` turns JSON numbers into doubles, so integral doubles are converted back to integers before the digest is recomputed.

An exact retry (same envelope, same `idempotency_key`) is a **new A2A task** with a new task ID and, by default, a new `contextId`. The destination answers it from its idempotency ledger with `replayed: true` and the identical `artifact_digest`, so the task is not executed twice.

## 7. Errors

Pre-task refusals are A2A errors. No task is created, and the destination records the refusal by A2A message ID. The JSON-RPC codes are from A2A v1.0. The HTTP+JSON mapping is the one in `a2a-sdk` 1.2.2 (`a2a.utils.errors.A2A_ERROR_MAPPING`).

| Condition | A2A error | JSON-RPC | HTTP+JSON |
|---|---|---|---|
| Neither profile URI activated in `A2A-Extensions` | `ExtensionSupportRequiredError` | -32008 | 400 `EXTENSION_SUPPORT_REQUIRED` |
| `A2A-Version` missing or not `1.0` (enforced by the SDK) | `VersionNotSupportedError` | -32009 | 400 `VERSION_NOT_SUPPORTED` |
| Message URI not activated, more than one or an unknown profile URI, wrong metadata or part shape, extra or missing field, unknown `schema_version`, kind or operation, digest mismatch, `taskId` or `referenceTaskIds` present, request-level metadata, or a `contextId` refused under §5 | `InvalidParamsError` (message `handoff profile rejected: <reason>`) | -32602 | 400 `INVALID_PARAMS` |
| Task kind valid for the schema but not advertised by this agent | `UnsupportedOperationError` | -32004 | 400 `UNSUPPORTED_OPERATION` |

Refusals after the task exists end in the terminal state `TASK_STATE_REJECTED`. The status message holds one `data` part (`application/json`):

| Condition | `error` value |
|---|---|
| Receiver-side approval missing, wrong, expired or revoked, or the destination ID does not match | `"approval_denied"` |
| Idempotency key reused with different content | `"idempotency_conflict"` |
| Envelope fails the defensive re-check in the executor | `"invalid_contract"` |

Cancellation is not supported: tasks complete synchronously, and the executor's `cancel` raises `UnsupportedOperationError`.

## 8. Security notes

- **No authentication.** Agent IDs, `approval_ref` and the Agent Card itself are unauthenticated claims. The Agent Card declares no `securitySchemes`. The receiver-side approval is a local policy check, not proof of who sent the request. Do not expose a server that implements this profile beyond loopback. Authentication and authorization before task content is disclosed are tracked in [issue #8](https://github.com/MSKazemi/agent-movement/issues/8).
- **Content is disclosed on send.** The task text travels in the first message, so a client that sends to the wrong agent has already disclosed it. The card checks in §3 are capability negotiation, not trust.
- **Allowlist in both directions.** Only the fields in §4 and §6 are mapped. Both sides require exact key sets, so smuggled fields such as `provider_state` or vendor metadata namespaces are refused, not ignored.
- **No arbitrary execution.** The destination runs only the advertised pure functions. There is no tool, shell, network or file access.
- **Audit without content.** The destination's correlation log stores IDs, outcome codes and SHA-256 digests, never task text. IDs chosen by the client that are not short safe tokens are stored hashed.
- **contextId is not authority.** A `contextId`, whether server-generated or bound, groups messages. It grants nothing. Approval is always checked against the envelope.
- **Mutable document URL.** The URI points at `main`. Integrity of the specification relies on the repository's review process and on the rule in §2 that only backward-compatible edits are allowed under this URI.

## 9. Conformance and limitations

- Reference implementation and tests: [`docs/a2a-adapter.md`](a2a-adapter.md), `src/agent_movement/a2a_*.py`, `tests/test_a2a_profile.py` and `tests/test_a2a_adapter.py`. The tests also send the profile 0.1 wire shape through the alias.
- Both ends use the same SDK and version. The official A2A Inspector and TCK, and a second implementation, have not been run against this profile.
- The server does not echo activated extensions in an `A2A-Extensions` response header, which the A2A Extensions topic recommends (SHOULD). `a2a-sdk` 1.2.2 does not do this automatically.
- The destination's correlation log does not record which profile URI a request used, so use of the deprecated alias is visible only in the request itself, not in the audit.
