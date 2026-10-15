# Networks, paths and topologies for agent movement

**Status:** engineering options, not supported deployments.

## Connectivity matrix

| Network / environment | Typical links | Endpoint constraints | Suitable movement pattern | Risk/constraint |
| --- | --- | --- | --- | --- |
| Same process / host | Function, Unix socket, stdio, loopback TCP | Strong local OS boundary, shared host | R / D / P | Tool privilege isolation |
| LAN / campus | Ethernet, Wi-Fi, IPv4/IPv6 | Internal firewalls, enterprise policy | D, C, compatible M | LAN trust cannot be assumed |
| Data center / cloud VPC | Private IP, service mesh, Kubernetes | Service identities and egress policy | D/C/M | Replica vs task identity |
| Hybrid / multicloud | WAN, private link, VPN | Different IAM, residency and provider policy | D; carefully M | Credential audience, data governance |
| Public internet | TLS over TCP/QUIC | NAT, firewalls, reachability | D over authenticated HTTPS | Discover only approved hosts |
| Mobile WAN | LTE/5G + Wi-Fi roaming | NAT, changing IP, battery/background | R/D with resumable requests | QUIC path migration ≠ agent relocation |
| Browser → cloud | HTTPS, WSS, WebRTC | Origin sandbox, limited filesystem, sleep | R/D/P | Explicit user consent, no silent installation |
| Edge industrial | Ethernet, fieldbus gateway, Wi-Fi | OT boundaries, device certification | R/P; controlled D | Safety and network zoning |
| Robot / drone LAN | Wi-Fi, Ethernet, DDS/RTPS | Embedded control and hard real-time limits | R/P/D at planning layer | Autonomous execution not a safety exemption |
| IoT constrained mesh | Thread/802.15.4, BLE, 6LoWPAN | Small MTU, CPU/RAM, intermittent | R/P via gateway | Only authorized firmware/modules |
| Long-range low-bit-rate | LoRaWAN, LPWAN | Tiny packets, duty cycles, latency | Telemetry, task signals via gateway | Not suitable for large checkpoints or model weights |
| Satellite / remote field | Satellite IP, delayed gateway | Expensive bandwidth, outage, high RTT | Store-and-forward D/P/C | No assumption of timely remote control |
| Disconnected / air-gapped | Removable media, trusted local link | No simultaneous connectivity | Signed offline bundle D/C/P | Anti-replay and origin-fencing for M |
| P2P overlay | WebRTC, libp2p, VPN overlay | NAT traversal, relays, peer permissions | Opt-in D/P | Consent, trust, privacy, relay governance |

**Link technologies are not agent-movement protocols.** Ethernet/Wi-Fi/5G/BLE carry data; a separate application contract defines what moved.

## Reference topologies

### 1. Laptop ↔ cloud specialist

~~~mermaid
flowchart LR
  U[User approval] --> L[Laptop agent]
  L -->|A2A HTTPS| C[Cloud agent]
  L -->|Scoped HTTPS artifact ref| S[Object store]
  C -->|Fetch approved input| S
  C -->|A2A result| L
~~~

Use public/synthetic files initially. OIDC/OAuth or independently provisioned workload identities must be audience-scoped; never send laptop keys.

### 2. Edge gateway ↔ controlled device

~~~mermaid
flowchart LR
  A[Agent] -->|MCP / HTTPS| G[Authorized gateway]
  G -->|CoAP / MQTT / OPC UA / ROS 2| D[Device interface]
  D --> X[Independent safety controls]
~~~

The gateway validates authorization, command type, resource bounds and owner enrollment. MCU firmware must be installed only with owner-managed signed update facilities. Read-only mode is safest for first experiments.

### 3. Durable cloud relocation

~~~mermaid
flowchart LR
  O[Old worker] -->|Checkpoint| S[(Durable store)]
  K[Coordinator] -->|Fence old lease| O
  K -->|Assign epoch N+1| N[New worker]
  S -->|Compatible snapshot| N
  N -->|Result and trace| K
~~~

Use one logical task ID with distinct execution/instance IDs. If old worker cannot be fenced, status is **unknown**, not safely migrated. The new worker must not repeat irreversible effects without reconciliation.

### 4. Intermittent / offline store-and-forward

~~~mermaid
flowchart LR
  A[Origin] --> B[Signed encrypted bundle]
  B --> Q[Outbox / physical transfer / delayed gateway]
  Q -->|Verify allowlist and expiry| C[Destination]
  C --> R[Receipt and result queue]
  R --> A
~~~

Offline copy/delegation can succeed after delayed transfer. Exclusive live task relocation requires a defensible fencing mechanism and may be refused during partitions.

## Network selection checklist

- Reachable outbound endpoint? Need inbound connection? Prefer outbound client requests through firewalls; avoid unauthorized inbound exposure.
- Payload bytes, peak bandwidth, latency, disconnection tolerance, MTU and metered cost measured?
- TLS/mTLS, VPN, identity verification, authorized endpoint allowlist, certificate rotation in place?
- User, tenant, jurisdiction, data residency and retention constraints satisfied?
- Delivery durability and backpressure necessary? Choose appropriate broker and queue settings.
- Multi-hop relays trusted and documented? Avoid open proxies and uncontrolled peer discovery.
- Can the destination execute or only expose a tool? Mark R, P, C, D, M accurately.
- Does device have emergency-stop / local failsafe? Never bridge untrusted instructions into direct actuator control.

See [protocol catalog](protocol-catalog.md) and [security](security-reliability-and-observability.md).