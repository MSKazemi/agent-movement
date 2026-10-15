# Language and SDK strategy (public implementation-strategy proposal)

**Date:** 2026-10-15  
**Status:** Proposal; recommendation only, not an approved implementation commitment. The Python-first part has since been prototyped (see [Implementation status](#implementation-status-2026-10-16)).  
**Scope:** Agent Movement's research-to-prototype transition, including cross-runtime and cross-device targets.

## Recommendation

**Choose Python for the first executable reference implementation, while designing a language-neutral protocol contract from day one.** Then add **TypeScript** as the first independent consumer or adapter. Introduce **Rust** only if a real deployment requirement justifies a small, resource-efficient or sandbox-oriented native component; use **Go** when a Kubernetes/cloud controller is needed. The best *single starting language* is Python; there is no single best language for all proposed targets.

When this proposal was written (2026-10-15), the [README](../README.md) described a research-stage effort without production movement code, the [roadmap](roadmap.md) prioritized an A2A delegation demo, and the only executable tooling was [Python corpus tooling](../tools/news_corpus.py). The recommendation does **not** mean Python is a universal runtime for phones, embedded firmware, or browsers.

## Implementation status (2026-10-16)

The Python-first recommendation now exists as an **experimental, research-stage** package, [`src/agent_movement`](../src/agent_movement/). It runs synthetic local experiments only and is not production software:

- **Core (Python 3.11+, standard library only):** strict synthetic handoff envelope, SQLite audit and receipt deduplication, epoch-fenced effect gateway and a loopback-only HTTP receiver ([local implementation](local-implementation.md)); the MobilityBench smoke suite and v0.1 harness ([MobilityBench v0.1](mobilitybench-v0.1.md)); HS256 peer authentication ([peer authentication](peer-authentication.md)).
- **Optional extras**, each installed with `pip install -e '.[<extra>]'`: `a2a` (official `a2a-sdk` adapter, [A2A adapter](a2a-adapter.md)), `ed25519` (asymmetric peer keys), `relocation` (pinned LangGraph checkpoint relocation, [checkpoint relocation](checkpoint-relocation.md)) and `signing` (Ed25519 [movement receipts](movement-receipts.md)).

Still not implemented from this proposal: the language-neutral `spec/` JSON Schema, a TypeScript second implementation, and any Rust or Go component. The A2A adapter lives in `src/agent_movement/a2a_*.py`, not in a separate `adapters/a2a/` tree.

## Rationale and trade-offs

| Language | Best initial responsibilities | Strengths for this project | Reasons not to make it the only language |
| --- | --- | --- | --- |
| **Python (first)** | Reference movement SDK, envelope validation, A2A bridge, policy tests, checkpoint/retry experiments, evaluation harness | Existing repo code; mature AI/workflow ecosystem; official A2A and MCP SDKs; quick experimentation | Interpreter/runtime packaging; resource constraints; not a native browser or most embedded-device target |
| **TypeScript (second)** | Cross-language A2A endpoint, Node.js SDK, UI or AG-UI integration, browser-facing client | Official A2A JavaScript SDK and MCP TypeScript SDK; strong web/Node ecosystem; proves wire interoperability | Browser security and sandbox limitations; do not assume a browser can host a free-standing privileged agent |
| **Rust (conditional)** | Small native transfer worker, local security boundary, selected edge/desktop/embedded targets, optional WebAssembly module | Compile-time memory-safety guarantees without a garbage collector; native deployment choices | More implementation cost and steeper onboarding; device hardware and OS permissions still govern what can run |
| **Go (conditional)** | Cloud coordinator, Kubernetes operator/controller, service-to-service transport | Suits cloud-native services and operational tooling; official A2A and MCP SDKs | Less direct leverage of research/AI Python libraries; do not prematurely split the codebase |
| **Kotlin/Java, Swift, C/C++ (later adapters)** | Android, Apple platforms, or firmware/robotics integration as needed | Match platform-native APIs and existing stacks | No arbitrary agent state can be exported or run merely because a language targets the device |

These are **architecture recommendations**, not claims that every capability is available or that all official SDKs have identical feature coverage. Verify SDK version and support for the specific transport, authentication, streaming, and data model before selecting an integration.

## Separate the protocol from the SDK

1. **Contract-first:** maintain a versioned JSON Schema for the public task/handoff envelope and example payloads under `spec/`. Derive or validate language-specific models against that contract. Specify required fields, encoding, size limits, failure states, forward/backward compatibility, and canonicalization rules only when necessary and tested.
2. **Transport adapters:** use existing [A2A](https://a2a-protocol.org/latest/sdk/) semantics for independent agent-to-agent delegation. Use [MCP](https://modelcontextprotocol.io/docs/sdk) for tool and resource integration, not as an invented agent-migration transport. Do not claim that either protocol supports portable live process checkpoints.
3. **Authorization and isolation:** enforce destination allowlisting, bounded delegated permissions, human approval for risky side effects, secret-free envelopes, audit correlation, idempotency, and unknown/reconciliation states as described in [security-and-trust.md](security-and-trust.md).
4. **Runtime-specific checkpoint adapters:** start with one runtime and explicitly describe what state can be serialized and resumed. Cross-framework re-execution, delegation, and actual checkpoint relocation remain distinct operations.
5. **Interoperability tests:** run the same valid and invalid fixtures against independent implementations in Python and TypeScript; compare canonical task IDs, artifacts, state transitions, error handling, redaction, and retry behavior. Pin protocol and SDK versions in CI.

**No portable arbitrary model internal state:** Python objects, JavaScript closures, Rust memory, private model reasoning, process stacks, credentials and open browser sessions are not portable merely because the envelope is JSON.

## Language by destination/target environment

| Target | Suggested code language | Realistic initial operation | Special condition |
| --- | --- | --- | --- |
| Laptop / developer workstation | Python, with TS/Rust optional | Local delegation, checkpoint/restart of a supported workflow | Explicit file/tool permissions and process isolation |
| Linux/cloud VM / container | Python for agent; Go if a cloud controller is required | Restartable task worker, remote delegation | Network trust, durable storage, quotas |
| Web application / browser tab | TypeScript | UI, human approval, A2A client or backend-mediated delegation | Do not assume unrestricted filesystem, persistent process, or credential export |
| Android phone | Kotlin for native host, optional embedded Python/Rust only if supported | Permission-controlled host app or remote delegation | OS sandbox, energy/background restrictions |
| iPhone/iPad/macOS | Swift for native host, Python/Rust where deployable | Host-mediated task UI, device-approved capability access | Platform policies and entitlement constraints |
| IoT / constrained edge | Rust or C/C++ where feasible | Task endpoint or limited capability client | CPU, RAM, firmware update model, OS/network availability |
| Robot / industrial controller | C++/Python/ROS stack as applicable | Expose approved robot capabilities to an agent | Safety interlocks, physical authorization, real-time separation |
| Serverless worker | Provider-supported Python/TypeScript/Go | Short stateless delegation steps | Execution duration and persistent state limits |

**Device compatibility is capability-based, not language-based.** The [device target catalog](../data/device-targets.csv) enumerates candidate classes, not verified deployment compatibility. Any target must independently satisfy runtime availability, supported architecture, lifecycle management, policy enforcement, identity, network reachability, persistence and applicable platform rules. Devices without a trusted agent runtime may still offer remote tools, but that is not agent migration.

## Implementation order and acceptance criteria

### Phase 1 — Python, no remote production execution

- Create `spec/movement-envelope.schema.json` and positive/negative synthetic fixtures from the existing draft [envelope](how-it-works.md).
- Create a typed `agent_movement` Python package (recommended Python 3.11+ if compatible with the chosen pinned SDK) with validation, immutable movement IDs, policy gating and a local A2A adapter. *(Prototyped; see Implementation status.)*
- Demonstrate a **synthetic, non-destructive** task handoff between two isolated test agents with an artifact return and correlated audit trace.
- Pass tests for malformed versions, denied destinations, missing approval, duplicate messages, revoked grants, crashes and unknown external status.

### Phase 2 — TypeScript interoperability

- Build a minimal TypeScript client or receiver using the *same* schema and recorded fixtures.
- Run Python-to-TypeScript and TypeScript-to-Python integration tests; publish a compatibility table with precise protocol/SDK version pins.
- Keep browser-facing UI separate from privileged agent execution.

### Phase 3 — add a systems language only for a measured need

- Compare Python and a Rust or Go prototype for actual target requirements: memory, cold start, dispatch latency, packaging, sandbox policy, supported architectures and developer effort.
- Adopt Rust for a verified constrained/native-worker need, or Go for a verified cloud/controller need. Do not rewrite the research/agent logic without evidence.

## Proposed repository layout (partly implemented)

Only `src/agent_movement/`, `tests/` and `docs/` exist today; the other directories are still proposals.

```text
spec/                         # Language-independent JSON Schema and examples
src/agent_movement/           # Python reference implementation
tests/                        # Unit, contract, security and fault-injection tests
adapters/a2a/                 # Explicit A2A transport integration
sdk/typescript/               # Later second-language implementation
runtimes/rust/                # Optional, only if justified
deploy/                       # Optional cloud-native tooling
docs/                         # Public documentation and research
```

Do not create the placeholder directories until they contain actual maintained source or tests.

## Decision triggers to revisit

Revisit the language choice when (a) Python cannot meet a measured latency/resource/security target, (b) the primary audience or destination is browser/Node, (c) the product is fundamentally a Kubernetes operator, (d) the project targets a constrained device that cannot run Python, or (e) the supported official SDK matrix changes. Record benchmark data and platform constraints rather than language popularity.

## Sources (reviewed 2026-10-15)

- [A2A official SDK overview](https://a2a-protocol.org/latest/sdk/) — Python, JavaScript, Go, Rust and other language SDKs; consult each SDK for actual supported capabilities.
- [Official A2A JavaScript SDK](https://github.com/a2aproject/a2a-js) and [A2A Python SDK](https://github.com/a2aproject/a2a-python).
- [MCP SDK directory](https://modelcontextprotocol.io/docs/sdk), [MCP Python SDK](https://py.sdk.modelcontextprotocol.io/) and [MCP TypeScript SDK v2](https://ts.sdk.modelcontextprotocol.io/v2/).
- [MCP 2026-07-28 release and SDK compatibility](https://blog.modelcontextprotocol.io/posts/2026-07-28/).
- [A2A official samples](https://github.com/a2aproject/a2a-samples) for multi-language agent handoff examples.
- Existing repository docs: [roadmap](roadmap.md), [security](security-and-trust.md), [device inventory](device-compatibility-and-capability-matrix.md).

**Outcome recommended for owner review:** Python-first executable reference, language-neutral envelope, TypeScript second, Rust/Go only after target-specific measurements. This proposal does not assert that an agent can copy or migrate onto every device in the catalog.
