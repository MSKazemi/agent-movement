# Agent Movement: documentation navigator

**Reviewed and updated:** 2026-10-17. **Scope:** `main` research prototype, not production software. For claims about the currently installed version or tests, the [README](../README.md), [CHANGELOG](../CHANGELOG.md), [as-built architecture](architecture.md), and the code are authoritative; historical documents retain their own review dates.

The primary research question is whether explicitly authorized agent work can continue on another executor **without hidden state loss, unauthorized effects or unverifiable changes in task ownership**, and when moving is preferable to staying, restarting or delegating. Delegation is a comparison/protocol operation, not the same as ownership relocation.

## Start by what you want to do

| Goal | Start here | What you will find |
| --- | --- | --- |
| Understand the project and status | [README](../README.md) → [glossary](glossary.md) → [architecture](architecture.md) | Claims and limits, precise vocabulary, module/entrypoint map |
| Run a synthetic local example | [development](development.md) → [CLI reference](cli.md) → [local implementation](local-implementation.md) | Install extras, run local demos and tests, interpret error codes |
| Study agent/network interoperability | [protocol guide](protocols-and-networks/README.md) → [A2A adapter](a2a-adapter.md) → [A2A profile](a2a-profile-extension.md) | Draft profiles, real A2A framing and explicit limitations |
| Understand identity and security | [security model](security-and-trust.md) → [peer authentication](peer-authentication.md) → [secure-test inventory](secure-test-route-inventory.md) → [broker-only lab](secure-broker-only-profile.md) | Authenticated versus unmediated routes, explicit experimental boundary and remaining bypasses |
| Test checkpoint relocation | [checkpoint relocation](checkpoint-relocation.md) → [architecture](architecture.md) | LangGraph-compatible local checkpoint/copy/fencing experiments and fault limits |
| Examine verification evidence | [movement receipts](movement-receipts.md) → [forensics](agent-forensics-and-fingerprints.md) | Receipt validation, authority and lineage versus self-reported logs |
| Evaluate alternatives | [MobilityBench v0.2](mobilitybench-v0.2.md) → [v0.2 results](mobilitybench-v0.2-results.md) → [v0.3 scorer pilot](continuity-benchmark-v03-pilot.md) | Deterministic LLM-free baselines, frozen public split, explicit unavailable modes; no model-backed results yet |
| Investigate science and prior art | [research landscape](research-landscape.md) → [questions](open-questions.md) → [evidence map](evidence-map.md) | Literature, falsifiable open problems, and evidence gaps |
| Contribute or check quality | [contributing](../CONTRIBUTING.md) → [development](development.md) → [test registry](../data/test-registry.csv) | Current tests, scope boundaries, review workflow |

## Source-of-truth boundaries

- **Implementation:** `src/agent_movement/`, `pyproject.toml`, `tests/` and [as-built architecture](architecture.md). A strategy or spec document can describe an unimplemented feature.
- **Protocol/schema drafts:** [handoff JSON Schema](../schemas/handoff-envelope.schema.json), [how it works](how-it-works.md), [A2A extension](a2a-profile-extension.md). A `0.2.0-draft` schema is not evidence that the core runtime accepts it; core currently validates `0.1.0-draft`.
- **Authorization limits:** [continuity runtime](continuity-runtime-enforcement.md), [guarded authority activation](guarded-authority-transfer.md), [legacy target-side ingress fence](guarded-legacy-ingress-fence.md), and [peer preflight fence](guarded-peer-preflight-fence.md) cover distinct *opt-in, shared-store synthetic* paths. The [broker-only profile](secure-broker-only-profile.md) isolates one non-root worker; it **does not** disable independently launched legacy/A2A processes or globally mediate arbitrary tools and files.
- **Benchmarks:** [MobilityBench v0.1](mobilitybench-v0.1.md) and [v0.2](mobilitybench-v0.2.md) use scripted synthetic workloads, not sampled live model calls; differences between baselines are **not** proof of real-world superiority.
- **Research evidence:** [paper corpus](paper-corpus/README.md), [news corpus](news-corpus/README.md), [primary sources index](sources.md), [corpus timeline](corpus-analysis/README.md), and [standards tracker](standards-tracker.md). Published `AMP-` / `AMN-` identifiers and reproducibility rules must stay stable.
- **Decisions/proposals:** [architecture structure proposal](proposals/2026-10-16-repository-structure.md) and [decision record convention](decisions/README.md). Proposed direction is not approved governance.

## Next bounded milestone

**Issue #50** remains the umbrella for **complete mediation of all actually enabled test routes**, not an assertion of production security. The [charter](project-charter.md) and [roadmap](roadmap.md) were adopted through merged PR #88; the Linux seccomp experiment (#87), signed destination activation (#107), separate non-root worker (#113), guarded legacy/A2A denial (#114), broker-only operator profile (#118) and guarded peer preflight (#120) have now merged. Each covers a restricted synthetic path; they are **not** an end-to-end, all-listener tool/egress policy. PR #16's decision-only sample is a separate proposal and must not become a competing source of runtime authorization.

Target **one** demonstrator: synthetic authorized move with two isolated workers; independently verified identity and consent; a compatible checkpoint; stale-worker fencing; a missing/expired grant refusal before sensitive disclosure; an effect-side revocation denial; and independently verified receipts and fault evidence. Record which portions run only in the synthetic harness.

Keep `docs/news-corpus/`, `docs/paper-corpus/` and package fixture locations intact. Do not create a large new hierarchy until a concrete tested component needs a new home.
