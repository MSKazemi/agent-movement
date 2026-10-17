# Project charter: Agent Movement Lab

**Adopted research direction:** 2026-10-16. **Scope:** a bounded research-and-conformance laboratory, not a production mobility runtime or ratified standard. This document owns the current mission and success criteria; the [strategy review](strategy-review-2026-10-16.md) records the rationale and [roadmap](roadmap.md) owns the execution sequence.

## The problem, in one sentence

**When can AI-agent work continue on another authorized executor without silent task-state loss, unsafe or unauthorized effects, or untraceable changes in ownership—and when is movement worse than staying or restarting?**

**Mission.** Build reproducible scientific evidence and small, inspectable reference implementations for **authorized, verifiable continuation of agent work** across execution boundaries.

We study *work*, not the transmission of an LLM's hidden internal reasoning or the physical motion of robots. Under the [glossary](glossary.md), strict movement changes ownership of a logical task; **delegation is an important comparison but does not itself change ownership**. Agent identity, task identity, execution identity, authority and artifact provenance remain separate concepts.

## Who it serves

**Primary:** agent-framework maintainers, distributed-systems researchers, and AI reliability/security engineers who need reproducible answers about safe continuation and failure boundaries.

**Later:** teams moving real workflows across local/cloud/edge environments, only after trust, privacy, interoperability and operational safety have been evaluated beyond synthetic loopback tests.

## Three central scientific questions

1. **Continuity:** What minimal, explicit and compatible task state is sufficient to resume? What context, constraint, checkpoint or effect state is lost; when must import refuse?
2. **Authority and control:** Under which *enumerated and independently mediated* interfaces can the old executor be fenced, destination authority scoped, sensitive context withheld until authorized, and uncertain effects reconciled? No claims of bypass resistance outside those boundaries.
3. **Evidence and value:** Can an independent verifier establish a limited movement and effect timeline, and **when does moving beat staying, restarting or ordinary delegation** in correctness, intervention, latency and cost?

All other topics—hardware binding, copy/fork/replication, multi-hop drift, deletion obligations, device trust and external standards—should be traceable to one of these questions, not treated as independent simultaneous product commitments.

## First reference experiment (the north star)

A synthetic multi-step task starts on **Worker A**, with an explicit logical task ID, constraints, approved checkpoint and simulated effect ledger. After a crash or approved handoff request, a separate authority checks destination identity, grant, policy and compatibility before transferring allowed state. Worker B resumes from a compatible application checkpoint. A revived/stale Worker A must be denied by a controlled effect gateway. A side effect whose outcome is unknown must stop at **unknown/reconcile**, not be assumed absent. Sanitized, independently verified receipts distinguish observed facts from missing or self-reported events.

Run the *same intended workload* under four options:

| Mode | What it means | Why the comparison matters |
| --- | --- | --- |
| Stay | Continue on A if possible | Movement can introduce unnecessary risk and overhead |
| Restart | Begin an equivalent task on B with permitted inputs | A simple alternative can beat migration |
| Delegate | A retains ownership and asks B to do bounded work | Existing A2A-style cooperation may be enough |
| Relocate | Exclusive task ownership/checkpoint moves from A to B | The actual strict-movement hypothesis |

Reject incompatible or unsafe movement. A successful **safe refusal** is not a successful **task completion**. The north-star integrated evidence claim is **planned**; current modules test parts of it separately.

## What already exists on main (2026-10-16)

- A Python package with **loopback** handoff, optional A2A adapter, authenticated peer path, same-runtime LangGraph checkpoint relocation, two-store bundle copy, simulated effect fencing/reconciliation, signed receipts and an offline verifier. See [as-built architecture](architecture.md).
- A [Continuity Guard](continuity-guard-v0.md) decision-function prototype and [opt-in Continuity Runtime](continuity-runtime-enforcement.md) for a specific synthetic peer/effect path; **not global mediation of all adapters and egress paths**.
- An [abstract bounded state-space explorer](algorithms-and-cs-foundations.md); model findings do not imply verification of the Python runtime.
- Frozen [MobilityBench v0.1](mobilitybench-v0.1.md) and [v0.2](mobilitybench-v0.2.md) deterministic, **LLM-free** fault/continuation evaluations. Their results do not demonstrate agent behavior under model sampling or actual external tools.

**Important compatibility gap:** [the proposed canonical envelope](how-it-works.md) is `0.2.0-draft`; the current core uses `0.1.0-draft`. This distinction must remain visible until a tested migration/adaptation is implemented. Package version `0.2.0` is a separate version.

## Explicit non-goals for this stage

No universal process/LLM live migration; no recovery of hidden model state; no transfer of reusable human credentials; no automatic self-installation on unknown devices; no uncontrolled cloning/swarm growth; no new rival to A2A/MCP; no production-security or unqualified exactly-once claim. Physical actuation is limited to simulations and separate future safety reviews.

## A successful 90-day research cycle must deliver

1. **Coherent claims:** README, glossary, charter and roadmap distinguish historical designs, proposed contracts, implemented synthetic features and verified results.
2. **Bounded enforcement evidence:** origin, receiver and simulated effect paths in a **defined secure test profile** have independent checks and adversarial gate-removal/alternate-path tests; unmediated paths are disabled or explicitly out of scope. [Issue #50](https://github.com/MSKazemi/agent-movement/issues/50) is the primary tracking gate.
3. **Fair benchmarks:** held-out task splits, non-agent and one-agent controls, staying/restarting/delegation/relocation arms, cost and human-intervention accounting, available/unavailable mode reporting, and reproducible manifests. A model-backed arm is a *planned separate track*; it must not be implied by LLM-free pilot results.
4. **Independent demonstration:** a two-worker synthetic continuation, crash/partition and stale-origin negative tests, a compatibility/loss/refusal report, and a third-party-verifiable sanitized timeline. Publish failures and null results as well as successes.

A paper-worthy novelty claim requires prior-art comparison and independent replication; a passing unit-test count alone is not a scientific result.

## Scope and decision discipline

- **Now:** strict continuation/authority semantics, controlled-effect safety, receipts and fair evaluation.
- **Next (evidence-dependent):** cross-runtime compatibility with explicit loss, multi-hop intent/obligation continuity, offline edge simulation.
- **Later:** copying/forking/replication, real device/cloud deployment and broad human-impact experiments.
- **Stop condition:** if a capability cannot state its trust boundary, falsifiable hypothesis, fair baseline, observable failures and evidence source, it stays in research notes instead of becoming a product promise.

**Open strategic decisions:** whether to rename the project's MobilityBench suite to avoid confusion with a separate route-planning benchmark, the exact transition from 0.1 runtime to the 0.2 proposal, and which second runtime (if any) is worth an adapter. Freeze existing benchmark release names, formats and corpora until a versioned decision is recorded.

See the [12-week roadmap](roadmap.md) for sequencing and the [2026-10-16 review](strategy-review-2026-10-16.md) for alternatives and limitations.
