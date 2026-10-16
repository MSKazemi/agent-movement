# Guarded Authority Transfer v0.1 — opt-in synthetic runtime experiment

**Research review:** 2026-10-16. **Status:** executable localhost/SQLite experiment, not production security, not an implementation of all MASM-0.1 transitions. **Related:** [the mathematical authority model](movement-authority-state-machine.md), [the first runtime refinement](runtime-model-refinement.md), and [P0 implementation issue #93](https://github.com/MSKazemi/agent-movement/issues/93).

## Why this exists

The lower-level `core.EffectGateway.transfer` is a correct simulated *epoch compare-and-swap*, but **not** a complete movement authorization decision. In particular, it could change the owner row after a task's authorizations were withdrawn, although its subsequent protected effects would be blocked for an admitted, revoked task. The new `GuardedAuthority` is a **separate opt-in lane** that keeps the old API available for unguarded research tasks and fences legacy operations for a specifically enrolled guarded task.

This is a **bounded improvement**, not closure of the all-path security objective [#50](https://github.com/MSKazemi/agent-movement/issues/50). Only the gateway-owned SQLite `owners` and `effects` path is guarded by the new runtime. Synthetic peer `authorized_effects`, A2A, relocation's own ledger, arbitrary TCP/HTTP, OS execution and external APIs remain separate implementations and are **not proven covered**.

## High-level contract

A trusted operator provisions:

- **One authoritative SQLite database:** `SQLiteStore`, `ContinuityRuntime`, peer grant revocation ledger and guarded state all on the *same path*. The protected effect must share that database transaction, not merely consult an HTTP policy service beforehand.
- **Verified issuer roots:** `TrustStore` and `ContinuityRuntime` share the same grant-trust object; origin-verifier keys are pinned outside the untrusted agent. A signed origin intent binds movement, task, destination, expected source epoch, kind, classification, policy epoch and digest of the independently signed destination grant.
- **Independent receiver-owned policy facts:** `ContinuityRuntime.require` checks signed mandatory principal consents, destination acknowledgement, observation freshness, measured manifest, scope and policy epoch. The test fixture requires **human and data owner** approvals; different deployments must define the rights model themselves.
- **A trusted local clock and operator budget:** the caller cannot supply the current time, maximum effect budget, receiver policy or an `authenticated: true` claim. Credential rotation and workload identity are not implemented.
- **Authenticated cancellation and unknown-outcome holds:** separate signed operator notices set durable irreversible flags in the same database. These are conservative holds, not evidence that every opaque tool action was discovered or globally undone.

### State transitions

```text
UNMANAGED (legacy lab profile)
  -> signed intent + verified destination grant + all receiver-owned policy facts
  -> guarded_tasks PREPARED (enroll must happen before any task effect)
  -> recheck current signed grant, policy, revocation, expiry, cancellation, unknown hold
  -> owners CAS source A/epoch N -> destination B/epoch N+1
  -> guarded_tasks TRANSFERRED
  -> destination's guarded simulated effect: check B+epoch, current grant/policy,
     cancellation/unknown hold and shared budget; insert effect + decrement budget
     in the same SQLite write transaction
```

The origin may still be running; it cannot commit via either `core.EffectGateway` (blocked on enrolled tasks) or the guarded lane with stale identity/epoch. Attempts to call the low-level transfer/commit from a **separate Python process** are explicitly tested.

### Signed intent fields (all mandatory)

```json
{
  "type": "guarded-transfer-intent",
  "movement_id": "movement-1",
  "task_id": "task-1",
  "origin_id": "agent-a",
  "destination_id": "agent-b",
  "expected_epoch": 1,
  "kind": "word_count",
  "classification": "synthetic",
  "policy_epoch": 4,
  "grant_digest": "<SHA-256-of-signed-grant>"
}
```

The intent must be sealed under the purpose `guarded-transfer-intent`, verified against a *pinned origin key*, and accompanied by an issuer-signed grant for precisely the declared origin, destination, task, capability and classification. This example is schematic; do not commit real keys or task contents.

## Invariants in this controlled experiment

| Property | Enforcement point | Test |
| --- | --- | --- |
| Signed issuer, source proof, audience, task, kind | `enroll` verifies both signed objects; no self-reported auth | forged/scope-mismatch cases |
| Independent principal consent and obligations | `ContinuityRuntime.require` in every guarded write transaction | missing human, owner, sensor, acknowledgement, quarantine |
| Revocation and grant expiry at transfer | `transfer` checks peer grant revocations and continuity facts before CAS in the *same* `BEGIN IMMEDIATE` | withdrawal before transfer |
| Revocation/policy expiry at effect commit | `commit` rechecks both authorities *before* deduplication | post-transfer withdrawal, expiry and policy epoch rollover |
| No old owner effect / legacy bypass | guarded effect checks current owner+epoch; legacy gateway checks durable guard enrollment | stale owner and external child process |
| Idempotent synthetic protected effects | stable `task_id,effect_id` primary key; modified payload rejected | duplicate, collision |
| Budget conservation | shared guarded task budget and synthetic effect insert update together | exhausted budget and replay |
| Cancellation / uncertain effects fail closed | signed operator-authenticated flags checked in same transaction | cancel and unknown hold |
| Pre-existing effects cannot be silently budget-reset | enrollment refuses if a committed simulated effect already exists | late enrollment denial |

**Scope of atomicity:** a single SQLite store, under the trusted host/process, with a single writer lock. A network partition, alternate unmediated tool, compromised host, untrusted issuer/clock, external effect that succeeded without an acknowledgement, or a second independent authority database is **outside the modeled guarantee**. There is no proof of global termination, confidential transport or universally exactly-once side effects.

## Reproduce

```sh
python -m pip install -e . 'pytest>=9.1'
python -m pytest -q tests/test_guarded_authority.py tests/test_core.py tests/test_runtime_revocation.py
python -m pytest -q
make lint typecheck
```

There are no model keys or real tools. The new gateway is an *importable Python class*, not a new public network endpoint or a replacement for A2A/MCP.

## What remains open before issue #93 can close

1. **Effect-side universal coverage:** guard all enabled peer, A2A and relocation effect interfaces or disable them under an independently enforced secure profile. The core low-level fence alone is not complete mediation. This depends on [#50](https://github.com/MSKazemi/agent-movement/issues/50).
2. **Semantic model/runtime refinement:** generate specific schedule traces from [MASM](../tools/movement_authority_machine.py), replay them through `GuardedAuthority` under subprocess fault injection, and compare authoritative durable SQL state to the abstract state. This module is a smaller, testable profile—not a full MASM-0.1 implementation.
3. **Unknown-effect reconciliation:** the signed `mark_unknown` command can *park* but deliberately cannot claim a real remote effect was undone. Implement a separately verified operator/external proof path before resuming.
4. **Recovery and continuity:** model actual checkpoint compatibility, network outages, two-store failures, policy service loss and destination liveness. Initial enrollment explicitly rejects pre-existing simulated effects.
5. **Independent security review:** key pinning, possible unmediated writes from other authorized modules, host compromise, tenant isolation, clock failure, durability under sudden power loss and OS-level process bypass remain unresolved.

### Scientific reporting

Publish a row for every supported transition: `(source_state, verified_facts, action, SQL_observation, expected_state, failure_reason, boundary)`. Mark every missing route `UNTESTED` or `OUT_OF_SCOPE`; do not count a refusal on a different route as proof that this one is mediated. This work improves a particular runtime safety property without making a production security claim.
