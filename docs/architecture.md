# As-built architecture of the `agent_movement` package

**Status:** Describes the code as it is, not as it is planned. The package is a research-stage set of **synthetic, local prototypes**, not production software.
**Last verified against commit `fbecb57`** (2026-10-16). Every module, class, function, command, table and column named here was checked against that commit with `grep` or by importing it, and every demo was run (see the [development guide](development.md#the-agent_movement-package) for the commands and their exit codes). If the code has changed since then, the code is authoritative.

> **Snapshot notice.** `src/` keeps changing under the follow-up issues #18–#42. This document describes `fbecb57` only. It was first written against `b21da27` and refreshed after the work on issues #18–#22, #29–#32, #41 and #43 landed. Check `git log -- src/agent_movement` for later changes before relying on a detail.

For the reasons behind each slice, see the topic documents: [local implementation](local-implementation.md), [A2A adapter](a2a-adapter.md) and its [profile extension spec](a2a-profile-extension.md), [peer authentication](peer-authentication.md), [checkpoint relocation](checkpoint-relocation.md), [movement receipts](movement-receipts.md) and [MobilityBench v0.1](mobilitybench-v0.1.md). Every command is listed in the [CLI reference](cli.md). For setup, tests and CI, see the [development guide](development.md#the-agent_movement-package).

## 1. What is real and what is simulated

| Aspect | Real | Synthetic or simulated |
|---|---|---|
| Processes | The demos start separate OS processes (`subprocess.Popen`; `os.fork` for every actor action in both relocation demos). | Every "agent" is a small Python function. No model is called and there are no LLM credentials. |
| Network | Real HTTP over TCP, bound to `127.0.0.1` only (`http.make_server`, `peer_http.make_peer_server`, uvicorn in `a2a_server.main`). | No TLS, no channel binding and no cross-host transfer. Peer card endpoints must be `http://127.0.0.1:<port>` or `local://<name>` (`trust._ENDPOINT`). The relocation bundle is copied between local directories. |
| A2A | The official `a2a-sdk` (pinned `1.2.2`) frames the messages on both ends: Agent Card, JSON-RPC, HTTP+JSON and SSE. | Both ends use the same SDK. The card declares no security scheme. |
| Cryptography | Real HMAC-SHA256 (`trust.HmacKey`), Ed25519 (`trust.Ed25519Key`, `receipts.Ed25519Signer`), and RFC 9180 HPKE with X25519 and ChaCha20-Poly1305 (`trust.HpkeKey`), the last two through the `cryptography` package. SHA-256 digests. | Keys are throw-away test keys generated for each run. The receipt fixture seeds are public (`receipt_fixtures.synthetic_seed`). There is no PKI, X.509 or OAuth. |
| Persistence | Real SQLite transactions (`BEGIN IMMEDIATE`, WAL mode, `ATTACH` in two-store relocation), a versioned core store layout with an in-place migration (`PRAGMA user_version`), and real LangGraph `SqliteSaver` checkpoints. | The demos and benchmarks keep their SQLite files in temporary directories that are deleted at exit (see [§5](#5-storage-schema)). |
| Tasks | Two real pure computations: `word_count` and `sha256` (`core.SQLiteStore.receive`). | The input text is synthetic. Only the classifications `synthetic` and `public` are accepted. |
| External effects | None. | "Effects" are rows in SQLite tables: `effects`, `authorized_effects` and `opaque_effects`. No third-party tool is ever called. In operator reconciliation the operator's out-of-band check is simulated by the harness reading `opaque_effects`. |
| Faults | Hard crashes are real process exits (`os._exit(CRASH_EXIT)`, `CRASH_EXIT = 86`, in `relocation.Faults.hit`). | The fault schedules are scripted. In MobilityBench the faults (`mobilitybench_v01.FAULT_KINDS`) are simulated by a deterministic interpreter inside one process; no model is called (`MODEL = "none"`). |
| Identity | Peer identity is proof of possession of a key pinned in a `TrustStore`. Receipt principals are bound to keys by a trust-anchor file passed with `--trust`. | In `core`, the A2A adapter and MobilityBench, `agent_id` strings are **unauthenticated claims**. |

## 2. Module map

All modules are in `src/agent_movement/`. The core is standard-library only. Each optional extra (see [`pyproject.toml`](../pyproject.toml)) enables one group of modules. Without its extra, a module either fails closed with a hint or reports results as unchecked.

Every experiment is reachable through the `agent-movement` console script (`[project.scripts]` in `pyproject.toml`, implemented in `cli.py`) or `python -m agent_movement`. Each subcommand forwards its arguments unchanged to the `main()` of one module, so `python -m agent_movement.<module>` keeps working with the same flags and exit codes. The [CLI reference](cli.md) is generated from the live `--help` output by `tools/cli_reference.py` (`make cli-docs`).

| Module | Group / extra | Entry point | Main contents |
|---|---|---|---|
| `__init__.py` | core | none | Re-exports `Approval`, `Conflict`, `ContractError`, `EffectGateway`, `HandoffReceiver`, `PolicyDenied` and `SQLiteStore`. |
| `cli.py`, `__main__.py` | core | `agent-movement <command>`, `python -m agent_movement` | Subcommands `demo`, `a2a-demo`, `peer-demo`, `relocate`, `bench` (with the added `smoke`), `receipts` and the built-in `version`. A missing extra (`EXTRAS`, `required_extras`) gives an install hint and exit 2 (`MISSING_EXTRA_EXIT`). |
| `core.py` | core | none | `SCHEMA_VERSION = "0.1.0-draft"` (envelope) and `STORE_SCHEMA_VERSION = 1` (store layout, `StoreSchemaError`). `parse_json` (strict: rejects duplicate keys and NaN, 16 KiB limit), `canonical`, `digest`, `validate_envelope`. `Approval`, `SQLiteStore`, `HandoffReceiver`, `EffectGateway`. Exceptions: `ContractError`, `PolicyDenied`, `Conflict`. |
| `http.py` | core (`--receipts-log` needs `signing`) | `python -m agent_movement.http --db PATH [--port 0] [--receipts-log FILE]` | `LocalServer` (a `ThreadingHTTPServer`) and `make_server`. Routes: `GET /health` and `POST /v0/handoffs`. Errors map to 400, 403, 409, 413, 415 and 500. |
| `demo.py` | core (`--receipts` needs `signing`) | `agent-movement demo [--receipts OUTDIR]` | Starts `agent_movement.http` as a child process, then sends a handoff, an exact replay and an unapproved request. Finally runs an in-process `EffectGateway` stale-epoch check. With `--receipts` it also signs live receipts and verifies the exported bundle ([§3.7](#37-receipt-verification-offline)). |
| `jcs.py` | core | none | `canonicalize` and `jcs_digest`: a documented subset of RFC 8785 that rejects floats. |
| `trust.py` | core (`ed25519` for asymmetric keys, `hpke` for sealed delivery) | none | `HmacKey`, `Ed25519Key`, `generate_key`, `import_key`, `seal`/`unseal` (signatures domain-separated by purpose), `TrustStore`, `issue_card`/`verify_card` (optional `enc_key`), grants (`issue_grant` with a signed `max_uses`, `verify_grant`, `check_grant_live`, `check_grant_scope`), revocations, `commitment`. HPKE: `HPKE_SUITE`, `hpke_available`, `HpkeKey`, `import_enc_key`, `delivery_info`, `seal_response`/`open_response`. |
| `peer.py` | core | none | `PeerLedger` (with `consume_use` for counted grants), `AuthorizedEffectGateway`, `PeerReceiver` (`handle`), `PeerClient` (`discover`, `handoff`, `delivery_seal`), `DeliverySeal`, and the transports `InProcessTransport`, `HttpTransport` and `RecordingTransport`. |
| `peer_http.py` | core | `python -m agent_movement.peer_http --config FILE` | `make_peer_server` and `load_receiver` (optional `enc_key` in the provisioning file). Binds exactly the loopback port named in the receiver's card. |
| `peer_demo.py` | core (`--alg Ed25519` needs `ed25519`, `--delivery hpke` needs `hpke`) | `agent-movement peer-demo [--alg HS256\|Ed25519] [--delivery auto\|plaintext\|hpke]` | One honest handoff and nine attack scenarios against a receiver child process. Checks that no task text is sent before a denial and, with HPKE, that the task canary never appears on the wire. `auto` means HPKE with Ed25519 and plaintext with HS256. |
| `a2a_profile.py` | core (does not import the SDK) | none | `EXTENSION_URI` (the spec's URL), `LEGACY_EXTENSION_URI` (the 0.1 URN), `PROFILE_VERSION`, media types, `envelope_to_a2a`, `a2a_to_envelope`, contextId policy (`CLIENT_CONTEXT_REJECTED`, `CLIENT_CONTEXT_BOUND`, `context_policy`, `check_context_id`), `receipt_to_artifact`, `verify_receipt`, `A2ACorrelationLog`. |
| `a2a_server.py` | `a2a` | `python -m agent_movement.a2a_server --db PATH [--accept-client-context-id]` | `build_agent_card`, `decode_handoff`/`decode_message`, `HandoffRequestHandler` (admits a request before any task exists), `HandoffExecutor` (wraps `core.HandoffReceiver`) and `build_app` (Starlette). |
| `a2a_client.py` | `a2a` | `python -m agent_movement.a2a_client --url URL --envelope FILE [--client-context-id] [--legacy-extension-uri]` | `check_card`, `build_message` and `delegate` (async) over the SDK `ClientFactory`. Exits 3 unless the final task state is `TASK_STATE_COMPLETED`. |
| `a2a_demo.py` | `a2a` | `agent-movement a2a-demo` | Server process plus seven client processes: completed, retry, denied, unknown capability, unknown schema, legacy URN alias with a bound contextId, and a refused client contextId. Joins the results with the receiver tables. |
| `relocation.py` | `relocation` (LangGraph, exact pins) | none | `PINNED_RUNTIME`, `CRASH_POINTS`, `init_store` (single store), `init_authority` and `init_worker_store` (two stores), `FencedSqliteSaver`, `EffectLedger`, `OpaqueTool`, `build_graph`, `build_manifest`, `build_bundle`, `export_bundle`, `compatibility`, `Coordinator` (`request`, `request_bundle`, `transfer`, `acknowledge`, `failover`), `Worker` (`export`, `export_bundle`, `accept`), `observe`. |
| `relocation_bundle.py` | `relocation` (module itself is stdlib) | none | Bundle format `BUNDLE_FORMAT`: `read_payload`, `describe`, `encode`, `write_atomic`, `copy`, `parse`, `corrupt_sections`, `decode_checkpoint`, `insert_payload`, `BundleRejected`. Knows nothing about owners or epochs. |
| `relocation_demo.py` | `relocation` (POSIX `os.fork`) | `agent-movement relocate [--two-store] [--json FILE]`, `agent-movement relocate reconcile ...` | A headline relocation plus a 30-row crash, duplicate and version fault matrix (`run_matrix`), followed by the operator-reconciliation rows; each actor action runs in a forked child (`run_actor`). `--two-store` hands over to `relocation_demo_two_store`; `reconcile` hands over to `relocation_reconcile`. |
| `relocation_demo_two_store.py` | `relocation` | `agent-movement relocate --two-store` (or `python -m agent_movement.relocation_demo_two_store`) | `TwoStoreRun`, a two-store headline and an 11-row copy fault matrix (`MATRIX`, rows B1–B11: crashes around export and import, a checkpoint after the export request, truncated, altered or ungranted bundles, duplicate and superseded imports, and a partitioned origin that keeps stepping in its own store). |
| `relocation_reconcile.py` | `relocation` | `agent-movement relocate reconcile {list,decide,resume,log,example}` or `python -m agent_movement.relocation_reconcile` | Operator CLI for parked effects ([§3.6](#36-operator-reconciliation-of-parked-effects)). Exits 0 (done or identical replay), 1 (denied) or 2 (usage error or missing extra). |
| `relocation_demo_reconcile.py` | `relocation` | printed by `agent-movement relocate` after the fault matrix | Nine operator rows: C13a, C13d, C14d and C14a resolve the effects that rows C13/C14 park with a true or a FALSE decision, and R1–R5 cover stale-epoch, replayed, conflicting and unparked decisions; `MATRIX`, `run_matrix`. |
| `live_receipts.py` | `signing` | through `agent-movement demo --receipts OUTDIR` or `http --receipts-log FILE` | Opt-in signed receipts on the live HTTP path: `ReceiptEmitter`, `RecordingEffectGateway`, `trust_document`, `export_run` (bundle `live-run/` plus a separate `trust-anchors.json`). Ephemeral synthetic keys; emission never changes a handoff's outcome. |
| `receipts.py` | `signing` for signature checks | `agent-movement receipts {verify,timeline,make-fixtures}` | Receipt schema `agent-movement.receipt/0.1-draft`. `validate_body`, `Ed25519Signer`, `commitment`, `body_from_handoff`, `load_trust`, `load_trust_anchors`, `resolve_trust`, revocation notices (`verify_notice`, `apply_notices`), `ReplayGuard`, `verify_bundle` and `render_text`. Exit codes in [§3.7](#37-receipt-verification-offline). |
| `receipt_fixtures.py` | `signing` | through `receipts make-fixtures DIR` | Nine deterministic scenarios (`SCENARIOS`) and their `EXPECTED` results, built on real runs of `HandoffReceiver` and `EffectGateway` (`pr6_handoff`, `gateway_epochs`). Privacy canaries are derived from a public seed (`privacy_canaries`, `canary_marker`). |
| `mobilitybench.py` | core | `agent-movement bench smoke [--output FILE] [--no-timing]` | The local smoke suite `mobilitybench-local-smoke-v0.2`: case declarations from a packaged fixture (`load_cases`, `validate_case`, `CaseFixtureError`), one evaluator per case (`case_*`, collected into `EVALUATORS`), `verdict_for`, `run_suite`, `outcome_digest`, `summarize`. Exits 1 if a case fails and 2 if the case fixture is invalid. The subcommands `run`, `report`, `verify` and `schedule` go to `mobilitybench_v01`. |
| `mobilitybench_v01.py` | core (two modes need `a2a` or `relocation`) | `agent-movement bench {run,report,verify,schedule}` | A frozen-fixture loader with a SHA-256 manifest check (`verify_fixtures`), a scripted interpreter (`AgentState`, `Attempt`), baselines (`MODE_SPECS`, `mode_table`, `MODES`, `RUNNERS`, `EXTRAS`, `extra_available`), security-case handlers (`SECURITY`), `fault_schedule`, `run_suite`, `summarize` and `build_report`. `run` exits 1 on a harness error, a failed security case or a reproducibility mismatch, and 2 if the fixtures fail verification. |
| `mobilitybench_optional.py` | `a2a` or `relocation` (each imported lazily) | through `bench run` | `run_a2a_delegate` (B2: every pure step over the official A2A SDK to a loopback worker thread) and `run_checkpoint_relocate` (B3: fenced LangGraph checkpoint relocation in one shared file), in `OPTIONAL_RUNNERS`. |
| `fixtures/mobilitybench-local-smoke/` | package data | none | `cases.jsonl`: the 20 smoke-case declarations (17 `pass`, 3 `known_gap`). |
| `fixtures/mobilitybench-v0.1/` | package data | none | `tasks.jsonl` (18), `ground_truth.jsonl` (18), `negative.jsonl` (12), `seeds.json` and `MANIFEST.json`. |

Related scripts outside the package: `tools/mobilitybench_freeze.py` recomputes or checks (`--check`) the v0.1 ground truth and manifest; `tools/schema_subset.py` validates documentation examples against [`schemas/handoff-envelope.schema.json`](../schemas/handoff-envelope.schema.json) (see [§6](#6-versioned-identifiers)); `tools/cli_reference.py` writes or checks [`docs/cli.md`](cli.md); `tools/check_test_registry.py` checks [`data/test-registry.csv`](../data/test-registry.csv) against `tests/`.

### Import dependencies

```mermaid
flowchart LR
    core[core]
    cli["cli (stdlib)"]
    main_mod[__main__] --> cli
    cli -. "lazy, per subcommand" .-> demo
    cli -. "lazy" .-> a2a_demo
    cli -. "lazy" .-> peer_demo
    cli -. "lazy" .-> relocation_demo
    demo -. "lazy, --receipts" .-> live_receipts
    cli -. "lazy" .-> mobilitybench
    cli -. "lazy" .-> receipts
    http[http] --> core
    demo[demo] --> core
    demo -. subprocess .-> http
    trust[trust] --> core
    peer[peer] --> core
    peer --> trust
    peer_http[peer_http] --> core
    peer_http --> http
    peer_http --> peer
    peer_http --> trust
    peer_demo[peer_demo] --> core
    peer_demo --> peer
    peer_demo --> peer_http
    peer_demo --> trust
    peer_demo -. subprocess .-> peer_http
    a2a_profile[a2a_profile] --> core
    a2a_server["a2a_server (a2a-sdk)"] --> a2a_profile
    a2a_server --> core
    a2a_client["a2a_client (a2a-sdk)"] --> a2a_profile
    a2a_client --> core
    a2a_demo[a2a_demo] --> core
    a2a_demo --> a2a_profile
    a2a_demo -. subprocess .-> a2a_server
    a2a_demo -. subprocess .-> a2a_client
    relocation_bundle[relocation_bundle] --> core
    relocation["relocation (langgraph)"] --> core
    relocation --> relocation_bundle
    relocation_demo[relocation_demo] --> relocation
    relocation_demo --> core
    relocation_demo -. "lazy, --two-store" .-> relocation_demo_two_store
    relocation_demo_two_store[relocation_demo_two_store] --> relocation
    relocation_demo_two_store --> relocation_demo
    relocation_demo_two_store --> core
    relocation_demo -. "lazy, reconcile" .-> relocation_reconcile
    relocation_demo -. "lazy" .-> relocation_demo_reconcile
    relocation_reconcile[relocation_reconcile] --> core
    relocation_reconcile -. lazy .-> relocation
    relocation_demo_reconcile[relocation_demo_reconcile] --> relocation
    relocation_demo_reconcile --> relocation_demo
    relocation_demo_reconcile --> relocation_demo_two_store
    live_receipts[live_receipts] --> core
    live_receipts --> jcs
    live_receipts --> receipts
    receipts --> trust
    jcs[jcs]
    receipts[receipts] --> core
    receipts --> jcs
    receipts -. "lazy, make-fixtures" .-> receipt_fixtures
    receipt_fixtures[receipt_fixtures] --> receipts
    receipt_fixtures --> jcs
    receipt_fixtures --> core
    mobilitybench[mobilitybench] --> core
    mobilitybench -. "lazy, v0.1 subcommands" .-> mobilitybench_v01
    mobilitybench_v01[mobilitybench_v01] --> mobilitybench
    mobilitybench_v01 --> core
    mobilitybench_v01 -. "lazy, B2 and B3" .-> mobilitybench_optional
    mobilitybench_optional[mobilitybench_optional] --> mobilitybench_v01
    mobilitybench_optional --> core
    mobilitybench_optional -. lazy .-> a2a_server
    mobilitybench_optional -. lazy .-> a2a_client
    mobilitybench_optional -. lazy .-> relocation
```

Solid arrows are module-level Python imports inside the package. Dotted arrows labelled `subprocess` start a child process with `python -m`; dotted arrows labelled `lazy` are imports inside a function (`cli` imports its targets with `importlib` only when a subcommand runs). Only `a2a_server` and `a2a_client` (`a2a-sdk`, `httpx`, `starlette`, `protobuf`, `uvicorn`), `relocation` (`langgraph`) and the Ed25519 and HPKE paths in `trust`, `receipts` and `receipt_fixtures` (`cryptography`) import third-party code. `trust` and `receipts` import `cryptography` only when it is installed.

## 3. Data flows

### 3.1 Delegation over loopback HTTP (core, not A2A)

`demo.main` sends a `0.1.0-draft` envelope to a receiver process. `validate_envelope` accepts exactly 11 top-level fields and rejects anything else. That includes unknown fields, other task kinds, other classifications and text longer than 2048 bytes.

```mermaid
sequenceDiagram
    participant O as demo.py origin agent-a
    participant H as http.py process agent-b
    participant R as HandoffReceiver
    participant S as SQLiteStore
    O->>H: POST /v0/handoffs with envelope JSON
    H->>H: Content-Type, size and parse_json checks
    H->>R: receive message
    R->>R: validate_envelope, destination equals own name
    R->>R: Approval.allows - ref, task, origin, destination, kind, classification, not revoked, not expired
    alt no matching approval
        R->>S: denied writes handoff.denied event
        H-->>O: 403 approval_denied
    else approved
        R->>S: receive in one BEGIN IMMEDIATE transaction
        alt sender and idempotency_key seen with the same envelope digest
            S-->>H: stored receipt with replayed true
            H-->>O: 200 receipt
        else key or movement_id reused with a different envelope
            S-->>H: Conflict
            H-->>O: 409 idempotency_conflict
        else new
            S->>S: compute word_count or sha256, insert deliveries row and audit events
            H-->>O: 200 receipt with envelope_digest and artifact_digest
        end
    end
```

A malformed body or envelope returns 400 `invalid_contract` before any of this runs.

**Per-sender idempotency keys and the store version (issue #29).** `SQLiteStore.receive(envelope, sender=None)` scopes an idempotency key to a sender: the authenticated origin when the caller knows it (`PeerReceiver` passes `sender=origin.agent_id`), otherwise the envelope's claimed `origin.agent_id` (`HandoffReceiver`, which authenticates nobody). Two senders may use the same key; a `movement_id` stays unique across all senders. The layout is recorded in `PRAGMA user_version` (`STORE_SCHEMA_VERSION = 1`). On open, `_ensure_schema` migrates a version-0 file (global keys) in one `BEGIN IMMEDIATE` transaction by copying `deliveries` into a new table keyed by `(sender_id, idempotency_key)`, taking the sender from each stored receipt's `origin_agent_id`; a newer version raises `StoreSchemaError`.

The same `SQLiteStore` provides the **simulated** effect fence, `EffectGateway`. `claim` inserts an `owners` row at epoch 1. `transfer` compares the owner and epoch and then increments the epoch. `commit` rereads `owners` in the same transaction as the `effects` insert, so a stale epoch raises `PolicyDenied`. `reconcile` returns `committed` or `unknown`. The receipt is **unsigned**, and its digests are unsalted SHA-256 values over canonical JSON that contains the task text.

### 3.2 Delegation over A2A v1 (optional `a2a` extra)

The A2A path reuses `HandoffReceiver` unchanged. `a2a_profile` maps envelope fields into `Message.metadata[<profile URI>]` and puts `{kind, text}` into a single data part with the media type `application/vnd.agent-movement.task+json`. The profile URI is `EXTENSION_URI`, the URL of the [profile extension spec](a2a-profile-extension.md); the old URN `LEGACY_EXTENSION_URI` is still accepted as a deprecated alias.

**contextId policy (issue #18).** By default the server generates the A2A `contextId` and the client sends none. `check_context_id` runs at admission, on the contextId exactly as the client sent it: an empty one is always accepted; a client-supplied one is accepted only under the policy `bound-to-logical-task-id` and only if it equals the envelope's `logical_task_id`. The server adopts that policy only when started with `--accept-client-context-id`, and the card publishes it in the profile extension's `params.client_context_id`, so `a2a_client.check_card` can refuse to send a contextId to a server that does not accept one. Requests that use the legacy URN keep the profile 0.1 rule (bound to `logical_task_id`).

```mermaid
sequenceDiagram
    participant C as a2a_client.delegate
    participant A as a2a_server Starlette app
    participant Q as HandoffRequestHandler
    participant E as HandoffExecutor
    participant R as HandoffReceiver and SQLiteStore
    participant L as A2ACorrelationLog
    C->>A: GET /.well-known/agent-card.json
    C->>C: check_card - profile URI, skill and, if sending a contextId, the client_context_id policy
    C->>A: SendMessage over /a2a/jsonrpc or /a2a/rest, profile URI activated, no contextId by default
    A->>Q: on_message_send or on_message_send_stream
    Q->>Q: _admit - URI activated, decode_handoff, check_context_id, kind advertised
    alt admission fails
        Q->>L: record rejected outcome
        Q-->>C: A2A error, no task created
    else admitted
        Q->>E: execute with the server-generated or bound contextId
        E-->>C: task SUBMITTED, then WORKING
        E->>R: receive envelope
        alt PolicyDenied, Conflict or ContractError
            E->>L: record reason
            E-->>C: task REJECTED with an error data part
        else completed or replayed
            E-->>C: artifact handoff-receipt, metadata keyed by the URI the client used
            E->>L: record completed or replayed
            E-->>C: task COMPLETED
        end
    end
    C->>A: GetTask by A2A task id
    C->>C: verify_receipt and check that a contextId was generated or preserved
```

Before the profile checks, `_admit` also applies two core A2A v1.0 rules: an undeclared part media type gives `ContentTypeNotSupportedError` (`validate_input_modes`), and a message that names a `taskId` gives `TaskNotFoundError` or `UnsupportedOperationError`. The card is served with `Cache-Control: public, max-age=60`. These checks were added after running the official A2A TCK; the optional `a2a-interop.yml` workflow runs the TCK, the A2A Inspector and a JavaScript SDK client.

This shows **delegation**, not migration. Nothing is authenticated, and the agent IDs remain claims.

### 3.3 Authenticated pre-disclosure handoff (`trust` and `peer`)

`PeerClient.handoff` sends metadata before the payload. The task text leaves the origin only after it has verified the destination card and a receiver-signed admission. Every signed message is a `seal` object `{alg, kid, payload, sig}`, and each signature covers a purpose-specific domain (`agent-card`, `grant`, `preflight`, `admission`, `delivery`, `receipt` or `revocation`).

**HPKE-sealed delivery (issue #19, optional `hpke` extra).** A receiver card may carry an X25519 `enc_key` that the same CA signature covers, so a relay cannot substitute its own encryption key. If it does, the delivery is always sealed to it (`PeerClient` never downgrades; if HPKE is unavailable it aborts with `encryption_unavailable`). The task, salt and a fresh 32-byte response key travel only inside an RFC 9180 HPKE ciphertext (`HPKE_SUITE`: base mode, DHKEM(X25519, HKDF-SHA256), HKDF-SHA256, ChaCha20-Poly1305). `trust.delivery_info` binds the ciphertext to the preflight transcript: suite, key ID, card digest, movement, origin, audience, endpoint, client nonce, admission and preflight digest. The origin signs the ciphertext; the receiver verifies that signature before it opens the ciphertext, and returns its signed receipt encrypted under the response key (`seal_response`). A receiver with an `enc_key` refuses a plaintext delivery (`plaintext_delivery_refused`). `require_confidentiality=True` makes the client refuse cards without an `enc_key`. Without an `enc_key`, which is always the case in the stdlib-only mode, deliveries are plaintext and have **no confidentiality**.

```mermaid
sequenceDiagram
    participant U as user authority test key
    participant O as PeerClient agent-a
    participant B as PeerReceiver agent-b
    participant D as SQLite PeerLedger and SQLiteStore
    U->>O: issue_grant - subject, actor, audience, task, capabilities, window
    O->>B: GET /v0/agent-card
    B-->>O: CA-signed card, optionally with an X25519 enc_key
    O->>O: verify_card against pinned TrustStore, check id, endpoint, schema, capability, enc_key policy
    O->>O: never_send guard on preflight and delivery bytes
    O->>B: POST /v0/preflight - signed metadata, grant, nonce, salted commitment, no text
    B->>B: verify origin card and signature, clock skew, destination binding, allowlist
    B->>B: verify_grant and check_grant_scope
    B->>D: BEGIN IMMEDIATE - grant live and not revoked, nonce, consume_use under max_uses, admission
    B-->>O: signed admission echoing nonce and preflight digest
    O->>O: unseal with card key, check bindings and expiry
    alt card has enc_key
        O->>B: POST /v0/deliveries - signed HPKE ciphertext bound to the transcript
        B->>B: verify signature, then open with the enc_key private key
    else no enc_key, plaintext mode
        O->>B: POST /v0/deliveries - signed task text and salt, no confidentiality
    end
    B->>B: re-verify card, admission expiry, commitment match, grant live
    B->>D: SQLiteStore.receive - pure computation, idempotent
    B->>D: AuthorizedEffectGateway.commit - revocation and expiry rechecked in the same transaction
    B-->>O: signed receipt, encrypted under the response key in HPKE mode
```

**Counted grants (issue #29).** A grant carries a signed `max_uses` (default 1, at most `MAX_GRANT_USES`; a grant signed without the field verifies as single-use). In the preflight transaction `PeerLedger.consume_use` records one row in `grant_uses` per distinct movement and refuses the next one with `grant_uses_exhausted`. A retry of an admitted movement whose binding (`MOVEMENT_BINDING`: origin, task, grant, kind, classification, idempotency key, trace) is unchanged is re-admitted (`readmitted`) and consumes nothing; a different binding under the same `movement_id` is a conflict. A ledger written before use counting is backfilled with one use per existing admission.

A grant issuer can post a signed revocation to `POST /v0/revocations`. `PeerLedger.revoke` and `AuthorizedEffectGateway.commit` both use `BEGIN IMMEDIATE`, so whichever commits first wins. If a revocation arrives after delivery has started, the task text has already been sent (sealed in HPKE mode) but the effect is refused; `peer_demo` reports this case as `revoked-in-flight`. Peers receive only coarse HTTP errors (400, 401, 403 or 409). The specific reason is written only to `peer_trace`.

The suite is checked against RFC 9180 Appendix A.2.1 in `tests/test_peer.py::Rfc9180KnownAnswerTests`. That vector uses a non-empty AAD, which the public single-shot API does not take, so the test calls a private `cryptography` helper and skips itself if that helper disappears; the protocol uses only the public `encrypt`/`decrypt` with `info`.

### 3.4 Checkpoint relocation, single store (optional `relocation` extra)

A logical task is one LangGraph `thread_id`. An execution is `worker_id.incarnation`. Ownership is the core `owners` row (`agent_id`, `epoch`). Every write rechecks it inside its own SQLite transaction (`relocation._fence`): checkpoint writes in `FencedSqliteSaver.cursor`, `EffectLedger.record_intent`/`mark` and `OpaqueTool.invoke`.

```mermaid
sequenceDiagram
    participant A as Worker A worker-a.1
    participant K as Coordinator
    participant B as Worker B worker-b.1
    participant S as shared SQLite file
    A->>S: start - EffectGateway.claim epoch 1, run supersteps with durable checkpoints
    A->>A: export - must own task, build_manifest cooperative, no pending writes, no uncertain effects
    A->>K: request manifest
    K->>S: fence A at epoch 1, insert relocations row status requested
    K->>S: transfer - compatibility check, head checkpoint equals manifest, owners epoch to 2
    K->>S: relocations status transferred
    B->>S: accept - grant addressed to B, owner is B at epoch 2
    B->>B: compatibility, exported checkpoint digest, head unchanged
    B->>K: acknowledge
    K->>S: relocations status acknowledged
    B->>S: run from the exported checkpoint at epoch 2
    A--xS: any later write by A at epoch 1 is fenced with PolicyDenied
```

`Coordinator.failover` builds a `failover` manifest from the durable head without the origin's help. `compatibility` refuses on any mismatch (`refuse_fail_closed`) in the profile, the pinned runtime, the graph ID or version, the checkpoint format or the channels. The effect node writes an intent before the call, marks `attempt_started`, and calls either `EffectGateway.commit` (idempotent and queryable) or `OpaqueTool.invoke` (neither). For `opaque`, an interrupted call becomes `unknown` and the run ends with `reconcile_required` instead of retrying. In this mode origin and receiver share **one local file**, so the checkpoint is exported by reference.

### 3.5 Checkpoint relocation, two stores (issue #20)

With `Worker(..., store=PATH)` each worker keeps its checkpoints, effect ledger and node journal in **its own** SQLite file (`init_worker_store`). The coordinator file (`init_authority`) holds only `owners`, `effects`, `relocations` and `opaque_effects`. A worker store `ATTACH`es the coordinator file as schema `authority`, so one `BEGIN IMMEDIATE` holds both files' write locks while `_fence` checks the epoch and the write runs. The head checkpoint is **copied, not shared**: it travels as one canonical-JSON bundle (`relocation_bundle`), with no network transport.

```mermaid
sequenceDiagram
    participant A as Worker A, own store worker-a.sqlite
    participant K as Coordinator, coordinator.sqlite
    participant T as harness copy, outbox to inbox
    participant B as Worker B, own store worker-b.sqlite
    A->>A: export_bundle - build_manifest plus read_payload of the head checkpoint, writes and effect ledger
    A->>A: write_atomic to outbox-worker-a/MOVEMENT.bundle.json, manifest has section and channel digests
    A->>K: request_bundle - head still equals the bundled checkpoint, record manifest_digest
    Note over A,K: export freeze - A's writes are denied while the request is pending
    K->>K: transfer - compatibility, owners epoch to 2, status transferred
    T->>B: copy bundle bytes into inbox-worker-b
    B->>B: parse - size limit, canonical bytes, known format, no duplicate keys
    B->>K: bundle manifest digest must equal the recorded manifest_digest
    B->>B: compatibility, then section digests before any deserialization
    B->>B: decode_checkpoint with the pinned serializer, channel and checkpoint digests
    B->>B: _import_rows - one fenced transaction inserts rows and a bundle_imports record, never rewinds
    B->>K: acknowledge, then run from the copied checkpoint at epoch 2
```

The coordinator's recorded manifest digest, not the bundle, is the trust anchor; bundles are not signed. Section digests are checked before LangGraph's serializer runs, and only `msgpack` checkpoint rows are accepted (`CHECKPOINT_TYPES`), so `pickle` is refused unread. Any refusal raises `Incompatible` with a report (`reason`, `corrupt_sections`, `corrupt_channels`, `unavailable_state`) and imports nothing. In two-store failover, `Coordinator.failover(..., source_store=..., outbox=...)` re-exports from the store that holds the durable head, which the recovering operator must be able to read. Only the head checkpoint is copied; its ancestors stay in the origin store (`BUNDLE_UNSUPPORTED_STATE`).

### 3.6 Operator reconciliation of parked effects (issue #30)

An `opaque` tool has no idempotency key and no status lookup, so a crash around its call leaves the outcome unknown and the run ends with `reconcile_required` (fault rows C13 and C14). The effect is then **parked**: `relocation._park` writes an `effect_reconciliations` row with status `parked` and an audit event in the coordinator file. An operator checks the external system out of band and records a decision; the owning worker then resumes.

```mermaid
sequenceDiagram
    participant W as owning worker, epoch N
    participant K as Coordinator, authority file
    participant O as operator, relocation_reconcile CLI
    participant X as external system, simulated
    W->>W: effect_commit finds attempt_started or unknown for an opaque tool
    W->>K: _park - effect_reconciliations row parked, reconciliation_events parked
    W-->>W: run ends with reconcile_required
    O->>K: list - parked effects and their decisions
    O->>X: out-of-band check, not verified by the code
    O->>K: decide confirmed_done or confirmed_absent with operator, reason and the epoch inspected
    K->>K: Coordinator.reconcile - fenced by the current epoch, identical replay accepted, any other denied and logged
    O->>W: resume with worker, incarnation and epoch
    W->>W: EffectLedger.apply_decision in a fenced transaction
    alt confirmed_done
        W->>W: effect settled as committed, no call
    else confirmed_absent
        W->>X: one retry under the new effect ID with suffix .retry-1
    end
    W->>K: reconciliation_events applied, run continues to done
```

`decide` records the operator's claim; the code fences it by the ownership epoch and keeps an append-only log, but cannot check it. A false `confirmed_done` loses the effect and a false `confirmed_absent` duplicates it; rows C13d and C14a show both on purpose. A `confirmed_absent` decision authorizes exactly one retry (`RETRY_SUFFIX`). The same commands work in two-store mode, where `resume --store` names the worker's own file.

### 3.7 Receipt verification (offline)

`agent-movement receipts verify BUNDLE --trust ANCHORS` reads an evidence bundle directory and never contacts the network.

**Out-of-band trust anchors (issue #21).** `resolve_trust` fails closed (exit 2) unless `--trust FILE` is given, and it also refuses a trust file inside the bundle being verified, because anchors shipped with the evidence prove nothing. A `trust.json` next to the evidence is never used implicitly. `--fixture-trust` is an explicit opt-in for the synthetic fixtures only: it reads the bundle's or its parent's `trust.json`, prints a warning, and marks the report `trust_anchor_mode: fixture`.

```mermaid
flowchart TD
    T["anchors from --trust, obtained out of band"] --> RT["resolve_trust - missing or inside the bundle means exit 2"]
    RT --> LT["load_trust_anchors - receipt keys and revocation_issuers"]
    RN["revocations.jsonl in the bundle, or --revocations FILE"] --> AN["apply_notices - verify_notice against pinned Ed25519 revocation issuers"]
    LT --> AN
    AN --> VW
    R1[receipts.jsonl] --> VW["_verify_wire per line"]
    R2[tool-records.jsonl] --> VW
    VW --> V{"verdict"}
    V -->|"VALID or UNCHECKED"| RG["ReplayGuard - duplicate means REPLAYED, reuse means CONFLICTING"]
    V -->|"TAMPERED, UNTRUSTED or MALFORMED"| REP[report]
    RG --> CH["_check_chains - per-key seq and prev_receipt_digest"]
    CH --> MV["_movements, _effects, _lineage, _executions"]
    SUB["subjects/REF.json"] --> SJ["_subjects - DIGEST_MATCH or DIGEST_MISMATCH"]
    TEL[telemetry.jsonl] --> LTEL["_load_telemetry - redact and keep allowlisted attributes"]
    MV --> TL[_timeline]
    SJ --> TL
    LTEL --> TL
    TL --> REP
    REP --> EX["exit 0 all valid, 1 rejected or conflicting, 3 unchecked or nothing valid, 2 usage error or no anchors"]
```

**Signed revocation notices (issue #32).** The trust anchor file may pin `revocation_issuers` (Ed25519 public keys only; HS256 is refused because its verifier is a shared secret). Notices in the issue #8 format (`trust.issue_revocation`) are read from the bundle's `revocations.jsonl` and from each `--revocations FILE`. They may travel with the evidence because they are self-authenticating: `verify_notice` checks each one with `trust.verify_revocation` against the pinned issuers, and only a `VALID` notice is applied. It revokes the receipt key whose `key_id` equals the notice's `grant_id` from `revoked_at` on, and a notice can only make a key less trusted (the earliest verified time wins). `revoked_at` is still the issuer's claim, so a receipt backdated before it is not detectable.

**Live receipts (issue #32, opt-in).** `agent-movement demo --receipts OUTDIR` makes the sender sign `movement.dispatched` before it posts, the receiver (`http --receipts-log`) sign `movement.accepted` plus `execution.completed` or `movement.rejected` before it answers, and a `RecordingEffectGateway` sign `tool.effect_recorded` for each fenced effect attempt. `export_run` writes the evidence bundle `OUTDIR/live-run/` and, outside it, `OUTDIR/trust-anchors.json`; the demo then verifies the bundle and fails if the verifier does not exit 0. Keys are fresh synthetic Ed25519 keys held only in memory for the run, and receipts reference salted commitments, never task text. Emission is best effort: a receipt that cannot be signed or written shows up as an absent receipt (`UNKNOWN`), never as a fabricated one.

`_verify_wire` checks the following, in order: the strict JSON wire shape `{receipt, body_digest, signature}`, a credential scan (`contains_token_like`), `validate_body`, the `jcs_digest` match, the signature block against `issuer.key_id`, whether the key is in the trust anchors, Ed25519 over `SIGNATURE_DOMAIN || canonicalize(body)`, the key validity window and revocation at the claimed `issued_at`, the claimed principal, and the signer role (`tool` keys for `tool.effect_recorded`, `agent` keys for everything else). Without the `signing` extra, signatures are reported as `UNCHECKED` and valid bundles exit 3. Evidence grades are `E1` (unverified claim), `E2` (verified signature) and `E3` (an agent claim corroborated by an independent tool record, or both sides of a movement verified). `E0` is never assigned. The committed fixture files are also scanned with a subset of the gitleaks v8.30.1 rules, and with the real `gitleaks` binary when it is available (`tests/test_movement_receipts_secret_scan.py`).

### 3.8 MobilityBench (core; B2 and B3 need extras)

`mobilitybench.run_suite` runs the cases declared in `fixtures/mobilitybench-local-smoke/cases.jsonl` directly against the core classes. Each declaration names its scenario, the expected observation and an `expectation` (`pass`, `known_gap` or `gap_closed`); `load_cases` requires every declaration to have a `case_<scenario>` evaluator and, for the packaged file, every evaluator to have a declaration. Each case runs in its own temporary directory, so results do not depend on order, and `verdict_for` compares the observation with the declaration: a `known_gap` case that shows its declared `closed_observation` is reported as `gap_closed`, not as a failure. At `fbecb57` the 20 cases give 17 `pass` and 3 `known_gap`. With `--no-timing`, `duration_ms` is `null` and two runs are byte-identical; `outcome_digest` hashes the records without timing.

`mobilitybench_v01.run_suite` first checks the packaged fixtures against `MANIFEST.json`, then runs every selected task in each mode of `MODES` under the seeded `fault_schedule`, then runs the 12 negative cases of `negative.jsonl` through the 10 attack handlers in `SECURITY` (two cases share `classification_gate` and two share `run_task`). `HARNESS_VERSION` is `0.2.0`; the fixture release and `SUITE_VERSION` are unchanged.

| Mode | Baseline | Needs | Without the extra |
|---|---|---|---|
| `keep_on_origin` | B0 | core | always scored |
| `restart_on_destination` | B1 | core | always scored |
| `local_delegate` | B2-local, in-process `HandoffReceiver` | core | always scored |
| `a2a_delegate` | B2, every pure step over the official A2A SDK to a loopback worker thread (`mobilitybench_optional.run_a2a_delegate`) | `a2a` | `unavailable`, reason `extra_not_installed:a2a` |
| `checkpoint_relocate` | B3, fenced LangGraph relocation in one shared file (`run_checkpoint_relocate`) | `relocation` | `unavailable`, reason `extra_not_installed:relocation` |
| `cross_framework_reconstruct` | B4 | not implemented | always `unavailable`, reason `baseline_not_implemented` |

`mode_table` resolves the status with `extra_available`, and `run_attempt` still emits one record per (task, mode, fault, seed, repeat) with `outcome: "unavailable"` and that reason, so unavailable modes stay in every denominator. The run manifest records the installed extra versions (`extras_versions`). `run_suite` raises `RuntimeError` if any `redact_terms` string from the fixtures or the `CANARY` string appears in the records. No model is called (`MODEL = "none"`).

MobilityBench therefore measures the core handoff and fencing logic under scripted faults, plus the A2A adapter and single-store relocation when their extras are installed. It does not exercise peer authentication, HPKE, two-store relocation or operator reconciliation.

## 4. Trust boundaries

```mermaid
flowchart LR
    subgraph ORIGIN["Origin process"]
        OC["demo, PeerClient or a2a_client"]
        GUARD["never_send guard and HPKE seal - peer only"]
    end
    subgraph LOOP["Loopback TCP 127.0.0.1, no TLS"]
        W1["/v0/handoffs"]
        W2["/v0/agent-card, /v0/preflight, /v0/deliveries, /v0/revocations"]
        W3["/a2a/jsonrpc, /a2a/rest, agent card"]
    end
    subgraph RECV["Receiver process"]
        VAL["parse_json and validate_envelope"]
        POL["Approval or grant, card and contextId checks"]
        STORE[("SQLite file")]
    end
    subgraph RELOC["Two-store relocation, local files"]
        SA[("worker-a store")]
        BUN["bundle file, copied outbox to inbox"]
        SB[("worker-b store")]
        AUTH[("coordinator file: owners, relocations, manifest_digest")]
    end
    subgraph OOB["Out of band, pinned before the run"]
        TS["TrustStore: CA, user authority, HS256 peer keys"]
        TA["receipts trust anchors and revocation issuers, passed with --trust"]
    end
    OC --> GUARD --> W2
    OC --> W1
    OC --> W3
    W1 --> VAL
    W2 --> VAL
    W3 --> VAL
    VAL --> POL --> STORE
    TS --> POL
    TS --> OC
    SA --> BUN --> SB
    AUTH -. "digest check before import" .-> SB
    TA -. offline verifier .-> STORE
```

| Boundary | What is enforced in code | What is **not** enforced |
|---|---|---|
| Network bind | All servers bind `127.0.0.1` (`http.make_server`, `peer_http.make_peer_server`, `a2a_server.main`). `peer.HttpTransport` refuses any URL that is not loopback. | TLS, authentication of the HTTP peer, rate limits. |
| Input parsing | `core.parse_json` rejects duplicate keys and NaN/Infinity and limits the body to 16 KiB. The two stdlib servers (`http`, `peer_http`) require `application/json` and `0 < Content-Length <= 16384`; the A2A server relies on the SDK for framing and then applies `decode_handoff`. Envelope, preflight, delivery and receipt objects must have exact field sets. | A schema language. The checks are hand-written. |
| Core authorization | `Approval.allows` is a receiver-local allowlist entry with an expiry. | Sender identity. `origin.agent_id` is only a claim. |
| A2A context | A client contextId is rejected unless the server opted in, and then must equal `logical_task_id`; the policy is published on the card. | Authentication of the A2A client. |
| Peer identity | The card is signed by a pinned CA. The request is signed with the key the card names. Cards are bound to an endpoint. The admission is bound to the client nonce and the preflight digest. | Channel binding. HS256 keys are symmetric, so any verifier can also forge signatures; only Ed25519 rules this out. |
| Delivery confidentiality | With a CA-signed `enc_key`, the delivery is HPKE-sealed, transcript-bound and never downgraded, and the receipt is encrypted; an on-path relay at the real endpoint sees only ciphertext (`test_on_path_relay_sees_only_ciphertext_with_hpke`). | Any confidentiality in plaintext mode (no `enc_key`, the stdlib default). Metadata in the preflight is never encrypted. |
| User authority | Grants are scoped by actor, audience, task, capabilities, classification, validity window and a signed `max_uses`, and are rechecked at preflight, at delivery and inside the effect transaction; uses are counted in the admission transaction. | A real OAuth/RFC 8693 exchange. |
| Disclosure | Only a salted commitment travels before admission. `PeerClient` refuses to send bytes that contain a `never_send` value or its own secret key. | Disclosure after delivery has started, for example `revoked-in-flight`. |
| Operator decisions | A reconciliation decision is fenced by the current ownership epoch, must target a parked effect, is applied once in a fenced transaction, and every decision, denial and application is appended to `reconciliation_events`. | The truth of the operator's claim about the external system. |
| Ownership | The `owners` epoch is checked in the same transaction as every fenced write, in two-store mode through the attached coordinator file; an exporting owner is frozen until transfer or refusal. | Tools outside the simulated gateway. `OpaqueTool` outcomes can stay `unknown`. |
| Relocation bundle | Bytes are size-bounded, canonical and of a known format; the manifest must match the coordinator's recorded digest; section digests are checked before deserialization; import is one fenced transaction and never rewinds. | Bundle signatures (integrity rests on the shared coordinator file), cross-host transport, history before the head checkpoint. |
| Evidence | Trust anchors must come from `--trust` and must not lie inside the bundle; `--fixture-trust` is an explicit, warned exception for synthetic fixtures. Revocation notices are applied only if signed by an Ed25519 issuer pinned in the anchors. Agent labels stay `claimed_agent_id`. | Anchor provenance beyond "passed by the operator". Trusted time: `issued_at` is the signer's claim. Completeness: a bundle may be missing receipts. |

## 5. Storage schema

All persistent state is SQLite. One file can hold several groups of tables, because each class adds its own `CREATE TABLE IF NOT EXISTS` statements to the same path.

| Table | Created by | Columns (key in **bold**) | Contents |
|---|---|---|---|
| `deliveries` | `core.SQLiteStore` | **`sender_id`, `idempotency_key`**, `movement_id` (UNIQUE), `envelope_digest`, `receipt_json` | One memoized receipt per (sender, key). Layout version 1 in `PRAGMA user_version`; version-0 files (key alone) are migrated on open. |
| `audit_events` | `core.SQLiteStore` | **`seq`**, `movement_id`, `task_id`, `event_type`, `info_digest`, `event_time` | `handoff.accepted`, `handoff.completed` and `handoff.denied` events. Stores digests only, never task text. |
| `owners` | `core.SQLiteStore` | **`task_id`**, `agent_id`, `epoch` | The ownership epoch used by `EffectGateway` and by `relocation`. |
| `effects` | `core.SQLiteStore` | **`task_id`, `effect_id`**, `payload_digest`, `epoch` | Simulated, fenced effect commits. |
| `a2a_correlations` | `a2a_profile.A2ACorrelationLog` | **`seq`**, `a2a_task_id`, `a2a_context_id`, `a2a_message_id`, `movement_id`, `trace_id`, `outcome`, `envelope_digest`, `artifact_digest`, `event_time` | Joins A2A IDs to handoff outcomes. IDs that are not safe tokens are hashed (`safe_token`). |
| `peer_nonces` | `peer.PeerLedger` | **`origin_id`, `nonce`**, `seen_at` | Replay protection for preflights. Old rows are pruned. |
| `peer_admissions` | `peer.PeerLedger` | **`admission_id`**, `movement_id` (UNIQUE), `record_json`, `expires_at` | Admitted preflight metadata, including the commitment. Never contains task text. |
| `grant_uses` | `peer.PeerLedger` | **`grant_id`, `movement_id`**, `origin_id`, `use_number` (UNIQUE per grant, at least 1), `max_uses`, `at` | One counted use per admitted movement. |
| `authority_log` | `peer.PeerLedger` | **`seq`**, `event`, `grant_id`, `ref`, `at` | `revoke` and `effect` events in commit order. |
| `grant_revocations` | `peer.PeerLedger` | **`grant_id`**, `revoked_at`, `log_seq` | Revoked grants. |
| `authorized_effects` | `peer.PeerLedger` | **`task_id`, `effect_id`**, `grant_id`, `agent_id`, `payload_digest`, `log_seq` | Simulated effects committed under a live grant. |
| `peer_trace` | `peer.PeerLedger` | **`seq`**, `at`, `stage`, `outcome`, `reason`, `movement_id`, `peer`, `claimed_peer`, `admission_id` | A sanitized decision trace. `peer` is the authenticated ID and `claimed_peer` is the unauthenticated claim. |
| `relocations` | `relocation.AUTHORITY_SCHEMA` | **`movement_id`**, `task_id`, `mode`, `from_execution`, `from_epoch`, `to_execution`, `to_epoch`, `checkpoint_id`, `manifest_json`, `manifest_digest`, `status`, `report_json`, `transport` | `status`: `requested`, `transferred`, `acknowledged`, `refused` or `superseded`. `transport`: `shared` (default) or `bundle`. |
| `opaque_effects` | `relocation.AUTHORITY_SCHEMA` | **`seq`**, `task_id`, `effect_id`, `payload_digest`, `execution_id`, `epoch` | Ground truth for the non-idempotent tool. Only the harness reads it. |
| `effect_reconciliations` | `relocation.AUTHORITY_SCHEMA` | **`task_id`, `effect_id`**, `tool`, `payload_digest`, `parked_by`, `parked_epoch`, `retry_of`, `status`, `decision_json`, `decision_digest`, `retry_effect_id`, `applied_by`, `applied_epoch` | One parked effect and its operator decision. `status`: `parked`, `confirmed_done` or `confirmed_absent`. |
| `reconciliation_events` | `relocation.AUTHORITY_SCHEMA` | **`seq`**, `task_id`, `effect_id`, `event_type`, `actor`, `epoch`, `detail_json`, `event_time` | Append-only audit log: `parked`, decisions, `replayed`, `denied` and `applied` events. |
| `effect_intents` | `relocation.STATE_SCHEMA` | **`task_id`, `effect_id`**, `payload_digest`, `tool`, `status`, `execution_id`, `epoch`, `attempts` | A write-ahead effect ledger. `status`: `intent`, `attempt_started`, `committed`, `reconciled_committed` or `unknown`, and after an operator decision `confirmed_done` or `confirmed_absent`. |
| `node_runs` | `relocation.STATE_SCHEMA` | **`seq`**, `task_id`, `execution_id`, `epoch`, `node`, `item_index` | Harness instrumentation: every node attempt. |
| `bundle_imports` | `relocation.STATE_SCHEMA` | **`movement_id`**, `task_id`, `checkpoint_id`, `manifest_digest`, `bundle_sha256`, `execution_id`, `epoch` | One row per imported movement. A repeated import of the same movement must carry the same manifest digest and bundle hash, otherwise it is refused. |
| `checkpoints`, `writes` | LangGraph `SqliteSaver.setup()` | Defined by `langgraph-checkpoint-sqlite` 3.1.2 | Durable graph checkpoints. `Coordinator` and `relocation_bundle` read and copy their rows directly. |

`relocation.init_store` (single store) creates `SCHEMA = AUTHORITY_SCHEMA + STATE_SCHEMA` plus the core and LangGraph tables in one file. In two-store mode `init_authority` creates the core tables and `AUTHORITY_SCHEMA` (`relocations`, `opaque_effects`, `effect_reconciliations`, `reconciliation_events`) in the coordinator file, and `init_worker_store` creates `STATE_SCHEMA` and the LangGraph tables in each worker file.

Which file holds which tables:

- `demo` and `http`: `ledger.sqlite` holds the core tables. With `--receipts`, per-participant receipt logs sit in the same temporary directory, and only `OUTDIR/live-run/` and `OUTDIR/trust-anchors.json` are kept.
- `peer_demo`: `receiver.sqlite` holds the core and peer tables.
- `a2a_demo`: `receiver.sqlite` holds the core tables and `a2a_correlations`.
- `relocation_demo`: one `<scenario>.sqlite` per matrix row holds the core, relocation and LangGraph tables.
- `relocate reconcile example --dir DIR`: keeps `DIR/example.sqlite` (or the two-store files with `--two-store`) so the operator commands can be tried on it.
- `relocation_demo --two-store`: one directory per row with `coordinator.sqlite`, `worker-a.sqlite`, `worker-b.sqlite`, and the bundle directories `outbox-worker-a/`, `outbox-coordinator/` and `inbox-worker-b/`.
- `mobilitybench` (smoke suite): one `case.sqlite` per case, each in its own temporary directory, holding the core tables.
- `mobilitybench_v01`: `effects.sqlite` per attempt (core tables used by `EffectGateway`), plus `receiver.sqlite` for `local_delegate` attempts and `neg.sqlite` for the security cases.

Apart from the files named above, all of these files are in temporary directories. The receipt verifier uses no database: its `ReplayGuard` is in memory and its inputs are JSONL files.

## 6. Versioned identifiers

| Constant | Value | Defined in |
|---|---|---|
| `SCHEMA_VERSION` | `0.1.0-draft` | `core.py` |
| `STORE_SCHEMA_VERSION` | `1` (core store layout, in `PRAGMA user_version`) | `core.py` |
| `PEER_SCHEMA_VERSION` | `0.1.0-peer-draft` | `trust.py` |
| `HPKE_SUITE` | `hpke-base-x25519-hkdfsha256-chacha20poly1305` (a local label for the RFC 9180 suite) | `trust.py` |
| `EXTENSION_URI` | `https://github.com/MSKazemi/agent-movement/blob/main/docs/a2a-profile-extension.md` | `a2a_profile.py` |
| `LEGACY_EXTENSION_URI` | `urn:agent-movement:a2a-handoff-profile:0.1.0-draft` (deprecated alias) | `a2a_profile.py` |
| `PROFILE_VERSION` | `0.2.0-draft` (A2A profile) | `a2a_profile.py` |
| `PROFILE` | `am-checkpoint-relocation/0.1.0-draft` | `relocation.py` |
| `BUNDLE_FORMAT` | `am-checkpoint-bundle/0.1.0-draft` | `relocation_bundle.py` |
| `PINNED_RUNTIME` | `langgraph` 1.2.15, `langgraph-checkpoint` 4.3.0, `langgraph-checkpoint-sqlite` 3.1.2 | `relocation.py` |
| `RECEIPT_SCHEMA`, `TRUST_SCHEMA`, `REPORT_SCHEMA` | `agent-movement.receipt/0.1-draft`, `agent-movement.trust/0.1-draft`, `agent-movement.verification-report/0.1-draft` | `receipts.py` |
| `SUITE_VERSION` | `mobilitybench-local-smoke-v0.2` (smoke), `mobilitybench-v0.1` (v0.1) | `mobilitybench.py`, `mobilitybench_v01.py` |
| `HARNESS_VERSION` | `0.2.0` (v0.1 harness, scores B2 and B3 when their extras are installed) | `mobilitybench_v01.py` |
| Canonical envelope `schema_version` | `0.2.0-draft` (`const` in the schema) | [`schemas/handoff-envelope.schema.json`](../schemas/handoff-envelope.schema.json) |

None of these is a published standard. They are experimental profile identifiers. The canonical envelope schema (`0.2.0-draft`) and the implemented core contract (`SCHEMA_VERSION = "0.1.0-draft"`) differ: `core.validate_envelope` rejects any other version, so the code at `fbecb57` accepts no `0.2.0-draft` envelope. The full list of differences is in [how it works: divergences](how-it-works.md#divergences-from-the-implemented-contract).
