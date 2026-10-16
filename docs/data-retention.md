# Data retention

This page lists what the local experiments store, why, for how long, and how to delete it. It covers the SQLite store behind `SQLiteStore` (core handoffs, the peer path and the A2A adapter), the relocation files, and the signed-receipt artifacts. It was added for [issue #39](https://github.com/MSKazemi/agent-movement/issues/39).

Everything here is a **synthetic, local research prototype**. This page describes how the code behaves. It is not a compliance statement for any law or standard.

## Summary

- **No plain content digests in a store.** Since store layout version 2, a digest of task content (envelope, result artifact or effect payload) is stored only as a *keyed commitment*: HMAC-SHA256 under a random 32-byte secret created with the store. Plain SHA-256 is gone from the file, from `SQLiteStore.audit()` and from the A2A correlation log, so someone holding one of them cannot confirm a guess of low-entropy task text (`"yes"`, a name, a short number) by hashing candidates. Opening an older store migrates it in place.
- **History expires on request.** `agent-movement purge --db FILE --older-than 30d` deletes rows older than the retention period from every table with a time column, records the purge in `retention_purges`, and overwrites the deleted content on disk.
- **Safety state is kept.** Purge never deletes task owners and epochs (fencing), the effect ledgers, parked effects awaiting (or holding) an operator decision, grant revocations, admissions or grant-use counts of a grant that could still be presented, replay nonces inside the clock-skew window, the store secret, or any relocation/checkpoint table.
- **No automatic expiry.** A store keeps everything until someone runs `purge`. There is no built-in default period, because the period ends the idempotent-retry window (see [Consequences](#consequences-of-a-purge)).

## What a store file holds

The demos create their stores in temporary directories and delete them on exit. A store persists only when you choose its path, for example `python -m agent_movement.http --db FILE`, `python -m agent_movement.a2a_server --db FILE`, or a path passed to `SQLiteStore`, `PeerReceiver` or the relocation API.

| Table | Written by | Contents | Why it is kept | Purge rule (age column) |
|---|---|---|---|---|
| `deliveries` | `SQLiteStore.receive` | sender, idempotency key, movement ID, keyed envelope commitment, receipt *without* content fields, `created_at` | Idempotency: an exact retry replays the receipt instead of executing again; a different envelope under the same key is a conflict | purged by age (`created_at`) |
| `audit_events` | `SQLiteStore` | movement and task IDs, event type, keyed commitment, time | Handoff audit trail | purged by age (`event_time`) |
| `owners` | `EffectGateway` | task ID, current owner, epoch | **Fencing**: a stale executor is refused because its epoch is old | **retained** |
| `effects` | `EffectGateway` | task ID, effect ID, keyed payload commitment, epoch | Exactly-once record of simulated effects; `reconcile()` reads it | **retained** |
| `store_secret` | `SQLiteStore` (created once) | the 32-byte HMAC key and its creation time | Needed to recompute every commitment | **retained** |
| `peer_nonces` | `PeerReceiver` | origin ID, preflight nonce, time seen | Refuse a replayed preflight | purged by age (`seen_at`), never inside the last 3600 s |
| `peer_admissions` | `PeerReceiver` | admission record: IDs, origin card, signed grant, client-salted task commitment, nonce, expiry | A delivery must present a live admission; a retry of an admitted movement must keep its binding | purged only when the admission **and** its grant expired before the cutoff, together with its `grant_uses` row |
| `grant_uses` | `PeerLedger` | grant ID, movement ID, use number, `max_uses`, time | Single-use and counted grants (issue #29) | purged only with its admission (see above), so a live grant never regains uses |
| `grant_revocations` | `PeerLedger.revoke` | grant ID, revocation time | A revoked grant must stay refused | **retained** |
| `approval_revocations` | `HandoffReceiver.revoke` (issue #38) | approval ref, issuer key ID, claimed and recorded revocation time, SHA-256 of the public signed notice | A runtime-revoked approval must stay refused at admission and at effect commit | **retained** |
| `task_approvals` | `SQLiteStore.receive` (issue #38) | task ID, approval ref it was delivered under | `EffectGateway.commit` refuses effects of a task whose approval was revoked | **retained** |
| `authority_log` | `PeerLedger` | revocation and effect-authorization events (IDs and times) | Authority history | purged by age (`at`) |
| `authorized_effects` | `AuthorizedEffectGateway` | task and effect IDs, grant, agent, keyed payload commitment | Exactly-once record of authorized simulated effects | **retained** |
| `peer_trace` | `PeerReceiver` | stage, outcome, reason code, IDs, time | Sanitized receiver trace | purged by age (`at`) |
| `a2a_correlations` | `A2ACorrelationLog` | A2A task, context and message IDs, movement and trace IDs, outcome, keyed envelope and artifact commitments, time | Join A2A tasks to handoff audit events | purged by age (`event_time`) |
| `retention_purges` | `purge` | time, periods applied, rows deleted per table | Audit of purges | **retained** |
| `relocations`, `opaque_effects`, `effect_intents`, `node_runs`, `bundle_imports`, `checkpoints`, `writes` | [checkpoint relocation](checkpoint-relocation.md) and LangGraph's `SqliteSaver` | ownership moves, effect intents, node journal, imported bundles, LangGraph checkpoints | Fencing, effect reconciliation and resume state; these tables have no time column | **retained**; see [Relocation files](#relocation-files) |
| `effect_reconciliations` | operator reconciliation (issue #30), coordinator file | parked unknown-outcome effects, their status and the first (final) operator decision | An unresolved parked effect must never disappear; a decided one must not be settled twice | **retained** |
| `reconciliation_events` | operator reconciliation (issue #30), coordinator file | append-only log of park, decision and denial events | Explains the decisions kept in `effect_reconciliations` | **retained** |

No table stores task text. The peer path keeps task text out of the store by design ([peer authentication](peer-authentication.md)). The core path stores only IDs and commitments. `purge` reports a table it does not know as `unmanaged` and leaves it alone.

## Keyed commitments

Every content digest a store writes is

```text
keyed_digest(h) = HMAC-SHA256(store_secret, "agent-movement/store-commitment/v1" || 0x00 || h)
```

where `h` is the plain SHA-256 hex digest the code computed before issue #39 (of the canonical JSON envelope, of the artifact, or of the effect payload). `SQLiteStore.fingerprint(value)` is `keyed_digest(digest(value))`. HMAC is the keyed hash of RFC 2104 ([SRC-HMAC]).

- **Equality still works.** Within one store, equal inputs give equal commitments, so idempotent retries, envelope conflicts and effect-payload conflicts are detected as before. Across stores they differ, so two stores cannot be joined on commitments.
- **The receipt a sender gets is unchanged.** `receive()` still returns plain `envelope_digest` and `artifact_digest`, so the sender can check them. The store keeps a receipt without those fields and without the artifact; on a replay it recomputes them from the presented envelope. The tasks are pure, and the commitment check has already shown that the presented envelope equals the original.
- **Where the secret lives.** The `store_secret` table, in the same file, outside every export: `audit()`, receipts, the A2A correlation rows and the purge log never contain it. It protects exported audit data and logs. It does **not** protect against someone who has the whole file, because the secret is in it. A deployment that needs that protection would keep the secret outside the file, for example in a key service. That is not implemented.
- **The secret is never regenerated.** If the row is missing, `SQLiteStore` refuses to open the file (`StoreSchemaError`). A fresh secret would silently make every stored commitment mismatch, turning exact retries into conflicts.
- **Why HMAC over the digest.** Wrapping the old plain digest, rather than the raw content, lets the migration convert existing rows without the original content.

### Migration from layout version 1

The layout version is kept in `PRAGMA user_version` (`STORE_SCHEMA_VERSION = 2`). Opening an older file migrates it in one `BEGIN IMMEDIATE` transaction, after the version 0 to 1 step of issue #29 if that is needed:

1. it creates `store_secret` with a fresh random key;
2. it rebuilds `deliveries` (create, copy, drop, rename), wrapping each envelope digest, removing the content fields from each stored receipt, and backfilling `created_at` from the movement's earliest audit event (or the migration time if there is none);
3. it wraps, in place, `audit_events.info_digest`, `effects.payload_digest` and, if those tables exist in the file, `authorized_effects.payload_digest` and the two digest columns of `a2a_correlations`.

Concurrent openers serialize on the lock and re-read the version, so the wrap runs exactly once. A stored receipt that is not a JSON object aborts the migration with `StoreSchemaError` and leaves the file unchanged. The migration connection uses `PRAGMA secure_delete` and ends with a `wal_checkpoint(TRUNCATE)`, so the replaced plain digests are overwritten rather than left in free pages or in the write-ahead log ([SRC-SQLITE-PRAGMA]). There is **no downgrade**: older code cannot insert into the new `deliveries` table and would treat every stored commitment as a conflict. Back up the file before upgrading if you might roll back.

## Purging

```bash
# Count what would go, delete nothing:
agent-movement purge --db receiver.sqlite --older-than 30d --dry-run
# Delete history older than 30 days, but keep audit events for 180 days and A2A correlations forever:
agent-movement purge --db receiver.sqlite --older-than 30d \
    --retain audit_events=180d --retain a2a_correlations=forever
```

The same is `python -m agent_movement.retention ...`, or `agent_movement.retention.purge(path, seconds, retain={...})` from Python. The full flag list is in the [CLI reference](cli.md).

- **Durations** are `<number><unit>` with unit `s`, `m`, `h`, `d` or `w`. `0s` deletes everything purgeable up to now.
- **`--retain TABLE=DURATION|forever`** overrides the period for one purgeable table: `deliveries`, `audit_events`, `a2a_correlations`, `peer_trace`, `authority_log`, `peer_nonces` or `peer_admissions` (which carries `grant_uses` with it). Retained tables cannot be configured: asking for `--retain owners=1d` is a usage error.
- **The file must exist.** `purge` never creates a store. If the file holds core tables it is opened through `SQLiteStore` first, so an older layout is migrated (and salted) before anything is deleted.
- **One transaction.** All deletions and the `retention_purges` row commit together, under the same write lock the receivers use.
- **Physical deletion.** The purge connection sets `PRAGMA secure_delete = ON`, so SQLite overwrites deleted content with zeros, and then runs `PRAGMA wal_checkpoint(TRUNCATE)` ([SRC-SQLITE-PRAGMA]). The report shows the checkpoint result; `busy: true` means another connection held the log open and the old frames are cleared at the next checkpoint. Copies outside the file, such as backups and filesystem snapshots, are not touched.
- **Timestamps.** ISO-8601 columns are compared with SQLite's `julianday()`, so a malformed timestamp is kept, not guessed about. The peer integer columns use the receiver's clock, in epoch seconds.
- **Output.** A JSON report with, for every table in the file, the action (`purged`, `retained` or `unmanaged`), the rows deleted, the cutoff and the reason. Exit codes: 0 done, 1 the store could not be used (for example a newer layout), 2 usage error or no such file.

### Consequences of a purge

- **The retry window ends.** An exact retry whose `deliveries` row was purged is executed again, and a purged movement ID can be used again. The tasks are pure and effects stay fenced by the retained `effects` and `authorized_effects` ledgers, but the retention period of `deliveries` should be longer than any sender's retry horizon.
- **The audit trail is shorter.** Purged audit events, traces, correlations and authority-log entries are gone. `authorized_effects.log_seq` and `grant_revocations.log_seq` can then refer to a purged log entry. Enforcement reads the state tables, not the log.
- **What is kept is still enforced.** Owners and epochs, effect ledgers and revocations are never purged. Admissions and grant uses go only after the grant itself expired before the cutoff, so a single-use grant never becomes usable again. An admission that has not expired is never purged, so no in-flight delivery loses its admission.

## Deleting what purge keeps

Purge keeps safety state on purpose. Delete it only when the task or the whole store is retired.

- **A whole store:** stop every process that uses it, then delete the file and its `-wal` and `-shm` companions. Deleting `store_secret` alone has the same effect on the commitments (they can no longer be checked), but the store then refuses to open.
- **A retired task's fencing and effect rows:** when no executor of the task can run any more, delete them by hand in one transaction, for example `DELETE FROM owners WHERE task_id = ?; DELETE FROM effects WHERE task_id = ?; DELETE FROM authorized_effects WHERE task_id = ?;` (with `PRAGMA secure_delete = ON`). A deleted owner row lets a stale executor claim the task again at epoch 1, and a deleted effect row lets the same effect ID commit again.
- **Revocations:** delete a `grant_revocations` row only after that grant's `expires_at` has passed. The store does not always know the expiry of a grant it never admitted, which is why purge keeps them.

## Other stores

### Relocation files

[Checkpoint relocation](checkpoint-relocation.md) keeps owners/epochs, relocation records and the simulated outside world in a coordinator file, and LangGraph checkpoints, effect intents and the node journal in each worker's state file (one file in single-store mode). These tables have no time column, and they hold exactly the state that fencing, effect reconciliation and resume depend on, so `purge` retains them. The same holds for the operator-reconciliation tables `effect_reconciliations` and `reconciliation_events`: purge never removes a parked effect, resolved or not. The demos run in temporary directories that are deleted on exit. For your own runs, delete a run's coordinator and worker files (with their `-wal`/`-shm` companions) and its bundle directories once the task finished and no worker can resume it. Effect-intent and bundle digests in these files are plain SHA-256 over synthetic payloads, because they are compared *across* stores (origin and receiver); a per-store key cannot be used for them.

### Signed movement receipts

[Signed movement receipts](movement-receipts.md) are files you choose: evidence bundles, the live run's receipt logs (`--receipts`, `--receipts-log`) and the separate trust-anchor file. They contain no task text, only digests of salted commitments, and the commitment documents stay in process memory. The offline verifier's replay guard is in memory only. Keep or delete these files like any other evidence; `purge` does not touch them. Deleting a bundle removes the evidence of a run, not any safety state.

### Benchmarks and logs

MobilityBench runs use temporary directories, and their outputs (`--out`, `--output`) are files you choose. The peer receiver logs each trace event (IDs and reason codes only) through the `agent_movement.peer` logger. Retention of those log records is up to the logging configuration of the host process.

## Limitations

- The store secret is in the store file. Commitments protect exports and logs, not a stolen file.
- There is no automatic, scheduled purge, and no default period. Run `purge` from your own scheduler if you need one.
- Physical deletion covers the SQLite file and its write-ahead log, not backups, snapshots, copies, or blocks the filesystem or SSD keeps after an overwrite.
- `safe_token` in the A2A adapter replaces an unsafe external ID by its plain `sha256:` digest. That is an untrusted identifier, not task content, but it is not keyed.
- The A2A extension metadata and the receipt returned to the sender still carry plain SHA-256 digests on the wire. They protect integrity, not confidentiality.

## References (accessed 2026-10-16)

- [SRC-HMAC] H. Krawczyk, M. Bellare, R. Canetti, *HMAC: Keyed-Hashing for Message Authentication*, RFC 2104, 1997. <https://www.rfc-editor.org/rfc/rfc2104>
- [SRC-SQLITE-PRAGMA] SQLite, *Pragma statements*: `secure_delete` and `wal_checkpoint`. <https://www.sqlite.org/pragma.html>
