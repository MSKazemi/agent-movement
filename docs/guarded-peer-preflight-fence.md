# Guarded peer preflight / historical-effect fence (issue #119)

**Status:** single-store synthetic research defense-in-depth, not production peer authentication, remote availability or global egress prevention. This is a successor to [the legacy acceptance fence](guarded-legacy-ingress-fence.md), closing an uncovered *authenticated peer admission* path in the **same** SQLite authority file.

## Invariant and race model

For a `task_id` already in `guarded_tasks`, `PeerReceiver._preflight` must never create a signed admission for the separate unguarded peer lane. Its new `EffectGateway._deny_guarded` check occurs **inside the peer admission's `BEGIN IMMEDIATE` write transaction**, and protected enrollment uses the same SQLite writer lock. A direct raw signed peer call bypassing `PeerClient` receives 403 and creates **no** admission row.

Conversely, `GuardedAuthority.enroll` checks *three kinds of existing historical task state* before it can claim the task is protected: core simulated `effects` (existing), legacy `handoff.completed` (PR #114), and now **peer `authorized_effects` plus peer `peer_admissions`** (even preflight-only). These are inspected under its enrollment write lock. Preexisting peer history must be operator-reconciled rather than silently carried into a fresh effect budget/ownership lineage.

The `peer_admissions` table stores bounded synthetic JSON records rather than a separate indexed task ID, so enrollment scans historical admission JSON **while holding the SQLite writer lock**. This is acceptable for the toy single-store lab but **not a scalable production query**. Malformed persisted admission history fails closed. An admin who has purged history or controls the SQLite store can circumvent these properties; this experiment does not restore already lost evidence.

## Disclosure classification

| Request stage | Gate and verified evidence | Disclosure claim |
| --- | --- | --- |
| Signed peer preflight after enrollment | Target-side guard check; deny before signed admission or `peer_admissions` insert | A normal `PeerClient` stops before delivering task text; preflight metadata, card and scoped grant have already been sent |
| Peer preflight BEFORE enrollment | Peer admission serialized first; guard enrollment must refuse historical admission | Metadata already accepted; no claim that remote observer did not see it |
| Signed delivery for an old admission AFTER guarded enrollment (test-only inconsistent state) | Early receiver guard refuses before decrypt/task processing, and core `SQLiteStore.receive` independently refuses before receipt | Sender may already have transmitted task text, especially in plaintext mode; **post-disclosure denial** only |
| Bare peer simulated effect before enrollment | Immutable `authorized_effects` history blocks late fresh enrollment | Effect already committed; the guard cannot undo it |
| Unmanaged signed peer delegate | Existing peer flow succeeds with one modeled effect | Does not imply legacy/A2A safe or all-path mediation |

The signed issuer/receiver protocol, grant revocation and continuity checks are still enforced by the original peer modules; the new guard is an additional **shared-store route selector**. It does not replace actor authentication, multiple independent consent, policy version controls or target-owned simulated effect authorization.

## Evidence and falsification

```sh
python -m pytest -q tests/test_guarded_peer_ingress.py
python -m pytest -q tests/test_peer.py tests/test_guarded_authority.py tests/test_continuity_runtime.py
make lint typecheck
```

`tests/test_guarded_peer_ingress.py` exercises direct properly signed preflight bypassing the high-level client, an honest sender's **zero task-text disclosure**, independent SQLite admission/effect/audit counts, successful unmanaged peer baseline, preflight-only historical admission and peer effect history refusal, unrelated task scope, a **test-only gate removal** that visibly causes a forbidden admission, early delivery denial against a deliberately inconsistent test setup, and a two-thread preflight-versus-enrollment write-lock race. The red mutant never ships as a runtime option.

**Boundaries:** no new external tool, hardware device, Internet listener, OS namespace or cryptographic primitive. A previous accepted peer delivery cannot be undone, and a raw malicious sender may disclose task text regardless of our SDK. `peer_admissions` historical data are only a proxy for possible prior disclosure, so the conservative denial does not prove an actual payload was transferred. Other independent databases, A2A/legacy handlers, arbitrary local calls and compromised host/kernel/issuers remain outside this property.

This is a narrow advancement toward [#50](https://github.com/MSKazemi/agent-movement/issues/50) and [#93](https://github.com/MSKazemi/agent-movement/issues/93); neither should be closed on this result. A holistic operator-controlled cross-process secure profile remains [#99](https://github.com/MSKazemi/agent-movement/issues/99).
