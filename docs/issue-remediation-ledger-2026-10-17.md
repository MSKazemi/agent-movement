# Twenty-work-unit remediation ledger — 2026-10-17

**Scope:** User request to fix 20 issues in [Agent Movement](../README.md). At the start of this pass, GitHub search returned **8 open issue tickets**: [#50](https://github.com/MSKazemi/agent-movement/issues/50), [#93](https://github.com/MSKazemi/agent-movement/issues/93), [#95](https://github.com/MSKazemi/agent-movement/issues/95), [#96](https://github.com/MSKazemi/agent-movement/issues/96), [#98](https://github.com/MSKazemi/agent-movement/issues/98), [#99](https://github.com/MSKazemi/agent-movement/issues/99), [#102](https://github.com/MSKazemi/agent-movement/issues/102), [#103](https://github.com/MSKazemi/agent-movement/issues/103).

**Count honesty:** the 20 rows below are distinct **remediation work units**, not 20 different open GitHub issues and not 20 claimed issue closures. **Concurrent update:** issue #96 was resolved on main via a separate merged compatibility implementation while PR #104 was under review; PR #104 has therefore been closed **unmerged** to avoid duplicating the API. The issue count below refers to the initial audit, not a claim that #96 remains open. Items marked `PR IN REVIEW` were committed to review branches, but are not completed until their CI/merge acceptance gates pass. No open ticket should be closed merely because a subset or a synthetic test passed.

| Work unit | Parent issue | Concrete defect / deliverable | Evidence & status |
| --- | --- | --- | --- |
| R01 | #96 | Advertise implemented 0.1 wire distinctly from canonical 0.2 proposal | [merged 0.1/0.2 compatibility implementation](../src/agent_movement/envelope_compat.py) — #96 closed; PR #104 duplicate closed unmerged |
| R02 | #96 | Refuse unsupported 0.2-only peer negotiation | [existing compatibility tests](../tests/test_envelope_compat.py) — #96 closed |
| R03 | #96 | Reject lossy draft→runtime conversion, including unsigned integrity/policy constraints | [existing compatibility tests](../tests/test_envelope_compat.py) — #96 closed |
| R04 | #96 | Core and A2A deny unconverted draft envelopes | [existing compatibility tests](../tests/test_envelope_compat.py) — #96 closed |
| R05 | #96 | Version ADR, field crosswalk, deterministic offline migration demonstration | [existing compatibility tests](../tests/test_envelope_compat.py) — #96 closed |
| R06 | #103 | Distinguish fenced owner from destination-active state | [PR #109](https://github.com/MSKazemi/agent-movement/pull/109) — PR in review |
| R07 | #103 | Verify pinned destination-signed activation proof with anti-replay/epoch binding | #109 — PR in review |
| R08 | #103 | Require independently signed per-effect payload/identity proof | #109 — PR in review |
| R09 | #103 | Refuse stale, forged, revoked, cancelled, expired, wrong-policy instructions | #109 — PR in review |
| R10 | #93 / #103 | Map model `resume_destination` to executable signed activation; observe SQL | #109 — PR in review |
| R11 | #95 | Freeze 20 public synthetic task-spec pilot inputs separately from v0.1/v0.2 | [PR #111](https://github.com/MSKazemi/agent-movement/pull/111) — PR in review |
| R12 | #95 | Deterministic development/holdout split with SHA-256 data and ID digests | #111 — PR in review |
| R13 | #95 | Define task-spec-only non-agent B5 without oracle plan | #111 — PR in review |
| R14 | #95 | Keep unsupported real A2A/relocation modes in denominators as UNAVAILABLE | #111 — PR in review |
| R15 | #95 | Detect false success/refusal, unknown outcomes and forbidden effects in pilot scoring | #111 — PR in review |
| R16 | #102 | Independently controlled target-side process/ledger/receipt with trust isolation | **OPEN** — not implemented by an in-process signed gateway |
| R17 | #99 | Enumerate and independently gate every enabled HTTP, A2A, peer, CLI and relocation route | **OPEN** — a single peer-effect fallback fix does not prove complete mediation |
| R18 | #98 | Independently privileged untrusted worker, filesystem/FD/network/UID isolation matrix | **OPEN** — prior seccomp probes are narrower |
| R19 | #93 | Crash/partition/stale-restart model-to-runtime schedules with true negative controls | **OPEN** — bounded synthetic witness mapping is not full refinement |
| R20 | #50 | All enabled path policy, before-disclosure wire evidence and external tool-side enforcement | **OPEN** — umbrella acceptance requires #98/#99/#102 plus further experiments |

## Merge/close policy

1. Run every PR's full Python core/optional-extras matrix, strict static checking, corpus and documentation-link CI. Do not treat queued or running checks as successes.
2. Merge only on green results and after reconciliation with current main. Do not overwrite new CI/doc files that other parallel branches introduced.
3. After merge, update the parent issue with exact paths, tested fault boundaries, known counterexamples, work-unit IDs and omitted paths. Issue **#96 is closed** after its narrower compatibility code and tests were merged; PR #104 was closed unmerged. Keep **#95**, **#103**, **#93**, **#99**, **#98**, **#102** and **#50** open while their material requirements remain.
4. Verify completed GitHub issue counts from current API state. **Do not invent 12 extra issues** to make a numerical target or silently mark partial security work complete.

## Priority after the three review branches

**P0:** independently controlled target-side authority (#102), real secure-test listener inventory and disabled/gated alternate routes (#99), and process/UID/FD/network adversarial containment (#98). These are **dependencies** for broad #50 security claims. Next: crash/partition refinement under the activated guard (#93/#103).

**Research:** the versioned public synthetic benchmark pilot (#95) intentionally has **no real agent runs**. Next add pinned actual LLM execution, held-out task families, fair non-agent versus agent arms, independent ground truth/effect oracles, paired stochastic repeats and measured token/compute/dollar costs; do not publish toy-pilot proxy results as a mobility advantage.

The objective is demonstrably correct and safely scoped work, not a cosmetic issue closure count.
