# Activated Guarded Authority v0.1 — signed, synthetic, opt-in

**Issue:** [#103](https://github.com/MSKazemi/agent-movement/issues/103) · **Status:** new **optional** single-store security research profile, not an all-route or production guarantee. This does not replace the legacy `GuardedAuthority` experiments, and it does not claim that all MASM state transitions are fully refined.

## Why an activation barrier is required

The [MASM model](movement-authority-state-machine.md) distinguishes source fencing from destination readiness. [Previous trace refinement](guarded-runtime-model-conformance.md) showed an explicit mismatch: standard `GuardedAuthority` accepted a synthetic protected effect immediately following a successful ownership transfer, before the model's `resume_destination` transition.

This experiment adds `ActivatedGuardedAuthority` to implement a stronger **explicitly opted-in** profile:

```text
source/epoch1 --signed enrolment--> PREPARED
PREPARED --atomic authority check + owner/epoch fencing--> FENCED (B/epoch2)
FENCED --destination signed activation + current authority--> ACTIVE
ACTIVE --destination signed effect instruction + current authority--> atomic simulated effect
```

Every protected operation on an activation-enrolled task is bound to one SQLite database. The enrollment inserts a `guarded_activations` record **in the same write transaction** as `guarded_tasks`; even a separately instantiated legacy `GuardedAuthority.commit` cannot bypass the check because it queries persisted activation enrollment before inserting effects. Base `EffectGateway.commit` and peer `AuthorizedEffectGateway.commit` already reject all enrolled guarded tasks under the SQLite lock.

## Trust and signed fields

A trusted operator constructs `ContinuityRuntime` with a pinned destination verifier, signed mandatory principal consents, observations, receiver ack, policy epoch and manifest callback. The destination signer is **not** learned from the caller's payload.

- `guarded-activation` signed proof: `{type, task_id, movement_id, destination_id, epoch, policy_epoch, grant_digest, activation_id, expires_at}`. The signer proves possession of the pinned destination key; all values must match current persisted owner/epoch, destination, signed destination grant, continuity policy and non-expired clock. Same signed token may replay without changing state; different activation ID/proof fails.
- `guarded-effect-intent` signed proof: `{type, task_id, movement_id, destination_id, epoch, policy_epoch, activation_id, effect_id, payload_sha256, expires_at}`. It is verified **again at the effect sink**. The payload commitment must match the exact UTF-8 effect body; the declared actor or epoch is not trusted without this signature. Policy freshness, receiver state, revocation, cancellation and an unknown-effect hold are rechecked under the same write lock as effect deduplication and budget charging.
- Signed tokens use **different purpose domains** in `trust.py`, so a valid activation cannot be reinterpreted as an effect instruction. In the test profile, HS256 is a synthetic *shared* key scheme: verification-key holders can sign, so the relevant threat model excludes compromise of the pinned operator/destination verifier. Separate asymmetric keys are preferable for stronger trust separation and will require independent testing.

No new HTTP listener, remote execution adapter, agent process sandbox, or real external effect is implemented. There is no guarantee of destination process liveness: the signed activation is a **bounded authorization event**, not a live attestation of runtime compatibility or semantic task continuation.

## Security properties exercised

| Scenario | Expected single-store behavior | Test |
| --- | --- | --- |
| Transfer without activation | no protected effect | `test_fencing_does_not_authorize_unsigned_or_pre_activation_effect` |
| Valid activation and effect | owner B/epoch2, one effect; stable replay free | `test_signed_activation_is_idempotent_and_exactly_one_effect_is_recorded` |
| Forged or wrong destination proof | no activation or effect | `test_signed_activation_rejects_wrong_binding`, `test_activation_rejects_forged_destination_key` |
| Wrong task/movement/epoch/policy/grant/expiry | fail closed | parametrized activation + effect tests |
| Changed effect body or forged instruction | fail closed | `test_payload_alteration_and_signature_forgery_are_rejected` |
| Retried or collided effect ID | idempotent replay, collision denial | stable digest test |
| Revocation, cancellation, policy rollover, expiry, unknown effect | no new protected effect | dynamic authority matrix |
| Concurrent identical activation | exactly one first state transition | concurrent SQLite test |
| Direct legacy route from separate process | reject persisted guarded task | child-process test |
| Budget exhaustion | no extra effects | shared ledger test |

## Reproduce

```sh
python -m pip install -e . 'pytest>=9.1'
python -m pytest -q tests/test_activated_authority.py tests/test_guarded_authority.py
python -m pytest -q tests/test_guarded_authority_refinement.py
make lint typecheck
```

**MASM replay update:** the optional activated profile is now exercised by the [bounded generated witness suite](../tests/test_guarded_authority_refinement.py). It verifies signed `resume_destination` and independently reads `guarded_activations` after each mapped step. The remaining projection is still partial: preparation, external effects, partitions, crash schedules and actual process identity are not modeled.

### Remaining issues / boundaries

- The earlier non-activation `GuardedAuthority` remains explicitly available for legacy synthetic experiments. It still has the documented mismatch to MASM's fenced/resumed distinction. Do **not** describe it as enforcing activated semantics.
- The test profile does not prove that the destination signing key is confined to a specific OS process or device. Shared signing keys can be cloned; the origin and target may still communicate through other unmanaged routes.
- No real host-level or independent tool service: [#98](https://github.com/MSKazemi/agent-movement/issues/98), [#99](https://github.com/MSKazemi/agent-movement/issues/99), [#102](https://github.com/MSKazemi/agent-movement/issues/102), [#50](https://github.com/MSKazemi/agent-movement/issues/50) remain separate requirements.
- Actual two-process activation/revocation *races*, crash-after-fence, liveness and cross-store failure experiments still require dedicated harnesses. The existing cross-process test attempts the core bypass, not an independently provisioned destination activation service.
- The bounded MASM witness test now opts into this profile and maps `resume_destination` to signed activation. Full MASM refinement, OS identity and crash/partition schedules remain unverified; retain red/green controls before stronger claims.
- An uncertain external effect must never be cleared by an unsupported operator assertion. The inherited `mark_unknown` remains irreversible in this prototype.

**Claim boundary:** this profile checks signers and state for a synthetic protected effect inside an honest SQLite authority host. It is neither general agent containment nor proof of physical process continuation or exactly-once execution at arbitrary external services.
