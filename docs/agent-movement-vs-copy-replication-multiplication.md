# Agent Movement vs Copy, Cloning, Replication, and Multiplication

> **Historical snapshot, not current implementation status (2026-10-16).** The matrix below was accurate for commit `487748c` on 2026-10-15, before code merged. Current `main` now includes bounded, synthetic/local delegation and checkpoint-relocation demonstrations, but not general cloning/replication or live process migration. For authoritative current capabilities see [project charter](project-charter.md), [as-built architecture](architecture.md) and [roadmap](roadmap.md). The original audit table is deliberately preserved for provenance.

**Audit date:** 2026-10-15  
**Scope:** Implementation status of this repository's default branch, plus proposed project vocabulary.  
**Verdict:** Research/documentation exists; **none** of the execution operations below is implemented here. Do not confuse a technology mentioned in docs with a working integration.

## Executive capability matrix

| Capability | Proposed operational meaning | Implemented in this repo? | What's available now |
| --- | --- | --- | --- |
| Task delegation | Agent A asks B to perform bounded work; A can remain active | **No** | A2A-based design and envelope proposal |
| Agent movement (task-context transfer) | Move responsibility for a task/work package from A to B | **No** | Conceptual lifecycle and threat model |
| Checkpoint relocation / resume | Restore compatible persisted task state on another worker | **No** | Research-only checkpoint proposal |
| Live process migration | Transfer a running process, stack, transient state and in-flight effects | **No; out of initial scope** | Explicitly excluded from current claims |
| Copy agent definition | Instantiate an independent agent using the same config/prompt/tool declarations | **No** | No launcher, package format or CLI |
| Clone agent from snapshot | Create one **new** identity from a permitted memory/checkpoint snapshot | **No** | No snapshot import/export |
| Replicate agent service | Maintain N equivalent instances for availability or throughput | **No** | No controller, lease or failover |
| Multiply / spawn agents | Create N bounded child agents or workers to parallelize tasks | **No** | No fan-out coordinator or budget policy |
| Fork divergent work | Branch one snapshot into multiple independently evolving branches | **No** | No lineage or merge/reconciliation system |
| Agent swarm / collaboration | Multiple distinct agents coordinate and exchange results | **No** | A2A and orchestration discussed only |
| Agent lifecycle management | Track create/start/pause/resume/stop/delete, health, audit and policy | **No** | Proposed states, not a running service |

**Evidence:** At the time of audit the tracked branch consisted of README.md and six Markdown research documents under docs/. There were no source-code modules, executable demos, dependency manifests, tests or CI workflows. Repository reference at audit: [main at 487748c](https://github.com/MSKazemi/agent-movement/tree/487748c9340c9863b53f6bd79dd08c30b21bf598). This establishes *repository implementation*, not the availability of these features in third-party products.

## The conceptual difference (do not use these words interchangeably)

### 1. Movement: A -> B (same logical work; changed execution location)

A task that started with A is handed over or resumed at B. For a **move**, the project should aim to preserve the *logical task ID*, checkpoint lineage, artifacts, and policy context; the destination has a separate physical execution identity. The origin must not keep executing the same externally-effectful task after ownership transfers.

- **Weak movement (task-context transfer):** Send explicit task context to B; B may begin its own execution. This is *not* a lossless runtime migration.
- **Checkpoint relocation:** Serialize a safe, runtime-compatible application checkpoint, restore at B, fence the old executor, and reconcile uncertain external effects.
- **Strong/live migration:** Transfer live process memory, stacks, connections, in-flight tool operations, model internals. Not generally portable across unrelated frameworks or model providers; explicitly **not promised**.
- For safe ownership changes, use a durable operation record, bounded leases/fencing, recipient verification, authorization, version checks, and explicit unknown/reconcile outcomes during partitions.

**Example:** Move a partially completed report-generation task from a laptop worker to a cloud worker, then prevent the laptop worker from submitting the final report again.

### 2. Copy: A -> A + B (same specification; independent instances)

Create a new agent from the same **definition** (model selection, system instructions, permitted tools, workflow and policies). A and B receive **different instance IDs** and independent runs; copying a definition does **not** copy an in-progress conversation or state. An API call to the same LLM model does not, by itself, clone a complete agent.

**Example:** Start two independently configured code-review agents using one versioned template.

### 3. Cloning: A(snapshot) -> A + B (snapshot fork, not one identity)

A stronger copy that includes an explicitly authorized exportable **application** snapshot: selected messages, task data, summaries, memory references, and/or compatible checkpoint. Create B with a **new agent/run ID**, lineage linking it to the source snapshot, and separate delegated permissions. The agents can immediately diverge. A cloned transcript does not restore arbitrary hidden model state or tool-side transactions.

**Example:** Fork a research assistant's approved public notes into a second assistant that explores a different hypothesis.

### 4. Replication: one logical service -> multiple managed instances

A controller maintains a desired number of equivalent agent workers/instances for availability or throughput. **Active/passive:** one writes, a standby can recover after failover using a durable state. **Active/active:** multiple work concurrently, requiring partitioning, coordination, and conflict policy. Replication of container processes is **not** automatically replication of conversational memory, workflow ownership, or external side effects.

**Example:** Keep one active and one standby agent worker; after the primary fails, only a fenced replacement may resume its task.

### 5. Multiplication: one request -> many spawned agents/tasks

"Agent multiplication" is an informal project term; the conventional system concepts are **dynamic spawning, fan-out, worker-pool scaling, or multi-agent orchestration**. A coordinator creates a bounded number of child agents (identical or specialized), assigns distinct subtasks, tracks costs/deadlines, and aggregates results. They are separate executions, **not all the same agent identity**. Scale-down and cancellation are part of the operation.

**Example:** A research agent spawns five specialists, each checking a different source set, and merges citation-checked findings.

### Related but distinct

- **Delegation:** A asks B to execute a task, normally keeping oversight and ownership. It is in the research scope of agent movement but is not a move. This can occur without moving A, copying its identity, or cloning its memory.
- **Fork:** Branch one approved snapshot into several independently evolving branches, preserving parent-child provenance. A clone creates one new identity; a fork creates several branches. Result merging is a *separate*, domain-specific operation.
- **Swarm:** Coordination pattern among multiple agents; the agents need not be copies or replicas.
- **Kubernetes replica / HPA:** Scales Pods. It does not create semantically independent agent tasks or solve application checkpoint transfer.

## Identity, state, and side-effect contracts (proposed)

| Operation | Logical task continuity | New agent/instance identity? | Copy application memory? | Origin remains active? | Main risk |
| --- | --- | --- | --- | --- | --- |
| Delegate | New delegated task linked to parent | B already has own ID | Minimal approved task context only | Yes | Accidental authority transfer |
| Move/relocate | **Yes**, same logical task and lineage | New runtime instance; logical task preserved | Validated portable checkpoint/context | Not for moved task after commit | Split-brain, duplicated effects |
| Copy definition | New task/run | **Yes** | **No** by default | Yes | Template secrets or policy drift |
| Clone snapshot | New branch/task | **Yes** | Approved snapshot only | Yes | Leaked memory; untracked forks |
| Replicate active/passive | Yes for takeover | Separate replica execution ID | Shared durable state, not blind memory copying | One active task owner | Unsafe failover / split brain |
| Replicate active/active | Multiple partitioned runs | Distinct instance IDs | Deliberate shared state model | Multiple active replicas | Races, inconsistent updates |
| Multiply/fan-out | Parent task plus child tasks | **Yes, per child** | Bounded context per subtask | Yes | Runaway cost and fan-out |

**Never propagate raw API keys, browser cookies, private chain-of-thought, or another runtime's implicit credentials as part of a copy/move.** Re-issue bounded permissions through trusted infrastructure after destination identity/policy checks. External side effects cannot universally be guaranteed exactly-once without cooperation from the tool/system; use idempotency, durable decisions and reconciliation.

## Illustrative relationship

~~~mermaid
flowchart TD
    A[Agent A]
    A -->|MOVE task ownership| M[Agent B resumes task]
    A -->|COPY config| C[Agent B starts independently]
    A -->|CLONE safe snapshot| F[Agent B forks memory]
    A -->|REPLICATE service| R[Replica controller maintains N]
    A -->|MULTIPLY / spawn| S[Coordinator creates N child tasks]
    A -->|DELEGATE| D[Existing specialist works on a subtask]
~~~

Diagram shows **proposed semantics, not running features**.

## What would count as "we have it"?

A feature is **Implemented** only when this repo contains executable code, documented installation/run instructions, a reproducible test, and a behavior trace demonstrating its promised semantics. A design document or an example from another project counts only as **Researched**.

| Candidate test ID | Passing demonstration required | Status |
| --- | --- | --- |
| DELEGATE-01 | Two test agents complete authenticated bounded task/artifact exchange; no source credentials leaked | Not built |
| COPY-01 | Create two distinct IDs from one versioned template; isolated stores and permissions | Not built |
| CLONE-01 | Create an independent child from a redacted/versioned snapshot; prove no secret copying and divergent memory | Not built |
| MULTIPLY-01 | Fan out a single test job into N child tasks; enforce max children, budget, cancellation, and stable aggregated output | Not built |
| MOVE-01 | Persist app checkpoint; B resumes; A is fenced; restart/duplicate-delivery tests exercise ambiguous side effects | Not built |
| REPLICA-01 | Primary crashes; standby takes over with one active lease and no duplicate simulated action | Not built |
| REPLICA-02 | Controlled active/active jobs show correct partitioning/conflict handling under concurrent writes | Not built |
| PORTABILITY-01 | Document two pinned runtimes, what checkpoint fields can cross, what is lost, and negative compatibility tests | Not built |

## Recommended implementation order

P0–P4 are priority tiers (lower means earlier), not phases; the staged plan is Phase 0–4 in the [roadmap](roadmap.md).

1. **P0: Definitions, schemas and lifecycle tests.** Separate task ID, agent-definition ID, agent-instance ID, run ID, snapshot ID, operation ID and lineage. Keep each operation's invariants explicit.
2. **P1: Delegation + definition copy.** Implement A2A test handoff with approval, then instantiate two isolated agents from a versioned definition. Both are bounded MVPs.
3. **P1: Controlled multiplication.** Add child-task spawning, quotas, cancellation, idempotent aggregation, max depth and budget ceilings.
4. **P2: Checkpoint relocation (meaningful movement).** Choose *one* runtime, safe checkpoint boundaries, portable envelope, compatibility negotiation, fencing and recovery.
5. **P2: Active/passive replication.** Add heartbeat/lease, recovery policy, strongly identified logical task and failover test suite.
6. **P3: Snapshot cloning and cross-runtime adaptation.** Strict provenance/redaction, memory compatibility and a loss report.
7. **P4: Active/active replication or cross-organization migration.** Only with a concrete workload, measured value and formal safety/consistency model.
8. **Non-goal for initial releases:** Live opaque model/process migration, identical consciousness/hidden model state, unrestricted autonomous self-replication, guaranteed exactly-once arbitrary third-party side effects.

**Recommendation:** Market the research umbrella as *Agent Movement & Lifecycle Operations*, but document copy, clone, replication and multiplication as explicit **different primitives**. Never use their names as evidence of implementation.

## Open design decisions

- Is the portable unit an *agent definition*, a *task*, a *checkpoint*, or a *workflow graph*? Probably different schemas.
- Is movement **exclusive ownership transfer**, or can origin and destination both run? Default should be exclusive for side-effectful tasks.
- Can replicas share a canonical memory store, or must memory be sharded? What are consistency and retention requirements?
- When spawning children, which abilities can be inherited and who approves them? How are cost, depth and duration bounded?
- Which framework should be the first checkpoint adapter? A2A is a message protocol, not an execution snapshot interface.
- Does snapshot cloning require source-owner consent, provenance, redaction, and data-deletion propagation?
- What is the observable fallback when checkpoint relocation is impossible: reject, delegate anew, or re-execute with explicit consent?

## Primary technical references

- [A2A v1.0 specification](https://a2a-protocol.org/v1.0.0/specification/) — task, agent discovery and interoperability; **not** arbitrary runtime state migration.
- [MCP 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28) — tool/data interoperability; stateless protocol transport does **not** imply stateless agent applications.
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence) — checkpoints, threads and stores *within its execution model*.
- [Temporal workflows](https://docs.temporal.io/workflows) and [Child Workflows](https://docs.temporal.io/child-workflows) — durable replay and child-workflow composition.
- [Kubernetes Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/) and [HPA](https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/) — workload replicas and horizontal resource scaling.
- [OAuth 2.0 Token Exchange, RFC 8693](https://www.rfc-editor.org/rfc/rfc8693) and [SPIFFE Workload API](https://spiffe.io/docs/latest/spiffe-specs/spiffe_workload_api/) — security building blocks requiring application policy.

Related project notes: [landscape](research-landscape.md), [proposed handoff](how-it-works.md), [roadmap](roadmap.md), [threat model](security-and-trust.md), [open questions](open-questions.md).

---
This document is a terminology and capability audit, **not** evidence that any feature has been deployed or tested.
