# Protocol choice, implementation sequence and benchmarks

## Decision tree

~~~mermaid
flowchart TD
  A[What should happen on target?] --> B{Only use a remote capability?}
  B -->|Yes| R[MCP / approved gateway: R]
  B -->|No| C{Different agent does work?}
  C -->|Yes| D[A2A over TLS: D]
  C -->|No| E{Start independent instance?}
  E -->|Yes| F[Signed package / OCI: C or P]
  E -->|No| G{Continue same logical task?}
  G -->|Yes| H{Compatible checkpoint and fenced original?}
  H -->|Yes| M[Durable restore with audited lease: M]
  H -->|No| X[Refuse M; propose new D with approval]
  G -->|No| Y[Clarify movement unit before implementation]
~~~

**Network choice is a secondary decision**: Choose HTTPS on ordinary reachable networks, a durable broker for intermittent links, a gateway for constrained devices, WebRTC only for explicitly approved peer connections, and encrypted signed bundles for offline environments.

## Baseline recommendations by target

| Environment | Control protocol | Bulk/artifact path | Discovery | Recovery |
| --- | --- | --- | --- | --- |
| Single machine | Local function/IPC; A2A loopback for interoperability | Local approved file/object store | Static config | Durable local checkpoint |
| Cloud ↔ cloud | A2A HTTPS/gRPC binding | Scoped object store HTTPS | Signed/allowlisted Agent Card, service discovery | Workflow DB / queue |
| Laptop ↔ cloud | A2A HTTPS | Short-lived scoped artifact object | Approved URL/Agent Card | Query status + retry discipline |
| Kubernetes | A2A front door, queue | OCI registry + object store | Cluster service discovery | Worker lease and durable checkpoint |
| Mobile/browser ↔ cloud | HTTPS, SSE/WSS as appropriate | User-approved HTTPS refs | Application enrollment | Offline outbox, user reapproval |
| Agent ↔ robot | A2A / MCP to companion gateway | Signed skills and artifacts | Allowlisted local gateway | Local failsafe, simulation |
| Industrial IoT | MQTT/CoAP/OPC UA gateway | Signed managed update, if permitted | Plant asset inventory | Store-forward, human release gate |
| Peer-to-peer | A2A via authenticated transport adapter | Scoped encrypted artifact transfer | Approved identity + relay plan | Durable local records |
| Air-gapped | Signed offline import/export format | Encrypted removable storage | Out-of-band owner enrollment | Receipt reconciliation, reject unsafe M |

## Build order

**P0 — Protocol survey and contracts (documentation only).** Fix the movement taxonomy, interface mappings, version pins, threat model, candidate devices and explicit excluded capabilities.

**P1 — Runnable delegated task (future work).** Two A2A-capable local agents with different instance IDs; sanitized synthetic task; approval simulation; artifact return; movement trace; no production credentials.

**P2 — Cross-host interoperability (future).** Linux laptop ↔ remote sandbox using TLS, scoped artifact store, verified endpoint, ACL and cancellation. Benchmark over Ethernet, Wi-Fi and emulated slow/partitioned WAN.

**P3 — Crash-safe compatible relocation (future).** Single chosen workflow runtime, versioned app checkpoint, fencing epoch (`fencing_epoch`) and fence, durable inbox/outbox, simulated side effects, fault injection. Explicitly distinguish pause/restart from live migration.

**P4 — Multi-runtime and non-cloud edges (future).** Second framework adapter with compatibility loss report, device gateway and benchmark cases for constrained links. Do not claim universal feature portability.

## Reproducible conformance test matrix

The scenarios T01–T18 are maintained in the single [test registry](../../data/test-registry.csv) (`data/test-registry.csv`). Each registry row gives the scenario with its expected result, the OWASP Agentic Top 10 threat (`ASI01`–`ASI10`), the status (`implemented`, `partial` or `planned`) and the pytest node IDs of the tests that implement it. The status is kept only there. When a scenario duplicates a case from another list, the registry keeps one canonical row and records the old ID in its `aliases` column. This crosswalk maps each old ID to its registry row:

| Old ID | Scenario | Registry row |
| --- | --- | --- |
| T01 | A2A task submitted to allowlisted destination | T01 |
| T02 | Unsupported binding, schema or mandatory capability | T02 |
| T03 | Forged discovery metadata or unapproved host | COM-T002 |
| T04 | Wrong-audience / revoked / expired authorization | COM-T003, COM-T004, COM-T005 |
| T05 | Mutated artifact/checkpoint digest | COM-T028 |
| T06 | Same idempotency key sent twice | T06 |
| T07 | Connectivity lost after acceptance | COM-T018 |
| T08 | Relocation without origin fence | T08 |
| T09 | Stale destination fencing epoch | T09 |
| T10 | Checkpoint/runtime version mismatch | T10 |
| T11 | Token and private text intentionally seeded in sample context | T11 |
| T12 | Simulated robot sends unsafe actuator command | COM-T025 |
| T13 | 24-hour disconnected queue / offline bundle | T13 |
| T14 | Concurrent copies from same template | T14 |
| T15 | Crash during each state transition | T15 |
| T16 | Cancellation before tool action | T16 |
| T17 | Large artifact versus small control message | T17 |
| T18 | Transport upgrade/downgrade attempt | T18 |

## Measurement schema for future experiments

Per trial record: test ID, timestamp, origin/destination runtime and versions, network class, protocol/binding, payload bytes, transport attempts, accepted/completed times, response code, task correctness, external effect count, checkpoint compatibility, trace coverage, policy outcome, CPU/RAM, transferred bytes, power/battery where relevant and per-task cost. Report median/p95 with sample count and confidence intervals; distinguish emulated from real link measurements.

**Which scenarios have tests is recorded only in the [test registry](../../data/test-registry.csv).** A `planned` row is an acceptance criterion for contributors, not an achieved feature. An `implemented` or `partial` row proves the case only in the local, synthetic setting of its tests.

See [protocol catalog](protocol-catalog.md) and [movement contract](handoff-and-relocation-contract.md).