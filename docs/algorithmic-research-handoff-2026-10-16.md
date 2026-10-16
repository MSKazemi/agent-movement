# Research handoff — formal algorithms to enforced agent movement

**Checkpoint date:** 2026-10-16. **Primary project:** [Agent Movement](../README.md). This document saves the key decisions, evidence boundaries, unresolved problems and next executable experiments from the algorithmic-foundations work. It is a continuation map, **not** a release claim.

## Mission in one sentence

Study which aspects of an agentic task—**execution ownership, bounded permissions, relevant state, semantics and accountability**—can be transferred between executors with falsifiable safety and measurable utility. Treat `MOVE`, `DELEGATE`, `RESTART`, `FORK` and `CLONE` as distinct operations, not synonyms.

**Do not invent another universal transport protocol.** A2A and MCP already address neighboring interoperability layers. The research contribution should focus on verifiable authority transfer and semantic continuation under named failure assumptions.

## What this work established

| Layer | Saved artifact | Demonstrated within stated assumptions | Remaining gap |
| --- | --- | --- | --- |
| Vocabulary, algorithms and research agenda | [Computer-science foundations](algorithms-and-cs-foundations.md), merged [PR #85](https://github.com/MSKazemi/agent-movement/pull/85) | Ranked hard problems: fencing, grants, consensus assumptions, distributed snapshots, transaction ambiguity, type/semantic continuity, placement economics | No full formal proof of real system |
| Small abstract relocation checker | [movement_modelcheck.py](../tools/movement_modelcheck.py) | 336 states and 1,130 transitions in a fixed abstract experiment, with stale-worker negative control | No network/host containment |
| Model to current SQLite gateway | [runtime-model-refinement.md](runtime-model-refinement.md), merged PR #85 | Reachable synthetic traces replayed with independently read SQL owner/effect rows | Core low-level CAS not policy-complete |
| Unified authority model | [MASM-0.1](movement-authority-state-machine.md), merged [PR #92](https://github.com/MSKazemi/agent-movement/pull/92) | 59,200 states and 330,294 transitions in the **complete tiny finite model**; four weakened variants yield counterexamples | Model assumptions, especially one honest atomic gateway, are stronger than real deployments |
| First opt-in guarded runtime lane | [guarded-authority-transfer.md](guarded-authority-transfer.md), [PR #94](https://github.com/MSKazemi/agent-movement/pull/94) | Proposed implementation binds signed intent, scoped grant, multi-principal continuity, atomic fenced owner CAS and simulated effects on one SQLite store | Still requires CI, adversarial review, second implementation, multi-route mediation, external effect evidence |

The model exploration counts are observations for **fixed finite state spaces**, not general safety probabilities and not formal verification of hidden LLM state, arbitrary processes or hostile devices. Do not combine the two models' state counts as though they were independent production tests.

## Four decisions to preserve

1. **Protected effects, not apparent process death, are the enforceable property.** A stale agent process may remain alive. Enforce epoch fencing and authorization at the tool/effect sink in the same transaction where possible; never infer global shutdown from a heartbeat timeout.
2. **Sender approval is not authorization for every descendant.** Destination grants must be independently issued and attenuated, verified for task, audience, capability, policy version, expiry and revocation. If several principals own different rights, each relevant mandatory approver must consent.
3. **Serialization is not semantic continuation.** A checkpoint may deserialize yet produce incorrect work under another model or framework. Track semantic constraints, tool preconditions, uncertainty, and loss reports; compare to restart/delegation baselines.
4. **Unknown remote effect outcomes remain unknown.** A timeout does not imply that an action did not occur. Stable effect IDs work only when the target side cooperates. False human reconciliation claims can lose or duplicate real effects.

## Next work, in order

### P0 — Complete enforcement and model refinement

**Tracked:** [#93: real guarded authority transfer](https://github.com/MSKazemi/agent-movement/issues/93) and [#50: mandatory all-path runtime policy](https://github.com/MSKazemi/agent-movement/issues/50).

- Review PR #94's explicit trust boundaries and CI. Verify guarded enrollment is performed *before* any effect for tasks claiming the protected profile; reject pre-existing unaccounted effects rather than resetting a budget.
- Demonstrate every **enabled** path to a protected effect: core gateway, peer `authorized_effects`, A2A adapter, relocation, command tool/transport and subprocess. A verified origin *message* is not a sandbox. Disable or independently mediate alternatives when asserting a secure execution profile.
- Extend the MASM scheduler to generate executable failure schedules: revoke-before/after-fence, expiry and policy change at the commit boundary, duplicate concurrent effect IDs, crash/restart, partition/reheal, stale worker, shared-budget races, and unknown opaque effects.
- Collect independently observed database/event traces, not merely Python return values. Classify `PASS`, `COUNTEREXAMPLE`, `UNSUPPORTED`, `OUT_OF_SCOPE` separately.
- Specify and test crash-durability limitations of SQLite and cross-store authority assumptions. An atomic SQL transaction is not automatic distributed consensus.
- Request an independent review of operator-provisioned keys, authorization scope, clock trust, resource caps and bypass routes before making stronger safety claims.

**Done means:** guarded policy is evaluated at all *claimed covered* effect/transfer entry points and adversarial tests show no accepted forbidden operation within a published threat model. If one enabled sink remains unguarded, narrow the claim or keep #50 open.

### P1 — Semantics, portability and cost

- Define a typed *portable continuation contract* separate from model-private reasoning, checkpoint internals, tool credentials and hardware-specific state.
- Build a compatibility/loss matrix for same-runtime relocation, a second pinned framework, and restart/delegation baselines. Reject on unknown critical constraints; never silently drop safety requirements.
- Compare cost per **correct** completion, latency, context bytes, effect ambiguities, human interventions and privacy exposure, with failure injection and repeated stochastic trials when LLMs are introduced.
- Analyze multi-hop authority attenuation and memory divergence over forks/clones, including who can erase copies and how that evidence is scoped.

### P2 — Stronger formalisms

- Translate the abstract model into a TLA+/PlusCal specification with explicit state assumptions and fairness; add bounded TLC checking and mutation tests.
- Explore authority/consent composition as a typed capability calculus, and movement placement as an online constrained optimization problem. Formulate impossibility/tradeoff cases before claiming general solutions.

## Reproducibility and review gates

```sh
python tools/movement_modelcheck.py --depth 12
python tools/movement_authority_machine.py --depth 20
python -m pytest -q tests/test_movement_modelcheck.py tests/test_movement_refinement.py \
  tests/test_movement_authority_machine.py tests/test_guarded_authority.py
python -m pytest -q
make lint typecheck
make sources check-ids
```

The guarded transfer test is introduced by PR #94; it does not exist in `main` until the PR is merged. The model's negative controls deliberately exit nonzero on counterexamples and should not be placed in a success-only CI step without asserting the expected failure.

## Research reporting rule

Every result must state: **which abstraction was checked, source code revision, enabled routes, trusted components, concurrency/fault assumptions, initial state, acceptance oracle, counterexample trace if any, and excluded effects.** Fail closed on missing mandatory authorization facts, but never claim a system is globally safe because a single compliant Python API refused an unsafe request.

This handoff does not close #93 or #50. It documents the gap between the abstract theorem targets and deployable enforcement that should guide the next development session.
