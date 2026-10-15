# Most important open research questions in Agent Movement

**Research review:** 2026-10-15  
**Project status:** Research/design only. No movement, cloning, replication, or interoperability demonstration has been implemented in this repository.  
**Scope:** Movement of AI-agent *work* across executors, frameworks, model providers and trust domains; not movement of a robot in physical space.

## Executive answer

The central unsolved problem is not sending a message between agents. It is **preserving useful task continuity, exclusive execution authority, and safety across an execution boundary**.

This project's working definition of *movement* is a transfer of task ownership and, when supported, an explicitly portable application checkpoint to a different executor. A transfer of the same agent's opaque model internals, hidden chain-of-thought or live process memory is **not** assumed possible.

The three most fundamental questions are:

1. **What, exactly, is the portable unit?** A definition, the goal, selected memory, task state, pending side-effect intents, artifact references, a graph checkpoint, or a combination?
2. **What level of semantic continuity is attainable?** Can a different runtime or LLM continue the same work with acceptable loss, and how can that be established by test rather than asserted?
3. **How can ownership and authority change safely?** How do we fence the old executor, prevent unauthorized privilege inheritance and reconcile uncertain external actions when a crash or network partition occurs?

These questions are related but distinct. A2A and MCP provide interoperability *building blocks*; they do not constitute a general cross-framework checkpoint or an exactly-once side-effect contract [S1, S2]. LangGraph and Temporal support durability within their execution models, but that alone is not proof of portable execution semantics between unrelated runtimes [S3, S4].

## Ranked questions: P0 = answer before claiming real movement

| ID | Priority | Open question | Why it is hard | Falsifiable first experiment |
| --- | --- | --- | --- | --- |
| AM-01 | **P0** | **What exactly moves?** Define separate portable contracts for an agent definition, a delegated task, a memory snapshot and a resumable checkpoint. | Different concepts have different identity and restoration semantics. Transcript copying is not execution recovery. | Export the proposed envelope; restore it on an isolated worker; enumerate each field retained, removed and unrecoverable. |
| AM-02 | **P0** | **What counts as the *same* task or agent after movement?** | Agent template, logical task, run, instance and destination principal need separate IDs. Continuity is not identity impersonation. | Trace the same logical task through two physical executors; verify lineage, unique execution IDs and no ambiguous owner. |
| AM-03 | **P0** | **Can a task be resumed without two agents executing the same side effects?** | Crash windows, leases, delayed messages and split-brain behavior undermine naive handoffs. | Pause A, transfer lease to B, delay A's messages, restart A and prove fenced A cannot trigger the simulated effect. |
| AM-04 | **P0** | **What are the limits of replay-safe external actions?** | After a timeout, a remote action may have happened even if there was no acknowledgement. Idempotency requires target-system cooperation. | Inject a crash before/after a fake purchase commits; require an explicit *unknown/reconcile* state rather than automatic blind retry. |
| AM-05 | **P0** | **How is execution authority attenuated, re-issued and revoked?** | User approval of A must not turn into B inheriting A's credentials or unrestricted tool rights. | Destination receives only a narrow expiring grant; test wrong audience, elevated scope, revoked grant and offline queued action. |
| AM-06 | **P0** | **Which context and memory may legally and safely cross boundaries?** | Instructions, private content, licensing, user consent, artifacts and third-party tool output have different disclosure and retention rules. | Inject secret canaries, hostile retrieved text and disallowed classifications; assert no unauthorized field reaches destination or logs. |
| AM-07 | **P0** | **Can a checkpoint migrate across frameworks, and what is lost?** | LangGraph checkpoints, Temporal histories, framework memory and scheduler states are not interchangeable. | Compare same-runtime restart against two pinned cross-framework adapters; publish a field-level compatibility/loss report and hard refusal for unsafe resumes. |
| AM-08 | **P0** | **Can a model change preserve the intent and quality of unfinished work?** | A new model may reinterpret the same instructions, plans and evidence differently even when serialization succeeds. | Run the same approved snapshot with same-model and different-model continuations; compare correctness, constraint violations and drift across repeated trials. |
| AM-09 | **P0** | **How does a sender authenticate a destination's real capabilities and trustworthiness?** | Agent discovery metadata may be spoofed; advertised capabilities are not evidence of actual security or policy compliance. | Fake Agent Card, hostile endpoint, swapped tool definition and unsupported capability test; default deny before disclosure. |
| AM-10 | **P0** | **What guarantees are actually offered by cancellation and revocation?** | Cancellation races against external actions; stopping future work does not undo already completed effects. | Cancel before dispatch, while queued, during tool call and after remote commit; specify observed states and non-rollback warnings. |

### Important P1 questions: evidence, usefulness and adoption

| ID | Priority | Open question | Why it matters | Falsifiable first experiment |
| --- | --- | --- | --- | --- |
| AM-11 | P1 | **How should semantic compatibility be negotiated?** | Schema and version match do not imply the destination understands policies, output quality, available tools or memory semantics. | Define required/optional capabilities, tool preconditions and loss reporting; force downgrade and reject unsupported critical constraints. |
| AM-12 | P1 | **Can copying, cloning, replication and multiplication share a safe common model?** | Forks legitimately diverge; replicas may race; child agents require bounded scope and budget. None is automatically a move. | Create distinct IDs for clone/fork/fan-out; test lineage, stale replica fencing, divergent memory, budget ceilings and cancellation. |
| AM-13 | P1 | **Who controls approval, deletion, retention and provenance after transfer?** | Multiple administrative domains may retain memory, traces or copied artifacts even after origin revocation. | Verify retention TTL, deletion propagation report, lineage, consent evidence and redacted cross-domain audit log. |
| AM-14 | P1 | **How much does movement *actually* improve outcomes?** | Migration can increase latency, token use, attack surface and failure rates compared with re-execution or delegation. | Compare four baselines: restart, ordinary A2A delegation, same-runtime checkpoint relocation, cross-runtime reconstruction. |
| AM-15 | P1 | **How should movement be benchmarked fairly?** | LLM output is stochastic; benchmarks can reward merely copying a transcript or hiding failed cases. | Pre-register tasks, failure points, models, seeds/replicates, evaluation rubrics, cost and raw traces; publish negative cases. |
| AM-16 | P1 | **Where should interoperability be standardized instead of duplicated?** | A2A already defines communications; MCP handles tool interfaces; new packaging must avoid pretending to replace them. | Prototype a minimal versioned task/checkpoint envelope as a documented application profile or optional extension, and run a second implementation. |

### Longer-term P2 questions

- **Offline and cross-cloud reconciliation:** What happens after prolonged partitions or when origin and destination cannot reach a central authority? Choose an explicit availability/consistency tradeoff.
- **Active/active replication and memory consistency:** Are agent memories shared, partitioned or merged, and who arbitrates concurrent updates? There may be no universal semantic merge.
- **Provenance of model-dependent decisions:** Can the system show what evidence, instructions, model version and tool versions informed a decision while respecting privacy and not exporting private model reasoning?
- **Economic scheduling:** Under which workload and security assumptions is moving preferable to spawning, re-running, or delegating? Optimize for completion, cost, latency, quality and risk—not agent count.
- **Registry/marketplace governance:** Can discovery be made safe enough for untrusted third-party agents, including supply-chain integrity, reputation gaming and takedown?
- **Formal guarantees:** Which properties can be proven under a clearly stated fault model, and which require human reconciliation because external systems cannot participate in the protocol?

## Evidence: what has partial solutions already?

| Existing research or standard | Supported observation | Important open gap |
| --- | --- | --- |
| **A2A v1.0** [S1] | Agents can discover endpoints, exchange messages/tasks/artifacts and request cancellation. The spec says Send Message *may* be idempotent and cancellation has defined task semantics. | It does not define a portable checkpoint for arbitrary running agent internals or make arbitrary external actions exactly once. |
| **MCP 2026-07-28** [S2] | A stateless request-oriented tool/context protocol; long-running Tasks are an extension; authorization is treated separately. | Stateless MCP transport does not mean the *agent application* or its workflow state is stateless or migratable. |
| **LangGraph persistence** [S3] | Checkpointers persist thread/graph state; stores persist application-defined memory across threads. | Persisting native state within one execution model is not cross-framework checkpoint compatibility. |
| **Temporal workflows** [S4] | Durable execution relies on persisted event history and replay of workflow code under replay constraints. | Foreign workflow implementations and external side effects still need adapter and idempotency semantics. |
| **Open Agent Specification / Agent Spec** [S5, S6] | Research provides a declarative, framework-agnostic representation of agent definitions/workflows and cross-framework evaluation. | *Definition portability* is a different claim from restoration of arbitrary in-flight execution or private model state. Evaluate reuse before inventing another definition language. |
| **Cross-agent specification transfer study (2026)** [S7] | A controlled software-migration study observed large agent-dependent differences when one coding assistant consumed another's specifications. | Results are domain-specific; they motivate tests of semantic portability, not a universal quantified failure rate. |
| **Durable-execution retry guidance** [S8] | At-most-once-per-retry and at-least-once-per-retry have different failure behavior; neither is blanket exactly-once execution. | Portable handoff needs operation IDs, target idempotency where available, and explicit reconciliation of ambiguous outcomes. |

**Interpretation, not a verified universal theorem:** The hardest missing piece is likely a verifiable *continuation contract*: portable allowed state + versioned capabilities + authority transfer + external effect ledger + measurable continuity. It may be practical to standardize safe *handoff* without standardizing live *migration*.

## Three proposed experiments, in research order

### E1 — Minimum safe handoff (tests AM-01, 02, 05, 06, 09, 10)

- Implement two *local* test agents with different implementation boundaries, authenticated A2A exchange, a public/synthetic task and a structured result.
- Use a versioned task envelope: task ID, origin execution ID, destination ID, intent and constraints, allowed artifact references, policy/approval reference, idempotency key and correlation ID.
- Negative tests: unsupported schema, forged endpoint/Agent Card, overbroad permission, unapproved data, prompt injection and revoked grant.
- **Pass condition:** correct artifact and end-to-end audit; zero transmitted secret canaries, zero unauthorized synthetic tool calls, and explicit denial with no input disclosure before trust verification.
- **Do not claim:** checkpoint migration. E1 proves delegated interoperability only.

### E2 — Same-runtime durable relocation (tests AM-02, 03, 04, 07)

- Pick a single checkpoint-capable framework and persistent store; move one logical task from Worker A to Worker B at a defined safe boundary.
- Introduce an epoch/fencing token, a durable side-effect intent/ack record, stable operation IDs and a simulated payment/action tool with idempotency support.
- Crash A, B or the coordinator at *every* transition; delay messages, inject duplicate delivery and partition connectivity.
- **Pass condition:** one active authorized executor per task epoch, no duplicated simulated committed effects in the test, correct fail-closed outcomes for ambiguous actions, and a verified post-restart state.
- **Do not claim:** exactly-once execution for arbitrary third-party tools.

### E3 — Cross-framework and cross-model continuation (tests AM-01, 07, 08, 11, 14, 15)

- Choose two pinned frameworks/models. Export only an explicitly portable *application-level* state representation, not undocumented runtime internals.
- Compare (A) from-scratch re-execution, (B) transcript/context replay, (C) A2A task delegation, (D) checkpoint-based same-runtime continuation, and (E) cross-framework reconstructed continuation.
- Use several task classes: document analysis, software change under test constraints, a multi-step tool workflow, and a side-effect-free long task. Repeat runs to quantify model variance.
- Publish per-task correctness, preserved constraints, resumption point, lost fields, duplicate effects, secret leakage, latency p50/p95, payload bytes and total cost.
- **Pass condition:** claims are scoped to measured workload and pinned versions; unsafe/incompatible migrations are *rejected*, not labeled successful.

### Suggested evaluation record (each attempt)

- Run IDs, operation and lineage; source/destination framework and model versions; exact source snapshot hash.
- Task class, intent constraints, input classification, approval scope and required capabilities.
- Movement mode, compatibility decision, accepted losses and outcome state (*complete*, *failed*, *canceled*, *unknown/reconcile*).
- Quality score with evaluator/rubric, constraint preservation, retries/duplicate tool intents/effects, privacy/policy violations, elapsed time and cost.
- Reproducible environment and fault-injection seed; sanitized trace and artifact digests.

There is **no measured performance result from this repository** yet. The pass conditions above are proposed targets for synthetic experiments, not actual achievements.

## Research decisions to take next

1. **Adopt a narrow initial claim:** safe task handoff first, same-runtime checkpoint relocation second, cross-framework reconstruction third; explicitly exclude opaque live-process/model-state migration.
2. **Specify identifiers and invariants first:** distinguish agent definition, logical task, run, runtime instance, operation, snapshot and lineage. Define what a transfer commits, when old work is fenced, and how an ambiguous outcome is represented.
3. **Reuse existing standards:** treat A2A as the delegation interface, MCP as the tool interface, LangGraph/Temporal as potential durability substrates and Agent Spec as related prior work on declarative portability.
4. **Require conformance and fault injection before publicity:** make the benchmark and denial tests part of the deliverable, not post hoc assertions.
5. **Publish negative results:** migration is scientifically useful even when the evidence shows explicit limits, lost state or a case where restarting is safer.

## Primary and research sources

- **[S1]** [A2A v1.0 specification](https://a2a-protocol.org/v1.0.0/specification/) — task/message/artifact interface, idempotency and error semantics.
- **[S2]** [MCP 2026-07-28 specification announcement](https://blog.modelcontextprotocol.io/posts/2026-07-28/) and [specification](https://modelcontextprotocol.io/specification/2026-07-28) — stateless protocol core, Tasks extension and authorization.
- **[S3]** [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence) — native checkpointers/stores and their scopes.
- **[S4]** [Temporal workflow execution](https://docs.temporal.io/workflow-execution) — event history, replay, state continuity.
- **[S5]** [Open Agent Specification Technical Report (2025)](https://arxiv.org/abs/2510.04173) — declarative agent-definition interoperability.
- **[S6]** [Open Agent Specification: Enabling Cross-Framework Comparison of AI Agents (CAIS 2026)](https://doi.org/10.1145/3786335.3813130) — cross-framework evaluation using a shared representation.
- **[S7]** [Specification Portability Across LLM Development Agents (2026)](https://arxiv.org/abs/2608.21208) — software-migration study of cross-agent interpretation, not runtime snapshot migration.
- **[S8]** [AWS Durable Execution SDK: Idempotency and retries](https://docs.aws.amazon.com/durable-execution/patterns/best-practices/idempotency/) — replay and external side-effect limitations.
- Related project files: [concept taxonomy](agent-movement-vs-copy-replication-multiplication.md), [proposed lifecycle](how-it-works.md), [threat model](security-and-trust.md), [staged roadmap](roadmap.md), [source log](sources.md).

---

**Evidence boundary:** This is a ranked research program, not a systematic literature review, an implemented protocol, or a conformance/security certificate. All experiments and acceptance criteria are proposals pending implementation and independent replication.
