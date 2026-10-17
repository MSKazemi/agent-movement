# Movement Authority State Machine (MASM-0.1)

**Status:** executable, bounded **research specification**, reviewed 2026-10-16. **Not production authorization, formal verification of the deployed runtime, or a new protocol.** [Executable model](../tools/movement_authority_machine.py) · [14 focused tests](../tests/test_movement_authority_machine.py) · [previous two-worker model](../tools/movement_modelcheck.py) · [runtime refinement boundary](runtime-model-refinement.md).

## Research question and result

What state must an agent movement authority coordinate so that two logically distinct executors cannot gain unauthorized *protected effects* when grants, approval, policy, time, budgets and network conditions change concurrently?

The proposed answer is a **product state machine**: task ownership is just one dimension of authority. The effect gateway decides using fresh, independently verified inputs under a single atomic decision-and-commit boundary. A movement is allowed only if the destination has a separately issued, attenuated and correctly bound grant. Human and data-owner permissions are **independent**. A revoked grant cannot be laundered by moving ownership.

The initial depth-eight run enumerated **15,453 distinct states and 59,981 transitions**, with no invariant violation, but correctly reports `complete_finite_state_space=false`. A deeper run (`--depth 20`) **exhausted the complete reachable graph in this fixed, tiny universe: 59,200 states and 330,294 transitions, with no invariant violation** (`complete_finite_state_space=true`). This is finite-model exhaustion **only under the explicitly stated two-worker, two-effect, bounded-clock and trusted-gateway assumptions**, not a theorem about the real Python runtime, arbitrary agents or hardware. The four negative-control mutations each produce a counterexample.

## Model, authority and fault assumptions

Model state (simplified):

\[
S=(q,o,e,G_u,G_d,G_B,\pi,t,b,n,c,r_A,r_B,U,L)
\]

where `q` is the movement phase, `o` the authoritative owner, `e` its fencing epoch, `G_u` the current user consent, `G_d` the independent data-owner consent, `G_B` the distinct destination grant, `π` the policy epoch, `t` bounded logical time, `b` shared effect budget, `n` gateway availability, `c` cancellation, `r_A/r_B` process responsiveness, `U` opaque-external-effect outcome (`none`, `unknown`, or an operator claim), and `L` the persistent protected-effect ledger. A single task, workers A/B, up to two logical protected effects and a fixed two-tick test clock form the deliberately small universe.

**Trusted subsystem:** one linearizable effect/ownership gateway; independent credential and principal-verification adapters whose results are **not derived from agent-supplied booleans**; an uncompromised policy authority; monotonic trusted time; serialized ownership, budget, revocation and effect-id decisions; gateway persistence; and a client that cannot bypass protected effect sinks. The toy model represents these assumptions **but does not implement or prove** cryptographic signatures, operating-system containment, hardware attestation, all-network-path mediation, real data retention or actual external-effect finality.

**Faults represented:** source/destination crashes and restarts, gateway partitions and recovery, reordering by exhaustive interleaving, revocation by either independent principal, policy epoch rollovers, expiry and cancellation, retries of protected-effect IDs, and ambiguous opaque external effects. The model does **not** include Byzantine gateway corruption, multiple independent consensus replicas, clock rollback, malicious database writes or a real third-party payment API.

## State and transition contract

| Operation | Required preconditions | Atomic / persistent effect | Explicit limitation |
| --- | --- | --- | --- |
| `prepare_destination` | Task not cancelled, origin phase | Phase becomes `prepared` | No real checkpoint transfer in this model |
| `issue_attenuated_grant_B` | Both principal approvals; right task/destination; scope subset; live parent policy/time | Distinct B grant bound to task, audience, actions and policy epoch | Signature verification assumed independent, not modeled |
| `fence_and_transfer` | Prepared, distinct grant live, no revocation/cancellation, trusted gateway reachable, no unresolved opaque effect | Owner A/epoch 1 → B/epoch 2 | Real core `EffectGateway.transfer` is a **lower-level CAS** with weaker checks; see below |
| `resume_destination` | Post-fence, task not cancelled | B becomes running | Synthetic readiness, not a runtime checkpoint validation |
| `commit_A_*` / `commit_B_*` | Current epoch, running worker, both principal grants, required audience/scope/task, matching policy, unexpired, gateway available, budget positive, effect ID unused, no unknown external outcome | One historical effect record, decrement shared budget | All effects are synthetic, not external API calls |
| `revoke_user` / `revoke_data_owner` | Independent authority event | Future transfers/commits denied; old effects remain recorded | No rollback of completed actions or remote copies |
| `cancel_task` | Task active | Blocks further protected commits/transfer | Does not stop arbitrary uncooperative code |
| `partition_gateway` | Gateway reachable | No new protected effects until healed | Trades availability for safety |
| `advance_clock` / `bump_policy_epoch` | Test time/version advances | Older grants no longer authorize effects | Rescoped reissuance is intentionally **not modeled** |
| `dispatch_opaque_effect_unknown` | Current live authority | `unknown` status; automated protected commits and transfer held | No claim about whether a remote effect happened |
| `operator_claim_done/absent` | Outcome `unknown` | Records a **claim** enabling continuation | Human truthfulness is outside the model; false claims can cause lost/duplicated real effects |

`authorize_child_grant` independently checks audience, task, requested scope attenuation, parent validity and required principals. Destination grants cannot be minted by silently treating the source's user approval as permission for the receiver. Even an accepted destination grant is insufficient after policy rollover or revocation.

## Safety properties and how to falsify them

| ID | Machine-checkable safety property | Negative-control or test |
| --- | --- | --- |
| MASM-I1 | Unique current owner and epoch consistent with the movement phase | Stale worker after transfer; direct invariant evaluation |
| MASM-I2 | Destination cannot become active before fencing and separate grant | Activation-order test |
| MASM-I3 | Child grant is strictly task/audience-bound and action-attenuated | Adversarial child-scope / task mismatch tests |
| MASM-I4 | Every protected effect came from the then-current epoch | `skip_epoch` mutation yields shortest stale-worker counterexample |
| MASM-I5 | User **and** data-owner grants are live at each effect commit | `skip_principals` mutation yields revoked-principal counterexample |
| MASM-I6 | Every protected effect uses the grant's policy epoch, required scope, task and audience | `skip_policy` mutation; wrong grant injection |
| MASM-I7 | Gateway reachable, clock within deadline and no cancellation at commit | Partition/expiry/cancellation tests |
| MASM-I8 | Effect IDs unique across A and B and budget decreases exactly once per unique commit | `skip_dedup` mutation and cross-epoch budget tests |
| MASM-I9 | Uncertain third-party outcome remains blocked until explicit operator reconciliation | Opaque-unknown and operator-claim tests |
| MASM-I10 | Revocation or cancellation never rewrites historical committed effects | Post-revocation historical-evidence test |

An invariant is evaluated on **historical facts captured at commit time**, not by comparing old commits with today's grants: revocation is not retroactive. Budget conservation is per task, not per copy, to prevent fan-out budgets resetting. All decisions are conditional on the trusted gateway actually mediating every protected effect.

### Formal-style transfer and effect predicates

\[
\begin{aligned}
\operatorname{TransferOK}(S) \equiv {}&\operatorname{Prepared}\land \operatorname{GrantBValid}\land G_u\land G_d\\
&\land\operatorname{PolicyMatch}\land\operatorname{GatewayUp}\land\neg c\land(U\ne\mathrm{unknown})\\
\operatorname{EffectOK}(S,w,i) \equiv {}&(w,e_w)=(o,e)\land G_u\land G_d\\
&\land\operatorname{GrantScopeAudienceTaskValid}\land\operatorname{PolicyMatch}\\
&\land(t\le t_{exp})\land(n=\mathrm{up})\land(b>0)\\
&\land(i\notin L)\land\neg c\land(U\ne\mathrm{unknown})
\end{aligned}
\]

The atomic effect update is `(L,b) := (L ∪ {i}, b−1)` under the same gateway decision boundary. A transport `ACK`, a model-generated statement of approval or a local transcript is **not** a substitute for that boundary.

## Reproduce and interpret

From the repository root:

```sh
python tools/movement_authority_machine.py --depth 8
python tools/movement_authority_machine.py --depth 20  # exhaust this particular tiny finite universe
python tools/movement_authority_machine.py --depth 8 --mutation skip_epoch
python tools/movement_authority_machine.py --depth 8 --mutation skip_principals
python tools/movement_authority_machine.py --depth 8 --mutation skip_dedup
python tools/movement_authority_machine.py --depth 8 --mutation skip_policy
python -m pytest -q tests/test_movement_authority_machine.py
```

The safe runs return exit `0`, `status: no_violation_within_bound` and an explicit completeness flag. At depth 20, the flag is true because all states reachable in **this finite specification** were explored; the status name deliberately does not imply runtime security. Mutated runs intentionally exit `1`, with a shortest trace and the violated invariant. Mutation controls are **negative tests**, not runtime configuration toggles. The tests compare two CLI runs byte-for-byte to catch accidental nondeterminism.

### Observed negative-control witnesses at depth eight

| Removed check | Counterexample trace (shortest under BFS ordering) | Invariant violated |
| --- | --- | --- |
| Current fencing epoch | `prepare_destination → issue_attenuated_grant_B → fence_and_transfer → commit_A_publish-1` | MASM-I4 |
| Independent principal check | `revoke_user → commit_A_publish-1` | MASM-I5 |
| Global effect-ID deduplication | `commit_A_publish-1 → commit_A_publish-1` | MASM-I8 |
| Policy epoch | `bump_policy_epoch → commit_A_publish-1` | MASM-I6 |

## Relationship to what the repository *actually* implements

- [`core.EffectGateway`](../src/agent_movement/core.py) uses SQLite transactions to enforce an owner/epoch on synthetic effects and stable IDs; a previously admitted task has runtime approval-revocation rechecks. Its low-level `transfer` CAS **does not** check the modeled independent multi-principal grants, cancellation, destination policy, expiry or opaque external outcome. In particular a low-level ownership transfer can still occur after revocation, while downstream synthetic effects are denied. This is a documented **model/runtime mismatch**, not a claim that the runtime implements MASM-I1 through MASM-I10.
- [`continuity_runtime`](../src/agent_movement/continuity_runtime.py) adds independently signed principal facts and a bound effect-side recheck for one opt-in peer receiver, but that **does not** automatically protect other handlers or the lower-level core gateway. See [continuity runtime enforcement](continuity-runtime-enforcement.md) and [the active mandatory-policy issue #50](https://github.com/MSKazemi/agent-movement/issues/50).
- [`movement_refinement`](../tools/movement_refinement.py) replays a narrower two-worker model against real SQLite transactions; it is not upgraded to a whole-protocol proof by this new specification.

**Next implementation experiment:** introduce an explicitly *guarded* ownership-transfer entry point that consumes verifier-produced principal/recipient/policy facts and checks them **atomically with the ownership CAS**; make it impossible to reach protected effects by a non-mediated path in an independently restricted test environment. Then run the same generated schedule corpus through a real runtime adapter. Do not weaken the existing core API tests by silently redefining the lower-level CAS as a full movement authorization decision.

## Safety, progress and prior work

These tests study **safety** (what never happens in an explored finite model). They do **not** establish progress or termination during an indefinite partition, unavailable approval service, a dishonest human reconciler or arbitrary Byzantine faults. Strict gateway dependence intentionally chooses safety over availability. Any liveness assertion needs an explicit fair scheduler, eventual connectivity, durable state availability and truthful independent observers. Distributed linearizability, asynchronous-consensus limits, consistent snapshots and compensating workflows are established prior art; the research contribution here is a falsifiable **composition contract** applied to agent movement, not a claim to invent these concepts. See [foundations](algorithms-and-cs-foundations.md), [the source index](sources.md), and [checkpoint relocation](checkpoint-relocation.md).