# Technology landscape (reviewed 2026-10-15)

## Taxonomy: five different notions of movement

| Mode | Example | State transferred? | Key issue |
|---|---|---|---|
| Delegation | Planner asks specialist to analyze file | Task input only | Ownership and authority |
| Copy / replication | Start another instance from same agent package | Config and optionally memory | Divergence, duplicate effects |
| Multiplication / scaling | Launch N worker agents | Usually shared queue/context pointers | Coordination and cost |
| Checkpoint-resume relocation | Persist safe checkpoint and resume on new worker | Portable workflow checkpoint | Compatibility and recovery |
| Strong migration | Move live process incl. stack/in-flight operations | Live execution state | Generally not available across unrelated AI frameworks |

A model's private internal state, chain-of-thought, temporary tool runtime, or browser session cannot be presumed exportable. Agent "memory" can mean stored messages, retrieved documents, summaries or application state; each needs distinct handling.

## Technology-by-technology

### A2A: agent-to-agent communication
Primary specification: https://a2a-protocol.org/v1.0.0/specification/

A2A provides an interface for interoperating with independently hosted agents through capabilities/discovery, structured messages, tasks, artifacts and updates. A2A is the leading candidate for **remote delegation**, not a general process-checkpoint standard. Authentication and trust policies still need to be enforced in deployment.

### MCP: model/agent-to-tool interoperability
Spec: https://modelcontextprotocol.io/specification/2026-07-28

MCP servers expose tools, resources and prompts to clients, allowing a moved/delegated agent to use eligible tools without custom integration for each tool. MCP does not provide a portable runtime checkpoint or automatic authority transfer. Treat remote tool output as untrusted.

### AG-UI: agent-to-frontend interaction
Code and docs: https://github.com/ag-ui-protocol/ag-ui

Useful for user-visible streaming, approvals, event/state synchronization and a live movement timeline; not a replacement for A2A.

### Durability: LangGraph and Temporal
LangGraph: https://docs.langchain.com/oss/python/langgraph/persistence
Temporal: https://docs.temporal.io/workflow-execution

LangGraph checkpoints support persistence and resumption within its execution model. Temporal offers durable workflows and retryable activities, subject to deterministic workflow and external side-effect discipline. Neither alone ensures byte-for-byte migration between different agent frameworks.

### Hosting: OCI + Kubernetes
OCI image specification: https://specs.opencontainers.org/image-spec/
Kubernetes Jobs: https://kubernetes.io/docs/concepts/workloads/controllers/job/

Packaging makes deployment portable, not agent state. Pods may be restarted or replaced; ephemeral runtime state and external resources require additional design. Use versioned containers and compatible checkpoint formats.

### Trust: identity, delegation and observability
OAuth 2.0 token exchange: https://www.rfc-editor.org/rfc/rfc8693
SPIFFE / SPIRE: https://spiffe.io/docs/latest/spire-about/spire-concepts/
OPA: https://www.openpolicyagent.org/docs
OpenTelemetry GenAI conventions: https://opentelemetry.io/docs/specs/semconv/gen-ai/

These are building blocks, not proof of end-to-end security. Verify token audiences, resource scopes, recipient identity, tool authorization and trace privacy separately.

## Research gaps / hypotheses

1. Portable minimal **task envelope** across vendors (goals, task/trace IDs, capability needs, safe artifact references, checkpoint pointer, provenance).
2. **Compatibility negotiation**: what is mandatory vs optional, what may be lost and when to refuse.
3. **Trust-preserving delegation** with short-lived delegated identity and explicit user approval.
4. **Replay-safe resumption** for external actions, including partially complete operations.
5. **Portable evaluation**: reproducible success, data leakage, duplicate side effects, latency and operational cost.

## What the project should not claim

Do not equate A2A with migration, MCP with authentication for all connected services, multiple replicas with a single migrating agent, or a serialized transcript with a correct execution checkpoint. Avoid promising exact-once behavior for arbitrary external tools.

See [sources](sources.md), [security](security-and-trust.md), and [questions](open-questions.md).
