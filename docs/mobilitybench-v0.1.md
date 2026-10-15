# MobilityBench v0.1: frozen task-continuity baselines

**Status:** Pre-registered pilot protocol plus an executable, deterministic, LLM-free harness (2026-10-16).
**Tracks:** [issue #10](https://github.com/MSKazemi/agent-movement/issues/10); builds on [PR #6](https://github.com/MSKazemi/agent-movement/pull/6) and the [20-case smoke](human-impact-research-lab.md) (PR #14), which keeps working unchanged.
**Study plan:** the broader [proposed pre-registration protocol](mobilitybench-experiment-protocol.md) and [scientific agenda](strategic-target-and-scientific-agenda.md) (PR #4); this pilot covers only part of that plan.
**Question ([AM-14 / AM-15](open-questions.md)):** *When does moving agent work improve outcomes instead of only adding overhead, and how do we measure that without hiding failures?*

> This pilot gives exact, reproducible observations about a scripted interpreter. It does **not** measure LLM agents, real A2A interoperability, checkpoint relocation, cross-framework reconstruction, real external tools, or human outcomes. Nothing here supports a general statistical claim.

## Quick start

~~~sh
python -m pip install -e .
python -m agent_movement.mobilitybench verify --suite v0.1                       # fixture SHA-256 release check
python -m agent_movement.mobilitybench run --suite v0.1 --out results.jsonl      # 3 seeds x 2 repeats
python -m agent_movement.mobilitybench report --in results.jsonl --out report.md
python -m agent_movement.mobilitybench run --suite v0.1 --subset smoke --out smoke.jsonl   # CI subset
python -m agent_movement.mobilitybench run --suite v0.1 --no-timing --out a.jsonl # byte-identical output
python -m agent_movement.mobilitybench schedule --suite v0.1                     # seeded fault plan
python -m agent_movement.mobilitybench --output local.jsonl                      # original 20-case smoke
~~~

`run` writes one sanitized JSONL record per attempt, plus a `run_manifest` record first and one `security` record per negative fixture. Wall-clock fields (`elapsed_ms`, `started_at`) are the only non-deterministic values. They are excluded from every fingerprint and from the run's `outcome_digest`, and `--no-timing` sets them to `null` so that two runs produce byte-identical JSONL. It exits `2` when the fixture release check fails (nothing runs), `1` for a harness error, an unexpected negative-fixture result or a non-reproducible repeat, and `0` otherwise. A baseline that answers **incorrectly** is data, not a harness failure, so it does not change the exit code. The full suite takes about 10 seconds on a laptop and needs no dependencies beyond the standard library.

## Frozen release

The fixtures are in `src/agent_movement/fixtures/mobilitybench-v0.1/`, and they ship in the wheel.

| File | Content | SHA-256 |
| --- | --- | --- |
| `tasks.jsonl` | 18 frozen synthetic tasks (input, initial constraints, plan, session events, movement point) | `0062f2134ef67585d2ee55d6e84391fec37993985b0c3a4025d07ca677f7bd0b` |
| `ground_truth.jsonl` | Expected output lines, file and inventory digests, expected effects (payload digests) | `5f419aad1211864c55b6cf0b3dbf960ab142f1606675449a1c1feeb4ee89c620` |
| `negative.jsonl` | 12 negative/security fixtures with pre-declared expected observations | `4ace73a005d3355f35dd160159b0ad7422656e9f08ca59a60de62e09b1ed129e` |
| `seeds.json` | Seed manifest (`1103, 2207, 3301`), repeats (2), fault kinds, assignment rule, smoke subset | `2a383050ce093176d4bf5ae2a4da8a89c15db024cdbd1fefab3a113b33a3d368` |

**Release digest:** `920e9a2f4a7117729cba9f028c4c1ab394c9edbef4dd8fb10e49dda0ecc9a001`. This is the SHA-256 of the `sha256sum`-format listing of those four files in name order. You can check it independently:

~~~sh
cd src/agent_movement/fixtures/mobilitybench-v0.1
sha256sum ground_truth.jsonl negative.jsonl seeds.json tasks.jsonl | sha256sum   # must print the release digest
~~~

`run` and `verify` compute the same digest and fail closed when it does not match `MANIFEST.json`. Each record carries the digest under `run_version.fixture_release_digest`. A `.gitattributes` file marks the fixtures `-text` so that line-ending conversion cannot change the bytes.

**Versioning rule:** a frozen release is never edited in place. Any change to a task, a rubric, the interpreter semantics or the ground truth needs a new suite version and a new fixture directory. `tools/mobilitybench_freeze.py` regenerates the ground truth and the manifest, and is for maintainers only. CI runs `tools/mobilitybench_freeze.py --check`, which fails when the committed ground truth no longer matches the reference interpreter.

## Execution model

Each task is a short **plan** for one of three workload families. A deterministic interpreter (`deterministic-interpreter-v0.1`) executes it with **no model calls**.

- **Document work:** extract the first *n* sentences of sections, count words, hash the output, then publish a note (a simulated effect).
- **Constrained coding:** text-level `replace` / `append_line` on an in-memory synthetic file tree, a `check_contains` "test", file hashes, then open a review (a simulated effect). The code is never executed.
- **Multi-step simulated tools:** inventory `lookup`, `reserve` (a simulated effect that also changes state) and `notify` (a simulated effect).

There are two kinds of context:

- **Initial constraints** belong to the original request, so every executor knows them.
- **Session events** are rules a user adds mid-session (`at` = the plan step before which the rule arrives). Only the executor that is live at that moment hears them. This is the context that a naive restart loses.

At `movement_at`, the task is due to move from `agent-a` (origin) to `agent-b` (destination). Every simulated effect is a commit to the PR #6 `EffectGateway`: an owner/epoch-fenced SQLite ledger in a fresh temporary database for each attempt.

### Frozen tasks

"Effects pre / post" lists the planned effect steps before and after the movement point. "Delegable tail" means every step from the movement point onwards is a pure op that the PR #6 `0.1.0-draft` envelope can carry (`word_count`, `sha256`).

| Task | Family | Steps | Move at | Initial rules | Events before move (lost by restart) | Events after move | Effects pre / post | Delegable tail |
| --- | --- | ---: | ---: | --- | --- | --- | --- | --- |
| `doc-release-notes` | document | 5 | 3 | – | redact_terms@1 | – | 2 / – | yes |
| `doc-meeting-summary` | document | 5 | 2 | require_label | redact_terms@1 | – | – / 3 | no |
| `doc-policy-digest` | document | 4 | 1 | – | – | – | – / 3 | no |
| `doc-incident-brief` | document | 5 | 3 | – | redact_terms@0 | – | 2 / – | yes |
| `doc-faq-merge` | document | 5 | 2 | – | – | redact_terms@2 | – / 3 | no |
| `doc-handbook-excerpt` | document | 5 | 3 | – | require_label@1 | – | 1 / – | yes |
| `code-rename-helper` | coding | 5 | 2 | – | forbid_path@1 | – | – / 4 | no |
| `code-add-docstring` | coding | 5 | 2 | max_line_length | – | – | – / 4 | no |
| `code-version-bump` | coding | 5 | 3 | – | – | – | 2 / – | yes |
| `code-guard-config` | coding | 5 | 1 | – | – | forbid_path@2 | – / 4 | no |
| `code-line-limit` | coding | 5 | 2 | – | max_line_length@0 | – | – / 3 | no |
| `code-test-fixture` | coding | 5 | 2 | – | – | – | 1 / – | yes |
| `tools-restock-order` | tools | 5 | 3 | – | forbid_tool@2 | – | 1, 2 / – | no |
| `tools-travel-booking` | tools | 4 | 1 | – | – | – | 0 / 1 | no |
| `tools-ticket-triage` | tools | 5 | 3 | allowed_recipients | – | – | 1, 2 / – | yes |
| `tools-calendar-hold` | tools | 5 | 2 | – | – | forbid_tool@3 | 1 / 3 | no |
| `tools-refund-sim` | tools | 5 | 3 | – | allowed_recipients@1 | – | 1, 2 / 3 | no |
| `tools-inventory-audit` | tools | 5 | 2 | – | – | – | – / 3 | no |

All text, names, addresses (`192.0.2.7` is the TEST-NET-1 documentation range) and recipients are synthetic.

## Baseline modes

| Mode | ID | Status | Definition in v0.1 |
| --- | --- | --- | --- |
| `keep_on_origin` | B0 | implemented | The origin runs every step and nothing is transferred. If the origin is pre-empted at the movement point, the attempt is **incomplete**. |
| `restart_on_destination` | B1 | implemented | The origin runs up to the movement point and transfers the *original request* (input, initial constraints and plan, no session context). The gateway transfers ownership to B (epoch 2), and B re-executes from step 0. B hears only the session events at or after the movement point, and it uses fresh effect IDs (`…r1`) because it cannot know the origin's IDs. |
| `local_delegate` | B2-local | implemented | The origin keeps ownership and delegates each remaining step through the **real PR #6 `HandoffReceiver`** (in-process, with a scoped `Approval`, a strict envelope and idempotent receipts). If any remaining step is not a contract-expressible pure op, the attempt is **refused** (`incompatible_state:<ops>`) before anything is sent. A pre-empted origin cannot collect receipts, so the attempt is **incomplete**. |
| `a2a_delegate` | B2 | **UNAVAILABLE** | Official A2A v1 SDK delegation, [issue #7](https://github.com/MSKazemi/agent-movement/issues/7). |
| `checkpoint_relocate` | B3 | **UNAVAILABLE** | Same-runtime checkpoint relocation, [issue #9](https://github.com/MSKazemi/agent-movement/issues/9). |
| `cross_framework_reconstruct` | B4 | **UNAVAILABLE** | Cross-framework reconstruction. Not scheduled yet ([AM-14](open-questions.md); follows #9). |

Unavailable modes are still emitted once per (seed, task, repeat), with `outcome: "unavailable"` and a tracking reference. They appear in every denominator table and are never scored as failures or successes. When a mode is implemented, it gets a new suite version, not a silent change to v0.1.

## Fault injection

The seed manifest declares the seeds `1103, 2207, 3301` and 2 repeats. For each seed *s*, the tasks are ordered by `sha256("mobilitybench-v0.1:<s>:<task_id>")`, and the fault index is `(position + s) mod 5`. This gives a balanced, auditable schedule with no global random number generator. It is identical on Python 3.10, 3.11 and 3.13 (verified). All modes of a (seed, task) pair get the **same** fault, so the mode comparisons are paired. Over the full run the fault counts are: `none` 10, `origin_preempted` 10, `effect_ack_lost` 11, `duplicate_delivery` 12, `stale_origin_returns` 11. Each record states whether the fault actually applied to that mode (`fault_applied`).

| Fault | B0 keep | B1 restart | B2-local delegate |
| --- | --- | --- | --- |
| `origin_preempted` (at the movement point) | incomplete | unaffected (B owns the task) | incomplete (the owner is not transferred), unless already refused |
| `effect_ack_lost` (first commit) | commit lands, ack lost → `unknown` → reconcile → `committed` | same | same, if an effect occurs before the move |
| `duplicate_delivery` (each transfer message ×2) | n/a | intake deduplicates on movement ID | PR #6 receiver replays the receipt (`replayed: true`) |
| `stale_origin_returns` (after the move) | n/a | old-epoch commit attempt → fenced or accepted | n/a (the origin is still the owner) |

## Per-attempt record (sanitized JSONL)

The records contain IDs, enums, counts and digests only. There is never any task text, effect payload, section content or exception message. `run` refuses to write output if any fixture redaction term or the synthetic canary appears anywhere in the records.

| Field | Meaning |
| --- | --- |
| `run_id`, `run_version{suite_version, fixture_release_digest, contract_version, harness_version, executor, model, python}` | Run version. `model` is `none`, and `model_calls` is always 0 (cost = 0 tokens). |
| `seed`, `repeat`, `task_id`, `family`, `mode`, `baseline`, `mode_status`, `tracking`, `fault`, `fault_applied` | Attempt identity |
| `outcome` ∈ `completed / incomplete / refused / unavailable / harness_error`, plus `reason` | Refusals and incompatible states are published, not dropped |
| `task_correct`, `output_correct` | See the rubric. `null` when the attempt did not complete. |
| `constraints_preserved` / `constraints_total` | Preserved constraints (evaluated on completed attempts) |
| `policy_violations` | Committed effects that violate an active policy, plus accepted stale-epoch commits |
| `duplicate_effects`, `unexpected_effects`, `missing_effects`, `effects_committed` | Committed synthetic effects compared with the ground truth |
| `unknown_events`, `reconciled_events` | Unknown/reconcile events |
| `stale_commits_fenced`, `stale_commits_accepted`, `duplicate_deliveries_suppressed` | Fencing and deduplication evidence |
| `transfer_bytes`, `transfer_messages`, `sensitive_transfers` | Canonical JSON bytes and messages crossing origin↔destination (both directions for delegate). `sensitive_transfers` counts messages that contain a term the task marks for redaction. |
| `steps_executed`, `steps_reexecuted` | Deterministic work proxy |
| `elapsed_ms` | Wall-clock time. Machine-dependent and dominated by SQLite setup, so it is **not** a fair latency comparison. |
| `outcome_fingerprint` | SHA-256 over every deterministic field (all except time, run ID and repeat) |

The `run` stderr summary and the report also carry an `outcome_digest`: a SHA-256 over every attempt fingerprint and every negative-fixture observation. It is timing-free, so two machines can compare whole runs by this one value.

## Evaluator rubrics

The ground truth is the output of a **full-knowledge, fault-free** execution: B0 with every session event heard. The constraint and policy checks below are computed from the final state and the ledger. They do not re-use the executor's decisions.

- **`output_correct`:** the SHA-256 of `{output lines, per-file SHA-256, inventory}` equals the frozen `output_digest`.
- **Constraints**, checked on completed attempts:
  - `redact_terms`: no listed term appears in the output lines or in any committed effect payload.
  - `forbid_path`: the protected file is byte-identical to the input.
  - `max_line_length`: every line of every file is within the limit.
  - `require_label`: every committed payload starts with the label.
- **Policies**, time-aware and counted on every attempt including incomplete ones. A committed effect at plan step *k* violates a rule that became active at a step ≤ *k*:
  - `forbid_tool`: any commit of that tool.
  - `allowed_recipients`: a commit of that tool to a recipient not on the list.
  - A stale-epoch commit accepted by the gateway also counts.
- **Effects:**
  - `duplicate_effects` = Σ(commits per plan step − 1).
  - `unexpected_effects` = commits whose (step, tool, recipient, payload digest) is not in the ground truth.
  - `missing_effects` = expected effects that were never committed (completed attempts only).
- **`task_correct`:** completed **and** output correct **and** all constraints preserved **and** 0 policy violations, duplicates, unexpected effects and missing effects.

## Negative and security fixtures

Every negative fixture pre-declares its expected observation and runs in its own temporary directory and database. The cases share no state and give the same results in any order (tested).

The possible verdicts are:

- `pass`: the observation matches the expectation.
- `known_gap`: a documented missing control was reproduced. This is **not** a pass.
- `gap_closed`: a known-gap case observed its pre-declared `closed_observation`, meaning the control now exists (for example after issue #8). This is reported separately, does not fail CI, and requires the case to be rewritten in the next suite version.
- `fail`: any other observation. A fail makes `run` exit 1.

| Case | Expected | Verdict class | What it shows / does not show |
| --- | --- | --- | --- |
| `neg-private-restart` | `refused_before_transfer` | pass | The harness movement gate stops a `private` task before any bytes leave the origin |
| `neg-private-delegate` | `disclosed_before_refusal` | **known_gap** | The PR #6 receiver rejects `private` only *after* receiving the envelope (536 bytes). Authorization before disclosure is issue #8. |
| `neg-oversized-delegate` | `refused` | pass | State above the 2048-byte contract is refused, not truncated |
| `neg-canary-delegate` | `absent_from_records_and_audit` | pass | The canary never reaches the JSONL or the receiver audit table. It **is** still sent to the receiver. |
| `neg-forged-destination` | `denied` | pass | A destination-claim mismatch is denied. The claims themselves are still unauthenticated (see smoke). |
| `neg-movement-id-reuse` | `denied` | pass | Movement-ID reuse under a new idempotency key is a conflict |
| `neg-stale-origin` | `fenced` | pass | The old-epoch origin cannot commit after the ownership transfer |
| `neg-effect-payload-conflict` | `denied` | pass | Same effect ID with a different payload is rejected |
| `neg-instruction-in-data` | `not_executed` | pass | Instruction-like data does not trigger an effect in a **deterministic** interpreter. This is a regression placeholder that says nothing about LLM executors. |
| `neg-tampered-fixture` | `rejected` | pass | A one-byte change fails the release digest |
| `neg-unknown-effect` | `unknown` | pass | A missing ledger row is `unknown`, never "failed" |
| `neg-revocation-not-at-effect` | `committed_without_grant_recheck` | **known_gap** | After revocation, the receiver denies a new handoff, but the executor's next simulated effect still commits. The gateway checks epochs, not grants. |

## Pilot observations (2026-10-16, Python 3.11.16, release `920e9a2f…`)

There are 324 attempt records per repeat (18 tasks × 3 seeds × 6 modes). Of these, 162 are implemented-mode attempts and 162 are unavailable-mode records. Repeat 1 reproduced every repeat-0 outcome fingerprint (0 mismatches of 324 groups). The run's timing-free `outcome_digest` was `32be6911f2d16b12d3eb18bcad847a2a9c406614e7b8249310251666e62b6adb` on Python 3.10, 3.11 and 3.13 alike, with the wheel installed and run outside the source tree. There were 0 harness errors. The negative fixtures gave 10 passes, 2 known gaps, 0 closed gaps and 0 failures out of 12.

| Mode | Completed | Correct / attempts | Correct / completed | Constraints kept (completed) | Policy violations | Duplicate effects | Unexpected effects | Unknown→reconciled | Stale fenced | Transfer bytes | Refused | Incomplete |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B0 keep | 44/54 | 44/54 | 44/44 | 27/27 | 0 | 0 | 0 | 11→11 | 0 | 0 | 0 | 10 |
| B1 restart | 54/54 | 15/54 | 15/54 | 12/30 | 6 | 30 | 24 | 11→11 | 11 | 33 580 | 0 | 0 |
| B2-local delegate | 16/54 | 16/54 | 16/16 | 8/8 | 0 | 0 | 0 | 4→4 | 0 | 48 004 | 36 | 2 |
| B2 A2A / B3 relocate / B4 reconstruct | UNAVAILABLE | not scored (54 records each) | – | – | – | – | – | – | – | – | – | – |

Correct / attempts by fault:

| Mode | none | origin_preempted | effect_ack_lost | duplicate_delivery | stale_origin_returns |
| --- | ---: | ---: | ---: | ---: | ---: |
| B0 keep | 10/10 | 0/10 | 11/11 | 12/12 | 11/11 |
| B1 restart | 3/10 | 1/10 | 4/11 | 3/12 | 4/11 |
| B2-local delegate | 5/10 | 0/10 | 3/11 | 5/12 | 3/11 |

The `report` subcommand regenerates these tables, the per-family breakdown, the refusal reasons and every raw per-case row from the JSONL.

**What these observations support, within this interpreter and these 18 tasks:**

1. **Keep vs. restart is a trade-off, not a winner.** B0 is correct whenever the origin survives, and it never completes under pre-emption (0/10). B1 always completes, but it is correct only on the 5 tasks that have **no pre-movement session context and no pre-movement effects** (`doc-policy-digest`, `doc-faq-merge`, `code-add-docstring`, `code-guard-config`, `tools-inventory-audit`; 5 × 3 seeds = 15). It lost mid-session constraints (12/30 kept), repeated committed effects (30 duplicates) and violated lost policies (6).
2. **Output correctness is not enough.** In `tools-travel-booking`, B1 produces a byte-identical output but books the seat twice. The rubric marks it incorrect through `duplicate_effects`.
3. **Ordinary delegation is not movement.** B2-local never violated a constraint or policy. However, it refused 36/54 attempts because the PR #6 envelope cannot carry effects, edits or context (`incompatible_state:*`). It also does not survive origin pre-emption, because ownership never moves. It transferred more bytes than restart (48 004 vs 33 580), even though it covered fewer tasks.
4. **The missing comparator is exactly the unavailable one.** Surviving pre-emption *and* preserving context and effect identity needs state and ownership transfer (B3, issue #9). v0.1 measures the gap that B3 must close, but it cannot show that B3 closes it.

**What they do not support:** any claim about LLM agents, real networks, latency, cost in tokens, real tool APIs, or the frequency of these situations in practice. The counts are deterministic consequences of the authored fixtures and fault schedule, not samples from a population. No confidence intervals are reported, because repeats do not vary.

## Validity threats

- **Construct:**
  - The ground truth is produced by the same interpreter that the baselines use, in full-knowledge mode. The constraint and policy checks are independent of the executor, but `output_correct` checks consistency with the interpreter semantics, not human-judged quality.
  - Restart's fresh effect IDs are a modelling assumption: a restarted LLM agent typically issues new tool-call IDs. A restart that derived deterministic IDs would show fewer duplicates.
  - The "delegable" set is defined by the PR #6 contract, so B2-local refusals measure that contract, not delegation in general (that is B2/A2A, issue #7).
- **Internal:**
  - The fixtures and faults were authored by the same project that builds the system. Movement points and session events were chosen to exercise each mechanism, so the task mix is **not** representative.
  - Restart's intake deduplication on the movement ID is harness-level code, not a separately tested component.
  - Delegate runs in-process with its receiver. Transfer bytes are canonical-JSON sizes, not wire bytes, and they exclude HTTP overhead.
  - Each attempt runs in a single process with its own fresh SQLite files. v0.1 therefore does not exercise the multi-process "database is locked" race when a fresh file is first switched to WAL. That race is fixed separately on the PR #14 review branch, and v0.1 says nothing about multi-process contention.
- **External:** these are 18 tiny synthetic tasks with no model, no real tools, no network, no concurrency between agents and a single machine. Real agents add stochasticity, partial outputs and model or version drift that v0.1 does not exercise.
- **Statistical conclusion:** the "samples" are deterministic, so repeats only test reproducibility. A different seed only re-assigns faults. Any percentage computed from these counts describes this fixture set and nothing beyond it.
- **Security scope:** the negative fixtures test the local application profile only. Agent IDs remain unauthenticated claims (see the smoke's known gaps). The canary test shows that records and audit are clean, not that the receiver never saw the data.

## Reproducibility checklist

1. `python -m agent_movement.mobilitybench verify --suite v0.1` should report release digest `920e9a2f4a7117729cba9f028c4c1ab394c9edbef4dd8fb10e49dda0ecc9a001`.
2. `run --suite v0.1 --out results.jsonl` should exit 0. The stderr summary should report `harness_errors: 0` and `reproducibility.mismatched: 0`.
3. Compare the `outcome_digest` (or the per-attempt `outcome_fingerprint` values, never `elapsed_ms`) with another machine's results. They should be identical on Python ≥ 3.10.
4. `report --in results.jsonl` should match the tables above, apart from timing.
5. CI (`.github/workflows/python-smoke.yml`) runs `freeze --check`, `verify` and the smoke subset (6 tasks × 1 seed × 6 modes plus the 12 negatives) on Python 3.11 and 3.13, and uploads the JSONL and the Markdown report as artifacts.

## Next versions

- **v0.2:** score B3 once issue #9 lands, with crash points inside the plan (not only at the movement point) and partitions. Score B2 once issue #7 lands.
- **Later:** an LLM executor behind the same interface, with pinned model versions in `run_version.model`, real repeated sampling, and pre-registered sample sizes and intervals. Also blinded human rubric scoring for document tasks, and external task contributions.
