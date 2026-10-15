# Optional A2A v1 adapter (official Python SDK)

**Status:** Experimental, tested on loopback with synthetic data (2026-10-16).

> **This proves DELEGATION, not migration.** One process (the origin) asks another, independent process (the destination worker) to perform one allowlisted, pure task over A2A v1. Code, memory, checkpoints, model context and runtime state do **not** move. Nothing here shows that an agent relocated, resumed or continued elsewhere.
>
> **Authentication is experimental: it is absent.** The Agent Card declares no `securitySchemes`. Agent IDs in the handoff profile are **unauthenticated claims**. The receiver-side approval is a local policy check, not proof of who sent the request. Peer authentication and authorization before task content is disclosed are tracked separately in issue #8. Do not expose this worker beyond `127.0.0.1`.

This adapter carries the existing `0.1.0-draft` handoff envelope ([local implementation](local-implementation.md)) over real A2A v1 framing, using the official [`a2a-sdk`](https://github.com/a2aproject/a2a-python) for the client and the server. The application contract and its safety checks (`core.py`: strict envelope, allowlisted kinds, receiver-side approval, idempotent SQLite receipts) are unchanged. They sit behind the SDK's `AgentExecutor`. All A2A framing comes from the SDK, with no custom framing: Agent Card, JSON-RPC and HTTP+JSON bindings, task lifecycle, SSE streaming and error codes.

## Install, test and demo

The core package keeps zero runtime dependencies. The adapter is an opt-in extra:

~~~sh
python -m pip install -e '.[a2a]'            # or: uv venv .venv && uv pip install -e '.[a2a]'
python -m pytest -q                           # without the extra, 11 adapter tests skip
python -m agent_movement.a2a_demo             # exit 0 only if every check below passes
~~~

Manual two-terminal run:

~~~sh
python -m agent_movement.a2a_server --db /tmp/a2a-receiver.sqlite --port 0   # prints {"port":…, "url":…}
python -m agent_movement.a2a_client --url http://127.0.0.1:<port> --envelope envelope.json [--binding HTTP+JSON] [--no-stream]
~~~

## Version pins and test matrix

| Component | Version | Source |
|---|---|---|
| A2A specification | v1.0 (`protocolVersion: "1.0"`, `A2A-Version: 1.0`) | <https://a2a-protocol.org/v1.0.0/specification/>; SDK constant `PROTOCOL_VERSION_CURRENT = '1.0'` |
| `a2a-sdk[http-server]` | **==1.2.2** (exact pin) | Latest release on PyPI on 2026-10-16, uploaded 2026-10-05 (<https://pypi.org/pypi/a2a-sdk/json>) |
| `uvicorn` | >=0.54 (0.54.0 tested) | Latest on PyPI on 2026-10-16. The ASGI server is not included in `a2a-sdk[http-server]` |
| Transitively resolved | starlette 1.8.0, sse-starlette 3.5.0, httpx 0.28.1, protobuf 7.36.2, pydantic 2.14.1 | `uv pip install -e '.[a2a]'` |

Results recorded on 2026-10-16 (Linux x86_64):

| Environment | `unittest discover -s tests` | `a2a_demo` | `demo` (core) |
|---|---|---|---|
| CPython 3.11.16 + `[a2a]` | 36 run, OK, 1 skipped (the missing-extra check) | exit 0, `failures: []` | exit 0 |
| CPython 3.13.15 + `[a2a]` | 36 run, OK, 1 skipped | exit 0 | not re-run |
| CPython 3.13.15, core only (no extra) | 36 run, OK, 11 skipped (adapter tests) | exit 2 with install hint | exit 0 |

The table records the adapter branch before integration, run with `unittest`. On the integrated tree the suite runs with `python -m pytest -q`, because `tests/` also holds the pytest-style corpus tests.

CI: `.github/workflows/python-smoke.yml` has a core-only job (no extras; the adapter tests skip and `a2a_demo` must exit 2) and an `extras` job on 3.11 and 3.13. The extras job installs every optional extra, prints the resolved versions, runs the full suite and runs this demo.

## Architecture

```
origin process (agent_movement.a2a_client)              destination process (agent_movement.a2a_server)
  envelope ──validate_envelope──► envelope_to_a2a        Starlette + uvicorn, 127.0.0.1 only
  A2ACardResolver: GET /.well-known/agent-card.json ───► create_agent_card_routes(card)
  check_card(): profile extension + skill advertised?
  ClientFactory(JSONRPC | HTTP+JSON).send_message ─────► create_jsonrpc_routes / create_rest_routes
     A2A-Version: 1.0, A2A-Extensions: <profile URI>       HandoffRequestHandler(DefaultRequestHandlerV2)
                                                             _admit(): extension, profile shape, skill
                                                               └─ reject → JSON-RPC/REST error, no task
                                                           HandoffExecutor(AgentExecutor)
                                                             SUBMITTED → WORKING → core HandoffReceiver
  verify_receipt() ◄── Task + receipt artifact ─────────     → artifact + COMPLETED | REJECTED
  get_task(id) for the final state                         SQLite: deliveries, audit_events, a2a_correlations
```

Modules: `a2a_profile.py` (stdlib only: mapping, receipt verification, correlation log), `a2a_server.py`, `a2a_client.py`, `a2a_demo.py` (stdlib-only orchestrator). `core.py` is unchanged.

## Capability advertisement (Agent Card)

The destination worker serves an A2A v1 Agent Card at `/.well-known/agent-card.json` with:

- `supportedInterfaces`: `JSONRPC` at `/a2a/jsonrpc` and `HTTP+JSON` at `/a2a/rest`, both `protocolVersion: "1.0"`.
- `capabilities`: `streaming: true`, `pushNotifications: false`, `extendedAgentCard: false`, and one extension, `urn:agent-movement:a2a-handoff-profile:0.1.0-draft`, marked `required: true`. Its `params` declare the schema version, `operations: ["delegate"]`, the destination ID, `proves: "delegation-not-migration"` and `authentication: "none-experimental"`.
- `skills`: one per **enabled** task kind (`agent-movement.word_count` by default; `--advertise sha256` adds the other). Each skill declares `inputModes: [application/vnd.agent-movement.task+json]` and `outputModes: [application/vnd.agent-movement.receipt+json]`.
- No `securitySchemes` or `securityRequirements`. These fields are optional in the spec (§4.4.1) and are deliberately left out until issue #8 is resolved.

## Envelope → A2A mapping

| Handoff envelope field | A2A location |
|---|---|
| `task.kind`, `task.text` | `Message.parts[0]`: the only part, a `data` part with `mediaType: application/vnd.agent-movement.task+json`, containing exactly `{kind, text}` |
| `schema_version`, `movement_id`, `logical_task_id`, `operation`, `origin.agent_id`, `destination.agent_id`, `context.classification`, `authority.approval_ref`, `execution.idempotency_key`, `observability.trace_id`, plus a computed `envelope_digest` | `Message.metadata["urn:agent-movement:a2a-handoff-profile:0.1.0-draft"]`, a flat object with exactly these 11 keys |
| `logical_task_id` (again) | `Message.contextId`. A2A lets the server accept a client-provided contextId (§3.4.1); this server requires it to equal the logical task ID |
| Profile activation | `Message.extensions = [<profile URI>]` and the HTTP header `A2A-Extensions: <profile URI>` |
| *(server-assigned)* | `Task.id`: the A2A task ID. `Message.messageId` is a client UUID |

Metadata keyed by the extension URI follows the spec's extension examples (§4.6). Results map as follows:

| Receipt (core) | A2A location |
|---|---|
| `status, movement_id, logical_task_id, origin/destination_agent_id, trace_id, envelope_digest, artifact, artifact_digest` | `Task.artifacts[0]`: `name: handoff-receipt`, `artifactId: receipt-<movement_id>`, one `data` part (`application/vnd.agent-movement.receipt+json`) |
| `movement_id, trace_id, envelope_digest, artifact_digest, replayed` | `Artifact.metadata[<profile URI>]` |
| Policy denial / idempotency conflict | Terminal state `TASK_STATE_REJECTED`. The status message holds one data part `{"error": "approval_denied" \| "idempotency_conflict"}` |

**Provider-private state is never serialized.** The mapping copies fields by explicit allowlist from an envelope that has already passed `validate_envelope`, which rejects any unknown field at any level. The receiver then requires exact key sets again: one part only, no part metadata or filename, no request-level metadata, no metadata keys other than the profile URI, no `taskId` or `referenceTaskIds` (no continuation). It also recomputes `envelope_digest`. The A2A task store keeps no message history (`new_task(..., history=None)`). The receiver's audit and correlation tables hold IDs, outcome codes and SHA-256 digests only. Tests assert that the raw task text never appears in them.

Protobuf `Value` turns every JSON number into a double (`5` arrives as `5.0`). `verify_receipt` converts integral doubles back to integers before it recomputes `artifact_digest`.

## Rejections (no arbitrary tool execution)

Admission runs in `HandoffRequestHandler._admit` **before the SDK creates a task**. Only `core.HandoffReceiver.receive` executes anything, and it runs only the two pure functions `word_count` and `sha256`. There is no tool, shell, network or file access.

| Case | Where | A2A result |
|---|---|---|
| Client did not activate the required profile extension | server | `ExtensionSupportRequiredError`, JSON-RPC `-32008`. The spec says this is a MUST (§3.3.4) |
| `A2A-Version: 0.3`, or the header is missing (read as 0.3 per §3.6.2) | SDK | `VersionNotSupportedError`, `-32009` |
| Unknown schema version, unknown task kind, `operation: relocate`, extra or missing fields, smuggled `provider_state`, extra metadata namespace, plain-text part, more than one part, digest or contextId mismatch | server | `InvalidParamsError`, `-32602`; no task is created |
| Kind is valid in the schema but not advertised by this worker (e.g. `sha256` when only `word_count` is enabled) | server | `UnsupportedOperationError`, `-32004`; no task is created |
| The same, but the client checked the card first | client | `CapabilityMismatch`; nothing is sent |
| Card from a foreign agent without the profile extension | client | `CapabilityMismatch` |
| Approval missing, wrong, expired or revoked | executor | Task `REJECTED`, reason `approval_denied`; core audit `handoff.denied` |
| Idempotency key reused with different content | executor | Task `REJECTED`, reason `idempotency_conflict` |

Every pre-task rejection is still recorded in `a2a_correlations` with outcome `rejected.<ErrorType>`, the A2A message ID and `a2a_task_id = NULL`.

## End-to-end identifiers and receiver-side audit correlation

The receiver keeps a new table, `a2a_correlations` (`A2ACorrelationLog`), in the same SQLite file as the core `audit_events`. Each A2A request adds one row: `a2a_task_id, a2a_context_id, a2a_message_id, movement_id, trace_id, outcome, envelope_digest, artifact_digest`. Correlation chain:

`client a2a_message_id / a2a_task_id` → `a2a_correlations` row → `movement_id` → core `audit_events` (`handoff.accepted` with `info_digest = envelope_digest`, `handoff.completed` with `info_digest = artifact_digest`) → receipt artifact `artifact_digest`, verified again by the client.

An exact retry is a **new A2A task** (new `a2a_task_id`). The core receiver answers it from its idempotency ledger (`replayed: true`, identical `artifact_digest`), so the core audit still shows a single `handoff.completed`.

## Actual demo output (2026-10-16, CPython 3.11.16, abridged)

Command: `python -m agent_movement.a2a_demo` (exit 0). UUIDs differ per run.

~~~json
"agent_card": {"interfaces": [["JSONRPC","1.0"],["HTTP+JSON","1.0"]],
               "skills": ["agent-movement.word_count"],
               "extensions": [["urn:agent-movement:a2a-handoff-profile:0.1.0-draft", true]],
               "security_schemes": {}},
"first":  {"binding": "JSONRPC", "streaming": true, "final_state": "TASK_STATE_COMPLETED",
           "observed_states": ["TASK_STATE_SUBMITTED","TASK_STATE_WORKING","TASK_STATE_COMPLETED"],
           "a2a_task_id": "682c67ce-…", "a2a_context_id": "demo-task",
           "receipt": {"artifact": {"kind": "word_count", "value": 5}, "replayed": false,
                       "artifact_digest": "39027882…2696", "envelope_digest": "4768fbf3…2cba"}},
"retry":  {"binding": "HTTP+JSON", "streaming": false, "final_state": "TASK_STATE_COMPLETED",
           "a2a_task_id": "5696fb67-…", "receipt": {"replayed": true, "artifact_digest": "39027882…2696"}},
"denied": {"final_state": "TASK_STATE_REJECTED", "reason": "approval_denied",
           "observed_states": ["TASK_STATE_SUBMITTED","TASK_STATE_WORKING","TASK_STATE_REJECTED"]},
"unknown_capability": {"error": {"type": "UnsupportedOperationError",
           "message": "capability not advertised by this agent: agent-movement.sha256"}},
"unknown_schema": {"error": {"type": "InvalidParamsError",
           "message": "handoff profile rejected: unsupported schema version or operation"}},
"receiver": {"a2a_correlations": [
   {"a2a_task_id": "682c67ce-…", "movement_id": "a2a-demo-movement", "outcome": "completed", "artifact_digest": "39027882…2696"},
   {"a2a_task_id": "5696fb67-…", "movement_id": "a2a-demo-movement", "outcome": "replayed",  "artifact_digest": "39027882…2696"},
   {"a2a_task_id": "caa27165-…", "movement_id": "a2a-demo-denied",   "outcome": "approval_denied"},
   {"a2a_task_id": null, "outcome": "rejected.UnsupportedOperationError"},
   {"a2a_task_id": null, "outcome": "rejected.InvalidParamsError"}],
 "audit_events": [
   {"movement_id": "a2a-demo-movement", "event_type": "handoff.accepted",  "info_digest": "4768fbf3…2cba"},
   {"movement_id": "a2a-demo-movement", "event_type": "handoff.completed", "info_digest": "39027882…2696"},
   {"movement_id": "a2a-demo-denied",   "event_type": "handoff.denied",    "info_digest": "d1033896…df77"}]},
"failures": []
~~~

## What this does not establish

- **Not migration.** No state, checkpoint or ownership moves. The `EffectGateway` fencing experiment is not wired into A2A.
- **No authentication or transport security.** There is no TLS, signed Agent Card (`signatures`), mTLS, OAuth or OIDC. Agent IDs are claims. Approval is a local, pre-configured record (issue #8).
- **No independent interoperability check yet.** Both ends use the same SDK and version. The tests include raw wire-level JSON-RPC requests (no SDK client) and raw Agent Card fetches. The official A2A Inspector and TCK, and a second non-Python implementation, have **not** been run against this worker.
- **Not durable on the A2A side.** The SDK `InMemoryTaskStore` loses A2A task records when the process restarts. The core SQLite receipts and correlation rows persist. Cancellation is unsupported, because tasks complete synchronously.
- **Experimental profile.** The extension URI is a placeholder URN, not a published A2A extension specification.
