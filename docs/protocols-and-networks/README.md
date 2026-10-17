# How AI agents can move: protocols and networks

**Status:** research and architecture guide, not an implemented SDK. **Reviewed:** 2026-10-15. The project term *Agent Movement* is a proposal, not an adopted internet standard. Sources below distinguish documented protocol behavior from proposed interoperability design.

## What actually moves?

Software does not physically travel: bytes are transmitted or stored; execution begins or resumes at an authorized destination. A network connection by itself is **not** agent migration.

| Operation | Unit transferred | Destination behavior | A typical stack | What this is NOT |
| --- | --- | --- | --- | --- |
| R: remote capability use | Tool call / result | Tool runs remotely; agent stays put | MCP via local stdio or HTTPS | Agent migration |
| D: delegation | Task, bounded context, artifact references | A different agent handles work | A2A over HTTPS (JSON-RPC, gRPC or HTTP+JSON) | Identity or checkpoint transfer |
| P: partial deployment | Specific module / skill / proxy | Only authorized component runs there | OCI/HTTPS; app install; signed firmware; robot middleware | Whole-agent transfer |
| C: copy / replication | Versioned package and permitted config | New instance with **new** identity and authority | OCI registry + orchestrator; signed artifact + HTTPS | A single continuing execution |
| M: application checkpoint relocation | Exportable task checkpoint + references | Compatible runtime resumes **one logical task** after origin is fenced | Durable store + HTTPS/queue + lease protocol | Live arbitrary process migration |
| L: live-process migration | Memory/OS process state | Highly environment-specific process continuation | Hypervisor or compatible checkpoint tooling | Cross-framework/OS general-purpose mobility |

Modes R, D, P, C, M and L follow the [device taxonomy](../device-compatibility-and-capability-matrix.md). For checkpoint relocation, external side effects need independent reconciliation; no network protocol guarantees that a payment, database update or robot action occurred exactly once.

## The protocol stack: choose by layer

| Layer | Question | Important choices | Role in movement |
| --- | --- | --- | --- |
| Physical / link | How are devices connected? | Ethernet, Wi-Fi, cellular 4G/5G, satellite, BLE, IEEE 802.15.4/Thread, LoRaWAN | Available path and link constraints; **never** sufficient to migrate software |
| Routing / reachability | Can endpoints address one another? | IPv4/IPv6, DNS, NAT, VPN, private overlay, relay, gateways | Locates reachable endpoints |
| Transport / security | How are bytes carried safely? | TCP+TLS, HTTP/2, HTTP/3 over QUIC, WebSocket/WSS, WebRTC DataChannel, SSH, DTLS | Connection, confidentiality, stream behavior |
| Agent interoperability | How do agents understand a task? | **A2A**: JSON-RPC/HTTPS, gRPC, HTTP+JSON | Discovery, task messages, status, artifact exchange |
| Tools / user interfaces | How do tools or frontends interact? | **MCP**: stdio, Streamable HTTP; **AG-UI**: agent/front-end events | Tools and UI, **not** checkpoint relocation |
| Messaging / resilience | Can work survive disconnects? | AMQP 1.0, MQTT, NATS JetStream, Kafka, queues, outbox | Async dispatch, replay and backpressure (with limits) |
| Artifact / program movement | How are large blobs and code moved? | HTTPS/object store, signed OCI images, managed storage, SSH/SFTP | Package / model / file / checkpoint distribution |
| Execution / identity | Who may run, and how do we continue? | Compatible runtimes, checkpoints, fencing leases, OAuth/SPIFFE, policies | Makes a movement operation controlled and auditable |

A2A, MCP and AG-UI occupy **different interfaces**. They complement rather than replace one another. A2A v1.0.x provides three standard bindings: JSON-RPC, gRPC and HTTP+JSON. A2A custom bindings are possible but must be explicitly specified and are not automatically standard A2A-over-MQTT or A2A-over-WebSocket. [A2A specification](https://a2a-protocol.org/v1.0.1/specification/), [custom bindings](https://github.com/a2aproject/A2A/blob/main/docs/topics/custom-protocol-bindings.md).

MCP revision **2026-07-28** uses stdio or Streamable HTTP (independent POSTs with JSON or request-scoped SSE responses); its prior session/GET streaming model changed. Implementations must pin/handle protocol versions rather than copy older examples blindly. [MCP transport overview](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports), [Streamable HTTP](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http).

## Proposed reference pattern (not implemented)

~~~mermaid
flowchart LR
    A[Origin agent] --> G[Policy and authorization gate]
    G --> D[Authenticated destination discovery]
    D --> E[Versioned task or checkpoint envelope]
    E --> B[A2A or adapter control plane]
    E --> S[Encrypted artifact and checkpoint store]
    B --> T[Destination runtime]
    S --> T
    T --> M[MCP tools / permitted device gateway]
    T --> Q[Result, checkpoint and reconciliation]
    Q --> A
    G --> O[Audit and trace]
    T --> O
~~~

**Control plane:** permission, negotiation, task submission, status, cancel and result. **Data plane:** immutable artifacts, model packages and checkpoints (prefer short-lived authorized references, not megabytes embedded in an RPC). **Execution plane:** compatible runtime and an exclusive task lease for relocation. **Evidence plane:** trace IDs, content hashes, approval records and observed outcomes.

## Choose a stack by situation

| Situation | Recommended initial path | Movement claim | Why |
| --- | --- | --- | --- |
| Two agents on one laptop | Direct in-process/IPC, or A2A over loopback HTTPS in tests; MCP stdio for local tools | D or R | Simple, easily reproducible |
| Laptop to trusted cloud agent | A2A/HTTPS; artifacts via scoped HTTPS URLs; policy + OIDC/OAuth as applicable | D | Works across machine/runtime boundaries without state portability claim |
| One compatible worker to another | Durable checkpoint store + coordinator + fenced lease + replay-safe resume | M, **only after verified tests** | State and side-effect semantics matter more than wire protocol |
| Kubernetes replicas | Signed OCI images, Kubernetes control plane, workflow queue | C / multiplication | Multiple instances are not one migrated identity |
| Enterprise asynchronous agents | A2A front door plus durable broker (AMQP/JetStream/Kafka) via application bridge | D + durable dispatch | Clients need not be simultaneously online |
| Browser / mobile companion | Outbound HTTPS, WebSocket or constrained WebRTC with user permission | R/P; sometimes app-scoped C | Sandboxing, sleep and platform restrictions |
| Raspberry Pi / Jetson / robot edge | HTTPS/A2A on companion computer; ROS 2 middleware to approved local skills | D/P/C; selected M | Control loop stays under device-local safety system |
| Tiny IoT MCU | CoAP/MQTT/Thread/BLE through owner-managed gateway | Usually R/P | Too constrained or restricted for arbitrary agent runtime |
| Disconnected field site | Locally durable outbox + signed, encrypted bundle; store/carry/forward when link available | D/P/C; M only if fence proven | Partition may cause ambiguous task ownership |
| High-latency satellite | Small envelope + resumable artifact sync + queued acknowledgments | D/P/C; conditional M | Delay, outages and bandwidth shape protocol choice |

## What is present in this repository?

No agent has been transferred by this repository and no reference implementation exists today. All recommended architectures and packet formats are **design proposals**; protocol names and documented behavior link to vendor/specification sources. Do not count candidate transports as implemented or tested compatibility.

## Documentation map

1. [Protocol catalog and interoperability details](protocol-catalog.md) — A2A, MCP, HTTP, gRPC, broker, IoT/robotics, packaging.
2. [Network types and topologies](network-topologies.md) — LAN, WAN, NAT, peer-to-peer, edge, mobile, offline.
3. [Proposed handoff and relocation contract](handoff-and-relocation-contract.md) — lifecycle, schema sketch, leases, status semantics.
4. [Security, reliability and observability](security-reliability-and-observability.md) — threat boundaries, revocation, replay safety, evidence.
5. [Decision guide and conformance benchmarks](decision-guide-and-benchmarks.md) — stack selection, cases and test criteria.
6. [Primary sources and evidence notes](primary-sources.md) — verifiable specifications and limitations.
7. [Machine-readable protocol/network matrix](../../data/protocol-network-matrix.csv) — comparison data, **not** interoperability certification.

Related existing work: [movement model](../how-it-works.md), [device inventory](../device-compatibility-and-capability-matrix.md), [security baseline](../security-and-trust.md), [roadmap](../roadmap.md).

**Default design:** Use an authenticated A2A handoff over TLS for the first cross-host demonstration; MCP for destination-local tools; HTTPS/object store for bigger artifacts; durable application checkpoint only in a second phase. Never autonomously propagate to unapproved hosts, copy reusable credentials, or claim universal live migration.