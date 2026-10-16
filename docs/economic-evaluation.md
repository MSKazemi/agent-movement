# Economic evaluation of agent movement: a proposed cost model

**Status:** **Proposed methodology. No results.** This document has no measured costs, prices, savings or return on investment for any system. Every formula below is a measurement plan, and the only worked numbers are labelled **synthetic** parameters.
**Date:** 2026-10-16. Web sources were accessed on 2026-10-16. Corpus items are cited by ID (`AMP-xxx` = [paper corpus](paper-corpus/README.md), `AMN-xxx` = [news corpus](news-corpus/README.md)).
**Tracks:** [issue #36](https://github.com/MSKazemi/agent-movement/issues/36), which covers research question 8 of [issue #1](https://github.com/MSKazemi/agent-movement/issues/1): *"How do you measure end-to-end economic value including review cost and incidents?"*
**Depends on:** [MobilityBench v0.1](mobilitybench-v0.1.md), its [experiment protocol](mobilitybench-experiment-protocol.md) and [checkpoint relocation](checkpoint-relocation.md), all on `main`. The record fields in §5 were verified against `src/agent_movement` on `main`.
**Related questions:** [AM-14 and AM-15, and "Economic scheduling"](open-questions.md); the "Cost per completed task" metric in the [roadmap](roadmap.md#proposed-benchmark-metrics).

## Executive answer

Moving an agent's work is worth it only when the **whole** cost of a correct outcome falls compared with simpler options. The cost of the move itself (tokens, bytes) is not enough. The proposed model adds up seven cost terms per attempt:

1. compute and tokens;
2. transfer bytes;
3. latency (delay);
4. human review time;
5. incidents;
6. rework;
7. failure handling and reconciliation;

plus amortized fixed costs. It compares them across six arms: **keep, restart, delegate, relocate, reconstruct, and a non-agent workflow**.

Four rules come from the literature cited below:

- **Record quantities and prices separately.** Store tokens, bytes, seconds and counts per attempt. Apply a dated price table only at analysis time, because prices change ([Kapoor et al. 2024](#ref-kapoor2024)).
- **Report cost per correct completion and the cost–accuracy trade-off, not accuracy alone** ([Kapoor et al. 2024](#ref-kapoor2024); [Kapoor et al. 2025](#ref-kapoor2025)).
- **Measure human time. Do not ask people to estimate it.** In one randomized trial, developers' own estimates of AI speed-up had the opposite sign from the measured effect ([Becker et al. 2025](#ref-becker2025)).
- **Count incidents and failure handling in the cost, even when the attempt "completed".** An output can be byte-correct while its side effects are wrong. MobilityBench v0.1 already records such a case (a duplicated booking), and it uses that to define `task_correct`.

Today, MobilityBench v0.1 can feed only the **deterministic proxy** quantities: steps, re-executed steps, canonical transfer bytes, effect and policy counts, and unknown/reconcile events. It has **no** tokens (`model_calls` is always 0), no fair latency, no human time, and no incident severity or money. Those are listed below as **unmeasured**, each with a proposed record field.

## 1. Scope and unit of analysis

- **Unit:** one *attempt* = one logical task run under one arm, for one (task, fault, seed, repeat). This matches the MobilityBench v0.1 pairing, in which every arm of a (seed, task) pair gets the same injected fault.
- **Decision question:** for a given task population and fault model, which arm gives the lowest expected **total cost per correct completion**? At what task value does moving pay off against the best non-moving arm?
- **Out of scope:**
  - macro-economic or labour-market effects;
  - pricing strategy;
  - the value of tasks to a particular business (this is a stakeholder input, see §3.4);
  - any claim about real deployments before real executors exist.

## 2. Cost model

For arm *m* and attempt *i*:

```
C_i(m) = C_compute + C_transfer + C_delay + C_review + C_incident + C_rework + C_failure
C(m)   = Σ_i C_i(m) + F(m)            F(m) = fixed cost amortized over the evaluation horizon
```

Each term is **Σ (measured quantity × price parameter)**. Quantities come from run records. Price parameters come from a versioned price table (`price_table_ref`, with source URL and access date), so the same records can be priced again later. This follows the observation that agent costs "vary over time, which would affect the outcomes of the cost-controlled assessments" ([Kapoor et al. 2024](#ref-kapoor2024)).

| # | Term | Quantity × price (proposed) | Grounding |
| --- | --- | --- | --- |
| T1 | **Compute and tokens** | (input, output and cached tokens × per-token prices) + tool calls × per-call price + CPU/GPU seconds × rate. Includes the work an arm **repeats**: restart re-runs steps that the origin already did. | [Kapoor et al. 2024](#ref-kapoor2024): "The total cost of running an agent includes fixed and variable costs. Variable costs are incurred each time the agent is run and depend on the number of input and output tokens." AMP-074 (ACON) shows that history length drives inference memory cost (26–54% lower peak tokens from compression), so the context that is moved is a cost lever. AMN-077 (DBOS) describes resuming from the last completed step "without repeating costly earlier ones": avoiding re-execution is the claimed benefit. |
| T2 | **Transfer bytes** | wire bytes × network/egress price per region pair + messages × per-message cost. Counts both directions and duplicate deliveries. | AMP-011 (Lange and Oshima 1999) gives lower network load as a motivation for mobile agents. AMP-014 (D'Agents) measured when moving code beats client/server. AMP-056 models "latency/cost" constraints for LLM-agent migration at the edge and moves "only essential state". Bytes are a cost **and** a disclosure surface (see T5). |
| T3 | **Latency / delay** | time to correct completion (and the movement pause) × a stakeholder-supplied delay-cost rate. **The default is to report it as its own dimension (p50/p95) and not convert it to money.** | AMP-035 (Llumnix) reports tail latency and serving cost together when it migrates in-flight LLM request state. The [roadmap](roadmap.md#proposed-benchmark-metrics) lists mean/p95 latency. |
| T4 | **Human review time** | measured reviewer seconds × a loaded labour rate, for: approval before movement, review of the output, investigation of `unknown` outcomes, and sign-off on compensation. | No corpus item covers review cost. [Sadowski et al. 2018](#ref-sadowski2018) studied review using tool logs from about 9 million reviewed changes, which shows that review effort can be logged instead of guessed. [Becker et al. 2025](#ref-becker2025) (RCT, 16 developers, 246 tasks) found that allowing AI tools "increases completion time by 19%", while developers had expected a 24% reduction. **Self-reported time is therefore not an acceptable measure.** |
| T5 | **Incidents** | Σ over incidents of (time to detect + respond + recover × staff rate) + external impact (stakeholder-supplied, by severity class). Expected value = frequency × severity cost. | Google SRE book, "Postmortem Culture": postmortem triggers include "Data loss of any kind" and "On-call engineer intervention (release rollback, rerouting of traffic, etc.)". DORA: change fail rate and failed deployment recovery time. AMN-033 (ForcedLeak) and AMN-034 (postmark-mcp) are examples of agent/tool incident **classes**, not cost data. |
| T6 | **Rework** | (incorrect or constraint-violating completions × the cost of redoing them) + (duplicate or unexpected effects × compensation cost) + (missing effects × completion cost). | DORA "deployment rework rate" (unplanned deployments triggered by an incident) is the closest delivery-practice analogue. MobilityBench's rubric already separates `output_correct` from `task_correct`, so rework from effects can be counted even when the output looks right. |
| T7 | **Failure and reconciliation** | (`unknown` outcomes × reconcile cost) + (refused/incomplete attempts × cost of the **declared fallback arm**) + exactly-once overhead (logging, fencing). | AMP-023 (Halfmoon) shows that exactly-once retries have a measurable logging overhead, which it reduces. That overhead is the price of avoiding duplicates. The Google SRE book's "toil" ("manual, repetitive, automatable, tactical, devoid of enduring value, and that scales linearly") describes manual reconciliation work that should be costed, not ignored. |
| F | **Fixed / amortized** | engineering and operation of coordinators, gateways, receipt verification, workflow authoring (for the non-agent arm) and evaluation infrastructure, ÷ the tasks over a stated horizon. | [Kapoor et al. 2024](#ref-kapoor2024) (fixed versus variable costs). [Kapoor et al. 2025](#ref-kapoor2025) (HAL) reports its own evaluation-infrastructure cost, which shows that evaluation cost should be stated too. |

## 3. Composite metrics and analysis plan

### 3.1 Primary metric: cost per correct completion

```
CPC(m) = C(m) / N_correct(m)        N_correct = number of attempts with task_correct = true
```

The denominator uses `task_correct`, not `output_correct`. Refused, incomplete and unavailable attempts are **kept** in the cost numerator and in the denominator tables, and are never dropped. If no attempt is correct, CPC is reported as undefined, not as zero or infinity.

### 3.2 Fallback-adjusted cost

A refused or incomplete attempt still needs the task done somehow. Each arm must **pre-declare** a fallback (for example, "B2 refusal → B0 keep" or "→ non-agent workflow"). The analysis adds the fallback arm's measured mean cost and correctness to the refused and incomplete attempts. Results are reported both with and without this adjustment.

### 3.3 Cost–accuracy frontier

Plot each arm (and each executor configuration) as (mean cost per attempt, `task_correct` rate) and report the Pareto frontier. This follows Kapoor et al.: "Visualizing the cost and accuracy of agents as a Pareto frontier opens up a new space for agent design" ([2024](#ref-kapoor2024)). HAL builds cost-controlled evaluation into a shared harness ([Kapoor et al. 2025](#ref-kapoor2025)). For stochastic executors, also report **pass^k**, the reliability over *k* repeated trials ([Yao et al. 2024](#ref-yao2024)). A cheap arm that succeeds only sometimes needs retries, and retries are costs.

### 3.4 Break-even task value (no business value needs to be assumed)

Let *P* be the probability of a correct completion and *V* the value of one correct completion. Then the movement arm *m* beats the baseline *b* when

```
V·P_m − C_m  >  V·P_b − C_b     ⇔     V > V* = (C_m − C_b) / (P_m − P_b)      (when P_m > P_b)
```

If P_m ≤ P_b and C_m ≥ C_b, then *m* is dominated. The analysis reports **V\*** with its uncertainty and lets the stakeholder compare it with their own *V*. This avoids inventing task values.

> **Synthetic illustration (made-up parameters, not measurements):** suppose an arm *m* has P_m = 0.90 and C_m = 12 cost units per attempt, and a baseline has P_b = 0.60 and C_b = 9. Then V\* = (12 − 9) / (0.90 − 0.60) = 10 cost units: moving pays off only for tasks worth more than 10 units per correct completion. None of these four numbers comes from any system.

### 3.5 Uncertainty and sensitivity

- **Paired design:** arms share tasks, faults and seeds, so the comparison uses paired differences per (task, fault, seed).
- **Confidence intervals:** cluster-bootstrap over tasks once executors are stochastic. v0.1 is deterministic, so its repeats test reproducibility only and support **no** intervals.
- **Price sensitivity:** recompute every metric under low, base and high price tables, and report which ranking flips.
- **Pre-registration:** register the price-table sources, delay-cost rate, labour rate, severity classes, fallback rules and horizon **before** the runs. Anything chosen after seeing results is labelled exploratory. This follows the rules of the [experiment protocol](mobilitybench-experiment-protocol.md).

## 4. Arms (baselines)

| Arm | Definition | Where each arm is expected to pay (hypotheses to test, not findings) | Status on `main` |
| --- | --- | --- | --- |
| **B0 keep** | origin finishes, nothing moves | no transfer; under pre-emption the attempt is incomplete, so T7 is the fallback cost | implemented |
| **B1 restart** | destination starts again from the original request | T1 re-execution; T6 rework from lost session context and duplicated effects; T5 when lost policies are violated | implemented |
| **B2 delegate** | origin keeps ownership and sends bounded sub-work | T2 for every round trip; T7 from refusals when state is not expressible | local profile implemented; A2A (issue #7) scored in MobilityBench v0.1 only when the `a2a` extra is installed, otherwise an explicit unavailable record (issue #31) |
| **B3 relocate** | same-runtime checkpoint moves, origin fenced | T2 checkpoint bytes; F coordinator and fencing; T7 reconcile for opaque tools | scored in MobilityBench v0.1 only when the `relocation` extra is installed, otherwise an explicit unavailable record (issue #31); separate fault matrix and operator reconciliation in [`checkpoint-relocation.md`](checkpoint-relocation.md) (issues #9, #30) |
| **B4 reconstruct** | re-create the work in another framework from documented state | T6 from semantic loss; T4 to verify the reconstruction | unavailable |
| **B5 non-agent workflow** *(proposed)* | a deterministic script/workflow, or a human doing the task, with no LLM agent | F authoring and maintenance; T4 human time; near-zero T1 tokens | **not in MobilityBench (proposed arm)** |

B5 answers research question 4 of issue #1 ("Is agent B actually better than a deterministic workflow or single agent on the same test suite?") and the [open question](open-questions.md) on economic scheduling. Without it, a positive result for movement only shows that movement beats other agent arms.

<!-- Field names verified against src/agent_movement on main at b21da27 (2026-10-16). -->
## 5. Mapping to MobilityBench record fields

> **Verified on `main`.** These field names were checked against `src/agent_movement/mobilitybench_v01.py` and `relocation_demo.py` on `main` (2026-10-16). Re-check them when the record schema changes.
>
> Sources:
> - `src/agent_movement/mobilitybench_v01.py`: `METRIC_KEYS` and `run_attempt()` for attempt records; `run_suite()` for the `run_manifest` record; `run_security_cases()` for `security` records.
> - [`docs/mobilitybench-v0.1.md`](mobilitybench-v0.1.md), section "Per-attempt record (sanitized JSONL)".
> - `src/agent_movement/relocation_demo.py` for the separate B3 fault matrix.
>
> "Unmeasured" means that no v0.1 field carries the quantity. The proposed fields are suggestions for a later suite version, not existing schema.

| Term | Quantity | Existing field (file) | Status | Proposed field(s) |
| --- | --- | --- | --- | --- |
| T1 compute/tokens | model calls | `model_calls` (attempt record, `mobilitybench_v01.py`); `run_version.model` | measured but always `0` / `"none"`: the executor is a deterministic interpreter | `input_tokens`, `output_tokens`, `cached_input_tokens`, `tool_calls`, `compute_seconds`, `price_table_ref` |
| T1 compute/tokens | work done and repeated | `steps_executed`, `steps_reexecuted` (`mobilitybench_v01.py`) | **measured (deterministic proxy)**; no unit price | per-step token/compute attribution |
| T1 (B3 only) | re-executed items | `item_reexecutions`, `opaque_invocations` (`relocation_demo.py` fault-matrix rows, not MobilityBench records) | measured in the relocation demo only. MobilityBench B3 records (issue #31) carry `steps_reexecuted` instead, which is 0 in v0.1 because movement happens only at clean step boundaries | carry `opaque_invocations` into MobilityBench B3 records |
| T2 transfer | bytes and messages | `transfer_bytes`, `transfer_messages` (`mobilitybench_v01.py`, `Attempt.send`) | **measured**, but as canonical-JSON sizes, **not wire bytes**: no HTTP or JSON-RPC framing. B2-local is in-process; B2 A2A crosses loopback HTTP but counts only the A2A-bound projection and the receipt; B3 counts the manifest, the checkpoint channels and the grant | `wire_bytes`, `region_pair`, `checkpoint_bytes` |
| T3 latency | wall-clock | `elapsed_ms` (attempt and security records); `started_at` (`run_manifest`) | recorded but **not a fair latency measure** (machine-dependent, dominated by SQLite setup, `null` under `--no-timing`) | `movement_pause_ms`, `time_to_correct_completion_ms` (monotonic), measured on a fixed testbed |
| T4 human review | reviewer time, approvals | none (approvals in v0.1 are scripted `Approval` objects) | **unmeasured** | `human_review_seconds`, `approvals_requested`, `approvals_granted`, `reviewer_role`, `review_stage` |
| T5 incidents | incident precursors | `policy_violations`, `stale_commits_accepted`, `sensitive_transfers`, `unexpected_effects` (attempt); `verdict`, `known_gap` (security records) | **measured as counts only**: no severity, detection or recovery time, no money | `incident_severity`, `time_to_detect_ms`, `time_to_recover_ms`, `incident_ref` |
| T6 rework | incorrect / lost constraints / wrong effects | `task_correct`, `output_correct`, `constraints_preserved`, `constraints_total`, `duplicate_effects`, `missing_effects`, `unexpected_effects` (`mobilitybench_v01.py`) | **measured** (counts); rework effort itself unmeasured | `rework_steps`, `compensation_actions` |
| T7 failure/reconciliation | unknown outcomes, fencing, dedup, refusals | `unknown_events`, `reconciled_events`, `stale_commits_fenced`, `duplicate_deliveries_suppressed`, `outcome`, `reason`, `fault`, `fault_applied` (`mobilitybench_v01.py`) | **measured** (counts and enums) | `reconcile_ms`, `fallback_mode`, `fallback_attempt_ref` |
| T7 (B3 only) | operator decisions on parked opaque effects | `reconciliation_events` rows (`event_type` `parked`, `confirmed_done`, `confirmed_absent`, `replayed`, `denied`, `applied`; `actor`, `epoch`, `event_time`) and the decision record in `effect_reconciliations` (`relocation.py`, issue #30; relocation experiment only, not MobilityBench records) | **recorded as events**: who decided, at which epoch, and when. No review duration, and the decision's correctness is not checked | `reconcile_interventions` in MobilityBench records; `reconcile_ms` |
| T7 exactly-once overhead | ledger/fencing cost | none | **unmeasured** | `ledger_writes`, `ledger_bytes` |
| F fixed | infrastructure, authoring, evaluation | none (`run_manifest` has versions, not costs) | **unmeasured** | `fixed_cost_ref` in `run_manifest`, with horizon and amortization rule |
| all | arm identity and pairing | `mode`, `baseline`, `mode_status`, `seed`, `task_id`, `family`, `repeat` | measured | `fallback_policy` in `run_manifest` |
| B5 non-agent arm | all terms | none | **unmeasured (arm absent)** | new mode `non_agent_workflow` |

## 6. What is missing

1. **Real executors.** With `model_calls = 0`, the token cost (T1) and output variance are outside v0.1. An LLM executor with pinned models is already listed as "later" in the MobilityBench plan.
2. **Human time (T4).** This needs instrumented review UIs or timed protocols with consent. It may require ethics review if real participants take part.
3. **Incident severity and cost (T5).** Counts of precursors exist. Mapping them to severity and money needs a pre-declared severity scale and stakeholder-supplied impact costs. Public incident write-ups (for example AMN-033 and AMN-034) give the incident classes, not cost data.
4. **Fair latency (T3) and wire bytes (T2).** These need a fixed multi-host testbed instead of in-process canonical sizes.
5. **Prices.** Token, compute and egress price tables must be cited with an access date for each run. This document deliberately quotes no prices.
6. **Non-agent arm (B5) and reconstruction (B4) in the same paired harness.** A2A (B2) and relocation (B3) now run in it when their extras are installed (issue #31), but only with the deterministic interpreter, on one host, with movement at a single point.
7. **Task population.** Costs depend on how often movement is triggered and on the fault rates. The v0.1 fixtures are authored to exercise mechanisms, not sampled from practice. So no v0.1 count is a frequency estimate, and no expected cost computed from them generalizes.

## 7. Validity threats specific to economic claims

- **Price drift:** rankings can flip as prices change, so the analysis is re-priced from stored quantities, never from stored dollars.
- **Hidden fixed costs:** an arm that looks cheap per attempt may carry large coordinator or authoring costs (F).
- **Cherry-picked denominators:** cost per *completed* attempt hides refusals. Always use cost per *correct* completion, plus the fallback adjustment.
- **Perception bias in human time:** this is the reason for T4 measurement ([Becker et al. 2025](#ref-becker2025)).
- **Proxy validity:** steps and canonical bytes are proxies. Their correlation with real tokens and wire bytes must be measured before they are used as cost stand-ins.

## References

Corpus items (metadata verified in the corpora; summaries checked against the source abstracts where quoted above):

- **AMP-011:** Lange, D. B. and Oshima, M. (1999). Seven good reasons for mobile agents. *Communications of the ACM*. https://doi.org/10.1145/295685.298136
- **AMP-014:** Gray, R. S., Cybenko, G., Kotz, D., Peterson, R. A. et al. (2002). D'Agents: Applications and performance of a mobile-agent system. *Software: Practice and Experience*. https://doi.org/10.1002/spe.449
- **AMP-023:** Qi, S., Liu, X. and Jin, X. (2023). Halfmoon: Log-Optimal Fault-Tolerant Stateful Serverless Computing. *SOSP '23*. https://doi.org/10.1145/3600006.3613154
- **AMP-035:** Sun, B., Huang, Z., Zhao, H., Xiao, W. et al. (2024). Llumnix: Dynamic Scheduling for Large Language Model Serving. *OSDI '24*. https://www.usenix.org/conference/osdi24/presentation/sun-biao
- **AMP-056:** Wang, X., He, J., Tang, Z., Guo, J. et al. (2025). Adaptive AI Agent Placement and Migration in Edge Intelligence Systems. *IEEE ICCT 2025*. https://doi.org/10.1109/icct67417.2025.11373977 (arXiv:2508.03345, abstract checked 2026-10-16)
- **AMP-074:** Kang, M., Chen, W.-N., Han, D., Inan, H. A. et al. (2026). ACON: Optimizing Context Compression for Long-horizon LLM Agents. *ICML 2026*. https://arxiv.org/abs/2510.00615 (abstract checked 2026-10-16)
- **AMN-033:** Noma Security (2025-09-25). ForcedLeak: AI agent risks exposed in Salesforce Agentforce.
- **AMN-034:** The Register (2025-09-29). One line of malicious npm code led to massive Postmark email heist.
- **AMN-077:** DBOS (2026-04-07). Building Durable Agents with DBOS and Databricks.

Primary sources outside the corpora (all accessed 2026-10-16):

- <a id="ref-kapoor2024"></a>Kapoor, S., Stroebl, B., Siegel, Z. S., Nadgir, N. and Narayanan, A. (2024). AI Agents That Matter. arXiv:2407.01502 (v1, 1 July 2024). https://arxiv.org/abs/2407.01502. Quotations are from the HTML v1 text.
- <a id="ref-kapoor2025"></a>Kapoor, S., Stroebl, B., Kirgis, P., Nadgir, N. et al. (2025). Holistic Agent Leaderboard: The Missing Infrastructure for AI Agent Evaluation. arXiv:2510.11977 (v1, 13 October 2025); listed as accepted at ICLR 2026. https://arxiv.org/abs/2510.11977
- <a id="ref-yao2024"></a>Yao, S., Shinn, N., Razavi, P. and Narasimhan, K. (2024). τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains. arXiv:2406.12045. https://arxiv.org/abs/2406.12045
- <a id="ref-becker2025"></a>Becker, J., Rush, N., Barnes, E. and Rein, D. (2025). Measuring the Impact of Early-2025 AI on Experienced Open-Source Developer Productivity. arXiv:2507.09089. https://arxiv.org/abs/2507.09089
- <a id="ref-sadowski2018"></a>Sadowski, C., Söderberg, E., Church, L., Sipko, M. and Bacchelli, A. (2018). Modern code review: a case study at Google. *ICSE-SEIP '18*, pp. 181–190. https://doi.org/10.1145/3183519.3183525 (metadata checked through Crossref; abstract checked at research.google)
- Lunney, J. and Lueder, S. Postmortem Culture: Learning from Failure. In *Site Reliability Engineering* (Google), ch. 15. https://sre.google/sre-book/postmortem-culture/
- Rau, V. Eliminating Toil. In *Site Reliability Engineering* (Google), ch. 5. https://sre.google/sre-book/eliminating-toil/
- DORA. DORA's software delivery performance metrics. https://dora.dev/guides/dora-metrics/
