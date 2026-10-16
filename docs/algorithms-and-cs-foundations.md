# Algorithmic and computer-science foundations of Agent Movement

**Research/design review:** 2026-10-16. **Code status:** the accompanying `tools/movement_modelcheck.py` is an executable **finite, abstract model**, not a verified implementation or a proof of the real Python handoff paths. **Scope:** movement of agent *work and bounded execution authority*; not teleportation of a process, model weights, private hidden state, or physical motion.

## Executive decision

Treat Agent Movement as a **distributed, policy-constrained transfer-of-authority problem with partial state portability**, not a messaging or networking feature. The first scientific question is whether a destination can continue useful work while all *protected* effects remain authorized and unambiguous under crashes, retries, and partitions. Prove safety for a precisely stated subsystem before claiming liveness or semantic continuity.

Existing pieces are already nontrivial: [core effect fencing](../src/agent_movement/core.py), [authenticated peer tests](peer-authentication.md), [same-runtime relocation and operator reconciliation](checkpoint-relocation.md), [lifecycle definitions](agent-lifecycle-liveness-and-death.md), and [MobilityBench v0.2](mobilitybench-v0.2.md). These do **not** yet combine into a verified, uniformly enforced cross-host mobility protocol. The current [runtime-policy enforcement issue #50](https://github.com/MSKazemi/agent-movement/issues/50) is a prerequisite for any all-enabled-path safety claim; this document is complementary theory, not closure of that issue.

## 1. Research decomposition: the important algorithms

| Priority | Domain / foundation | Decision to make | Candidate method and falsifiable test |
| --- | --- | --- | --- |
| **P0** | Distributed algorithms | Who owns a task and its protected effects during transfer? | Linearizable compare-and-swap (CAS), monotonically increasing epochs, fenced target-side commits; inject delayed/duplicated workers. |
| **P0** | State-transition systems | Which of requested, prepared, fenced, resumed, canceled, and uncertain states are legal? | Explicit transition relation with terminal monotonicity; enumerate bad transitions. |
| **P0** | Formal verification | Which safety properties follow from which assumptions? | Invariants + small-state model checking; produce a minimal counterexample for a removed guard. |
| **P0** | Concurrency/transactions | What if the agent crashes around an irreversible tool call? | Stable effect IDs, atomic gateway deduplication; opaque effects enter `UNKNOWN_RECONCILE`, not blind retry. |
| **P0** | Capability security | How is destination authority limited and revoked? | Independently issued, resource-/tenant-/task-scoped grants; decision and enforcement at each boundary, especially commit. |
| **P0** | Crash recovery | Is a persisted state actually resumable? | Checkpoint manifest, digest, dependencies, runtime compatibility and effect-intent ledger; fail closed on mismatch. |
| **P1** | Graph theory | What movement/delegation paths are authorized? | Directed trust/capability graph, path constraints, bounded lineage DAG, cycle/hop/fan-out checks. |
| **P1** | Scheduling / operations research | When should work stay, restart, delegate or relocate? | Feasibility filter then risk-aware min-cost placement; compare against baselines rather than mobility alone. |
| **P1** | Type systems / compiler semantics | Can two frameworks interpret the portable unit safely? | Typed intermediate representation (IR), schema/version negotiation, explicit loss map and adapter refinement tests. |
| **P1** | Replicated data and consistency | How do forks share memory and budgets? | Single-writer ownership for effects; use CRDTs only for suitably mergeable data and domain-specific conflict rules for plans. |
| **P1** | Distributed failure detection | Is a silent agent dead, partitioned or only suspended? | Evidence freshness, challenge/response and eventually accurate suspicion; unknown instead of unprovable death. |
| **P1** | Information theory / state minimization | Which context must be carried for successful continuation? | Ablation, sufficient-state experiments, private-field leakage checks; no unsupported lossless hidden-state promise. |
| **P1** | Resource accounting | Can clone/fan-out multiply permissions or spending? | Budget conservation, descendant-scope intersection, quota/escrow accounting; adversarial concurrent allocations. |
| **P1** | Causality and forensics | Can an investigator reconstruct what happened? | Causal event DAG, signed movement receipts, hash commitments and explicit observation gaps. |
| **P2** | Online algorithms | Can policy-compliant placement adapt to uncertain latency/cost? | Contextual bandits or robust optimization in a simulator, with a static scheduler as control. |
| **P2** | Complexity / decidability | Which decisions remain tractable at scale? | Characterize NP-hard multi-task placement; bound or approximate it; avoid claiming arbitrary semantic equivalence is decidable. |
| **P2** | Multi-domain trust and Byzantine faults | What if an executor or issuer lies? | Separate cryptographic authentication from honest behavior; threat-specific attestations, cross-checks, quarantine. |
| **P2** | Human/physical safety | What changes for actuators, robots, hospitals or finances? | Safety interlocks and independently controlled effect gateways; never infer real-world safety from synthetic benchmarks. |

These are research *directions*, not statements that the named methods are already implemented. See also [open research questions](open-questions.md), [the 2031 agenda](2031-frontier-research-agenda.md) and the [evaluation plan](evaluation-plan.md).

## 2. Mathematical objects and semantics

Define a managed system with tasks `T`, execution instances `I`, principals `P`, devices `D`, checkpoints `S`, effects `E`, grants `G` and a potentially partitioned network `N`.

- **Logical task identity** is stable across relocation: `task_id`. An execution `instance_id` is not reused after crash or replacement. `principal_id`, `logical_agent_id`, `movement_id` and `lineage_parent_id` are independent identifiers.
- **Movement** changes the authorized *effect owner* of `task_id` from execution `A` to `B`; it does not imply the old process is physically destroyed. **Delegation** may leave task ownership at A and assigns B only separate bounded work rights. **Fork/clone** creates new branch IDs and never silently reuses one task's exclusive effect authority.
- A checkpoint `s` is a manifest of typed application state, compatible scheduler position, approved references, dependency versions, causal history/offset and *pending effect intents*. It is **not** an arbitrary Python process image or opaque language-model internal state.
- For a protected effect, the authoritative register is `R[task_id] = (owner, epoch, policy_version, revocation_state)` in one consistency domain; the target-side gateway must check it at the effect's actual commit point. If there are multiple independent gateways, they need a shared linearizable authority or a stated weaker guarantee.

A proposed relocation trace is:

`REQUEST -> VALIDATE -> PREPARE_DESTINATION -> GRANT_DESTINATION -> FENCE_SOURCE -> ACTIVATE_DESTINATION -> VERIFY -> COMPLETE`

with explicit `DENIED`, `CANCELED`, `FAILED`, or `UNKNOWN_RECONCILE` exits. Preparation can copy an authorized checkpoint but **must not** confer effect permission before fencing. One atomic transfer of the gateway's authoritative epoch is the **linearization point**; copying bytes is not.

## 3. Assumptions before any formal guarantee

For the *abstract protected-effect model* only:

1. A **single trusted linearizable gateway** atomically manages task epoch, revocation observation and deduplicated protected effects in durable storage. The model assumes atomic actions rather than implementing a real distributed consensus protocol.
2. Every relevant effect **must** pass through that gateway. A worker cannot use another network path, leaked credential, external account or unguarded tool to achieve the same effect.
3. Workers may crash, restart with old tokens, delay or retry, and the gateway may be unreachable. The gateway itself is trusted and non-Byzantine. Idempotency keys are stable for the logical effect, not regenerated per attempt.
4. Issuing a destination grant means trusted identity, scope and policy checks have already succeeded. The tiny checker models that fact as a boolean; it does not prove authenticity, cryptography, data locality, confidentiality or grant expiry.
5. The gateway can refuse protected operations while unreachable; the system chooses safety over availability. Arbitrary third-party side effects outside the gateway have no such guarantee.
6. No network fairness, eventual repair or reliable clock is assumed for **safety**. Liveness is conditional on stronger progress assumptions.

These assumptions are **security-critical**. The toy model proves nothing about bypassable runtime paths, compromised hosts, malicious reviewers, side effects that occur before gateway authorization, other device operating systems, or the correct translation of arbitrary agent context.

## 4. Properties to specify and test

| ID | Kind | Property | Boundary/qualification |
| --- | --- | --- | --- |
| F-01 | Safety | A protected effect commit has a valid task owner and current epoch **at commit**. | Only effects mediated by trusted gateway. |
| F-02 | Safety | Protected effect ID has at most one durable commit. | Target supports atomic idempotency; not arbitrary APIs. |
| F-03 | Safety | Destination cannot commit without its own validated grant, prepared state and current epoch. | Grants must be separately authenticated outside toy model. |
| F-04 | Safety | After effective revocation, **no new** protected commit passes the gateway. | Past effects are not undone; revocation propagation/atomicity matters. |
| F-05 | Safety | Gateway partition/unavailability cannot yield an authorized commit. | Availability sacrificed for protected effects. |
| F-06 | Safety | Epochs never decrease and old instance tokens never become current after transfer. | Requires one authoritative epoch register. |
| F-07 | Safety | Move does not widen data classification, scopes, retention or budget. | Future cross-component refinement target; not in toy checker. |
| F-08 | Safety | An opaque, unconfirmed external result is not silently marked successful or retried. | Requires `UNKNOWN_RECONCILE` state and operator/tool reconciliation. |
| F-09 | Safety | Completed/terminal task records and lineage edges do not reverse. | Future persistence/integration test. |
| F-10 | Safety | No destination receives disallowed data before admission. | Requires independent sender/egress gate; issue #50. |
| F-11 | Progress | An authorized task eventually resumes after source failure. | Only with fair retries, a compatible checkpoint, available authority and an eventually available destination. |
| F-12 | Progress | An uncertain effect eventually resolves. | **Not unconditional**: may remain unknown until an external observer can determine outcome. |

Write **safety** claims as invariants over all permitted transitions. Write **liveness** separately, with explicit weak fairness / eventual connectivity assumptions. Do not equate timeout with proof of death or claim that a distributed partition can always preserve both immediate progress and one exclusive owner.

### Minimal protected handoff (pseudocode, proposed)

```text
move(task_id, source, destination, checkpoint, grant):
    assert authenticate(destination) and authorize_checkpoint_disclosure(...)
    assert verify_checkpoint(checkpoint) and compatible(destination, checkpoint)
    stage_checkpoint(destination, checkpoint)    # no activation or effect right
    new_grant = attenuate_and_issue(grant, destination, task_id, allowed_effects)
    # CAS and revocation check are atomic in the authoritative gateway.
    new_epoch = gateway.transfer_if_current(task_id, source, old_epoch,
                                            new_grant, policy_version)
    if transfer fails or gateway unreachable: HOLD   # not speculative dual execution
    destination.resume(checkpoint, token=(task_id, new_epoch, new_grant))
    record_movement_receipt(...)

protected_commit(token, effect_id, payload):
    gateway.transaction:
        require token.owner == current_owner(token.task_id)
        require token.epoch == current_epoch(token.task_id)
        require valid_grant(token) and not_revoked(token)
        if effect_id already committed: return cached_result
        require permitted_effect(effect_id, payload)
        commit_effect_and_dedup_record_atomically()  # when underlying effect cooperates
```

**Important limitation:** the last atomic line is an assumption, not an implementation technique for arbitrary remote services. An opaque external tool can acknowledge too late, commit before timeout, or have no lookup API. Treat the outcome as **unknown** and reconcile; a saga's compensation is a new authorized effect and is not automatically a rollback.

## 5. Executable small-state model (the first algorithm artifact)

The repo includes a standard-library-only breadth-first state explorer:

- [`tools/movement_modelcheck.py`](../tools/movement_modelcheck.py) — two workers (A, B), one task, epochs 1 and 2, independent destination grant, two stable protected effect IDs, gateway up/down, crash/restart, global revocation and a stale old worker;
- [`tests/test_movement_modelcheck.py`](../tests/test_movement_modelcheck.py) — safety, denial, deduplication, recovery of stale source and deliberate faulty-gateway regression tests.

Run from the repository root:

```sh
python tools/movement_modelcheck.py --depth 12
python -m pytest -q tests/test_movement_modelcheck.py
python tools/movement_modelcheck.py --depth 8 --unsafe-stale-writer  # expected exit 1
```

**Local verification (2026-10-16, isolated toy model):** depth 12 visits **336 reachable states and 1,130 transitions** and exhausts this finite model's reachable state space with no violation of its seven implemented invariant families. Six unit tests pass. The intentionally unsafe variant admits a stale epoch-1 writer after the gateway has transferred ownership to epoch 2, and the checker produces a four-step counterexample: `prepare_destination`, `issue_separate_destination_grant`, `atomic_fence_and_transfer`, `unsafe_stale_A_effect`.

The model is **not** wired to `agent_movement.peer`/`relocation`, and its boolean grants and single atomic gateway are abstractions. Therefore the result is **not a security proof of the repository**, nor a result for A2A, cross-host operation, live hardware, non-cooperating tools or dynamic credentials. Next refinement: extract observed traces from the actual coordinator/effect gateway and compare their transitions with the abstract specification. A TLA+/Apalache or PlusCal specification can then separately examine partial synchrony, multi-gateway behavior and refinement.

## 6. Placement and graph algorithms

Let `options = {stay, restart, delegate, relocate}` and candidate destination devices `d in D`. Each option-device pair is subject first to **hard constraints**: policy, tenant and data residency, destination attestation/trust, compatible runtime and checkpoint, memory/accelerator, energy and user-approved effect scope. Reject infeasible pairs; never turn a policy violation into a finite weighted penalty.

For a feasible pair `(o,d)` minimize a pre-registered expected loss:

`J(o,d) = w_L * latency + w_C * total_cost + w_E * energy + w_F * failure_risk + w_Q * expected_quality_loss + w_H * human_review_cost`

Calibrate weights, uncertainty and objective units; compare each option against `stay` and `restart`, and allow **HOLD** if none is admissible. One independent task over `k` candidate pairs with `r` predicates is `O(k*r)` to filter and score (excluding estimator and discovery cost). Joint placement of many tasks with multi-resource capacities and affinity can embed multidimensional knapsack/generalized assignment and is NP-hard; use exact ILP only when small enough, else measure heuristics and approximation/regret against a constrained baseline.

A trust/topology graph `G=(V,E)` needs **typed** edges: network reachability is not permission to move, and authenticated transport is not permission to invoke tools. Candidate paths must satisfy per-hop policy and residency; transfers should have bounded hop counts and prevent cycles/repeated unsafe fan-out. A multi-hop route's effective privileges are at most the intersection of grants along the path; a new node never inherits a parent's unrestricted credentials. Make route feasibility monotonic under adding a denial edge, and test this as a property.

## 7. Checkpoints, semantics, memory and duplication

Treat checkpoint portability as a **typed protocol compatibility problem**, not pickle serialization:

1. Distinguish agent *definition*, goal/context, execution checkpoint, tool effect ledger, memory store and credential reference. Record which of these was exported.
2. Specify a minimal portable IR: version, schema hash, task goal/invariants, state machine/program counter, pending intents, artifact digests, tool contracts, effect ordering and required capabilities. Unsupported required features cause refusal; optional losses are reported, not hidden.
3. Check semantic behavior experimentally: pre/post conditions, state invariants, correct tool use, task quality and forbidden-action rate after moving across two runtimes or models. Textual similarity does not prove equivalence.
4. For memory, use causal IDs/version vectors only when there is a meaningful merge policy. CRDTs solve convergence for specific data types, not semantic disagreement between two agent plans; shared executable authority should remain explicitly serialized or partitioned.
5. For clones/forks, assign fresh branch identity, tenant quotas, lineage and constrained grants. A child's permissions should be scoped to its assigned work. Concurrent budget spend needs atomic reservation or escrow-like allocation; mere independent counters can overspend.

General behavioral equivalence between arbitrary Turing-complete executions is not decidable in full generality. Make **bounded, typed, domain-specific continuity claims**, with counterexamples and measured loss. An LLM may produce a different answer even with an identical checkpoint; that's an empirical semantics question, not a proof of migration correctness.

## 8. Failure and recovery: an essential matrix

| Fault injection | Required result under stated assumptions | Future evidence |
| --- | --- | --- |
| Crash before destination preparation | No new owner; safe retry or abort | Coordinator state + recovery test |
| Crash after checkpoint upload but before CAS | Destination staged only, cannot commit | Prove activation gate precedes no effects |
| Crash immediately after CAS before ack | New epoch authoritative; source blocked; safe reconciliation of transfer status | Read-after-recovery authority record |
| Partition at gateway while A is still active | A/B protected effects fail closed | Partition test across distinct processes |
| Delayed A call after B is active | Stale epoch rejected at commit | Target-side check, not client-side belief |
| Replay effect ID after A->B | Same committed logical effect returned, never re-issued | Durable effect ID trace |
| Revoke during B's tool call | Result depends on **atomic commit-time** policy check | Commit boundary race test |
| Crash between opaque external effect and receipt | Report `UNKNOWN_RECONCILE` | Reconciliation and false-operator-decision cases |
| Cross-framework unsupported node/tool | Explicit incompatibility/loss report; no unsafe resume | Typed IR compatibility suite |
| Policy service unreachable or credentials invalid | No new admission/commit; log unresolved state | Independent enforcement-bypass experiment |

The [existing relocation fault matrix](checkpoint-relocation.md) is the implementation starting point; the model adds conceptual constraints but does not replace those tests.

## 9. Research program and measurable hypotheses

| Order | Proposed study | Hypothesis (to falsify) | Baseline and required metrics | Deliverable |
| --- | --- | --- | --- | --- |
| **1 / P0** | Authority refinement and attack traces | Every mediated protected effect in the declared secure profile refines F-01–F-06 under modeled crashes and replay. | Runtime-policy issue #50; permission-bypass rate, stale commits, unknown states, false denials | Abstract spec mapped to `core`, `peer`, `relocation`; negative controls. |
| **2 / P0** | External-effect ambiguity | Replay-safe effect ledger reduces duplicates, but an opaque post-commit crash must remain unknown absent independent evidence. | Idempotent target vs noncooperating target; duplicate count, safe recovery fraction, reconciliation burden | Two-tool-class benchmark and failure taxonomy. |
| **3 / P1** | Minimal checkpoint / semantic portability | For selected workflows, a typed, least-privilege state subset resumes with equal task correctness and fewer leaked bytes than transcript copying. | Same-runtime restart, re-run, delegate, full-history transfer; quality, violations, bytes, cost | Adapter-loss manifest and preregistered benchmark. |
| **4 / P1** | Constrained placement | A policy-first optimizer beats simple stay/restart baselines on cost per **correct** completion without security regressions. | Random, shortest-latency, always-stay, always-move; cost, p95, harm risk, failure, energy | Deterministic simulator, public benchmark seeds. |
| **5 / P1** | Fan-out and lineage authority | Budget-aware descendant grants bound resource amplification even with concurrent forks and late retries. | Naive copying vs scoped grants and atomic reservations; excess allocations and unauthorized effects | Multi-agent graph/fault model. |
| **6 / P2** | Offline/edge and multiple gateways | A system with independent gateways cannot provide one exclusive effect-owner claim during arbitrary partitions without stronger coordination assumptions. | Strong-consistency gateway vs offline lease/escrow alternative; safety, rejected work, recovery time | Explicit CAP/availability tradeoff and falsifying traces. |

**Scientific discipline:** Freeze fault schedule, code revision, model and runtime versions; define the oracle and allowed side effects before measurement; include negative cases; report **unavailable** and **unknown** results, and avoid claims from one deterministic synthetic run that generalize to real LLM agents.

## 10. Recommended concrete order of implementation

**First 2 weeks:** (a) merge/reconcile required runtime-policy enforcement before expanding claims; (b) keep abstract checker green and add an adversarial stale-writer negative control in CI; (c) document each implementation's trusted boundary and effect commit point.

**Weeks 3–4:** Add an executable transition-to-model adapter that records `owner`, `epoch`, grant ID, policy digest, effect ID and result status from current local demos. Test that every observed transition refines the abstract state machine; explicitly list non-refinable paths.

**Weeks 5–8:** Split protected/deduplicated effects from opaque ones; model ambiguous outcomes, timeout, cancellation and reconciliation as additional states. Expand from one task to two tasks and from one effect gateway to two independent gateways to locate missing coordination assumptions.

**Weeks 9–12:** Build a deterministic device/capability graph and placement baseline feeding MobilityBench. Only then evaluate checkpoint minimization, second-runtime IR and privacy-preserving context ablation. Publish counterexamples and unsuccessful hypotheses too.

### Acceptance criteria before calling a mechanism "verified"

- A declared actor/fault/adversary model, trust assumptions, and allowed network paths exist.
- Every advertised safety guarantee has a named invariant, a target-side enforcement point and a synthetic negative control that breaks when the guard is removed.
- Model and implementation traces are related through an explicit abstraction/refinement map, not just similar diagrams.
- The benchmark compares movement to **keeping, delegating, and restarting**; reports failure, privacy exposure, cost and ambiguity without hiding refused cases.
- No claim of universal migration, arbitrary external exactly-once effects, global deletion, or production security is made from a small-state or localhost experiment.

## 11. Foundations in established literature

These foundational papers and tools are **prior art**, not discoveries of this project. Their precise relevance and bibliographic identifiers are recorded in [the sources index](sources.md#distributed-algorithms-and-formal-foundations); the authoritative specifications for A2A, MCP, SPIFFE, OAuth token exchange and runtime persistence are also indexed there.

- Fischer, Lynch and Paterson (1985), *Impossibility of Distributed Consensus with One Faulty Process* — why asynchronous crash-fault progress needs assumptions. **Not** a blanket impossibility proof for every migration.
- Dwork, Lynch and Stockmeyer (1988), *Consensus in the Presence of Partial Synchrony* — conditional progress when timing assumptions eventually hold.
- Herlihy and Wing (1990), *Linearizability* — the authoritative transfer/commit point needs a precise consistency meaning.
- Chandy and Lamport (1985), *Distributed Snapshots* — consistent distributed snapshots and causal in-flight messages; not arbitrary private process-memory export.
- Garcia-Molina and Salem (1987), *Sagas* — compensating workflows as an alternative to blanket atomic multi-service transactions.
- Lamport (2002), *Specifying Systems* / TLA+; and current TLC tooling — for future temporal and refinement specifications.
- Featonby (2021), *Making retries safe with idempotent APIs* — operation identity, replay and mismatched intent in practical services.

**Research principle:** the main chance for a novel contribution is *composition*: measured continuity of work + enforceable changing authority + semantic compatibility + fault-aware economics, with the limitations visible in the protocol and benchmark.
