# MobilityBench v0.2: mid-step crashes, partitions and a stable-ID restart

**Status:** Frozen, digest-verified pilot release plus deterministic, LLM-free harness 0.3.0 (2026-10-16). Like v0.1 it is frozen in this repository's version control and has **not** been registered with an external, time-stamped registry, so it is **not a pre-registration**.
**Tracks:** [issue #40](https://github.com/MSKazemi/agent-movement/issues/40). Builds on [MobilityBench v0.1](mobilitybench-v0.1.md), whose fixtures, digests and outcomes are unchanged.
**Question ([AM-03 / AM-04 / AM-14](open-questions.md)):** *When a move is interrupted inside a step, or the messages between origin and destination are lost or late, which continuation keeps effect identity and task correctness, and which modes cannot be faulted that way at all?*

> v0.2 gives exact, reproducible observations about a scripted interpreter under simulated crashes and partitions. It does not measure LLM agents, real process kills, real networks, cross-host relocation or real external tools. Nothing here supports a general statistical claim.

## What v0.2 adds

v0.1 injects faults only at the movement point and at the first effect, and its restart baseline (B1) assumes that a restarted run issues fresh effect IDs. v0.2 keeps the 18 v0.1 tasks, the rubrics and the interpreter, and adds:

1. **Seeded mid-step crashes:** the executor dies *inside* an effect step, either after it formed the effect intent but before the commit reached the ledger, or after the commit is durable but before the acknowledgement reached it.
2. **Seeded partitions** between origin and destination: the first request is dropped, the first reply is dropped, or the first request is delayed past the sender's timeout.
3. **A new baseline, `restart_stable_ids` (B1-stable):** B1 with the origin's deterministic effect IDs, so the gateway deduplicates a re-issued effect. It makes the fresh-ID assumption behind B1's duplicate effects visible.
4. **Explicit applicability:** every record whose scheduled fault did not act carries a `fault_not_applied_reason`, and the report tabulates them.
5. **A new frozen release** with a frozen fault schedule (`schedule.jsonl`) and three new negative fixtures.

## Quick start

~~~sh
python -m pip install -e .                       # core: B0, B1, B1-stable, B2-local scored
python -m pip install -e '.[a2a,relocation]'     # optional: also score B2 (A2A v1) and B3 (relocation)
agent-movement bench verify --suite v0.2                        # fixture SHA-256 release check
agent-movement bench schedule --suite v0.2                      # frozen fault plan, with crash steps
agent-movement bench run --suite v0.2 --out results.jsonl       # 5 seeds x 2 repeats
agent-movement bench report --in results.jsonl --out report.md
agent-movement bench run --suite v0.2 --subset smoke --no-timing --out a.jsonl   # CI subset, byte-identical
python tools/mobilitybench_freeze.py --suite v0.2 --check       # ground truth, schedule and manifest
~~~

The same subcommands work as `python -m agent_movement.mobilitybench …`. `--suite` defaults to `v0.1`, so every v0.1 command keeps its meaning. Exit codes are those of v0.1: `2` when the fixture release check fails, `1` for a harness error, an unexpected negative-fixture result or a non-reproducible repeat, `0` otherwise. The full run took about 11 seconds without extras and about 60 seconds with both extras on a laptop.

## Frozen release

The fixtures are in `src/agent_movement/fixtures/mobilitybench-v0.2/` and ship in the wheel.

| File | Content | SHA-256 |
| --- | --- | --- |
| `tasks.jsonl` | The 18 v0.1 tasks, byte-identical (paired comparison with v0.1) | `0062f2134ef67585d2ee55d6e84391fec37993985b0c3a4025d07ca677f7bd0b` |
| `ground_truth.jsonl` | Byte-identical to v0.1 (same tasks, same reference interpreter) | `5f419aad1211864c55b6cf0b3dbf960ab142f1606675449a1c1feeb4ee89c620` |
| `negative.jsonl` | 16 negative/security fixtures: the 12 of v0.1 plus 4 for stable IDs, a lost receipt, a crashed-but-paused origin and runtime revocation | `03848608b7e3eae082e37c6622aa2cc1abe21d88b04215c13cc5cd6cc251a14d` |
| `seeds.json` | Seeds `1103, 2207, 3301, 4409, 5501`, 2 repeats, 10 fault kinds, both assignment rules, smoke subset | `0c55da237cd34d8ec85c661871e29d2aa7447bc51adb1a40e88edbfa3f2977bd` |
| `schedule.jsonl` | The materialized schedule: one `{seed, task_id, fault, crash_step}` row per (seed, task), 90 rows | `59bfb99295115fae3d3ae1c569b6c0c1767aac1b3fdc32e6f7f2627d18f759c4` |

**Release digest:** `2408da9a991d5a57c2467df17ca09247b69c3c5faa20099f3725a8210fc1fd63`, the SHA-256 of the `sha256sum` listing of the five files in name order:

~~~sh
cd src/agent_movement/fixtures/mobilitybench-v0.2
sha256sum ground_truth.jsonl negative.jsonl schedule.jsonl seeds.json tasks.jsonl | sha256sum
~~~

`verify`, `run` and `schedule` fail closed when a digest does not match `MANIFEST.json`. Loading the suite also recomputes the schedule from the seeded generator and refuses a `schedule.jsonl` that differs from it, even when the manifest digests were regenerated to match an edited file (tested). The v0.2 negative fixtures cite prefixed question IDs (`HQ-nn`, `AM-nn`; see [the crosswalk](question-id-crosswalk.md)); the frozen v0.1 file keeps its legacy `"Qn"` values.

**v0.1 is untouched.** No v0.1 fixture byte changed (`tools/mobilitybench_freeze.py --check` and the release digest `920e9a2f…` still pass). Harness 0.3.0 reproduces every v0.1 outcome: the full v0.1 run gives the documented `outcome_digest` values in both environments (`d3f51dd6…` with both extras, `15442176…` without), its 661 JSONL records equal those of harness 0.2.0 field for field apart from `run_version.harness_version` and the `run_id` derived from it, and a test pins the v0.1 smoke-subset digests computed with harness 0.2.0. v0.1 records carry no v0.2 field.

## Fault model

The schedule assigns one fault kind to each (seed, task); all modes of that pair get the same fault, so mode comparisons are paired. For each seed *s*, tasks are ordered by `sha256("mobilitybench-v0.2:<s>:<task_id>")` and the fault index is `(position + s) mod 10`. For the two crash kinds, `crash_step` is the plan's effect steps (effect and reserve ops, in plan order) indexed by `int(sha256("mobilitybench-v0.2:<s>:<task_id>:crash_step"), 16) mod (their count)`. There is no global random number generator. Over the full run the counts are: `none` 8, `origin_preempted` 9, `effect_ack_lost` 9, `duplicate_delivery` 10, `stale_origin_returns` 10, `crash_before_effect_commit` 9, `crash_after_effect_commit` 9, `partition_drop_request` 9, `partition_drop_reply` 9, `partition_delay` 8. Every seed schedules all ten kinds, and the smoke subset (seed 1103, 10 tasks) contains each kind once. Of the 18 crash assignments, 8 fall before the task's movement point and 10 at or after it.

The five v0.1 kinds keep their v0.1 semantics. The new kinds:

- **`crash_before_effect_commit` / `crash_after_effect_commit`.** The crash fires **once**, inside the first execution of the scheduled step that forms an effect intent, whichever executor that is. "Before" means nothing reached the ledger. "After" means the commit is durable in the ledger, but the executor dies before it sees the acknowledgement. The crashed executor loses its in-memory state, including the session events it had heard.
- **`partition_drop_request`.** The first origin→destination message is lost. The sender times out and retries the identical message once; the destination receives one copy, two were sent.
- **`partition_drop_reply`.** The destination processes the first request, but its reply is lost. The sender retries the identical request once, and the destination must answer it idempotently.
- **`partition_delay`.** The first request is held past the sender's timeout. The sender's retry is processed first; the held original arrives **late**, after the destination already acted on the retry, and must be deduplicated.

Timeouts are modelled as events, not wall-clock waits, and every retry succeeds (retry budget 1).

| Fault | B0 keep | B1 restart / B1-stable | B2-local / B2 A2A delegate | B3 relocate |
| --- | --- | --- | --- | --- |
| crash, origin executes the step (before the move) | **incomplete**: nothing recovers the task | the task moves at once; the destination restarts from step 0 and hears only events after the crash step | **incomplete**: the owner died before the movement decision | coordinator **failover** from the origin's last durable checkpoint; the destination re-executes the crashed step with the same effect ID |
| crash, destination executes the step (after the move) | – (the origin runs every step) | the destination process restarts from step 0 (no checkpoint), same owner and epoch; the events the crashed process heard are lost; fresh IDs become `…r2`, stable IDs stay the same | not reached: a tail with an effect step is refused at the move | the destination restarts from **its own** durable head and re-executes the step once |
| `partition_drop_request` | no transfer channel | the restart request is retried | the first envelope is retried | the relocation request (manifest + state) is retried |
| `partition_drop_reply` | no transfer channel | **not applicable**: the B1 model has no reply message | the first receipt is lost; the retried envelope gets the **replayed** receipt (over A2A: a new A2A task with the replayed receipt) | the coordinator's answer is lost; the re-sent request is a replay by movement ID |
| `partition_delay` | no transfer channel | the late original reaches the destination after it ran the task and is deduplicated by movement ID | the late envelope gets the replayed receipt | the late request arrives after the grant was acknowledged and is a replay |

The coordinator's grant to the destination (B3's second message) and receipts of later steps are never partitioned: each attempt has at most one partition fault.

### When a fault cannot act on a mode

A scheduled fault that did not act sets `fault_applied: false` and names the reason in `fault_not_applied_reason`. Nothing is dropped from a denominator.

| Reason | Meaning |
| --- | --- |
| `no_transfer_channel` | B0 sends nothing, so duplicates and partitions have nothing to act on |
| `no_ownership_transfer` | B0 never moves ownership, so there is no stale origin |
| `origin_remains_owner` | the delegates keep ownership on the origin, so there is no stale origin |
| `no_reply_message` | B1 and B1-stable model no reply to the restart request |
| `attempt_ended_before_fault_point` | the attempt was refused or ended incomplete before the fault point (most B2 rows: the remaining plan is not delegable) |
| `no_effect_intent_at_crash_step` | the scheduled step formed no effect intent in this mode, e.g. the effect was skipped by an active policy |
| `no_effect_committed` | `effect_ack_lost` with no commit at all |
| `mode_unavailable` | the mode is not implemented here (B4, or B2/B3 without their extra) |

## The `restart_stable_ids` baseline

B1-stable is B1 with one change: the destination re-issues each effect under the origin's deterministic ID (`<task>.e<step>`) instead of `<task>.e<step>.r1`. The PR #6 gateway then

- **deduplicates** a re-issued effect whose payload is identical (no new row), and
- **rejects** one whose payload differs (`Conflict`). B1-stable treats that as "an earlier owner already committed this effect": the ledger keeps the first payload, the step continues, and the record counts it in `effect_id_conflicts`. Nothing is overwritten.

Everything else is B1: no session context crosses, the destination hears only the events after the move, and the evaluator rubric is the v0.1 rubric. An effect-ID conflict is therefore evidence that the restarted executor's view diverged (here: it lost a mid-session redaction or path rule), even though the ledger stayed correct.

## Per-attempt record

v0.2 records carry every v0.1 field (same meaning) plus:

| Field | Meaning |
| --- | --- |
| `crash_step` | Scheduled crash step for the crash kinds, otherwise `null` |
| `fault_not_applied_reason` | See the table above; `null` when the fault acted or is `none` |
| `effect_id_conflicts` | Re-issued effects whose deterministic ID already held a different payload (B1-stable) |
| `messages_dropped`, `messages_delayed`, `retries` | Partition evidence. Dropped and delayed messages still count in `transfer_bytes` and `transfer_messages`: they left the origin. |

`steps_reexecuted` is now computed generically as Σ(executions per plan step − 1), which equals the v0.1 values for every v0.1 attempt and also counts the steps a crash forces a mode to run again. The run manifest adds `crash_step_assignment`.

## Pilot observations (harness 0.3.0, 2026-10-16, release `2408da9a…`)

There are 630 attempt records per repeat (18 tasks × 5 seeds × 7 modes). With the `a2a` and `relocation` extras installed (a2a-sdk 1.2.2; langgraph 1.2.15, langgraph-checkpoint 4.3.0, langgraph-checkpoint-sqlite 3.1.2; Python 3.14.7), **540 are implemented-mode attempts across 6 scored modes** and 90 are unavailable-mode records (B4). Repeat 1 reproduced every repeat-0 fingerprint (0 mismatches of 630 groups), two complete `--no-timing` runs produced byte-identical JSONL, and there were 0 harness errors. The timing-free `outcome_digest` was `c7760c6c025399a55f38247a2fa3c854bb09d455194cf5aff74cfa283ccfd8ca`; without the extras (B2 and B3 then `extra_not_installed`) it was `70109cfd28e0b89d39ad45a73e7951a658ae9720bef87e57411bb19c2cbb0550`, with identical rows for the four core modes. The negative fixtures gave 14 passes, 2 known gaps (the two v0.1 ones), 0 closed gaps and 0 failures out of 16.

The full generated report of the extras run, with every denominator and all 630 raw per-case rows of repeat 0, is [mobilitybench-v0.2-results.md](mobilitybench-v0.2-results.md) (produced by `report` from a `--no-timing` run, so its `ms` column is empty).

| Mode | Completed | Correct / attempts | Correct / completed | Constraints kept (completed) | Policy violations | Duplicate effects | Unexpected effects | Effect-ID conflicts | Unknown→reconciled | Stale fenced | Transfer bytes / messages | Refused | Incomplete |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B0 keep | 67/90 | 67/90 | 67/67 | 35/35 | 0 | 0 | 0 | 0 | 9→9 | 0 | 0 / 0 | 0 | 23 |
| B1 restart | 90/90 | 21/90 | 21/90 | 17/50 | 13 | 61 | 46 | 0 | 9→9 | 10 | 58 698 / 117 | 0 | 0 |
| B1-stable restart | 90/90 | 52/90 | 52/90 | 22/50 | 10 | 0 | 26 | 17 | 9→9 | 10 | 58 698 / 117 | 0 | 0 |
| B2-local delegate | 24/90 | 24/90 | 24/24 | 12/12 | 0 | 0 | 0 | 0 | 3→3 | 0 | 64 397 / 125 | 60 | 6 |
| B2 A2A delegate (extra `a2a`) | 24/90 | 24/90 | 24/24 | 12/12 | 0 | 0 | 0 | 0 | 3→3 | 0 | 66 477 / 125 | 60 | 6 |
| B3 checkpoint relocate (extra `relocation`) | 90/90 | 90/90 | 90/90 | 50/50 | 0 | 0 | 0 | 0 | 9→9 | 10 | 230 300 / 226 | 0 | 0 |
| B4 reconstruct | UNAVAILABLE | not scored (90 records) | – | – | – | – | – | – | – | – | – | – | – |

Fault-path evidence (repeat 0):

| Mode | Faults applied / attempts | Messages dropped | Messages delayed | Retries | Duplicate deliveries suppressed | Steps re-executed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B0 keep | 32/90 | 0 | 0 | 0 | 0 | 0 |
| B1 restart | 71/90 | 9 | 8 | 17 | 18 | 249 |
| B1-stable restart | 71/90 | 9 | 8 | 17 | 18 | 249 |
| B2-local delegate | 21/90 | 9 | 2 | 11 | 8 | 0 |
| B2 A2A delegate | 21/90 | 9 | 2 | 11 | 8 | 0 |
| B3 checkpoint relocate | 78/90 | 18 | 8 | 26 | 37 | 14 |

Correct / attempts by fault (repeat 0):

| Mode | none | origin_preempted | effect_ack_lost | duplicate_delivery | stale_origin_returns | crash_before_effect_commit | crash_after_effect_commit | partition_drop_request | partition_drop_reply | partition_delay |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B0 keep | 8/8 | 0/9 | 9/9 | 10/10 | 10/10 | 3/9 | 1/9 | 9/9 | 9/9 | 8/8 |
| B1 restart | 2/8 | 2/9 | 3/9 | 5/10 | 3/10 | 1/9 | 0/9 | 1/9 | 2/9 | 2/8 |
| B1-stable restart | 5/8 | 5/9 | 5/9 | 7/10 | 5/10 | 3/9 | 5/9 | 6/9 | 6/9 | 5/8 |
| B2-local delegate | 5/8 | 0/9 | 2/9 | 1/10 | 3/10 | 2/9 | 0/9 | 5/9 | 4/9 | 2/8 |
| B2 A2A delegate | 5/8 | 0/9 | 2/9 | 1/10 | 3/10 | 2/9 | 0/9 | 5/9 | 4/9 | 2/8 |
| B3 checkpoint relocate | 8/8 | 9/9 | 9/9 | 10/10 | 10/10 | 9/9 | 9/9 | 9/9 | 9/9 | 8/8 |

Faults applied / scheduled (repeat 0); the reasons for every unapplied cell are tabulated in the [results report](mobilitybench-v0.2-results.md):

| Mode | origin_preempted | effect_ack_lost | duplicate_delivery | stale_origin_returns | crash_before_effect_commit | crash_after_effect_commit | partition_drop_request | partition_drop_reply | partition_delay |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B0 keep | 9/9 | 9/9 | 0/10 | 0/10 | 6/9 | 8/9 | 0/9 | 0/9 | 0/8 |
| B1 restart | 9/9 | 9/9 | 10/10 | 10/10 | 7/9 | 9/9 | 9/9 | 0/9 | 8/8 |
| B1-stable restart | 9/9 | 9/9 | 10/10 | 10/10 | 7/9 | 9/9 | 9/9 | 0/9 | 8/8 |
| B2-local delegate | 2/9 | 3/9 | 1/10 | 0/10 | 0/9 | 4/9 | 5/9 | 4/9 | 2/8 |
| B2 A2A delegate | 2/9 | 3/9 | 1/10 | 0/10 | 0/9 | 4/9 | 5/9 | 4/9 | 2/8 |
| B3 checkpoint relocate | 9/9 | 9/9 | 10/10 | 10/10 | 6/9 | 8/9 | 9/9 | 9/9 | 8/8 |
| B4 reconstruct | 0/9 | 0/9 | 0/10 | 0/10 | 0/9 | 0/9 | 0/9 | 0/9 | 0/8 |

**What these observations support, within this interpreter, these 18 tasks and this schedule:**

1. **B1's duplicate effects come from its fresh-ID assumption, not from restarting as such.** On the same 90 attempts, B1 committed 61 duplicate effects and B1-stable none; B1-stable was correct on 52/90 instead of 21/90. Its remaining failures come from lost session context: 22/50 constraints kept, 26 unexpected effects (post-move payloads computed without the lost rules) and 17 effect-ID conflicts, where the gateway refused a divergent re-issue and kept the origin's payload. Deterministic IDs fix effect identity; they do not restore context.
2. **A mid-step crash is a recovery question, and only modes with a recovery path answer it.** B0 ended incomplete on all 14 crashes that fired. The delegates ended incomplete on their 4 (the owner died before the movement decision; a crash step after the move is never reached because such a tail is refused). B1 completed all 18 crash-scheduled attempts (16 crashes fired) but was correct on 1; a crash on the destination also restarted it from step 0 and lost the session events that process had heard (tested on `code-guard-config`). B3 was correct on all 18 crash attempts: it failed over from the origin's last durable checkpoint, or the destination resumed from its own, and each fired crash re-executed exactly one step (14 in total) without a duplicate effect, because the re-executed commit reuses the effect ID and the gateway deduplicates it. This exercises the at-least-once node re-execution that v0.1 never reached. It holds **by construction**, as B3's v0.1 result does: the checkpoint is the interpreter's complete state.
3. **One lost or late message is absorbed by every mode that has the channel.** All 82 applied partition faults completed after exactly one retry each. A lost delegation receipt was answered by a replayed receipt (`neg-lost-receipt-replay`; over A2A as a new A2A task carrying the replayed receipt), and a late original was deduplicated by movement ID in B1 and B3 and by idempotency key in the delegates. Partitions changed no correctness field for any mode: re-running each of those 82 attempts without the fault gave the same outcome, correctness, constraint, policy and effect counts (checked).
4. **A fault that cannot act is reported, not hidden.** 198 of the 540 implemented-mode attempts had a scheduled, non-`none` fault that did not act; each names its reason. For the delegates, most scheduled faults never act because the task is refused at the move (`attempt_ended_before_fault_point`).

**What they do not support:** any claim about LLM agents, real crashes (torn writes, lost fsyncs, process kills), real networks (reordering beyond one late copy, long or asymmetric partitions, timeouts), latency, cost, cross-host relocation, or the frequency of these situations in practice. The counts are deterministic consequences of the authored fixtures and schedule. No confidence intervals are reported, because repeats do not vary.

## Negative and security fixtures

The 12 v0.1 cases run unchanged under v0.2 (same expectations, same verdicts). `neg-revocation-not-at-effect` stays a known gap: it revokes with the static `Approval.revoked` flag, which the gateway never sees. Four cases are new:

| Case | Mode | Expected | Verdict class | What it shows / does not show |
| --- | --- | --- | --- | --- |
| `neg-stable-id-divergent-payload` | B1-stable | `ledger_kept_first_payload` | pass | A re-issued effect under the origin's ID with a payload built without the lost redaction is refused; the ledger keeps the origin's commit, with no duplicate or unexpected effect. The restart's output is still wrong. |
| `neg-lost-receipt-replay` | B2-local | `replayed_not_reexecuted` | pass | After the first receipt is lost, the retried envelope gets the replayed receipt, not a second execution (the test also checks the receiver audit: one execution per delegated step). |
| `neg-runtime-revocation-at-effect` | simulated gateway | `rejected` | pass | The v0.1 revocation attack with the grant revoked at runtime by a notice signed by the pinned synthetic authority ([issue #38](https://github.com/MSKazemi/agent-movement/issues/38)): the receiver denies a new handoff and the core gateway rechecks the approval at the effect commit and rejects it. It records in v0.2 the control that the frozen v0.1 case cannot see. |
| `neg-crash-zombie-commit` | B1 | `fenced` | pass | The origin was declared crashed inside its reserve step but was only paused; after the task moved, its in-flight commit with the old epoch is fenced by the gateway. It says nothing about effects outside this gateway. |

## Validity threats

- **Construct:**
  - Crashes are Python exceptions raised inside one in-process interpreter at precise points (around a single SQLite commit). Real crashes can tear writes, lose unsynced data, or die inside the transfer protocol itself; v0.2 does not crash the coordinator, the receiver or the grant handshake (issue #9's 30-row relocation fault matrix covers those for B3 alone).
  - The crash fires only inside effect steps, once per attempt, at the first execution that forms an effect intent at the scheduled step. A crash inside a pure step, or a second crash during recovery, is not exercised.
  - The recovery behaviour of each mode is a modelling choice: B0 and the delegates have no recovery path, B1's destination restarts from step 0 without a durable session log, and B3 restarts from a durable checkpoint. A real deployment could add supervisors, session logs or retries to any of them.
  - B3's mid-step recovery relies on LangGraph re-running a node whose previous run left only an error write. That was observed with langgraph 1.2.15 and the issue #9 fenced saver, not with other runtimes or versions.
  - B1-stable's "ledger wins" conflict policy is one choice among several. Real idempotency keys differ by tool: some return the stored response, some reject a mismatched request, some silently accept it. The stable ID is derived from the plan step index, which a restarted LLM agent does not naturally have.
  - Partitions act once, on the first message only, with one retry that always succeeds. Timeouts are events, not clocks. B1 models no reply message, so `partition_drop_reply` cannot act on it, and B3's grant message is never partitioned.
- **Internal:**
  - The fixtures, the schedule and the recovery semantics were authored by the project that builds the system, and the movement points and crash steps exercise its own mechanisms. Tasks are the v0.1 tasks; they are not representative.
  - Restart intake deduplication and the B2/B3 retry loops are harness code; the deduplication they rely on (gateway, receiver, coordinator) is the tested component.
  - Every attempt runs in one process with fresh SQLite files; v0.2 says nothing about multi-process contention.
- **External:** 18 tiny synthetic tasks, no model, no real tools, no network, a single machine. The B2 A2A path is loopback HTTP to a worker thread in the same process.
- **Statistical conclusion:** outcomes are deterministic, so repeats only test reproducibility, and a seed only re-assigns faults and crash steps. Each (mode, fault) cell has 8 to 10 attempts. A percentage computed from these counts describes this fixture set and schedule and nothing beyond it.
- **Security scope:** the negative fixtures test the local application profile only. Agent IDs remain unauthenticated claims, as in v0.1.

## Reproducibility checklist

1. `agent-movement bench verify --suite v0.2` reports release digest `2408da9a991d5a57c2467df17ca09247b69c3c5faa20099f3725a8210fc1fd63`; `python tools/mobilitybench_freeze.py --suite v0.2 --check` and `python tools/mobilitybench_freeze.py --check` (v0.1) both pass.
2. `agent-movement bench run --suite v0.2 --out results.jsonl` exits 0, and its stderr summary reports `harness_errors: 0` and `reproducibility.mismatched: 0`.
3. Compare the `outcome_digest` with a run **that had the same extras installed** (`run_version.extras`): `c7760c6c…` with both extras, `70109cfd…` with none. They should be identical on every supported Python (3.11+); the digests above were produced on Python 3.14.7.
4. `report --in results.jsonl` reproduces the tables above and the [results report](mobilitybench-v0.2-results.md), apart from the run manifest's environment fields and timing.
5. CI (`.github/workflows/python-smoke.yml`) runs `freeze --check --suite v0.2`, `verify` and the v0.2 smoke subset (10 tasks × 1 seed × 7 modes plus the 16 negatives) twice with `--no-timing` and requires byte-identical JSONL, in the core job on Python 3.11, 3.13 and 3.15; the extras job runs the same smoke subset with B2 and B3 scored and fails unless B4 is the only unavailable mode. `tests/test_mobilitybench_v02.py` covers the fault schedules, each fault path and the stable-ID baseline.

## Next versions

- B2 over the streaming and HTTP+JSON A2A bindings, and B4 once cross-framework reconstruction exists.
- Crashes inside pure steps and inside the transfer protocol, second crashes during recovery, and partitions of the grant and of later messages.
- The planned [multi-hop track](mobilitybench-v0.1.md#planned-multi-hop-track), which would apply these fault kinds at any hop.
