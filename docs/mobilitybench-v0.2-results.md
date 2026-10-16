# MobilityBench v0.2 report — run `358865e20aebe1c8`

> **Pilot, deterministic, LLM-free.** A scripted interpreter executed frozen synthetic tasks; effects are simulated SQLite commits. Outcomes are deterministic functions of (task, mode, fault), so repeats test reproducibility, not sampling variance: no confidence intervals or significance claims are made, and none should be inferred from these counts. Unavailable baselines are listed, not scored. See `docs/mobilitybench-v0.2.md` for rubrics and validity threats.

## Run manifest

| field | value |
| --- | --- |
| contract_version | `0.1.0-draft` |
| executor | `deterministic-interpreter-v0.1` |
| extras | `{"a2a":{"a2a-sdk":"1.2.2"},"relocation":{"langgraph":"1.2.15","langgraph-checkpoint":"4.3.0","langgraph-checkpoint-sqlite":"3.1.2"}}` |
| fixture_release_digest | `2408da9a991d5a57c2467df17ca09247b69c3c5faa20099f3725a8210fc1fd63` |
| harness_version | `0.3.0` |
| model | `none` |
| python | `3.14.7` |
| suite_version | `mobilitybench-v0.2` |
| subset | `full` |
| seeds | `1103, 2207, 3301, 4409, 5501` |
| repeats | `2` |
| tasks | 18 |
| started_at | `None` |
| outcome_digest (timing-free) | `c7760c6c025399a55f38247a2fa3c854bb09d455194cf5aff74cfa283ccfd8ca` |

## Denominators

- Attempt records (all repeats): **1260**; summary tables use repeat 0 only: **630** = 18 tasks × 5 seeds × 7 modes.
- Implemented-mode attempts (repeat 0): **540**; unavailable-mode records: **90** (not scored).
- Harness errors (all repeats): **0**.
- Security/negative cases: **16** (14 pass, 2 known gap, 0 gap closed, 0 fail).

## Baseline summary (repeat 0)

`correct` requires completed + exact output digest + all constraints + no policy violation, duplicate, unexpected or missing effect. Each fraction shows its own denominator.

| mode | baseline | status | completed | correct / attempts | correct / completed | constraints kept (completed) | policy violations | duplicate effects | unexpected effects | unknown→reconciled | stale fenced | transfer bytes | refused | incomplete | median ms |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| keep_on_origin | B0 | implemented | 67/90 | 67/90 | 67/67 | 35/35 | 0 | 0 | 0 | 9→9 | 0 | 0 | 0 | 23 | – |
| restart_on_destination | B1 | implemented | 90/90 | 21/90 | 21/90 | 17/50 | 13 | 61 | 46 | 9→9 | 10 | 58698 | 0 | 0 | – |
| restart_stable_ids | B1-stable | implemented | 90/90 | 52/90 | 52/90 | 22/50 | 10 | 0 | 26 | 9→9 | 10 | 58698 | 0 | 0 | – |
| local_delegate | B2-local | implemented | 24/90 | 24/90 | 24/24 | 12/12 | 0 | 0 | 0 | 3→3 | 0 | 64397 | 60 | 6 | – |
| a2a_delegate | B2 | implemented | 24/90 | 24/90 | 24/24 | 12/12 | 0 | 0 | 0 | 3→3 | 0 | 66477 | 60 | 6 | – |
| checkpoint_relocate | B3 | implemented | 90/90 | 90/90 | 90/90 | 50/50 | 0 | 0 | 0 | 9→9 | 10 | 230300 | 0 | 0 | – |
| cross_framework_reconstruct | B4 | **UNAVAILABLE** (not scheduled (AM-14; after issue #9)) | – | not scored (90 records) | – | – | – | – | – | – | – | – | – | – | – |

## Fault-path evidence (repeat 0)

`faults applied` counts attempts on which the scheduled fault actually acted; the others are listed with their reason under *Fault applicability*. Effect-ID conflicts are re-issued effects whose deterministic ID already held a different payload (the ledger kept the first one).

| mode | faults applied / attempts | effect-ID conflicts | messages dropped | messages delayed | retries | duplicate deliveries suppressed | steps re-executed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| keep_on_origin | 32/90 | 0 | 0 | 0 | 0 | 0 | 0 |
| restart_on_destination | 71/90 | 0 | 9 | 8 | 17 | 18 | 249 |
| restart_stable_ids | 71/90 | 17 | 9 | 8 | 17 | 18 | 249 |
| local_delegate | 21/90 | 0 | 9 | 2 | 11 | 8 | 0 |
| a2a_delegate | 21/90 | 0 | 9 | 2 | 11 | 8 | 0 |
| checkpoint_relocate | 78/90 | 0 | 18 | 8 | 26 | 37 | 14 |

## By fault (repeat 0): correct / attempts

| mode | none | origin_preempted | effect_ack_lost | duplicate_delivery | stale_origin_returns | crash_before_effect_commit | crash_after_effect_commit | partition_drop_request | partition_drop_reply | partition_delay |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| keep_on_origin | 8/8 | 0/9 | 9/9 | 10/10 | 10/10 | 3/9 | 1/9 | 9/9 | 9/9 | 8/8 |
| restart_on_destination | 2/8 | 2/9 | 3/9 | 5/10 | 3/10 | 1/9 | 0/9 | 1/9 | 2/9 | 2/8 |
| restart_stable_ids | 5/8 | 5/9 | 5/9 | 7/10 | 5/10 | 3/9 | 5/9 | 6/9 | 6/9 | 5/8 |
| local_delegate | 5/8 | 0/9 | 2/9 | 1/10 | 3/10 | 2/9 | 0/9 | 5/9 | 4/9 | 2/8 |
| a2a_delegate | 5/8 | 0/9 | 2/9 | 1/10 | 3/10 | 2/9 | 0/9 | 5/9 | 4/9 | 2/8 |
| checkpoint_relocate | 8/8 | 9/9 | 9/9 | 10/10 | 10/10 | 9/9 | 9/9 | 9/9 | 9/9 | 8/8 |

## By family (repeat 0): correct / attempts

| mode | document | coding | tools |
| --- | ---: | ---: | ---: |
| keep_on_origin | 26/30 | 17/30 | 24/30 |
| restart_on_destination | 10/30 | 6/30 | 5/30 |
| restart_stable_ids | 15/30 | 17/30 | 20/30 |
| local_delegate | 12/30 | 7/30 | 5/30 |
| a2a_delegate | 12/30 | 7/30 | 5/30 |
| checkpoint_relocate | 30/30 | 30/30 | 30/30 |

## Fault applicability (repeat 0): applied / scheduled

A fault that cannot act on a mode is reported, never silently dropped: every scheduled but unapplied fault carries a `fault_not_applied_reason` (table below).

| mode | origin_preempted | effect_ack_lost | duplicate_delivery | stale_origin_returns | crash_before_effect_commit | crash_after_effect_commit | partition_drop_request | partition_drop_reply | partition_delay |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| keep_on_origin | 9/9 | 9/9 | 0/10 | 0/10 | 6/9 | 8/9 | 0/9 | 0/9 | 0/8 |
| restart_on_destination | 9/9 | 9/9 | 10/10 | 10/10 | 7/9 | 9/9 | 9/9 | 0/9 | 8/8 |
| restart_stable_ids | 9/9 | 9/9 | 10/10 | 10/10 | 7/9 | 9/9 | 9/9 | 0/9 | 8/8 |
| local_delegate | 2/9 | 3/9 | 1/10 | 0/10 | 0/9 | 4/9 | 5/9 | 4/9 | 2/8 |
| a2a_delegate | 2/9 | 3/9 | 1/10 | 0/10 | 0/9 | 4/9 | 5/9 | 4/9 | 2/8 |
| checkpoint_relocate | 9/9 | 9/9 | 10/10 | 10/10 | 6/9 | 8/9 | 9/9 | 9/9 | 8/8 |
| cross_framework_reconstruct | 0/9 | 0/9 | 0/10 | 0/10 | 0/9 | 0/9 | 0/9 | 0/9 | 0/8 |

| mode | fault | not applied because | count |
| --- | --- | --- | ---: |
| a2a_delegate | crash_after_effect_commit | `attempt_ended_before_fault_point` | 5 |
| a2a_delegate | crash_before_effect_commit | `attempt_ended_before_fault_point` | 7 |
| a2a_delegate | crash_before_effect_commit | `no_effect_intent_at_crash_step` | 2 |
| a2a_delegate | duplicate_delivery | `attempt_ended_before_fault_point` | 9 |
| a2a_delegate | effect_ack_lost | `attempt_ended_before_fault_point` | 6 |
| a2a_delegate | origin_preempted | `attempt_ended_before_fault_point` | 7 |
| a2a_delegate | partition_delay | `attempt_ended_before_fault_point` | 6 |
| a2a_delegate | partition_drop_reply | `attempt_ended_before_fault_point` | 5 |
| a2a_delegate | partition_drop_request | `attempt_ended_before_fault_point` | 4 |
| a2a_delegate | stale_origin_returns | `origin_remains_owner` | 10 |
| checkpoint_relocate | crash_after_effect_commit | `no_effect_intent_at_crash_step` | 1 |
| checkpoint_relocate | crash_before_effect_commit | `no_effect_intent_at_crash_step` | 3 |
| cross_framework_reconstruct | crash_after_effect_commit | `mode_unavailable` | 9 |
| cross_framework_reconstruct | crash_before_effect_commit | `mode_unavailable` | 9 |
| cross_framework_reconstruct | duplicate_delivery | `mode_unavailable` | 10 |
| cross_framework_reconstruct | effect_ack_lost | `mode_unavailable` | 9 |
| cross_framework_reconstruct | origin_preempted | `mode_unavailable` | 9 |
| cross_framework_reconstruct | partition_delay | `mode_unavailable` | 8 |
| cross_framework_reconstruct | partition_drop_reply | `mode_unavailable` | 9 |
| cross_framework_reconstruct | partition_drop_request | `mode_unavailable` | 9 |
| cross_framework_reconstruct | stale_origin_returns | `mode_unavailable` | 10 |
| keep_on_origin | crash_after_effect_commit | `no_effect_intent_at_crash_step` | 1 |
| keep_on_origin | crash_before_effect_commit | `no_effect_intent_at_crash_step` | 3 |
| keep_on_origin | duplicate_delivery | `no_transfer_channel` | 10 |
| keep_on_origin | partition_delay | `no_transfer_channel` | 8 |
| keep_on_origin | partition_drop_reply | `no_transfer_channel` | 9 |
| keep_on_origin | partition_drop_request | `no_transfer_channel` | 9 |
| keep_on_origin | stale_origin_returns | `no_ownership_transfer` | 10 |
| local_delegate | crash_after_effect_commit | `attempt_ended_before_fault_point` | 5 |
| local_delegate | crash_before_effect_commit | `attempt_ended_before_fault_point` | 7 |
| local_delegate | crash_before_effect_commit | `no_effect_intent_at_crash_step` | 2 |
| local_delegate | duplicate_delivery | `attempt_ended_before_fault_point` | 9 |
| local_delegate | effect_ack_lost | `attempt_ended_before_fault_point` | 6 |
| local_delegate | origin_preempted | `attempt_ended_before_fault_point` | 7 |
| local_delegate | partition_delay | `attempt_ended_before_fault_point` | 6 |
| local_delegate | partition_drop_reply | `attempt_ended_before_fault_point` | 5 |
| local_delegate | partition_drop_request | `attempt_ended_before_fault_point` | 4 |
| local_delegate | stale_origin_returns | `origin_remains_owner` | 10 |
| restart_on_destination | crash_before_effect_commit | `no_effect_intent_at_crash_step` | 2 |
| restart_on_destination | partition_drop_reply | `no_reply_message` | 9 |
| restart_stable_ids | crash_before_effect_commit | `no_effect_intent_at_crash_step` | 2 |
| restart_stable_ids | partition_drop_reply | `no_reply_message` | 9 |

## Refusals, incomplete attempts and harness errors (repeat 0)

| mode | outcome | reason | count |
| --- | --- | --- | ---: |
| a2a_delegate | incomplete | `origin_crashed_owner_not_transferred` | 4 |
| a2a_delegate | incomplete | `origin_preempted_owner_not_transferred` | 2 |
| a2a_delegate | refused | `incompatible_state:check_contains+effect` | 10 |
| a2a_delegate | refused | `incompatible_state:effect` | 10 |
| a2a_delegate | refused | `incompatible_state:effect+extract` | 10 |
| a2a_delegate | refused | `incompatible_state:effect+lookup` | 10 |
| a2a_delegate | refused | `incompatible_state:effect+replace` | 5 |
| a2a_delegate | refused | `incompatible_state:lookup` | 5 |
| a2a_delegate | refused | `incompatible_state:reserve` | 10 |
| keep_on_origin | incomplete | `origin_crashed_no_recovery` | 14 |
| keep_on_origin | incomplete | `origin_preempted_no_transfer` | 9 |
| local_delegate | incomplete | `origin_crashed_owner_not_transferred` | 4 |
| local_delegate | incomplete | `origin_preempted_owner_not_transferred` | 2 |
| local_delegate | refused | `incompatible_state:check_contains+effect` | 10 |
| local_delegate | refused | `incompatible_state:effect` | 10 |
| local_delegate | refused | `incompatible_state:effect+extract` | 10 |
| local_delegate | refused | `incompatible_state:effect+lookup` | 10 |
| local_delegate | refused | `incompatible_state:effect+replace` | 5 |
| local_delegate | refused | `incompatible_state:lookup` | 5 |
| local_delegate | refused | `incompatible_state:reserve` | 10 |

## Unavailable baselines

An unavailable mode is never scored. `extra_not_installed:<extra>` means the run's environment lacked that optional extra (`pip install -e '.[<extra>]'`); `baseline_not_implemented` means no implementation exists.

| mode | baseline | reason | tracking | records |
| --- | --- | --- | --- | ---: |
| cross_framework_reconstruct | B4 | `baseline_not_implemented` | not scheduled (AM-14; after issue #9) | 90 |

## Negative and security fixtures

A `known_gap` reproduces a deliberately documented missing control; it is **not** a pass. `gap_closed` means the control now exists: the case must be rewritten in the next suite version.

| case | mode | questions | expected | observed | verdict |
| --- | --- | --- | --- | --- | --- |
| neg-private-restart | restart_on_destination | HQ-05 | `refused_before_transfer` | `refused_before_transfer` | **pass** |
| neg-private-delegate | local_delegate | HQ-05 | `disclosed_before_refusal` | `disclosed_before_refusal` | **known_gap** |
| neg-oversized-delegate | local_delegate | HQ-19 | `refused` | `refused` | **pass** |
| neg-canary-delegate | local_delegate | HQ-05, HQ-06 | `absent_from_records_and_audit` | `absent_from_records_and_audit` | **pass** |
| neg-forged-destination | local_delegate | HQ-03 | `denied` | `denied` | **pass** |
| neg-movement-id-reuse | local_delegate | HQ-18, HQ-19 | `denied` | `denied` | **pass** |
| neg-stale-origin | restart_on_destination | HQ-01, HQ-18 | `fenced` | `fenced` | **pass** |
| neg-effect-payload-conflict | simulated_gateway | HQ-18 | `denied` | `denied` | **pass** |
| neg-instruction-in-data | keep_on_origin | HQ-03, HQ-05 | `not_executed` | `not_executed` | **pass** |
| neg-tampered-fixture | harness | HQ-06 | `rejected` | `rejected` | **pass** |
| neg-unknown-effect | simulated_gateway | HQ-06, HQ-18 | `unknown` | `unknown` | **pass** |
| neg-revocation-not-at-effect | simulated_gateway | HQ-01, HQ-03 | `committed_without_grant_recheck` | `committed_without_grant_recheck` | **known_gap** |
| neg-runtime-revocation-at-effect | simulated_gateway | HQ-01, HQ-03 | `rejected` | `rejected` | **pass** |
| neg-stable-id-divergent-payload | restart_stable_ids | AM-04 | `ledger_kept_first_payload` | `ledger_kept_first_payload` | **pass** |
| neg-lost-receipt-replay | local_delegate | AM-04 | `replayed_not_reexecuted` | `replayed_not_reexecuted` | **pass** |
| neg-crash-zombie-commit | restart_on_destination | AM-03 | `fenced` | `fenced` | **pass** |

## Reproducibility

- Repeats: 2; (seed, task, mode) groups: 630; groups with differing outcome fingerprints: **0**.
- Fingerprints exclude wall-clock time, which is machine-dependent and not a fair cross-mode latency comparison.

## Raw per-case results (repeat 0)

| seed | task | family | mode | fault | applied | outcome | reason | correct | output | constraints | policy | dup | unexp | missing | unknown | fenced | bytes | ms | crash step | not applied because | conflicts | dropped | delayed | retries | re-executed |
| ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 1103 | doc-release-notes | document | keep_on_origin | none | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 1103 | doc-release-notes | document | restart_on_destination | none | no | completed | – | no | no | 0/1 | 0 | 1 | 1 | 0 | 0 | 0 | 584 | – | – | – | 0 | 0 | 0 | 0 | 3 |
| 1103 | doc-release-notes | document | restart_stable_ids | none | no | completed | – | no | no | 0/1 | 0 | 0 | 0 | 0 | 0 | 0 | 584 | – | – | – | 1 | 0 | 0 | 0 | 3 |
| 1103 | doc-release-notes | document | local_delegate | none | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 2139 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 1103 | doc-release-notes | document | a2a_delegate | none | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 2203 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 1103 | doc-release-notes | document | checkpoint_relocate | none | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 2078 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 1103 | doc-release-notes | document | cross_framework_reconstruct | none | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | – | – | – | – | – | – |
| 1103 | doc-meeting-summary | document | keep_on_origin | partition_drop_reply | no | completed | – | yes | yes | 2/2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_transfer_channel` | 0 | 0 | 0 | 0 | 0 |
| 1103 | doc-meeting-summary | document | restart_on_destination | partition_drop_reply | no | completed | – | no | no | 1/2 | 0 | 0 | 1 | 1 | 0 | 0 | 618 | – | – | `no_reply_message` | 0 | 0 | 0 | 0 | 2 |
| 1103 | doc-meeting-summary | document | restart_stable_ids | partition_drop_reply | no | completed | – | no | no | 1/2 | 0 | 0 | 1 | 1 | 0 | 0 | 618 | – | – | `no_reply_message` | 0 | 0 | 0 | 0 | 2 |
| 1103 | doc-meeting-summary | document | local_delegate | partition_drop_reply | no | refused | `incompatible_state:effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 1103 | doc-meeting-summary | document | a2a_delegate | partition_drop_reply | no | refused | `incompatible_state:effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 1103 | doc-meeting-summary | document | checkpoint_relocate | partition_drop_reply | yes | completed | – | yes | yes | 2/2 | 0 | 0 | 0 | 0 | 0 | 0 | 3935 | – | – | – | 0 | 1 | 0 | 1 | 0 |
| 1103 | doc-meeting-summary | document | cross_framework_reconstruct | partition_drop_reply | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 1103 | doc-policy-digest | document | keep_on_origin | duplicate_delivery | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_transfer_channel` | 0 | 0 | 0 | 0 | 0 |
| 1103 | doc-policy-digest | document | restart_on_destination | duplicate_delivery | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 910 | – | – | – | 0 | 0 | 0 | 0 | 1 |
| 1103 | doc-policy-digest | document | restart_stable_ids | duplicate_delivery | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 910 | – | – | – | 0 | 0 | 0 | 0 | 1 |
| 1103 | doc-policy-digest | document | local_delegate | duplicate_delivery | no | refused | `incompatible_state:effect+extract` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 1103 | doc-policy-digest | document | a2a_delegate | duplicate_delivery | no | refused | `incompatible_state:effect+extract` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 1103 | doc-policy-digest | document | checkpoint_relocate | duplicate_delivery | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 3566 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 1103 | doc-policy-digest | document | cross_framework_reconstruct | duplicate_delivery | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 1103 | doc-incident-brief | document | keep_on_origin | partition_drop_reply | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_transfer_channel` | 0 | 0 | 0 | 0 | 0 |
| 1103 | doc-incident-brief | document | restart_on_destination | partition_drop_reply | no | completed | – | no | no | 0/1 | 0 | 1 | 1 | 0 | 0 | 0 | 580 | – | – | `no_reply_message` | 0 | 0 | 0 | 0 | 3 |
| 1103 | doc-incident-brief | document | restart_stable_ids | partition_drop_reply | no | completed | – | no | no | 0/1 | 0 | 0 | 0 | 0 | 0 | 0 | 580 | – | – | `no_reply_message` | 1 | 0 | 0 | 0 | 3 |
| 1103 | doc-incident-brief | document | local_delegate | partition_drop_reply | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 3214 | – | – | – | 0 | 1 | 0 | 1 | 0 |
| 1103 | doc-incident-brief | document | a2a_delegate | partition_drop_reply | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 3310 | – | – | – | 0 | 1 | 0 | 1 | 0 |
| 1103 | doc-incident-brief | document | checkpoint_relocate | partition_drop_reply | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 3975 | – | – | – | 0 | 1 | 0 | 1 | 0 |
| 1103 | doc-incident-brief | document | cross_framework_reconstruct | partition_drop_reply | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 1103 | doc-faq-merge | document | keep_on_origin | stale_origin_returns | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_ownership_transfer` | 0 | 0 | 0 | 0 | 0 |
| 1103 | doc-faq-merge | document | restart_on_destination | stale_origin_returns | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 1 | 524 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 1103 | doc-faq-merge | document | restart_stable_ids | stale_origin_returns | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 1 | 524 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 1103 | doc-faq-merge | document | local_delegate | stale_origin_returns | no | refused | `incompatible_state:effect+extract` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `origin_remains_owner` | 0 | 0 | 0 | 0 | 0 |
| 1103 | doc-faq-merge | document | a2a_delegate | stale_origin_returns | no | refused | `incompatible_state:effect+extract` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `origin_remains_owner` | 0 | 0 | 0 | 0 | 0 |
| 1103 | doc-faq-merge | document | checkpoint_relocate | stale_origin_returns | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 1 | 1876 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 1103 | doc-faq-merge | document | cross_framework_reconstruct | stale_origin_returns | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 1103 | doc-handbook-excerpt | document | keep_on_origin | crash_after_effect_commit | yes | incomplete | `origin_crashed_no_recovery` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 1 | – | 0 | 0 | 0 | 0 | 0 |
| 1103 | doc-handbook-excerpt | document | restart_on_destination | crash_after_effect_commit | yes | completed | – | no | yes | 0/1 | 0 | 1 | 1 | 0 | 0 | 0 | 576 | – | 1 | – | 0 | 0 | 0 | 0 | 2 |
| 1103 | doc-handbook-excerpt | document | restart_stable_ids | crash_after_effect_commit | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 576 | – | 1 | – | 1 | 0 | 0 | 0 | 2 |
| 1103 | doc-handbook-excerpt | document | local_delegate | crash_after_effect_commit | yes | incomplete | `origin_crashed_owner_not_transferred` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 1 | – | 0 | 0 | 0 | 0 | 0 |
| 1103 | doc-handbook-excerpt | document | a2a_delegate | crash_after_effect_commit | yes | incomplete | `origin_crashed_owner_not_transferred` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 1 | – | 0 | 0 | 0 | 0 | 0 |
| 1103 | doc-handbook-excerpt | document | checkpoint_relocate | crash_after_effect_commit | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 1951 | – | 1 | – | 0 | 0 | 0 | 0 | 1 |
| 1103 | doc-handbook-excerpt | document | cross_framework_reconstruct | crash_after_effect_commit | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | 1 | `mode_unavailable` | – | – | – | – | – |
| 1103 | code-rename-helper | coding | keep_on_origin | origin_preempted | yes | incomplete | `origin_preempted_no_transfer` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 1103 | code-rename-helper | coding | restart_on_destination | origin_preempted | yes | completed | – | no | no | 0/1 | 0 | 0 | 1 | 1 | 0 | 0 | 579 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 1103 | code-rename-helper | coding | restart_stable_ids | origin_preempted | yes | completed | – | no | no | 0/1 | 0 | 0 | 1 | 1 | 0 | 0 | 579 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 1103 | code-rename-helper | coding | local_delegate | origin_preempted | no | refused | `incompatible_state:check_contains+effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 1103 | code-rename-helper | coding | a2a_delegate | origin_preempted | no | refused | `incompatible_state:check_contains+effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 1103 | code-rename-helper | coding | checkpoint_relocate | origin_preempted | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 1941 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 1103 | code-rename-helper | coding | cross_framework_reconstruct | origin_preempted | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 1103 | code-add-docstring | coding | keep_on_origin | none | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 1103 | code-add-docstring | coding | restart_on_destination | none | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 599 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 1103 | code-add-docstring | coding | restart_stable_ids | none | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 599 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 1103 | code-add-docstring | coding | local_delegate | none | no | refused | `incompatible_state:effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 1103 | code-add-docstring | coding | a2a_delegate | none | no | refused | `incompatible_state:effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 1103 | code-add-docstring | coding | checkpoint_relocate | none | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 1909 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 1103 | code-add-docstring | coding | cross_framework_reconstruct | none | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | – | – | – | – | – | – |
| 1103 | code-version-bump | coding | keep_on_origin | stale_origin_returns | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_ownership_transfer` | 0 | 0 | 0 | 0 | 0 |
| 1103 | code-version-bump | coding | restart_on_destination | stale_origin_returns | yes | completed | – | no | yes | 0/0 | 0 | 1 | 0 | 0 | 0 | 1 | 538 | – | – | – | 0 | 0 | 0 | 0 | 3 |
| 1103 | code-version-bump | coding | restart_stable_ids | stale_origin_returns | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 1 | 538 | – | – | – | 0 | 0 | 0 | 0 | 3 |
| 1103 | code-version-bump | coding | local_delegate | stale_origin_returns | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 1915 | – | – | `origin_remains_owner` | 0 | 0 | 0 | 0 | 0 |
| 1103 | code-version-bump | coding | a2a_delegate | stale_origin_returns | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 1979 | – | – | `origin_remains_owner` | 0 | 0 | 0 | 0 | 0 |
| 1103 | code-version-bump | coding | checkpoint_relocate | stale_origin_returns | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 1 | 1889 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 1103 | code-version-bump | coding | cross_framework_reconstruct | stale_origin_returns | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 1103 | code-guard-config | coding | keep_on_origin | crash_before_effect_commit | yes | incomplete | `origin_crashed_no_recovery` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 4 | – | 0 | 0 | 0 | 0 | 0 |
| 1103 | code-guard-config | coding | restart_on_destination | crash_before_effect_commit | yes | completed | – | no | no | 0/1 | 0 | 0 | 1 | 1 | 0 | 0 | 547 | – | 4 | – | 0 | 0 | 0 | 0 | 6 |
| 1103 | code-guard-config | coding | restart_stable_ids | crash_before_effect_commit | yes | completed | – | no | no | 0/1 | 0 | 0 | 1 | 1 | 0 | 0 | 547 | – | 4 | – | 0 | 0 | 0 | 0 | 6 |
| 1103 | code-guard-config | coding | local_delegate | crash_before_effect_commit | no | refused | `incompatible_state:effect+replace` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 4 | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 1103 | code-guard-config | coding | a2a_delegate | crash_before_effect_commit | no | refused | `incompatible_state:effect+replace` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 4 | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 1103 | code-guard-config | coding | checkpoint_relocate | crash_before_effect_commit | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 1815 | – | 4 | – | 0 | 0 | 0 | 0 | 1 |
| 1103 | code-guard-config | coding | cross_framework_reconstruct | crash_before_effect_commit | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | 4 | `mode_unavailable` | – | – | – | – | – |
| 1103 | code-line-limit | coding | keep_on_origin | partition_delay | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_transfer_channel` | 0 | 0 | 0 | 0 | 0 |
| 1103 | code-line-limit | coding | restart_on_destination | partition_delay | yes | completed | – | no | no | 0/1 | 0 | 0 | 1 | 1 | 0 | 0 | 1206 | – | – | – | 0 | 0 | 1 | 1 | 2 |
| 1103 | code-line-limit | coding | restart_stable_ids | partition_delay | yes | completed | – | no | no | 0/1 | 0 | 0 | 1 | 1 | 0 | 0 | 1206 | – | – | – | 0 | 0 | 1 | 1 | 2 |
| 1103 | code-line-limit | coding | local_delegate | partition_delay | no | refused | `incompatible_state:check_contains+effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 1103 | code-line-limit | coding | a2a_delegate | partition_delay | no | refused | `incompatible_state:check_contains+effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 1103 | code-line-limit | coding | checkpoint_relocate | partition_delay | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 3609 | – | – | – | 0 | 0 | 1 | 1 | 0 |
| 1103 | code-line-limit | coding | cross_framework_reconstruct | partition_delay | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 1103 | code-test-fixture | coding | keep_on_origin | crash_after_effect_commit | yes | incomplete | `origin_crashed_no_recovery` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 1 | – | 0 | 0 | 0 | 0 | 0 |
| 1103 | code-test-fixture | coding | restart_on_destination | crash_after_effect_commit | yes | completed | – | no | yes | 0/0 | 0 | 1 | 0 | 0 | 0 | 0 | 415 | – | 1 | – | 0 | 0 | 0 | 0 | 2 |
| 1103 | code-test-fixture | coding | restart_stable_ids | crash_after_effect_commit | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 415 | – | 1 | – | 0 | 0 | 0 | 0 | 2 |
| 1103 | code-test-fixture | coding | local_delegate | crash_after_effect_commit | yes | incomplete | `origin_crashed_owner_not_transferred` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 1 | – | 0 | 0 | 0 | 0 | 0 |
| 1103 | code-test-fixture | coding | a2a_delegate | crash_after_effect_commit | yes | incomplete | `origin_crashed_owner_not_transferred` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 1 | – | 0 | 0 | 0 | 0 | 0 |
| 1103 | code-test-fixture | coding | checkpoint_relocate | crash_after_effect_commit | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 1758 | – | 1 | – | 0 | 0 | 0 | 0 | 1 |
| 1103 | code-test-fixture | coding | cross_framework_reconstruct | crash_after_effect_commit | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | 1 | `mode_unavailable` | – | – | – | – | – |
| 1103 | tools-restock-order | tools | keep_on_origin | crash_before_effect_commit | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | 2 | `no_effect_intent_at_crash_step` | 0 | 0 | 0 | 0 | 0 |
| 1103 | tools-restock-order | tools | restart_on_destination | crash_before_effect_commit | yes | completed | – | no | no | 0/0 | 1 | 2 | 1 | 0 | 0 | 0 | 414 | – | 2 | – | 0 | 0 | 0 | 0 | 6 |
| 1103 | tools-restock-order | tools | restart_stable_ids | crash_before_effect_commit | yes | completed | – | no | no | 0/0 | 1 | 0 | 1 | 0 | 0 | 0 | 414 | – | 2 | – | 0 | 0 | 0 | 0 | 6 |
| 1103 | tools-restock-order | tools | local_delegate | crash_before_effect_commit | no | refused | `incompatible_state:lookup` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 2 | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 1103 | tools-restock-order | tools | a2a_delegate | crash_before_effect_commit | no | refused | `incompatible_state:lookup` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 2 | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 1103 | tools-restock-order | tools | checkpoint_relocate | crash_before_effect_commit | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 1785 | – | 2 | `no_effect_intent_at_crash_step` | 0 | 0 | 0 | 0 | 0 |
| 1103 | tools-restock-order | tools | cross_framework_reconstruct | crash_before_effect_commit | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | 2 | `mode_unavailable` | – | – | – | – | – |
| 1103 | tools-travel-booking | tools | keep_on_origin | partition_delay | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_transfer_channel` | 0 | 0 | 0 | 0 | 0 |
| 1103 | tools-travel-booking | tools | restart_on_destination | partition_delay | yes | completed | – | no | yes | 0/0 | 0 | 1 | 0 | 0 | 0 | 0 | 754 | – | – | – | 0 | 0 | 1 | 1 | 1 |
| 1103 | tools-travel-booking | tools | restart_stable_ids | partition_delay | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 754 | – | – | – | 0 | 0 | 1 | 1 | 1 |
| 1103 | tools-travel-booking | tools | local_delegate | partition_delay | no | refused | `incompatible_state:effect+lookup` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 1103 | tools-travel-booking | tools | a2a_delegate | partition_delay | no | refused | `incompatible_state:effect+lookup` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 1103 | tools-travel-booking | tools | checkpoint_relocate | partition_delay | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 3221 | – | – | – | 0 | 0 | 1 | 1 | 0 |
| 1103 | tools-travel-booking | tools | cross_framework_reconstruct | partition_delay | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 1103 | tools-ticket-triage | tools | keep_on_origin | partition_drop_request | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_transfer_channel` | 0 | 0 | 0 | 0 | 0 |
| 1103 | tools-ticket-triage | tools | restart_on_destination | partition_drop_request | yes | completed | – | no | yes | 0/0 | 0 | 1 | 0 | 0 | 0 | 0 | 1022 | – | – | – | 0 | 1 | 0 | 1 | 3 |
| 1103 | tools-ticket-triage | tools | restart_stable_ids | partition_drop_request | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 1022 | – | – | – | 0 | 1 | 0 | 1 | 3 |
| 1103 | tools-ticket-triage | tools | local_delegate | partition_drop_request | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 2565 | – | – | – | 0 | 1 | 0 | 1 | 0 |
| 1103 | tools-ticket-triage | tools | a2a_delegate | partition_drop_request | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 2661 | – | – | – | 0 | 1 | 0 | 1 | 0 |
| 1103 | tools-ticket-triage | tools | checkpoint_relocate | partition_drop_request | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 3465 | – | – | – | 0 | 1 | 0 | 1 | 0 |
| 1103 | tools-ticket-triage | tools | cross_framework_reconstruct | partition_drop_request | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 1103 | tools-calendar-hold | tools | keep_on_origin | duplicate_delivery | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_transfer_channel` | 0 | 0 | 0 | 0 | 0 |
| 1103 | tools-calendar-hold | tools | restart_on_destination | duplicate_delivery | yes | completed | – | no | yes | 0/0 | 0 | 1 | 0 | 0 | 0 | 0 | 806 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 1103 | tools-calendar-hold | tools | restart_stable_ids | duplicate_delivery | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 806 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 1103 | tools-calendar-hold | tools | local_delegate | duplicate_delivery | no | refused | `incompatible_state:effect+lookup` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 1103 | tools-calendar-hold | tools | a2a_delegate | duplicate_delivery | no | refused | `incompatible_state:effect+lookup` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 1103 | tools-calendar-hold | tools | checkpoint_relocate | duplicate_delivery | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 3420 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 1103 | tools-calendar-hold | tools | cross_framework_reconstruct | duplicate_delivery | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 1103 | tools-refund-sim | tools | keep_on_origin | partition_drop_request | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_transfer_channel` | 0 | 0 | 0 | 0 | 0 |
| 1103 | tools-refund-sim | tools | restart_on_destination | partition_drop_request | yes | completed | – | no | no | 0/0 | 1 | 1 | 1 | 0 | 0 | 0 | 986 | – | – | – | 0 | 1 | 0 | 1 | 3 |
| 1103 | tools-refund-sim | tools | restart_stable_ids | partition_drop_request | yes | completed | – | no | no | 0/0 | 1 | 0 | 1 | 0 | 0 | 0 | 986 | – | – | – | 0 | 1 | 0 | 1 | 3 |
| 1103 | tools-refund-sim | tools | local_delegate | partition_drop_request | no | refused | `incompatible_state:reserve` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 1103 | tools-refund-sim | tools | a2a_delegate | partition_drop_request | no | refused | `incompatible_state:reserve` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 1103 | tools-refund-sim | tools | checkpoint_relocate | partition_drop_request | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 3493 | – | – | – | 0 | 1 | 0 | 1 | 0 |
| 1103 | tools-refund-sim | tools | cross_framework_reconstruct | partition_drop_request | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 1103 | tools-inventory-audit | tools | keep_on_origin | effect_ack_lost | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 1103 | tools-inventory-audit | tools | restart_on_destination | effect_ack_lost | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 1 | 0 | 360 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 1103 | tools-inventory-audit | tools | restart_stable_ids | effect_ack_lost | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 1 | 0 | 360 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 1103 | tools-inventory-audit | tools | local_delegate | effect_ack_lost | no | refused | `incompatible_state:reserve` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 1103 | tools-inventory-audit | tools | a2a_delegate | effect_ack_lost | no | refused | `incompatible_state:reserve` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 1103 | tools-inventory-audit | tools | checkpoint_relocate | effect_ack_lost | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 1 | 0 | 1745 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 1103 | tools-inventory-audit | tools | cross_framework_reconstruct | effect_ack_lost | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 2207 | doc-release-notes | document | keep_on_origin | partition_drop_request | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_transfer_channel` | 0 | 0 | 0 | 0 | 0 |
| 2207 | doc-release-notes | document | restart_on_destination | partition_drop_request | yes | completed | – | no | no | 0/1 | 0 | 1 | 1 | 0 | 0 | 0 | 1168 | – | – | – | 0 | 1 | 0 | 1 | 3 |
| 2207 | doc-release-notes | document | restart_stable_ids | partition_drop_request | yes | completed | – | no | no | 0/1 | 0 | 0 | 0 | 0 | 0 | 0 | 1168 | – | – | – | 1 | 1 | 0 | 1 | 3 |
| 2207 | doc-release-notes | document | local_delegate | partition_drop_request | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 2750 | – | – | – | 0 | 1 | 0 | 1 | 0 |
| 2207 | doc-release-notes | document | a2a_delegate | partition_drop_request | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 2846 | – | – | – | 0 | 1 | 0 | 1 | 0 |
| 2207 | doc-release-notes | document | checkpoint_relocate | partition_drop_request | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 3981 | – | – | – | 0 | 1 | 0 | 1 | 0 |
| 2207 | doc-release-notes | document | cross_framework_reconstruct | partition_drop_request | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 2207 | doc-meeting-summary | document | keep_on_origin | crash_before_effect_commit | yes | incomplete | `origin_crashed_no_recovery` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 3 | – | 0 | 0 | 0 | 0 | 0 |
| 2207 | doc-meeting-summary | document | restart_on_destination | crash_before_effect_commit | yes | completed | – | no | no | 1/2 | 0 | 0 | 1 | 1 | 0 | 0 | 618 | – | 3 | – | 0 | 0 | 0 | 0 | 6 |
| 2207 | doc-meeting-summary | document | restart_stable_ids | crash_before_effect_commit | yes | completed | – | no | no | 1/2 | 0 | 0 | 1 | 1 | 0 | 0 | 618 | – | 3 | – | 0 | 0 | 0 | 0 | 6 |
| 2207 | doc-meeting-summary | document | local_delegate | crash_before_effect_commit | no | refused | `incompatible_state:effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 3 | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 2207 | doc-meeting-summary | document | a2a_delegate | crash_before_effect_commit | no | refused | `incompatible_state:effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 3 | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 2207 | doc-meeting-summary | document | checkpoint_relocate | crash_before_effect_commit | yes | completed | – | yes | yes | 2/2 | 0 | 0 | 0 | 0 | 0 | 0 | 2057 | – | 3 | – | 0 | 0 | 0 | 0 | 1 |
| 2207 | doc-meeting-summary | document | cross_framework_reconstruct | crash_before_effect_commit | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | 3 | `mode_unavailable` | – | – | – | – | – |
| 2207 | doc-policy-digest | document | keep_on_origin | duplicate_delivery | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_transfer_channel` | 0 | 0 | 0 | 0 | 0 |
| 2207 | doc-policy-digest | document | restart_on_destination | duplicate_delivery | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 910 | – | – | – | 0 | 0 | 0 | 0 | 1 |
| 2207 | doc-policy-digest | document | restart_stable_ids | duplicate_delivery | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 910 | – | – | – | 0 | 0 | 0 | 0 | 1 |
| 2207 | doc-policy-digest | document | local_delegate | duplicate_delivery | no | refused | `incompatible_state:effect+extract` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 2207 | doc-policy-digest | document | a2a_delegate | duplicate_delivery | no | refused | `incompatible_state:effect+extract` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 2207 | doc-policy-digest | document | checkpoint_relocate | duplicate_delivery | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 3566 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 2207 | doc-policy-digest | document | cross_framework_reconstruct | duplicate_delivery | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 2207 | doc-incident-brief | document | keep_on_origin | stale_origin_returns | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_ownership_transfer` | 0 | 0 | 0 | 0 | 0 |
| 2207 | doc-incident-brief | document | restart_on_destination | stale_origin_returns | yes | completed | – | no | no | 0/1 | 0 | 1 | 1 | 0 | 0 | 1 | 580 | – | – | – | 0 | 0 | 0 | 0 | 3 |
| 2207 | doc-incident-brief | document | restart_stable_ids | stale_origin_returns | yes | completed | – | no | no | 0/1 | 0 | 0 | 0 | 0 | 0 | 1 | 580 | – | – | – | 1 | 0 | 0 | 0 | 3 |
| 2207 | doc-incident-brief | document | local_delegate | stale_origin_returns | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 2167 | – | – | `origin_remains_owner` | 0 | 0 | 0 | 0 | 0 |
| 2207 | doc-incident-brief | document | a2a_delegate | stale_origin_returns | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 2231 | – | – | `origin_remains_owner` | 0 | 0 | 0 | 0 | 0 |
| 2207 | doc-incident-brief | document | checkpoint_relocate | stale_origin_returns | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 1 | 2076 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 2207 | doc-incident-brief | document | cross_framework_reconstruct | stale_origin_returns | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 2207 | doc-faq-merge | document | keep_on_origin | partition_delay | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_transfer_channel` | 0 | 0 | 0 | 0 | 0 |
| 2207 | doc-faq-merge | document | restart_on_destination | partition_delay | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 1048 | – | – | – | 0 | 0 | 1 | 1 | 2 |
| 2207 | doc-faq-merge | document | restart_stable_ids | partition_delay | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 1048 | – | – | – | 0 | 0 | 1 | 1 | 2 |
| 2207 | doc-faq-merge | document | local_delegate | partition_delay | no | refused | `incompatible_state:effect+extract` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 2207 | doc-faq-merge | document | a2a_delegate | partition_delay | no | refused | `incompatible_state:effect+extract` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 2207 | doc-faq-merge | document | checkpoint_relocate | partition_delay | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 3585 | – | – | – | 0 | 0 | 1 | 1 | 0 |
| 2207 | doc-faq-merge | document | cross_framework_reconstruct | partition_delay | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 2207 | doc-handbook-excerpt | document | keep_on_origin | origin_preempted | yes | incomplete | `origin_preempted_no_transfer` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 2207 | doc-handbook-excerpt | document | restart_on_destination | origin_preempted | yes | completed | – | no | yes | 0/1 | 0 | 1 | 1 | 0 | 0 | 0 | 576 | – | – | – | 0 | 0 | 0 | 0 | 3 |
| 2207 | doc-handbook-excerpt | document | restart_stable_ids | origin_preempted | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 576 | – | – | – | 1 | 0 | 0 | 0 | 3 |
| 2207 | doc-handbook-excerpt | document | local_delegate | origin_preempted | yes | incomplete | `origin_preempted_owner_not_transferred` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 2207 | doc-handbook-excerpt | document | a2a_delegate | origin_preempted | yes | incomplete | `origin_preempted_owner_not_transferred` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 2207 | doc-handbook-excerpt | document | checkpoint_relocate | origin_preempted | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 2080 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 2207 | doc-handbook-excerpt | document | cross_framework_reconstruct | origin_preempted | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 2207 | code-rename-helper | coding | keep_on_origin | stale_origin_returns | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_ownership_transfer` | 0 | 0 | 0 | 0 | 0 |
| 2207 | code-rename-helper | coding | restart_on_destination | stale_origin_returns | yes | completed | – | no | no | 0/1 | 0 | 0 | 1 | 1 | 0 | 1 | 579 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 2207 | code-rename-helper | coding | restart_stable_ids | stale_origin_returns | yes | completed | – | no | no | 0/1 | 0 | 0 | 1 | 1 | 0 | 1 | 579 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 2207 | code-rename-helper | coding | local_delegate | stale_origin_returns | no | refused | `incompatible_state:check_contains+effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `origin_remains_owner` | 0 | 0 | 0 | 0 | 0 |
| 2207 | code-rename-helper | coding | a2a_delegate | stale_origin_returns | no | refused | `incompatible_state:check_contains+effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `origin_remains_owner` | 0 | 0 | 0 | 0 | 0 |
| 2207 | code-rename-helper | coding | checkpoint_relocate | stale_origin_returns | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 1 | 1944 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 2207 | code-rename-helper | coding | cross_framework_reconstruct | stale_origin_returns | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 2207 | code-add-docstring | coding | keep_on_origin | effect_ack_lost | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 2207 | code-add-docstring | coding | restart_on_destination | effect_ack_lost | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 1 | 0 | 599 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 2207 | code-add-docstring | coding | restart_stable_ids | effect_ack_lost | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 1 | 0 | 599 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 2207 | code-add-docstring | coding | local_delegate | effect_ack_lost | no | refused | `incompatible_state:effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 2207 | code-add-docstring | coding | a2a_delegate | effect_ack_lost | no | refused | `incompatible_state:effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 2207 | code-add-docstring | coding | checkpoint_relocate | effect_ack_lost | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 1 | 0 | 1909 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 2207 | code-add-docstring | coding | cross_framework_reconstruct | effect_ack_lost | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 2207 | code-version-bump | coding | keep_on_origin | none | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 2207 | code-version-bump | coding | restart_on_destination | none | no | completed | – | no | yes | 0/0 | 0 | 1 | 0 | 0 | 0 | 0 | 538 | – | – | – | 0 | 0 | 0 | 0 | 3 |
| 2207 | code-version-bump | coding | restart_stable_ids | none | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 538 | – | – | – | 0 | 0 | 0 | 0 | 3 |
| 2207 | code-version-bump | coding | local_delegate | none | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 1915 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 2207 | code-version-bump | coding | a2a_delegate | none | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 1979 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 2207 | code-version-bump | coding | checkpoint_relocate | none | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 1889 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 2207 | code-version-bump | coding | cross_framework_reconstruct | none | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | – | – | – | – | – | – |
| 2207 | code-guard-config | coding | keep_on_origin | crash_after_effect_commit | yes | incomplete | `origin_crashed_no_recovery` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 4 | – | 0 | 0 | 0 | 0 | 0 |
| 2207 | code-guard-config | coding | restart_on_destination | crash_after_effect_commit | yes | completed | – | no | no | 0/1 | 0 | 1 | 1 | 0 | 0 | 0 | 547 | – | 4 | – | 0 | 0 | 0 | 0 | 6 |
| 2207 | code-guard-config | coding | restart_stable_ids | crash_after_effect_commit | yes | completed | – | no | no | 0/1 | 0 | 0 | 0 | 0 | 0 | 0 | 547 | – | 4 | – | 1 | 0 | 0 | 0 | 6 |
| 2207 | code-guard-config | coding | local_delegate | crash_after_effect_commit | no | refused | `incompatible_state:effect+replace` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 4 | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 2207 | code-guard-config | coding | a2a_delegate | crash_after_effect_commit | no | refused | `incompatible_state:effect+replace` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 4 | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 2207 | code-guard-config | coding | checkpoint_relocate | crash_after_effect_commit | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 1815 | – | 4 | – | 0 | 0 | 0 | 0 | 1 |
| 2207 | code-guard-config | coding | cross_framework_reconstruct | crash_after_effect_commit | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | 4 | `mode_unavailable` | – | – | – | – | – |
| 2207 | code-line-limit | coding | keep_on_origin | partition_drop_reply | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_transfer_channel` | 0 | 0 | 0 | 0 | 0 |
| 2207 | code-line-limit | coding | restart_on_destination | partition_drop_reply | no | completed | – | no | no | 0/1 | 0 | 0 | 1 | 1 | 0 | 0 | 603 | – | – | `no_reply_message` | 0 | 0 | 0 | 0 | 2 |
| 2207 | code-line-limit | coding | restart_stable_ids | partition_drop_reply | no | completed | – | no | no | 0/1 | 0 | 0 | 1 | 1 | 0 | 0 | 603 | – | – | `no_reply_message` | 0 | 0 | 0 | 0 | 2 |
| 2207 | code-line-limit | coding | local_delegate | partition_drop_reply | no | refused | `incompatible_state:check_contains+effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 2207 | code-line-limit | coding | a2a_delegate | partition_drop_reply | no | refused | `incompatible_state:check_contains+effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 2207 | code-line-limit | coding | checkpoint_relocate | partition_drop_reply | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 3609 | – | – | – | 0 | 1 | 0 | 1 | 0 |
| 2207 | code-line-limit | coding | cross_framework_reconstruct | partition_drop_reply | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 2207 | code-test-fixture | coding | keep_on_origin | none | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 2207 | code-test-fixture | coding | restart_on_destination | none | no | completed | – | no | yes | 0/0 | 0 | 1 | 0 | 0 | 0 | 0 | 415 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 2207 | code-test-fixture | coding | restart_stable_ids | none | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 415 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 2207 | code-test-fixture | coding | local_delegate | none | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 2892 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 2207 | code-test-fixture | coding | a2a_delegate | none | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 2988 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 2207 | code-test-fixture | coding | checkpoint_relocate | none | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 1747 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 2207 | code-test-fixture | coding | cross_framework_reconstruct | none | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | – | – | – | – | – | – |
| 2207 | tools-restock-order | tools | keep_on_origin | origin_preempted | yes | incomplete | `origin_preempted_no_transfer` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 2207 | tools-restock-order | tools | restart_on_destination | origin_preempted | yes | completed | – | no | no | 0/0 | 1 | 1 | 1 | 0 | 0 | 0 | 414 | – | – | – | 0 | 0 | 0 | 0 | 3 |
| 2207 | tools-restock-order | tools | restart_stable_ids | origin_preempted | yes | completed | – | no | no | 0/0 | 1 | 0 | 1 | 0 | 0 | 0 | 414 | – | – | – | 0 | 0 | 0 | 0 | 3 |
| 2207 | tools-restock-order | tools | local_delegate | origin_preempted | no | refused | `incompatible_state:lookup` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 2207 | tools-restock-order | tools | a2a_delegate | origin_preempted | no | refused | `incompatible_state:lookup` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 2207 | tools-restock-order | tools | checkpoint_relocate | origin_preempted | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 1782 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 2207 | tools-restock-order | tools | cross_framework_reconstruct | origin_preempted | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 2207 | tools-travel-booking | tools | keep_on_origin | effect_ack_lost | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 2207 | tools-travel-booking | tools | restart_on_destination | effect_ack_lost | yes | completed | – | no | yes | 0/0 | 0 | 1 | 0 | 0 | 1 | 0 | 377 | – | – | – | 0 | 0 | 0 | 0 | 1 |
| 2207 | tools-travel-booking | tools | restart_stable_ids | effect_ack_lost | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 1 | 0 | 377 | – | – | – | 0 | 0 | 0 | 0 | 1 |
| 2207 | tools-travel-booking | tools | local_delegate | effect_ack_lost | yes | refused | `incompatible_state:effect+lookup` | – | – | – | 0 | 0 | 0 | – | 1 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 2207 | tools-travel-booking | tools | a2a_delegate | effect_ack_lost | yes | refused | `incompatible_state:effect+lookup` | – | – | – | 0 | 0 | 0 | – | 1 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 2207 | tools-travel-booking | tools | checkpoint_relocate | effect_ack_lost | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 1 | 0 | 1701 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 2207 | tools-travel-booking | tools | cross_framework_reconstruct | effect_ack_lost | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 2207 | tools-ticket-triage | tools | keep_on_origin | partition_drop_reply | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_transfer_channel` | 0 | 0 | 0 | 0 | 0 |
| 2207 | tools-ticket-triage | tools | restart_on_destination | partition_drop_reply | no | completed | – | no | yes | 0/0 | 0 | 1 | 0 | 0 | 0 | 0 | 511 | – | – | `no_reply_message` | 0 | 0 | 0 | 0 | 3 |
| 2207 | tools-ticket-triage | tools | restart_stable_ids | partition_drop_reply | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 511 | – | – | `no_reply_message` | 0 | 0 | 0 | 0 | 3 |
| 2207 | tools-ticket-triage | tools | local_delegate | partition_drop_reply | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 3053 | – | – | – | 0 | 1 | 0 | 1 | 0 |
| 2207 | tools-ticket-triage | tools | a2a_delegate | partition_drop_reply | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 3149 | – | – | – | 0 | 1 | 0 | 1 | 0 |
| 2207 | tools-ticket-triage | tools | checkpoint_relocate | partition_drop_reply | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 3465 | – | – | – | 0 | 1 | 0 | 1 | 0 |
| 2207 | tools-ticket-triage | tools | cross_framework_reconstruct | partition_drop_reply | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 2207 | tools-calendar-hold | tools | keep_on_origin | partition_delay | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_transfer_channel` | 0 | 0 | 0 | 0 | 0 |
| 2207 | tools-calendar-hold | tools | restart_on_destination | partition_delay | yes | completed | – | no | yes | 0/0 | 0 | 1 | 0 | 0 | 0 | 0 | 806 | – | – | – | 0 | 0 | 1 | 1 | 2 |
| 2207 | tools-calendar-hold | tools | restart_stable_ids | partition_delay | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 806 | – | – | – | 0 | 0 | 1 | 1 | 2 |
| 2207 | tools-calendar-hold | tools | local_delegate | partition_delay | no | refused | `incompatible_state:effect+lookup` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 2207 | tools-calendar-hold | tools | a2a_delegate | partition_delay | no | refused | `incompatible_state:effect+lookup` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 2207 | tools-calendar-hold | tools | checkpoint_relocate | partition_delay | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 3241 | – | – | – | 0 | 0 | 1 | 1 | 0 |
| 2207 | tools-calendar-hold | tools | cross_framework_reconstruct | partition_delay | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 2207 | tools-refund-sim | tools | keep_on_origin | duplicate_delivery | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_transfer_channel` | 0 | 0 | 0 | 0 | 0 |
| 2207 | tools-refund-sim | tools | restart_on_destination | duplicate_delivery | yes | completed | – | no | no | 0/0 | 1 | 1 | 1 | 0 | 0 | 0 | 986 | – | – | – | 0 | 0 | 0 | 0 | 3 |
| 2207 | tools-refund-sim | tools | restart_stable_ids | duplicate_delivery | yes | completed | – | no | no | 0/0 | 1 | 0 | 1 | 0 | 0 | 0 | 986 | – | – | – | 0 | 0 | 0 | 0 | 3 |
| 2207 | tools-refund-sim | tools | local_delegate | duplicate_delivery | no | refused | `incompatible_state:reserve` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 2207 | tools-refund-sim | tools | a2a_delegate | duplicate_delivery | no | refused | `incompatible_state:reserve` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 2207 | tools-refund-sim | tools | checkpoint_relocate | duplicate_delivery | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 3666 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 2207 | tools-refund-sim | tools | cross_framework_reconstruct | duplicate_delivery | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 2207 | tools-inventory-audit | tools | keep_on_origin | partition_drop_request | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_transfer_channel` | 0 | 0 | 0 | 0 | 0 |
| 2207 | tools-inventory-audit | tools | restart_on_destination | partition_drop_request | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 720 | – | – | – | 0 | 1 | 0 | 1 | 2 |
| 2207 | tools-inventory-audit | tools | restart_stable_ids | partition_drop_request | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 720 | – | – | – | 0 | 1 | 0 | 1 | 2 |
| 2207 | tools-inventory-audit | tools | local_delegate | partition_drop_request | no | refused | `incompatible_state:reserve` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 2207 | tools-inventory-audit | tools | a2a_delegate | partition_drop_request | no | refused | `incompatible_state:reserve` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 2207 | tools-inventory-audit | tools | checkpoint_relocate | partition_drop_request | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 3307 | – | – | – | 0 | 1 | 0 | 1 | 0 |
| 2207 | tools-inventory-audit | tools | cross_framework_reconstruct | partition_drop_request | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 3301 | doc-release-notes | document | keep_on_origin | duplicate_delivery | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_transfer_channel` | 0 | 0 | 0 | 0 | 0 |
| 3301 | doc-release-notes | document | restart_on_destination | duplicate_delivery | yes | completed | – | no | no | 0/1 | 0 | 1 | 1 | 0 | 0 | 0 | 1168 | – | – | – | 0 | 0 | 0 | 0 | 3 |
| 3301 | doc-release-notes | document | restart_stable_ids | duplicate_delivery | yes | completed | – | no | no | 0/1 | 0 | 0 | 0 | 0 | 0 | 0 | 1168 | – | – | – | 1 | 0 | 0 | 0 | 3 |
| 3301 | doc-release-notes | document | local_delegate | duplicate_delivery | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 4276 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 3301 | doc-release-notes | document | a2a_delegate | duplicate_delivery | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 4404 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 3301 | doc-release-notes | document | checkpoint_relocate | duplicate_delivery | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 4156 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 3301 | doc-release-notes | document | cross_framework_reconstruct | duplicate_delivery | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 3301 | doc-meeting-summary | document | keep_on_origin | effect_ack_lost | yes | completed | – | yes | yes | 2/2 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 3301 | doc-meeting-summary | document | restart_on_destination | effect_ack_lost | yes | completed | – | no | no | 1/2 | 0 | 0 | 1 | 1 | 1 | 0 | 618 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 3301 | doc-meeting-summary | document | restart_stable_ids | effect_ack_lost | yes | completed | – | no | no | 1/2 | 0 | 0 | 1 | 1 | 1 | 0 | 618 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 3301 | doc-meeting-summary | document | local_delegate | effect_ack_lost | no | refused | `incompatible_state:effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 3301 | doc-meeting-summary | document | a2a_delegate | effect_ack_lost | no | refused | `incompatible_state:effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 3301 | doc-meeting-summary | document | checkpoint_relocate | effect_ack_lost | yes | completed | – | yes | yes | 2/2 | 0 | 0 | 0 | 0 | 1 | 0 | 2057 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 3301 | doc-meeting-summary | document | cross_framework_reconstruct | effect_ack_lost | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 3301 | doc-policy-digest | document | keep_on_origin | none | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 3301 | doc-policy-digest | document | restart_on_destination | none | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 455 | – | – | – | 0 | 0 | 0 | 0 | 1 |
| 3301 | doc-policy-digest | document | restart_stable_ids | none | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 455 | – | – | – | 0 | 0 | 0 | 0 | 1 |
| 3301 | doc-policy-digest | document | local_delegate | none | no | refused | `incompatible_state:effect+extract` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 3301 | doc-policy-digest | document | a2a_delegate | none | no | refused | `incompatible_state:effect+extract` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 3301 | doc-policy-digest | document | checkpoint_relocate | none | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 1783 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 3301 | doc-policy-digest | document | cross_framework_reconstruct | none | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | – | – | – | – | – | – |
| 3301 | doc-incident-brief | document | keep_on_origin | partition_delay | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_transfer_channel` | 0 | 0 | 0 | 0 | 0 |
| 3301 | doc-incident-brief | document | restart_on_destination | partition_delay | yes | completed | – | no | no | 0/1 | 0 | 1 | 1 | 0 | 0 | 0 | 1160 | – | – | – | 0 | 0 | 1 | 1 | 3 |
| 3301 | doc-incident-brief | document | restart_stable_ids | partition_delay | yes | completed | – | no | no | 0/1 | 0 | 0 | 0 | 0 | 0 | 0 | 1160 | – | – | – | 1 | 0 | 1 | 1 | 3 |
| 3301 | doc-incident-brief | document | local_delegate | partition_delay | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 3214 | – | – | – | 0 | 0 | 1 | 1 | 0 |
| 3301 | doc-incident-brief | document | a2a_delegate | partition_delay | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 3310 | – | – | – | 0 | 0 | 1 | 1 | 0 |
| 3301 | doc-incident-brief | document | checkpoint_relocate | partition_delay | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 3975 | – | – | – | 0 | 0 | 1 | 1 | 0 |
| 3301 | doc-incident-brief | document | cross_framework_reconstruct | partition_delay | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 3301 | doc-faq-merge | document | keep_on_origin | stale_origin_returns | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_ownership_transfer` | 0 | 0 | 0 | 0 | 0 |
| 3301 | doc-faq-merge | document | restart_on_destination | stale_origin_returns | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 1 | 524 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 3301 | doc-faq-merge | document | restart_stable_ids | stale_origin_returns | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 1 | 524 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 3301 | doc-faq-merge | document | local_delegate | stale_origin_returns | no | refused | `incompatible_state:effect+extract` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `origin_remains_owner` | 0 | 0 | 0 | 0 | 0 |
| 3301 | doc-faq-merge | document | a2a_delegate | stale_origin_returns | no | refused | `incompatible_state:effect+extract` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `origin_remains_owner` | 0 | 0 | 0 | 0 | 0 |
| 3301 | doc-faq-merge | document | checkpoint_relocate | stale_origin_returns | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 1 | 1876 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 3301 | doc-faq-merge | document | cross_framework_reconstruct | stale_origin_returns | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 3301 | doc-handbook-excerpt | document | keep_on_origin | crash_after_effect_commit | yes | incomplete | `origin_crashed_no_recovery` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 1 | – | 0 | 0 | 0 | 0 | 0 |
| 3301 | doc-handbook-excerpt | document | restart_on_destination | crash_after_effect_commit | yes | completed | – | no | yes | 0/1 | 0 | 1 | 1 | 0 | 0 | 0 | 576 | – | 1 | – | 0 | 0 | 0 | 0 | 2 |
| 3301 | doc-handbook-excerpt | document | restart_stable_ids | crash_after_effect_commit | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 576 | – | 1 | – | 1 | 0 | 0 | 0 | 2 |
| 3301 | doc-handbook-excerpt | document | local_delegate | crash_after_effect_commit | yes | incomplete | `origin_crashed_owner_not_transferred` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 1 | – | 0 | 0 | 0 | 0 | 0 |
| 3301 | doc-handbook-excerpt | document | a2a_delegate | crash_after_effect_commit | yes | incomplete | `origin_crashed_owner_not_transferred` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 1 | – | 0 | 0 | 0 | 0 | 0 |
| 3301 | doc-handbook-excerpt | document | checkpoint_relocate | crash_after_effect_commit | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 1951 | – | 1 | – | 0 | 0 | 0 | 0 | 1 |
| 3301 | doc-handbook-excerpt | document | cross_framework_reconstruct | crash_after_effect_commit | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | 1 | `mode_unavailable` | – | – | – | – | – |
| 3301 | code-rename-helper | coding | keep_on_origin | crash_before_effect_commit | yes | incomplete | `origin_crashed_no_recovery` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 4 | – | 0 | 0 | 0 | 0 | 0 |
| 3301 | code-rename-helper | coding | restart_on_destination | crash_before_effect_commit | yes | completed | – | no | no | 0/1 | 0 | 0 | 1 | 1 | 0 | 0 | 579 | – | 4 | – | 0 | 0 | 0 | 0 | 7 |
| 3301 | code-rename-helper | coding | restart_stable_ids | crash_before_effect_commit | yes | completed | – | no | no | 0/1 | 0 | 0 | 1 | 1 | 0 | 0 | 579 | – | 4 | – | 0 | 0 | 0 | 0 | 7 |
| 3301 | code-rename-helper | coding | local_delegate | crash_before_effect_commit | no | refused | `incompatible_state:check_contains+effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 4 | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 3301 | code-rename-helper | coding | a2a_delegate | crash_before_effect_commit | no | refused | `incompatible_state:check_contains+effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 4 | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 3301 | code-rename-helper | coding | checkpoint_relocate | crash_before_effect_commit | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 1944 | – | 4 | – | 0 | 0 | 0 | 0 | 1 |
| 3301 | code-rename-helper | coding | cross_framework_reconstruct | crash_before_effect_commit | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | 4 | `mode_unavailable` | – | – | – | – | – |
| 3301 | code-add-docstring | coding | keep_on_origin | origin_preempted | yes | incomplete | `origin_preempted_no_transfer` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 3301 | code-add-docstring | coding | restart_on_destination | origin_preempted | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 599 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 3301 | code-add-docstring | coding | restart_stable_ids | origin_preempted | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 599 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 3301 | code-add-docstring | coding | local_delegate | origin_preempted | no | refused | `incompatible_state:effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 3301 | code-add-docstring | coding | a2a_delegate | origin_preempted | no | refused | `incompatible_state:effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 3301 | code-add-docstring | coding | checkpoint_relocate | origin_preempted | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 1906 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 3301 | code-add-docstring | coding | cross_framework_reconstruct | origin_preempted | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 3301 | code-version-bump | coding | keep_on_origin | origin_preempted | yes | incomplete | `origin_preempted_no_transfer` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 3301 | code-version-bump | coding | restart_on_destination | origin_preempted | yes | completed | – | no | yes | 0/0 | 0 | 1 | 0 | 0 | 0 | 0 | 538 | – | – | – | 0 | 0 | 0 | 0 | 3 |
| 3301 | code-version-bump | coding | restart_stable_ids | origin_preempted | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 538 | – | – | – | 0 | 0 | 0 | 0 | 3 |
| 3301 | code-version-bump | coding | local_delegate | origin_preempted | yes | incomplete | `origin_preempted_owner_not_transferred` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 3301 | code-version-bump | coding | a2a_delegate | origin_preempted | yes | incomplete | `origin_preempted_owner_not_transferred` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 3301 | code-version-bump | coding | checkpoint_relocate | origin_preempted | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 1886 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 3301 | code-version-bump | coding | cross_framework_reconstruct | origin_preempted | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 3301 | code-guard-config | coding | keep_on_origin | crash_after_effect_commit | yes | incomplete | `origin_crashed_no_recovery` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 4 | – | 0 | 0 | 0 | 0 | 0 |
| 3301 | code-guard-config | coding | restart_on_destination | crash_after_effect_commit | yes | completed | – | no | no | 0/1 | 0 | 1 | 1 | 0 | 0 | 0 | 547 | – | 4 | – | 0 | 0 | 0 | 0 | 6 |
| 3301 | code-guard-config | coding | restart_stable_ids | crash_after_effect_commit | yes | completed | – | no | no | 0/1 | 0 | 0 | 0 | 0 | 0 | 0 | 547 | – | 4 | – | 1 | 0 | 0 | 0 | 6 |
| 3301 | code-guard-config | coding | local_delegate | crash_after_effect_commit | no | refused | `incompatible_state:effect+replace` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 4 | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 3301 | code-guard-config | coding | a2a_delegate | crash_after_effect_commit | no | refused | `incompatible_state:effect+replace` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 4 | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 3301 | code-guard-config | coding | checkpoint_relocate | crash_after_effect_commit | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 1815 | – | 4 | – | 0 | 0 | 0 | 0 | 1 |
| 3301 | code-guard-config | coding | cross_framework_reconstruct | crash_after_effect_commit | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | 4 | `mode_unavailable` | – | – | – | – | – |
| 3301 | code-line-limit | coding | keep_on_origin | effect_ack_lost | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 3301 | code-line-limit | coding | restart_on_destination | effect_ack_lost | yes | completed | – | no | no | 0/1 | 0 | 0 | 1 | 1 | 1 | 0 | 603 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 3301 | code-line-limit | coding | restart_stable_ids | effect_ack_lost | yes | completed | – | no | no | 0/1 | 0 | 0 | 1 | 1 | 1 | 0 | 603 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 3301 | code-line-limit | coding | local_delegate | effect_ack_lost | no | refused | `incompatible_state:check_contains+effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 3301 | code-line-limit | coding | a2a_delegate | effect_ack_lost | no | refused | `incompatible_state:check_contains+effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 3301 | code-line-limit | coding | checkpoint_relocate | effect_ack_lost | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 1 | 0 | 1890 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 3301 | code-line-limit | coding | cross_framework_reconstruct | effect_ack_lost | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 3301 | code-test-fixture | coding | keep_on_origin | partition_drop_request | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_transfer_channel` | 0 | 0 | 0 | 0 | 0 |
| 3301 | code-test-fixture | coding | restart_on_destination | partition_drop_request | yes | completed | – | no | yes | 0/0 | 0 | 1 | 0 | 0 | 0 | 0 | 830 | – | – | – | 0 | 1 | 0 | 1 | 2 |
| 3301 | code-test-fixture | coding | restart_stable_ids | partition_drop_request | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 830 | – | – | – | 0 | 1 | 0 | 1 | 2 |
| 3301 | code-test-fixture | coding | local_delegate | partition_drop_request | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 3354 | – | – | – | 0 | 1 | 0 | 1 | 0 |
| 3301 | code-test-fixture | coding | a2a_delegate | partition_drop_request | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 3482 | – | – | – | 0 | 1 | 0 | 1 | 0 |
| 3301 | code-test-fixture | coding | checkpoint_relocate | partition_drop_request | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 3319 | – | – | – | 0 | 1 | 0 | 1 | 0 |
| 3301 | code-test-fixture | coding | cross_framework_reconstruct | partition_drop_request | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 3301 | tools-restock-order | tools | keep_on_origin | stale_origin_returns | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_ownership_transfer` | 0 | 0 | 0 | 0 | 0 |
| 3301 | tools-restock-order | tools | restart_on_destination | stale_origin_returns | yes | completed | – | no | no | 0/0 | 1 | 1 | 1 | 0 | 0 | 1 | 414 | – | – | – | 0 | 0 | 0 | 0 | 3 |
| 3301 | tools-restock-order | tools | restart_stable_ids | stale_origin_returns | yes | completed | – | no | no | 0/0 | 1 | 0 | 1 | 0 | 0 | 1 | 414 | – | – | – | 0 | 0 | 0 | 0 | 3 |
| 3301 | tools-restock-order | tools | local_delegate | stale_origin_returns | no | refused | `incompatible_state:lookup` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `origin_remains_owner` | 0 | 0 | 0 | 0 | 0 |
| 3301 | tools-restock-order | tools | a2a_delegate | stale_origin_returns | no | refused | `incompatible_state:lookup` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `origin_remains_owner` | 0 | 0 | 0 | 0 | 0 |
| 3301 | tools-restock-order | tools | checkpoint_relocate | stale_origin_returns | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 1 | 1785 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 3301 | tools-restock-order | tools | cross_framework_reconstruct | stale_origin_returns | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 3301 | tools-travel-booking | tools | keep_on_origin | partition_drop_reply | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_transfer_channel` | 0 | 0 | 0 | 0 | 0 |
| 3301 | tools-travel-booking | tools | restart_on_destination | partition_drop_reply | no | completed | – | no | yes | 0/0 | 0 | 1 | 0 | 0 | 0 | 0 | 377 | – | – | `no_reply_message` | 0 | 0 | 0 | 0 | 1 |
| 3301 | tools-travel-booking | tools | restart_stable_ids | partition_drop_reply | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 377 | – | – | `no_reply_message` | 0 | 0 | 0 | 0 | 1 |
| 3301 | tools-travel-booking | tools | local_delegate | partition_drop_reply | no | refused | `incompatible_state:effect+lookup` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 3301 | tools-travel-booking | tools | a2a_delegate | partition_drop_reply | no | refused | `incompatible_state:effect+lookup` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 3301 | tools-travel-booking | tools | checkpoint_relocate | partition_drop_reply | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 3221 | – | – | – | 0 | 1 | 0 | 1 | 0 |
| 3301 | tools-travel-booking | tools | cross_framework_reconstruct | partition_drop_reply | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 3301 | tools-ticket-triage | tools | keep_on_origin | partition_drop_reply | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_transfer_channel` | 0 | 0 | 0 | 0 | 0 |
| 3301 | tools-ticket-triage | tools | restart_on_destination | partition_drop_reply | no | completed | – | no | yes | 0/0 | 0 | 1 | 0 | 0 | 0 | 0 | 511 | – | – | `no_reply_message` | 0 | 0 | 0 | 0 | 3 |
| 3301 | tools-ticket-triage | tools | restart_stable_ids | partition_drop_reply | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 511 | – | – | `no_reply_message` | 0 | 0 | 0 | 0 | 3 |
| 3301 | tools-ticket-triage | tools | local_delegate | partition_drop_reply | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 3053 | – | – | – | 0 | 1 | 0 | 1 | 0 |
| 3301 | tools-ticket-triage | tools | a2a_delegate | partition_drop_reply | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 3149 | – | – | – | 0 | 1 | 0 | 1 | 0 |
| 3301 | tools-ticket-triage | tools | checkpoint_relocate | partition_drop_reply | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 3465 | – | – | – | 0 | 1 | 0 | 1 | 0 |
| 3301 | tools-ticket-triage | tools | cross_framework_reconstruct | partition_drop_reply | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 3301 | tools-calendar-hold | tools | keep_on_origin | partition_drop_request | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_transfer_channel` | 0 | 0 | 0 | 0 | 0 |
| 3301 | tools-calendar-hold | tools | restart_on_destination | partition_drop_request | yes | completed | – | no | yes | 0/0 | 0 | 1 | 0 | 0 | 0 | 0 | 806 | – | – | – | 0 | 1 | 0 | 1 | 2 |
| 3301 | tools-calendar-hold | tools | restart_stable_ids | partition_drop_request | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 806 | – | – | – | 0 | 1 | 0 | 1 | 2 |
| 3301 | tools-calendar-hold | tools | local_delegate | partition_drop_request | no | refused | `incompatible_state:effect+lookup` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 3301 | tools-calendar-hold | tools | a2a_delegate | partition_drop_request | no | refused | `incompatible_state:effect+lookup` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 3301 | tools-calendar-hold | tools | checkpoint_relocate | partition_drop_request | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 3241 | – | – | – | 0 | 1 | 0 | 1 | 0 |
| 3301 | tools-calendar-hold | tools | cross_framework_reconstruct | partition_drop_request | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 3301 | tools-refund-sim | tools | keep_on_origin | crash_before_effect_commit | yes | incomplete | `origin_crashed_no_recovery` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 3 | – | 0 | 0 | 0 | 0 | 0 |
| 3301 | tools-refund-sim | tools | restart_on_destination | crash_before_effect_commit | yes | completed | – | no | no | 0/0 | 2 | 3 | 2 | 0 | 0 | 0 | 493 | – | 3 | – | 0 | 0 | 0 | 0 | 7 |
| 3301 | tools-refund-sim | tools | restart_stable_ids | crash_before_effect_commit | yes | completed | – | no | no | 0/0 | 1 | 0 | 1 | 0 | 0 | 0 | 493 | – | 3 | – | 0 | 0 | 0 | 0 | 7 |
| 3301 | tools-refund-sim | tools | local_delegate | crash_before_effect_commit | no | refused | `incompatible_state:reserve` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 3 | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 3301 | tools-refund-sim | tools | a2a_delegate | crash_before_effect_commit | no | refused | `incompatible_state:reserve` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 3 | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 3301 | tools-refund-sim | tools | checkpoint_relocate | crash_before_effect_commit | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 1833 | – | 3 | – | 0 | 0 | 0 | 0 | 1 |
| 3301 | tools-refund-sim | tools | cross_framework_reconstruct | crash_before_effect_commit | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | 3 | `mode_unavailable` | – | – | – | – | – |
| 3301 | tools-inventory-audit | tools | keep_on_origin | duplicate_delivery | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_transfer_channel` | 0 | 0 | 0 | 0 | 0 |
| 3301 | tools-inventory-audit | tools | restart_on_destination | duplicate_delivery | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 720 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 3301 | tools-inventory-audit | tools | restart_stable_ids | duplicate_delivery | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 720 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 3301 | tools-inventory-audit | tools | local_delegate | duplicate_delivery | no | refused | `incompatible_state:reserve` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 3301 | tools-inventory-audit | tools | a2a_delegate | duplicate_delivery | no | refused | `incompatible_state:reserve` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 3301 | tools-inventory-audit | tools | checkpoint_relocate | duplicate_delivery | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 3490 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 3301 | tools-inventory-audit | tools | cross_framework_reconstruct | duplicate_delivery | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 4409 | doc-release-notes | document | keep_on_origin | partition_drop_request | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_transfer_channel` | 0 | 0 | 0 | 0 | 0 |
| 4409 | doc-release-notes | document | restart_on_destination | partition_drop_request | yes | completed | – | no | no | 0/1 | 0 | 1 | 1 | 0 | 0 | 0 | 1168 | – | – | – | 0 | 1 | 0 | 1 | 3 |
| 4409 | doc-release-notes | document | restart_stable_ids | partition_drop_request | yes | completed | – | no | no | 0/1 | 0 | 0 | 0 | 0 | 0 | 0 | 1168 | – | – | – | 1 | 1 | 0 | 1 | 3 |
| 4409 | doc-release-notes | document | local_delegate | partition_drop_request | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 2750 | – | – | – | 0 | 1 | 0 | 1 | 0 |
| 4409 | doc-release-notes | document | a2a_delegate | partition_drop_request | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 2846 | – | – | – | 0 | 1 | 0 | 1 | 0 |
| 4409 | doc-release-notes | document | checkpoint_relocate | partition_drop_request | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 3981 | – | – | – | 0 | 1 | 0 | 1 | 0 |
| 4409 | doc-release-notes | document | cross_framework_reconstruct | partition_drop_request | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 4409 | doc-meeting-summary | document | keep_on_origin | stale_origin_returns | no | completed | – | yes | yes | 2/2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_ownership_transfer` | 0 | 0 | 0 | 0 | 0 |
| 4409 | doc-meeting-summary | document | restart_on_destination | stale_origin_returns | yes | completed | – | no | no | 1/2 | 0 | 0 | 1 | 1 | 0 | 1 | 618 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 4409 | doc-meeting-summary | document | restart_stable_ids | stale_origin_returns | yes | completed | – | no | no | 1/2 | 0 | 0 | 1 | 1 | 0 | 1 | 618 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 4409 | doc-meeting-summary | document | local_delegate | stale_origin_returns | no | refused | `incompatible_state:effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `origin_remains_owner` | 0 | 0 | 0 | 0 | 0 |
| 4409 | doc-meeting-summary | document | a2a_delegate | stale_origin_returns | no | refused | `incompatible_state:effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `origin_remains_owner` | 0 | 0 | 0 | 0 | 0 |
| 4409 | doc-meeting-summary | document | checkpoint_relocate | stale_origin_returns | yes | completed | – | yes | yes | 2/2 | 0 | 0 | 0 | 0 | 0 | 1 | 2057 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 4409 | doc-meeting-summary | document | cross_framework_reconstruct | stale_origin_returns | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 4409 | doc-policy-digest | document | keep_on_origin | duplicate_delivery | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_transfer_channel` | 0 | 0 | 0 | 0 | 0 |
| 4409 | doc-policy-digest | document | restart_on_destination | duplicate_delivery | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 910 | – | – | – | 0 | 0 | 0 | 0 | 1 |
| 4409 | doc-policy-digest | document | restart_stable_ids | duplicate_delivery | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 910 | – | – | – | 0 | 0 | 0 | 0 | 1 |
| 4409 | doc-policy-digest | document | local_delegate | duplicate_delivery | no | refused | `incompatible_state:effect+extract` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 4409 | doc-policy-digest | document | a2a_delegate | duplicate_delivery | no | refused | `incompatible_state:effect+extract` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 4409 | doc-policy-digest | document | checkpoint_relocate | duplicate_delivery | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 3566 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 4409 | doc-policy-digest | document | cross_framework_reconstruct | duplicate_delivery | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 4409 | doc-incident-brief | document | keep_on_origin | effect_ack_lost | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 4409 | doc-incident-brief | document | restart_on_destination | effect_ack_lost | yes | completed | – | no | no | 0/1 | 0 | 1 | 1 | 0 | 1 | 0 | 580 | – | – | – | 0 | 0 | 0 | 0 | 3 |
| 4409 | doc-incident-brief | document | restart_stable_ids | effect_ack_lost | yes | completed | – | no | no | 0/1 | 0 | 0 | 0 | 0 | 1 | 0 | 580 | – | – | – | 1 | 0 | 0 | 0 | 3 |
| 4409 | doc-incident-brief | document | local_delegate | effect_ack_lost | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 1 | 0 | 2167 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 4409 | doc-incident-brief | document | a2a_delegate | effect_ack_lost | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 1 | 0 | 2231 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 4409 | doc-incident-brief | document | checkpoint_relocate | effect_ack_lost | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 1 | 0 | 2076 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 4409 | doc-incident-brief | document | cross_framework_reconstruct | effect_ack_lost | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 4409 | doc-faq-merge | document | keep_on_origin | partition_drop_reply | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_transfer_channel` | 0 | 0 | 0 | 0 | 0 |
| 4409 | doc-faq-merge | document | restart_on_destination | partition_drop_reply | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 524 | – | – | `no_reply_message` | 0 | 0 | 0 | 0 | 2 |
| 4409 | doc-faq-merge | document | restart_stable_ids | partition_drop_reply | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 524 | – | – | `no_reply_message` | 0 | 0 | 0 | 0 | 2 |
| 4409 | doc-faq-merge | document | local_delegate | partition_drop_reply | no | refused | `incompatible_state:effect+extract` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 4409 | doc-faq-merge | document | a2a_delegate | partition_drop_reply | no | refused | `incompatible_state:effect+extract` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 4409 | doc-faq-merge | document | checkpoint_relocate | partition_drop_reply | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 3585 | – | – | – | 0 | 1 | 0 | 1 | 0 |
| 4409 | doc-faq-merge | document | cross_framework_reconstruct | partition_drop_reply | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 4409 | doc-handbook-excerpt | document | keep_on_origin | none | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 4409 | doc-handbook-excerpt | document | restart_on_destination | none | no | completed | – | no | yes | 0/1 | 0 | 1 | 1 | 0 | 0 | 0 | 576 | – | – | – | 0 | 0 | 0 | 0 | 3 |
| 4409 | doc-handbook-excerpt | document | restart_stable_ids | none | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 576 | – | – | – | 1 | 0 | 0 | 0 | 3 |
| 4409 | doc-handbook-excerpt | document | local_delegate | none | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 2229 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 4409 | doc-handbook-excerpt | document | a2a_delegate | none | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 2293 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 4409 | doc-handbook-excerpt | document | checkpoint_relocate | none | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 2083 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 4409 | doc-handbook-excerpt | document | cross_framework_reconstruct | none | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | – | – | – | – | – | – |
| 4409 | code-rename-helper | coding | keep_on_origin | none | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 4409 | code-rename-helper | coding | restart_on_destination | none | no | completed | – | no | no | 0/1 | 0 | 0 | 1 | 1 | 0 | 0 | 579 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 4409 | code-rename-helper | coding | restart_stable_ids | none | no | completed | – | no | no | 0/1 | 0 | 0 | 1 | 1 | 0 | 0 | 579 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 4409 | code-rename-helper | coding | local_delegate | none | no | refused | `incompatible_state:check_contains+effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 4409 | code-rename-helper | coding | a2a_delegate | none | no | refused | `incompatible_state:check_contains+effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 4409 | code-rename-helper | coding | checkpoint_relocate | none | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 1944 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 4409 | code-rename-helper | coding | cross_framework_reconstruct | none | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | – | – | – | – | – | – |
| 4409 | code-add-docstring | coding | keep_on_origin | effect_ack_lost | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 4409 | code-add-docstring | coding | restart_on_destination | effect_ack_lost | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 1 | 0 | 599 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 4409 | code-add-docstring | coding | restart_stable_ids | effect_ack_lost | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 1 | 0 | 599 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 4409 | code-add-docstring | coding | local_delegate | effect_ack_lost | no | refused | `incompatible_state:effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 4409 | code-add-docstring | coding | a2a_delegate | effect_ack_lost | no | refused | `incompatible_state:effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 4409 | code-add-docstring | coding | checkpoint_relocate | effect_ack_lost | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 1 | 0 | 1909 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 4409 | code-add-docstring | coding | cross_framework_reconstruct | effect_ack_lost | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 4409 | code-version-bump | coding | keep_on_origin | crash_after_effect_commit | yes | incomplete | `origin_crashed_no_recovery` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 2 | – | 0 | 0 | 0 | 0 | 0 |
| 4409 | code-version-bump | coding | restart_on_destination | crash_after_effect_commit | yes | completed | – | no | yes | 0/0 | 0 | 1 | 0 | 0 | 0 | 0 | 538 | – | 2 | – | 0 | 0 | 0 | 0 | 3 |
| 4409 | code-version-bump | coding | restart_stable_ids | crash_after_effect_commit | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 538 | – | 2 | – | 0 | 0 | 0 | 0 | 3 |
| 4409 | code-version-bump | coding | local_delegate | crash_after_effect_commit | yes | incomplete | `origin_crashed_owner_not_transferred` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 2 | – | 0 | 0 | 0 | 0 | 0 |
| 4409 | code-version-bump | coding | a2a_delegate | crash_after_effect_commit | yes | incomplete | `origin_crashed_owner_not_transferred` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 2 | – | 0 | 0 | 0 | 0 | 0 |
| 4409 | code-version-bump | coding | checkpoint_relocate | crash_after_effect_commit | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 1893 | – | 2 | – | 0 | 0 | 0 | 0 | 1 |
| 4409 | code-version-bump | coding | cross_framework_reconstruct | crash_after_effect_commit | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | 2 | `mode_unavailable` | – | – | – | – | – |
| 4409 | code-guard-config | coding | keep_on_origin | partition_delay | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_transfer_channel` | 0 | 0 | 0 | 0 | 0 |
| 4409 | code-guard-config | coding | restart_on_destination | partition_delay | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 1094 | – | – | – | 0 | 0 | 1 | 1 | 1 |
| 4409 | code-guard-config | coding | restart_stable_ids | partition_delay | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 1094 | – | – | – | 0 | 0 | 1 | 1 | 1 |
| 4409 | code-guard-config | coding | local_delegate | partition_delay | no | refused | `incompatible_state:effect+replace` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 4409 | code-guard-config | coding | a2a_delegate | partition_delay | no | refused | `incompatible_state:effect+replace` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 4409 | code-guard-config | coding | checkpoint_relocate | partition_delay | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 3455 | – | – | – | 0 | 0 | 1 | 1 | 0 |
| 4409 | code-guard-config | coding | cross_framework_reconstruct | partition_delay | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 4409 | code-line-limit | coding | keep_on_origin | origin_preempted | yes | incomplete | `origin_preempted_no_transfer` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 4409 | code-line-limit | coding | restart_on_destination | origin_preempted | yes | completed | – | no | no | 0/1 | 0 | 0 | 1 | 1 | 0 | 0 | 603 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 4409 | code-line-limit | coding | restart_stable_ids | origin_preempted | yes | completed | – | no | no | 0/1 | 0 | 0 | 1 | 1 | 0 | 0 | 603 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 4409 | code-line-limit | coding | local_delegate | origin_preempted | no | refused | `incompatible_state:check_contains+effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 4409 | code-line-limit | coding | a2a_delegate | origin_preempted | no | refused | `incompatible_state:check_contains+effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 4409 | code-line-limit | coding | checkpoint_relocate | origin_preempted | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 1887 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 4409 | code-line-limit | coding | cross_framework_reconstruct | origin_preempted | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 4409 | code-test-fixture | coding | keep_on_origin | stale_origin_returns | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_ownership_transfer` | 0 | 0 | 0 | 0 | 0 |
| 4409 | code-test-fixture | coding | restart_on_destination | stale_origin_returns | yes | completed | – | no | yes | 0/0 | 0 | 1 | 0 | 0 | 0 | 1 | 415 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 4409 | code-test-fixture | coding | restart_stable_ids | stale_origin_returns | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 1 | 415 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 4409 | code-test-fixture | coding | local_delegate | stale_origin_returns | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 2892 | – | – | `origin_remains_owner` | 0 | 0 | 0 | 0 | 0 |
| 4409 | code-test-fixture | coding | a2a_delegate | stale_origin_returns | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 2988 | – | – | `origin_remains_owner` | 0 | 0 | 0 | 0 | 0 |
| 4409 | code-test-fixture | coding | checkpoint_relocate | stale_origin_returns | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 1 | 1747 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 4409 | code-test-fixture | coding | cross_framework_reconstruct | stale_origin_returns | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 4409 | tools-restock-order | tools | keep_on_origin | origin_preempted | yes | incomplete | `origin_preempted_no_transfer` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 4409 | tools-restock-order | tools | restart_on_destination | origin_preempted | yes | completed | – | no | no | 0/0 | 1 | 1 | 1 | 0 | 0 | 0 | 414 | – | – | – | 0 | 0 | 0 | 0 | 3 |
| 4409 | tools-restock-order | tools | restart_stable_ids | origin_preempted | yes | completed | – | no | no | 0/0 | 1 | 0 | 1 | 0 | 0 | 0 | 414 | – | – | – | 0 | 0 | 0 | 0 | 3 |
| 4409 | tools-restock-order | tools | local_delegate | origin_preempted | no | refused | `incompatible_state:lookup` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 4409 | tools-restock-order | tools | a2a_delegate | origin_preempted | no | refused | `incompatible_state:lookup` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 4409 | tools-restock-order | tools | checkpoint_relocate | origin_preempted | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 1782 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 4409 | tools-restock-order | tools | cross_framework_reconstruct | origin_preempted | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 4409 | tools-travel-booking | tools | keep_on_origin | duplicate_delivery | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_transfer_channel` | 0 | 0 | 0 | 0 | 0 |
| 4409 | tools-travel-booking | tools | restart_on_destination | duplicate_delivery | yes | completed | – | no | yes | 0/0 | 0 | 1 | 0 | 0 | 0 | 0 | 754 | – | – | – | 0 | 0 | 0 | 0 | 1 |
| 4409 | tools-travel-booking | tools | restart_stable_ids | duplicate_delivery | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 754 | – | – | – | 0 | 0 | 0 | 0 | 1 |
| 4409 | tools-travel-booking | tools | local_delegate | duplicate_delivery | no | refused | `incompatible_state:effect+lookup` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 4409 | tools-travel-booking | tools | a2a_delegate | duplicate_delivery | no | refused | `incompatible_state:effect+lookup` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 4409 | tools-travel-booking | tools | checkpoint_relocate | duplicate_delivery | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 3402 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 4409 | tools-travel-booking | tools | cross_framework_reconstruct | duplicate_delivery | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 4409 | tools-ticket-triage | tools | keep_on_origin | crash_before_effect_commit | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | 2 | `no_effect_intent_at_crash_step` | 0 | 0 | 0 | 0 | 0 |
| 4409 | tools-ticket-triage | tools | restart_on_destination | crash_before_effect_commit | no | completed | – | no | yes | 0/0 | 0 | 1 | 0 | 0 | 0 | 0 | 511 | – | 2 | `no_effect_intent_at_crash_step` | 0 | 0 | 0 | 0 | 3 |
| 4409 | tools-ticket-triage | tools | restart_stable_ids | crash_before_effect_commit | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 511 | – | 2 | `no_effect_intent_at_crash_step` | 0 | 0 | 0 | 0 | 3 |
| 4409 | tools-ticket-triage | tools | local_delegate | crash_before_effect_commit | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 2043 | – | 2 | `no_effect_intent_at_crash_step` | 0 | 0 | 0 | 0 | 0 |
| 4409 | tools-ticket-triage | tools | a2a_delegate | crash_before_effect_commit | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 2107 | – | 2 | `no_effect_intent_at_crash_step` | 0 | 0 | 0 | 0 | 0 |
| 4409 | tools-ticket-triage | tools | checkpoint_relocate | crash_before_effect_commit | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 1822 | – | 2 | `no_effect_intent_at_crash_step` | 0 | 0 | 0 | 0 | 0 |
| 4409 | tools-ticket-triage | tools | cross_framework_reconstruct | crash_before_effect_commit | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | 2 | `mode_unavailable` | – | – | – | – | – |
| 4409 | tools-calendar-hold | tools | keep_on_origin | partition_delay | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_transfer_channel` | 0 | 0 | 0 | 0 | 0 |
| 4409 | tools-calendar-hold | tools | restart_on_destination | partition_delay | yes | completed | – | no | yes | 0/0 | 0 | 1 | 0 | 0 | 0 | 0 | 806 | – | – | – | 0 | 0 | 1 | 1 | 2 |
| 4409 | tools-calendar-hold | tools | restart_stable_ids | partition_delay | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 806 | – | – | – | 0 | 0 | 1 | 1 | 2 |
| 4409 | tools-calendar-hold | tools | local_delegate | partition_delay | no | refused | `incompatible_state:effect+lookup` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 4409 | tools-calendar-hold | tools | a2a_delegate | partition_delay | no | refused | `incompatible_state:effect+lookup` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 4409 | tools-calendar-hold | tools | checkpoint_relocate | partition_delay | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 3241 | – | – | – | 0 | 0 | 1 | 1 | 0 |
| 4409 | tools-calendar-hold | tools | cross_framework_reconstruct | partition_delay | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 4409 | tools-refund-sim | tools | keep_on_origin | crash_after_effect_commit | yes | incomplete | `origin_crashed_no_recovery` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 3 | – | 0 | 0 | 0 | 0 | 0 |
| 4409 | tools-refund-sim | tools | restart_on_destination | crash_after_effect_commit | yes | completed | – | no | no | 0/0 | 2 | 4 | 2 | 0 | 0 | 0 | 493 | – | 3 | – | 0 | 0 | 0 | 0 | 7 |
| 4409 | tools-refund-sim | tools | restart_stable_ids | crash_after_effect_commit | yes | completed | – | no | no | 0/0 | 1 | 0 | 1 | 0 | 0 | 0 | 493 | – | 3 | – | 0 | 0 | 0 | 0 | 7 |
| 4409 | tools-refund-sim | tools | local_delegate | crash_after_effect_commit | no | refused | `incompatible_state:reserve` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 3 | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 4409 | tools-refund-sim | tools | a2a_delegate | crash_after_effect_commit | no | refused | `incompatible_state:reserve` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 3 | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 4409 | tools-refund-sim | tools | checkpoint_relocate | crash_after_effect_commit | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 1833 | – | 3 | – | 0 | 0 | 0 | 0 | 1 |
| 4409 | tools-refund-sim | tools | cross_framework_reconstruct | crash_after_effect_commit | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | 3 | `mode_unavailable` | – | – | – | – | – |
| 4409 | tools-inventory-audit | tools | keep_on_origin | crash_before_effect_commit | yes | incomplete | `origin_crashed_no_recovery` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 3 | – | 0 | 0 | 0 | 0 | 0 |
| 4409 | tools-inventory-audit | tools | restart_on_destination | crash_before_effect_commit | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 360 | – | 3 | – | 0 | 0 | 0 | 0 | 6 |
| 4409 | tools-inventory-audit | tools | restart_stable_ids | crash_before_effect_commit | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 360 | – | 3 | – | 0 | 0 | 0 | 0 | 6 |
| 4409 | tools-inventory-audit | tools | local_delegate | crash_before_effect_commit | no | refused | `incompatible_state:reserve` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 3 | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 4409 | tools-inventory-audit | tools | a2a_delegate | crash_before_effect_commit | no | refused | `incompatible_state:reserve` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 3 | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 4409 | tools-inventory-audit | tools | checkpoint_relocate | crash_before_effect_commit | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 1745 | – | 3 | – | 0 | 0 | 0 | 0 | 1 |
| 4409 | tools-inventory-audit | tools | cross_framework_reconstruct | crash_before_effect_commit | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | 3 | `mode_unavailable` | – | – | – | – | – |
| 5501 | doc-release-notes | document | keep_on_origin | partition_delay | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_transfer_channel` | 0 | 0 | 0 | 0 | 0 |
| 5501 | doc-release-notes | document | restart_on_destination | partition_delay | yes | completed | – | no | no | 0/1 | 0 | 1 | 1 | 0 | 0 | 0 | 1168 | – | – | – | 0 | 0 | 1 | 1 | 3 |
| 5501 | doc-release-notes | document | restart_stable_ids | partition_delay | yes | completed | – | no | no | 0/1 | 0 | 0 | 0 | 0 | 0 | 0 | 1168 | – | – | – | 1 | 0 | 1 | 1 | 3 |
| 5501 | doc-release-notes | document | local_delegate | partition_delay | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 3172 | – | – | – | 0 | 0 | 1 | 1 | 0 |
| 5501 | doc-release-notes | document | a2a_delegate | partition_delay | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 3268 | – | – | – | 0 | 0 | 1 | 1 | 0 |
| 5501 | doc-release-notes | document | checkpoint_relocate | partition_delay | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 3981 | – | – | – | 0 | 0 | 1 | 1 | 0 |
| 5501 | doc-release-notes | document | cross_framework_reconstruct | partition_delay | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 5501 | doc-meeting-summary | document | keep_on_origin | duplicate_delivery | no | completed | – | yes | yes | 2/2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_transfer_channel` | 0 | 0 | 0 | 0 | 0 |
| 5501 | doc-meeting-summary | document | restart_on_destination | duplicate_delivery | yes | completed | – | no | no | 1/2 | 0 | 0 | 1 | 1 | 0 | 0 | 1236 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 5501 | doc-meeting-summary | document | restart_stable_ids | duplicate_delivery | yes | completed | – | no | no | 1/2 | 0 | 0 | 1 | 1 | 0 | 0 | 1236 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 5501 | doc-meeting-summary | document | local_delegate | duplicate_delivery | no | refused | `incompatible_state:effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 5501 | doc-meeting-summary | document | a2a_delegate | duplicate_delivery | no | refused | `incompatible_state:effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 5501 | doc-meeting-summary | document | checkpoint_relocate | duplicate_delivery | yes | completed | – | yes | yes | 2/2 | 0 | 0 | 0 | 0 | 0 | 0 | 4114 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 5501 | doc-meeting-summary | document | cross_framework_reconstruct | duplicate_delivery | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 5501 | doc-policy-digest | document | keep_on_origin | duplicate_delivery | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_transfer_channel` | 0 | 0 | 0 | 0 | 0 |
| 5501 | doc-policy-digest | document | restart_on_destination | duplicate_delivery | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 910 | – | – | – | 0 | 0 | 0 | 0 | 1 |
| 5501 | doc-policy-digest | document | restart_stable_ids | duplicate_delivery | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 910 | – | – | – | 0 | 0 | 0 | 0 | 1 |
| 5501 | doc-policy-digest | document | local_delegate | duplicate_delivery | no | refused | `incompatible_state:effect+extract` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 5501 | doc-policy-digest | document | a2a_delegate | duplicate_delivery | no | refused | `incompatible_state:effect+extract` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 5501 | doc-policy-digest | document | checkpoint_relocate | duplicate_delivery | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 3566 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 5501 | doc-policy-digest | document | cross_framework_reconstruct | duplicate_delivery | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 5501 | doc-incident-brief | document | keep_on_origin | none | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 5501 | doc-incident-brief | document | restart_on_destination | none | no | completed | – | no | no | 0/1 | 0 | 1 | 1 | 0 | 0 | 0 | 580 | – | – | – | 0 | 0 | 0 | 0 | 3 |
| 5501 | doc-incident-brief | document | restart_stable_ids | none | no | completed | – | no | no | 0/1 | 0 | 0 | 0 | 0 | 0 | 0 | 580 | – | – | – | 1 | 0 | 0 | 0 | 3 |
| 5501 | doc-incident-brief | document | local_delegate | none | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 2167 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 5501 | doc-incident-brief | document | a2a_delegate | none | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 2231 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 5501 | doc-incident-brief | document | checkpoint_relocate | none | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 2076 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 5501 | doc-incident-brief | document | cross_framework_reconstruct | none | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | – | – | – | – | – | – |
| 5501 | doc-faq-merge | document | keep_on_origin | stale_origin_returns | no | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_ownership_transfer` | 0 | 0 | 0 | 0 | 0 |
| 5501 | doc-faq-merge | document | restart_on_destination | stale_origin_returns | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 1 | 524 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 5501 | doc-faq-merge | document | restart_stable_ids | stale_origin_returns | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 1 | 524 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 5501 | doc-faq-merge | document | local_delegate | stale_origin_returns | no | refused | `incompatible_state:effect+extract` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `origin_remains_owner` | 0 | 0 | 0 | 0 | 0 |
| 5501 | doc-faq-merge | document | a2a_delegate | stale_origin_returns | no | refused | `incompatible_state:effect+extract` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `origin_remains_owner` | 0 | 0 | 0 | 0 | 0 |
| 5501 | doc-faq-merge | document | checkpoint_relocate | stale_origin_returns | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 1 | 1876 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 5501 | doc-faq-merge | document | cross_framework_reconstruct | stale_origin_returns | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 5501 | doc-handbook-excerpt | document | keep_on_origin | effect_ack_lost | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 5501 | doc-handbook-excerpt | document | restart_on_destination | effect_ack_lost | yes | completed | – | no | yes | 0/1 | 0 | 1 | 1 | 0 | 1 | 0 | 576 | – | – | – | 0 | 0 | 0 | 0 | 3 |
| 5501 | doc-handbook-excerpt | document | restart_stable_ids | effect_ack_lost | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 1 | 0 | 576 | – | – | – | 1 | 0 | 0 | 0 | 3 |
| 5501 | doc-handbook-excerpt | document | local_delegate | effect_ack_lost | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 1 | 0 | 2229 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 5501 | doc-handbook-excerpt | document | a2a_delegate | effect_ack_lost | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 1 | 0 | 2293 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 5501 | doc-handbook-excerpt | document | checkpoint_relocate | effect_ack_lost | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 1 | 0 | 2083 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 5501 | doc-handbook-excerpt | document | cross_framework_reconstruct | effect_ack_lost | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 5501 | code-rename-helper | coding | keep_on_origin | effect_ack_lost | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 5501 | code-rename-helper | coding | restart_on_destination | effect_ack_lost | yes | completed | – | no | no | 0/1 | 0 | 0 | 1 | 1 | 1 | 0 | 579 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 5501 | code-rename-helper | coding | restart_stable_ids | effect_ack_lost | yes | completed | – | no | no | 0/1 | 0 | 0 | 1 | 1 | 1 | 0 | 579 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 5501 | code-rename-helper | coding | local_delegate | effect_ack_lost | no | refused | `incompatible_state:check_contains+effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 5501 | code-rename-helper | coding | a2a_delegate | effect_ack_lost | no | refused | `incompatible_state:check_contains+effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 5501 | code-rename-helper | coding | checkpoint_relocate | effect_ack_lost | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 1 | 0 | 1944 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 5501 | code-rename-helper | coding | cross_framework_reconstruct | effect_ack_lost | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 5501 | code-add-docstring | coding | keep_on_origin | crash_after_effect_commit | yes | incomplete | `origin_crashed_no_recovery` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 4 | – | 0 | 0 | 0 | 0 | 0 |
| 5501 | code-add-docstring | coding | restart_on_destination | crash_after_effect_commit | yes | completed | – | no | yes | 1/1 | 0 | 1 | 0 | 0 | 0 | 0 | 599 | – | 4 | – | 0 | 0 | 0 | 0 | 7 |
| 5501 | code-add-docstring | coding | restart_stable_ids | crash_after_effect_commit | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 599 | – | 4 | – | 0 | 0 | 0 | 0 | 7 |
| 5501 | code-add-docstring | coding | local_delegate | crash_after_effect_commit | no | refused | `incompatible_state:effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 4 | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 5501 | code-add-docstring | coding | a2a_delegate | crash_after_effect_commit | no | refused | `incompatible_state:effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 4 | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 5501 | code-add-docstring | coding | checkpoint_relocate | crash_after_effect_commit | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 1909 | – | 4 | – | 0 | 0 | 0 | 0 | 1 |
| 5501 | code-add-docstring | coding | cross_framework_reconstruct | crash_after_effect_commit | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | 4 | `mode_unavailable` | – | – | – | – | – |
| 5501 | code-version-bump | coding | keep_on_origin | partition_drop_reply | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_transfer_channel` | 0 | 0 | 0 | 0 | 0 |
| 5501 | code-version-bump | coding | restart_on_destination | partition_drop_reply | no | completed | – | no | yes | 0/0 | 0 | 1 | 0 | 0 | 0 | 0 | 538 | – | – | `no_reply_message` | 0 | 0 | 0 | 0 | 3 |
| 5501 | code-version-bump | coding | restart_stable_ids | partition_drop_reply | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 538 | – | – | `no_reply_message` | 0 | 0 | 0 | 0 | 3 |
| 5501 | code-version-bump | coding | local_delegate | partition_drop_reply | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 2844 | – | – | – | 0 | 1 | 0 | 1 | 0 |
| 5501 | code-version-bump | coding | a2a_delegate | partition_drop_reply | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 2940 | – | – | – | 0 | 1 | 0 | 1 | 0 |
| 5501 | code-version-bump | coding | checkpoint_relocate | partition_drop_reply | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 3603 | – | – | – | 0 | 1 | 0 | 1 | 0 |
| 5501 | code-version-bump | coding | cross_framework_reconstruct | partition_drop_reply | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 5501 | code-guard-config | coding | keep_on_origin | origin_preempted | yes | incomplete | `origin_preempted_no_transfer` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 5501 | code-guard-config | coding | restart_on_destination | origin_preempted | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 547 | – | – | – | 0 | 0 | 0 | 0 | 1 |
| 5501 | code-guard-config | coding | restart_stable_ids | origin_preempted | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 547 | – | – | – | 0 | 0 | 0 | 0 | 1 |
| 5501 | code-guard-config | coding | local_delegate | origin_preempted | no | refused | `incompatible_state:effect+replace` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 5501 | code-guard-config | coding | a2a_delegate | origin_preempted | no | refused | `incompatible_state:effect+replace` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 5501 | code-guard-config | coding | checkpoint_relocate | origin_preempted | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 1812 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 5501 | code-guard-config | coding | cross_framework_reconstruct | origin_preempted | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 5501 | code-line-limit | coding | keep_on_origin | crash_before_effect_commit | yes | incomplete | `origin_crashed_no_recovery` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 3 | – | 0 | 0 | 0 | 0 | 0 |
| 5501 | code-line-limit | coding | restart_on_destination | crash_before_effect_commit | yes | completed | – | no | no | 0/1 | 0 | 0 | 1 | 1 | 0 | 0 | 603 | – | 3 | – | 0 | 0 | 0 | 0 | 6 |
| 5501 | code-line-limit | coding | restart_stable_ids | crash_before_effect_commit | yes | completed | – | no | no | 0/1 | 0 | 0 | 1 | 1 | 0 | 0 | 603 | – | 3 | – | 0 | 0 | 0 | 0 | 6 |
| 5501 | code-line-limit | coding | local_delegate | crash_before_effect_commit | no | refused | `incompatible_state:check_contains+effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 3 | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 5501 | code-line-limit | coding | a2a_delegate | crash_before_effect_commit | no | refused | `incompatible_state:check_contains+effect` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 3 | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 5501 | code-line-limit | coding | checkpoint_relocate | crash_before_effect_commit | yes | completed | – | yes | yes | 1/1 | 0 | 0 | 0 | 0 | 0 | 0 | 1890 | – | 3 | – | 0 | 0 | 0 | 0 | 1 |
| 5501 | code-line-limit | coding | cross_framework_reconstruct | crash_before_effect_commit | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | 3 | `mode_unavailable` | – | – | – | – | – |
| 5501 | code-test-fixture | coding | keep_on_origin | partition_drop_request | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_transfer_channel` | 0 | 0 | 0 | 0 | 0 |
| 5501 | code-test-fixture | coding | restart_on_destination | partition_drop_request | yes | completed | – | no | yes | 0/0 | 0 | 1 | 0 | 0 | 0 | 0 | 830 | – | – | – | 0 | 1 | 0 | 1 | 2 |
| 5501 | code-test-fixture | coding | restart_stable_ids | partition_drop_request | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 830 | – | – | – | 0 | 1 | 0 | 1 | 2 |
| 5501 | code-test-fixture | coding | local_delegate | partition_drop_request | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 3354 | – | – | – | 0 | 1 | 0 | 1 | 0 |
| 5501 | code-test-fixture | coding | a2a_delegate | partition_drop_request | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 3482 | – | – | – | 0 | 1 | 0 | 1 | 0 |
| 5501 | code-test-fixture | coding | checkpoint_relocate | partition_drop_request | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 3319 | – | – | – | 0 | 1 | 0 | 1 | 0 |
| 5501 | code-test-fixture | coding | cross_framework_reconstruct | partition_drop_request | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 5501 | tools-restock-order | tools | keep_on_origin | stale_origin_returns | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_ownership_transfer` | 0 | 0 | 0 | 0 | 0 |
| 5501 | tools-restock-order | tools | restart_on_destination | stale_origin_returns | yes | completed | – | no | no | 0/0 | 1 | 1 | 1 | 0 | 0 | 1 | 414 | – | – | – | 0 | 0 | 0 | 0 | 3 |
| 5501 | tools-restock-order | tools | restart_stable_ids | stale_origin_returns | yes | completed | – | no | no | 0/0 | 1 | 0 | 1 | 0 | 0 | 1 | 414 | – | – | – | 0 | 0 | 0 | 0 | 3 |
| 5501 | tools-restock-order | tools | local_delegate | stale_origin_returns | no | refused | `incompatible_state:lookup` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `origin_remains_owner` | 0 | 0 | 0 | 0 | 0 |
| 5501 | tools-restock-order | tools | a2a_delegate | stale_origin_returns | no | refused | `incompatible_state:lookup` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `origin_remains_owner` | 0 | 0 | 0 | 0 | 0 |
| 5501 | tools-restock-order | tools | checkpoint_relocate | stale_origin_returns | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 1 | 1785 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 5501 | tools-restock-order | tools | cross_framework_reconstruct | stale_origin_returns | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 5501 | tools-travel-booking | tools | keep_on_origin | partition_drop_request | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_transfer_channel` | 0 | 0 | 0 | 0 | 0 |
| 5501 | tools-travel-booking | tools | restart_on_destination | partition_drop_request | yes | completed | – | no | yes | 0/0 | 0 | 1 | 0 | 0 | 0 | 0 | 754 | – | – | – | 0 | 1 | 0 | 1 | 1 |
| 5501 | tools-travel-booking | tools | restart_stable_ids | partition_drop_request | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 754 | – | – | – | 0 | 1 | 0 | 1 | 1 |
| 5501 | tools-travel-booking | tools | local_delegate | partition_drop_request | no | refused | `incompatible_state:effect+lookup` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 5501 | tools-travel-booking | tools | a2a_delegate | partition_drop_request | no | refused | `incompatible_state:effect+lookup` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 5501 | tools-travel-booking | tools | checkpoint_relocate | partition_drop_request | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 3221 | – | – | – | 0 | 1 | 0 | 1 | 0 |
| 5501 | tools-travel-booking | tools | cross_framework_reconstruct | partition_drop_request | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 5501 | tools-ticket-triage | tools | keep_on_origin | crash_before_effect_commit | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | 2 | `no_effect_intent_at_crash_step` | 0 | 0 | 0 | 0 | 0 |
| 5501 | tools-ticket-triage | tools | restart_on_destination | crash_before_effect_commit | no | completed | – | no | yes | 0/0 | 0 | 1 | 0 | 0 | 0 | 0 | 511 | – | 2 | `no_effect_intent_at_crash_step` | 0 | 0 | 0 | 0 | 3 |
| 5501 | tools-ticket-triage | tools | restart_stable_ids | crash_before_effect_commit | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 511 | – | 2 | `no_effect_intent_at_crash_step` | 0 | 0 | 0 | 0 | 3 |
| 5501 | tools-ticket-triage | tools | local_delegate | crash_before_effect_commit | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 2043 | – | 2 | `no_effect_intent_at_crash_step` | 0 | 0 | 0 | 0 | 0 |
| 5501 | tools-ticket-triage | tools | a2a_delegate | crash_before_effect_commit | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 2107 | – | 2 | `no_effect_intent_at_crash_step` | 0 | 0 | 0 | 0 | 0 |
| 5501 | tools-ticket-triage | tools | checkpoint_relocate | crash_before_effect_commit | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 1822 | – | 2 | `no_effect_intent_at_crash_step` | 0 | 0 | 0 | 0 | 0 |
| 5501 | tools-ticket-triage | tools | cross_framework_reconstruct | crash_before_effect_commit | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | 2 | `mode_unavailable` | – | – | – | – | – |
| 5501 | tools-calendar-hold | tools | keep_on_origin | origin_preempted | yes | incomplete | `origin_preempted_no_transfer` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 5501 | tools-calendar-hold | tools | restart_on_destination | origin_preempted | yes | completed | – | no | yes | 0/0 | 0 | 1 | 0 | 0 | 0 | 0 | 403 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 5501 | tools-calendar-hold | tools | restart_stable_ids | origin_preempted | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 403 | – | – | – | 0 | 0 | 0 | 0 | 2 |
| 5501 | tools-calendar-hold | tools | local_delegate | origin_preempted | no | refused | `incompatible_state:effect+lookup` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 5501 | tools-calendar-hold | tools | a2a_delegate | origin_preempted | no | refused | `incompatible_state:effect+lookup` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 5501 | tools-calendar-hold | tools | checkpoint_relocate | origin_preempted | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 1707 | – | – | – | 0 | 0 | 0 | 0 | 0 |
| 5501 | tools-calendar-hold | tools | cross_framework_reconstruct | origin_preempted | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
| 5501 | tools-refund-sim | tools | keep_on_origin | crash_after_effect_commit | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | 2 | `no_effect_intent_at_crash_step` | 0 | 0 | 0 | 0 | 0 |
| 5501 | tools-refund-sim | tools | restart_on_destination | crash_after_effect_commit | yes | completed | – | no | no | 0/0 | 2 | 3 | 2 | 0 | 0 | 0 | 493 | – | 2 | – | 0 | 0 | 0 | 0 | 6 |
| 5501 | tools-refund-sim | tools | restart_stable_ids | crash_after_effect_commit | yes | completed | – | no | no | 0/0 | 1 | 0 | 1 | 0 | 0 | 0 | 493 | – | 2 | – | 0 | 0 | 0 | 0 | 6 |
| 5501 | tools-refund-sim | tools | local_delegate | crash_after_effect_commit | no | refused | `incompatible_state:reserve` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 2 | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 5501 | tools-refund-sim | tools | a2a_delegate | crash_after_effect_commit | no | refused | `incompatible_state:reserve` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | 2 | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 5501 | tools-refund-sim | tools | checkpoint_relocate | crash_after_effect_commit | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 1833 | – | 2 | `no_effect_intent_at_crash_step` | 0 | 0 | 0 | 0 | 0 |
| 5501 | tools-refund-sim | tools | cross_framework_reconstruct | crash_after_effect_commit | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | 2 | `mode_unavailable` | – | – | – | – | – |
| 5501 | tools-inventory-audit | tools | keep_on_origin | partition_drop_reply | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | – | – | `no_transfer_channel` | 0 | 0 | 0 | 0 | 0 |
| 5501 | tools-inventory-audit | tools | restart_on_destination | partition_drop_reply | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 360 | – | – | `no_reply_message` | 0 | 0 | 0 | 0 | 2 |
| 5501 | tools-inventory-audit | tools | restart_stable_ids | partition_drop_reply | no | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 360 | – | – | `no_reply_message` | 0 | 0 | 0 | 0 | 2 |
| 5501 | tools-inventory-audit | tools | local_delegate | partition_drop_reply | no | refused | `incompatible_state:reserve` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 5501 | tools-inventory-audit | tools | a2a_delegate | partition_drop_reply | no | refused | `incompatible_state:reserve` | – | – | – | 0 | 0 | 0 | – | 0 | 0 | 0 | – | – | `attempt_ended_before_fault_point` | 0 | 0 | 0 | 0 | 0 |
| 5501 | tools-inventory-audit | tools | checkpoint_relocate | partition_drop_reply | yes | completed | – | yes | yes | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 3307 | – | – | – | 0 | 1 | 0 | 1 | 0 |
| 5501 | tools-inventory-audit | tools | cross_framework_reconstruct | partition_drop_reply | no | unavailable | `baseline_not_implemented` | – | – | – | – | – | – | – | – | – | – | – | – | `mode_unavailable` | – | – | – | – | – |
