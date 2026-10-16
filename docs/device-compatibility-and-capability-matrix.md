# Device targets and capability requirements for Agent Movement

**Status:** Research taxonomy / proposed engineering matrix, not supported-product claims. Reviewed 2026-10-15.  
**Machine-readable inventory:** [134 device classes in CSV](../data/device-targets.csv). Entries are classes, not exhaustive SKUs; new products should be added as data rows and verified with per-device test evidence. No device-specific agent deployment in this repository has yet been demonstrated.

## Terms and operations

- **Remote use (R):** Origin stays in place and requests an approved capability from a device or gateway. This is *not movement*.
- **Partial deployment (P):** Install a narrowly scoped tool proxy, perception module, policy filter, planner or inference service; it has its own lifecycle.
- **Definition copy (C):** Deploy compatible code/configuration to another host and create a **different instance identity**; memory and credentials do not automatically transfer.
- **Checkpoint relocation (M):** Save an application-level, approved checkpoint; fence old executor; resume same logical task on compatible destination with a new runtime execution ID. Requires a durable lease/reconciliation protocol.
- **Live migration (L):** Move volatile OS/process execution with minimal interruption. Specialized environment-dependent technique, not generally portable between heterogeneous agent systems.
- **Robot arm/part transfer:** Move **software controlling an end effector, skill, or perception module** or send commands to a robot. Hardware doesn't teleport. Embedded real-time safety controller retains authority. A modular robot may physically dock a tool, but that is a separate mechanical process.

## Normalized host profiles (NOT migration levels)

| Host profile | Suitable target | Typical resource envelope (approximate design heuristics, not minimum specifications) | Practical outcomes |
|---|---|---|---|
| H0: peripheral/tool only | Lock, PLC, sensor, actuator, safety-critical control device | No programmable agent resources exposed | Remote capability (R) through owner-approved API only |
| H1: tiny embedded module | MCU, sensor board, constrained RTOS or coprocessor | Tens of KB–few MB RAM; flash/firmware dependent | Signed rules/TinyML/sensor prefilter (P), generally not LLM orchestration |
| H2: thin client/proxy | Browser tab, watch, TV, router, proprietary hub, restricted embedded host | Often tens–hundreds of MB *when permitted* | R or P; local agent often limited by API/background policy |
| H3: app-class host | Phone/tablet, workstation, Raspberry Pi-class board, onboard robot computer | Often hundreds of MB–several GB usable memory | C; selective P; application checkpoint M may be feasible, not assumed |
| H4: durable compute host | Linux server, x86/ARM SBC with sufficient resources, Jetson, capable edge server | Usually ~1+ GiB for light API-backed runtime and more for tools; local LLM requires model-dependent RAM/VRAM | R/P/C; M for compatible versioned runtimes with engineered state/fencing; not automatic L |

**H designation in the CSV is a candidate maximum hosting profile, not a ranking of device safety, automation permission, or observed compatibility.** In particular, iOS and Android app restrictions, product vendor policies, battery, model architecture and local inference needs may lower feasibility. Serverless H3 does not imply a persistent daemon.

## Platform families

| Family | Examples | Most realistic operation(s) | Notes |
|---|---|---|---|
| Servers, VMs, Kubernetes, HPC, cloud | Linux servers; ARM/x86 nodes; cloud containers | C; M on compatible checkpoint runtime; P; R | OCI images do not carry agent memory or identities automatically; persistent state and lease required |
| Desktop & laptop | Windows/macOS/Linux PCs | C; P; M with verified compatible runtime | Different OS and CPU architectures require packaging and compatibility check |
| Smartphones & tablets | Android; iOS/iPadOS | C or P inside authorized apps; R | Foreground/background limits, app signing, entitlements; not unrestricted autonomous self-installation |
| Browser/extension/PWA | Web apps, WebAssembly clients | P; R, limited C | Tabs may suspend; origin-permission sandbox; no arbitrary host filesystem |
| Wearables/AR/XR | Watches, glasses, headsets | P or app-scoped C where vendor permits | Sensor privacy, heat, battery, limited execution |
| Single-board and edge AI | Raspberry Pi, Jetson, x86 mini PCs, industrial edge gateways | C; P; M on compatible systems | ARM64 versus x86 images and models; device drivers matter |
| Microcontrollers and RTOS | ESP32, STM32, Zephyr/FreeRTOS | P for deterministic rules, tiny ML or telemetry | No universal Python/LLM agent migration; OTA must be signed and managed |
| Consumer IoT | Smart speaker, TV, light, camera, thermostat, lock | R; select P on open firmware | Cloud API use is not software movement; locks/heaters have physical risks |
| Network/storage | Routers, switches, firewalls, NAS, modem | R; P/C on supported open Linux/NAS | Separate management plane from production forwarding; no unapproved privilege |
| Industrial and scientific | PLC, SCADA, CNC, machine vision, lab devices | R; analytics P on IPC/gateway | OT change control; real-time/PLC loops and physical safety remain separate |
| Robotics | Robot arm, cobot, humanoid, AMR, quadruped, ROV | C or P on companion computer; R to actuators | ROS 2/MoveIt/vendor SDK; validated low-level control, E-stop and geofencing remain authoritative |
| Mobility/aerospace | Drones, cars, trains, aircraft, satellites | R; some mission component P or companion C | Never equate remote mission planning with permission to operate safety-critical flight/drive control |
| Simulation and digital twins | Robot simulator, game engine, HIL bench | C/M; P/R | Safest initial place to test before physical equipment |

## Six independent capability dimensions

Never reduce device support to a single yes/no boolean. Record:
1. **Hosting:** remote-only, restricted app, signed firmware, OS process, container, VM.
2. **Compute:** ISA (x86-64, ARM64, ARMv7, RISC-V, MCU), CPU/NPU/GPU, RAM, flash/storage, power envelope, OS/ABI.
3. **State:** stateless request, resumable task context, compatible app checkpoint, source-of-truth external state, mutable artifacts, ephemeral tool state.
4. **Connectivity:** local IPC, authenticated internet, LAN/VPN, intermittent, offline signed transfer; time and bandwidth.
5. **Authority/safety:** ownership consent, workload identity, artifact signing and attestation (workload, supply-chain or hardware), action allowlists, human approval, safety-critical separation, revocation.
6. **Observability/assurance:** platform test status, audit trace, fencing, retry reconciliation, resource budgets, physical fail-safe, rollback.

### Recommended device declaration

```json
{
  "target_id": "example-edge-001",
  "platform": {"os": "linux", "arch": "arm64", "abi": "glibc", "runtime": "oci"},
  "resources": {"ram_available_mb": 2048, "storage_available_mb": 8192, "accelerators": []},
  "hosting": ["remote_tool", "partial_module", "definition_copy", "checkpoint_resume"],
  "connectivity": {"mode": "intermittent", "inbound_reachable": false},
  "interfaces": [{"name": "sensor.read", "protocol": "mcp", "risk": "read_only"}],
  "policy": {"owner_enrollment": true, "signed_artifacts_required": true,
             "physical_actions": "deny", "delegated_auth": "short_lived"},
  "compatibility": {"checkpoint_schema": "draft-0.1", "runtime_version": "pinned",
                    "tested": false},
  "state": "candidate_unverified"
}
```

This is illustrative schema content, not an implemented discovery standard; advertised properties need authentication and test evidence.

## Agent software components that can move independently

| Component | Typical host | Portability requirement | Caution |
|---|---|---|---|
| Prompt/config/role definition | Almost any agent-capable host | Versioned specification; destination model capability | Copy is a *new instance*, not continued identity |
| Task intent/plan | Any receiver with interpretable schema | Sanitized task envelope, authorization | Delegation, not a move |
| Approved conversation summary/memory | Host with storage and permission | Explicit data classification, export permissions, lineage | No implicit copying of private transcripts or secrets |
| Workflow checkpoint | Compatible process/runtime | Versioned serializable state, durable store, fencing epoch | External actions require reconciliation |
| Retrieval index/knowledge subset | Sufficient disk/RAM | Format, license, provenance, retention | Access-control and data residency |
| Tool adapter (MCP, SDK) | OS/app or device gateway | Supported protocol and API | Tool availability differs from actual authority |
| Vision/speech/inference model | GPU/NPU/CPU device with capacity | Model size, quantization, licenses, driver | Local processing only if resources permit |
| Planner agent | Application-capable OS/edge host | Model inference local or authenticated remote | No unrestricted physical authority |
| Robot arm skill | Robot companion computer | Robot model, kinematics, safety validated trajectory/controller | Never bypass protective stop or hard safety limits |
| Low-level motor/flight controller | Certified dedicated controller | Vendor-controlled firmware and safety assessment | **Do not** treat as freely migratable agent component |
| Audit/trace identity | Durable trusted infrastructure | Trace IDs, signed lineage, pseudonymous target IDs | Avoid exporting source credentials |

## Compatibility decision procedure

1. Confirm owner enrollment and requested *operation* R/P/C/M/L; reject implicit self-spreading or unknown destinations.
2. Read authenticated host capability declaration and compare architecture, OS/ABI, image/SDK/driver compatibility, network and hardware interfaces.
3. Check resources for **the actual packaged agent**, including model weights, tool processes and peak memory; profile instead of assuming a fixed minimum.
4. Apply data-classification, geographic, license, retention and user-consent checks; issue separate short-lived target permissions.
5. For copy, install a signed artifact and issue new instance/run IDs; do not blindly duplicate secrets or browser sessions.
6. For relocation, checkpoint only at safe boundary, verify integrity/schema, acquire exclusive task lease, fence origin, and reconcile ambiguous effects before resume.
7. For partial deployment, expose explicitly scoped interfaces; device-local safety controller vetoes dangerous actions and maintains safe fallback.
8. Record checks, placement, source/destination identity, result, and revocation; require human approval for consequential actions.
9. If the exact operation is unsupported, fall back *explicitly* from M to new delegation or R, **never falsely label it migration**.

### Focused proof-of-concept matrix

| Priority | Target | Demonstration | Pass criteria |
|---|---|---|---|
| P0 | Two Linux containers/VMs | C and same-runtime M of synthetic task | Independent IDs on copy; exactly one fenced task owner on move; restart + replay tests |
| P0 | Linux laptop ↔ cloud VM | R, C and app checkpoint relocation | Correct permissions, integrity, revocation and recovery |
| P1 | Raspberry Pi 64-bit ↔ Linux x86 cloud | Multi-arch C and protocol handoff | Correct per-arch artifacts, explicit checkpoint compatibility |
| P1 | Android + iOS companion app | R and scoped P | No unsupported background assumptions; user-visible consent |
| P1 | Raspberry Pi/Jetson ↔ simulated robot arm | M of **high-level planning task** and P of skill | Simulated hard safety boundary, E-stop, actuator veto; no direct unsafe motor commands |
| P2 | ESP32/Zephyr simulated node | Signed P telemetry/perception module | Signature, bounds checks, rollback, stable operation offline |
| P2 | OPC UA simulator + edge gateway | Read-only R, analytics P | No writes across OT boundary; audit |
| P3 | Physical approved robot testbed | High-level supervised R/P | Owner signoff, hardware interlock tests, recovery after network loss |

## Critical open questions

- Is the movable unit a full package, a policy-scoped *task*, a memory snapshot, a workflow checkpoint or a robotics skill?
- Can a capability be used remotely without transferring the agent at all?
- Which execution effects must be fenced when transitioning between two computers, and which can be safely replayed?
- Does recipient compute meet verified model/runtime benchmarks rather than guessed memory cutoffs?
- How are movement, copying, module installation and tool-control authorities separately granted and revoked?
- How do software identity, task continuity, child lineage and physical-device ownership intersect?
- What is the safe fallback if connectivity is lost mid-transfer or a robot loses cloud access?
- How do we publicly report *verified* versus *candidate* platform support?

## Sources (primary documentation; do not infer product certification)

- [A2A protocol specification](https://a2a-protocol.org/v1.0.0/specification/) — interoperability and task delegation, **not arbitrary migration**.
- [MCP specification](https://modelcontextprotocol.io/specification/2026-07-28) — tools/data protocol, **not generic host installation**.
- [Docker multi-platform images](https://docs.docker.com/build/building/multi-platform/) — package targets for different CPU architectures.
- [Kubernetes architecture](https://kubernetes.io/docs/concepts/architecture/) — workload scheduling and nodes.
- [Android background tasks](https://developer.android.com/develop/background-work/background-tasks) — platform background-execution constraints.
- [Apple BackgroundTasks](https://developer.apple.com/documentation/backgroundtasks) — restricted app background tasks.
- [micro-ROS](https://micro.ros.org/) — ROS 2 connectivity for embedded microcontrollers.
- [ROS 2 documentation](https://docs.ros.org/en/jazzy/) — distributed robotics software.
- [MoveIt 2](https://moveit.ai/) — robotic manipulation planning, not safety certification.
- [MAVLink](https://mavlink.io/en/) — drone and vehicle messaging.
- [CRIU](https://criu.org/Main_Page) — Linux userspace checkpoint/restore; subject to kernel/runtime constraints.
- [NIST SP 800-82 Rev. 3](https://csrc.nist.gov/pubs/sp/800/82/r3/final) — OT security guidance.
- [Zephyr RTOS](https://docs.zephyrproject.org/latest/) — embedded RTOS/boards.

**Implementation disclosure:** This repository does not currently contain code validating these compatibility hypotheses. The CSV's 134 target classes are candidate research entries, not 134 working integrations.
