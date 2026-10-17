# Protocol catalog: what each one can and cannot move

**Research guide — 2026-10-15.** Compatibility statements are conceptual, not test results. Transport and application interoperability are separate.

## Agent-facing and tool-facing protocols

| Protocol | Interface | Native communication model | Movement usage | Crucial limitation |
| --- | --- | --- | --- | --- |
| A2A v1.0.x | Agent ↔ agent | Agent Cards, tasks, messages, artifacts; JSON-RPC, gRPC, HTTP+JSON bindings, task updates | Cross-agent delegation. *Project recommendation, not a measured result:* start here, because A2A is specified for "communication and interoperability between independent, potentially opaque AI agent systems" and defines Agent Card discovery, tasks with states, and three standard bindings ([spec v1.0.1](https://a2a-protocol.org/v1.0.1/specification/), accessed 2026-10-16) | Not a standard for migrating arbitrary process/checkpoint |
| MCP 2026-07-28 | Agent/model host ↔ tools/resources/prompts | stdio (local); Streamable HTTP (remote), JSON-RPC messages | Rebind a moved/delegated agent to approved tools | Does not move the agent or transfer authority |
| AG-UI (SDK `@ag-ui/core` 1.0.x: 1.0.0 on 2026-09-17, latest 1.0.2 on 2026-10-05; [npm registry](https://registry.npmjs.org/@ag-ui/core), checked 2026-10-16) | Agent backend ↔ frontend | Event stream and UI state | Show progress and request approval | Not an agent checkpoint or migration protocol |
| HTTP/1.1, HTTP/2 | General request-response | HTTPS requests; HTTP/2 multiplexing | A2A/MCP gateways, artifacts, registration | Application semantics and replay protection still needed |
| HTTP/3 / QUIC | Network transport | TLS-protected QUIC streams, connection mobility features | Mobile/WAN when supported by both endpoints | QUIC connection migration ≠ agent migration |
| gRPC | Typed RPC (usually HTTP/2) | Unary, server/client/bidirectional streams | Efficient internal control plane; A2A binding | No intrinsic agent checkpoint portability |
| WebSocket / WSS | Duplex channel | Messages over persistent connection | Progress, control channel, interactive agents | Reconnect must restore application state; not standard A2A binding by itself |
| SSE | Server → client events | One-way streamed event responses | Progress updates over HTTP | No guaranteed replay without application-level event IDs/storage |
| WebRTC DataChannel | Peer ↔ peer | SCTP/DTLS; ICE with possible STUN/TURN | Opt-in browser-to-edge/peer links | Peer discovery, NAT relay, consent and application schema required |

## Durable communication and event buses

| Protocol / system | Common use | Fit | Caution |
| --- | --- | --- | --- |
| MQTT 5 | Lightweight publish/subscribe between gateways and constrained devices | Remote telemetry, approved commands, offline-buffered flows | QoS 0/1/2 is not end-to-end exactly-once physical action; assess retained messages |
| AMQP 1.0 | Brokered interoperable messaging | Durable enterprise handoff commands via bridge | Broker delivery not identical to exactly-once tool effects |
| NATS Core / JetStream | Pub/sub, request/reply / persisted streams | Edge-cloud queue and retry coordination | JetStream deduplication windows, ack policy and consumer semantics need testing |
| Kafka | Durable partitioned event log | High-throughput tracking, replay, outbox | Kafka transactions do not atomically commit arbitrary outside actions |
| Redis Streams | Application stream/consumer groups | Small controlled deployments | Ack, redelivery and persistence configuration matter |
| CoAP | Compact REST-like constrained device protocol | Embedded read-only tool gateway | Gateway should mediate authentication and policy; no full agent runtime |
| DDS / RTPS (ROS 2) | Robot middleware pub/sub and services | Local robot perception, planning and skill invocation | Real-time safety remains device-local; ROS graph is not cross-vendor agent migration |
| OPC UA (client/server, PubSub) | Industrial interoperability | Approved factory / PLC gateway | Start read-only; safety and OT zoning enforce policy |

## Discovery, addressing and overlays

- **A2A Agent Card:** advertises capabilities/endpoints; authenticate the source and allowlist destination. A self-asserted capability is not a trust credential.
- **DNS/DNS-SD/mDNS:** service discovery on trusted LANs; mDNS is not a secure public agent registry.
- **Kubernetes Services/DNS:** locate service replicas; may change the process behind an endpoint without moving the logical task.
- **libp2p:** peer IDs, discovery and transports for opt-in decentralized overlays; does not define agent-task or execution semantics.
- **VPN / WireGuard / service mesh:** network reachability and encryption, not user authorization for a tool.
- **ICE/STUN/TURN:** help permitted peer connections work across NAT; relay does not make endpoint identity trustworthy.
- **SSH/SFTP / HTTPS object stores:** controlled distribution of packages, checkpoints, models and artifacts. Use hashes, signing and destination-bound credentials.
- **OCI registry:** distributes multi-architecture images and dependencies. Restarting an image elsewhere is copy, unless compatible state and fencing establish relocation.
- **Git:** source/version distribution, not a secure automatically running movement transport.

## Choosing among communication mechanisms

1. Prefer **A2A over authenticated HTTPS** for heterogeneous task delegation.
2. Prefer **MCP stdio** for local tools and properly secured **MCP Streamable HTTP** for remote tools.
3. Prefer **object storage + integrity digest** for large artifacts, models and checkpoint blobs rather than embedding blobs in messages.
4. Add a **durable queue** where peers are offline, slow or failure-prone; preserve stable operation IDs through bridges.
5. Prefer **VPN/overlay and mTLS** for infrastructure-level confidentiality and authenticated workload connections; apply authorization separately.
6. For a robotics system, use a **companion computer/gateway** with ROS 2/DDS or vendor-supported interfaces and safety constraints; never let a general LLM directly replace a safety controller.
7. Treat MQTT/CoAP/BLE as **device communication**, not the full-agent migration protocol.

## Negotiation and compatibility fields (proposal)

Before movement, agree on: operation kind; envelope version; task/artifact schemas; runtime and checkpoint format; CPU ISA/OS where software is deployed; transport and encoding; max payload size; compression; supported authentication; data locality; expected latency; accepted side effects; cancellation; TTL; idempotency; and telemetry/redaction policy. Unknown critical capability or security property = reject.

## Important traps

- HTTP/3 **connection migration** follows a network path change; it does *not* transfer execution to another machine.
- A2A **task handoff** may involve a different agent with different identity/semantics.
- MCP tool discovery does not grant permission to use a tool.
- A Kafka/NATS/MQTT acknowledgment is not proof that an external side effect happened precisely once.
- A container image is not an agent's memory.
- TCP, TLS, WebSocket, QUIC, MQTT and ROS 2 can all be on the path while **none** independently supply cross-framework checkpoint portability.

See [primary sources](primary-sources.md), [networks](network-topologies.md), [contract](handoff-and-relocation-contract.md).