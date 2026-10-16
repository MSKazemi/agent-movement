# Evaluation plan for reference tasks EV-A, EV-B and EV-C

**Status:** Design document: a proposed protocol with **no results**. Nothing here has been run, and the plan has not been registered with any external registry. Every expected effect below is a labelled **hypothesis**, not a finding.
**Date:** 2026-10-16. Web sources were accessed on 2026-10-16. Corpus items are cited by ID (`AMP-xxx` = [paper corpus](paper-corpus/README.md)).
**Tracks:** [issue #26](https://github.com/MSKazemi/agent-movement/issues/26). This covers the "Reproducible evaluation proposal" in [issue #1](https://github.com/MSKazemi/agent-movement/issues/1), which asks for three reference tasks: (A) single-agent tool use, (B) A2A-delegated researcher/implementer/reviewer, and (C) a task resumed after process interruption. Issue #1 asks to compare them against "a **deterministic non-agent baseline**, a **one-agent baseline**, and the movement baselines", and to capture "human interventions".
**Builds on:** [MobilityBench v0.1](mobilitybench-v0.1.md) (frozen fixtures, rubric and record schema) and [MobilityBench v0.2](mobilitybench-v0.2.md) (the same tasks with mid-step crashes, partitions and a stable-ID restart, issue #40), the [proposed MobilityBench experiment protocol](mobilitybench-experiment-protocol.md), the [scientific agenda](strategic-target-and-scientific-agenda.md) (PR #4) and the [economic evaluation methodology](economic-evaluation.md) (issue #36). **That methodology is the cost model. This plan only references it and does not repeat it.**

**Labels used:**

- **FACT** means verified in this repository's code (cited as `path::symbol`) or in a cited source.
- **ANALYSIS** means this project's interpretation.
- **HYPOTHESIS** means an untested prediction with a stated falsification condition.
- **Implemented** means it runs today on `main`. **Planned** means it does not exist yet and has a tracking issue where one exists.

## Identifiers

The three tasks are **EV-A**, **EV-B** and **EV-C**. Their hypotheses are numbered **EV-A-H1**, **EV-B-H1** and so on. These prefixes are new and do not clash with any identifier in the repository (checked with `git grep "EV-"` on 2026-10-16). Issue #34 replaced the bare question and stage labels in the agenda documents with prefixed IDs (`AM-`, `HQ-`, `SQ-`, `ST-` and others; see the [question ID crosswalk](question-id-crosswalk.md)), so this plan uses none of those bare labels.

Baselines keep their existing IDs:

- **B0–B4** are defined in `src/agent_movement/mobilitybench_v01.py::MODES` and in [MobilityBench v0.1](mobilitybench-v0.1.md#baseline-modes).
- **B1-stable** (`restart_stable_ids`, suite v0.2 only) is defined in `src/agent_movement/mobilitybench_v01.py::SUITE_MODE_SPECS` and in [MobilityBench v0.2](mobilitybench-v0.2.md#the-restart_stable_ids-baseline) (issue #40).
- **B5** (non-agent workflow) is the proposed arm from the [economic evaluation](economic-evaluation.md#4-arms-baselines).

No new baseline ID is introduced. The one-agent baseline of issue #1 is **B0 keep** applied to a multi-role task (see EV-B).

## 1. Overview: tasks, MobilityBench mapping and status

The workload families are `document`, `coding` and `tools` (FACT: `mobilitybench_v01.py::FAMILIES`). The modes are B0 `keep_on_origin`, B1 `restart_on_destination`, B2-local `local_delegate`, B2 `a2a_delegate`, B3 `checkpoint_relocate` and B4 `cross_framework_reconstruct` (FACT: `mobilitybench_v01.py::MODES`). The faults are `none`, `origin_preempted`, `effect_ack_lost`, `duplicate_delivery` and `stale_origin_returns` (FACT: `mobilitybench_v01.py::FAULT_KINDS`). Suite v0.2 keeps these and adds the mode B1-stable `restart_stable_ids` and the faults `crash_before_effect_commit`, `crash_after_effect_commit`, `partition_drop_request`, `partition_drop_reply` and `partition_delay` (FACT: `mobilitybench_v01.py::SUITE_SPECS`, `::FAULT_KINDS_V02`, `::modes_for`).

| Task | Question it answers | v0.1 families used | v0.1 modes and faults used | Implemented today | Planned |
| --- | --- | --- | --- | --- | --- |
| **EV-A** single-agent tool use | Is a single agent better than a deterministic workflow on the same frozen tool-use cases, and what does it cost in human interventions and review? | `tools` (primary), plus `coding` and `document` | B0 under `none`, `effect_ack_lost` and `duplicate_delivery` | Frozen plans executed by a **deterministic interpreter** (`EXECUTOR = "deterministic-interpreter-v0.1"`, `MODEL = "none"`), the fenced effect gateway, the rubric and the `neg-instruction-in-data` placeholder | An LLM executor (v0.1 "Next versions: Later"); the B5 arm as a scored mode; adversarial variants; the intervention fields |
| **EV-B** A2A-delegated researcher / implementer / reviewer | Does splitting work across three delegated roles beat one agent doing all roles, and at what transfer, review and intervention cost? | `document` (researcher), `coding` (implementer; plans end with an `open_review` effect) | B0 as the one-agent baseline, B2-local, B2 (scored only with the `a2a` extra) | B2-local delegates only the pure ops `word_count` and `sha256` (`core.py::validate_envelope`), so it refuses role work with `incompatible_state`. B2 `a2a_delegate` sends the same envelope over the A2A v1 adapter ([a2a-adapter.md](a2a-adapter.md)) and is scored when the `a2a` extra is installed ([issue #31](https://github.com/MSKazemi/agent-movement/issues/31)); without it, it is an explicit unavailable record. It refuses the same role work | A multi-role task family (needs a new suite version, because `FAMILIES` is frozen) and a contract that lets B2 carry role work; interoperability ([issue #28](https://github.com/MSKazemi/agent-movement/issues/28)); cross-agent injection variants ([issue #35](https://github.com/MSKazemi/agent-movement/issues/35)) |
| **EV-C** resume after process interruption | After the origin dies, which continuation keeps correctness, constraints and effect identity, and how many human reconcile decisions remain? | All three | B0, B1 and B3 under `origin_preempted` (also `stale_origin_returns`, `effect_ack_lost`) | B0 and B1 are scored. B3 `checkpoint_relocate` is scored when the `relocation` extra is installed ([#31](https://github.com/MSKazemi/agent-movement/issues/31)), with movement only at the movement point; without the extra it is an explicit unavailable record. Separately, the relocation fault matrix ([checkpoint-relocation.md](checkpoint-relocation.md), `relocation_demo.py`, `[relocation]` extra) adds crashes at every transition and operator reconciliation of parked opaque effects ([#30](https://github.com/MSKazemi/agent-movement/issues/30)). [MobilityBench v0.2](mobilitybench-v0.2.md) ([#40](https://github.com/MSKazemi/agent-movement/issues/40)) adds one seeded crash inside an effect step, one-message partitions and the B1-stable `restart_stable_ids` arm on the same 18 tasks | Several interruption points per case on new held-out cases; crashes inside pure steps, inside the transfer protocol and during recovery (v0.2 "Next versions"); reconcile interventions counted in MobilityBench records |

**ANALYSIS (central caveat).** In v0.1 the "agent" is a scripted interpreter that is **given** the frozen plan. So v0.1's B0 is itself a deterministic, non-agent workflow, but one that holds an **oracle plan** taken from the fixture. It is an upper bound for B5, not a fair B5. A fair B5 has to be written from the task specification alone, without seeing the evaluation cases (see §3.2). None of the three tasks can test an agent until an LLM executor exists.

## 2. Literature basis for the metric and baseline choices

| Choice | Grounding (FACT from the cited source) | How this plan uses it (ANALYSIS) |
| --- | --- | --- |
| A **deterministic non-agent baseline** is mandatory | Kapoor et al. (2024), §2.3: "'State-of-the-art' agent architectures for HumanEval do not outperform simple baselines", and "papers proposing new agents haven't adequately tested simple baselines". Xia et al. (2024), *Agentless*: "the simplistic Agentless is able to achieve both the highest performance (32.00%, 96 correct fixes) and low cost ($0.70)" on SWE-bench Lite. | Every task scores B5 alongside the agent arms. Without it, a positive result shows only that one agent arm beat another (the same argument as the [economic evaluation](economic-evaluation.md#4-arms-baselines)). |
| A **one-agent baseline** for multi-agent work | Cemri et al. (2025, AMP-042) start from the observation that multi-agent LLM systems often show minimal gains on benchmarks, and derive 14 failure modes in 3 categories, "(i) system design issues, (ii) inter-agent misalignment, and (iii) task verification" (kappa = 0.88). ChatDev (AMP-029) and MetaGPT (AMP-032) are role-specialized multi-agent designs. | EV-B compares the three-role arm with one agent doing all roles (B0), and uses the three failure categories as labels for failed EV-B attempts. |
| **Costs reported jointly with accuracy** | Kapoor et al. (2024): "useful agent evaluations must control for cost". | Cost per correct completion, the fallback adjustment and the Pareto frontier are taken unchanged from the [economic evaluation](economic-evaluation.md#3-composite-metrics-and-analysis-plan). |
| **Reliability over repeated trials** | Yao et al. (2024), τ-bench: "a new metric (pass^k) to evaluate the reliability of agent behavior over multiple trials". | pass^k is reported for stochastic executors only. v0.1 is deterministic, so its repeats test reproducibility only. |
| **Utility and attack success under adversarial variants** | Debenedetti et al. (2024, AMP-039), AgentDojo §3.4: benign utility is "the fraction of user tasks that the model solves in the absence of any attacks"; utility under attack is computed over "security cases (i.e., a pair of user task and injection task)"; the targeted attack success rate is "the fraction of security cases where the attacker's goal is met". InjecAgent (AMP-031) and ToolEmu (AMP-081) evaluate tool-agent risk. | Adversarial variants are paired with their benign case. Utility under attack and the attack success rate use the security-case denominator. |
| **Human interventions as a metric** | Parasuraman, Sheridan and Wickens (2000) model automation as applying to four functions, "1) information acquisition; 2) information analysis; 3) decision and action selection; and 4) action implementation", each "across a continuum of levels from low to high, i.e., from fully manual to fully automatic". California regulation 13 CCR § 227.50 makes autonomous-vehicle testers report each "disengagement": "a deactivation of the autonomous mode when a failure of the autonomous technology is detected" or when safe operation requires the test driver to "take immediate manual control of the vehicle". | §3.4 defines an intervention by the function it touches (decision versus action) and separates **planned** approvals from **unplanned** takeovers, which is the distinction a disengagement count makes. |
| **Measured, not self-reported, human time** | Becker et al. (2025) and Sadowski et al. (2018), as cited in the [economic evaluation](economic-evaluation.md#2-cost-model). | Review cost is measured by instrumentation. This plan adds only *what* is reviewed in each task. |
| **Paired analysis and clustered uncertainty** | Miller (2024) recommends "computing clustered standard errors" when questions come in related groups, "statistical inference on the question-level paired differences" when two models are compared, and "power analysis" to decide whether an eval can test a hypothesis. | Arms share cases, faults and seeds. Comparisons use per-case paired differences, clustered by base case (an adversarial variant and its benign case form one cluster). Case counts come from a pilot power analysis. |
| **Frozen, auditable cases** | SWE-bench (Jimenez et al., 2024) builds "2,294 software engineering problems drawn from real GitHub issues and corresponding pull requests", each graded by tests. | Every case has an executable oracle (the v0.1 rubric and digests), not a model or human judgement, wherever the task allows it. |
| **Checkpoint-restore hazards** | Zheng et al. (2026, AMP-070), ACRFence (arXiv abstract): LLM agents "re-synthesize subtly different requests after restore", "Servers treat these re-generated requests as new", and the paper identifies "two attack classes, Action Replay and Authority Resurrection". | These are the adversarial variants for EV-C. |

## 3. Shared design

### 3.1 Frozen-case design

- **Unit:** a *case* is one frozen task: input, initial constraints, plan or goal, session events, movement or interruption point, and ground truth. This is the v0.1 task schema (`mobilitybench_v01.py::TASK_FIELDS`), extended per task below.
- **Size:**
  - Issue #1 asks for 30–100 frozen cases per task. The protocol starts at 30 per workload, with "at least five designed negative/security cases", and calls that "an engineering starting point, not a statistical-power claim".
  - Plan: a pilot of at least 30 benign cases per EV task, plus adversarial variants (§3.3).
  - The final count is set by a power analysis on the pilot variance (Miller 2024). v0.1 has 18 tasks (6 per family) and 12 negative fixtures, so it is below this size for every EV task (FACT: [frozen release](mobilitybench-v0.1.md#frozen-release)).
- **Split:** each task has a **development** split, which B5 workflows and executor prompts may be tuned on, and a **held-out** split, which nobody reads before the run. B5 is written against the development split and the task specification only.
- **Freezing:** v0.1's rule applies. A frozen release is never edited in place. Any change to a case, rubric or interpreter semantics needs a new suite version and a new fixture directory, with SHA-256 digests regenerated by `tools/mobilitybench_freeze.py`. A new family (EV-B) also needs a new suite version, because `FAMILIES` is part of the frozen interpreter.
- **Registration (planned):** OSF describes preregistration as "posting a time-stamped, read-only version of your study plan to a public repository" before "beginning data collection or analysis". This plan, the case digests, the fault schedule, the fallback rules and the price, labour and severity tables required by the [economic evaluation](economic-evaluation.md#35-uncertainty-and-sensitivity) are registered before the first scored run. Until then, every reference to this plan says "proposed".

### 3.2 Baselines (all tasks)

| Arm | Definition for this plan | Status |
| --- | --- | --- |
| **B0 keep** | One executor runs the whole task, with no movement and no delegation. In EV-B this **is the one-agent baseline**: a single executor plays every role. | Implemented (deterministic interpreter only) |
| **B1 restart** | The destination restarts from the original request, without session context | Implemented |
| **B1-stable restart** | B1, but the destination re-issues each effect under the origin's deterministic effect ID, so the gateway deduplicates it | Implemented in MobilityBench v0.2 only, as mode `restart_stable_ids` (FACT: `mobilitybench_v01.py::run_restart_stable_ids`; [v0.2](mobilitybench-v0.2.md#the-restart_stable_ids-baseline)) |
| **B2-local** | In-process PR #6 delegate. Pure ops only. | Implemented |
| **B2 A2A delegate** | Delegation over the official A2A v1 SDK | Implemented ([a2a-adapter.md](a2a-adapter.md)). Scored as MobilityBench mode `a2a_delegate` when the `a2a` extra is installed; otherwise an explicit unavailable record ([#31](https://github.com/MSKazemi/agent-movement/issues/31)) |
| **B3 relocate** | Same-runtime checkpoint relocation with origin fencing | Implemented, with a separate fault matrix ([checkpoint-relocation.md](checkpoint-relocation.md)). Scored as MobilityBench mode `checkpoint_relocate` when the `relocation` extra is installed; otherwise an explicit unavailable record ([#31](https://github.com/MSKazemi/agent-movement/issues/31)) |
| **B4 reconstruct** | Cross-framework reconstruction | Unavailable; not scheduled |
| **B5 non-agent workflow** | A deterministic script or workflow written from the task specification and the development split only. It calls the same simulated tools through the same gateway. It may stop and ask a human, and those requests are counted as interventions (§3.4). | **Planned.** Proposed mode `non_agent_workflow` ([economic evaluation](economic-evaluation.md#5-mapping-to-mobilitybench-record-fields)) |

Rules carried over from v0.1:

- Unavailable arms are emitted and reported, and are never scored as success or failure.
- All arms of one (case, fault, seed) get the same fault, so comparisons are paired.

Two further rules are added here:

- **Same budget, same tools.** Every arm gets the same tool set, step budget and, for LLM executors, token budget, and these are recorded in `run_version`.
- **Pre-declared fallback.** Every arm pre-declares what happens to a refused or incomplete attempt, as the [economic evaluation](economic-evaluation.md#32-fallback-adjusted-cost) requires.

### 3.3 Adversarial variants (all tasks)

Each adversarial variant is **derived from one benign case** and frozen with it. The pair is one analysis cluster. Variant kinds reuse the v0.1 vocabulary where it exists:

- `session_event` rules arriving mid-task;
- `forbid_tool` and `allowed_recipients` policies;
- the five v0.1 fault kinds, and the two crash and three partition kinds of v0.2;
- the v0.1 negative-fixture attacks: `data_not_instructions`, canary, forged destination, movement-ID reuse, stale origin, revocation and tampered fixture.

The variant kinds specific to each task are listed in that task's section.

### 3.4 Human interventions: definition and measurement

**Definition (proposed).** An *intervention* is any point at which a human must supply a decision or take an action before the attempt can continue or finish. Each one is classified on two axes:

- **Planned or unplanned.** A *planned* intervention is an approval checkpoint that the case or the arm declares in advance, for example an approval before an external effect or before a movement. An *unplanned* intervention is any other request. This is the agent analogue of a disengagement: a human takes over because the automation failed or safety required it.
- **Kind**, following the four automation functions of Parasuraman et al. (2000):
  - `clarify`: the human supplies information;
  - `correct`: the human edits an analysis or an output;
  - `approve` / `deny`: the human makes a decision at a gate;
  - `takeover` / `abort`: the human performs or stops an action;
  - `reconcile`: the human resolves an `unknown` effect outcome, as an operator does for parked opaque effects in the relocation experiment ([issue #30](https://github.com/MSKazemi/agent-movement/issues/30));
  - `fallback`: the human routes a refused or incomplete attempt to its pre-declared fallback arm.

**Measurement without human participants (planned).**

- The LLM-free harness uses a **scripted operator**: a deterministic policy, frozen with the cases, that answers every intervention request and logs it. Counts are then deterministic and reproducible like every other v0.1 field. The script supplies answers only, so it measures *how often* a human is needed, not human time or human error.
- Human review time and the cost of interventions come from instrumented sessions with consenting participants. Those are the human-review and incident terms of the [economic evaluation](economic-evaluation.md#2-cost-model), which also notes that ethics review may be needed. This plan does not redefine them.

**Proposed record fields.** These are not in the v0.1 schema (FACT: `mobilitybench_v01.py::METRIC_KEYS` has no intervention field):

- `interventions_planned` and `interventions_unplanned` (counts);
- `intervention_kinds` (a count per kind);
- `first_unplanned_step` (the plan step, or `null`).

They complement the economic evaluation's proposed `human_review_seconds`, `approvals_requested`, `approvals_granted`, `reviewer_role` and `review_stage`, which are not repeated here.

**Proxies available today (ANALYSIS).** v0.1 already records events that would require a human in a real deployment:

- `outcome = refused` or `incomplete`: a `fallback` intervention;
- `unknown_events`: a potential `reconcile` intervention. v0.1 reconciles them automatically through its gateway lookup, so they are proxies, not interventions;
- the `known_gap` verdicts on security records.

These proxies are reported as proxies and never as intervention counts.

### 3.5 Denominators

The same rules apply to every task:

- **Attempt-level rates** (`task_correct`, completion, refusal, incompleteness, interventions per attempt) divide by **all scored attempts** of an arm, *including* refused and incomplete ones. Unavailable-arm records are counted and shown, but excluded from scored denominators. This is the v0.1 convention.
- **Constraint retention** divides by the constraints of **completed** attempts (`constraints_preserved / constraints_total`), as in v0.1. It is always shown next to the completion count, so that an arm cannot raise it by refusing.
- **Effect counts** (`duplicate_effects`, `unexpected_effects`, `policy_violations`, `stale_commits_accepted`) are totals over **all** attempts, including incomplete ones. They are also reported per 100 attempts.
- **Utility under attack** and the **attack success rate** divide by the number of **security cases** (benign case × attack variant), following AgentDojo. **Benign utility** divides by benign cases.
- **Cost per correct completion** uses `task_correct` as its denominator and is undefined (not zero or infinity) when that is 0. This follows the [economic evaluation](economic-evaluation.md#31-primary-metric-cost-per-correct-completion).
- **pass^k** divides by cases, with *k* fixed in the registration.
- **Planned interventions** are reported per attempt. **Unplanned interventions** are reported per attempt *and* per correct completion, because an arm that needs a human to finish has not finished autonomously.

### 3.6 Analysis

- **Primary comparisons** use paired differences per (case, fault, seed) between an arm and B5, and between an arm and B0, with standard errors clustered by base case (Miller 2024).
- **Confidence intervals** are reported only for stochastic executors. For the deterministic interpreter, repeats test reproducibility, and every percentage describes the fixture set only. This is v0.1's [statistical-conclusion caveat](mobilitybench-v0.1.md#validity-threats).
- **Multiple comparisons:** each task has at most three primary hypotheses. Every other comparison is labelled exploratory, following the protocol's rule: "Do not retrofit hypotheses after viewing results".
- **Raw rows:** every per-attempt row is published, including refusals, incompletes and unavailable arms.

## 4. EV-A: single-agent tool use

**Purpose.** EV-A is the reference task with no movement at all. It tests issue #1's research question 4, "Is agent B actually better than a deterministic workflow or a single agent on the same test suite?", in its simplest form, and it gives the per-case baseline that EV-B and EV-C are compared against.

**Mapping to MobilityBench v0.1.**

- The closest family is `tools`: inventory `lookup`, `reserve` (an effect that changes state) and `notify`, with `forbid_tool` and `allowed_recipients` policies. `coding` and `document` cases are included so that tool use is not confounded with one domain.
- Only B0 applies, under the faults `none`, `effect_ack_lost` and `duplicate_delivery`. `origin_preempted` and `stale_origin_returns` belong to EV-C.
- **Implemented:** the frozen plans, the deterministic interpreter, the fenced effect gateway, the rubric, and the negative fixtures `neg-instruction-in-data`, `neg-unknown-effect` and `neg-effect-payload-conflict`.
- **Planned:**
  - an LLM executor that receives the **goal and the tool descriptions, not the plan**;
  - B5 as a scored mode;
  - the adversarial variants below;
  - the intervention fields.

**Frozen cases (planned).** Each case adds a natural-language goal and tool descriptions to the v0.1 task schema. The frozen plan stays as the oracle that the ground truth is computed from, and it is hidden from LLM executors. At least 30 benign cases, spread over the three families, plus variants.

**Adversarial variants.**

1. **Instruction in data:** tool output or input text contains an instruction to call a forbidden tool or a non-allowed recipient. This is AgentDojo's security case, and it generalizes `neg-instruction-in-data`, which v0.1 calls a placeholder that "says nothing about LLM executors".
2. **Mid-session policy change:** a session event adds `forbid_tool` before the effect step.
3. **Ambiguous acknowledgement:** `effect_ack_lost` on the first commit.
4. **Under-specified goal:** the correct response is to ask (a `clarify` intervention) or to abstain, not to act.

**Metrics.**

- From v0.1: `task_correct`, `output_correct`, `constraints_preserved/constraints_total`, `policy_violations`, `duplicate_effects`, `unexpected_effects`, `missing_effects`, `unknown_events/reconciled_events`, `steps_executed`.
- New:
  - **unsafe action attempts**: gateway requests that would violate an active policy, counted whether or not they were committed. The protocol asks for "forbidden/duplicate synthetic tool *commits* (not only client attempts)", and v0.1 counts commits only;
  - benign utility, utility under attack and attack success rate;
  - pass^k;
  - interventions (§3.4);
  - review cost and cost per correct completion ([economic evaluation](economic-evaluation.md)).
- **What a human reviews:** the proposed effect payload before commit (planned `approve`) and the final output.

**Baselines.**

- **B5:** the primary comparison.
- **B0 with the oracle plan:** v0.1's interpreter, as an upper bound for B5.
- **B0 with an LLM executor:** the agent under test.

**Hypotheses.**

- **EV-A-H1 (HYPOTHESIS):** on cases whose steps are fully determined by the specification, B5 reaches a `task_correct` rate no lower than the LLM executor, at a lower cost per correct completion.
  - *Falsified if* the paired difference in `task_correct` favours the LLM executor on held-out fully-specified cases at an equal or lower cost per correct completion.
  - Grounding: Kapoor et al. 2024; Xia et al. 2024.
- **EV-A-H2 (HYPOTHESIS):** the LLM executor's advantage over B5, if any, is concentrated in cases with mid-session events or under-specified goals, and it costs unplanned interventions.
  - *Falsified if* the advantage is spread evenly across case types, or if it comes with no more unplanned interventions than B5.
- **EV-A-H3 (HYPOTHESIS):** instruction-in-data variants lower utility under attack below benign utility for the LLM executor, but not for B5, which never interprets data as instructions.
  - *Falsified if* utility under attack is not lower than benign utility for the LLM executor, or if B5 shows the same drop.

**Validity threats.**

- **Construct:**
  - B5 quality depends on author effort. Authoring time is recorded as a fixed cost, as the economic evaluation requires, and B5 is frozen before the held-out split is opened.
  - "Unsafe attempt" depends on the gateway's view of active policies.
- **Internal:** the same project writes the cases, B5 and the executor prompts. Mitigations are the held-out split and B5 being frozen before the held-out split is opened.
- **External:** simulated tools only; no real APIs or latency.

## 5. EV-B: A2A-delegated researcher / implementer / reviewer

**Purpose.** EV-B tests whether splitting a task across three delegated roles improves outcomes over one agent doing everything, and how much transfer, review and intervention it costs. It is the multi-agent instance of the agenda's comparison of "move, restart, keep executing, and ordinary A2A delegation".

**Roles.**

- The **researcher** extracts and condenses source sections. This is v0.1 `document` work.
- The **implementer** applies constrained edits and runs the `check_contains` test. This is v0.1 `coding` work.
- The **reviewer** accepts or rejects the implementer's change before the `open_review` effect commits.

Each role boundary is a delegation from an orchestrator, which keeps ownership of the user's intent (README, "Proposed flow").

**Mapping to MobilityBench v0.1.**

- **Families:** `document` and `coding`. v0.1 has no multi-role family. Its coding plans end with an `open_review` effect (FACT: 6 `open_review` effects in `tasks.jsonl`), but the review is a scripted effect, not a reviewing agent.
- **Modes:**
  - B0 is the one-agent baseline.
  - B2-local is implemented but can carry only `word_count` and `sha256` tasks (FACT: `core.py::validate_envelope`), so v0.1 refuses role work with `incompatible_state:<ops>`. v0.1 refused 36 of 54 B2-local attempts this way ([pilot observations](mobilitybench-v0.1.md#pilot-observations-harness-020-2026-10-16-release-920e9a2f)).
  - B2 `a2a_delegate` is scored only when the `a2a` extra is installed, and is otherwise an explicit unavailable record ([#31](https://github.com/MSKazemi/agent-movement/issues/31)). It carries the same envelope as B2-local, so it refused the same 36 of 54 attempts in the pilot.
- **Implemented:**
  - the A2A v1 adapter on the official SDK, which proves "DELEGATION, not migration" of one allowlisted pure task, unauthenticated ([a2a-adapter.md](a2a-adapter.md));
  - peer authentication before disclosure ([peer-authentication.md](peer-authentication.md));
  - the negative fixtures `neg-forged-destination`, `neg-movement-id-reuse`, `neg-oversized-delegate` and `neg-private-delegate` (a known gap: disclosure before refusal).
- **Planned:**
  - a new multi-role family in a new suite version;
  - a delegation contract that can carry role inputs and artifacts;
  - `a2a_delegate` scored on the multi-role family, which needs that contract (v0.1 scores it on the pure-op envelope only, [#31](https://github.com/MSKazemi/agent-movement/issues/31));
  - independent interoperability ([#28](https://github.com/MSKazemi/agent-movement/issues/28));
  - cross-agent injection fixtures ([#35](https://github.com/MSKazemi/agent-movement/issues/35)).

**Frozen cases (planned).** Each case is a research-then-implement-then-review chain over synthetic sources and a toy file tree. It has:

- a ground-truth output;
- a ground-truth review verdict;
- for a subset of cases, a **seeded defect** that the implementer is scripted or prompted to introduce, so that the reviewer's verdict can be scored against a known answer.

At least 30 benign chains, plus variants.

**Adversarial variants.**

1. **Injected instruction in a delegated artifact:** the researcher's output carries an instruction aimed at the implementer or the reviewer. This is the cross-agent injection of issue #35. Prompt Infection (AMP-072) shows that an injected prompt can copy itself from agent to agent in a multi-agent system.
2. **Forged or mismatched destination:** this generalizes `neg-forged-destination`.
3. **Rubber-stamp reviewer:** the reviewer approves everything. This tests whether the metrics can tell a reviewer from no reviewer.
4. **Oversized or private state:** the role input exceeds the contract, or is classified `private`.
5. **Duplicate delivery** of a role task. This is v0.1's `duplicate_delivery`.

**Metrics.**

- From v0.1: `task_correct`, constraints, effect counts, `transfer_bytes`, `transfer_messages`, `sensitive_transfers`, and refusal reasons.
- New:
  - **seeded-defect detection rate**: reviewer rejections ÷ cases with a seeded defect;
  - **false rejection rate**: rejections ÷ defect-free cases;
  - **failure category** of each failed attempt, labelled with the three categories of Cemri et al. (2025);
  - interventions (§3.4);
  - human review cost of the final artifact.
- The in-loop *agent* reviewer is **not** human review, and its cost is compute, not the human-review term of the [economic evaluation](economic-evaluation.md#2-cost-model).

**Baselines.**

- **B0:** one executor plays all three roles. This is issue #1's one-agent baseline.
- **B5:** a deterministic pipeline: scripted extraction, scripted edit, test-based review.
- **B2-local**, scored only on the delegable subset and reported with its refusals.
- **B2 A2A**, when the `a2a` extra is installed (otherwise reported as unavailable).

**Hypotheses.**

- **EV-B-H1 (HYPOTHESIS):** at an equal per-attempt budget, the three-role delegated arm does not exceed B0 in `task_correct`, and has a higher cost per correct completion.
  - *Falsified if* the paired `task_correct` difference favours delegation at an equal or lower cost per correct completion.
  - Grounding: AMP-042's starting observation of minimal multi-agent gains.
- **EV-B-H2 (HYPOTHESIS):** a role-separated reviewer detects seeded defects at a higher rate than the same executor reviewing its own output in B0.
  - *Falsified if* detection rates do not differ on the seeded-defect subset, or if the gain comes only with a higher false rejection rate.
- **EV-B-H3 (HYPOTHESIS):** injected instructions in delegated artifacts reach effect-committing roles more often than injected instructions in single-agent tool output (EV-A), because each role boundary adds an untrusted input.
  - *Falsified if* the attack success rate in EV-B is not higher than in the matched EV-A variant.

**Validity threats.**

- **Construct:**
  - Seeded defects are authored, so they may be easier or harder than real defects.
  - Role prompts can encode the answer.
  - The A2A arm measures one SDK talking to itself until issue #28 lands.
- **Internal:**
  - B0 and the delegated arm must use the same model and the same total budget. Otherwise the comparison measures budget, not structure.
- **External:**
  - Three fixed roles are one point in a large design space (ChatDev, MetaGPT).

## 6. EV-C: resume after process interruption

**Purpose.** EV-C tests what continuation preserves after the process doing the work dies mid-task: correctness, session-context constraints, effect identity and ownership. It is the closest task to the project's core claim, and the one where B3 is the decisive comparator. v0.1 scores B3 only when the `relocation` extra is installed, and only with movement at a single, clean step boundary.

**Mapping to MobilityBench v0.1.**

- **Families:** all three.
- **Faults:** `origin_preempted` at the movement point is the interruption. `stale_origin_returns` and `effect_ack_lost` are the hazards after the interruption.
- **Modes:**
  - B0 is incomplete under pre-emption by construction.
  - B1 completes, but hears only post-movement session events and issues fresh effect IDs.
  - B2-local cannot survive pre-emption, because ownership never moves.
  - B3 is scored when the `relocation` extra is installed and is otherwise an explicit unavailable record ([#31](https://github.com/MSKazemi/agent-movement/issues/31)). It fails over from the durable checkpoint under pre-emption.
- **Implemented:**
  - B0 and B1 scored on the 18 frozen tasks, and B3 too when the `relocation` extra is installed;
  - the fault schedule `mobilitybench_v01.py::fault_schedule`;
  - fencing and deduplication evidence fields;
  - the negative fixtures `neg-stale-origin` and `neg-revocation-not-at-effect` (a known gap: "The gateway checks epochs, not grants"). The frozen case revokes with the static `Approval.revoked` flag; a runtime revocation by a signed notice is rechecked at the core effect commit (issue #38, `core.py::EffectGateway.commit`), and v0.2's `neg-runtime-revocation-at-effect` passes;
  - in [MobilityBench v0.2](mobilitybench-v0.2.md) ([#40](https://github.com/MSKazemi/agent-movement/issues/40)), on the same 18 tasks: a seeded crash inside an effect step (before the commit reaches the ledger, or after it is durable but before the acknowledgement), the three one-message partitions, the B1-stable arm, and the new record fields `crash_step`, `fault_not_applied_reason`, `effect_id_conflicts`, `messages_dropped`, `messages_delayed` and `retries` (FACT: `mobilitybench_v01.py::V02_RECORD_FIELDS`);
  - **separately**, a 30-row crash and duplicate fault matrix for same-runtime LangGraph relocation, including opaque-tool rows that end `reconcile_required` (FACT: `relocation.py`, `relocation_demo.py`);
  - **separately**, 9 operator-reconciliation rows in which an operator resolves those parked effects as `confirmed_done` or `confirmed_absent`. Each decision is fenced by the ownership epoch and appended to a `reconciliation_events` audit log, but it is not verified: a false decision loses or duplicates the effect (FACT: `relocation.py::Coordinator.reconcile`, `relocation_demo_reconcile.py`; `tests/test_relocation_reconcile.py`; [checkpoint-relocation.md](checkpoint-relocation.md#operator-reconciliation-of-parked-effects-issue-30)). These are recorded `reconcile` events in the relocation experiment, not fields of MobilityBench records.
- **Planned:**
  - several interruption points per case, crashes inside pure steps and during recovery, and longer partitions (v0.2 crashes once per attempt, only inside effect steps, and each partition acts once with one successful retry; [v0.2 validity threats](mobilitybench-v0.2.md#validity-threats));
  - `reconcile` intervention counts in MobilityBench records. Operator reconciliation exists only in the relocation experiment ([#30](https://github.com/MSKazemi/agent-movement/issues/30)), and v0.1 still reconciles `unknown` effects automatically through its gateway lookup.

**Frozen cases (planned).** The v0.1 task schema with **several interruption points per case**: before, between and after effects, and while an effect's outcome is unknown. Session events are placed before and after each point. At least 30 benign cases.

**Adversarial variants.**

1. **Action replay:** the resumed run re-generates an effect request with a slightly different payload (Zheng et al. 2026, AMP-070). v0.1's `neg-effect-payload-conflict` covers the same-ID case only.
2. **Authority resurrection:** a grant is revoked between checkpoint and resume. This extends `neg-revocation-not-at-effect`.
3. **Stale origin returns** after the interruption. This extends `neg-stale-origin`.
4. **Opaque tool:** the outcome of a commit is unknowable after the crash, so a human must reconcile it.
5. **Tampered checkpoint:** a checkpoint or artifact whose digest does not match. This extends `neg-tampered-fixture`.

**Metrics.**

- From v0.1: completion, `task_correct`, constraint retention for session events heard before the interruption, `duplicate_effects`, `stale_commits_fenced` / `stale_commits_accepted`, `unknown_events` / `reconciled_events`, `steps_reexecuted` and `transfer_bytes`.
- From the protocol: **safe continuation** = "target correct **and** no forbidden action **and** ownership invariant respected", and recovery success.
- New:
  - `reconcile` interventions per attempt;
  - effects left `unknown` at the end of the attempt;
  - **semantic loss**: constraints or context fields present before the interruption and absent after it.

**Baselines.**

- **B0:** a lower bound under pre-emption.
- **B1:** restart.
- **B1 with stable IDs:** implemented in v0.2 as `restart_stable_ids` (B1-stable, #40).
- **B3:** relocate.
- **B5:** a workflow-engine-style deterministic resume from the last completed step. It is still a non-agent arm. Durable-execution systems of this kind are compared in the [research landscape](research-landscape.md#durability-langgraph-and-temporal).

**Hypotheses.**

- **EV-C-H1 (HYPOTHESIS):** on a new held-out case set with interruption points inside the plan, B1 loses pre-interruption session constraints and duplicates pre-interruption effects, and B3 does neither.
  - *Falsified if* B3's constraint retention or duplicate-effect count is not better than B1's on paired cases.
  - The v0.1 pilot observed both sides on its own 18 tasks, with movement only at the movement point ([observations](mobilitybench-v0.1.md#pilot-observations-harness-020-2026-10-16-release-920e9a2f)): B1 kept 12/30 constraints with 30 duplicate effects, and B3 (with the `relocation` extra) kept 30/30 with 0 duplicates. B3's result holds by construction, because its checkpoint carries the interpreter's complete state. Neither observation is evidence for this hypothesis on new cases with interruption points inside the plan.
  - v0.2 places one seeded crash inside an effect step of the same 18 tasks ([pilot observations](mobilitybench-v0.2.md#pilot-observations-harness-030-2026-10-16-release-2408da9a)). Over all v0.2 faults, B1 kept 17/50 constraints with 61 duplicate effects and B3 (with the `relocation` extra) 50/50 with 0. On the 18 crash-scheduled attempts per mode, B1 completed all 18 but was correct on 1, and B3 was correct on all 18. B3's result again holds by construction, and these are the v0.1 tasks, not a held-out set, so they are not evidence for this hypothesis either.
- **EV-C-H2 (HYPOTHESIS):** B3 does not reduce `reconcile` interventions to zero. Opaque-tool cases still need a human decision, because no lookup can resolve them.
  - *Falsified if* B3 resolves opaque-tool cases without a human decision **and** without a duplicate or a lost effect.
  - The relocation experiment's reconciliation rows are consistent with this by design, not as evidence: a parked opaque effect is resumed only after an operator decision, and the decision's correctness depends on the operator ([checkpoint-relocation.md](checkpoint-relocation.md#trust-assumption-a-human-in-the-loop)).
- **EV-C-H3 (HYPOTHESIS):** restart with stable effect IDs removes most of B1's duplicate effects but none of its lost session constraints.
  - *Falsified if* stable IDs leave duplicate effects unchanged, or also restore the constraints.
  - v0.2 measured this on the v0.1 tasks, not on held-out cases ([pilot observations](mobilitybench-v0.2.md#pilot-observations-harness-030-2026-10-16-release-2408da9a), 90 attempts per arm): B1 committed 61 duplicate effects and B1-stable 0; B1 kept 17/50 constraints and B1-stable 22/50; B1 was correct on 21/90 and B1-stable on 52/90. The v0.2 report attributes B1-stable's remaining failures to lost session context. **ANALYSIS:** the constraint kinds `redact_terms` and `require_label` are checked over committed payloads (`mobilitybench_v01.py::check_constraint`), and B1-stable's ledger keeps the origin's first payload when a re-issue conflicts (17 effect-ID conflicts), so the 5 extra constraints need not mean restored context. Whether they do was not analysed.

**Validity threats.**

- **Construct:**
  - "Same runtime" is one pinned LangGraph version, so B3 results say nothing about other runtimes (that is B4).
  - Fresh effect IDs for restart are a modelling assumption; v0.2's B1-stable arm (#40) makes it visible. Its stable IDs come from the plan step index, which a restarted LLM agent does not naturally have.
- **Internal:**
  - Interruption points are authored to exercise mechanisms, not sampled from practice.
  - Single-host, in-process transfer.
- **External:**
  - No real crashes of real services.
  - Fault frequencies are design choices, not estimates.

## 7. Validity threats common to all three tasks

- **Self-authored benchmark:** the cases, the rubric, B5 and the system under test come from one project. Mitigations are the held-out split, B5 being frozen before the held-out split is opened, registration before the run, and publishing every raw row. External case contributions are a v0.1 "Next versions" item.
- **Oracle from the same interpreter:** ground truth is the output of a full-knowledge, fault-free interpreter run. `output_correct` therefore checks consistency with the interpreter semantics, not human-judged quality (FACT: [v0.1 validity threats](mobilitybench-v0.1.md#validity-threats)). Blinded human rubric scoring for document cases is planned.
- **Scripted operator:** intervention counts measure the need for a human under one frozen policy, not real human behaviour, error or time.
- **Proxy metrics:** steps and canonical-JSON bytes are not tokens or wire bytes ([economic evaluation](economic-evaluation.md#7-validity-threats-specific-to-economic-claims)).
- **Version drift:** LLM executors must pin model versions in `run_version.model`. Reused external benchmarks must pin their version, because issue #1 notes that OSWorld and τ-bench scores are not comparable across versions.
- **No generalization from deterministic runs:** until an executor is stochastic, every number is a property of the fixture set, and no interval is reported.

## 8. Order of work

1. **EV-C on the existing harness:** B3 is now scored when the `relocation` extra is installed ([#31](https://github.com/MSKazemi/agent-movement/issues/31)). The stable-ID restart and crashes inside effect steps now run in MobilityBench v0.2 ([#40](https://github.com/MSKazemi/agent-movement/issues/40)). Remaining: held-out cases with several interruption points each, and the intervention fields with the scripted operator. No LLM is needed.
2. **B5 as a mode** (`non_agent_workflow`) for all three tasks, written against a development split.
3. **EV-A with an LLM executor** behind the same interface, with pinned models.
4. **EV-B:** a new multi-role family and delegation contract, then `a2a_delegate` scoring on that family (v0.1 already scores it on the pure-op envelope when the `a2a` extra is installed, [#31](https://github.com/MSKazemi/agent-movement/issues/31)) and cross-agent injection fixtures ([#35](https://github.com/MSKazemi/agent-movement/issues/35)).
5. **Registration** of the frozen plan and case digests before any of the scored runs above are reported as results.

## References

Corpus items (metadata verified in the [paper corpus](paper-corpus/README.md); quoted summaries checked against the source abstracts on 2026-10-16):

- **AMP-029:** Qian, C., Liu, W., Liu, H., Chen, N. et al. (2024). ChatDev: Communicative Agents for Software Development. *ACL 2024*. https://doi.org/10.18653/v1/2024.acl-long.810
- **AMP-031:** Zhan, Q., Liang, Z., Ying, Z. and Kang, D. (2024). InjecAgent: Benchmarking Indirect Prompt Injections in Tool-Integrated Large Language Model Agents. *Findings of ACL 2024*. https://doi.org/10.18653/v1/2024.findings-acl.624
- **AMP-032:** Hong, S., Zhuge, M., Chen, J., Zheng, X. et al. (2024). MetaGPT: Meta Programming for A Multi-Agent Collaborative Framework. *ICLR 2024*. https://arxiv.org/abs/2308.00352
- **AMP-039:** Debenedetti, E., Zhang, J., Balunović, M., Beurer-Kellner, L. et al. (2024). AgentDojo: A Dynamic Environment to Evaluate Prompt Injection Attacks and Defenses for LLM Agents. *NeurIPS 2024 Datasets and Benchmarks*. Metric definitions quoted from §3.4 of https://arxiv.org/html/2406.13352
- **AMP-042:** Cemri, M., Pan, M. Z., Yang, S., Agrawal, L. A. et al. (2025). Why Do Multi-Agent LLM Systems Fail? *NeurIPS 2025 Datasets and Benchmarks*. https://arxiv.org/abs/2503.13657
- **AMP-070:** Zheng, Y., Yang, Y., Zhang, W., Quinn, A. et al. (2026). ACRFence: Preventing Semantic Rollback Attacks in Agent Checkpoint-Restore. arXiv. https://arxiv.org/abs/2603.20625
- **AMP-072:** Lee, D., Tiwari, M. and Miranda, B. (2026). Prompt Infection: LLM-to-LLM Prompt Injection within Multi-agent Systems. *ESORICS 2025 International Workshops*, LNCS. https://doi.org/10.1007/978-3-032-16092-8_28 (arXiv:2410.07283)
- **AMP-081:** Ruan, Y., Dong, H., Wang, A., Pitis, S. et al. (2024). Identifying the Risks of LM Agents with an LM-Emulated Sandbox. *ICLR 2024*. https://openreview.net/forum?id=GEcwtMk1uA

Primary sources outside the corpora (all accessed 2026-10-16):

- Kapoor, S., Stroebl, B., Siegel, Z. S., Nadgir, N. and Narayanan, A. (2024). AI Agents That Matter. arXiv:2407.01502. https://arxiv.org/abs/2407.01502. Quotations are from §2.3 of the HTML v1 text.
- Xia, C. S., Deng, Y., Dunn, S. and Zhang, L. (2024). Agentless: Demystifying LLM-based Software Engineering Agents. arXiv:2407.01489. https://arxiv.org/abs/2407.01489
- Yao, S., Shinn, N., Razavi, P. and Narasimhan, K. (2024). τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains. arXiv:2406.12045. https://arxiv.org/abs/2406.12045
- Jimenez, C. E., Yang, J., Wettig, A., Yao, S., Pei, K., Press, O. and Narasimhan, K. (2024). SWE-bench: Can Language Models Resolve Real-World GitHub Issues? *ICLR 2024*. https://arxiv.org/abs/2310.06770
- Parasuraman, R., Sheridan, T. B. and Wickens, C. D. (2000). A model for types and levels of human interaction with automation. *IEEE Transactions on Systems, Man, and Cybernetics, Part A*, 30(3), 286–297. https://doi.org/10.1109/3468.844354 (metadata checked through Crossref; abstract read from the published PDF)
- California Code of Regulations, Title 13, § 227.50, Reporting Disengagement of Autonomous Mode. https://www.law.cornell.edu/regulations/california/13-CCR-227.50
- Miller, E. (2024). Adding Error Bars to Evals: A Statistical Approach to Language Model Evaluations. arXiv:2411.00640. https://arxiv.org/abs/2411.00640. Recommendations quoted from the HTML text.
- Center for Open Science. OSF Registrations and Preregistrations help guide. https://help.osf.io/article/158-create-a-preregistration
- Becker et al. (2025) and Sadowski et al. (2018) are cited through the [economic evaluation](economic-evaluation.md#references).
