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
| First opt-in guarded runtime lane | [guarded-authority-transfer.md](guarded-authority-transfer.md), merged [PR #94](https://github.com/MSKazemi/agent-movement/pull/94) | Tested opt-in implementation binds signed intent, scoped grant, multi-principal continuity, atomic fenced owner CAS and simulated effects on one SQLite store | CI passed; independent adversarial review, second implementation, multi-route mediation and external effect evidence remain open |
| Sender-side pre-disclosure gate | [secure-sender-gate.md](secure-sender-gate.md), merged [PR #90](https://github.com/MSKazemi/agent-movement/pull/90), [REG-058](../data/test-registry.csv) | Opt-in `PeerClient.handoff` checks verified identity, signer possession, signed grant, destination, task scope and revocation before discovery and again before delivery; 14/14 CI checks passed on PR head | A caller can bypass the API or invoke other transports; stale/revoked authority can still race after sender checks; not a global no-disclosure result |
| Independent-process network/spawn probe | [isolated-egress-lab.md](isolated-egress-lab.md), merged [PR #87](https://github.com/MSKazemi/agent-movement/pull/87), [REG-059](../data/test-registry.csv) | Linux/x86_64 separate child, syscall filter, trusted pipe broker, external loopback observer and 16-case deterministic evidence | Same-UID filesystem/IPC and inherited descriptors remain outside the fence; labels for A2A/legacy HTTP are generic socket probes, not actual adapter attacks |

The model exploration counts are observations for **fixed finite state spaces**, not general safety probabilities and not formal verification of hidden LLM state, arbitrary processes or hostile devices. Do not combine the two models' state counts as though they were independent production tests.

## Security boundary checkpoint after PR #90 (2026-10-16)

**Merge evidence:** [#87](https://github.com/MSKazemi/agent-movement/pull/87) merged as `ac378f04`; [#90](https://github.com/MSKazemi/agent-movement/pull/90) merged as `f0dae170` after 14 successful CI checks on its tested head `bef7235c`. Separate [#92](https://github.com/MSKazemi/agent-movement/pull/92) and [#94](https://github.com/MSKazemi/agent-movement/pull/94) refine the authority specification and an **opt-in single-store** guarded runtime lane. These are complementary experiments, **not one mandatory secure operating mode**.

| Protected boundary | Tested claim | Disclosure classification | Uncovered alternative |
| --- | --- | --- | --- |
| Configured peer sender `PeerClient.handoff` with `OutboundGate` | Unlisted endpoints/scopes, invalid grants, absent revocation service and signer mismatch abort before **discovery**; a revocation between admission and delivery aborts before task delivery | Before-discovery denial: **no outbound request**. Revocation after preflight: **grant metadata already disclosed, task text not sent** | Unguarded sender API, direct sockets and external tool calls |
| Continuity-configured peer receiver and SQLite effect gateway | Independent signer, grant, consent, epoch, manifest and revocation verification fence the covered simulated effect | Denial **after delivery** can block the effect but **cannot undo task-byte disclosure** | Other receivers and real third-party effects |
| Linux/x86_64 hostile child + trusted pipe broker | Tested socket/spawn bypass attempts are blocked under the installed seccomp filter; the broker accepts only allowlisted synthetic task IDs | Independent observer saw no additional tested loopback contact; this does **not** imply all exfiltration blocked | Same-UID file access, inherited FDs, `/proc`, unmodeled syscalls/IPC and unguarded parent |
| Opt-in guarded authority transfer in one SQLite store | Scoped signed intent and continuity facts, owner fence and simulated effect are checked in one local transaction | **Effect-sink safety only** for this guarded synthetic lane | Real tools, disjoint stores, split-brain network partitions and malicious operators |

**Invariant separation:** `unauthorized protected effect == 0` in a specified simulation is *not* equivalent to `payload never disclosed`, `agent cannot copy`, `all network paths blocked` or `cross-system exactly once`. A negative result must identify whether rejection happened before metadata transmission, before task text, or only at the effect sink. Where attempts are not independently observed, classify them `UNOBSERVED` or `OUT_OF_SCOPE`, never `BLOCKED` by assumption.

### Next three falsifiable experiments

**Implementation trackers:** [#98 — independently privileged worker and non-socket leakage](https://github.com/MSKazemi/agent-movement/issues/98) and [#99 — real legacy/A2A bypass conformance](https://github.com/MSKazemi/agent-movement/issues/99), both decomposed from [#50](https://github.com/MSKazemi/agent-movement/issues/50). These track work to do, not evidence that it has passed.

1. **P0 — Independently privileged worker boundary:** run the attacker under a different UID, controlled filesystem/mount and `/proc` access, strict inherited-FD inventory, resource limits and an independent host-owned network policy. Include deliberate positive control, file/IPC/FD attempts and unsupported-platform fail-closed behavior. Report each attempted channel as `BLOCKED`, `OBSERVED_ALLOWED`, `UNOBSERVED` or `OUT_OF_SCOPE`. The current seccomp denylist alone does not establish this result.
2. **P0 — Actual alternative-adapter enforcement:** start the *real* legacy HTTP and A2A listeners plus the authenticated peer handler under a single, explicitly documented secure-test profile. Verify direct signed/unsigned requests and bypassing the official client; either disable those adapters at an independent boundary or apply the same verified authorization and no-effect oracle. Report payload disclosure separately. Synthetic HTTP requests bearing `/a2a` as a label do not count.
3. **P0 — Independent effect-side authorization:** use a separately controlled tool-service process with signed, destination-bound, expiring grants and fencing/revocation checked at its own commit boundary. Inject partitions, stale workers, duplicate IDs, crash/restart, policy changes, confused-deputy requests and incorrect operator claims. Never call a callback in the same SQLite process a production tool guarantee.

**Acceptance rule:** keep [#50](https://github.com/MSKazemi/agent-movement/issues/50) open until all *claimed enabled paths* are inventoried and mediated, with independent adversarial evidence; [#93](https://github.com/MSKazemi/agent-movement/issues/93) continues the model/runtime refinement. Use [REG-058](../data/test-registry.csv) and [REG-059](../data/test-registry.csv) to find the current bounded sender and Linux evidence.

**Reproduce on the audited Linux/x86_64 platform** (without real user data):

```sh
python -m pytest -q tests/test_sender_gate.py tests/test_isolated_egress.py \
  tests/test_continuity_runtime.py tests/test_guarded_authority.py
python -m agent_movement.egress_experiment --output /tmp/amv-egress.json
cmp /tmp/amv-egress.json docs/isolated-egress-results.json
python tools/check_test_registry.py
```

On other platforms the Linux-only tests may skip; a skip is not a passed confinement experiment. CI is evidence for the tested code revision and environment, not certification or verification of the installed user's computer.

## Four decisions to preserve

1. **Protected effects, not apparent process death, are the enforceable property.** A stale agent process may remain alive. Enforce epoch fencing and authorization at the tool/effect sink in the same transaction where possible; never infer global shutdown from a heartbeat timeout.
2. **Sender approval is not authorization for every descendant.** Destination grants must be independently issued and attenuated, verified for task, audience, capability, policy version, expiry and revocation. If several principals own different rights, each relevant mandatory approver must consent.
3. **Serialization is not semantic continuation.** A checkpoint may deserialize yet produce incorrect work under another model or framework. Track semantic constraints, tool preconditions, uncertainty, and loss reports; compare to restart/delegation baselines.
4. **Unknown remote effect outcomes remain unknown.** A timeout does not imply that an action did not occur. Stable effect IDs work only when the target side cooperates. False human reconciliation claims can lose or duplicate real effects.

## Next work, in order

### P0 — Complete enforcement and model refinement

**Tracked:** [#93: real guarded authority transfer](https://github.com/MSKazemi/agent-movement/issues/93) and [#50: mandatory all-path runtime policy](https://github.com/MSKazemi/agent-movement/issues/50).

- Audit merged PR #94's explicit trust boundaries, even though its CI passed. Verify guarded enrollment is performed *before* any effect for tasks claiming the protected profile; reject pre-existing unaccounted effects rather than resetting a budget.
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
python -m pytest -q tests/test_sender_gate.py tests/test_isolated_egress.py tests/test_continuity_runtime.py
python -m pytest -q
make lint typecheck
make sources check-ids
```

The guarded transfer test is available in `main` after merged PR #94; its Python, static, corpus and docs-link GitHub workflows passed. The model's negative controls deliberately exit nonzero on counterexamples and should not be placed in a success-only CI step without asserting the expected failure.

## Research reporting rule

Every result must state: **which abstraction was checked, source code revision, enabled routes, trusted components, concurrency/fault assumptions, initial state, acceptance oracle, counterexample trace if any, and excluded effects.** Fail closed on missing mandatory authorization facts, but never claim a system is globally safe because a single compliant Python API refused an unsafe request.

This handoff does not close #93 or #50. It documents the gap between the abstract theorem targets and deployable enforcement that should guide the next development session.
