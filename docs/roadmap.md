# Reference architecture and roadmap (proposal)

## Architecture components

1. **Movement SDK** (typed task envelope, schema validation, operation IDs).
2. **Agent adapters** (local origin, A2A receiver; later LangGraph/other framework).
3. **Registry/discovery layer** (start static authenticated allowlist).
4. **Policy/approval service** (data class, destination trust, actions, budget, expiry).
5. **Transfer coordinator** (state machine, retry/reconciliation, cancellation).
6. **Artifact/checkpoint store** (content integrity, explicit retention, access controls).
7. **Telemetry/audit** (correlation IDs, redact payloads, record authorizations).
8. **Conformance and fault-injection suite** (security, reliability and interoperability).

This is an architectural hypothesis. Avoid inventing a new protocol where existing A2A/MCP fits.

## Phase 0: foundation / specifications

Deliver: written definitions, scope exclusions, protocol comparison, threat model, schema draft, glossary and test matrix. **This phase is documentation only; no working prototype is implied.**

Exit criteria: every promised "movement" capability maps to an explicit test and a dependency; separate delegation from relocation.

## Phase 1: end-to-end delegation demonstrator

Deliver: two local, isolated A2A-capable agents, simple allowlisted discovery, synthetic task, minimal versioned envelope, policy approval simulation, structured artifact return and correlated trace.

Exit criteria:
- Two distinct agent implementations exchange a task and artifact.
- Unsupported version / destination denied before disclosure.
- Every transfer event has a stable operation ID.
- Authentication failures and canceled grants are tested.
- Zero production secrets or private data in fixtures.

## Phase 2: durable execution and failure recovery

Implement a checkpoint abstraction for **one chosen runtime**, not universal migration; add durable state store, retries, cancellation, incident traces and idempotency tests.

Exit criteria:
- Crash/restart at each modeled state transition has documented behavior.
- Duplicate delivery never silently duplicates a simulated side effect.
- Ambiguous external execution returns **unknown/reconcile**, not false success.
- Compatibility mismatch explicitly blocks resume.

## Phase 3: multi-runtime portability

Introduce a second framework adapter, compatibility negotiation and loss-reporting. Benchmark delegation vs checkpoint relocation vs re-execution.

Exit criteria: publish reproducible failure/success matrices, partial compatibility boundaries and measured latency/cost under pinned versions.

## Phase 4: cross-machine/cloud trust boundary

Optional only after threat review: SPIFFE/OAuth-style bounded identities, encryption/isolated workers, data residency policies, stronger observability, registry governance and supply-chain checks.

## Proposed benchmark metrics

- Completion rate (%) and artifact correctness
- Duplicate externally visible effects (count)
- Mean/p95 dispatch and total latency (ms)
- Recovery time and failure injection survival (%)
- Transfer payload size (bytes)
- Unauthorized operations and leaked fields (target: zero in security fixtures)
- Policy decision correctness (%)
- Cost per completed task (tokens, compute, network)

## First tasks for contributors

1. Validate A2A SDK interoperability with a tiny two-agent smoke test.
2. Write JSON Schema for the proposed envelope and backward-compatibility tests.
3. Implement a fake side-effect tool with operation IDs and retry checks.
4. Build a fault-injection matrix with expected outcomes.
5. Compare one workflow's native checkpoints with an exportable application-level snapshot.

**Decision needed:** pick Phase 1 delegation-first as recommended starting point, or explicitly choose the far more complex checkpoint-relocation-first alternative.
