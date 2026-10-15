# Agent Movement

**Research-stage project: portable, interoperable, and governable AI-agent work across runtimes and environments.**

**Status:** Research-led, with an **experimental, localhost-only task-handoff and simulated-effect fencing prototype**. This is **not A2A interoperability, production security, checkpoint migration, or deployment to other devices**. Last reviewed: 2026-10-15.

## What does "agent movement" mean?

*Agent Movement* is the **proposed name and working definition for this project**, not a recognized universal standard. We use it to study how an AI-agent task or execution can move between agents, frameworks, models, machines, and organizations **without losing relevant context, accountability, or safety controls**.

Four distinct operations must not be conflated:

1. **Delegation / handoff:** Agent A asks Agent B to perform a task. Agent A need not expose or migrate its internals. A2A addresses this interface.
2. **Portable task context:** Transfer an explicit, policy-checked package of goals, inputs, artifact references, and resumable checkpoints.
3. **Runtime relocation:** Stop at a safe boundary and resume compatible execution elsewhere, with durable workflow state and idempotency controls. This is substantially harder than delegation.
4. **Cross-framework migration:** Reconstruct a workflow on a different runtime using an adapter and a portable representation, with explicitly documented loss of features.

**Not claimed:** Live process migration or lossless transfer of arbitrary agent hidden state, model internals, credentials, or in-flight side effects.

## Why this matters

A useful agent might start on a laptop, delegate to a cloud agent, use tools in another organization, pause for approval, and resume after failure. Today the building blocks span multiple layers:

| Layer | Relevant technologies | What they solve | What they do **not** solve |
| --- | --- | --- | --- |
| Agent-to-agent | [A2A](https://a2a-protocol.org/v1.0.0/specification/) | Discovery, messaging, tasks, artifacts, streaming | Generic checkpoint migration |
| Agent-to-tools/data | [MCP, spec 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28) | Structured access to external capabilities | Agent-to-agent execution transfer |
| Agent-to-user | [AG-UI](https://github.com/ag-ui-protocol/ag-ui) | Agent/frontend events, state, interaction | Migration between runtimes |
| Orchestration and recovery | [LangGraph](https://docs.langchain.com/oss/python/langgraph/persistence), [Temporal](https://docs.temporal.io/workflow-execution) | Checkpoints, durable execution and recovery | Automatic semantic compatibility across all frameworks |
| Deployments | [OCI](https://specs.opencontainers.org/image-spec/), [Kubernetes](https://kubernetes.io/docs/concepts/workloads/controllers/job/) | Portable packaging and workload scheduling | App-level state/identity migration |
| Trust, policy and audit | [OAuth token exchange](https://www.rfc-editor.org/rfc/rfc8693), [SPIFFE](https://spiffe.io/docs/latest/spire-about/spire-concepts/), [OPA](https://www.openpolicyagent.org/docs), [OpenTelemetry](https://github.com/open-telemetry/semantic-conventions-genai) | Delegated access patterns, workload identity, policy and telemetry | An end-to-end agent mobility protocol |

The *research hypothesis* is that a small **portable handoff envelope**, compatible adapters, strict authorization, and an auditable lifecycle could make these layers work together.

## Proposed flow (illustrative, not implemented)

```mermaid
flowchart LR
    U[User] --> A[Origin agent]
    A --> P[Policy and approval]
    P --> H[Portable task envelope]
    H --> D[Agent discovery via A2A]
    D --> B[Destination agent]
    B --> T[Approved MCP tools]
    B --> C[Checkpoint and artifacts]
    C --> R[Result, audit and trace]
    R --> A
```

The origin retains ownership of the user's intent and consent. Delegated privileges are scoped independently at the destination. Retries need explicit idempotency and reconciliation.

## Run the first local experiment

The [local proof of concept](docs/local-implementation.md) uses two separate processes, a strict synthetic handoff envelope, a preconfigured receiver-side approval, SQLite-backed audit/receipt deduplication, and a separate simulated stale-worker fencing exercise. It uses a **custom loopback HTTP interface, not A2A**; the next integration milestone is the official A2A SDK.

```sh
python -m pip install -e . pytest
python -m agent_movement.demo
python -m pytest -q          # all tests: agent_movement + corpus tooling
```

The demo outputs a completed task, an idempotent replay, a denied unapproved request, and a rejected stale epoch. The unit/integration tests run in CI on Python 3.11 and 3.13; check CI for repository-hosted results. No model credentials, live external tool effects, private data or public endpoints are required.

## Read the research

Suggested reading order:

1. [Agent movement vs copy, clone, replication and multiplication: status audit](docs/agent-movement-vs-copy-replication-multiplication.md): vocabulary, and what is (not) implemented
2. [Glossary: 70 terms, each tagged as standard, research or project working definition](docs/glossary.md)
3. [Research landscape and technology comparison](docs/research-landscape.md): what A2A, MCP, LangGraph, Temporal and others do and do not solve
4. [Standards and protocol version tracker (28 specs, primary sources, checked 2026-10-16)](docs/standards-tracker.md) · [CSV](data/standards-tracker.csv)
5. [How movement would work: lifecycle and draft handoff envelope](docs/how-it-works.md)
6. [Agent lifecycle, liveness, death and safe retirement (proposed model)](docs/agent-lifecycle-liveness-and-death.md)
7. [Device compatibility and capability requirements (134 candidate device classes)](docs/device-compatibility-and-capability-matrix.md) · [CSV catalog](data/device-targets.csv)
8. [Security, privacy, and threat model](docs/security-and-trust.md)
9. [Agent fingerprints, movement tracking, and digital forensics](docs/agent-forensics-and-fingerprints.md): identity vs fingerprint, evidence grades, auditable movement receipts
10. [Open technical and product questions](docs/open-questions.md): ranked questions with falsifiable experiments
11. [Evidence map: which corpus items bear on each open question, and where evidence is missing](docs/evidence-map.md) · [CSV](data/evidence-map.csv)
12. [Proposed architecture and staged roadmap](docs/roadmap.md)
13. [Primary sources and evidence log](docs/sources.md): index of the references cited in the core research docs, with a spot-check log
14. [News corpus: 100 dated, verified and coded news items (2024–2026) with summaries, BibTeX and protocol](docs/news-corpus/README.md) ([digest](docs/news-corpus/digest.md))
15. [Paper corpus: 83 metadata-verified, audited scholarly papers (1980–2026), from mobile agents and process migration to MCP/A2A security](docs/paper-corpus/README.md) ([digest](docs/paper-corpus/digest.md))
16. [Corpus timeline and coverage analysis (generated)](docs/corpus-analysis/README.md)
17. [Corpus link health and Wayback availability (2026-10-16): no dead links; 16 cited URLs not yet archived](docs/corpus-qa/README.md)
18. [How to cite this repository or a corpus item](docs/how-to-cite.md) · [Development and quality gates](docs/development.md)

Experimental code (synthetic, local, not production):

- [Executable local handoff, tests, limits and next implementation milestones](docs/local-implementation.md)
- [Optional A2A v1 adapter on the official SDK: delegation, not migration; experimental, unauthenticated](docs/a2a-adapter.md)
- [Peer authentication and pre-disclosure authorization (synthetic, local; `python -m agent_movement.peer_demo`)](docs/peer-authentication.md)
- [Same-runtime checkpoint relocation (pinned LangGraph) with a 30-row crash/duplicate fault matrix](docs/checkpoint-relocation.md) (optional extra: `pip install -e '.[relocation]'`)
- [Signed movement receipts and offline forensic verifier (experimental, synthetic fixtures)](docs/movement-receipts.md)

## Executable human-impact research pilot (stacked PR)

The [human-impact research lab protocol](docs/human-impact-research-lab.md) maps real-world questions about control, identity, privacy, accountability, replication and task continuity onto falsifiable **synthetic** experiments. When the prototype is available, run:

~~~sh
python -m pip install -e . pytest
python -m agent_movement.mobilitybench --output mobilitybench-local.jsonl
python -m pytest -q          # all tests: agent_movement + corpus tooling
~~~

The local smoke suite currently models 20 cases. **Seventeen checks reproduce their expected narrow behavior; three are marked known gaps, not security successes.** This is not A2A, trusted peer identity, portable live state or a production system. See the experiment protocol for limits and next steps.

[MobilityBench v0.1](docs/mobilitybench-v0.1.md) extends this with 18 frozen, digest-verified synthetic tasks across three workload families: document work, constrained coding and simulated tools. It compares keep-on-origin, restart-on-destination and the PR #6 local delegate under seeded faults. The A2A, checkpoint-relocation and cross-framework baselines are reported as **unavailable**. Run it with `python -m agent_movement.mobilitybench run --suite v0.1 --out results.jsonl`, then `report --in results.jsonl`. The suite is deterministic and LLM-free, so it supports no general statistical claims.

## Recommended initial experiment

The local non-destructive **non-A2A** task handoff and deduplication test is now implemented on the feature branch. Next, implement an **actual A2A v1.x SDK-based** interaction between two independent test agents with capability discovery and authorization *before input disclosure*. After that, test crash recovery and same-runtime checkpoint relocation before claiming agent migration.

See [local implementation](docs/local-implementation.md) and [roadmap](docs/roadmap.md). These later capabilities remain research proposals, not implemented integrations.

## Contribute

Research corrections, protocol compatibility experiments, concrete failure modes, and reproducible benchmarks are especially welcome. Distinguish **verified protocol behavior** from **proposed project design** and link to primary sources; add any new citation to [docs/sources.md](docs/sources.md). No credentials, private conversations, or confidential task payloads should ever be committed.

**License:** Not selected. Until a license is added by the repository owner, do not assume this repository grants open-source reuse rights.

---
Sources were reviewed on **2026-10-15**; upstream protocols and SDKs continue to evolve.
