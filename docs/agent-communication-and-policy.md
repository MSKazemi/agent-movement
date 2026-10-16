# Agent communication and enforceable policy: v0.1 research proposal

**Status:** Normative **project proposal**, not a published standard, certified control, or implemented production gateway. Reviewed 2026-10-15. This document complements the existing [movement lifecycle](how-it-works.md), [security threat model](security-and-trust.md), [forensics design](agent-forensics-and-fingerprints.md), and the open authentication/pre-disclosure work in [issue #8](https://github.com/MSKazemi/agent-movement/issues/8). The proposed [protocols and networks guide, PR #5](https://github.com/MSKazemi/agent-movement/pull/5), addresses transports in greater detail.

## Executive recommendation

**Separate the ability to send a message from the authority to have it obeyed.** Every cross-boundary request must pass an independent, fail-closed policy enforcement point (PEP) *before sensitive content is released*, and side effects must be checked again at their own point of execution. Prompt-level instructions, self-declared agent IDs, signed Agent Cards, or encrypted transport alone are not authorization.

In phase 1, begin with authenticated, allowlisted, localhost-only **public/synthetic** task delegation. The proposed policy may later extend to multiple machines, tenants, tools, mobile devices, and robotics only after measurable controls and explicit threat review. Never call ordinary delegation "migration" or assume that agent model state, private reasoning, or credentials can be transported.

## 1. What is an agent communication?

An agent communication is a versioned, attributable exchange of *data*, *intent*, or *control* between a principal acting as an AI agent and a destination principal. A message may be a request, response, notification, event, stream item, artifact reference, delegation, or control signal. Messages alone do not confer authority.

| Communication plane | Typical purpose | Protocol / interface examples | Security boundary |
| --- | --- | --- | --- |
| Agent-to-agent | discover capabilities, request/coordinate tasks, report artifacts | A2A v1, authenticated app RPC, local queue | sender and receiver principals; per-task scope |
| Agent-to-tool/resource | call approved tools and access data | MCP, APIs | tool-side IAM and data permissions |
| Agent-to-human | explain status, request informed approval, show results | application UI, AG-UI events | user session/approval proof |
| Agent-to-device/actuator | issue physical commands | device-specific APIs, ROS interfaces, industrial control | actuator controller, safety interlocks |
| Agent-to-memory/artifacts | read, write, synchronize checkpoints | application storage, object store | ownership, sensitivity, integrity |
| Agent-to-platform | provision workers, replicas, execution locations | container/job orchestrators | infrastructure IAM; quotas; network controls |
| Agent-to-many | broadcast, publish-subscribe, multi-agent voting | queues, event buses, streams | topic ACLs; fan-out, privacy, coordination risks |

A2A is suitable for agent/task messaging and discovery; MCP is for tool/resource interaction, not generic agent migration. Neither substitutes for end-to-end identity, policy, data classification, and accountable governance. Distinguish request acceptance from eventual task completion and external side-effect finality.

### Proposed message-intent types

- **READ/QUERY:** ask for information or an analysis without side effects.
- **RESULT/STATUS/EVENT:** return data and progress updates; treat contents as untrusted.
- **DELEGATE:** ask another agent to work on an explicitly scoped task.
- **TOOL_ACTION:** request a tool operation; must be separately authorized by the tool's enforcement point.
- **MOVE/CHECKPOINT_TRANSFER:** move execution context or ownership; requires distinct movement authority.
- **SPAWN/REPLICATE:** create another agent/process or delegate to N agents; requires explicit provisioning authority.
- **DEVICE_COMMAND:** actuate a real-world device; controller must independently authorize and interlock.
- **CANCEL/REVOKE:** signal cessation; privileged authorization channel, independently authenticated.

A passive message does not implicitly permit any active operation. For example, a DELEGATE grant is not a MOVE or SPAWN grant.

## 2. Trust model and essential invariants

Trust is scoped to a principal + user/tenant + destination + specific action + resource + duration + data class. A model-generated statement such as "I am the administrator" has **zero** authentication value.

**Actors:** initiating user/owner; origin agent and its runtime; independent origin-side communication egress PEP; identity verifier; policy decision point (PDP); identity/authorization service; authenticated destination ingress PEP; execution/tool PEP; audit service; optional human approval service.

**Authoritative inputs must be populated by trusted platform components**, not copied from an incoming model prompt or unverified payload: verified origin identity, verified recipient binding, actual current time, effective delegation grant, current revocation state, approved user action, recipient registry, quotas, network route, data classification and destination tenancy.

**Safety invariants:**

1. Default deny on absent, malformed, unsupported, or contradictory evidence.
2. Verify identity and authorize the *destination* before sending a private task body. Inbound checks do not repair outbound leakage.
3. Every transitive delegation strictly attenuates authority; agent B cannot create more scope than agent A received.
4. Approval is not a free-standing "yes" in text: it is a server-verifiable binding to exact action, target/resource, task/user, risk and expiry.
5. A successful message delivery is not evidence that an external effect happened once, or at all.
6. Revocation blocks **future** network and tool operations, but cannot undo already completed irreversible effects.
7. A message, memory artifact, tool result, or Agent Card is untrusted content even when transport-authenticated; separate **identity** from **instruction authority**.
8. If a compromised agent has an unmediated network path, file export, alternate credential, or actuator command path, gateway-only safety claims are invalid.

### Layered reference architecture (proposed)

~~~text
User / owner
    -> Intent and approval service [verified human authorization]
    -> Origin agent
    -> Origin egress PEP [verify identity, destination, grant, data BEFORE SEND]
    -> Transport: mTLS/TLS + verified peer + A2A/queue/RPC
    -> Destination ingress PEP [re-authenticate, re-authorize, validate schema]
    -> Destination agent (isolated environment)
    -> Tool / device PEP [re-check active grant and human approval AT USE]
    -> Tool / device / artifact store

Independent: identity authority, central policy & revocation service,
data-classification/egress controls, signed policy version, tamper-evident audit.
~~~

**Infrastructure complement:** block unapproved direct network paths with sandbox/network ACL/egress proxy, constrain DNS and IP resolution for SSRF protection, control file/clipboard/process creation, and apply device-side interlocks. All routes capable of making the prohibited effect must be covered; otherwise the intended invariant is not guaranteed.

## 3. Policy rule catalog (proposed; machine-testable)

Project keywords **MUST / SHOULD / MAY** here are **proposed project requirements**, not claims about what A2A, MCP, OAuth or NIST mandates. Use a versioned rule ID in every deny/audit record. The initial prototype posture is the strictest profile (public/synthetic only).

| ID | Requirement | Independent enforcement | Failure outcome |
| --- | --- | --- | --- |
| COM-01 | Verify sender via trusted cryptographic/session/workload identity; bind to user and tenant | transport/auth verifier on both ends | DENY before task body |
| COM-02 | Resolve recipient via an approved registry and authenticate actual destination; a claimed Agent Card alone is insufficient | outbound connection + recipient binding | DENY before disclosure |
| COM-03 | For each message, require an unexpired audience-, action-, resource-, task- and tenant-scoped grant | PDP/PEP at ingress and egress | DENY |
| COM-04 | Reject unknown schema versions, missing mandatory fields and disallowed message types | strict schema validation | DENY |
| COM-05 | Check classification, purpose, residency and recipient clearance **before sending** any payload or artifact pointer | outbound data policy and receiver ACL | DENY |
| COM-06 | Never embed raw OAuth tokens, API keys, session cookies, passwords, private chain-of-thought or credential-bearing URLs in handoff content | envelope schema + secret/taint checks + runtime secret isolation | DENY/QUARANTINE |
| COM-07 | Treat received text and tool outputs as data; no untrusted content can modify higher-priority policy or grant permissions | model/tool orchestration and action PEP | DENY unauthorized requested effect |
| COM-08 | Delegate only a subset of caller's scope; restrict maximum depth, fan-out, geography and expiry | grant issuer and execution PEP | DENY |
| COM-09 | Require distinct explicit grants for MOVE, SPAWN, replication, deployment, external communication and DEVICE_COMMAND | platform and destination PEP | DENY |
| COM-10 | Require separately verified human approval for high-impact/irreversible side effects; approval must bind exact scope and expiry | approval service and tool PEP | HOLD until approval / DENY |
| COM-11 | Enforce message, token, compute, cost, size, duration, fan-out and concurrency budgets | queues/gateway/runtime | THROTTLE / DENY |
| COM-12 | Check nonces, expiry, operation IDs and idempotency state; reconcile ambiguous side effects rather than blind retry | trusted durable state store and tool PEP | DEDUPLICATE / HOLD |
| COM-13 | Require authenticated encrypted transport and authenticated webhooks; protect callback URLs from SSRF and DNS rebinding | transport/network PEP | DENY |
| COM-14 | Revalidate revocation and scope immediately before each external effect, including after a long-running approval wait | destination tool/device PEP | DENY / CANCEL |
| COM-15 | Record redacted decision, policy version, verified principals, task/message IDs and result with audit integrity controls | separate audit pipeline | FAIL CLOSED if required audit unavailable |
| COM-16 | Authorize publish/subscribe topics, subscribers, broadcast fan-out and cross-tenant sharing | event broker, queue ACL and gateway | DENY |
| COM-17 | For physical or safety-critical commands, require separate device-controller interlock, bounded command set and emergency stop | hardware/robot control system | DENY / SAFE STATE |
| COM-18 | Detect multi-agent cumulative effects: independently benign actions may compose into prohibited spending, privilege gain or exfiltration | shared task/tenant budgets and effect ledger | DENY / ESCALATE |
| COM-19 | Only privilege-bearing control messages (e.g., revoke/override) from the trusted control plane may change policy or lifecycle authority | control-plane PEP | DENY |
| COM-20 | Report received/accepted/running/completed/failed/canceled/unknown precisely; do not claim exactly-once arbitrary effects | task coordinator and receipts | HOLD / RECONCILE |

There should be **no "allow all if internal network" or "allow all if same model family" bypass**. A rule engine with missing context defaults to deny. A suspicious message cannot unilaterally declassify itself or rewrite its own risk tier.

## 4. Example risk tiers, starting defaults and policy logic

**All values below are illustrative Phase 1 defaults, not industry standards or production recommendations.** A real deployment should derive limits from threat analysis and performance testing.

| Tier | Example | Phase 1 decision |
| --- | --- | --- |
| R0: passive public/synthetic | Ask an allowlisted peer to summarize a public test document | ALLOW if authenticated + scoped + within budget |
| R1: internal or personally identifying data | Share internal logs or client profile | DENY (not permitted in first demonstrator) |
| R2: operational side effect | Create files, deploy an agent, send a message to an external address | DENY unless later separately enabled and authorized |
| R3: irreversible or physical impact | Payments, deletion, robotic actuation, critical infrastructure | DENY; require dedicated future safety case and independent control plane |

Prototype starting constraints: maximum payload 256 KiB; maximum message TTL 300 seconds; one delegation hop; up to 60 messages per minute per verified principal; no unaudited agent broadcasts; destination allowlist static; **public and synthetic data only**; no external side effects. These should become configurable, independently measured limits before any application deployment.

For a candidate outbound message, the origin gateway evaluates:

~~~text
ALLOW :=
    transport_authenticated
    AND principal_bound_to_origin
    AND destination_allowlisted_and_verified
    AND schema_and_message_type_supported
    AND active_grant_matches(sender, recipient, user, tenant,
                             task, action, resource, audience, time)
    AND no_authority_amplification
    AND classification_permits_disclosure
    AND purpose_and_residency_permit_disclosure
    AND payload_and_artifact_refs_screened
    AND egress_route_and_budget_allowed
    AND required_approval_verified
    AND required_audit_sink_available

If any input is missing, unknown or false: DENY.
If waiting on human approval: HOLD (no sensitive send and no effect).
If duplicate request: return previously recorded status; do not reexecute.
If previous effect status is uncertain: unknown/reconcile (the [canonical outcome label](glossary.md#reconciliation-and-the-unknownreconcile-state)), not "success".
~~~

At receiver **repeat** identity, payload, grant, tenant and schema validation against locally trusted facts. Before any tool or physical command, perform **fresh** authorization and revocation checks; never treat an earlier gateway ALLOW as perpetual authority.

### Envelope for DELEGATE and MOVE messages

This policy does **not** define its own envelope. A message whose intent is DELEGATE or MOVE/CHECKPOINT_TRANSFER carries the canonical [handoff envelope `0.2.0-draft`](how-it-works.md#canonical-handoff-envelope-020-draft) (schema: [`schemas/handoff-envelope.schema.json`](../schemas/handoff-envelope.schema.json)) as application metadata; it is not native A2A wire schema. DELEGATE maps to `operation: "delegate"` and MOVE/CHECKPOINT_TRANSFER to `operation: "relocate"`. The other intents (READ/QUERY, RESULT/STATUS/EVENT, TOOL_ACTION, SPAWN/REPLICATE, DEVICE_COMMAND, CANCEL/REVOKE) are not handoffs and do not use this envelope. The earlier `agent-communication/0.1-proposal` example is retired; its fields map to canonical names as listed in [Envelope field naming (2026-10-16)](how-it-works.md#envelope-field-naming-2026-10-16).

This policy extends the canonical envelope in two ways:

- **The `message` block**, defined in the canonical schema for this policy: `message.message_id` identifies the message that carries the envelope, `message.parent_message_id` links replies, and `message.expires_at` is the delivery TTL (at most 300 seconds after sending in Phase 1). The TTL is separate from `authority.expires_at`, the expiry of the authority itself.
- **Policy constraints** that a schema-valid envelope must also meet before the gateway sends it (Phase 1 defaults, section 4): `context.classification` is `public` or `synthetic`; `authority.delegation_depth` is 0 (our reading of "one delegation hop": the destination may not delegate onward); `authority.grant_ref` is present (COM-03); `authority.approval_ref` references the policy approval even when no human approval is required, because the schema always requires it; payload at most 256 KiB.

Example (all values synthetic; the artifact digest is the placeholder artifact used in [how it works](how-it-works.md#examples)):

<!-- envelope-example -->
```json
{
  "schema_version": "0.2.0-draft",
  "movement_id": "mov-public-fixture-123",
  "logical_task_id": "public-fixture-123",
  "operation": "delegate",
  "origin": {"agent_id": "urn:example:agent:researcher"},
  "destination": {"agent_id": "urn:example:agent:reviewer"},
  "task": {"kind": "summarize_public_fixture"},
  "context": {
    "classification": "public",
    "purpose": "synthetic_research_demo",
    "artifact_refs": [{
      "ref": "opaque-storage-reference",
      "sha256": "af7688acddc82b568a78f804c84de44631eee954d4c72a0571da1f6e74042854"
    }]
  },
  "authority": {
    "approval_ref": "policy-approval-public-fixture-123",
    "grant_ref": "opaque-identifier-not-a-reusable-token",
    "delegation_depth": 0
  },
  "execution": {"idempotency_key": "opaque-operation-id"},
  "observability": {"trace_id": "opaque-trace-correlation"},
  "message": {
    "message_id": "msg-generated-by-runtime",
    "parent_message_id": null,
    "expires_at": "2026-10-15T20:15:00Z"
  }
}
```

**Critical:** sender/recipient are *claims* for correlation, not proofs. An authenticated transport/session verifier derives the actual principals separately. The policy engine receives independently verified time, grants, scopes, endpoint and classification labels from platform services. References must be resolved with separate ACLs and may never be pre-authenticated bearer URLs. Reject forged metadata even if a message field looks reasonable. The example timestamp is illustrative and not an active credential.

## 5. How this interacts with current protocols

- **A2A 1.0:** provides agent discovery, messages, tasks, artifacts, updates, multiple bindings and authentication/authorization hooks. Its server authorizes requests under local policy. The spec says Send Message operations MAY be idempotent and agents may use `messageId` to detect duplicates; do not assume universal exactly-once behavior. [Specification v1.0.1](https://a2a-protocol.org/v1.0.1/specification/).
- **MCP 2026-07-28:** exposes structured tools/resources/prompts and an HTTP authorization model. Servers **MUST** "Validate all tool inputs", "Implement proper access controls", "Rate limit tool invocations" and "Sanitize tool outputs" ([tools, security considerations](https://modelcontextprotocol.io/specification/2026-07-28/server/tools#security-considerations)). What the spec requires about trust in tool metadata and results, quoted exactly (accessed 2026-10-16):
  - *Normative, annotations only:* "For trust & safety and security, clients MUST consider tool annotations to be untrusted unless they come from trusted servers." ([tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools), `annotations` field)
  - *Overview, lower-case and so not a BCP 14 keyword* (the spec applies RFC 2119/8174 keywords "when, and only when, they appear in all capitals"): "Tools represent arbitrary code execution and must be treated with appropriate caution. In particular, descriptions of tool behavior such as annotations should be considered untrusted, unless obtained from a trusted server." ([specification, Tool Safety](https://modelcontextprotocol.io/specification/2026-07-28))
  - *Normative, results:* "Clients SHOULD: … Validate tool results before passing to LLM" ([tools, security considerations](https://modelcontextprotocol.io/specification/2026-07-28/server/tools#security-considerations)).
  - **Project guidance, not an MCP requirement:** this project goes further and treats every tool `description` and every tool output as untrusted content, whatever the server, unless trusted through an independent channel (COM-07). The spec makes only annotations a MUST, and leaves result validation at SHOULD. Rationale: a published demonstration used hidden instructions in a tool `description`, not an annotation, to make a Cursor agent exfiltrate `~/.cursor/mcp.json` and SSH keys ([AMN-003](news-corpus/digest.md#amn-003)).
- **Human/UI plane:** can display approvals, messages and status, but the UI does not replace signed/verified approval records, and absence of a UI does not confer implicit consent.
- **IAM and policy:** OAuth 2.0 token exchange (RFC 8693), SPIFFE workload identity and OPA/Rego are useful building blocks; none alone implements every control. Grant issuers and verification infrastructure must be operated independently of untrusted agent output.
- **Observability:** traces correlate events, but plain logs are not sufficient forensic proof of sender identity or policy compliance. See [forensics](agent-forensics-and-fingerprints.md).

## 6. Delivery lifecycle and multi-party controls

1. **Preflight:** origin resolves a pinned destination identity/capabilities using *minimum necessary* public metadata; no private task context is disclosed.
2. **Authorize:** policy verifies actual sender, user intent, tenant, task, audience, expiry, purpose, data class, recipient and budget.
3. **Approve if required:** authorized human confirms a specific action. Expire or invalidate approval when action parameters change.
4. **Dispatch:** origin egress gateway sends an authenticated, protected message; encrypted transit alone does not prevent sending to a wrong authenticated peer.
5. **Admit:** destination verifies identity, grant and payload independently; distinguishes ACCEPTED from COMPLETED.
6. **Act:** each tool/robot/controller makes its own fresh authorization decision and uses limited capabilities.
7. **Reconcile:** preserve operation IDs and distinguish safe retry of idempotent reads from ambiguous one-time effects; observe status before retrying.
8. **Return:** publish only permitted artifacts and sanitized provenance; origin validates artifact integrity and acceptable output class.
9. **Revoke/cancel/expire:** close grants and channels, block further effects, report remaining unknown/irreversible actions.
10. **Audit:** preserve a minimal, access-controlled event timeline; investigate mismatched or missing receipts.

### Communication and mobility are independent permissions

- "Agent B can answer questions" does not mean "B may take over A's identity or execution".
- "A may call a tool" does not mean "A may give that tool capability to B".
- "A may copy public context" does not mean "A may export the underlying memory store".
- "A may spawn a worker" does not mean "worker may spawn more workers".
- "A may receive a push notification" does not mean "webhook may target arbitrary local endpoints".
- "A may collaborate" does not mean "A and B may collectively evade a per-agent limit"; quota and effect accounting require shared scope.

## 7. Failure, attack and assurance approach

**Threats to test:** identity spoofing, fake Agent Cards, unauthorized recipient, prompt injection across agents, deceptive success reports, malicious "approve" texts, token passthrough, leaked memory, artifact-ref exfiltration, DNS rebinding/SSRF, callback forgery, replay, permission amplification, covert fan-out, oversize streams, cross-tenant mistakes, denial of service, revocation races, coordinated multi-agent side effects and lack of network mediation.

**Verification layers:**

- *Static/configuration tests:* policy schema, deny-by-default behavior, explicit scope and data classifications, bounded TTL/hops.
- *Unit/property tests:* unknown fields, wrong recipient, expiring/revoked grants, reused IDs, classification lattice, monotonic scope attenuation, concurrency budget.
- *Integration tests:* independent authenticated senders and receivers, **zero private bytes sent before authorization**, tool-side permission checks, queue subscriber ACLs, direct egress blocked.
- *Adversarial tests:* compromised model instructions, collusion and prompt injection, rogue endpoints, reordered/delayed messages, trusted-principal token abuse.
- *Chaos tests:* drop acknowledgments, network partitions, delayed cancellation, policy service outage, audit service outage, restart mid-side-effect.
- *Evidence:* capture sanitized decision events and tool/device receipts, compare them with packet-level egress counters and independent audit records.

The associated [communication conformance case matrix](../data/agent-communication-conformance-cases.csv) specifies expected outcomes, boundaries and evidence for cases COM-T001 to COM-T028. Whether a case has a test is recorded only in the single [test registry](../data/test-registry.csv): each case is a registry row, or, where it duplicates another list's case, an alias of that row (the matrix's `registry_id` column names it). Many cases are still **planned tests, not passing tests**. A passing set of synthetic tests cannot prove safety against a compromised runtime, undocumented out-of-band channels, covert exfiltration or unforeseen behaviors; prefer bounded threat-model claims over "agents can never violate rules."

## 8. Research questions for the next five years

1. **Compositional authority:** Can proofs of least privilege remain valid over arbitrary delegation chains and cross-organization links?
2. **Pre-disclosure verification:** How can a sender prove remote agent identity, execution environment and data-retention commitments *before* releasing private context?
3. **Multi-agent collusion:** How do we detect when individually permitted messages together implement an unauthorized collective action?
4. **Covert channels:** What bounds are possible on confidential-information leakage through summaries, embeddings, timing, tool choice and apparently harmless text?
5. **Counterfactual accountability:** Which authenticated traces make it possible to tell whether a decision was caused by a given message, policy or compromised endpoint?
6. **Revocation latency:** Can we bound the number and impact of external actions after authorization is revoked across partitions and partially disconnected devices?
7. **Policy portability:** Can independent implementations interpret the same action/scope/approval semantics without silently broadening permissions?
8. **Machine-checkable lifecycle:** Can model checking or reference monitors establish practical invariants about fan-out, idempotency and budget compliance?
9. **Human comprehension:** Which approval interface enables users to understand compound risk without confirmation fatigue?
10. **Safety-critical messaging:** How should AI-intent messages be transformed into bounded actuator commands with separately verified real-time safety guarantees?

These are research problems, not claims of unpublished novelty.

## 9. Proposed next implementation milestones

**P0 — contract and tests:** version policy input schema and grants; publish fixed synthetic test vectors; create an independent offline decision evaluator; test deny-before-disclosure; do not insert credentials in messages.

**P1 — real network mediation:** deliver a preflight + outbound gateway and inbound middleware, authenticated peer binding, sandbox egress controls and minimal, redacted audit trail. Connect to the existing [peer-authentication issue #8](https://github.com/MSKazemi/agent-movement/issues/8) and [local handoff PR #6](https://github.com/MSKazemi/agent-movement/pull/6). Do not merge a nominal "policy engine" without a proven PEP covering the actual network and effect paths.

**P2 — tools and adverse conditions:** add tool-side checks, durable operation deduplication, cancellation/revocation races, quota fencing, independent audit/forensics and multi-agent budget tests.

**P3 — federated, device and physical safety:** negotiate policy semantics cross-tenant; independently validate identities and destinations; test denied movement/replication; involve safety-engineering review and hardware interlocks before any robotics use.

**Exit gate:** Publish a bounded safety claim that names the protected boundaries, out-of-scope threat actors, independent tests run, residual bypasses and evidence. A document or model prompt cannot itself enforce the policy.

## Primary sources (verified 2026-10-15)

- [A2A Protocol v1.0.1 specification](https://a2a-protocol.org/v1.0.1/specification/) (v1.0.1 is a bug-fix release of v1.0.0) — messages, tasks, discovery, authn/authz and partial idempotency semantics.
- [MCP specification 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28) and [MCP tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools) — tool boundaries and client/server obligations.
- [OWASP Top 10 for Agentic Applications 2026](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/) — agentic security risks, including inter-agent abuse.
- [NIST AI Agent Standards Initiative](https://www.nist.gov/artificial-intelligence/ai-agent-standards-initiative) — current interoperability, identity, authorization and security research activity; not a prescriptive communication policy.
- [OPA policy engine](https://www.openpolicyagent.org/docs) — separation of policy evaluation and enforcement.
- [RFC 8693 OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693) — scoped token exchange primitives.
- [SPIFFE/SPIRE concepts](https://spiffe.io/docs/latest/spire-about/spire-concepts/) — workload identity building blocks.
- [OpenTelemetry semantic conventions for generative AI](https://github.com/open-telemetry/semantic-conventions-genai) (moved out of opentelemetry.io; status Development) — observability vocabulary, not proof of causality or authorization.
