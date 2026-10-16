# MASM-to-runtime trace refinement — first bounded conformance suite

**Research status:** experimental synthetic model-to-SQLite projection, updated 2026-10-17. This is an executable **partial refinement**, not a proof of production agent migration, complete safety, actor/process identity, or cross-system exactly-once effects.

**Related:** [MASM-0.1](movement-authority-state-machine.md), [existing guarded transfer profile](guarded-authority-transfer.md), [earlier runtime bridge](runtime-model-refinement.md), [handoff](algorithmic-research-handoff-2026-10-16.md), issues [#93](https://github.com/MSKazemi/agent-movement/issues/93) and [#50](https://github.com/MSKazemi/agent-movement/issues/50).

## Goal and research decisions

The previous model counted 59,200 states but did not establish a simulation relation to the live guarded gateway. This study instead asks a smaller, falsifiable question:

> For shortest action schedules that have an explicitly declared mapping, do the independently observed durable task owner, fencing epoch, guarded registration, recorded synthetic effects, shared budget, revocation facts and policy epoch agree with the corresponding MASM state *after each step*?

The answer comes from test assertions over **fresh SQLite files**, not from trusting a gateway's returned value. Case names and shortest abstract traces are deterministically generated from the [MASM transitions](../tools/movement_authority_machine.py) using [the planner](../tools/authority_trace_plan.py). The [regression suite](../tests/test_guarded_authority_refinement.py) constructs separately signed synthetic facts, applies each mapped runtime action and reads committed SQLite records independently.

The planner defines **20 named cases** and searches only its supported subgraph through a bounded depth, stopping at one shortest witness per case. It does **not** assert the full 59,200-state model has been replayed, or that the supported subgraph is exhaustive.

## State and transition correspondence

| MASM event / fact | Runtime analogue | Oracle / claim |
| --- | --- | --- |
| Initial owner `A/1` | `EffectGateway.claim`, trusted test fixture | Independently read `owners` |
| `prepare_destination` | **Abstract marker only** | No runtime preparation is verified |
| `issue_attenuated_grant_B` | `GuardedAuthority.enroll` **pre-issued, verified** task/receiver grant and origin-signed intent | Guard row `status=prepared`; this does **not** prove actual grant issuance at this point |
| `fence_and_transfer` | Signed/receiver-owned authority checks in one SQLite write transaction | `owners` becomes `agent-b/2`, guard status `fenced`; no effect permitted |
| `resume_destination` | `GuardedAuthority.activate` with pinned destination-signed receipt | `guarded_activations` row and status `active`, but not verified process liveness |
| `commit_B_publish-{1,2}` | `GuardedAuthority.commit` with signed per-effect invocation bound to exact actor, epoch, effect and payload | Compare `effects` IDs and epochs and budget; signed request is not OS actor attestation |
| `revoke_user`, `revoke_data_owner` | Independent signed `ContinuityRuntime.apply_consent_revocation` | Committed consent tombstones and no accepted forbidden effects in named tests |
| `cancel_task` | Operator-signed `GuardedAuthority.cancel` for enrolled task | Durable `cancelled` flag and negative transfer/effect probes |
| `bump_policy_epoch` | Receiver-owned `ContinuityRuntime.advance_epoch(5)` | Current control epoch 5; guarded intent remains bound to old epoch |
| `advance_clock` (0→1→2) | Synthetic clock mapping `NOW / NOW+100 / NOW+1300` | Tick 1 inside grant+consent+observation validity; tick 2 beyond expiry, **not** a timing-equivalence proof |
| `dispatch_opaque_effect_unknown` | Operator-signed conservative `mark_unknown` | Durable hold **only**; no actual remote effect was dispatched |

The formal capability `publish` is projected to the runtime's restricted synthetic `word_count` task kind. This is a **case-specific mapping**, not a proof that arbitrary scopes are semantically equivalent. MASM starts with independent root approvals; the test fixture provisions both signed principal consents before trace replay, and revocation is still a real, durable operation.

The independent SQL snapshot reads (1) `owners`, (2) `guarded_tasks`, (3) `effects`, (4) `continuity_control`, (5) `continuity_consents`, and (6) `authorized_effects`. It compares the authoritative ledger after **every** mapped step. The last relation is that guarded tasks have **no peer-ledger effects**, not that other routes have been globally disabled.

### Named adversarial cases

The deterministic plan covers: grant preparation and transfer, destination running **as an abstract marker**, one and two protected effects, mandatory user/data-owner revocation before transfer or after resume/effect, cancellation before or after transfer, policy epoch rollover before or after transfer, expiry on either side of transfer, and an unknown opaque-effect hold before or after transfer.

On appropriate endpoints the suite also attempts a **denied** second transfer and a denied or idempotently suppressed new effect, confirming no new durable effect appears. These probes must not be mistaken for arbitrary interleaving or network-failure verification.

## The fenced activation counterexample is now a negative regression

The previous runtime allowed an effect immediately after fencing despite MASM
requiring a separate `resume_destination`. The current test denies even a
correctly signed effect invocation during `fenced`, independently verifies
that SQLite has no committed effect, then activates using a separately verified
destination-signed receipt. After the `resume_destination` model transition,
the actual runtime transitions to `active` and accepts a bound signed effect.

The witness runner now calls a real `GuardedAuthority.activate` operation,
rather than treating `resume_destination` as an abstract marker. Only
`prepare_destination` remains an abstract marker. This narrows the previously
known counterexample; it does not prove process liveness, real tools, or a
complete implementation of MASM.

## Alternate-route bypass regression

The guarded profile originally blocked the legacy `core.EffectGateway`, but a separate `peer.AuthorizedEffectGateway` stored simulated effects in `authorized_effects` without checking guarded enrollment. The new [peer change](../src/agent_movement/peer.py) denies this fallback under the **same SQLite `BEGIN IMMEDIATE` transaction** as the effect attempt, even if the caller constructs a bare `AuthorizedEffectGateway` with no `ContinuityRuntime` argument.

The new cross-process test reopens the same SQLite file from a separate Python interpreter, constructs the bare peer gateway with a caller-provided grant-shaped dictionary, attempts the forbidden effect, and confirms both denial and absence of a committed `authorized_effects` row. This is a stronger check than an in-process method stub, but **still assumes an honest host and OS-mediated database protection**: an attacker with arbitrary write access to the DB or unrestricted execution may bypass Python checks entirely. A2A, separate-store relocation, arbitrary subprocess tools and generic networking are **not** demonstrated mediated here.

## Unsupported / nonrefined dimensions

- MASM `commit_A_*` before movement: the guarded runtime enrolls before any protected effect and only permits destination-side effects after transfer.
- Source/destination crashes and restarts, partitions and gateway healing, independent-authority stores, hostile hosts and unmediated OS writes: no faithful fault injection here.
- `operator_claim_done/absent`: an operator's unsupported assertion cannot convert an unknown remote side effect into established fact. The runtime intentionally has no `clear_unknown` method.
- Real external tool/effect semantics, arbitrary delegated transport routes, device capability compatibility, actual model-state checkpointing, physical destination readiness and independent OS process identity: not covered.
- Cryptographic strength of symmetric test keys (HS256), trusted time source availability, compromised issuer, full multi-hop grant attenuation and distributed durability: outside the test assumptions.

The unguarded or alternate routes remain tracked in [#50](https://github.com/MSKazemi/agent-movement/issues/50). Trace replay and future activation/refinement remain in [#93](https://github.com/MSKazemi/agent-movement/issues/93).

## Reproduce and inspect

From the repo root:

```sh
python tools/authority_trace_plan.py --json
python -m pytest -q tests/test_guarded_authority_refinement.py
python -m pytest -q tests/test_guarded_authority.py
python -m pytest -q
make lint typecheck
```

The planner JSON contains only case IDs, synthetic action names, and excluded routes; no task text, credentials or private identifiers. To inspect one concrete schedule, run:

```sh
python -m pytest -v tests/test_guarded_authority_refinement.py -k data_owner_revoked_after_effect
```

**CI rule:** A green run establishes passing assertions for this bounded test profile only. If the projection or an observed effect diverges, retain the shortest violating witness and revise the model or implementation, not the oracle to match the desired result.

## Next implementable milestone

Exercise independently privileged actor identity, signed readiness after crash, real effect-gateway enforcement and a capability/route matrix across peer, A2A and checkpoint relocation. Signed receipts do not establish actual agent liveness. Keep #93, #50 and #102 open until their complete acceptance criteria are supported.
