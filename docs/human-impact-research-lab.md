# From human-impact questions to falsifiable Agent Movement research

**Reviewed:** 2026-10-16  
**Status:** Research protocol + a small executable local smoke study. Neither successful synthetic tests nor a protocol design establish production safety.  
**Scope:** Software agents moving tasks and authority, not physical robot motion. Synthetic/public data and mock side effects only.

## Research method: one question, one testable claim, one limitation

For each major human-impact question:

1. State a **bounded claim** and what is *not* claimed.
2. Pre-register baseline, failure model, synthetic fixtures, negative controls and correctness oracle before collecting scores.
3. Compare **keep**, **restart**, **delegate**, **same-runtime checkpoint relocate**, and later **cross-framework reconstruct**; mark unavailable modes as unavailable, never silently score them as failures.
4. Measure at enforcement points: an agent's promise and a correlated trace ID do not establish permission or prove a committed tool action.
5. Publish per-case outcomes, denominator, software versions, known gaps, all failures, and alternative interpretations.
6. Seek external implementation, model/task diversity and blinded evaluation before making general claims.

A zero-violation count over a small set of scripted synthetic cases does **not** establish real-world safety. A cooperative SQLite transaction does not guarantee exactly-once behavior for third-party services.

## Six immediately testable questions

| Human-impact question | Testable hypothesis in this repo | Baseline and observation | What falsifies or limits the claim | Tracking |
| --- | --- | --- | --- | --- |
| **Q1 Human control** | A revoked/expired receiver-local grant blocks a **new** handoff | Approved task vs revoked and expired synthetic deliveries | Unapproved new task accepted; *existing* downstream work is separate | PR #6, issue #8 |
| **Q3 Verified identity** | Allowed task IDs/origin/destination **claims** are scoped, but must not be confused with authenticated principals | Wrong string claims denied; deliberately show expected-ID impersonation is unverified | No caller/workload authentication in current prototype | Issue #8 |
| **Q5 Context privacy** | Strict envelope rejects unsupported classification and unknown fields; synthetic payload canary absent from stored audit events | Compare canary-bearing task to redacted local audit | This does not protect data **before it reaches** receiver or guarantee remote deletion | Issue #8 and future retention research |
| **Q6 Accountability** | Local receipt/artifact hashes and database logs support limited debugging | Repeat and reopen SQLite, verify artifact digest; forge a receipt and show the offline digest check accepts it | No authenticated principal, independently signed receipt or complete event chain | Issue #11 |
| **Q18 Safe replication** | Cooperative simulated gateway rejects duplicate effects and stale epochs | Multiple attempts, 12 concurrent calls, ownership transfer A -> B | Any stale-epoch commit or duplicated synthetic effect, within modeled gateway | Issue #9 |
| **Q19 Safe task continuation** | A pure approved task gives the expected artifact and exact retry returns persisted receipt | Direct local computation B0 vs Python-call delegated-like B2 | Receipt replay is **not** checkpoint relocation or cross-model continuity | Issues #7, #9, #10 |

This lab cannot resolve human-outcome questions such as healthcare efficacy, employment, discrimination or education on its own. It can develop technical safeguards and evidence useful to domain experts.

## Runnable pilot: MobilityBench local smoke (suite `mobilitybench-local-smoke-v0.2`)

The smoke started as a stacked PR on [PR #6](https://github.com/MSKazemi/agent-movement/pull/6) (PR #14) and now runs on main. [Issue #22](https://github.com/MSKazemi/agent-movement/issues/22) made its expectations fixture-declared, its cases independent and its output byte-reproducible.

~~~bash
python -m pip install -e . pytest
python -m agent_movement.mobilitybench --output local-observations.jsonl
python -m agent_movement.mobilitybench --no-timing --output a.jsonl   # byte-identical across runs
python -m pytest -q          # all tests: agent_movement + corpus tooling
~~~

The runner directly invokes local Python receiver/gateway classes, not a native A2A client. It emits one **sanitized JSONL** record per scenario: scenario ID, human-impact question IDs, mode, declared expectation, expected/observed behavior, verdict, monotonic local duration, allowlisted evidence and (for gaps) the expected fix. The summary line on stderr adds the counts per verdict and an `outcome_digest`. There are no model calls, network requests, production tokens, private user records, physical devices or external effects. CLI exits `1` if an observed behavior matches neither the declaration nor a declared gap's closed state, and `2` if the case declarations are invalid.

**Declared expectations.** Every case declares its expectation in the packaged fixture [`cases.jsonl`](../src/agent_movement/fixtures/mobilitybench-local-smoke/cases.jsonl), the same approach as the [v0.1 negative fixtures](mobilitybench-v0.1.md). The expectation is `pass`, `known_gap` (with the expected fix and the observation that would show the control exists), or `gap_closed`. The tests derive every count from these declarations, so no count is hard-coded.

**Verdicts.** The four verdicts are **pass**, **known_gap**, **gap_closed** and **fail**. A known gap is **not** a passed security guard: it means a scripted attack on a missing control succeeded, and it is counted separately. If a later change closes the gap on the path this case exercises, the case observes its declared closed observation and is reported as `gap_closed`. That is not a failure and does not break CI, but the case must then be rewritten with a new hypothesis rather than counting its earlier absence as success.

**Isolation and determinism.** Each case runs in its own temporary directory with its own SQLite database, and no case reads state written by another. The tests check that reversed execution order gives byte-identical output and that every case run alone gives the same record as in the full run. `duration_ms` is the only wall-clock field. It is excluded from `outcome_digest`, and `--no-timing` writes it as `null`, so two runs give byte-identical JSONL (tested, and checked with `cmp` in CI).

### Current local observations (2026-10-16)

| Verdict | Count | Meaning |
| --- | ---: | --- |
| `pass` | **17 of 20** | Expected *narrow* local behavior reproduced: scripted admission, exact retry, redaction, local ledger and fencing |
| `known_gap` | **3 of 20** | The scripted attack succeeded against the core path (see the table below) |
| `gap_closed` | **0 of 20** | No declared gap is closed on the core path |
| `fail` | **0 of 20** | No discrepancy against the declarations |

These counts were identical on CPython 3.11.16, 3.13.15, 3.14.7 and 3.15.0rc2, with the same timing-free `outcome_digest` (`828c9114ce4c4fc15655c6a3746875a87443287cab7fa825443bd7349cbd9f35`). They describe this commit; the authoritative counts are whatever the declarations and the latest run say.

This is a **small deterministic engineering check**, not a statistically powered research result. Local B0 direct calculation and B2-like receiver calls have different execution boundaries, so their durations are **not a fair performance comparison**. No A2A, actual checkpoint, remote identity or external-tool result was measured.

### The three known gaps, re-evaluated after issues #8 and #11

Issues #8 (peer authentication, commit-time grant recheck) and #11 (signed movement receipts) are on main. Both add **separate** modules. Neither changes the PR #6 core classes (`HandoffReceiver`, `EffectGateway`) that this smoke exercises. All three gaps therefore remain open **on the core path**, and each case points to the module that closes it elsewhere.

| Case | Attack exercised | Observed on the core path | Closed elsewhere by |
| --- | --- | --- | --- |
| `claimed_identity_is_not_authenticated` (Q3) | A party other than agent-a builds an envelope from non-secret identifiers, claims origin agent-a and supplies its own text | Executed; the receipt attributes it to agent-a | `agent_movement.peer.PeerReceiver`: signed agent cards and scoped grants, checked before delivery ([peer authentication](peer-authentication.md), issue #8) |
| `grant_revocation_not_bound_to_effect_gateway` (Q1, Q3) | Approved work starts, the grant is revoked, then the executor commits its next simulated effect | The receiver denies a new handoff, but the effect still commits | `agent_movement.peer.AuthorizedEffectGateway`: grant recheck inside the commit transaction (issue #8) |
| `receipt_is_not_independently_authenticated` (Q6) | Anyone holding a core receipt rewrites the artifact value and recomputes the unkeyed digest | The forgery passes the only offline check a third party can run | `agent_movement.receipts`: Ed25519-signed receipts and an offline verifier ([signed movement receipts](movement-receipts.md), issue #11, optional `signing` extra) |

The first case has an inherent limit: the direct Python API has no notion of the actual caller, so the harness can only state that the forger is not agent-a. The receiver's inability to tell the two apart is exactly the gap.

### Exactly what the current tests do NOT show

- **Identity before disclosure:** the receiver sees the task message before its local policy validation. An allowed-looking origin string is not a cryptographic identity.
- **End-to-end revocation:** the core simulated gateway enforces ownership epochs, but does not recheck the original user's grant at commit. The separate `AuthorizedEffectGateway` (issue #8) does, but only for the peer-auth path, and only in simulation.
- **Privacy across trust domains:** rejection of an unsupported classification does not mean a remote server never received it.
- **Independent incident reconstruction:** unsigned digests and logs are neither complete nor proof of the truth of an agent's claims.
- **Real agent migration:** reopening an artifact receipt is not restoring hidden chain-of-thought, a live process stack or a framework checkpoint.
- **Exactly-once arbitrary effects:** the simulator's in-transaction idempotency does not extend to non-cooperating third-party APIs.
- **Real-world human impact:** there are no clinical, employment, educational or social outcome trials here.

## Next experiments with explicit falsification conditions

**E1 — Identity and consent before disclosure (issue #8):** Build an authenticated preflight gate that checks the intended recipient, user grant and allowed data class *before sending task content*. Negative control: a forged destination obtains any synthetic secret-canary byte. The current receiver must remain labeled insecure until this test passes under a declared trust model.

**E2 — Real protocol interoperability (issue #7):** Use the official pinned A2A Python SDK between two independently running processes; compare the correct artifact and contract checks against the local baseline. Reject missing capabilities, unsupported schema and mismatched destination. Do not rename direct Python-call evidence as A2A.

**E3 — Crash-safe same-runtime checkpoint relocation (issue #9):** Stop an unfinished task at a documented safe checkpoint, persist it, transfer ownership A -> B, and show B resumes rather than repeats from the beginning. Inject crashes before/after each state transition. A stale executor committing a simulated effect falsifies the safety claim. Uncertain external acknowledgements must be represented as **unknown/reconcile**.

**E4 — Independent forensic verifier (issue #11):** Have a separate verifier validate a canonical signed receipt, simulated independent tool records, issuer identities and conflicting/missing evidence. A signature makes a particular statement attributable, not necessarily true; explicitly report uncertainty.

**E5 — Meaningful task and model comparisons (issue #10, [PR #4](https://github.com/MSKazemi/agent-movement/pull/4)):** Freeze input digests and rubrics for document analysis, code editing and multi-step workflows. Include B0 keep, B1 restart, real B2 A2A delegate, B3 same-runtime resume, and later B4 reconstruct. Report task correctness, lost constraints, unauthorized simulated effects, partial outcomes, cost and latency across repeated runs. Publish failures and unavailable baselines.

*Status (2026-10-16):* a deterministic, LLM-free first slice is [MobilityBench v0.1](mobilitybench-v0.1.md). It has 18 frozen synthetic tasks with a SHA-256 release manifest. B0 keep, B1 restart and the PR #6 local delegate are scored under seeded faults. B2 A2A, B3 relocate and B4 reconstruct are reported as unavailable. The suite also includes 12 negative/security fixtures and a report with denominators. Model-based tasks, real A2A and checkpoint relocation remain open.

## Suggested four-week research sprint

- **Week 1:** Review/merge prerequisite PR #6; run the 20-case smoke and publish a sanitized CI artifact (done: CI uploads it). Record known gaps, not just passes.
- **Week 2:** Implement authenticated peer preflight and a simulated effect-time grant check; expand negative tests (issue #8).
- **Week 3:** Integrate official A2A with a two-process interoperability smoke (issue #7); preserve the application-level envelope.
- **Week 4:** Add first crash/replay fault schedule and a separate verifier design (issues #9/#11). Publish a small evidence report with caveats.

**Go/no-go rule:** Do not claim production-trustworthy movement without verified principals, scoped authority at every effect boundary, canceled/uncertain-action treatment and independently reproducible evidence. Keep actual health, financial and infrastructure actions outside this early testbed.

## Evidence and standards

- [Open technical questions](open-questions.md), [security and trust](security-and-trust.md), [roadmap](roadmap.md), [agent forensics](agent-forensics-and-fingerprints.md), [human-impact ranking on main](https://github.com/MSKazemi/agent-movement/blob/main/docs/top-20-human-impact-questions-for-agentic-ai.md).
- [MobilityBench full protocol proposal (PR #4)](https://github.com/MSKazemi/agent-movement/pull/4): separate from this small local smoke pilot.
- [A2A v1.0 specification](https://a2a-protocol.org/v1.0.0/specification/); [MCP](https://modelcontextprotocol.io/specification/2026-07-28); [NIST AI Agent Standards Initiative](https://www.nist.gov/news-events/news/2026/02/announcing-ai-agent-standards-initiative-interoperable-and-secure); [OWASP Agentic Top 10 2026](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/).

**Reproducibility note:** This document describes a local single-run reproduction and scripted assumptions. Independent CI and external replication are necessary before elevating the evidence grade.
