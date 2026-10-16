# Same-runtime checkpoint relocation and crash-fault matrix (2026-10-16)

**Status:** tested experimental software, synthetic data only. This adds **same-runtime checkpoint relocation** to the [local proof of concept](local-implementation.md). An unfinished task moves from Worker A to Worker B at a persisted LangGraph checkpoint, and B continues it. By default both workers share one store; in [two-store mode](#two-store-mode-copy-the-checkpoint-into-worker-bs-own-store-issue-20) the checkpoint is copied into B's own store as a digest-verified bundle, and only the coordinator stays shared. It is **not** cross-framework reconstruction, cross-host transfer, live process migration, A2A, or production-secure. An effect whose outcome is unknown after a crash is parked, and an operator can [resolve it](#operator-reconciliation-of-parked-effects-issue-30) as `confirmed_done` or `confirmed_absent`. It makes **no exactly-once claim for arbitrary tools.** It addresses open questions [AM-03, AM-04 and AM-07](open-questions.md) for one runtime only.

## Run it

~~~sh
python -m pip install -e '.[relocation]'          # optional extra; core stays dependency-free
python -m agent_movement.relocation_demo           # headline + 30-row fault matrix, exit 0 if all rows match
python -m agent_movement.relocation_demo --json results.json
python -m agent_movement.relocation_demo --two-store   # own store per worker, bundle copy, 11-row copy fault matrix
python -m agent_movement.relocation_reconcile --help    # operator CLI for parked effects (also: agent-movement relocate reconcile)
python -m pytest -q tests/test_relocation.py tests/test_relocation_two_store.py tests/test_relocation_reconcile.py   # skipped cleanly without the extra
~~~

Both modes end with nine [operator-reconciliation rows](#reconciliation-rows-observed) that resolve the effects parked by C13 and C14.

The default mode shares one SQLite file between coordinator and workers and exports the checkpoint *by reference*. `--two-store` gives each worker its own SQLite file and *copies* the checkpoint into Worker B's store as a digest-verified bundle; see [Two-store mode](#two-store-mode-copy-the-checkpoint-into-worker-bs-own-store-issue-20).

The experiment needs `os.fork` (Linux/macOS). The default mode completes in roughly 20 s, `--two-store` in roughly 15 s, the reconciliation rows included. It makes no model calls, needs no network, and uses no credentials. Each scenario uses fresh SQLite files in a temporary directory, and the directory is deleted afterwards. CI runs both modes in the `extras` job of [`python-smoke.yml`](../.github/workflows/python-smoke.yml) on Python 3.11 and 3.13 and uploads the JSON results as artifacts.

## Pinned runtime (one durable runtime, exact pins)

| Package | Pinned | Why exact |
| --- | --- | --- |
| `langgraph` | 1.2.15 | Graph runtime (Pregel loop, `interrupt_after`, `durability="sync"`) |
| `langgraph-checkpoint` | 4.3.0 | Checkpoint format `v=4`, serializer |
| `langgraph-checkpoint-sqlite` | 3.1.2 | `SqliteSaver`, subclassed by `FencedSqliteSaver` |

These versions were the latest stable releases on PyPI when checked on 2026-10-16 (PyPI JSON API; all three uploaded 2026-10-12). The integration relies on internals that were **read in the installed source**, not assumed:

- `SqliteSaver.put`, `put_writes` and `delete_thread` all write through `SqliteSaver.cursor()`. `list()`'s second cursor only reads pending writes. `FencedSqliteSaver` therefore overrides `cursor()` and adds `BEGIN IMMEDIATE` plus an ownership check.
- With `durability="sync"`, the Pregel loop waits for `_put_checkpoint_fut.result()` before the next superstep. The checkpoint and its writes are therefore durable when `invoke(..., interrupt_after="*")` returns.
- `put`/`put_writes` run on background threads. The checkpoint fault flag is thread-local for that reason; a first draft had a shared flag and attributed a fault to the wrong write.
- `StateSnapshot.next` leaves out tasks whose outputs already exist as durable pending writes. Boundaries are therefore computed from `StateSnapshot.tasks`.
- Checkpoint `v` is 4 (`langgraph/pregel/_checkpoint.py`).

`compatibility()` refuses any receiver whose installed runtime is not exactly these pins.

## Identities and authority

| Concept | Value in the experiment | Changes on relocation? |
| --- | --- | --- |
| **Task identity** (logical task) | `task-report-1` = LangGraph `thread_id` | **No**: one checkpoint lineage for the whole task |
| **Execution identity** | `worker-a.1`, `worker-b.1`, `worker-b.2` (worker + incarnation) | Yes: every relocation or failover creates a new execution |
| **Authority** | `owners(task_id → execution_id, epoch)`, the same table the core `EffectGateway` uses | Epoch +1 on every transfer |

Every checkpoint's metadata records the `execution_id` and `epoch` that wrote it, and each `step_log` entry names the execution that ran it. A crashed execution is never revived under its old epoch. Recovery always transfers to a new incarnation with a new epoch, so a zombie of the old one stays fenced.

## Protocol (all state in one SQLite file)

1. **Origin (A)**: at a superstep boundary A checks it is still the owner, then builds a manifest from the head checkpoint (`build_manifest`) and records an export request with the coordinator. The request is fenced: only the current `(execution, epoch)` may ask. A cooperative export is refused if the checkpoint has pending writes or an effect outcome is uncertain.
2. **Coordinator**: one `BEGIN IMMEDIATE` transaction does the compatibility check, confirms the manifest checkpoint is **still the head**, increments the epoch to B and marks older open movements `superseded`. A's fenced checkpoint writes take the same SQLite write lock. Either A's write lands first, and the transfer is refused as stale, or the transfer lands first, and A's write is denied. No interleaving loses an update.
3. **Receiver (B)**: B checks the grant is addressed to its execution and epoch, re-checks compatibility, reloads the exported checkpoint and verifies its digest against the manifest. It then confirms the checkpoint is still the head.
4. **Acknowledgement**: B records `acknowledged` (fenced and idempotent). A duplicate grant after that never rewinds B.
5. **Resume**: B calls `invoke(None, …)` one superstep at a time and LangGraph continues from the head checkpoint.
6. **Failover** (origin or receiver crashed): the coordinator builds the manifest itself from the durable head. A failover may carry LangGraph pending writes and uncertain effects; the receiver handles both.

The `checkpoint` transition in the matrix is LangGraph's `put_writes` + `put` inside `FencedSqliteSaver`.

## What is exported, and what is not

The checkpoint is exported **by reference** in the shared store and **verified by a SHA-256 digest** of its `id`, `channel_values`, `channel_versions` and `versions_seen`.

| Exported | Content |
| --- | --- |
| `thread_id` | Logical task ID (task identity) |
| `checkpoint_id` / `parent_checkpoint_id` | Head of the root namespace (`checkpoint_ns=""`) and its parent |
| `channel_values` | All declared channels: `items`, `constraints`, `cursor`, `word_total`, `artifacts`, `step_log`, `effect`, `status` (plus LangGraph's internal `branch:to:*` channel) |
| `channel_versions`, `versions_seen` | Scheduling bookkeeping needed to compute the next node |
| `next` | Node(s) B runs first (from `StateSnapshot.tasks`) |
| `metadata` | `step`, `source`, and the writer's `execution_id`/`epoch` |
| `pending_writes` (failover only) | Durable outputs of a superstep whose checkpoint never committed |
| Effect ledger | Intent rows for the task (by reference) |

| Unsupported / not exported | Handling |
| --- | --- |
| In-flight node execution (stack, locals, partial output) | Lost. The node re-runs from the last durable checkpoint (**at-least-once node execution**) |
| Pending writes, interrupts, `Send` packets | Refused for cooperative export. Failover carries durable pending writes only |
| Subgraph namespaces | Refused (root namespace only) |
| Non-JSON channel values | Refused |
| LangGraph `Store` (cross-thread memory) | Not used, not exported |
| Process-local resources (caches, counters, connections, sockets, file handles, thread pools) | Not exported |
| Credentials and grants | Never exported. B receives a **new** epoch |
| External tool state | Never in the checkpoint. Only the simulated gateway can be queried |
| Model / conversation state | None exists (LLM-free graph). Model continuation is **not** evaluated |
| Other runtimes, graph versions, checkpoint formats | Refused, fail closed |
| Cross-host byte transfer | Not implemented (shared local SQLite file) |

## The task and its effects

The graph `synthetic-batch-report` v1 is deterministic and LLM-free: `process_item` ×6 → `effect_intent` → `effect_commit` → `finalize`. Each step is its own superstep and its own checkpoint. There is one gated synthetic effect, `publish-report`, allowed at most once (`constraints.max_gated_effects = 1`).

Effects use a write-ahead ledger with these states: `intent` → `attempt_started` → `committed`, or `reconciled_committed`, or `unknown`. Two simulated tool classes exist, and both are gated by the ownership epoch:

- **`gateway`**: the core `EffectGateway`. It deduplicates by effect ID and its commit record can be queried. After a crash in the commit window, B calls `reconcile()`. If a record exists, B adopts it; if not, B retries with the **same** effect ID. The retry is safe **only because this gateway deduplicates**.
- **`opaque`**: no idempotency key and no lookup. After a crash in the commit window, B cannot know whether the effect happened. The task is parked as `reconcile_required` with effect status `unknown`, and there is **no blind retry**. Only the harness reads the ground truth. An operator who checks the external system out of band can then [resolve the parked effect](#operator-reconciliation-of-parked-effects-issue-30).

This is the AM-04 boundary in executable form. Exactly-once is achievable only where the target system cooperates (dedup or lookup). For anything else, the honest result is `unknown`.

## Headline result (observed)

Six items. A runs three supersteps, then relocates. The results below come from `python -m agent_movement.relocation_demo`, which matched on Python 3.11.16 and 3.13.15.

| Evidence | Observed |
| --- | --- |
| Items processed by execution (from `step_log` in the final state) | `worker-a.1`: [0, 1, 2]; `worker-b.1`: [3, 4, 5] |
| `process_item` executions | A: 3, B: 3; **restart baseline** (B runs the same task from scratch): 6 |
| B's first checkpoint parent | = the exported checkpoint ID (`true`) |
| Checkpoint lineage writers | steps −1…3 `worker-a.1`, steps 4…9 `worker-b.1` |
| Constraints and A's artifacts preserved in B's final state | `true` / `true` |
| Partitioned A runs one more superstep after transfer | Node computes (1 attempt journaled), **checkpoint write `PolicyDenied`** |
| A attempts the gated commit at epoch 1 | **`PolicyDenied`** |
| Gated commits | exactly 1, at epoch 2, by `worker-b.1` |

**Why this is not a restart and not transcript replay.** B never executes items 0–2: its node journal holds only indices 3–5, against 6 for the restart baseline. Its first checkpoint descends from the exported one. A's artifacts reach the final state without being recomputed. No transcript exists; the graph is LLM-free and the continuation reads only checkpoint channels.

**How out-of-process the evidence is.** Every actor action runs in a **fresh forked process** that shares nothing with the next action except the SQLite file. That holds even for two actions of the same execution, so all continuity has to come from durable state. A crash is `os._exit(86)` at the named point: no `finally`, no commit, and no LangGraph error bookkeeping. That is closer to `SIGKILL` than an in-process exception, which LangGraph would catch and record as an error write.

## Fault matrix (observed)

Outcome vocabulary:

- **allowed**: after the fault and the documented recovery, the task completes with all six artifacts, the correct word total, preserved constraints, and exactly one gated commit.
- **reconciled**: allowed, and the uncertain effect was resolved through the gateway's commit record.
- **unknown**: the effect outcome is not knowable by the worker. The task is parked as `reconcile_required` and nothing is retried until an operator decides ([reconciliation rows](#reconciliation-rows-observed)).
- **denied**: the injected message is rejected (`PolicyDenied`, `Conflict`, or `Incompatible`) and owner, head checkpoint, commits and relocation records are **unchanged**.
- **deduplicated**: the message is accepted as a replay and that same state is unchanged.

For D and V rows the task is then run to completion and checked as well.

Columns: *Gated commits* counts gateway commit records (ground truth). *Opaque calls* is the opaque-tool ground truth, which workers cannot read. *Item re-exec* counts `process_item` attempts beyond one per item, including fenced attempts.

| ID | Transition | Injected fault | Expected | Observed | Recovery / handling | Gated commits | Opaque calls | Item re-exec | Final |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C1 | origin | crash before export request | allowed | allowed | failover from durable head | 1 | 0 | 0 | done @ worker-b.1@2 |
| C2 | origin | crash after export request recorded | allowed | allowed | coordinator continues recorded request | 1 | 0 | 0 | done @ worker-b.1@2 |
| C3 | coordinator | crash inside transfer txn (before commit) | allowed | allowed | transaction rolled back; restarted coordinator retries | 1 | 0 | 0 | done @ worker-b.1@2 |
| C4 | coordinator | crash after transfer commit (reply lost) | allowed | allowed | grant re-delivered from durable record (no 2nd epoch bump) | 1 | 0 | 0 | done @ worker-b.1@2 |
| C5 | receiver | crash before reading grant | allowed | allowed | failover worker-b.1 -> worker-b.2 (epoch 3) | 1 | 0 | 0 | done @ worker-b.2@3 |
| C6 | receiver | crash after verifying checkpoint, before ack | allowed | allowed | failover worker-b.1 -> worker-b.2 (epoch 3) | 1 | 0 | 0 | done @ worker-b.2@3 |
| C7 | checkpoint | crash before B's first checkpoint commits | allowed | allowed | failover; LangGraph re-applies durable pending writes | 1 | 0 | 0 | done @ worker-b.2@3 |
| C8 | checkpoint | crash after B's first checkpoint commits | allowed | allowed | failover from B's newer checkpoint | 1 | 0 | 0 | done @ worker-b.2@3 |
| C9 | effect-intent | crash before intent is durable | allowed | allowed | failover; intent re-recorded | 1 | 0 | 0 | done @ worker-b.2@3 |
| C10 | effect-intent | crash after intent is durable | allowed | allowed | failover; intent idempotent | 1 | 0 | 0 | done @ worker-b.2@3 |
| C11 | effect-commit | gateway tool: crash after attempt mark, before call | reconciled | reconciled | reconcile: no commit record -> retry SAME effect ID (gateway dedups) | 1 | 0 | 0 | done @ worker-b.2@3 |
| C12 | effect-commit | gateway tool: crash after commit, before checkpoint | reconciled | reconciled | reconcile: commit record found -> adopt, no new commit | 1 | 0 | 0 | done @ worker-b.2@3 |
| C13 | effect-commit | opaque tool: crash after attempt mark, before call | unknown | unknown | no lookup possible -> parked reconcile_required, no blind retry | 0 | 0 | 0 | reconcile_required @ worker-b.2@3 |
| C14 | effect-commit | opaque tool: crash after call, before checkpoint | unknown | unknown | no lookup possible -> parked reconcile_required, no blind retry | 0 | 1 | 0 | reconcile_required @ worker-b.2@3 |
| C15 | acknowledgement | crash after ack recorded, before first step | allowed | allowed | failover worker-b.1 -> worker-b.2 (epoch 3) | 1 | 0 | 0 | done @ worker-b.2@3 |
| D1 | origin | delayed duplicate of the same export request | deduplicated | deduplicated | duplicate request move-1 -> ok | 1 | 0 | 0 | done @ worker-b.1@2 |
| D2 | origin | fenced A sends a NEW export request | denied | denied | fenced A exports move-9 -> PolicyDenied | 1 | 0 | 0 | done @ worker-b.1@2 |
| D3 | coordinator | duplicate transfer command after ack | deduplicated | deduplicated | duplicate transfer move-1 -> ok | 1 | 0 | 0 | done @ worker-b.1@2 |
| D4 | receiver | duplicate grant after B progressed | deduplicated | deduplicated | duplicate grant move-1 after B progressed -> ok | 1 | 0 | 0 | done @ worker-b.1@2 |
| D5 | receiver | delayed grant to superseded worker-b.1 | denied | denied | delayed grant move-1 to worker-b.1 -> PolicyDenied | 1 | 0 | 0 | done @ worker-b.2@3 |
| D6 | checkpoint | partitioned A keeps stepping after transfer | denied | denied | partitioned A keeps stepping -> PolicyDenied | 1 | 0 | 1 | done @ worker-b.1@2 |
| D7 | effect-intent | delayed intent from fenced A | denied | denied | fenced A records effect intent -> PolicyDenied | 1 | 0 | 0 | done @ worker-b.1@2 |
| D8 | effect-commit | delayed gated commit from fenced A (epoch 1) | denied | denied | fenced A commits gated effect -> PolicyDenied | 1 | 0 | 0 | done @ worker-b.1@2 |
| D9 | effect-commit | duplicate commit by B with same effect ID | deduplicated | deduplicated | duplicate commit by B (same effect ID) -> ok | 1 | 0 | 0 | done @ worker-b.1@2 |
| D10 | acknowledgement | duplicate ack from B | deduplicated | deduplicated | duplicate ack from worker-b.1 -> ok | 1 | 0 | 0 | done @ worker-b.1@2 |
| D11 | acknowledgement | stale ack from fenced A | denied | denied | stale ack from fenced A -> PolicyDenied | 1 | 0 | 0 | done @ worker-b.1@2 |
| V1 | coordinator | receiver graph_version 2 | denied | denied | refused (graph_version); lost=[], unavailable=8 channels; A keeps epoch 1 | 1 | 0 | 0 | done @ worker-a.1@1 |
| V2 | coordinator | receiver langgraph 1.3.0 | denied | denied | refused (runtime); lost=[], unavailable=8 channels; A keeps epoch 1 | 1 | 0 | 0 | done @ worker-a.1@1 |
| V3 | coordinator | receiver lacks state channel step_log | denied | denied | refused (channels); lost=['step_log'], unavailable=1 channels; A keeps epoch 1 | 1 | 0 | 0 | done @ worker-a.1@1 |
| V4 | receiver | checkpoint digest != manifest (corruption) | denied | denied | receiver refuses; failover back to worker-a.2 (epoch 3) completes | 1 | 0 | 0 | done @ worker-a.2@3 |

`rows: 30, matching expectation: 30` (byte-identical table on three consecutive runs on Python 3.13.15 and one on 3.11.16).

Notes on specific rows:

- **C7**: the crash hit after LangGraph's `put_writes` committed and before the checkpoint `put`. The head stayed at A's checkpoint with B's node outputs as durable pending writes. `worker-b.2` re-applied them without re-running the node (0 re-executions). Those writes came from `worker-b.1` while it legitimately owned epoch 2; fencing `put_writes` is what keeps a fenced worker's outputs from entering this path.
- **C11–C14** show the AM-04 boundary. With the queryable gateway, both crash windows end in exactly one commit. With the opaque tool, C13 (ground truth 0 calls) and C14 (ground truth 1 call) look **identical** to the worker, so both are `unknown`.
- **D6**: the "1" in *Item re-exec* is the partitioned A's single wasted, pure computation. Its output never became durable.
- **V1–V3**: refusal happens **before** any epoch change, so A keeps epoch 1 and finishes the task. Fail closed does not lose the task. The report lists `unavailable_state` (all 8 channels for a structural mismatch), `lost_state` (`["step_log"]` for V3) and the always-unsupported list.
- **V4**: the epoch has already moved when B detects corruption, so B refuses to resume. The coordinator then fails over to a new execution (`worker-a.2`, epoch 3), which verifies a fresh manifest and completes.

## Two-store mode: copy the checkpoint into Worker B's own store (issue #20)

`python -m agent_movement.relocation_demo --two-store` repeats the headline with **separate stores** and runs a copy-specific fault matrix. Code: `Worker(..., store=...)`, `Worker.export_bundle`, `Worker.accept(movement, bundle)`, `Coordinator.request_bundle` and `Coordinator.failover(..., source_store=, outbox=)` in [`relocation.py`](../src/agent_movement/relocation.py); the bundle format in [`relocation_bundle.py`](../src/agent_movement/relocation_bundle.py); the scenarios in [`relocation_demo_two_store.py`](../src/agent_movement/relocation_demo_two_store.py).

### What lives where

| File | Holds | Shared? |
| --- | --- | --- |
| `worker-a.sqlite` | A's LangGraph checkpoints and writes, A's effect ledger, A's node journal | No, A only |
| `worker-b.sqlite` | B's copy of the head checkpoint, then B's own checkpoints, ledger, journal and `bundle_imports` records | No, B only |
| `coordinator.sqlite` | `owners` (task → execution, epoch), `relocations`, and the simulated external systems (gateway `effects`, opaque-tool ground truth) | **Yes**: every worker reaches it |

The coordinator file has **no** `checkpoints`, `writes` or `effect_intents` table (checked in the headline). The ownership epoch stays authoritative there. Every fenced write in a worker store (checkpoint `put`/`put_writes`, effect intents, the bundle import) runs on a connection that `ATTACH`es the coordinator file. `BEGIN IMMEDIATE` then holds the write locks of **both** files while the epoch check and the write run, so a fenced write and the coordinator's epoch transfer still serialize. A unit test shows the coordinator file cannot be write-locked while a worker's fenced transaction is open. This is a same-host file lock, not a network fencing token.

### Protocol differences from the single-store mode

1. **Export (A).** A builds the manifest from its own head checkpoint, reads the raw `SqliteSaver` rows (checkpoint, its pending writes, the task's effect-ledger rows) and writes one bundle atomically (write, fsync, rename) to its outbox. Only then does it record the request. `request_bundle` checks, in one transaction over A's store and the attached coordinator file, that the bundled checkpoint is **still A's head**.
2. **Export freeze.** From that moment A is *frozen*: its fenced writes are denied until the coordinator transfers or refuses the movement. The coordinator cannot read A's store, so the single-store "is it still the head?" check at transfer time is replaced by "the head was checked under lock at request time and could not move since". A refused transfer (V1–V3 equivalent) releases the freeze and A continues. Failover requests may still be recorded for a frozen owner.
3. **Transfer.** Compatibility check and epoch bump, as before, without reading any worker store.
4. **Copy.** The harness "transport" copies the bytes from A's outbox into B's inbox. That copy is where B4–B6 inject faults.
5. **Import (B), fail closed, in this order.** (a) size limit 8 MiB, strict UTF-8 JSON without duplicate keys, canonical form; (b) the embedded manifest's SHA-256 must equal the digest the **coordinator recorded** at request time, which is the trust anchor (bundles are not signed); (c) the same `compatibility()` check as before; (d) per-section SHA-256 digests (`checkpoint`, `writes`, `effect_ledger`), **before** anything is deserialized; (e) only the `msgpack`/`null` serializer types are decoded (never `pickle`); the decoded checkpoint must match the manifest's semantic digest and **one SHA-256 per channel value**; (f) the effect records must agree with the manifest's `uncertain_effects`. Any failure raises `Incompatible` with a report: `reason`, `corrupt_sections`, `corrupt_channels`, `unavailable_state` (every channel plus the effect ledger) and the always-unsupported list. Nothing is written.
6. **Atomic, idempotent import.** One fenced transaction inserts the rows and a `bundle_imports` record, or nothing. Rows are copied byte for byte, never re-serialized. An existing identical row is accepted (re-import after a crash). A *different* row with the same key, rows the bundle does not describe, or a receiver store whose head is newer than the bundle are refused, so an import never overwrites, deletes or rewinds. After commit B re-reads its head through `SqliteSaver` and checks the digest again, then acknowledges.
7. **Failover** names the store that holds the durable head (the last acknowledged receiver's, else the origin's). The coordinator, acting as recovery operator, exports a bundle from it to its own outbox. This needs read access to that store; if it is lost, the task cannot be relocated.

The self-describing manifest adds `transport: "bundle"` and a `bundle` section to the single-store manifest: format `am-checkpoint-bundle/0.1.0-draft`, the section digests, a payload digest, `channel_digests`, and the number of pending writes and effect records. It keeps the graph ID and version, the pinned LangGraph versions, the channel list, the checkpoint ID, step, format and semantic digest. Its `exported_state` adds `pending_writes` and the copied `effect_ledger`. Its `unsupported_state` adds `checkpoint_history` (only the head checkpoint is copied; its ancestors stay in A's store), `shared_authority`, and a two-store meaning of `cross_host_byte_transfer` (local directories, no network).

### Headline with two stores (observed)

Same task and checks as the single-store headline; all hold (`headline_ok: True`):

| Evidence | Observed |
| --- | --- |
| Items processed by execution | `worker-a.1`: [0, 1, 2]; `worker-b.1`: [3, 4, 5] |
| `process_item` executions | A: 3, B: 3; restart baseline: 6 |
| B's first checkpoint parent | = the exported checkpoint ID (`true`) |
| Partitioned A runs one more superstep in **its own store** after transfer | checkpoint write **`PolicyDenied`** (fence through the attached coordinator file); A's store head unchanged |
| A attempts the gated commit at epoch 1 | **`PolicyDenied`** |
| Gated commits | exactly 1, at epoch 2 |
| B's store before import / rows imported | 0 checkpoint rows / 1 checkpoint, 0 pending writes, 0 effect records |
| Checkpoints in B's store written by `worker-a.1` | 1 (the copied head only) |
| Coordinator file tables | `audit_events`, `deliveries`, `effect_reconciliations`, `effects`, `opaque_effects`, `owners`, `reconciliation_events`, `relocations` (no checkpoint or ledger tables) |
| Bundle bytes B verified = bundle bytes A wrote (SHA-256) | `true` |

### Copy fault matrix (observed)

Same vocabulary and columns as the single-store matrix. *Final* is read from the current owner's store. For **denied** rows "unchanged" additionally covers every worker store (checkpoint count, head, effect records and import records).

| ID | Transition | Injected fault | Expected | Observed | Recovery / handling | Gated commits | Opaque calls | Item re-exec | Final |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B1 | export | crash after bundle written, before request | allowed | allowed | failover: coordinator re-exports from A's store; B imports | 1 | 0 | 0 | done @ worker-b.1@2 |
| B2 | export | crash after request recorded | allowed | allowed | coordinator continues recorded request; B imports A's bundle | 1 | 0 | 0 | done @ worker-b.1@2 |
| B3 | export | A checkpoints after its export request | denied | denied | A steps after its export request -> PolicyDenied | 1 | 0 | 1 | done @ worker-b.1@2 |
| B4 | copy | truncated bundle (half the bytes) | denied | denied | refused (bundle_unreadable); corrupt=[]; unavailable=9 items; re-copy -> completes | 1 | 0 | 0 | done @ worker-b.1@2 |
| B5 | copy | one byte changed in a channel (digest mismatch) | denied | denied | refused (digest_mismatch); corrupt=['checkpoint']; unavailable=9 items; re-copy -> completes | 1 | 0 | 0 | done @ worker-b.1@2 |
| B6 | copy | valid but ungranted (stale) bundle substituted | denied | denied | refused (manifest_not_granted); corrupt=[]; unavailable=9 items; re-copy -> completes | 1 | 0 | 0 | done @ worker-b.1@2 |
| B7 | import | crash inside import txn (partial import) | allowed | allowed | import rolled back (B store: 0 checkpoint rows); failover worker-b.2 (epoch 3) re-imports | 1 | 0 | 0 | done @ worker-b.2@3 |
| B8 | import | crash after import commit, before ack | allowed | allowed | import durable, not acked (B store: 1 checkpoint row); worker-b.2 re-import is idempotent | 1 | 0 | 0 | done @ worker-b.2@3 |
| B9 | import | duplicate import after B progressed | deduplicated | deduplicated | duplicate import of move-1 after B progressed -> ok | 1 | 0 | 0 | done @ worker-b.1@2 |
| B10 | import | delayed import by superseded worker-b.1 | denied | denied | delayed import of move-1 by worker-b.1 -> PolicyDenied | 1 | 0 | 0 | done @ worker-b.2@3 |
| B11 | checkpoint | partitioned A keeps stepping in its own store | denied | denied | partitioned A steps in its own store -> PolicyDenied | 1 | 0 | 1 | done @ worker-b.1@2 |

`rows: 11, matching expectation: 11`. The complete stdout, matrix included, was byte-identical on three consecutive runs (CPython 3.14.7). The single-store 30-row table above is unchanged by this mode, byte for byte.

Notes on specific rows:

- **B3** is the reason for the export freeze. Without it, an origin step between request and transfer would land only in A's store, and B would resume from an older checkpoint. A gated or opaque effect taken in that window could then run twice.
- **B4–B6** are refused **after** the epoch moved to `worker-b.1`, so B owns the task but holds no state for it (fail closed). Recovery re-copies the same, digest-addressed bundle from A's outbox. "unavailable=9 items" is the 8 state channels plus the effect ledger. **B5** changes one byte inside the `items` channel of the serialized checkpoint and keeps the length. The `checkpoint` section digest catches it **before** deserialization, so `corrupt_channels` stays empty by design: unverified bytes are never decoded. The per-channel digests are a second check after decoding. **B6** is a fully self-consistent bundle for the same movement, taken one superstep earlier and never recorded. Only the coordinator-recorded manifest digest tells it apart.
- **B7/B8** are the partial-import crashes. Before commit the import leaves 0 rows. After commit, the replacement execution's import finds the identical rows and accepts them without duplicating anything. As in the single-store matrix, a crashed execution is never revived. Recovery fails over to `worker-b.2` (epoch 3) from A's store, because no receiver acknowledged.
- **B9**: after the acknowledgement, a re-import is answered as a replay without reading the bundle, so B is never rewound. A store-level import record also makes a re-import before the acknowledgement idempotent (unit test).
- **B10/B11**: the import itself and A's writes to its *own* store are fenced through the coordinator epoch.

## Operator reconciliation of parked effects (issue #30)

Rows C13 and C14 end with the task parked as `reconcile_required`. The opaque tool cannot be queried, so no worker can learn whether its call happened. This section adds the step that resolves a parked effect: an operator checks the external system out of band and records what they found. Code: `Coordinator.parked_effects`, `Coordinator.reconcile`, `Coordinator.reconciliation_events`, `EffectLedger.apply_decision` and `Worker.resume_reconciled` in [`relocation.py`](../src/agent_movement/relocation.py); the operator CLI in [`relocation_reconcile.py`](../src/agent_movement/relocation_reconcile.py); the rows in [`relocation_demo_reconcile.py`](../src/agent_movement/relocation_demo_reconcile.py). The existing relocation API is unchanged; everything here is additive.

### Protocol

1. **Park.** When `effect_commit` marks an opaque effect `unknown`, the same fenced transaction registers it in the coordinator file (`effect_reconciliations`, status `parked`) and appends a `parked` event. In two-store mode the ledger row is in the worker's own store and the record is in the attached coordinator file; one `BEGIN IMMEDIATE` commits both or neither.
2. **Decide.** The operator records `confirmed_done` or `confirmed_absent` with a reason (1–512 bytes of printable text), an operator identity (same ID syntax as agent IDs) and the ownership epoch they inspected. One coordinator transaction then checks, in this order:
   1. **Epoch fence.** The task's current epoch must equal the decision's epoch, otherwise `PolicyDenied`. The fence runs first, so even an identical replay is denied once the epoch has moved on.
   2. **Parked.** The effect must have been parked, otherwise `Conflict`.
   3. **Double resolution.** The first decision is final. A replay of the identical decision (same decision, operator and reason) is answered as a replay and changes nothing. Any other second decision, including the opposite one from another operator, is `Conflict`.
   4. **Retry budget.** `confirmed_absent` for an effect that is itself the retry is `PolicyDenied`.
3. **Audit.** Every outcome appends one row to `reconciliation_events` in the coordinator file: `parked`, `confirmed_done` or `confirmed_absent`, `replayed`, `denied` (with the error) and `applied`. Each row records the actor (operator or execution), the epoch, the detail and a UTC timestamp. The decision record keeps the canonical decision and its SHA-256 digest.
4. **Resume.** The current owner calls `Worker.resume_reconciled()`. It needs a recorded decision and the current epoch. It writes one fenced checkpoint that re-enters the graph at `effect_commit` (LangGraph `update_state(..., as_node="effect_intent")`, with an `operator_reconcile` entry in `step_log`) and runs on. `effect_commit` applies the decision to the worker's ledger in one fenced transaction and records `applied`:
   - **`confirmed_done`**: the ledger entry becomes `confirmed_done` and the task continues to `finalize` **without re-executing the effect**.
   - **`confirmed_absent`**: the ledger entry becomes `confirmed_absent`, and **one** retry intent is recorded under the new effect ID `<effect_id>.retry-1` with the same payload digest. The retry takes the normal intent → attempt → commit path. If the retry also crashes in its commit window, it is parked like any opaque effect (with `retry_of` set). It can then only be confirmed done: a second `confirmed_absent` is denied, so an effect is retried at most once.

The operator writes only to the coordinator file and each worker updates only its own ledger, so the same protocol runs unchanged in single-store and two-store mode. The graph topology and `graph_version` are unchanged; the decision is applied inside the existing `effect_commit` node.

### Trust assumption: a human in the loop

This is **not** an exactly-once mechanism. The coordinator enforces *who* may decide and *when* (the epoch fence), that the first decision is final, and that every attempt is recorded. It cannot check *whether the claim is true*: the outcome of the effect is exactly what the system cannot observe. A false `confirmed_done` loses the effect (row C13d: zero calls) and a false `confirmed_absent` duplicates it (row C14a: two calls). The guarantee is therefore conditional: if the operator's out-of-band check is correct, the parked effect ends with exactly one call (C13a, C14d), or stays parked.

Further limits of this trust model: operator identities are unauthenticated strings, like execution IDs; decisions are not signed; there is no two-person rule; and the event log is append-only by convention of this module, not tamper-evident, since any client with write access to the SQLite file can rewrite it. In the experiment the operator's out-of-band check is simulated by the harness reading the opaque tool's ground truth, which workers never read.

### Operator CLI

~~~sh
# a synthetic parked task (row C14: the opaque call happened, then the receiver crashed)
python -m agent_movement.relocation_reconcile example --dir /tmp/rec [--crash before] [--two-store]
python -m agent_movement.relocation_reconcile list   --authority /tmp/rec/example.sqlite
python -m agent_movement.relocation_reconcile decide --authority /tmp/rec/example.sqlite --task task-report-1 \
    --effect publish-report --decision confirmed_done --operator ops-alice \
    --reason "checked the external system" --epoch 3
python -m agent_movement.relocation_reconcile resume --authority /tmp/rec/example.sqlite --task task-report-1 \
    --worker worker-b --incarnation 2 --epoch 3      # two-store: add --store <worker-b.sqlite>
python -m agent_movement.relocation_reconcile log    --authority /tmp/rec/example.sqlite
~~~

`example` prints the exact follow-up commands with the right paths. With `--two-store` the coordinator file is `<dir>/example/coordinator.sqlite`. The same commands run as `agent-movement relocate reconcile ...` and `python -m agent_movement.relocation_demo reconcile ...`; every subcommand and flag is in the [CLI reference](cli.md). Output is JSON. Exit codes: `0` done or an idempotent replay; `1` denied (stale epoch, already resolved differently, not parked, retry budget exhausted, not the owner); `2` usage error, invalid input or missing optional extra.

### Reconciliation rows (observed)

These rows extend C13 and C14. Each replays the crash (B crashes in the commit window, failover to `worker-b.2` at epoch 3, which parks the task), then lets the operator decide and resumes. Two outcomes are added to the vocabulary:

- **resolved**: the operator's decision matches the ground truth; the task completes with all six artifacts and **exactly one** opaque call. The decision is recorded, applied by the owner, and the original effect's ledger entry is `confirmed_done` or `confirmed_absent`.
- **misresolved**: the decision contradicts the ground truth. The protocol accepts it, because it cannot tell, and the task completes with **zero** calls (false `confirmed_done`) or **two** (false `confirmed_absent`). These rows are expected outcomes: they demonstrate the trust assumption.

**denied** and **deduplicated** keep their meaning; "unchanged" now also covers the decision records. The R rows are then run to completion and checked as well.

| ID | Extends | Injected fault / operator decision | Expected | Observed | Recovery / handling | Opaque calls by effect ID | Original effect ledger | Final |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C13a | C13 | operator: confirmed_absent (true) | resolved | resolved | retry once as publish-report.retry-1 | publish-report.retry-1: 1 | confirmed_absent | done @ worker-b.2@3 |
| C13d | C13 | operator: confirmed_done (FALSE) | misresolved | misresolved | continue without re-execution -> effect LOST | none | confirmed_done | done @ worker-b.2@3 |
| C14d | C14 | operator: confirmed_done (true) | resolved | resolved | continue without re-execution | publish-report: 1 | confirmed_done | done @ worker-b.2@3 |
| C14a | C14 | operator: confirmed_absent (FALSE) | misresolved | misresolved | retry once as publish-report.retry-1 -> effect DUPLICATED | publish-report: 1, publish-report.retry-1: 1 | confirmed_absent | done @ worker-b.2@3 |
| R1 | C14 | stale-epoch decision (epoch 2 after failover to 3) | denied | denied | decision made at epoch 2 arrives at epoch 3 -> PolicyDenied | publish-report: 1 | confirmed_done | done @ worker-b.2@3 |
| R2 | C14 | double resolution: identical decision replayed | deduplicated | deduplicated | identical decision re-sent after resume -> ok | publish-report: 1 | confirmed_done | done @ worker-b.2@3 |
| R3 | C14 | double resolution: second operator, opposite decision | denied | denied | ops-bob records confirmed_absent -> Conflict | publish-report: 1 | confirmed_done | done @ worker-b.2@3 |
| R4 | - | decision for an effect that was never parked | denied | denied | confirmed_absent for a settled effect -> Conflict | publish-report: 1 | committed | done @ worker-b.1@2 |
| R5 | C13 | confirmed_absent for the retry (retry crashed too) | denied | denied | confirmed_absent for publish-report.retry-1 -> PolicyDenied | publish-report.retry-1: 1 | confirmed_absent | done @ worker-b.3@4 |

`reconciliation rows: 9, matching expectation: 9`. The table is identical in single-store and `--two-store` mode, and the 30-row and 11-row tables above are unchanged by it. In two-store mode the coordinator file gains the `effect_reconciliations` and `reconciliation_events` tables (see the two-store headline); worker stores gain none.

Notes on specific rows:

- **C13a vs C13d** and **C14d vs C14a** are the same crash with opposite decisions. The worker-side state is identical in each pair before the decision; only the operator's claim differs, and with it the number of effects.
- **R1**: the operator inspected the task while `worker-b.1` owned it (epoch 2); the decision arrives after the failover to epoch 3 and is denied. The `denied` event is still logged. The operator then decides at epoch 3 and the task completes.
- **R2/R3** are the two kinds of double resolution. An identical replay after the resume changes nothing; an opposite decision by a second operator, before the resume, is denied and the first decision stands.
- **R4**: an effect that committed normally was never parked, so no decision can touch it.
- **R5**: after `confirmed_absent`, the retry `publish-report.retry-1` makes its call and then crashes before its checkpoint. A failover to `worker-b.3` (epoch 4) parks the retry with `retry_of = publish-report`. A second `confirmed_absent` is denied (retry budget), and the true `confirmed_done` for the retry completes the task with exactly one call.

### Limits of reconciliation

- **Trust**: the decision is only as correct as the operator's out-of-band check (see above).
- **The resuming execution must own the task.** A parked task has no scheduled node, so `failover` refuses it ("finished task"). If the owning execution's process is gone, the same execution identity can resume (as in the experiment, where every action is a fresh process), or ownership can be moved with the core `EffectGateway.transfer` in single-store mode. Relocating a parked task between stores is not implemented.
- **One execution, one process.** As elsewhere in the experiment, two concurrent processes with the same execution identity are outside the model; two concurrent resumes of one execution could both make the retry call.
- **Opaque tool only.** Gateway effects never park; they reconcile through the commit record (C11, C12).
- **No abandon or cancel decision.** A retry that is truly absent again stays parked; no further retry is allowed.
- **Schema.** Coordinator files created before this change lack the two tables; `init_store`/`init_authority` create them.

## Limits and threats to validity

- **What is still shared in two-store mode: the coordinator.** Owners/epochs, relocation records, the export freeze and the simulated external systems live in one coordinator SQLite file that every worker attaches. Fencing a worker's own store relies on SQLite's file locks on that shared file, so it holds only on one host (or on a filesystem with correct POSIX locking). A cross-host deployment would need a fencing token checked by each store, or a consensus service; neither is implemented. Failover needs read access to the store holding the durable head. Bundles are unsigned: integrity comes from the coordinator-recorded manifest digest, not from a signature, and nothing is encrypted. Only the head checkpoint is copied, so lineage history before it stays in the origin store. Importing into a store that holds divergent rows for the task is refused and needs an operator to clear it. An export freeze is released only by a transfer, a refusal or a superseding failover; there is no cancel API.
- **One host, one SQLite file, one coordinator.** There is no consensus, no coordinator high availability and no real network partition: "partition" means a worker that does not check ownership. Fencing holds because every write path re-checks the epoch inside the store. Any client with direct write access to the SQLite file could bypass it.
- **Crash model.** Process death via `os._exit` is tested. Power loss, disk corruption, torn writes and fsync behaviour are not.
- **Cooperative actors.** Agent and execution IDs are unauthenticated strings, as in the core profile. There is no signed manifest, no signed receipt and no attestation.
- **Node execution is at-least-once.** Nodes must be pure, or route every side effect through the ledger and gateway. The experiment journals node attempts; that journal is harness instrumentation, not protocol.
- **Pinned internals.** `FencedSqliteSaver` depends on `SqliteSaver.cursor()` being the single write path. Any version change needs re-review, and the code fails closed on unpinned runtimes.
- **Scope of AM-07.** Same-runtime and same-graph-version only. Cross-framework or cross-version translation is refused, not attempted.
- **No model in the loop.** Continuation quality, the subject of AM-08, is not measured.

## Mapping to issue #9 acceptance criteria

| Criterion | Evidence |
| --- | --- |
| Worker A is fenced after transfer and cannot commit gated synthetic effects | Headline (`PolicyDenied` for step and commit), D2, D6, D7, D8, D11 |
| Worker B continues from a persisted checkpoint, not a restart or transcript replay | Headline: 3 vs 6 executions, lineage parent, `step_log` per execution |
| Crash, restart, duplicate and partition outcomes documented as allowed, unknown or denied | Matrix C1–C15, D1–D11 (crash and duplicate for all 7 transitions) |
| Version mismatch fails closed and reports lost or unavailable state | V1–V4 and the `compatibility()` report |
| Synthetic-only, reproducible one-command experiment plus a CI subset | `python -m agent_movement.relocation_demo`, the `extras` job in `python-smoke.yml` |

## Mapping to issue #20 acceptance criteria

| Criterion | Evidence |
| --- | --- |
| The demo has a `--two-store` mode and the headline checks (no restart, A fenced, one commit) hold | [Headline with two stores](#headline-with-two-stores-observed): 3 vs 6 executions, lineage parent, A's step and commit `PolicyDenied`, one commit at epoch 2; `headline_ok: True` |
| Self-describing bundle, digest-verified, fail-closed import reporting lost or unavailable state | Manifest `bundle` section; import order (a)–(f) above; B4–B6 reports |
| Ownership epoch stays in the coordinator; A cannot commit after transfer | [What lives where](#what-lives-where); headline; B3, B10, B11 |
| New copy fault rows (truncated bundle, digest mismatch, partial import crash, duplicate import) with observed outcomes; matrix byte-identical across runs | B4, B5, B7/B8, B9 (plus B1–B3, B6, B10, B11); three identical runs |
| The limits state what is still shared | First bullet of [Limits](#limits-and-threats-to-validity) |

## Mapping to issue #30 acceptance criteria

| Criterion | Evidence |
| --- | --- |
| Operator API and CLI mark a parked effect `confirmed_done` or `confirmed_absent` with a reason and an operator identity; the decision is an auditable event fenced by the current ownership epoch | `Coordinator.reconcile` and the [operator CLI](#operator-cli); [protocol](#protocol) steps 2–3; `reconciliation_events` |
| After `confirmed_absent` the effect may be retried once with a new effect ID; after `confirmed_done` the task continues without re-execution | C13a (one call, under `publish-report.retry-1`), C14d (one call, no re-execution), R5 (no second retry) |
| Rows C13/C14 extended with both resolutions | C13a, C13d, C14d, C14a, in both store modes |
| Tests cover both resolutions, a stale-epoch decision (denied) and a double resolution (idempotent or denied) | `tests/test_relocation_reconcile.py` (registry rows REG-041 to REG-044); rows R1 (stale), R2 (identical replay), R3 (opposite decision) |
| No exactly-once claim; the human-in-the-loop trust assumption is explained | [Trust assumption](#trust-assumption-a-human-in-the-loop); misresolved rows C13d and C14a |

## References

- LangGraph persistence and checkpointers: <https://docs.langchain.com/oss/python/langgraph/persistence>
- SQLite transactions (`BEGIN IMMEDIATE`): <https://www.sqlite.org/lang_transaction.html>
- M. Kleppmann, "How to do distributed locking" (2016), on fencing tokens: <https://martin.kleppmann.com/2016/02/08/how-to-do-distributed-locking.html>
- P. Helland, "Life beyond Distributed Transactions: an Apostate's Opinion", CIDR 2007, on idempotence and uncertainty across boundaries.
