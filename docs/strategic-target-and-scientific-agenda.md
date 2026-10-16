# Strategic target and scientific research agenda (2026-10-15)

**Status:** Research recommendation, not an adopted standard or an implemented product.  
**Repository assessed:** MSKazemi/agent-movement, default branch on 2026-10-15.  
**Scope:** Software agents and movable **work**, not physical robot motion.  
**Evidence level:** Selective primary-source and peer-reviewed-source scan, not a systematic literature review. Novelty and performance require experiments.

## 1. Recommendation: build Agent Mobility Lab, not another agent framework

**Mission:** Make it possible to **measure, explain and safely implement** the transfer of an AI agent's work across runtimes, computers, models and trust boundaries.

**Narrow initial product:** An **open-source mobility conformance and benchmark lab**, paired with a **small, policy-gated handoff and resumable-execution reference implementation**.

**North-star demonstration:** A synthetic long-running task begins on Worker A, reaches a defined resumable boundary, is authorized for Worker B, and continues with verified artifacts, auditable lineage and bounded execution authority. When the transfer cannot be safe or semantically compatible, it refuses or returns **unknown/reconcile** with evidence instead of pretending the move succeeded.

**Positioning** (one statement, used verbatim in the [README](../README.md), the [2031 frontier agenda](2031-frontier-research-agenda.md) and `CITATION.cff`):

<!-- positioning:start -->
Agent Movement is a research prototype: an open, evidence-first testbed built to make claims about safely moving AI-agent work between executors falsifiable. It currently pairs ranked research questions with synthetic, localhost-only Python prototypes and MobilityBench v0.1, a frozen, deterministic, LLM-free benchmark of 18 synthetic tasks that scores keeping, restarting and locally delegating work under injected faults and reports refusals and unavailable baselines instead of hiding them. It is not production software, a new agent protocol or a rival to A2A or MCP.
<!-- positioning:end -->

**What it is NOT:** a new LLM model, a universal agent operating system, a replacement for MCP/A2A, a promise of lossless cross-framework reconstruction, a way to extract hidden reasoning/model internals, or a system for self-installation on third-party devices.

### Why this is a stronger target than a protocol-only project

- A2A v1.0 already specifies inter-agent discovery, tasks, artifacts, status and protocol bindings. A2A has extensions and existing authentication/security models; any mobility-specific additions should begin as an **application profile**, not a rival wire protocol [R1].
- MCP 2026-07-28 already specifies a largely stateless tool/context interface and an opt-in long-running Tasks extension. It does **not** make the agent's own running application checkpoint portable [R2].
- Open Agent Specification (Agent Spec) already represents **agent definitions** across frameworks and demonstrated that framework-dependent behavior remains different even with common specifications; avoid duplicating definition portability [R3].
- LangGraph and Temporal provide durability **inside their respective runtime models**, not a general semantic-compatibility guarantee between different frameworks [R4, R5].
- NIST's 2026 AI Agent Standards Initiative explicitly prioritizes interoperability, security and identity. A reproducible evidence-producing open-source lab maps to those needs more directly than an untested broad claim [R6].

**Potential contribution, not proven novelty:** An explicit *continuation contract* combining allowable task state, authority transfer/fencing, effect reconciliation, compatibility/loss reports and reproducible comparisons between handoff, resumption, reconstruction and restarting. A thorough prior-art review is needed before claiming a new standard or publishable novelty.

## 2. Current repository assessment

| Already present (research/design) | Missing evidence or implementation |
| --- | --- |
| Definitions of delegation, copying, cloning, replication, relocation and migration | Executable reference SDK, adapters and two-agent example |
| A2A/MCP/AG-UI/runtime/security comparison | End-to-end A2A interoperability smoke test |
| Draft handoff envelope, lifecycle, trust model | Formal validated schema and compatibility negotiation |
| Ranked scientific questions (AM-01 to AM-16) | Registered experiments, datasets, pinned environments and measured results |
| 134 candidate device classes and capability matrix | Verified support for any actual device/runtime pair |
| Forensic/event schema and lineage proposal | Independent evidence receipts, verifier and investigator-grade trace tests |
| Research corpus and references | Reproducible benchmark harness, failure injection and quality/cost baselines |

This repo is **documentation-first, not yet a working migration library**. See [open questions](open-questions.md), [roadmap](roadmap.md), [forensics](agent-forensics-and-fingerprints.md) and [device matrix](device-compatibility-and-capability-matrix.md). The best immediate value is to turn its existing hypotheses into a reference implementation plus independently checkable results.

## 3. Choose a target audience and first use case

**Primary early users:** agent-framework maintainers, reliability/security engineers working on agent applications, and distributed-systems/AI researchers who need comparable migration evidence.

**Secondary users:** teams running agent workflows across laptops, cloud workers and edge hosts, once authorization and failure handling are demonstrated.

**First reference scenario:** A developer starts a long-running *synthetic or public-data* coding/document-analysis workflow locally; a second isolated worker performs an approved step and returns an artifact. A later experiment resumes the **same logical task** from a durable checkpoint after an induced worker failure. No real purchase, deployment, device control, production token or private user data is needed.

This scope has practical infrastructure value and a clean scientific baseline. **Do not start** with unrestricted phones, robots, smart-home controls, an agent marketplace, or active-active swarms. These multiply platform, safety and consent variables before the core transfer contract is understood.

## 4. Strategic option ranking

These are **qualitative judgments**, not measured market scores.

| Project direction | Scientific upside | Initial feasibility | Adoption pathway | Decision |
| --- | --- | --- | --- | --- |
| **Safe task continuation + MobilityBench** | High: explicit invariants, semantic loss, failure recovery | Medium | Framework developers, SRE, research reproducibility | **Primary focus** |
| **Agent movement forensics / provenance verifier** | High: lineage evidence, conflicting accounts, attribution limits | Medium-high | Security, audit, incident response | **Co-develop as the differentiator** |
| **Portable checkpoint + cross-model compatibility lab** | High: measurable cross-runtime semantics | Medium-low | Research and framework integration | **Second major experiment** |
| **Policy-aware edge/offline agent placement** | High for partitions, heterogeneous resources, privacy | Medium-low | Industrial edge, robotics companion nodes | Later track after safe core |
| **Agent cloning / large-scale multi-agent swarm** | Medium; crowded orchestration field, consistency hard | Medium | Agent-platform operations | Explore only after transfer invariants |
| **New general A2A/MCP rival or agent DSL** | Limited incremental distinction; existing standards | Low strategic fit | Requires major ecosystem adoption | Avoid |
| **Universal live model/process migration** | Potentially ambitious but often technically undefined | Very low across vendors | Unclear | Explicitly outside initial claims |
| **Public marketplace of untrusted agents** | Mixed; governance/reputation hard | Low until security proofs | Commercial discovery | Defer |

**Recommended balance of new project effort** (planning allocation, not measured ROI): 45% reference mobility SDK and control plane; 30% benchmark/fault/security tests; 15% provenance and visualization; 10% interoperability documentation and contributor experience.

## 5. The most valuable open scientific questions

The repository already defines AM-01–AM-16 in [open-questions.md](open-questions.md). The table below reorganizes them into **falsifiable research programs**, rather than presenting generic questions as unsolved facts.

| Rank | Scientific question | Testable hypothesis / experiment | Observable answer |
| --- | --- | --- | --- |
| **P0 / Q1** | **What is the smallest sufficient portable unit?** Is it a task envelope, evidence + constraints, checkpoint, memory snapshot or all four? | Ablate fields from an allowed-state snapshot; compare reference continuation vs transferred continuation, across multiple task classes | Correctness/constraint retention vs payload bytes and disclosure |
| **P0 / Q2** | **When does a move preserve semantic continuity?** Can models or frameworks interpret an identical approved snapshot differently? | Cross model/framework/adapter factorial trials against same-model same-runtime restart; use blinded rubrics and repeat runs | Fidelity, lost constraints, incompatible states and variance |
| **P0 / Q3** | **Can logical task ownership move safely after failures?** How does split brain arise under delayed messages and restart? | Add monotonic fencing epochs checked by a simulated effect gateway; crash each transition and replay stale workers | Unauthorized or duplicate committed effects; explicit unknown states |
| **P0 / Q4** | **What can be asserted about side effects?** When is retry safe after a timeout? | Compare idempotent and non-idempotent simulated tools, durable intent/result ledger and independent reconciliation | Duplicates, ambiguity rate, time-to-reconcile; no blanket exactly-once claim |
| **P0 / Q5** | **Can authority be transferred without forwarding credentials?** What happens when a grant expires or is revoked? | Issue separate audience-, action- and expiry-bounded authorization; attempt replay, wrong-audience and late side effects | Rejected unauthorized actions and evidence of revocation limitations |
| **P0 / Q6** | **Can the destination be judged compatible before disclosure?** Is advertised capability truthful? | Negative tests with forged Agent Cards, missing tools, wrong versions, mismatched policy and tampered artifacts | Pre-disclosure denial, false acceptance, false rejection |
| **P1 / Q7** | **How much context can be minimized safely?** Does selective artifact-reference handoff outperform transcript dumping? | Compare raw history, summarized context, cited artifacts and minimal structured snapshot on paired tasks | Accuracy, privacy canaries, transfer size and token cost |
| **P1 / Q8** | **Can movement evidence survive adversarial disagreement?** What proves lineage vs mere correlation? | Corrupt/omit logs, replay receipts, use independently logged fake tool effects; verify signatures/digests and classify evidence grade | Detection of tampering and explicit uncertainty in reconstruction |
| **P1 / Q9** | **When is movement worth its cost and risk?** | Compare move, restart, keep executing, and ordinary A2A delegation with identical workloads and risk budgets | Quality-adjusted completion, latency, cost, unsafe-action rate |
| **P1 / Q10** | **How do copies/replicas diverge?** Can memory be merged without losing causality? | Fork from one approved snapshot with conflicting updates and tool intents; expose lineage and explicit conflict policies | Conflict rate, incorrect merges, duplicate actions, bounded divergence |
| **P2 / Q11** | **How should agents work under partitions and offline edge constraints?** | Simulate intermittent LAN/cloud connectivity, battery and memory limits, short-lived grants and delayed acks | Deadline success, stale-authority denials, fail-safe outcomes |
| **P2 / Q12** | **Can machine-readable evidence support independent certification or forensics?** | Have an external implementation verify signed metadata, hashes, grant refs, effect receipts and sampled trace claims | Inter-rater agreement and verified-vs-unknown statement accuracy |

### Three publishable-looking hypotheses to test first (not claims of novelty)

**H1 — Typed portability beats naive history replay.** A versioned task/constraint/artifact manifest with explicit lost-state reporting preserves critical constraints and reveals incompatibility better than simply copying a chat transcript. This might be **false** for some workloads; publish those cases.

**H2 — Fencing is necessary for safety, but insufficient for arbitrary external systems.** Within a bounded crash/partition model, a coordinator plus an **effect gateway that validates fencing epochs and idempotency keys** can prevent duplicated **simulated commits**; without cooperation from an external service, uncertain execution cannot safely be retried as though it never occurred.

**H3 — Definition interoperability does not imply continuation interoperability.** Reconstructing a workflow from a portable definition is not necessarily equivalent to resuming its execution, and the difference is measurable in accuracy, constraints, cost and lost state. Agent Spec research establishes adjacent evidence for runtime-dependent behavior, **not this project's result** [R3].

**Recommended scientific paper arc:** (1) vocabulary and safety invariants; (2) implementable continuation contract and verified reference implementation; (3) MobilityBench with fault/security/semantic comparisons and negative results; (4) limitations, reproducibility and interoperability boundaries.

## 6. Technologies worth developing here

Build small *composable* modules that complement upstream standards:

| Module (proposed working name) | Purpose | What you build and test | Existing technology to reuse |
| --- | --- | --- | --- |
| **Mobility Contract / Envelope** | Portable, explicit transfer unit | Versioned JSON Schema, content manifest, operation type, task lineage, required/optional capabilities, rejected/lost fields, digest | JSON Schema, RFC 3339 timestamps; A2A artifacts/metadata where appropriate |
| **Movement Coordinator** | Safe dispatch/relocation state machine | Prepare, validate, authorize, freeze, dispatch, acknowledge, reconcile, complete/cancel; lease and epoch model | Python application service; durable DB; Temporal later only if justified |
| **Movement Authority Gateway** | Fence stale executors and attenuate grants | Per-effect authorization, action/resource allowlist, user approval, revocation, audience/expiry checks; no raw credential transfer | OIDC/OAuth and RFC 8693; OPA policy; SPIFFE/SPIRE for deployed workloads [R7, R8] |
| **Agent Capability Profile** | Compatibility **evidence**, not marketing metadata | Runtime and model versions, checkpoint format, tools, permissions, compute profile, source of verification and freshness | A2A Agent Cards and extension mechanism; device matrix |
| **Adapter Layer** | Keep movement independent of one agent framework | A2A delegate adapter first; same-runtime LangGraph checkpoint adapter second; controlled second-runtime reconstruction only after tests | A2A, LangGraph, Agent Spec; MCP at tool boundary |
| **Effect/Checkpoint Ledger** | Model ambiguity and replay | Durable operation IDs, intent/commit/result states, idempotency, checkpoints, unknown/reconcile workflow | SQLite initially/PostgreSQL later; transactional outbox where applicable |
| **MobilityBench** | The scientific centerpiece | Frozen synthetic tasks, deterministic simulated tools, crash/fault injection, cross-model continuation, metrics and reproducible CI | pytest, Hypothesis, experiment manifests, containerized runners |
| **Movement Forensics** | Explain where a task went and why | Movement graph, receiver/issuer receipts, evidence grades, signed hashes, redacted OpenTelemetry correlation, verifier | OpenTelemetry, W3C Trace Context, standard cryptographic primitives |
| **Placement Research Module** | Decide move vs keep vs delegate | Cost/latency/privacy/resource-aware policy optimizer *after* measured baselines | Kubernetes/OCI/edge simulators; offline profiles |

**Do not** embed permissions or bearer tokens in the portable envelope. Transport identity, actual authorization checks and per-action effect fencing live at independently enforced boundaries. Agent-provided descriptions and trace IDs are **not proof of trust**.

### Suggested conceptual envelope fields (research only)

~~~json
{
  "schema_version": "0.1-draft",
  "operation": "relocate_at_checkpoint",
  "logical_task_id": "task-001",
  "movement_id": "move-002",
  "origin_execution_id": "exec-A",
  "destination_principal_ref": "allowlisted-principal",
  "context_manifest": {
    "data_classification": "synthetic",
    "artifact_digests": ["sha256:example-only"],
    "constraints_ref": "constraints-001"
  },
  "continuation": {
    "checkpoint_format": "specific-runtime-version",
    "checkpoint_digest_ref": "digest-001",
    "compatibility_decision": "requires-validation",
    "accepted_semantic_losses": []
  },
  "authority": {
    "approval_ref": "approved-test-operation",
    "grant_ref": "opaque-reference-not-token",
    "fencing_epoch": 2
  },
  "effects": {
    "ledger_ref": "ledger-001",
    "unresolved_effects": []
  },
  "evidence": {
    "trace_id": "synthetic-opaque-trace-id",
    "receipt_refs": []
  }
}
~~~

No universal wire standard is implied by this shape. **Representation and trust evidence must be pinned, tested and revised** before anyone integrates it with a production agent.

## 7. Architecture and technology stack

### Implement first (minimal dependencies)

- **Primary language: Python** for prototype, JSON Schema/Pydantic, adapter integrations, pytest/Hypothesis and publishable experiments. Do not spread the first implementation across multiple languages.
- **Transport: HTTP(S) with official A2A SDK/bindings** for delegation. Reuse MCP clients only for tools. Do not confuse MCP Tasks with agent-state portability [R1, R2].
- **State: SQLite for isolated reproducible tests**, with an interface for PostgreSQL once a multi-worker transactional lease is needed. An in-memory lease is not crash-safe.
- **Orchestration: a small explicit coordinator state machine** first; LangGraph checkpoint persistence only in the runtime-specific relocation experiment. Avoid hiding ownership guarantees behind a workflow library.
- **Security: default-deny synthetic policy gate** and locally enforced fake effect gateway; OPA is an option when policy complexity grows. Introduce RFC 8693 exchange/SPIFFE only after verifying the deployed trust model [R7, R8].
- **Observability: OpenTelemetry correlation plus a separate append-only evidence store**, with redacted payloads and independent effect receipts. GenAI semantic conventions are evolving; pin referenced versions and do not treat sampled spans as exhaustive evidence [R9].
- **Packaging: dev container / Docker Compose** first; OCI/Kubernetes scheduling is a later test target. OCI image portability is not runtime checkpoint portability.
- **Benchmarks: pytest + deterministic tool simulators + pinned model/provider settings**; retain per-attempt events/metrics with private data excluded.

### Implement later, only when the experiment requires it

- **Go:** a hardened high-concurrency coordinator/policy/effect gateway if Python becomes a bottleneck, not merely for language diversity.
- **TypeScript:** web trace explorer and approval UI, optionally AG-UI. Useful after the underlying evidence ledger works.
- **Rust:** constrained host/verifier or cryptographic components only if a measured security/performance need justifies the extra maintenance.
- **gRPC, NATS or other queues:** internal coordination only if latency, at-least-once delivery or topology testing establishes a need. Keep A2A as the external agent interface.
- **Edge/robotics:** Raspberry Pi/Jetson, simulated ROS 2 companion computing, intermittent connectivity. Keep low-level safety control independent and do not deploy self-propagating software.

## 8. Concrete staged milestones and exit criteria

| Stage | Visible deliverable | Required evidence / release gate |
| --- | --- | --- |
| **S0 — formalize the claim** | Architecture decision record; versioned schema; operation/lineage identifiers; state machine and effect semantics; dataset and protocol freeze | Clear distinction between *delegate*, *copy*, *fork*, *replicate*, *relocate* and *cross-framework reconstruct*; defined failure states |
| **S1 — local safe handoff** | Two independent local agent implementations via A2A, synthetic task, approval policy, verified artifact, audit timeline | Trust rejection before disclosure, no real credentials in fixtures, cancellation/revocation tests, repeatable integration test |
| **S2 — reliable relocation** | Worker A → checkpoint → Worker B within *one pinned runtime*, durable coordinator, fenced fake-effect gateway | Crash injection at every critical transition; stale worker cannot commit gated simulated side effects; ambiguous tool results remain unknown |
| **S3 — MobilityBench v0.1** | Public synthetic benchmark and 4-way baselines (keep, restart, delegate, relocate) | Raw anonymized per-attempt outputs, environment manifests, repeated trials, negative cases, reproducible reporting |
| **S4 — semantic portability** | Two framework/model adapters, compatibility/loss report, baseline against Agent Spec where appropriate | Cross-runtime reconstruction measured against same-runtime restart; no blanket portability claims |
| **S5 — optional edge/security** | Cross-host trust domain and intermittent network testbed, provenance verifier, UI | Identity/approval audit, privacy checks, clock/partition assumptions and edge feasibility clearly stated |

A **minimal compelling demo** is S1+S2, not a 134-device claim. Recommend one public video, one command-line reproducible experiment, and a report of successes **and failures** before expanding the device catalog.

## 9. Experimental discipline and metrics

Use [MobilityBench experimental protocol](mobilitybench-experiment-protocol.md) as the first test plan.

Every result must identify: dataset revision and digest; source/destination agent and runtime versions; model/provider/version and settings; checkpoint format; movement mode; compatibility losses; trust domain; fault schedule; number of repeated trials; grader; complete/failed/canceled/unknown; source and effect receipts; elapsed time; token/compute/net cost; policy and privacy violations.

**Important metrics:** task correctness, preserved constraints, safe continuation rate, duplicate synthetic commits, stale-owner rejections, leaked synthetic secret canaries, movement bytes, p50/p95 latency, cost per correct completion (see the proposed [economic evaluation methodology](economic-evaluation.md)), and independently verifiable evidence completeness.

**Baselines:** keep running on A; start over on B; ordinary A2A delegation; same-runtime checkpoint/restore; later, cross-framework reconstructed continuation. A successful move is not necessarily useful if it is slower, less accurate or harder to audit than the baseline.

**Do not claim:** production readiness, exactly-once arbitrary third-party actions, statistically proven generalization, complete agent identity inference from behavioral fingerprints, or safe real-world device control from synthetic tests.

## 10. Concrete adoption strategy

1. Publish a working **minimal reproducible example**, with a single command to run a safe transfer and then replay a failure.
2. Label every supported operation as **implemented**, **tested**, **experimental** or **proposed**, including the exact host/runtime combination.
3. Provide a documented **adapter and fault-case contribution template**, not a broad call for hundreds of unverified device integrations.
4. Make a small public **compatibility and failure matrix** that upstream A2A, LangGraph, Agent Spec and security communities can reproduce.
5. Write a research technical report with test artifacts, negative findings and clearly documented validity threats. Invite independent reimplementations rather than claiming a new ecosystem standard at launch.
6. Assess an owner-approved open-source license separately; the repository currently has no selected license, so external reuse rights should not be presumed.

**Research target:** a paper about *verifiable task continuity and authority under agent movement*, supported by a reference implementation and controlled benchmark.  
**Engineering target:** a library and harness that people can run today rather than a giant architecture document.  
**Industry target:** safe, auditable transfer of agent work between managed execution environments.

## 11. Evidence boundaries and primary sources

- **[R1] A2A v1.0 specification:** https://a2a-protocol.org/v1.0.0/specification/ — independent agent messaging, task lifecycle, artifact exchange, extensions, and authentication/authorization interfaces. Does not automatically serialize arbitrary private execution state.
- **[R2] MCP 2026-07-28 announcement/specification:** https://blog.modelcontextprotocol.io/posts/2026-07-28/ and https://modelcontextprotocol.io/specification/2026-07-28 — stateless core, updated SDKs and opt-in Tasks extension for tools, not entire agent migration.
- **[R3] Open Agent Specification (ACM CAIS, May 2026):** https://doi.org/10.1145/3786335.3813130 and https://github.com/oracle/agent-spec — declarative definitions, cross-framework comparisons; shared representation does not eliminate framework-specific runtime behavior.
- **[R4] LangGraph persistence:** https://docs.langchain.com/oss/python/langgraph/persistence — native checkpoint and stores.
- **[R5] Temporal workflow execution:** https://docs.temporal.io/workflow-execution — runtime-specific durable workflows/history.
- **[R6] NIST AI Agent Standards Initiative (February 2026):** https://www.nist.gov/news-events/news/2026/02/announcing-ai-agent-standards-initiative-interoperable-and-secure — interoperability, identity and security priorities.
- **[R7] OAuth 2.0 Token Exchange (RFC 8693):** https://www.rfc-editor.org/rfc/rfc8693 — a delegation/token exchange mechanism; scope and audience enforcement are implementation-specific.
- **[R8] SPIFFE/SPIRE concepts:** https://spiffe.io/docs/latest/spire-about/spire-concepts/ — attested workload identity building blocks.
- **[R9] OpenTelemetry GenAI conventions:** https://github.com/open-telemetry/semantic-conventions-genai — moved from opentelemetry.io (the old page is now only a "moved" notice); Development status with no tagged release, so pin a commit before implementing.
- **[R10] OWASP Top 10 for Agentic Applications 2026:** https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/ — agent security threat taxonomy.
- **[R11] Specification portability research (Aug 2026, preprint):** https://arxiv.org/abs/2608.21208 — controlled specification reuse across coding assistants; relevant motivation, **not** evidence of actual runtime checkpoint relocation.

**Verified at source level on 2026-10-15:** A2A/MCP descriptions, Agent Spec conference publication, NIST initiative, SPIFFE/SPIRE identity model and OWASP taxonomy. The evaluation architecture, effort allocation, hypotheses, data models, safety arguments and project ordering above are **recommendations requiring implementation and independent validation**. No experiment or market demand study was performed in preparing this document.
