# Agent Movement Lab: evidence-led roadmap

**Adopted research direction:** 2026-10-16. **Planning horizon:** roughly 12 weeks from charter adoption. These are priorities and acceptance gates, **not release promises**. The [project charter](project-charter.md) defines the single mission; the [strategy review](strategy-review-2026-10-16.md) records why we chose it.

## North-star goal

Demonstrate, within explicitly stated synthetic/local trust and failure boundaries, that an authorized long-running task can **resume on a compatible second executor**, a stale prior executor cannot commit a **protected simulated effect** through the controlled gateway, an uncertain action is parked for reconciliation, and an independent verifier can reconstruct the bounded evidence. Compare that with **stay, restart and delegation** so the project can say **when not to move**.

Delegation is a baseline and an interoperability mechanism, **not strict movement of ownership**. This roadmap never promises preservation of hidden model state, universal cross-framework portability, complete observability or global bypass resistance.

## Current snapshot on main (2026-10-16)

| Workstream | Already demonstrated (bounded) | Still missing for the north-star claim |
| --- | --- | --- |
| Contracts and identity | Strict core envelope, proposed 0.2 canonical JSON Schema, logical/execution IDs, peer signing/grants | [Decision ADR-001](handoff-contract-versioning.md): 0.1 live only, explicit lossless offline 0.2 projection and refusal of unsupported semantics. Actual 0.2 wire remains future work; unified admissions still open. |
| Transfer and persistence | Local HTTP/A2A experiments, same-runtime LangGraph checkpoint relocation, two-store digest-verified copy | End-to-end cross-worker policy composition with a single independently testable boundary; no general cross-framework resume |
| Authority and control | Peer checks, synthetic grant/revocation/effect fencing, Continuity Guard/opt-in Continuity Runtime, bounded state-space model | Mandatory enforcement on **all enabled controlled paths** and explicit accounting for unmediated egress/alternate adapters; issue #50 |
| Evidence | Signed receipts, fixtures, offline verifier, reconciled simulated effects | Independent end-to-end timeline with documented gaps and opposing observations; external effects remain out of scope |
| Evaluation | Frozen LLM-free MobilityBench v0.1 and v0.2 with fault schedules and explicit unavailable arms | Fair held-out tasks and a non-agent baseline, stochastic model-backed arm, reviewer/intervention and comparable cost data |

**Do not misread a module list as integrated guarantees.** The existing [as-built architecture](architecture.md), [Continuity Runtime notes](continuity-runtime-enforcement.md), [MobilityBench v0.2](mobilitybench-v0.2.md) and [evaluation plan](evaluation-plan.md) state the present limits. The abstract [model-checking research](algorithms-and-cs-foundations.md) validates only its small-state model, not the Python implementation. The runtime still accepts `0.1.0-draft` envelopes, while the canonical proposal specifies `0.2.0-draft`.

## Stage A — Strategic and documentation consistency (weeks 1–2)

**Deliverables:** adopt the [charter](project-charter.md); give README one-line mission/current status/start-here entry; retire stale **current-state** assertions without overwriting historical snapshots; replace the superseded planning roadmap; preserve the 0.1/0.2 contract divergence and record the next compatibility decision. Keep corpora and frozen benchmarks unchanged.

**Exit gate:** a reader can name the mission, distinguish strict movement from delegation, run one synthetic demo, and tell exactly what is **implemented**, **tested**, **planned** or **out of scope** without encountering a contradictory headline claim.

**Related:** [structure PR #17](https://github.com/MSKazemi/agent-movement/pull/17) should be reviewed against the present tree before any file migrations; architecture organization is secondary to research evidence.

## Stage B — Mandatory bounded enforcement (weeks 3–5)

**Deliverables:** prioritize [P0 issue #50](https://github.com/MSKazemi/agent-movement/issues/50). Reconcile the standalone [policy PR #16](https://github.com/MSKazemi/agent-movement/pull/16) with current authenticated peer and opt-in Continuity Runtime semantics, **without duplicating authority state**. Require verifier-derived identity, bound grants, policy epoch, permission and compatibility before disclosure; recheck at delivery and at atomic simulated-effect commit. Explicitly disable or independently gate legacy/A2A/relocation alternative paths in a named *secure experimental profile*.

Develop the adversarial process and egress experiment from [PR #87](https://github.com/MSKazemi/agent-movement/pull/87) as an **independent bounded negative test**, not a claim of arbitrary host or network containment.

**Exit gate:** enumerate every enabled ingress/egress/tool effect path, run positive and negative tests, verify no forbidden accepted handoff/protected simulated effect within the listed controls, identify exposure if denial happens *after* disclosure, and show at least one **red/green gate-removal** test. A proof under one modeled trust boundary is never promoted to universal safety.

**Stop on:** unmediated paths, missing trust evidence, policy ambiguity or ability to commit via an alternate enabled route. Publish the gap instead of calling the stage complete.

## Stage C — Comparative real-agent evidence (weeks 6–9)

**Deliverables:** preregister a *new* versioned evaluation suite rather than modifying frozen v0.1/v0.2 fixtures. Make held-out synthetic/public tasks with declared constraints and effect ground truth. Add a fair task-specification-only non-agent control and one-agent control; keep stay, restart, delegate and relocate available **only where implemented**. Evaluate optional LLM-backed executors as a **separate** stochastic arm with model/version, repeat runs, prompt/artifact provenance, cost and human-intervention fields.

**Exit gate:** reproducible pinned manifests and split hashes; comparable denominator and workload for each arm; predeclared scoring and confidence intervals where stochastic samples justify them; refusals, unknown outcomes, leaks, false decisions, duplicates and unavailable arms reported separately. Movement is allowed to lose on correctness, cost or safety.

**Stop on:** oracle-plan leakage into baselines, comparison with unsupported modes, fixture changes without suite-version bump, or claims about LLM agents derived solely from deterministic runs.

## Stage D — Independent north-star reproduction (weeks 10–12)

**Deliverables:** integrate one **safe, local, synthetic** two-worker checkpoint scenario, a simulated effect gateway and a verifier that does not trust evidence-bundle-supplied anchors. Fault a resumed worker and delayed prior owner; record compatibility and semantic-loss refusals plus unknown/reconciliation outcomes. Publish executable commands, full manifests, sanitized receipts, negative cases and a limitations table.

**Exit gate:** another investigator can reproduce the allowed continuation, the stale-worker denial, the incompatible-checkpoint refusal and the verifier's distinction between **verified**, **claimed** and **unknown** facts. No real purchases, private data or unattended device control.

## Metrics and evidence discipline

| Dimension | Required outputs | Non-negotiable interpretation |
| --- | --- | --- |
| Task continuity | correct/all attempts, correct/completed, constraint preservation, explicit refusal and incomplete rates | A refusal is not a completed task |
| Safety on controlled interfaces | blocked/unblocked attempted movement, disclosed bytes before consent, out-of-policy committed synthetic effects, stale epochs | Target zero **only under the enumerated mediation assumptions** |
| Ambiguity | unknown effects, operator reconcilations, replay conflicts, time to recovery | No end-to-end exactly-once claim for uncontrolled effects |
| Provenance | signed/verified receipts, omitted events, conflicting witness claims, trust-anchor failures | Signatures do not prove correctness or log completeness |
| Tradeoffs | latency, transfer size, compute/tokens, human intervention, cost per **correct** completion, fallback/regret | Report negative results and unavailable modes |
| Reproducibility | pinned versions, fixture hashes, split/seed manifests, validation scripts and environment limitations | Deterministic repeats are not statistical confidence intervals |

## After the evidence gate, not before

If Stage D succeeds, select **one** of: (a) second-runtime compatibility/loss-reporting, (b) multi-hop intent and multi-principal obligations, or (c) offline/edge continuation under partitions. Hardware binding, copying/replication, swarms and public cross-organization deployment stay research tracks pending a dedicated safety/threat case.

## Immediate maintainers' sequence

1. Adopt the charter and correct entry documentation; verify docs and corpus CI.
2. Review and reconcile PR #16, PR #17 and PR #87 to **current main**; prioritize #50.
3. Write the next benchmark protocol **before** adding model-backed runners; keep MobilityBench v0.1/v0.2 frozen.
4. Record decisions on contract versions, benchmark naming and next runtime as explicit, linkable issues rather than implicit promises.
5. Integrate and independently verify **one** north-star path; publish a bounded research report, including failures.

**Older milestones in this repository were proposals written before the runnable package existed.** They are not outstanding simply because earlier plans still mention them. The [2026-10-16 strategic audit](strategy-review-2026-10-16.md) preserves that history.
