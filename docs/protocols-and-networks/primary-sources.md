# Primary sources, status and research cautions

**Reviewed:** 2026-10-15. These citations document components, **not** an existing universal movement protocol or verified support in this repository. Exact release and version compatibility should be rechecked before code.

## Agent, tools and UI

- [A2A v1.0.1 specification](https://a2a-protocol.org/v1.0.1/specification/) — agent task, message, artifact and standard bindings; compare against deployed SDK version.
- [A2A source repository](https://github.com/a2aproject/A2A) — implementations and design notes.
- [MCP specification 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28) — tool and context interoperability.
- [MCP transport section](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports) — stdio and Streamable HTTP; protocol revisions change details.
- [AG-UI repository](https://github.com/ag-ui-protocol/ag-ui) — frontend/agent event interchange. SDK line `@ag-ui/core` 1.0.x: 1.0.0 published 2026-09-17, `dist-tags.latest` 1.0.2 published 2026-10-05 ([npm registry](https://registry.npmjs.org/@ag-ui/core), checked 2026-10-16). The repository uses date-tagged GitHub releases rather than version tags; [release/2026-09-17](https://github.com/ag-ui-protocol/ag-ui/releases/tag/release/2026-09-17) lists `@ag-ui/core` 1.0.0. These are package versions; no separately versioned AG-UI protocol specification was found.
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence) — framework-scoped checkpoint facilities.
- [Temporal workflow execution](https://docs.temporal.io/workflow-execution) — durable workflow execution and recovery semantics.

## IP, internet transport and service discovery

- [RFC 9293 TCP](https://www.rfc-editor.org/rfc/rfc9293), [RFC 8446 TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446)
- [RFC 9113 HTTP/2](https://www.rfc-editor.org/rfc/rfc9113), [RFC 9114 HTTP/3](https://www.rfc-editor.org/rfc/rfc9114), [RFC 9000 QUIC](https://www.rfc-editor.org/rfc/rfc9000)
- [RFC 6455 WebSocket](https://www.rfc-editor.org/rfc/rfc6455), [HTML EventSource/SSE](https://html.spec.whatwg.org/multipage/server-sent-events.html)
- [gRPC core concepts](https://grpc.io/docs/what-is-grpc/core-concepts/)
- [RFC 8831 WebRTC DataChannels](https://www.rfc-editor.org/rfc/rfc8831), [RFC 8445 ICE](https://www.rfc-editor.org/rfc/rfc8445), [RFC 8656 TURN](https://www.rfc-editor.org/rfc/rfc8656)
- [RFC 6762 mDNS](https://www.rfc-editor.org/rfc/rfc6762), [RFC 6763 DNS-SD](https://www.rfc-editor.org/rfc/rfc6763)
- [libp2p documentation](https://libp2p.io/docs/), [WireGuard overview](https://www.wireguard.com/)

## Messaging, constrained devices and robotics

- [OASIS MQTT 5.0 standard](https://docs.oasis-open.org/mqtt/mqtt/v5.0/mqtt-v5.0.html)
- [OASIS AMQP 1.0](https://docs.oasis-open.org/amqp/core/v1.0/os/amqp-core-overview-v1.0-os.html)
- [NATS JetStream](https://docs.nats.io/nats-concepts/jetstream)
- [Apache Kafka documentation](https://kafka.apache.org/documentation/)
- [RFC 7252 CoAP](https://www.rfc-editor.org/rfc/rfc7252)
- [ROS 2 middleware concepts](https://docs.ros.org/en/rolling/Concepts/Intermediate/About-Different-Middleware-Vendors.html), [ROS 2 QoS](https://docs.ros.org/en/rolling/Concepts/Intermediate/About-Quality-of-Service-Settings.html)
- [OPC Foundation](https://opcfoundation.org/about/opc-technologies/opc-ua/)
- [Thread Group](https://www.threadgroup.org/What-is-Thread)
- [Bluetooth LE](https://www.bluetooth.com/learn-about-bluetooth/tech-overview/)

## Package, identity, audit and orchestration

- [OCI image specification](https://specs.opencontainers.org/image-spec/)
- [Kubernetes Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/) and [Services](https://kubernetes.io/docs/concepts/services-networking/service/)
- [RFC 8693 OAuth token exchange](https://www.rfc-editor.org/rfc/rfc8693)
- [RFC 8705 OAuth mTLS](https://www.rfc-editor.org/rfc/rfc8705), [RFC 9449 DPoP](https://www.rfc-editor.org/rfc/rfc9449)
- [SPIFFE/SPIRE concepts](https://spiffe.io/docs/latest/spire-about/spire-concepts/)
- [Open Policy Agent](https://www.openpolicyagent.org/docs)
- [OpenTelemetry GenAI semantic conventions](https://github.com/open-telemetry/semantic-conventions-genai) (moved out of opentelemetry.io; status Development)

## Evidence grading

- **Standard behavior:** Supported by linked normative or maintainer material, subject to specified versions and deployment features.
- **Integration proposal:** Agent-movement envelope, exclusive task ownership, source-to-destination bridge, device class choice.
- **Not established:** universal transfer of hidden model state, portable live runtime state across frameworks, generic exactly-once external side effects, or real device/network interoperability.

## Known uncertainty

Web documentation and implementations may diverge; not every transport is supported by every SDK, proxy, device or deployment. Versions of A2A and MCP must be negotiated/pinned. Some links refer to continuously updated project pages. Before formal interoperability claims: record exact source revision, conformance tests and reproducible packet traces (with secrets removed).