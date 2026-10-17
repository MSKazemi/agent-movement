# Guarded task legacy-ingress fence — receiver transaction (issue #50)

**Date:** 2026-10-17. **Status:** synthetic local SQLite enforcement only. This is an *effect-adjacent and acceptance-side* guard, **not** sender authentication, encrypted transport, a general external firewall or production policy enforcement.

## The discovered bypass

Existing `GuardedAuthority` enrollment fenced the low-level `EffectGateway.transfer/commit` path and, after PR #101, the separate peer effect ledger. However a legacy `HandoffReceiver` with a matching preconfigured `Approval` could still call `SQLiteStore.receive` for the **same guarded task ID**, producing a **successful accepted handoff receipt** based only on a *self-declared* origin. Although subsequent lower-level protected effects were refused, the admission itself violated the stronger invariant of issue #50:

> For a task enrolled in a guarded authority lane, no legacy/core task handoff may record an accepted transition or successfully replay an old receipt.

A legacy HTTP client can fully disclose its synthetic task text *before* receiving an error. The new target-side denial **does not reverse or prevent that disclosure**. It protects the *receiver acceptance and protected effect state*, not pre-disclosure confidentiality. No caller outside the shared protected task database is covered.

## Fix

- `SQLiteStore.receive` now calls the same `EffectGateway._deny_guarded` predicate **inside the existing `BEGIN IMMEDIATE` transaction and before idempotency/replay lookup or receipt insertion**. It refuses **all** low-level store entries for a task present in the shared `guarded_tasks` table. No untrusted request fields are accepted as policy overrides. `HandoffReceiver.receive` records a sanitized denial event after the denied store transaction rolls back, so an independent audit can distinguish forbidden attempts from accepted handoffs.
- `GuardedAuthority.enroll` now rejects *retroactive* enrollment when the same trusted SQLite database already has a `handoff.completed` event for that task. Historical legacy acceptance requires explicit reconciliation, even if the simulated effect ledger has no effects. This avoids presenting an already-disclosed task as newly protected.
- The legacy/core path for **unmanaged** tasks remains intentionally available for backwards-compatible local research. This is not a blanket change to authentication semantics or a shutdown of arbitrary external listeners.

**Concurrency boundary:** All checks/enrollment/admission effects use the *same* SQLite file and writer serialization. A guarded enrollment and legacy admission are ordered by the SQLite write lock; once enrollment commits, a legacy handoff cannot be accepted through that store. There is no guarantee across different SQLite databases, arbitrary external adapters, compromised DB administrators or effects that bypass the listed gateways.

## Independent adversarial tests

```sh
python -m pytest -q tests/test_guarded_legacy_ingress.py
python -m pytest -q tests/test_core.py tests/test_guarded_authority.py tests/test_review_regressions.py
make lint typecheck
```

`tests/test_guarded_legacy_ingress.py` verifies:

1. a direct low-level `SQLiteStore.receive` call denies a guarded task, including would-be replays;
2. a direct legacy `HandoffReceiver` call denies and records a sanitized `handoff.denied` event, with no accepted handoff or simulated peer effect;
3. an **actual loopback legacy HTTP listener** is probed from a **different Python client process**, bypassing official `PeerClient`; it returns 403 and an independent SQLite audit has zero accepted events for that guarded task;
4. a test-only red mutation disables `_deny_guarded` and demonstrates the same syntactically valid request would produce a successful handoff. No shipped runtime flag can turn off the guard;
5. unmanaged legacy handoffs remain successful and idempotent;
6. an already completed legacy handoff prevents later enrollment and unearned retroactive guarantees.

The tests operate on synthetic/public text, allowlisted IDs and local databases; no real external APIs, credentials or devices are touched.

## What remains unresolved

- Legacy HTTP is still **reachable and untrusted** for an unenrolled task, and an attacker may send plaintext text to it before it denies. To prevent data disclosure, operator-owned sender/egress controls and secured delivery are required.
- A2A, checkpoint relocation and independent tool-effect service each have distinct admission/persistence tables; this store-level guard **must not** be extrapolated to them without adapter-specific tests and integration.
- Operator permissions, human consent, ownership epochs, grant freshness and effects are protected only within their **specifically configured** peer/guarded lanes. The legacy receiver is not made authenticated by this patch.
- If history was purged or imported without full provenance, the retroactive `handoff.completed` check is not an absolute guarantee that no earlier unrecorded disclosure/effect occurred.
- [Issue #99](https://github.com/MSKazemi/agent-movement/issues/99) still needs an operator-owned secure-test launcher that disables or independently gates *all enabled actual listeners*. [Issue #98](https://github.com/MSKazemi/agent-movement/issues/98) adds the independent UID/FD/file experiments; broader [issue #50](https://github.com/MSKazemi/agent-movement/issues/50) remains open until its combined conformance criteria are demonstrated.

The [source-linked 16-route matrix](secure-test-route-inventory.md) still classifies legacy HTTP as **must_disable** for the strong secure-test deployment profile. This store-level acceptance check is defense-in-depth on tasks explicitly guarded in one authoritative store, not a replacement for disabling legacy in that profile.
