# MobilityBench v0.1: proposed pre-registration protocol

**Date:** 2026-10-15. **Status:** Proposed study plan, not yet registered or frozen; no benchmark scores have been measured.  
**Purpose:** Test, rather than assume, the benefit, safety and semantic fidelity of moving an AI agent's work. Companion to [strategy](strategic-target-and-scientific-agenda.md) and [open questions](open-questions.md).
**Implementation note (2026-10-16):** a first executable, LLM-free pilot with frozen, digest-verified synthetic fixtures and the keep / restart / local-delegate baselines is documented in [MobilityBench v0.1: frozen task-continuity baselines](mobilitybench-v0.1.md). The study plan below, including the A2A, relocation and reconstruction arms, remains a proposal. The [evaluation plan for reference tasks EV-A, EV-B and EV-C](evaluation-plan.md) (design only, no results) adds the single-agent tool-use task, the deterministic non-agent baseline and the human-intervention metric.

## Research questions

- **RQ1:** Which approved task-state fields are necessary and sufficient for correct continuation?
- **RQ2:** Under which failure assumptions can a transfer coordinator prevent two workers from committing the same simulated action?
- **RQ3:** How do baseline restart, delegation, same-runtime relocation and cross-runtime reconstruction compare in correctness, constraint preservation, latency, cost and privacy?
- **RQ4:** Can independent evidence verifiers distinguish supported movement claims from incomplete or tampered traces?

## Study design

Use public/synthetic fixtures. Pre-register datasets, acceptance rubric and failure schedules in version-controlled YAML manifests. Never transfer keys, browser sessions, hidden reasoning or private user records.

### Experimental systems

- **B0 Keep:** complete a task on original worker with no movement.
- **B1 Restart:** begin again on a new worker using approved inputs, not private internal state.
- **B2 Delegate:** origin sends a fresh bounded task to recipient using A2A; not called migration.
- **B3 Relocate:** export a safe native checkpoint; fence origin; resume same logical task in another instance of the same pinned runtime.
- **B4 Reconstruct (later):** serialize only documented application-level state and recreate runnable work in a second framework or model; record all semantic loss.

Every experiment reports whether each baseline was available and why not. Compare like-for-like budgets, inputs and tooling.

### Workloads

1. **Document research** with synthetic source citations, fact constraints, tool outputs and distractors.
2. **Coding task** in a toy repository with deterministic unit tests, no internet, and synthetic secret canaries.
3. **Multi-step external actions** through a fake tool that can commit, time out, and acknowledge separately.
4. **Long-horizon workflow** with pauses, changing requirements and explicit user-approval checkpoints.
5. **Read-only edge scenario (later)** with resource and network partitions; no physical actuation.

Start with 30 frozen tasks **per workload**, including at least five designed negative/security cases. This is an engineering starting point, not a statistical-power claim. Conduct a pilot to estimate variance and set a justified sample size before a publishable comparison.

### Fault-injection schedule

For each transition (**prepared, authorized, frozen, dispatched, received, running, effect-intent, effect-commit, acknowledged, completed, canceled, unknown**), inject: source crash, receiver crash, coordinator crash, duplicated dispatch, delayed delivery, expired/revoked grant, mismatched checkpoint/schema, tampered artifact, forged recipient advertisement and network partition as applicable. Record test applicability and expected fail-closed or reconcile outcomes.

Do not call a simulation safe because the application side has an epoch field; **the simulated tool gateway must check fencing epochs atomically at the commit point**. Tests should explicitly demonstrate the failure when that enforcement is disabled.

### Outcome and evidence fields

Each JSONL result: task_id; workload; frozen_input_digest; experiment_id; baseline; source/destination principal and framework; model + settings; implementation version; seed; start/end; approval reference; transfer attempt ID; artifact digest; checkpoint schema; lost fields; state outcome; artifact correctness; constraints retained; attempted and committed effects; duplicates; stale-owner denials; authorization violations; canary leaks; unknown/reconcile count; task total cost; latency; source+recipient receipt refs; independent verifier result.

Use UTC event times, monotonic durations for timing, fixed budgets and artifact hashing. Trace IDs correlate activity; they do not prove authenticity.

### Planned metrics

- Task completion / correctness and constraint retention; raw rubrics and per-case failure modes.
- Safe continuation = target correct **and** no forbidden action **and** ownership invariant respected.
- Effect safety = forbidden/duplicate synthetic tool *commits* (not only client attempts).
- Recovery success, indeterminate effect outcomes, and time to reconciliation.
- Pre-disclosure policy rejection / synthetic canary leakage.
- Transfer bytes, latency p50/p95, token/tool/compute cost per correct completion.
- Independent provenance verification and gap/uncertainty classification.
- Compatibility refusal accuracy and explicit lost-context field counts.

Report denominators, confidence intervals where justified, and multiple-comparison/selection caveats. Never turn zero observed violations in a small synthetic test into a blanket security guarantee.

## Hypotheses and falsification

| ID | Hypothesis | Falsified or weakened if |
| --- | --- | --- |
| H1 | Typed application state with explicit constraints reduces critical constraint loss compared with history-only replay | Paired continuation trials show no reliable advantage or worse outcomes at comparable cost |
| H2 | A durable coordinator plus effect-gateway fencing avoids duplicate *simulated commits* within the modeled faults | Fault injection yields duplicated committed effects or late stale-epoch acceptance |
| H3 | Cross-framework reconstruction has measurable semantic loss relative to compatible same-runtime restore | Across appropriate tasks there is no meaningful difference in constraints, quality or loss reporting |
| H4 | Forensic receipts improve independent reconstruction of moves compared with traces only | Blinded verifiers cannot more accurately classify authenticated lineage/tampering/unknown outcomes |

Do not retrofit hypotheses after viewing results; any new analysis is exploratory and labeled as such.

## Initial implementation acceptance checklist

- [ ] Frozen synthetic fixtures and manifest with hashes
- [ ] Native A2A sender/receiver smoke test (no production endpoints)
- [ ] Documented versioned transfer schema and refusal behavior
- [ ] Stable IDs for logical task, execution, instance, movement and branch lineage
- [ ] Policy gate before any disclosure; negative tests on wrong-audience or revoked grant
- [ ] Effect ledger and fake gateway with idempotency and stale-epoch denial
- [ ] Crash/partition injection at every modeled state-machine boundary
- [ ] Unknown/reconcile behavior with withheld success claims
- [ ] Redacted, inspectable movement evidence and independently checked receipts
- [ ] Raw per-attempt outputs + deterministic or pinned environment
- [ ] Baseline comparisons and explicit unsupported scenarios
- [ ] CI running a reduced deterministic subset; full benchmark on demand

## Validity threats to report

Model stochasticity, prompt/environment drift, benchmark leakage, evaluator subjectivity, vendor differences, inadequate fault coverage, nonrepresentative synthetic actions, authorization systems not participating in tests, telemetry sampling, single runtime overfitting, performance instrumentation overhead, and survivorship bias. Verify versions at execution time.

## Related specifications / evidence

A2A: https://a2a-protocol.org/v1.0.0/specification/  
MCP: https://modelcontextprotocol.io/specification/2026-07-28  
LangGraph: https://docs.langchain.com/oss/python/langgraph/persistence  
Temporal: https://docs.temporal.io/workflow-execution  
Agent Spec: https://doi.org/10.1145/3786335.3813130  
OAuth token exchange: https://www.rfc-editor.org/rfc/rfc8693  
OWASP Agentic 2026: https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
