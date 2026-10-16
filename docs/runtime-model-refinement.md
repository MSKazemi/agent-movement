# A first runtime refinement bridge: model states vs committed SQLite effects

**Research review:** 2026-10-16. **Status:** executable, synthetic, bounded experiment, not a formal proof of deployed agent movement. This is the second step of [algorithms and CS foundations](algorithms-and-cs-foundations.md), connecting the abstract [movement explorer](../tools/movement_modelcheck.py) with the **actual** [`core.EffectGateway`](../src/agent_movement/core.py), receiver admission and signed revocation.

## Question and decision

Can a modeled, protected ownership-transfer schedule be replayed against *real Python and durable SQLite transactions*, and do independently read durable effects agree with the model? For a **narrow subset**, the new [refinement runner](../tools/movement_refinement.py) and [tests](../tests/test_movement_refinement.py) make that claim falsifiable. We explicitly avoid calling a caller-returned `True` a proof of committed effects: every transition reads the owner and effect ledger from the database independently.

This experiment **does not** map an arbitrary LangGraph checkpoint into a portable runtime, control an OS agent process, prove network containment or verify a complex LLM's semantic continuation. The destination is a different logical executor ID; the simulated effects are SQLite rows only. The origin's remaining process is not forcibly stopped.

## Relation and boundaries

The first model checker explores 336 finite abstract states with crashes, gateway partitions, epoch ownership, a separate grant and revocation. Not every abstract action has a counterpart in `core.py`. The refinement experiment uses the shortest trace to each reachable state in the **explicitly replayable subgraph** (with crashes and partitions excluded). Its projection is deliberately smaller than the complete model.

| Abstract event | Corresponding runtime activity | Evidence | Coverage statement |
| --- | --- | --- | --- |
| Initial owner `A/1` | `EffectGateway.claim(task-1, agent-a)` | Read `owners` row independently | Observed |
| `prepare_destination` | No equivalent in the core gateway | Abstract marker only | **Not verified** |
| `issue_separate_destination_grant` | No equivalent to independent destination grant issuance in the core gateway | Abstract marker only | **Not verified** |
| `atomic_fence_and_transfer` | `EffectGateway.transfer(agent-a, epoch 1, agent-b)` | Epoch 2 in `owners` | Observed |
| `resume_destination` | No core runtime/scheduler activation check | Abstract marker only | **Not verified** |
| `commit_A_effect-*` / `commit_B_effect-*` | `EffectGateway.commit(...)` | `effects` rows + return value + reconciliation | Observed under simulated gateway |
| `revoke_authority` | Receiver-signed notice using pinned test issuer; `HandoffReceiver.revoke` | Durable revocation row; subsequent effect denial | Observed **for previously admitted task** |
| `crash_*`, `restart_*` | No model/runtime mapping in the trace explorer | Deliberately excluded | **Not verified** |
| `partition_gateway` / `heal_gateway` | No real networked gateway in core | Deliberately excluded | **Not verified** |

**Important composition assumption:** The runner first admits a synthetic `delegate` task through `HandoffReceiver` so it can test a signed revocation binding. It then independently gives the core effect gateway an `agent-a` owner and transfers it to `agent-b`. This is a controlled composition of two existing mechanisms, **not** proof that the current receiver implements full ownership relocation. Neither the receiver's authenticated identity nor a separate destination grant is supplied to `EffectGateway` by this synthetic core composition. The peer/continuity runtime remains a distinct implementation boundary.

## Refinement relation and executable oracle

For a modeled state \(s\), define \(R(s)\) as the tuple:

\[
R(s) = (\mathrm{owner}(s),\ \mathrm{epoch}(s),\ \mathrm{sortedCommittedEffectIdsAndEpochs}(s),\ \mathrm{revoked}(s)).
\]

For the observed SQLite state \(D\), independently read the same four fields by querying the `owners`, `effects` and `approval_revocations` tables. After each replayable step, the runner requires:

\[
\mathrm{ReadSQLite}(D) = R(s).
\]

Both **successful commit** and **denied/replayed effects** are checked. Negative probes attempt a stale epoch, a stale ownership transfer, an identical effect replay, an effect-ID/payload collision, and a new/replayed effect after signed revocation. The runner also checks that these probes cannot add or alter committed effects, and that absent local ledger records return `unknown`, not an invented assertion about remote tools.

Because the runner has abstract-only markers, the result is a **trace-projection conformance test** for specific transactional state, not a complete forward-simulation or bisimulation proof. A useful stronger follow-up would prove that every real gateway transition in scope corresponds to an abstract transition, including all relevant rejected requests and adversarial schedulings.

## Run it

Use core-only dependencies; no LLM key or network target is needed:

```sh
python -m pip install -e . 'pytest>=9.1'
python tools/movement_modelcheck.py --depth 12
python tools/movement_refinement.py --json
python -m pytest -q tests/test_movement_modelcheck.py tests/test_movement_refinement.py
```

The JSON report separates `abstract_only:*` markers from `atomic_fence_and_transfer`, `protected_effect_commit`, and `signed_revocation` runtime observations. It also includes an explicit `excluded` field. Each trace gets a fresh SQLite database and throwaway signed-revocation key; database contents are not published. No wall-clock durations, model output, or random key bytes appear in the output.

The tests include a separate **real child process** that opens the persisted database after a transfer and attempts a stale `agent-a/epoch1` commit (expected deny) and an authorized `agent-b/epoch2` commit followed by an idempotent replay. This is a process-boundary persistence test, not an OS sandbox escape experiment.

A deliberate SQL write of an impossible extra effect is a **negative control** for the independent observer: the projection check must detect it. It is not an assertion that a compromised SQLite host cannot tamper with records, or that database inspection detects side effects performed outside this gateway.

## Known counterexample to whole-protocol refinement

The current `EffectGateway.transfer` uses an epoch compare-and-swap but **does not check whether the receiver's task approval was revoked**. In the synthetic test, a signed revocation is accepted and then the core ownership transfer still succeeds. The later effect commit is nevertheless rejected because the gateway rechecks the revoked approval at commit.

This is a genuine specification-to-implementation distinction: the abstract model disallows transfer after revocation, but the lower-level core gateway permits an authority-row change that cannot produce authorized effects. We document the mismatch rather than disguising the lower-level API as a complete movement protocol. No P0 all-path policy claim should be based on this experiment; [mandatory enforcement issue #50](https://github.com/MSKazemi/agent-movement/issues/50) remains separate.

**Other incomplete properties:** core effect expiry is not rechecked after admission; a direct `EffectGateway.claim` with no admitted handoff has no approval binding; broader transport and A2A paths are not gated by this test; a partition of an external gateway, external-world exactly-once execution, device-level side effects and arbitrary framework checkpoint equivalence are not covered. Exactly-once claims are limited to **the local keyed effect ledger** with a single cooperating SQLite store.

## Recommended next experiments

1. Extend the trace relation to the authenticated [`peer` and continuity runtime](continuity-runtime-enforcement.md), deriving identity, grant and obligation facts from verifier-produced observations rather than caller-provided fields.
2. Model an explicitly gated admission and transfer operation that atomically couples policy, destination grant and epoch; choose whether revocation blocks the transfer itself or only its effects, and reconcile the abstract model accordingly.
3. Add independent OS/process and gateway-partition fault injections (including alternate ingress paths), building on the real [relocation fault matrix](checkpoint-relocation.md) and [unauthorized movement threat tests](unnoticed-and-unauthorized-agent-movement.md).
4. Study an abstract-to-runtime trace witness format with stable IDs, authority epoch, decision scope and evidence source that does **not** disclose task text, signing secrets or private reasoning.
5. Use counterexamples and fault trajectories as **new MobilityBench tracks**, not as benchmark successes. Pre-register expected failures, disabled paths, and the conditions under which a case is outside the formal model.

**Acceptance for the next milestone:** a combined admission/transfer/effect state machine with a trusted destination grant, independently monitored execution paths, signed revocation across all enabled test routes, and observable exact failure semantics under crash/partition. Until then the result is an empirical subset refinement only.