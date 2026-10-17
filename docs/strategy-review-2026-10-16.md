# Strategic target reset: one research mission, measurable continuation

**Review date:** 2026-10-16  
**Status:** **Decision proposal**. This review is for maintainer discussion; it does not silently replace existing specs, change the runtime, confer security assurance, or assert original scientific novelty.  
**Repository snapshot:** main at [c58553a](https://github.com/MSKazemi/agent-movement/commit/c58553a1374c0cbceb8d28fdc834f9ed6929a00c); [open PRs](https://github.com/MSKazemi/agent-movement/pulls) and issue #50 checked on 2026-10-16.  
**Audit method:** Examined the current tree, README, roadmap, strategy/scientific agenda, open questions, architecture, canonical envelope and implemented core, evaluation plan, v0.2 results, and visible open PRs/issues. This is a strategic/document consistency audit, **not** a line-by-line verification of every document or a systematic external literature review.

**Post-review decision (2026-10-16):** The owner authorized the next phase of mission/roadmap consolidation. The resulting [project charter](project-charter.md) is the adopted current direction and [roadmap](roadmap.md) owns execution gates. This longer dated assessment remains a historical decision record; subsequent main-branch changes, including bounded Continuity Runtime and abstract state-space work, are covered by the charter and roadmap.\n\n## Executive decision

**Verdict:** The underlying research direction is coherent and the synthetic implementation is substantial, but the public-facing goal is too broad, the technical claims are scattered, and some entry documents preserve outdated snapshots. The next stage should consolidate rather than open more parallel topics.

**Proposed project thesis:**

> Agent Movement Lab studies when AI-agent **work** can cross an execution boundary while retaining authorized task intent, controlled side effects, and independently checkable continuity evidence. It pairs a narrowly scoped continuation reference implementation with adversarial, reproducible comparisons of **stay, restart, delegate and relocate**.

The primary problem is **verified continuation of work**, not movement of model weights, hidden reasoning, an agent's subjective identity, or a live OS process. Delegation is a valuable comparison and protocol adapter, but under the current glossary it is **not** strict movement of ownership.

**One-sentence README-friendly version:**

> Can an interrupted AI-agent task continue on another authorized executor **without silent state loss, unauthorized effects or untraceable ownership changes**—and when is moving better than staying or restarting?

**Recommended identity:** A research and conformance **lab**, not a production agent OS, a universal movement protocol, a device-propagation tool, or another generic multi-agent framework.

## A concrete north-star demonstration

An approved, synthetic, long-running coding/document workflow begins on Worker A. The workflow records an application-level safe checkpoint and an independently controlled simulated effect ledger. Worker A loses availability (or an operator requests relocation). A coordinator authenticates the destination, evaluates a scoped grant and compatibility evidence **before disclosure**, transfers an explicit versioned state package, fences A, and permits B to resume. A delayed or revived A tries to commit a stale effect; the controlled effect gateway refuses it. If any external action's outcome is unknowable, the task stops at **unknown / reconcile** until an authorized decision is recorded. A third-party verifier reads sanitized receipts and distinguishes verified facts from claims and missing evidence.

The accompanying evaluation runs the same test intent through four choices: **stay on A, restart on B, delegate bounded work to B, and relocate the compatible checkpoint to B**. It reports correctness, refusals, policy violations, duplicate effects, ambiguity, transfer bytes, total and human-review cost, and limitations. A move is allowed to lose: the research must show **when not to move**.

This is an **intended demonstrator**. Pieces exist on separate synthetic/local paths, not as a single production-secure end-to-end system.

## What exists and what the evidence really establishes

| Area | Observed in main (2026-10-16) | What it does NOT establish |
| --- | --- | --- |
| Terminology, research agendas, standards, source corpora | Extensive documents and curated literature/news metadata; distinctions between delegation, relocation, copying, forking and replication | Scientific originality, exhaustive coverage or operational portability |
| Local handoff, HTTP, peer path, A2A adapter | Python package, two-process loopback demonstrations, signed-grant/peer experiments, optional official A2A SDK adapter | Authenticated secure operation across every path; production cross-host interoperability |
| Checkpoint relocation | LangGraph-compatible experimental resumption, two-store bundle copy and crash/reconciliation matrices | General migration across agent runtimes/models; real external effects |
| Governance/evidence | Revocation, synthetic effects, receipts, trust-anchor verification, retention controls on covered paths | Mandatory mediation of every possible network/tool route; complete detection of unobserved behavior |
| MobilityBench v0.1/v0.2 | Frozen, deterministic, LLM-free suites with explicit unavailable modes, seeded faults and reproducible outputs | Behavioral results for stochastic LLM agents or a statistical claim of improved real-world performance |

The [v0.2 result report](mobilitybench-v0.2-results.md) gives, for one scripted configuration and repeat-0 denominators, **90/90** correct attempts for checkpoint relocation, **67/90** for keep-on-origin, **52/90** for stable-ID restart and **21/90** for naive restart. These are **deterministic fixture/harness outcomes**; do not generalize them as evidence that relocation outperforms alternatives for real AI agents. A2A delegation is also deliberately limited in the current task semantics.

The [evaluation plan](evaluation-plan.md) correctly recognizes that its deterministic interpreter receives an oracle plan and that fair non-agent and stochastic-agent arms are **not yet** scored. That gap should become the central next scientific milestone.

## Why clarity is presently weaker than the implementation

1. **Several goals compete for equal attention.** The README reading index covers device classes, agent multiplication, protocol networks, digital forensics, governance, human-life questions, frontier autonomy and a benchmark. All may remain research tracks, but should not imply equal build commitments.
2. **Entry points are inconsistent in time.** [Open questions](open-questions.md) still says no movement or interoperability demonstration is implemented. [The movement/copy audit](agent-movement-vs-copy-replication-multiplication.md) correctly reports a historical snapshot with no source code on 2026-10-15, but readers may mistake it for the current implementation status. [The roadmap](roadmap.md) still says Phase 0 is documentation-only and leaves Phase 1 delegation vs relocation undecided, although both now have synthetic prototypes. [How it works](how-it-works.md) retains a heading describing its whole flow as not implemented, although selected pieces are implemented separately.
3. **Canonical envelope and runtime wire shape diverge by design, but are easy to confuse.** [The proposal](how-it-works.md) and [JSON Schema](../schemas/handoff-envelope.schema.json) define **0.2.0-draft**, while the current core validates **0.1.0-draft**. The proposal documents its divergences; a strategy/README must not imply the 0.2 proposal is the runtime contract.
4. **A missing enforcement composition gate is more important than another conceptual taxonomy.** [PR #16](https://github.com/MSKazemi/agent-movement/pull/16) drafts a *decision-only* movement-policy helper. [Issue #50](https://github.com/MSKazemi/agent-movement/issues/50) correctly demands policy checks at sender, receiver and simulated effect commit, with independently controlled mediation; no blanket bypass-proof guarantee follows from prompt instructions or self-attested facts.
5. **Existing open proposals need refresh, not duplication.** [PR #17](https://github.com/MSKazemi/agent-movement/pull/17) proposes useful architecture boundaries but describes an older repository with no src package. [PR #83](https://github.com/MSKazemi/agent-movement/pull/83) adds neglected consent/obligation/compromise/human-control studies. Integrate them as subordinate tracks after reconciling their snapshots, instead of creating a competing fourth grand agenda.
6. **Benchmark naming is not unique in the broader research landscape.** The public AMAP-ML/MobilityBench (separate external route-planning benchmark; see PR #88 source discussion) is a separate KDD 2026 route-planning-agent benchmark. The shared name creates discoverability and citation confusion, **not by itself a demonstrated legal conflict**. Consider a distinct identifier such as *Agent Continuity Bench* as a proposal; check names and downstream references before any rename.

## Boundaries: the first release of the research program

| Now: core claim | Next: scientifically necessary | Later: only after evidence | Explicitly not a goal |
| --- | --- | --- | --- |
| Task/execution identity; safe same-runtime relocation; compatibility refusal; simulated policy-gated effects; independently verifiable receipts | Controlled model-backed experiments; held-out tasks; fair baselines; two-worker instrumentation; external verifier; scope of enforcement made explicit | Cross-framework reconstruction with **loss reports**; multi-hop intent/obligation continuity; carefully staged edge/offline simulation; cross-organization trust study | Universal lossless live migration; copied hidden chain-of-thought or reusable credentials; agents silently propagating to arbitrary devices; autonomous replication by default; an A2A/MCP replacement |

**First target audience:** agent framework engineers, distributed-systems researchers, and AI-security/reliability researchers who need testable failure/compatibility guarantees. Operator users and device/cloud portability products are **secondary** until the lab has data and threat-bounded demonstrations.

**First use case:** two deliberately isolated workers, synthetic/public inputs, controlled effect gateway, bounded delegated authority, failure/restart; no real purchases, credentials, private data, destructive tools or deployment to third-party devices.

## Three tightly connected workstreams

### P1 — Continuation semantics and contract (core of the project)

Specify the smallest *safe* portable unit: logical task ID, execution ID, operation type, critical intent/constraints, artifact references and digests, compatible checkpoint profile, authority/obligations, fencing epoch and known semantic loss. The imported contract must refuse incompatible or missing critical fields. Reconcile 0.1 runtime versus 0.2 proposal via an explicit migration/version plan; **do not** rename a draft and assume the old runtime implements it.

Research questions: **What survives? What cannot survive? When must continuation be refused?** Test by ablation, checkpoint corruption and compatibility mismatch, with exact loss/refusal reports.

### P2 — Bounded enforceability and accountability (engineering gate)

Integrate policy into *every enabled controlled* entry, transfer and side-effect boundary; distinguish authenticated/verifier-produced facts from self-declared labels. Attenuate rather than forward authority. Revocation, stale epochs, replay and ambiguous effects must be tested at commit time with denial or explicit reconciliation.

Research question: **Under which stated trust, mediation and fault assumptions can a forbidden transfer or effect be blocked?** The assertion is conditional; a compromised host, uncooperative tools, arbitrary egress or already-disclosed data remain outside a bounded proof.

[Issue #50](https://github.com/MSKazemi/agent-movement/issues/50) and the refreshed policy work in [PR #16](https://github.com/MSKazemi/agent-movement/pull/16) are the first implementation priority.

### P3 — Reproducible evidence and decisions (scientific output)

Make the benchmark a first-class product: deterministic unit/fault tests *plus* a separate **model-backed, held-out evaluation track** with pinned executors, repeat trials, fair stay/restart/delegate/relocate alternatives, pre-declared hypotheses, non-agent baseline, human interventions, security failures and quality-adjusted cost. Retain negative results.

Research questions: **When is transfer better than alternatives, and when does it damage quality, privacy, cost or authority?** Publication claims must not substitute test counts for independent real-agent evidence.

Signed receipts and independent timeline verification are part of this workstream, but a signed trace does not prove that everything consequential was observed.

## Proposed 90-day program (relative weeks, not a release promise)

| Window | Deliverable | Stop/go acceptance gate |
| --- | --- | --- |
| Weeks 1–2: define and reconcile | Adopt or edit a one-page charter; define in/out-of-scope operations; mark outdated historical docs as snapshots; choose canonical roadmap and API vocabulary; resolve version divergence **plan**, not necessarily migration | One current source of truth in README + roadmap; no contradictory headline status claims; a version/compatibility decision is recorded |
| Weeks 3–5: bounded policy implementation | Rebase/reconcile PR #16 against main; implement issue #50 at all **enabled** controlled boundaries or disable unmediated adapters in a secure experimental profile; preserve independent negative tests and trust boundary evidence | Zero unauthorized **simulated commits** or prohibited pre-disclosure payloads across the enumerated controlled attack matrix; explicitly list bypasses and out-of-scope paths; red/green gate-removal test |
| Weeks 6–9: benchmark with fair baselines | New suite version, held-out task families, non-agent and one-agent baselines, optional model-backed execution; repetition and cost/human-intervention reporting; preserve v0.1/v0.2 frozen outputs | Every mode has a comparable denominator and explicit availability; negative and null results preserved; manifests and evaluator rubric independently runnable |
| Weeks 10–12: consolidate evidence | Reproduce the north-star two-worker scenario under faults; independent receipt verifier; compatibility/refusal/loss report; publish an honest technical report and follow-on decision memo | Another researcher can run a pinned demo and reconstruct the specific bounded claims; unsupported claims are explicitly marked unknown |

**Do not expand scope mid-cycle** into general cloning, swarm growth, personal-device installation or a product marketplace. PR #83's gap studies are valuable, but should be queued behind their prerequisites or used as negative benchmark scenarios rather than all implemented in parallel.

## Required measurements and falsification

| Question | Measurement | Interpretation rule |
| --- | --- | --- |
| Does the task survive? | Correct completed tasks / all attempts, by mode and fault; retained critical constraints; false accept/false deny | Report incomplete, refused and unknown separately; do not count safe refusal as successful completion |
| Do controlled safety boundaries work? | Accepted unauthorized transfers, pre-disclosure sensitive bytes, out-of-policy simulated effects and stale-authority commits | Target zero **within enumerated mediated interfaces**; each enabled bypass invalidates that narrow claim |
| Is ownership clear? | Conflicting active effect-writer epochs, recoveries requiring reconciliation, stale-worker refusals | No generic exactly-once or global split-brain guarantee for uncooperative systems |
| Can evidence be checked? | Receipt verification/ambiguity rate, missing-anchor and forged-evidence detection, independently reconstructed event ordering | Distinguish cryptographic integrity, asserted identity, observed effect and unobserved gaps |
| Is relocation actually useful? | Quality-adjusted cost, wall time, transfer bytes, human interventions, opportunity cost and fallback/regret relative to stay/restart/delegate | If no advantage under fair conditions, publish that; do not optimize benchmark assumptions for relocation |
| Is semantic portability real? | Constraint retention and behavior discrepancy on held-out same-runtime vs changed-runtime/model tasks; compatibility/loss reports | Treat semantic equivalence as an empirical hypothesis; no claim from serialization alone |
| Can others reproduce it? | Pinned dependencies, deterministic fixtures, independent reruns, clean CI, provenance of evaluator and data splits | LLM-backed repeated trials need uncertainty/error bars; deterministic fixture repeats do not yield confidence intervals |

### Three first falsifiable hypotheses

- **H1, safety under stated assumptions:** With all allowed simulated effect routes mediated, epoch fencing and grant rechecks prevent stale/revoked workers from committing protected synthetic effects under enumerated crashes, replays and partitions. Removing a mandatory check should make a negative test fail.
- **H2, semantic continuation:** A typed, validated continuation manifest with explicit loss/refusal preserves critical constraints *at least as well as* naive history-only restart under selected held-out tasks. Failure is informative; preregister ablations and judge blindness.
- **H3, decision value:** A context/fault-aware policy choosing stay, restart, delegate or relocate may outperform always relocating on quality-adjusted cost for a declared workload distribution. Report regret and failure cases rather than expecting a win for movement.

## Documentation and repository navigation reset

Create **one hierarchy of authority** rather than deleting exploratory science:

1. **README:** a short problem statement, current *implemented vs proposed* capability table, one reproduction command, research scope/non-goals, and three links: charter, current benchmark, roadmap. Keep the long research library in a separately linked index over time.
2. **This strategy review:** decision record until adopted; maintainers accept, amend or reject it. On acceptance, carry the agreed short charter to README and update [roadmap](roadmap.md) rather than leaving multiple competing strategies.
3. **Canonical technical sources:** [glossary](glossary.md) for vocabulary; [how-it-works](how-it-works.md) for proposed envelope; [architecture](architecture.md) for **as-built** runtime; [evaluation plan](evaluation-plan.md) for unrun studies; [MobilityBench releases](mobilitybench-v0.2.md) and [results](mobilitybench-v0.2-results.md) for concrete run claims.
4. **Research library:** source corpora, forensic/security/frontier/human-impact agendas stay available but are labeled *background, hypothesis, or planned study* with an update date. Do not rewrite historical snapshot audits as though their original observations were false.
5. **Backlog/PR policy:** prioritize one end-to-end vertical slice, reject PR descriptions that contradict current main, and require each new research track to state hypothesis, baseline, negative test, evidence and stop condition before implementation.

The [open structure PR #17](https://github.com/MSKazemi/agent-movement/pull/17) already recommends research / reference implementation / evaluation separation. Reconcile it to current main, and migrate directories only with link, build and corpus-ID protections; reorganization is **not** the scientific milestone.

## Open maintainer decisions (proposal defaults)

| Decision | Recommended default | Alternative / trigger |
| --- | --- | --- |
| Research lab or product platform now? | **Lab first**, with one well-instrumented reference implementation | Product hardening only after verified real-user need and security boundary design |
| What counts as the central research operation? | **Relocation/ownership transfer**; delegation is baseline/adapter | Treat all remote delegation as movement only if glossary, evaluation and claims are deliberately rewritten |
| What makes the work distinctive? | Continuation contract + bounded authority + independent receipts + *fair* mobility decision benchmark | Do not claim a novel transport, identity passport or arbitrary live migration |
| How to settle runtime 0.1 vs proposal 0.2? | Write an explicit compatibility/migration decision and tests, keeping both statuses clear until landed | Design-only 0.2 permitted if README never calls it implemented |
| Benchmark name? | Discuss renaming or adding a distinctive scientific subtitle and machine ID; preserve aliases/references until migration | Keep MobilityBench only with citation/disambiguation strategy; do not assert trademark rights |
| What to do with PRs #16, #17, #83? | Refresh their factual snapshots; use #16 for #50, #17 for navigation, #83 for queued studies | Do not merge obsolete repository-state claims without edits |

## Immediate next actions (work that changes the project's trajectory)

1. **Approve or amend this charter** and choose one named measurable research outcome for the next 90 days.
2. **Fix headline factual debt:** status in [open questions](open-questions.md), historical snapshot banner in [movement-vs-copy](agent-movement-vs-copy-replication-multiplication.md), outdated [roadmap](roadmap.md), and proposed/implemented distinction in [how-it-works](how-it-works.md). Keep historical findings discoverable.
3. **Do issue #50 before new movement capabilities.** Bring PR #16 into current core/peer architecture and test independently controlled mediation.
4. **Write MobilityBench next-suite protocol before code**: held-out workload creation, baselines, LLM/no-LLM tracks, costs, human interventions, preregistered scoring, reproducibility.
5. **Run a bounded north-star experiment, publish negative results**, and only then decide whether cross-runtime semantic portability or a multi-hop human-authority study is the strongest next paper.
6. **Resolve the MobilityBench naming ambiguity** before promoting the suite widely; a separate 2026 benchmark already uses that name.

## External context and source boundaries

- [A2A interoperability notes](research-landscape.md) supports inter-agent task messaging/extension mechanisms; this project should **reuse**, not replace, that layer.
- [MCP interoperability notes](research-landscape.md) provides tool interface and task facilities; it is not proof of framework-independent checkpoint continuation.
- AMAP-ML/MobilityBench (separate external route-planning benchmark; see PR #88 source discussion) is a distinct route-planning benchmark using the same project benchmark name (checked 2026-10-16).

**Limitations of this review:** conclusions about implementation are inferred from available source/docs and repository history, not a fresh runtime penetration test or third-party reproduction. Roadmap dates are proposed sequencing. Nothing in this document is a claim of production security, mathematical proof, universal agent identity, legal clearance, or publishable originality.
