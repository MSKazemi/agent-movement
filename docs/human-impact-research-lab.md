# From human-impact questions to falsifiable Agent Movement research

**Reviewed:** 2026-10-15  
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
| **Q6 Accountability** | Local receipt/artifact hashes and database logs support limited debugging | Repeat and reopen SQLite, verify artifact digest; check signature-field absence | No authenticated principal, independently signed receipt or complete event chain | Issue #11 |
| **Q18 Safe replication** | Cooperative simulated gateway rejects duplicate effects and stale epochs | Multiple attempts, 12 concurrent calls, ownership transfer A -> B | Any stale-epoch commit or duplicated synthetic effect, within modeled gateway | Issue #9 |
| **Q19 Safe task continuation** | A pure approved task gives the expected artifact and exact retry returns persisted receipt | Direct local computation B0 vs Python-call delegated-like B2 | Receipt replay is **not** checkpoint relocation or cross-model continuity | Issues #7, #9, #10 |

This lab cannot resolve human-outcome questions such as healthcare efficacy, employment, discrimination or education on its own. It can develop technical safeguards and evidence useful to domain experts.

## Runnable pilot: MobilityBench local smoke v0.1

This pilot extends [PR #6](https://github.com/MSKazemi/agent-movement/pull/6) and is intentionally proposed as a **stacked PR** targeting that branch. It is **not** runnable on research-only main by itself.

~~~bash
python -m pip install -e .
python -m agent_movement.mobilitybench --output local-observations.jsonl
python -m unittest discover -s tests -v
~~~

The runner directly invokes local Python receiver/gateway classes, not a native A2A client. It emits one **sanitized JSONL** record per scenario: scenario ID, human-impact question IDs, mode, expected/observed behavior, verdict, monotonic local duration and allowlisted evidence. There are no model calls, network requests, production tokens, private user records, physical devices or external effects. Each run owns and deletes an ephemeral SQLite database. CLI exits nonzero if an observed behavior differs from the predefined expectation.

The three verdicts are **pass**, **fail**, and **known_gap**. A known gap is **not** a passed security guard: it means an intentionally scripted missing control was reproduced, and is counted separately. If that control is fixed, rewrite that case's hypothesis and expected result rather than representing its previous absence as success.

### Initial local observations (2026-10-15; Python 3.13)

| Verdict | Count | Meaning |
| --- | ---: | --- |
| Expected *narrow* local behavior reproduced | **17 of 20** | Validated scripted admission, exact retry, redaction, local ledger and fencing behavior |
| Known gaps reproduced | **3 of 20** | Caller can claim the approved agent ID; receiver grant revocation is not connected to tool commit; no signature/attestation field in receipt |
| Unexpected script outcomes | **0 of 20** | In this single run there were no discrepancies against the declared expected outputs |

This is a **single small deterministic engineering check**, not a statistically powered research result. Local B0 direct calculation and B2-like receiver calls have different execution boundaries; their measured durations are **not a fair performance comparison**. No A2A, actual checkpoint, remote identity or external-tool result was measured.

### Exactly what the current tests do NOT show

- **Identity before disclosure:** the receiver sees the task message before its local policy validation. An allowed-looking origin string is not a cryptographic identity.
- **End-to-end revocation:** the simulated gateway enforces ownership epochs, but does not independently recheck the original user's grant at commit.
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

## Suggested four-week research sprint

- **Week 1:** Review/merge prerequisite PR #6; run the 20-case smoke and publish a sanitized CI artifact. Record known gaps, not just passes.
- **Week 2:** Implement authenticated peer preflight and a simulated effect-time grant check; expand negative tests (issue #8).
- **Week 3:** Integrate official A2A with a two-process interoperability smoke (issue #7); preserve the application-level envelope.
- **Week 4:** Add first crash/replay fault schedule and a separate verifier design (issues #9/#11). Publish a small evidence report with caveats.

**Go/no-go rule:** Do not claim production-trustworthy movement without verified principals, scoped authority at every effect boundary, canceled/uncertain-action treatment and independently reproducible evidence. Keep actual health, financial and infrastructure actions outside this early testbed.

## Evidence and standards

- [Open technical questions](open-questions.md), [security and trust](security-and-trust.md), [roadmap](roadmap.md), [agent forensics](agent-forensics-and-fingerprints.md), [human-impact ranking on main](https://github.com/MSKazemi/agent-movement/blob/main/docs/top-20-human-impact-questions-for-agentic-ai.md).
- [MobilityBench full protocol proposal (PR #4)](https://github.com/MSKazemi/agent-movement/pull/4): separate from this small local smoke pilot.
- [A2A v1.0 specification](https://a2a-protocol.org/v1.0.0/specification/); [MCP](https://modelcontextprotocol.io/specification/2026-07-28); [NIST AI Agent Standards Initiative](https://www.nist.gov/news-events/news/2026/02/announcing-ai-agent-standards-initiative-interoperable-and-secure); [OWASP Agentic Top 10 2026](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/).

**Reproducibility note:** This document describes a local single-run reproduction and scripted assumptions. Independent CI and external replication are necessary before elevating the evidence grade.
