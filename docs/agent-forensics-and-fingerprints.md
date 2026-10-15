# Agent fingerprints, movement tracking, and digital forensics

**Research date:** 2026-10-15  
**Status:** Research and proposed architecture; **not implemented or validated in this repository**.  
**Scope:** AI-agent tasks and executions moving between runtimes, machines, services, frameworks and administrative domains. This is not physical tracking and not a proposal for covert surveillance.

## The central idea: a Sherlock Holmes for agent movements

Agent Movement needs an **evidence-based movement graph**: who initiated a task, which verified executor accepted it, which resources/tools it touched, what was copied, delegated or resumed, and which artifacts and external effects resulted. Forensic findings should include source evidence and uncertainty, not just a pretty timeline.

A **fingerprint is not necessarily an identity**. Distinguish:

1. **Authenticated workload identity**: a trusted issuer binds a workload principal to a credential (for example, SPIFFE/SVID). This can establish which *authenticated workload* made a request, subject to issuer, key and endpoint security.
2. **Definition/configuration fingerprint**: hash of normalized declared agent code/version, model *declaration*, tool manifest, policy version and runtime image. This identifies a declared configuration, **not a unique living agent**. Copies can share it.
3. **Execution/run identity**: a unique local execution ID with verified start/stop provenance, distinct from the logical agent definition.
4. **Task and movement identity**: one stable logical task ID and a fresh movement ID for each directed transfer; the receiver's A2A task ID is not necessarily the origin's task ID.
5. **Artifact/checkpoint fingerprint**: content digest of a defined byte representation. It proves integrity against a trusted reference digest, not authorship or the correctness of the content.
6. **Behavioral fingerprint**: observed patterns of outputs, tool use, latency and error types. This is noisy, vulnerable to mimicry, prompt/model changes and false positive identity matches. It is investigative context, not proof.
7. **Network/API evidence**: authenticated service/API audit logs, endpoint/certificate evidence and tool authorization decisions. IP addresses or User-Agent headers alone are weak identifiers.

No public standard provides a universal, unforgeable fingerprint for *any* AI agent on the open internet. Cross-organization tracking requires cooperating, authorized participants and verifiable receipts; a destination can otherwise hide or refuse to emit observations.

## Evidence inventory and relative strength

| Evidence item | Best question answered | Strength when verified | Failure/ambiguity |
| --- | --- | --- | --- |
| SPIFFE ID + verified SVID/mTLS session | Which workload authenticated? | Strong workload authentication | Identity issuance/key compromise; not logical model identity |
| Credential issuer/audience + policy decision reference | Was that workload allowed to receive or act? | Strong if server-side validated | Revocation race; permission != execution |
| Paired signed dispatch and receiver-accept receipts | Which handoff was mutually acknowledged? | Strong for the witnessed hop | A recipient may be untrusted; missing receipt leaves unknown state |
| Stable task/movement/execution IDs | Which events should correlate? | Strong correlation *within controlled instrumentation* | IDs may be forged or accidentally reused without auth |
| OpenTelemetry trace/span + GenAI metadata | Where was work instrumented? | Good visibility into observed operations | Sampling, dropped spans, broken propagation, incomplete instrumentation |
| A2A task/context IDs and task events | What did the A2A peer say about task status? | Good protocol-level linkage | Local A2A IDs are not global identities or security proofs |
| Tool-side audit and idempotency/effect ID | Was an external action committed? | Strong if sourced independently at the target | Client-side 'success' can disagree with target state |
| Content digest and signed artifact manifest | Has evidence/artifact changed? | Strong integrity check | Matching hash does not mean benign/correct input |
| Timestamp, host/container, workload metadata | Where and when was execution observed? | Useful corroboration | Clock skew; host spoofing; restarts |
| Output style or model-text 'watermark' guess | Does it resemble another agent/model? | Weak hypothesis only | Imitation, model updates, style steering; no safe identity conclusion |

**Evidence grades for this project (proposal, not standardized):**
- **E3 — cryptographically corroborated:** verified identity and signed linked receipts, independently anchored evidence, target-side action confirmation when relevant.
- **E2 — corroborated operational records:** independently consistent authenticated service, policy and tool logs, without complete signed chain.
- **E1 — correlated self-reported telemetry:** IDs, spans and event logs from a limited set of emitters.
- **E0 — inference only:** behavior, timing, language style, IP address similarity or unverified assertions.

An E3 event establishes only the claims within its verified trust boundary. Even signatures do not guarantee truthful execution or that *all* relevant events were logged. Never convert the grades automatically into probabilities.

## Identity and lineage model: move != clone

Keep separate fields for:

- \`agent_definition_id\` + \`definition_digest\`: declared agent design/build; multiple instances can share it.
- \`workload_principal\`: authenticated service/workload identity, with issuer/trust-domain and verification result.
- \`agent_instance_id\`: concrete instance/container/process lifecycle; changes on restart.
- \`execution_id\`: attempt/run; may change when a logical task resumes.
- \`logical_task_id\`: application-assigned continuity across agents.
- \`movement_id\`: new globally unique identifier per proposed source -> destination transition.
- \`parent_movement_id\`: transfer ancestry if there is a previous hop.
- \`parent_execution_id\`, \`lineage_relation\`: \`delegate\`, \`relocate\`, \`clone\`, \`fork\`, \`replicate\` or \`fan_out\`; the chosen meaning must be documented.
- \`origin_a2a_task_id\`, \`destination_a2a_task_id\`, \`a2a_context_id\`: local A2A protocol identifiers where available; do not assume a client can create a server task ID.
- \`trace_id\`, \`span_id\`: W3C trace context values; useful for correlation, **not credentials or proof of identity**.
- \`fencing_epoch\`: monotonic coordinator epoch for relocation authority; clone/delegation have different authority rules.

A **relocation** preserves logical task identity but starts a different execution under an explicitly transferred/fenced lease. A **clone** or **fan-out** creates separately identifiable descendants with distinct authority and effect budgets. If two executions share a definition digest, that alone does not make them the same agent.

## Proposed auditable movement lifecycle

~~~mermaid
flowchart LR
    A[Origin runtime] --> P[Policy and identity verification]
    P --> D[Signed dispatch receipt]
    D --> B[Destination runtime]
    B --> R[Signed acceptance receipt]
    B --> T[Tool and artifact activity]
    T --> L[Independent effect/audit records]
    D --> F[Evidence index and graph]
    R --> F
    L --> F
    F --> Q[Investigator timeline and confidence report]
~~~

1. **Before transfer:** verify the destination principal (for example, mTLS/SVID within configured trust), policy, approvals and data restrictions; bind operation and allowed recipient.
2. **Dispatch:** origin emits a unique movement event and (when assurance requires) signs a receipt over canonicalized, non-sensitive metadata and a digest of the *approved* envelope.
3. **Acceptance:** recipient validates authentication, policy and version; emits a distinct acceptance receipt, or a reasoned rejection. The two records can be compared.
4. **Execution:** instrument agent operations and tool calls with OpenTelemetry GenAI conventions and trace propagation; keep tool/service-side audit records separately. Capture external effect intents, results and reconciliation status.
5. **Completion or unknown:** record artifact/checkpoint digest and state, receiver acknowledgment, the issuer of any delegated grant, and revocation/fencing results. On timeout, **unknown/reconcile** is not equivalent to success or failure.
6. **Forensic preservation:** export append-only audit events to a controlled evidence store; retain ingestion metadata, signatures, verification reports, chain-of-custody actions and timestamps from multiple sources. Use independent anchoring/checkpoints to detect deletion or wholesale rewrite.

OpenTelemetry trace context solves correlation, not tamper-proof audit or identity. Keep security-critical audit receipts **unsampled** even when performance traces are sampled. A trace without spans is not proof that the action never happened. W3C Baggage can leak context across trust boundaries; do not put secrets or personal information into propagated headers.

## Minimum event contract (research sketch, NOT a wire standard)

Use stable, versioned field meanings and verify the sender against the receiving endpoint's authentication context. Fields absent from some operations should be null/omitted rather than invented. This example is synthetic.

~~~json
{
  "schema_version": "0.1.0-research",
  "event_id": "evt-example-002",
  "event_type": "movement.accepted",
  "event_time": "2026-10-15T09:04:02Z",
  "observed_time": "2026-10-15T09:04:03Z",
  "logical_task_id": "task-example-104",
  "movement_id": "mov-example-051",
  "parent_movement_id": null,
  "lineage_relation": "delegate",
  "source": {
    "workload_principal": "spiffe://example.test/agent/a",
    "execution_id": "run-example-a-1"
  },
  "destination": {
    "workload_principal": "spiffe://example.test/agent/b",
    "execution_id": "run-example-b-1",
    "a2a_task_id": "server-issued-task-example"
  },
  "trace": {
    "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
    "span_id": "00f067aa0ba902b7"
  },
  "authority": {
    "policy_decision_ref": "decision-example-7",
    "fencing_epoch": null
  },
  "evidence": {
    "envelope_digest_ref": "digest-record-example-3",
    "receiver_receipt_ref": "signed-record-example-2"
  },
  "outcome": "accepted",
  "data_classification": "synthetic",
  "retention_policy_id": "research-synthetic-short"
}
~~~

This illustrative event **does not itself verify** the principals or prove any cryptographic guarantee. To make it evidence:
- Define the immutable receipt body, precise canonicalization (consider RFC 8785 JCS), digest and signature algorithms, domains, replay window and signature field *outside* the signed body.
- Independently resolve and verify the signing identity against an allowlist/issuer and relevant validity time, key rotation/revocation and authorized recipient.
- Store the receipt digest, trusted ingestion timestamp, sequence/previous-digest links, signed source + destination assertions and independent checkpoint/anchor. A simple hash chain without an independently trusted anchor can be entirely rewritten.
- Verify artifact bytes against their recorded digest; avoid hashing low-entropy private information into public artifacts or exposing reusable token references.
- Record missing evidence as missing. Never fill gaps with guessed agent identities.

Suggested event types: \`task.started\`, \`movement.requested\`, \`movement.dispatched\`, \`movement.accepted\`, \`movement.rejected\`, \`authority.granted\`, \`authority.revoked\`, \`authority.fenced\`, \`execution.started\`, \`tool.intent\`, \`tool.completed\`, \`tool.unknown\`, \`artifact.created\`, \`checkpoint.created\`, \`execution.failed\`, \`task.completed\`, \`evidence.gap_detected\`. Require a clear difference between *requested*, *observed*, and *confirmed by independent target*.

## Sherlock-style investigation questions

| Investigation | Primary evidence / query | What an honest answer says |
| --- | --- | --- |
| Where did a task travel? | Graph traversal on movement_id, source/destination receipts and parent IDs | Observed path; indicate uninstrumented gaps |
| Who actually invoked a tool? | Verified workload auth + tool-side audit keyed by operation/effect ID | Authenticated invoker, not the human or model that 'intended' it |
| Was a destination swapped? | Compare expected principal, issuer, audience and signed acceptance | Mismatch => deny + preserve evidence |
| Did the task fork or clone? | One ancestor -> multiple distinct child execution/movement IDs and lineage relations | Multiple descendants, not a single migrating process |
| Was state tampered with? | Canonical digest checks, signatures and append-only anchors | Verified mismatches; if no trusted baseline, inconclusive |
| Did revoked Agent A still act? | Fence epoch, grant-revocation decision and tool-side commit time | Unauthorized attempted/committed effects, not just a stale trace |
| Did an action happen twice? | Two committed effect IDs/target records for the same logical intent | Duplicate effect only with independent target confirmation |
| Is this the same 'mysterious' agent? | Weak behavior similarities vs verified identity chain | Similarity is a hypothesis, never identity proof |
| Where did telemetry go missing? | Unmatched dispatch/accept and audit-to-trace reconciliation | A gap or timeout; not automatically malice |

### Detection rules worth prototyping

- **Sev high:** verified tool commit after revocation/fencing epoch; two accepted, concurrently active owners for one single-writer task; effect ledger reveals duplicate committed operation.
- **Sev high:** artifact hash mismatches; untrusted principal accepts private/sensitive handoff; invalid signature or wrong audience on supposed movement receipt.
- **Sev medium:** dispatch with no receiver receipt after a policy-defined time; unexpectedly changed declared definition/config digest; missing tool-side confirmation.
- **Investigate (not an accusation):** unusual agent communication patterns or output style; changed routing or rate, uncorroborated network metadata.

Use causal edges and receipt sequence to reconstruct order. Clock synchronization helps, but timestamps alone can be inaccurate or adversarially supplied.

## Recommended implementation strategy

**Keep the project's delegation-first sequence.** Phase 1 should use only synthetic/public tasks and two local A2A-capable agents; it is enough to show the first real, auditable handoff.

| Phase | Deliverable | Suggested standards/building blocks | Exit test |
| --- | --- | --- | --- |
| F0 — definitions | Identity/lineage/event contract; evidence grades and privacy rules | A2A Task/Context IDs; W3C trace context | Schema examples and clear ambiguity semantics |
| F1 — correlated trail | Trace and movement graph for two local agents | OpenTelemetry GenAI, traceparent; local JSONL/SQLite for audit | A -> B -> tool -> result shown with trace correlation |
| F2 — verified receipts | Sender dispatch + recipient accept, key binding and independently preserved audit | SPIFFE/SVID (or test identity provider), RFC 8785 canonicalization; signing approach such as in-toto/Sigstore where suitable | Forged sender/modified receipt/unauthorized destination rejected |
| F3 — forensic replay | Queryable cause/lineage graph, immutable evidence export and tamper check | Append-only evidence service; optional graph UI | Reports evidence gaps instead of inventing events |
| F4 — cross-runtime & adversarial testing | Crash, replay, clone/fork, false attribution and compromised-log experiments | A2A adapters, target-side effect ledger and fault injection | Deterministic negative tests and published limitations |

**Initial prototype data model:** relational \`events\`, \`executions\`, \`movements\`, \`artifact_digests\`, \`tool_effects\`, \`evidence_sources\`, \`verification_results\` tables and a read-only graph projection. Avoid introducing blockchain as a requirement: secure append-only storage plus signed periodically anchored checkpoints may suffice, depending on threat model.

**Metrics:** percentage of handoffs with paired verified receipts; percentage of tool actions with target-side confirmations; audited transition coverage; missing-event rate; forged-identity acceptance rate (target zero in fixtures); time to reconstruct a path; false attribution rate; secret leakage and retained-bytes counts; time-to-revoke/fence; proof-verification failures. Distinguish simulation pass rates from production guarantees.

**Adversarial test fixtures:**
1. Same definition digest used by two different replicas — must not merge identities.
2. Replayed valid signed dispatch — must be rejected or explicitly deduplicated.
3. Forged traceparent / changed self-reported agent name — must not confer identity.
4. Delayed accept after origin timeout — must reconcile, not silently invent a failed handoff.
5. Missing recipient-side evidence — report unknown, do not infer a path.
6. Receiver compromised or lying — show limits of source-only evidence.
7. Artifact bytes altered after receipt — digest verification fails.
8. Clock skew / reordered messages — causal reconstruction remains conservative.
9. Telemetry sampler drops a span — audit receipt still exists.
10. Revoked origin issues a delayed tool call — downstream tool-side fence rejects it.
11. Changed model declaration but same output style — configuration evidence wins over behavior guesses.
12. Privacy canary in tool arguments or propagated headers — blocked/redacted before export.

## Privacy, safety, and limits

- Collect only for **authorized systems and purposes**. Avoid covert cross-service fingerprinting, identity stalking and collection of unrelated user/device identifiers.
- Default to **metadata, bounded retention, least-privilege access, redaction and local/synthetic fixtures**. Raw prompts, memory, private chain-of-thought, cookies, API keys, full tool arguments and personal data must not be included by default.
- Correlation IDs should be opaque and scoped. Treat multi-domain IDs as sensitive linkable metadata; do not put user identity or secret grants into \`baggage\`, \`traceparent\` or public attestations.
- For incidents, record collector identity, export time, source, verification procedures and every evidence-handling step (chain of custody). Keep the original source evidence separate from analytic enrichment.
- A signature proves that a key signed particular data; not that the event actually occurred as described. A digest proves consistency with a trusted reference; not authorship. A log gap is not evidence of absence.
- EU and other privacy/legal requirements need review before deployment; this proposal is **not a legal/compliance certification**.

## Research answers and remaining uncertainties

**What we can do today using existing building blocks:** instrument trusted agent runs, connect local A2A interactions to W3C/OTel traces, correlate tool and artifact events, authenticate known workload identities, and verify receipts when both systems cooperate. The project itself has **implemented none of this yet**.

**What is not solved by these building blocks:** tracing agents that do not participate, exposing private model state, proving authorship from writing patterns, universal model identification, comprehensive traces despite lost telemetry, proving truthfulness of a compromised signer, or guaranteed exactly-once external side effects.

**Open questions for this project:**
1. Who issues and verifies a logical **agent** identity distinct from the runtime's workload identity?
2. What should the smallest privacy-safe, signed movement receipt contain to support independent cross-domain verification?
3. How do we make the evidence graph express *unknown*, *unverified*, *disputed* and *partially trusted*, rather than a falsely complete path?
4. What are the security and quality impacts of one globally correlated movement ID across organizations?
5. Which events must never be sampled, and how can an auditor detect silent log deletion?
6. Which behavior features are useful for anomaly alerting without false identity attribution or inappropriate surveillance?
7. How do clone/fork lineage and ownership/fencing influence responsibility for tool-side effects?
8. How can an investigator independently confirm external effects without exposing private payloads or exceeding access permissions?

## Primary references reviewed 2026-10-15

- [A2A v1.0 — task IDs, context IDs and lifecycle](https://a2a-protocol.org/v1.0.0/specification/) — task ID is server-generated and context ID groups related work.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/) — request correlation and portable trace propagation, not identity.
- [OpenTelemetry GenAI agent spans (maintained conventions repository)](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md) — agent, model, tool and conversation-related span fields.
- [OpenTelemetry tracing SDK/sampling](https://opentelemetry.io/docs/specs/otel/trace/sdk/) — sampled traces can omit evidence.
- [SPIFFE Working with SVIDs](https://spiffe.io/docs/latest/deploying/svids/) and [SPIRE concepts](https://spiffe.io/docs/latest/spire-about/spire-concepts/) — workload identities/attestation within trust domains.
- [OpenLineage specification](https://github.com/OpenLineage/OpenLineage/blob/main/spec/OpenLineage.md) — job/run/dataset provenance; potentially reusable for artifact/data lineage, *not* a universal agent mobility specification.
- [in-toto attestation framework](https://github.com/in-toto/attestation) and [Sigstore/Cosign attestation verification](https://docs.sigstore.dev/cosign/verifying/attestation/) — verifiable attestations, requiring validation of signer/trust/predicate.
- [RFC 8785 — JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785.html) — repeatable hashing/signing representation.
- [W3C Baggage privacy considerations](https://www.w3.org/TR/baggage/) — avoid propagating sensitive metadata.
- [NIST SP 800-86](https://csrc.nist.gov/pubs/sp/800/86/final) — chain of custody and forensic evidence handling.

See also [how it works](how-it-works.md), [security and trust](security-and-trust.md), [open questions](open-questions.md), and [roadmap](roadmap.md).
