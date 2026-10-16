# Agent Movement 2031: frontier research agenda

**Research snapshot:** 2026-10-15. **Horizon:** 2026-2031. **Status:** hypotheses and experiment proposals; nothing in this document is an implemented feature, validated result, ratified standard, or proof of novelty. **Scope:** authorized transfer, reconstruction, cloning and delegation of software-agent work across executors, devices, frameworks, model providers and administrative domains. Physical movement refers only to agents controlling authorized devices, never unapproved device access.

> Central thesis: communication between agents is becoming commoditized. The unusually valuable scientific question is whether intent, authority, memory integrity and causal accountability can remain *measurably continuous* through movement, forking, interruptions and long delegation chains.

This report extends, rather than duplicates, [the existing open questions](open-questions.md), [human-impact research questions](top-20-human-impact-questions-for-agentic-ai.md), [forensics research](agent-forensics-and-fingerprints.md), and [roadmap](roadmap.md). Questions are FM-01…FM-20 and flagship studies FS-1…FS-4; the [question ID crosswalk](question-id-crosswalk.md) lists which FM questions restate existing AM- or SQ- questions and which ID to cite.

## 1. What is already studied (the novelty reality check)

Do not pitch generic agent passports, portable agent definitions, delegation, signed events, checkpointing or memory-poisoning detection as untouched inventions:

| Existing work | What is already addressed | What it does **not** establish |
| --- | --- | --- |
| A2A v1 and MCP | Peer task exchange and tool interfaces, respectively | Portable, lossless execution continuation or proof that intent survived |
| Open Agent Specification / Agent Spec (2026) | Declarative representations and cross-framework comparison | Universal in-flight checkpoint transfer |
| ACRFence (2026) | Semantic rollback attacks (action replay, authority resurrection) and a mitigation that records irreversible tool effects and enforces replay-or-fork on restore | Semantic side-effect correctness across arbitrary tools/models/domains |
| Beyond Memory / Continuity Kernel (August 2026 preprint) | Transactional lineage, branch-head authority, writer handoff, and bounded model exploration | That a continued agent still pursues the *human's intended objective* |
| Authorization Revocation for Long-Running AI Agents (September 2026 preprint) | Root-scoped quiescence with explicit assumptions and manifested sinks | Quiescence across unknowable/uncooperative recipients or all copied data |
| Attesting Outputs and Delegation Ancestry (August 2026 preprint) | Signed released outputs and co-signed authorized edges | Truth of outputs, completeness of observations, or semantic compliance |
| Agent Passport System (September 2026 Internet-Draft) and AI-agent Internet architecture Internet-Draft (August 2026) | Proposed lifecycle/authority records and cross-protocol architecture | Deployed interoperability or standards-track ratification; individual Internet-Drafts are **not** Internet Standards |
| AgentAsk and Problem Drift (ACL 2026) | Handoff errors and drift in collaboration/debate settings | A mobility-specific, heterogeneous, rights-aware benchmark over many hops |
| MemMorph and Self-Propagating Misalignment (2026 preprints) | Memory-mediated influence and self-propagated objectives | Propagation rates and interventions across mixed-model **fork/move/merge** graphs |
| Agent Contracts (2026 preprint) and emergent multi-agent risk studies | Budget constraints and collective failures | Practical stop conditions across dynamically discovered workers and uncertain external effects |
| ITU-T Y.4618 (June 2026) | Device-edge-cloud AIoT requirements | Agent-level semantic migration and deadline safety for real-world actuation |

**Originality rule:** An unexplored *combination, failure boundary, metric or falsifiable comparison* may be a good contribution; it is not evidence that no paper has ever studied the idea. Each project should conduct an updated systematic prior-art and patent check before publishing a novelty claim.

## 2. Twenty frontier questions worth testing

The rankings are the author's **subjective strategic judgment**, not measured scores. "Under-tested angle" means a proposed test not established by the cited adjacent work; it does not mean absent from all literature.

| ID | Priority | Question and under-tested angle | Proposed falsifiable result |
| --- | --- | --- | --- |
| **FM-01** | **P0** | **Proof-carrying continuation:** can a destination verify the original task invariants, retained evidence and current authority before resuming, rather than merely deserialize a snapshot? | Reject intentionally altered critical constraints before *any* simulated external effect; measure false refusals and missing evidence |
| **FM-02** | **P0** | **Multi-hop intent drift:** how do errors and forgotten constraints compound across 1-8 hops, especially across model/framework/organization boundaries? | Compare errors versus hop count, with and without original-intent anchors, clarification and evidence; no assumption of monotonic drift |
| **FM-03** | **P0** | **Minimum sufficient move packet:** how little information can move while still preserving correctness, privacy and safe abstention? | Pareto curve: payload bytes versus task quality, leak rate and unsupported claims on frozen tasks |
| **FM-04** | P1 | **Move, delegate, restart, or stay?** Can a risk-aware decision engine choose a less powerful but safer option? | Blind comparison of four options under identical tasks, hardware and faults; record regret when mobility loses |
| **FM-05** | P1 | **Conflicting twins:** can independently changed agent branches be merged without laundering false beliefs, revived authority or duplicated actions? | Three-way synthetic merge with source-level provenance and explicit refusal of irreconcilable side effects |
| **FM-06** | **P0** | **Revocation horizon:** after a human withdraws permission, when can a bounded delegated workflow establish no *new authorized* effects under that grant? | Measure quiescence time and coverage for registered sinks; unknown/unreachable sinks must remain unknown, not "safe" |
| **FM-07** | P1 | **Derived-memory forgetting:** how can revocation/erasure propagate into embeddings, summaries, replicas and fork descendants without destroying minimal incident evidence? | Synthetic deletion requests, descendant inventory, exact limitations and post-erasure recall tests |
| **FM-08** | **P0** | **Descendant inventory and non-proliferation:** can an organization detect unapproved forks, delegated children and jobs queued outside the original executor? | Reconcile declared versus independently observed children under a bounded instrumented testbed, report detection gaps |
| **FM-09** | P1 | **Authority conservation across graphs:** do combinations of individually legitimate grants accidentally exceed the user's intended total authorization? | Construct DAGs with intersecting and disjoint grants; enforce root-level action limits and demonstrate rejected privilege amplification |
| **FM-10** | **P0** | **Zero disclosure before trust:** does discovery reveal secrets or sensitive context before identity, destination policy and recipient suitability are checked? | Capture traffic with secret canaries; require zero preauthorization payload disclosures in every negative case |
| **FM-11** | P2 | **Attestation versus behavior:** how much trust is justified by a valid runtime attestation if the agent has misleading state or unsafe objectives? | Separate platform integrity, model-version evidence and semantic correctness in a factorial test |
| **FM-12** | P1 | **Accountability without surveillance:** can a recipient prove that a specific effect was authorized while minimizing exposure of human content and identity? | Compare redacted receipts/commitments with full traces on verification accuracy and re-identification risk |
| **FM-13** | P1 | **Semantic rollback beyond a single tool:** when model B reconstructs an intent differently after migration, can already committed effects be recognized? | Simulate cross-model retry with changed nonessential fields; classify safe replay, denial and unknown/reconcile |
| **FM-14** | P1 | **Offline two-world problem:** how should authority and checkpoints behave when edge agents work offline and reconnect after another worker takes over? | Partition/rejoin test with fenced synthetic actions; measure progress sacrificed for safety |
| **FM-15** | P1 | **Embodied/hardware deadline continuity:** can cloud-edge-device relocation preserve an externally specified safety deadline and human emergency stop? | Digital-twin experiment only: deadline misses, bounded unsafe actuation attempts, and stop response |
| **FM-16** | P1 | **Forensics under missing evidence:** can an investigator distinguish verifiable movement, plausible lineage and unknowable gaps without falsely asserting completeness? | Independent verifier confronted with missing, contradicted, delayed and forged synthetic event histories |
| **FM-17** | **P0** | **Memory epidemiology:** what is the propagation rate of incorrect or unwanted self-authored beliefs across agent copies and model changes? | Benign synthetic false-fact seeds, 1-5-generation fork graph, outcome and quarantine tests without real harmful payloads |
| **FM-18** | P1 | **Collective governance failure:** can every member pass local checks while the collective causes an unauthorized or unfair system-level outcome? | Sandbox resource-allocation and negotiation games with global policy invariant; quantify violations as network size grows |
| **FM-19** | **P0** | **Fan-out conservation:** can every spawn/delegation path obey a finite combined compute, money, time and action budget—even after retries? | Dynamically generated sandbox DAGs; assert no accepted operation exceeds the root's remaining budget |
| **FM-20** | P2 | **Movement and the real world:** under which carbon, energy, privacy, latency and fairness constraints is cloud/edge/device mobility *actually* beneficial? | Public synthetic workload traces and Pareto trade-off, including results in which staying local wins |

### Five frontier themes

**A. Semantics is the missing layer.** Schema compatibility says a field can be parsed; semantic continuity asks whether constraints, evidence strength, uncertainty and decision boundaries are preserved. FM-01/02/03 are best evaluated together. A valid receipt must not be described as proof of correctness.

**B. Consent has a topology, not just a timestamp.** The human's authorization may flow through queued work, children and remote sinks. FM-06/08/09/19 ask for bounded and explicitly conditioned claims, not a magical global kill switch. Revoking a grant does not reverse previously completed work.

**C. Memory is a propagation medium.** A memory entry can outlive the original agent and be copied to a better model. FM-05/07/17 study provenance, false beliefs, self-authored goals and deletion across branches. Data erasure and legal compliance cannot be declared solely from removing one encryption key or one memory row.

**D. Evidence has an incompleteness problem.** Signed logs do not establish truth, completeness or lawful collection. FM-11/12/16 distinguish identity, observation, intent, acceptance and committed external effect; missing sources must be explicitly "unknown."

**E. Mobility meets physical and social constraints.** FM-14/15/18/20 address availability, human safety, emergent group behavior and real-world energy or resource costs; toy messaging demos cannot settle these questions.

## 3. Four concrete flagship studies

### Study FS-1 — MobilityBench multi-hop track: semantic conservation across hops

**Planned, not implemented.** Since [issue #44](https://github.com/MSKazemi/agent-movement/issues/44) this study is the multi-hop track of MobilityBench, not a separate benchmark; the design, and what [MobilityBench v0.1](mobilitybench-v0.1.md) can and cannot measure today, is in [Planned: multi-hop track](mobilitybench-v0.1.md#planned-multi-hop-track). v0.1 moves each task exactly once, between two executors.

**Research question:** What measurable fraction of *explicit task invariants* survives heterogeneous transfers, and which safeguards improve survival without introducing needless transfers or unacceptable disclosure?

- Pre-register an initial 100-200 synthetic/public task cases (an engineering starting point, not a power calculation; size the final study from pilot variance) in categories: document synthesis with protected facts, constrained coding, multi-step simulated tools, and tasks whose correct response is **abstention**.
- Annotate explicit invariant IDs: hard constraints, factual evidence references, allowed/forbidden actions, open uncertainties, required approvals, already committed effects and budget.
- Compare: no move; ordinary A2A handoff; restart with context; same-runtime checkpoint; cross-model application-level reconstruction **only if actually implemented**. Vary 0, 1, 2, 4 and 8 handoffs and include lossy summaries, conflicting evidence and simulated receiver refusal.
- Evaluate with programmatic invariants where possible; blind human review for ambiguous semantic outcomes. Repeat stochastic cases; record denominators, confidence intervals and unsupported modes as unavailable.
- **Primary metric:** task-invariant survival rate per hop and end-to-end, not similarity of generated text.
- **Secondary:** correctness, unsafe/duplicate synthetic effects, false confidence, unknown detection, disclosure bytes, total runtime, compute and monetary cost.
- **Critical falsifier:** if a restart/single-agent baseline wins on cost-adjusted quality or the "proof" misses known synthetic invariant violations, mobility-first framing should be abandoned for those classes.

### Study FS-2 — AuthorityMap: authorization coverage and descendant closure

**Research question:** Can a user or auditor establish a bounded answer to "what still has permission to act on my behalf?" after delegated work has forked?

- Model separate principals, logical tasks, executors, grants, epochs, sinks, queues, callbacks and descendants; record where an actor is not observable.
- In an entirely synthetic environment, generate bounded delegation DAGs, revocations, delayed acknowledgements, retries, duplicate child registrations, worker crashes and network partitions.
- Require pre-disclosure peer authentication, independent tool-side enforcement, signed evidence at covered boundaries and explicit coverage manifests.
- **Measures:** discovered child recall/precision under a known fixture oracle, root authority exposure, forbidden post-revocation acceptances, quiescence latency, unaccounted queued operations and cost overhead.
- **Critical falsifier:** success in a coordinator-only test but failure under an independently instrumented tool/queue sink. Do not claim global inactivity for unobserved systems.

### Study FS-3 — MemoryGenome: synthetic belief propagation, fork/merge and erasure

**Research question:** How do *benign false beliefs* and stale constraints spread when context is copied between distinct models or independently updated agent branches?

- Use fictitious organizations, canary facts, synthetic policies and model outputs; do **not** use secret real data or operational attack payloads.
- Test origin->clone, clone->clone, copy->different-model, two-branch merge and post-revocation continuations.
- Compare provenance tags, trust-weighted retrieval, quarantining newly derived memories, human review and hard refusal on conflicting provenance.
- **Measures:** false-belief inheritance rate, generations-to-extinction, correction persistence, unsupported citation rate, derived-memory erasure recall and useful information lost to defense.
- **Critical falsifier:** a control that suppresses false facts by simply erasing all useful task memory is not a satisfactory success.

### Study FS-4 — EdgeMove Safety Lab: disconnection and deadline-aware authority

**Research question:** What changes when an agent's destination is a low-power device with intermittent connectivity and time-bounded physical obligations?

- Use a **simulation/digital twin** for a sensor/actuator workflow. Keep actual devices disconnected from real-world high-stakes actuators.
- Vary network partition, device battery, compute capacity, deadline, cloud dependency, policy update and local emergency stop.
- Compare stay-on-device, cloud offload, human escalation and authorized checkpoint relocation; separate movement of an inference request from movement of a long-lived agent task.
- **Measures:** deadline misses, safety-invariant violations, stop latency, energy estimate, recovery point, necessary human interventions and data leaving the device.
- **Critical falsifier:** a cloud route that improves task accuracy but exceeds the safety deadline is not a safe successful move.

## 4. A scientific vocabulary and useful new metrics

These are **proposed project metrics**, not adopted industry definitions.

| Metric | Operational definition | Why it matters |
| --- | --- | --- |
| Intent survival (IS) | Number of independently verified original hard invariants retained at final output / number eligible, with missing evidence recorded separately | Prevents "completed" from hiding changed goals |
| Hop drift curve | IS and task accuracy by actual transfer depth, with uncertainty and task complexity controls | Exposes compounding loss |
| Disclosure footprint | Classified payload bytes exposed to recipients at each trust boundary | Shows cost of carrying context |
| Authority exposure | Sum over authorized sinks and durations, stratified by effect class, within an explicitly inventoried graph | Models how much delegated power remains active |
| Revocation closure time | Elapsed time until **all registered covered sinks** certify enforcement of the new root epoch; missing sinks -> unknown | A more meaningful measure than cancellation acknowledged |
| Descendant coverage | Number of independently observed descendants matching declared graph / total known descendants in synthetic oracle | Detects shadow/forgotten children |
| Semantic infection rate | Fraction of descendant branches whose answers repeat a planted synthetic false belief | Evaluates memory contamination |
| Recoverable state fraction | Required public, exportable state fields demonstrably restored / annotated required fields | Does not pretend to inspect hidden model state |
| Forensic evidence grade | Structural, authenticated, independently replayed and durably included claims tracked separately | Protects against over-reading signed receipts |
| Mobility-adjusted utility | Task quality and safety versus a single-agent baseline after accounting for latency, leakage, energy, human review and cost | Establishes when *not* to migrate |

Report the denominator, fault model, model/version, environment, uncertainty, known blind spots, and what the instrument actually observes for every metric.

## 5. Five-year roadmap (scenarios, not forecasts)

| Period | Valuable research milestone | Evidence required |
| --- | --- | --- |
| Late 2026-2027 | Reproducible task handoffs, negative authentication tests and a frozen first release of the MobilityBench multi-hop track | Two independent workers, baseline report, denial-before-disclosure traces |
| 2027-2028 | Model-agnostic application-state continuation profile with measurable semantic loss | Two cross-model/runtime adapters, loss reports and refusal cases |
| 2028-2029 | Covered-domain authority map and revocation closure reports | Independent sink tests, bounded assurances and published unknown states |
| 2029-2030 | Fork/merge memory provenance and data-deletion experiments | Realistic synthetic branch DAGs, independent evaluation |
| 2030-2031 | Edge/cloud autonomy routing with human-controllable safety contracts | Digital-twin evidence and comparison against staying local |

### First 90 days: executable, not just visionary

| Weeks | Deliverable | Connection to existing backlog | Exit criterion |
| --- | --- | --- | --- |
| 1-2 | Locked terminology, hypotheses, threat model and benchmark manifest | Existing [AM-01..16](open-questions.md), [issue #10](https://github.com/MSKazemi/agent-movement/issues/10) | Public protocol and frozen fixtures; no results claimed |
| 3-4 | Real official-A2A synthetic handoff + pre-disclosure auth negative tests | [issue #7](https://github.com/MSKazemi/agent-movement/issues/7), [issue #8](https://github.com/MSKazemi/agent-movement/issues/8) | Different workers pass basic task and all secret-canary denials |
| 5-6 | Same-runtime durable relocation and fault-injection baseline | [issue #9](https://github.com/MSKazemi/agent-movement/issues/9) | Origin fenced, safe checkpoint resume, unknown effects reconciled explicitly |
| 7-9 | MobilityBench multi-hop track matrix and original-intent constraints | [issue #10](https://github.com/MSKazemi/agent-movement/issues/10) | Per-attempt evidence with baselines, denominator, incompatibility refusals |
| 10-12 | Signed lineage receipts and covered-sink authority/descendant pilot | [issue #11](https://github.com/MSKazemi/agent-movement/issues/11) | Independent verifier rejects tampering and reports missing evidence as unknown |

**Positioning** (one statement, used verbatim in the [README](../README.md), the [strategic agenda](strategic-target-and-scientific-agenda.md) and `CITATION.cff`):

<!-- positioning:start -->
Agent Movement is a research prototype: an open, evidence-first testbed built to make claims about safely moving AI-agent work between executors falsifiable. It currently pairs ranked research questions with synthetic, localhost-only Python prototypes and MobilityBench v0.1, a frozen, deterministic, LLM-free benchmark of 18 synthetic tasks that scores keeping, restarting and locally delegating work under injected faults and reports refusals and unavailable baselines instead of hiding them. It is not production software, a new agent protocol or a rival to A2A or MCP.
<!-- positioning:end -->

It is also not an engine for unapproved autonomous spreading (see §6).

## 6. Research ethics, operational limits and negative results

- All initial experiments must operate on local/isolated, opted-in, synthetic agents, fake identities and simulated side-effect gateways; no scanning third-party machines, hidden installs, autonomous propagation, or reuse of real user tokens.
- Approval before disclosure and before consequential simulated effects is an enforceable boundary, not a prompt instruction.
- Respect environment privacy and data minimization. Do not include raw private logs, credentials, private messages, or full reasoning traces in public fixtures.
- Revocation cannot retroactively undo a payment, disclosure or actuation; under a network partition, strong safety may require refusing or pausing work.
- A hash, signature or attestation establishes integrity and source-bound claims under key/trust assumptions, not semantic truth or complete independent observation.
- Report failures, unknown cases and instances where a deterministic workflow or no movement is better. A negative result can be an important research contribution.

## 7. Dated research sources and adjacent prior art

Links below support **adjacent work**, not originality or future outcomes.

1. [A2A v1.0 specification](https://a2a-protocol.org/v1.0.0/specification/) — agent task/message/artifact interoperability.
2. [MCP specification](https://modelcontextprotocol.io/specification/2026-07-28) — tool/context interoperability.
3. [Open Agent Specification: Enabling Cross-Framework Comparison of AI Agents (CAIS 2026)](https://doi.org/10.1145/3786335.3813130) — definition representation and evaluation.
4. [ACRFence: Preventing Semantic Rollback Attacks in Agent Checkpoint-Restore (March 2026)](https://arxiv.org/abs/2603.20625) — action replay and authority resurrection hazards on checkpoint restore.
5. [Beyond Memory: A Transactional Continuity Kernel for Long-Lived AI Agents (August 2026)](https://arxiv.org/abs/2608.11632) — authority-controlled state activation and writer handoff.
6. [Authorization Revocation for Long-Running AI Agents (September 2026)](https://arxiv.org/abs/2609.21284) — root-scoped quiescence under declared coverage and fault assumptions.
7. [Attesting Outputs and Delegation Ancestry in Multi-Agent AI Systems (August 2026)](https://arxiv.org/abs/2608.30387) — signed output and co-signed lineage evidence.
8. [Agent Passport System (individual Internet-Draft, draft-pidlisnyi-aps-04, September 2026)](https://datatracker.ietf.org/doc/draft-pidlisnyi-aps/) — proposed passport-style authority/evidence architecture; intended status Informational, no IETF stream or endorsement; NOT a ratified IETF standard.
9. [Architectural Requirements for Supporting AI Agents on the Internet (August 2026 Internet-Draft)](https://www.ietf.org/archive/id/draft-daniel-ai-agent-internet-architecture-00.html) — proposed network architectural requirements.
10. [AgentAsk: Multi-Agent Systems Need to Ask (ACL 2026)](https://aclanthology.org/2026.acl-long.1294/) — errors at agent-to-agent communication edges.
11. [Stay Focused: Problem Drift in Multi-Agent Debate (EACL Findings 2026)](https://aclanthology.org/2026.findings-eacl.268/) — drift in multi-agent debate; related but not a movement benchmark.
12. [Self-Propagating Misalignment in LLM Agents, and Why Auditing or Disabling Memory Is Not Enough (October 2026)](https://arxiv.org/abs/2610.04083) — self-authored memory/file propagation risk.
13. [MemMorph: Tool Hijacking in LLM Agents via Memory Poisoning (May 2026)](https://arxiv.org/abs/2605.26154) — memory integrity under adversarial insertion.
14. [Emergent Risks in Generative Multi-Agent Systems (March 2026; v1 titled "Emergent Social Intelligence Risks in Generative Multi-Agent Systems", v3 September 2026)](https://arxiv.org/abs/2603.27771) — collective risks in multi-agent settings.
15. [Agent Contracts: A Formal Framework for Resource-Bounded Autonomous AI Systems (January 2026)](https://arxiv.org/abs/2601.08815) — budget constraints and delegation conservation.
16. [ITU-T Y.4618 (June 2026): AIoT reference model and requirements](https://www.itu.int/epublications/publication/itu-t-y-4618-2026-06-artificial-intelligence-of-things-reference-model-and-requirements) — device/edge/cloud architecture.
17. [Authorization Architectures for Tool-Using AI Agents (September 2026)](https://arxiv.org/abs/2609.15906) — principal hierarchy, authorization enforcement and audit gaps.
18. [SAIHM: Sovereign AI Horizontal Memory (May 2026 Internet-Draft)](https://datatracker.ietf.org/doc/html/draft-saihm-memory-protocol-00) — proposed portable memory/erasure ideas, not a ratified standard.

**Re-review date:** Before any paper submission, standards proposal, novelty claim or real-world deployment; new literature can narrow or invalidate these hypotheses.
