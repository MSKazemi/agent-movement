# Agent Movement: documentation navigator

**As-of:** 2026-10-16. **Scope:** `main` research prototype, not production software. For claims about the currently installed version or tests, the [README](../README.md), [CHANGELOG](../CHANGELOG.md), [as-built architecture](architecture.md), and the code are authoritative; historical documents retain their own review dates.

The primary research question is whether explicitly authorized agent work can continue on another executor **without hidden state loss, unauthorized effects or unverifiable changes in task ownership**, and when moving is preferable to staying, restarting or delegating. Delegation is a comparison/protocol operation, not the same as ownership relocation.

## Start by what you want to do

| Goal | Start here | What you will find |
| --- | --- | --- |
| Understand the project and status | [README](../README.md) → [glossary](glossary.md) → [architecture](architecture.md) | Claims and limits, precise vocabulary, module/entrypoint map |
| Run a synthetic local example | [development](development.md) → [CLI reference](cli.md) → [local implementation](local-implementation.md) | Install extras, run local demos and tests, interpret error codes |
| Study agent/network interoperability | [protocol guide](protocols-and-networks/README.md) → [A2A adapter](a2a-adapter.md) → [A2A profile](a2a-profile-extension.md) | Draft profiles, real A2A framing and explicit limitations |
| Understand identity and security | [security model](security-and-trust.md) → [peer authentication](peer-authentication.md) → [continuity runtime](continuity-runtime-enforcement.md) | What is authenticated and which paths are *not* protected |
| Test checkpoint relocation | [checkpoint relocation](checkpoint-relocation.md) → [architecture](architecture.md) | LangGraph-compatible local checkpoint/copy/fencing experiments and fault limits |
| Examine verification evidence | [movement receipts](movement-receipts.md) → [forensics](agent-forensics-and-fingerprints.md) | Receipt validation, authority and lineage versus self-reported logs |
| Evaluate alternatives | [MobilityBench v0.2](mobilitybench-v0.2.md) → [v0.2 results](mobilitybench-v0.2-results.md) → [evaluation plan](evaluation-plan.md) | Deterministic LLM-free baselines, honest gap reporting, proposed fair/model-backed studies |
| Investigate science and prior art | [research landscape](research-landscape.md) → [questions](open-questions.md) → [evidence map](evidence-map.md) | Literature, falsifiable open problems, and evidence gaps |
| Contribute or check quality | [contributing](../CONTRIBUTING.md) → [development](development.md) → [test registry](../data/test-registry.csv) | Current tests, scope boundaries, review workflow |

## Source-of-truth boundaries

- **Implementation:** `src/agent_movement/`, `pyproject.toml`, `tests/` and [as-built architecture](architecture.md). A strategy or spec document can describe an unimplemented feature.
- **Protocol/schema drafts:** [handoff JSON Schema](../schemas/handoff-envelope.schema.json), [how it works](how-it-works.md), [A2A extension](a2a-profile-extension.md). A `0.2.0-draft` schema is not evidence that the core runtime accepts it; core currently validates `0.1.0-draft`.
- **Authorization limits:** [continuity runtime](continuity-runtime-enforcement.md) describes **opted-in peer receiver + simulated effect** controls; legacy HTTP, unverified A2A, relocation, arbitrary egress and other listeners are not globally mediated by it.
- **Benchmarks:** [MobilityBench v0.1](mobilitybench-v0.1.md) and [v0.2](mobilitybench-v0.2.md) use scripted synthetic workloads, not sampled live model calls; differences between baselines are **not** proof of real-world superiority.
- **Research evidence:** [paper corpus](paper-corpus/README.md), [news corpus](news-corpus/README.md), [primary sources index](sources.md), [corpus timeline](corpus-analysis/README.md), and [standards tracker](standards-tracker.md). Published `AMP-` / `AMN-` identifiers and reproducibility rules must stay stable.
- **Decisions/proposals:** [architecture structure proposal](proposals/2026-10-16-repository-structure.md) and [decision record convention](decisions/README.md). Proposed direction is not approved governance.

## Next bounded milestone

**Issue #50** targets mandatory policy enforcement and independent bypass testing for a specifically defined **secure-test profile**. An opted-in peer-receiver/effect-store slice exists, but sender egress, independent sandbox evidence, and alternate route coverage remain incomplete. PR #16 (decision-only policy), PR #87 (Linux egress research), and PR #88 (mission/90-day strategy proposal) are related open work; review their status before implementation.

Target **one** demonstrator: synthetic authorized move with two isolated workers; independently verified identity and consent; a compatible checkpoint; stale-worker fencing; a missing/expired grant refusal before sensitive disclosure; an effect-side revocation denial; and independently verified receipts and fault evidence. Record which portions run only in the synthetic harness.

Keep `docs/news-corpus/`, `docs/paper-corpus/` and package fixture locations intact. Do not create a large new hierarchy until a concrete tested component needs a new home.
