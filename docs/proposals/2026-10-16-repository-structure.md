# Repository architecture: current-state review and incremental structure

**Reviewed:** 2026-10-16 against `main` at `7231c533dc35334030fec545be0ff866bcbaef1d`.  
**Status:** Draft proposal for maintainer review, **not** an adopted architecture decision or a production assurance statement.  
**Purpose:** Update the original structure review after many related PRs merged. This review focuses on organization and integration order; the separate mission/90-day charter proposal is in PR #88.

## Recommended focus

Treat **Agent Movement** as a research and conformance lab for *safe, verifiable continuation of AI-agent work* across executor boundaries. The distinctive questions are whether task intent and explicit state survive, whether transfer of authority is bounded and auditable, and when movement beats staying, restarting or delegating under fair tests.

Keep three connected workstreams:

1. **Research evidence:** hypotheses, standards and protocol comparisons, historical literature, device/safety questions and falsifiable scientific claims.
2. **Reference experiments:** a Python-first package with language-neutral contracts, policy-controlled boundaries, local/A2A adapters, same-runtime checkpoint transfer and verification artifacts.
3. **Reproducible evaluations:** frozen fixtures, security/fault-injection and independent results, eventually including held-out model-backed trials.

Do not confuse delegation with task ownership relocation, treat a content digest as proof of identity, or describe any existing experiment as secure arbitrary-device roaming. Cross-framework reconstruction, live process migration, concealed propagation and unrestricted self-copying are **not** implemented.

## 1. Verified repository snapshot

The earlier version of this proposal described a research-only `main` and PR #6 as open. That is **obsolete**. At the reviewed main commit:

| Area | Present on main | Boundary |
| --- | --- | --- |
| Documentation and data | `docs/`, `data/`, scholarly/news corpora, standards tracker, glossary, research agenda, device catalog, architecture, source index | Broad coverage does not demonstrate unique research results |
| Python package | `src/agent_movement/`, a package/CLI defined in `pyproject.toml`, multiple independent loopback demos | Experimental, synthetic/local; not a production SDK or secure cross-host runtime |
| Handoff and A2A | `core.py`, `http.py`, `peer.py`, `peer_http.py`, `a2a_*.py`, `trust.py` | A2A path documents unauthenticated identities; do not infer it inherits peer-path controls |
| Runtime continuation | `relocation*.py`, `relocation_bundle.py` with a pinned LangGraph experiment, local stores and crash matrices | Same-runtime, safe-checkpoint experiment; not universal migration |
| Authorization and evidence | `continuity_guard.py`, `continuity_runtime.py`, `receipts.py`, `live_receipts.py`, `retention.py` | An opt-in peer receiver gates a bounded synthetic SQLite effect; **not** complete mediation of every path |
| Benchmark and interoperability | `mobilitybench*.py`, `src/agent_movement/fixtures/`, `interop/js/`, `interop/conformance/`, `schemas/handoff-envelope.schema.json` | MobilityBench v0.1/v0.2 are deterministic and LLM-free; interoperability remains scoped |
| Testing and automation | `tests/`, `tools/`, research determinism checks and separate Python/A2A/static CI workflows | Coverage is not a substitute for attacker-controlled OS/network boundary testing |

Read `../architecture.md` for the as-built module inventory (it declares its verification commits), `../development.md` for test commands, `../cli.md` for generated CLI usage, and `../continuity-runtime-enforcement.md` for enforcement claims and explicit gaps. The new `../index.md` is the navigation entry point.

### Pending work as of this review

- **Issue #50, still open:** mandatory controlled-path enforcement, sender-side egress restriction, independent sandbox bypass testing, and security red/green regressions. PR #86 has already delivered *partial* opt-in continuity enforcement on the peer receiver and simulated effect ledger; do not discard or duplicate it.
- **PR #16, open:** useful deny-by-default policy evaluator, but decision-only and based on an older branch. Reconcile with `peer.py` / `continuity_runtime.py` rather than installing a second authorization truth.
- **PR #87, open:** separate proposed Linux egress bypass lab. Review together with #50 to avoid claiming that one Python-level wrapper provides OS isolation.
- **PR #85, open:** algorithmic/formal foundations; keep experimental and formal claims distinct until checked.
- **PR #88, open:** mission and 90-day strategy reset. This structure document should **complement**, not independently settle, its project positioning and benchmark-name questions.
- **PR #17:** the current document/navigation draft. Earlier PR #6 and PR #14 work is already represented on `main`; no remaining merge sequencing around those PRs is needed.

Recheck branch status and main SHA before merging or quoting the snapshot as current.

## 2. Architecture boundaries to keep explicit

These are conceptual responsibility boundaries, **not** a demand to split the current flat package into many directories immediately.

| Boundary | Should own | Must not assume |
| --- | --- | --- |
| **Contracts / schema** | Versioned operation, task/lineage IDs, supported capabilities, envelope/receipt/checkpoint formats and compatibility refusals | That a schema-valid task is authorized |
| **Identity and trust** | Cryptographically verified principals, intended peer, trusted evidence provenance, key/trust domain | That an advertised Agent Card or unverified `agent_id` is identity |
| **Policy and approval** | Scope/audience/expiry, consent and obligation evidence, revocation, deny-before-disclosure and effect-time checks | That client-side decisions or system prompts enforce a hostile executor |
| **Coordinator and authority** | Ownership, fencing epoch, state transition, recovery, idempotency, unknown/reconcile outcomes | Exactly-once effects at uncontrolled services |
| **Transport adapters** | A2A framing, local test transport and wire conversion | That A2A supplies authentication or portable checkpoint semantics |
| **Runtime adapter** | Explicit compatible checkpoint export/import, safe boundary and loss reporting | Lossless hidden/model state transfer |
| **Storage and evidence** | Artifact integrity, durable state, minimum disclosed audit, independent receipt verification and retention | That signed telemetry proves all events occurred or that no routes were unobserved |
| **Benchmark and tests** | Independent baselines, frozen fixtures, fault cases, model-backed follow-on, negative results and denominators | That deterministic toy-agent success implies real-agent superiority |

Security invariant to test in **named, enabled interfaces**: if a movement or effect is forbidden under independently verified policy, it must not produce an accepted protected handoff or committed simulated effect. The claim requires **complete mediation of those listed routes** under stated host, issuer and gateway assumptions. A dishonest sender, extra listener, compromised host or arbitrary network egress may remain unmediated and must be reported as such.

### Contract/version concern

The runtime currently validates a `0.1.0-draft` handoff contract, while the proposed schema/docs describe `0.2.0-draft`. Avoid declaring the draft to be already supported by `core.py`. Before a semantic package split or new remote transport, publish a migration/compatibility table and negative downgrade tests.

## 3. Recommended physical structure

Keep the **existing** paths as the stable integration boundary for now. Only files tagged `[future]` are proposed additions; do not create empty folders for presentation.

```text
agent-movement/
├── README.md                    # current public entry point
├── pyproject.toml               # existing experimental Python package and extras
├── Makefile
├── .github/workflows/           # existing corpus, static, Python, A2A, links checks
├── docs/
│   ├── index.md                # this PR: status-aware document index
│   ├── architecture.md         # existing as-built architecture
│   ├── decisions/README.md     # this PR: how to record proposed/adopted ADRs
│   ├── proposals/
│   │   └── 2026-10-16-repository-structure.md  # this PR
│   ├── protocols-and-networks/  # existing
│   ├── news-corpus/             # KEEP paths and published AMN IDs
│   ├── paper-corpus/            # KEEP paths and published AMP IDs
│   ├── corpus-analysis/         # KEEP generated and reproducible
│   ├── corpus-qa/               # KEEP provenance and verification
│   └── *.md                     # keep current references stable
├── data/                        # existing evidence, device, standards and test registries
├── schemas/
│   └── handoff-envelope.schema.json  # existing draft; not runtime source of truth
├── src/agent_movement/           # existing experiment package; stay flat for now
│   ├── core.py, trust.py, peer.py, continuity_runtime.py, ...
│   ├── a2a_*.py, relocation*.py, receipts*.py, mobilitybench*.py
│   └── fixtures/                # KEEP package data and frozen manifest paths
├── interop/
│   ├── js/                     # existing independent JS adapter test
│   └── conformance/            # existing protocol TCK-related tests
├── tests/                       # existing tests, fixture trees and conformance tests
├── tools/                       # existing reproducible corpus/QA/build scripts
├── experiments/                 # [future] only after versioned experiment manifests exist
└── benchmarks/                  # [future] optional public evaluation data/report index;
                                 # do not move package fixtures without compatibility plan
```

A possible **later** Python decomposition is `contracts/`, `identity/`, `policy/`, `coordinator/`, `transports/`, `runtimes/`, `storage/` and `evidence/`. Split one seam at a time **only** when there is a stable interface, independent regression coverage and no circular dependency. Preserve public imports, console commands, fixture manifests, experiment reproducibility and adapter compatibility. An aesthetically neat directory tree is not a milestone.

## 4. Immediate work sequence and acceptance checks

| Order | Work | Stop/go criteria |
| --- | --- | --- |
| **A. Clarify** | Review PR #88's charter, label current-vs-historical docs and explicitly decide `0.1` runtime versus `0.2` proposal compatibility plan | One agreed narrow central claim, no contradictory top-level capability status |
| **B. Enforce** | Reconcile PR #16 with current peer/runtime facts; finish #50 along with PR #87's bounded egress research where useful | Independent sender/receiver/effect gates for every **enabled secure-test route**; canary non-disclosure preflight tests, revocation/epoch race tests, direct endpoint bypass attempts and mutation red/green in CI |
| **C. Validate** | Build one repeatable two-worker, receipt-verified checkpoint case with injected failure and denied stale effect, and a verifier external to execution code | Published trace and signed receipt evidence with explicit known gaps, no false exactly-once claim |
| **D. Research** | Run held-out model-backed stay/restart/delegate/relocate evaluation with fair task/budget and non-agent baselines; retain deterministic suite as regression tests | Independent reruns, repeated trials, task correctness and constraints, refusals, cost and safety metrics, negative results |
| **E. Modularize** | Separate tightly coupled modules **only after** contract/coverage gates settle | Existing tests/CLI/schema/fixtures stable; no corpus-ID or published link churn |

Before any merge affecting existing paths run the relevant checks in `../development.md` and CI. Keep research corpus ID/digest determinism checks independent of optional SDK integrations. When a move changes import paths, fixture paths, or documented links, require automated migrations and test proof in the same PR.

## 5. Maintainer decisions not yet resolved by this PR

1. **Mission:** approve or revise the narrow *verifiable continuation* thesis in PR #88 and decide how copying/device/swarms topics remain secondary research tracks.
2. **Versioning:** whether and how the `0.2` handoff profile becomes executable without breaking `0.1` acceptance/refusal semantics.
3. **Complete mediation boundary:** list enabled senders, receivers, adapters, transports and simulated effect gateways; decide which must be disabled or separately gated in secure-test mode.
4. **Evidence standard:** which signatures, trust anchors and independent effect observations are required before making a verifiable-continuity claim.
5. **Benchmark identity:** assess the existing separately named MobilityBench research benchmark before choosing a non-confusing name. A naming decision is not made here.
6. **Licensing/contribution:** follow the repository's current policies; this document makes no new permission or license commitment.

## What this PR changes

**Documentation only:** add a status-aware entry index and a decision-record process, and replace the stale no-code architecture inventory with this current snapshot. This does **not** change any runtime code, published data IDs, schema, tests, CI, or `main`. It does not adopt PR #88 or close Issue #50.
