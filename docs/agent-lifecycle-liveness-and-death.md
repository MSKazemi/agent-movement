# Agent lifecycle, liveness, death, and safe retirement

**Status:** Research and protocol-design proposal, **not a standard and not an implementation**.
**Reviewed:** 2026-10-15.
**Applies to:** Agent Movement's task handoff, checkpoint relocation, cloning, replication and cross-runtime continuations.

## Executive answer

An AI agent should **not** have a single binary "alive/dead" field. An agent **definition** may exist, an **execution instance** may stop, a **task** may complete, a **checkpoint** may permit recovery, and an **authority grant** may be revoked while an unauthorized copy continues to run. These facts are independent.

**Core rules:**

1. A missed heartbeat implies **suspected/unreachable**, not proven dead.
2. A confirmed stopped process proves only that **one specified execution instance** ended, not that its logical agent or descendants are gone.
3. A valid checkpoint can allow a **new instance** to continue a task. It does not resurrect the old process, model-private state, or hidden reasoning.
4. "Revoked" means **not authorized**, not "physically shut down". The strongest practical safety property is that protected tools reject stale and unauthorized actions.
5. No general mechanism can verify that every copy of arbitrary software on every untrusted or disconnected machine was erased. "Globally dead forever" is not a justified claim.

Here, **alive** and **dead** are *operational computing terms*, not claims about consciousness, personhood or biological life.

## 1. The units that have lifecycles

| Unit | Stable identifier | Question | What is *not* implied |
| --- | --- | --- | --- |
| Agent definition | agent_definition_id + immutable definition_digest | Is this build/configuration registered? | A running process exists |
| Managed logical agent | logical_agent_id + identity_generation | Is this managed continuity/ownership record enabled or retired? | Every copy obeys the controller |
| Execution instance | agent_instance_id | Is this exact process/container/worker incarnation running or terminated? | Other instances have stopped |
| Execution attempt | execution_id | Which run made the observation/effect? | A successful logical task |
| Task | logical_task_id and local A2A task IDs | Is the work waiting, running, completed, canceled or ambiguous? | Agent is alive or dead |
| Movement operation | movement_id, parent_movement_id | Was state delegated, transferred or rejected? | Successful migration or stopped origin |
| Replica/descendant | distinct instance + parent_execution_id + lineage_relation | Was it cloned, forked, replicated, or delegated? | Identical authority or identity |
| Authority | grant/approval reference, principal, expiry, fencing_epoch | May this instance perform this action **now**? | Process availability or cessation |
| Durable checkpoint | checkpoint digest + compatibility/retention metadata | Could a new authorized run resume? | Semantic equivalence or complete data |

See [forensics and fingerprints](agent-forensics-and-fingerprints.md) for existing repository identity, lineage, fencing and evidence-grade conventions.

The **managed logical agent** is an administrative abstraction chosen by the system operator. We do not assume universal identity persistence across clones or unrelated agents. A copied model/configuration does not inherit an agent's unique identity or privileges.

## 2. Model states as independent dimensions

### 2.1 Execution state (one specific instance)

The following is a **project proposal**, not an A2A enum:

| State | Operational meaning | Preferred evidence |
| --- | --- | --- |
| CREATED | Instance identity reserved; no process started | Coordinator creation record |
| STARTING | Runtime initializing | Local supervisor startup record |
| RUNNING | Executing instructions or tool workflow | Fresh authenticated runtime/supervisor observation |
| IDLE | Running and able to accept work, none assigned | Supervisor + readiness observation |
| WAITING | Waiting for dependency, input, approval, timer or external effect reconciliation | Explicit wait reason and task record |
| QUIESCING | Stopping new effects to reach a checkpoint/safe boundary | Coordinator/supervisor receipt |
| SUSPENDED | Execution voluntarily paused; no active work in this incarnation | Checkpoint and supervisor pause/stop receipt |
| RESUMING | A *new or continuing* instance attempts compatible restore | Restore-validation receipt |
| STOPPING | Graceful stop requested/in progress | Stop-intent and supervisor observation |
| STOPPED | This instance exited normally | Durable supervisor exit record |
| CRASHED | This instance exited unexpectedly | Durable supervisor failure/exit record |
| DESTROYED | Runtime resource torn down after stop/crash | Host/container manager record |

**Important:** CRASHED, STOPPED and DESTROYED are terminal **for that instance identifier**. Restart is a new agent_instance_id and, where applicable, a new execution_id. Checkpoint recovery preserves the appropriate logical task ID, not the terminated instance ID.

"MIGRATING" belongs primarily to the **movement coordinator**, not as the sole state of an execution. During a move, source and destination have their own instance states, and the movement operation has its own state.

### 2.2 Observed reachability and freshness

| Observer state | Meaning |
| --- | --- |
| NEVER_OBSERVED | No authenticated execution evidence collected |
| RESPONDING | Authenticated fresh response from the particular instance |
| STALE | Last positive evidence older than observation freshness target |
| SUSPECTED_UNREACHABLE | Failed configured number of probes/time budget |
| UNKNOWN | Available evidence cannot determine whether it runs |
| CONFIRMED_EXIT | Trusted supervising system has a terminal record for that **instance** |

Do **not** store UNKNOWN as if it were a physical transition of the remote agent. It is the monitoring system's epistemic state. An agent can respond and crash immediately afterward; positive evidence always has a time and scope.

### 2.3 Recoverability and readiness

- **NO_CHECKPOINT:** No verified resumable state known.
- **CHECKPOINT_CANDIDATE:** Stored state exists but has not passed integrity, schema and compatibility checks.
- **RECOVERABLE:** Required snapshot, artifacts, compatible executor, policy authorization and relevant dependencies are available *under stated assumptions*.
- **RECOVERY_BLOCKED:** State exists but a necessary condition is missing (policy, key, artifact, runtime, data residency, operator approval).
- **UNRECOVERABLE_WITHIN_SCOPE:** Under the managed system's inventory, this specific continuation lacks adequate durable state. A copied definition might still start **a different task**, so the logical agent's existence is not disproven.
- **NOT_APPLICABLE:** Stateless or completed work.

"Checkpoint exists" is not sufficient for "recoverable"; it may be corrupt, incompatible, forbidden, dependent on inaccessible tool resources, or semantically incomplete.

### 2.4 Authority (independent of execution)

- **PENDING_APPROVAL:** No permitted action yet.
- **AUTHORIZED:** Explicit, currently valid bounded grant for the requesting principal/action/destination.
- **EXPIRED:** Grant time window elapsed.
- **REVOKED:** Grant invalidated by policy authority.
- **FENCED:** Another execution epoch superseded this instance as effect owner.
- **QUARANTINED:** Restricted to an explicitly approved non-side-effect diagnostic subset.
- **RETIRED:** Logical identity no longer permitted to create new authoritative runs.

A physical process may remain RUNNING with authority REVOKED/FENCED. Label that a **rogue or zombie execution** operationally, not a legitimate live agent. The authorization state must be checked by the protected service or gateway, not believed because the agent self-reports compliance.

### 2.5 Task state

**A2A v1.0** already defines task-state values: TASK_STATE_UNSPECIFIED, TASK_STATE_SUBMITTED, TASK_STATE_WORKING, TASK_STATE_COMPLETED, TASK_STATE_FAILED, TASK_STATE_CANCELED, TASK_STATE_INPUT_REQUIRED, TASK_STATE_REJECTED and TASK_STATE_AUTH_REQUIRED.

- The project should preserve those **exact wire enums** when interacting with A2A v1.0. Do not invent new A2A enum values.
- COMPLETED, FAILED, CANCELED and REJECTED are task-terminal.
- INPUT_REQUIRED and AUTH_REQUIRED are interrupted/waiting states.
- UNSPECIFIED means unknown/indeterminate; it is not proof of death.
- A2A TaskState describes a **task**, not a running agent instance, movement coordinator, or proof of physical shutdown.

Source: [A2A v1.0, TaskState](https://a2a-protocol.org/v1.0.0/specification/#413-taskstate).

### 2.6 Movement-operation state

Proposed separate coordinator transitions:
**REQUESTED -> VALIDATING -> APPROVED -> QUIESCING_SOURCE -> SNAPSHOT_VERIFIED -> FENCING_SOURCE -> DESTINATION_PREPARED -> DESTINATION_AUTHORIZED -> RESUMED -> RECONCILED -> COMPLETED**.

Failure exits are **DENIED**, **FAILED**, **CANCELED**, or **UNKNOWN_REQUIRES_RECONCILIATION**; do not mark COMPLETED solely because an envelope was delivered.

For simple delegation, source need not quiesce: the coordinator uses a different profile, **DELEGATION**, and documents multiple concurrent executors with separate, bounded grants. Full "movement" claims should require the stronger relocation semantics.

## 3. Exact definitions of "alive" and "dead"

Use scoped predicates or user-facing labels rather than one misleading boolean:

**INSTANCE_OBSERVED_ALIVE(instance, time, observer):** An authorized observer obtained a validated positive signal indicating the *specified instance* was executing or responsive at that observation time (for example, fresh challenge/response bound to instance ID, nonce and execution epoch, or local trusted supervisor record). It does **not** prove it is still alive at a later instant.

**INSTANCE_CONFIRMED_DEAD(instance, time, trust_domain):** A trusted supervisor issued an authenticated durable terminal record for that instance and the orchestrator will not restart that **same instance ID**. Claim is limited to that execution identity and supervising domain. The observation does not exclude unauthorized binaries, clones or other physical machines.

**LOGICAL_AGENT_ACTIVE(logical_agent):** At least one known, currently authorized execution is actively serving the managed agent's work, with bounded evidence freshness. A task can be active although the original instance crashed.

**LOGICAL_AGENT_DORMANT(logical_agent):** No known active execution; the managed logical identity and verified resumable state or ability to create a new authorized instance remain. Prefer "dormant" to "dead".

**LOGICAL_AGENT_RETIRED(logical_agent):** The authoritative managed registry marks the logical identity retired, blocks fresh execution grants and fences all *known* outstanding effect-owning epochs in systems under its control. This is an enforceable administrative decision where all effect gateways honor the registry; it is **not** a universal claim that all computation and copies ended.

**PERMANENTLY_ERASED or GLOBALLY_DEAD:** Do **not** emit as verified conclusions for arbitrary distributed agents. At most report evidence of erasure of enumerated, controlled storage copies and revocation of controlled permissions, together with out-of-scope locations.

**NO_EVIDENCE / UNKNOWN:** Prefer to any claim of death based on missed check-ins, inability to reach a worker or loss of telemetry.

| Scenario | Accurate conclusion |
| --- | --- |
| Heartbeat missing for 30 seconds | SUSPECTED_UNREACHABLE; execution unknown |
| Process A exit confirmed; checkpoint persists | A's instance is dead; task potentially recoverable |
| Laptop sleeps while workflow is paused | Instance suspended/dormant, not necessarily dead |
| Task successfully completed | Task terminal; agent may remain active for other tasks |
| A2A task fails | Task failed; no conclusion about server lifetime |
| Agent credentials revoked | Agent not authorized; process might still run |
| Origin A fenced; destination B resumes | A is stale/unauthorized for protected effects; task continues with B |
| Two replicas of same definition run | Two live *instances*; separate IDs and explicit authority scopes required |
| Task no longer makes progress but keeps answering pings | Process responsive; **semantic progress stalled** |
| Remote peer disappears behind a network partition | UNKNOWN; never presume safe deletion or non-execution |
| Operator presses "delete" on one server | Deletion requested/confirmed within local scope only; not proven global erasure |

## 4. Do not conflate different notions of liveness

1. **Process liveness** — does code execute/respond at a time?
2. **Service readiness** — can it accept work with working dependencies?
3. **Task progress** — does its task advance, or is it looping/stalled?
4. **Authorization liveness** — can it legitimately invoke a specific tool?
5. **Recovery liveness** — does a verified authorized path exist from saved state to resumed work?
6. **Lineage liveness** — are descendants still executing even if their ancestor is gone?

A ping-only monitor can be fooled by a healthy wrapper around a stalled agent. Progress needs separate *bounded, privacy-conscious* indicators: checkpoint advancement, validated artifact milestones, tool status or scheduler transitions. Progress metrics must not reward fabricated steps, useless token generation or needless tool calls. "No progress" may be correct while waiting for approved human input.

## 5. Formal safety and progress properties (under declared assumptions)

The strongest useful properties are about **authorized effects**, not detecting every running CPU process.

**I1 — Effect authorization:** For each protected side-effect commit, the target-side enforcer verifies the acting principal, scoped grant, expiry/revocation, operation ID and current fencing epoch **at commit time or under a documented transaction guarantee**. If the enforcer cannot determine validity, it fails closed for that operation.

**I2 — Single writer:** For a task configured with exclusive effect ownership, **at most one current authoritative epoch can commit protected effects**. It is not enough that only one coordinator *believes* a worker is active. The effect gateway must reject stale epoch values.

**I3 — Terminal monotonicity:** A given instance_id cannot move from STOPPED/CRASHED/DESTROYED back into RUNNING; resumption uses a new instance ID. A terminal A2A task must not be silently reused as a new nonterminal task.

**I4 — No blind retry:** When an external action's outcome is uncertain, label UNKNOWN_REQUIRES_RECONCILIATION and inspect independent target records or an idempotency-aware operation before any repeat.

**I5 — Explicit clone boundaries:** A clone, replica, fork or fan-out child gets a distinct execution/instance identity, parent lineage and authority budget; shared hashes or copied prompts never grant authority.

**I6 — Consent and data boundaries:** No migration or recovery can bypass current approval, classification, destination allowlists, residency rules, or secret filtering. Cancellation cannot retroactively undo prior committed effects.

**I7 — Evidence honesty:** Report unknown and out-of-scope domains; do not infer universal absence of copies or guarantee destruction.

One schematic safety contract for a protected effect is:

~~~text
commit(effect, task, executor, epoch)
  => verified_principal(executor)
     AND active_scoped_grant(executor, effect, task)
     AND epoch == authoritative_epoch(task)
     AND idempotency_or_reconciliation_policy_satisfied(effect)
~~~

And a conditional progress property:

~~~text
IF task is permitted and runnable
   AND a fair executor is eventually available
   AND required services are reachable
THEN the task eventually advances or reaches an explicit terminal/blocked outcome.
~~~

**Qualification:** These are proof *targets*, not established guarantees. They depend on trusted enforcement, fault assumptions, eventually available services, consistency of epoch allocation, and cooperating target systems. Generic third-party tools without fencing/idempotency support invalidate a blanket exactly-once or exclusive-effect claim.

## 6. Monitoring and inference: proposed practical algorithm

**Inputs:** signed/authenticated supervisor transitions, challenge responses or bounded authenticated heartbeats, coordinator lease/epoch record, checkpoint registry, task store, target-side side-effect log and identity/approval service.

**Procedure:**

1. Register definition, logical identity, distinct instance ID, execution ID, and parent/lineage where relevant.
2. At startup, verify workload identity and allowed capabilities; record a STARTING -> RUNNING transition with monotonically increasing status version.
3. Probe a specific instance using a fresh nonce/short observation deadline where available; bind response to principal, instance ID and epoch. Store source, reception timestamp and freshness period. TLS or SPIFFE alone authenticates a workload; it does not prove a unique human-like agent identity, honest behavior, or future liveness.
4. On a missed threshold, change **observer_state** to STALE/SUSPECTED_UNREACHABLE; never automatically claim CRASHED. An authenticated local process exit is stronger, scoped evidence.
5. Before failover/relocation, reconcile uncertain external effect intents and acquire a **new authoritative epoch from a strongly consistent source**.
6. Fence the old epoch at every cooperating effect gateway. Only then authorize the new executor to commit protected effects. A timed lease alone is not sufficient if an old actor can wake and write after expiry.
7. Verify checkpoint integrity and compatibility. Create a **new** instance ID. Preserve logical task lineage, not the dead instance identity.
8. Record endpoint confirmations (commit/deny), reconcile task state and durable audit trace. Fail closed on unverifiable permissions or side effects.
9. On retirement, revoke future grants, fence current epochs at known gateways, initiate cancellation and controlled retention/deletion workflows; report which destinations acknowledged versus which remain UNKNOWN.

**Demo configuration (non-normative):** heartbeat every 10 seconds, mark STALE after 20 seconds and SUSPECTED after 30 seconds. These are *illustrative parameters*, not scientifically guaranteed failure-detector cutoffs. Use task-specific objectives, latency distributions and network conditions when choosing values; do not infer death from expiry.

### Evidence and uncertainty

Reuse this project's forensic evidence grades [E0–E3](agent-forensics-and-fingerprints.md). For status claims, include:

- Observer principal and trust domain; exact target instance ID and execution epoch;
- Source event ID, authenticated receipt and monotonic sequence/status version;
- Observation and ingestion times, clock uncertainty, nonce/replay protection if a probe;
- Observed state, evidence freshness deadline, and confidence **category**;
- Policy/grant/fencing decision references, and whether target-side effects were independently confirmed.

Grades reflect evidence quality, not probabilities. A signed record from a dishonest or compromised domain is still limited to that domain's assertions.

## 7. Migration, replication and "zombie" examples

### Example A: safe relocation

At time T1, A executes task-17 under epoch 41. A quiesces; state is checkpointed and verified. The coordinator assigns epoch 42, and the tool gateway fences 41. B starts under a **new** instance ID and executes task-17 under epoch 42. If A later wakes up and sends an effect with 41, the protected tool rejects it.

- A may still be **physically alive**, but is **not authoritative**.
- B is a new live execution of the same logical task.
- The task's outcome and external effects are recorded once at independent authoritative endpoints where such enforcement is supported.

### Example B: network partition

B stops answering probes. B might have crashed, be blocked, or still be running. Mark B UNKNOWN/SUSPECTED. A replacement may be authorized **only after** the prior effect owner is fenced at protected services and uncertain actions are reconciled. Without such enforcement, report reduced guarantees and do not claim safe active failover.

### Example C: malicious or disconnected clone

A clone on an uncontrolled device can keep calculating or contact services with credentials it possesses. The project cannot truthfully certify global deletion. It **can** revoke controlled grants, use short-lived audience-bound credentials, isolate tools, rotate compromised secrets and reject external side effects at controlled endpoints. This is authorization containment, not omnipotent remote shutdown.

### Example D: apparent death of a multi-agent system

Coordinator C crashes, but agent workers A and B remain active. C's execution is dead; tasks may be live, blocked, orphaned, or unauthorized. Recovery depends on re-establishing ownership, authoritative epochs and a durable ledger, not declaring the entire agent collective dead.

## 8. Proposed portable lifecycle observation (illustrative JSON)

~~~json
{
  "schema_version": "0.1.0-draft",
  "observation_id": "obs-001",
  "logical_agent_id": "urn:example:agent:researcher",
  "identity_generation": 1,
  "agent_definition_id": "urn:example:definition:researcher-v1",
  "agent_instance_id": "instance-b-002",
  "execution_id": "run-002",
  "logical_task_id": "task-17",
  "movement_id": "move-101",
  "parent_execution_id": "run-001",
  "lineage_relation": "relocate",
  "states": {
    "execution": "RUNNING",
    "observer": "RESPONDING",
    "task": "TASK_STATE_WORKING",
    "authority": "AUTHORIZED",
    "recoverability": "CHECKPOINT_CANDIDATE"
  },
  "fencing_epoch": 42,
  "status_version": 6,
  "observed_at": "2026-10-15T19:00:00Z",
  "freshness_expires_at": "2026-10-15T19:00:20Z",
  "evidence": {
    "observer_principal": "spiffe://example.org/monitor/worker",
    "source_event_id": "event-456",
    "evidence_grade": "E2",
    "verification_result": "verified-within-example-trust-domain"
  },
  "authority": {
    "grant_ref": "external-opaque-grant-ref",
    "policy_version": "policy-7"
  },
  "checkpoint": {
    "reference": "content-addressed-placeholder",
    "compatibility_verified": false
  }
}
~~~

This payload is intentionally synthetic. The project has **not** defined canonical JSON signatures, operationally trusted event issuers, or a normative schema. Do not put API keys, credentials, private prompts or hidden chain-of-thought into observations. Do not rely on a self-reported status as independent evidence.

## 9. Acceptance and adversarial test matrix

| ID | Controlled test | Required outcome |
| --- | --- | --- |
| LC-01 | Pause an agent and miss heartbeat threshold | SUSPECTED or UNKNOWN, not falsely dead |
| LC-02 | Confirm worker exit with valid checkpoint | Old instance terminal, task recoverability independently evaluated |
| LC-03 | Same task resumed on different worker | New instance/execution IDs; stable logical task lineage |
| LC-04 | Reawaken old worker after fencing epoch increased | Old worker cannot commit protected effects |
| LC-05 | Keep process heartbeating but stall work | Responsive process, separate progress-stalled alarm |
| LC-06 | Expire/revoke auth while agent still running | Protected gateway denies further unauthorized effects |
| LC-07 | Crash after external side effect but before receipt | UNKNOWN_REQUIRES_RECONCILIATION, no blind replay |
| LC-08 | Corrupt/incompatible checkpoint | Recovery blocked; no unsafe resume |
| LC-09 | Two cloned instances share build hash | Distinct identities; no inherited grant |
| LC-10 | Partition monitor from alive worker | No false physical-death claim |
| LC-11 | Stop one of two workers | Only that instance terminal; collective status remains evidence-based |
| LC-12 | Request global deletion across one uncooperative domain | Truthful partial deletion/revocation report with unknown domain |
| LC-13 | Forge old heartbeat or reuse nonce | No false fresh liveness record |
| LC-14 | Try to resurrect a terminal instance ID | Reject; require new ID and lineage |
| LC-15 | Lose coordinator during relocation | No un-fenced dual-authority commits at protected test gateway |
| LC-16 | Send unexpected A2A task enum or task-terminal update | Follow versioned A2A compatibility rules; do not invent lifecycle state |

**Phase 0 deliverable:** decide the terminology, schema and transition guards; this document is that proposal.

**Phase 1:** two local isolated agents, synthetic tasks, one heartbeat/progress monitor, explicit task/instance separation and signed-identity stubs; no claim of hard remote-shutdown enforcement.

**Phase 2:** implement persistent coordinator/fencing + verified checkpoint restore for one runtime; run LC-01 through LC-16 with a simulated side-effect service.

**Phase 3:** cross-device and cross-runtime interoperability, multi-domain evidence gaps, distributed failure detection benchmarking and model-checking of coordinator invariants.

## 10. Open research questions worth testing over the next five years

1. **Semantic liveness:** How can we distinguish an agent making legitimate progress from one merely emitting pings, tokens or meaningless tool requests, without leaking private task content?
2. **Continuity:** What exactly survives a model switch or runtime migration: identity, intent, capability, memory, task, behavioral policy or only externally visible outcomes?
3. **Death certificates:** Can multiple independent observers give a verifiable **scope-bounded** terminal certificate without claiming universal deletion?
4. **Resurrection authorization:** When may a retained checkpoint create a new execution after the original agent was disabled, revoked, or "forgotten" by the user?
5. **Replication consistency:** Can multiple active replicas cooperate without double effects or destructive memory merging? Which workloads require single-writer ownership?
6. **Offline agents:** Can a mobile device perform any meaningful work under an expiring authority boundary without creating un-revocable effects?
7. **Zombie detection:** How reliably can we identify stale epochs, orphaned workers and unapproved descendants across heterogeneous runtimes and trust domains?
8. **Evidentiary trust:** Can attestations and target-side audit distinguish "running", "responsive", "making progress" and "acting legitimately"?
9. **Graceful death:** What is the minimum correct shutdown protocol for in-flight external actions, secrets, artifacts, child agents, memory and delegated budgets?
10. **Safety versus availability:** How much useful autonomous work should stop when coordination or revocation checks are unavailable? What tradeoffs are acceptable for low vs high impact actions?
11. **Data after death:** How can we report retention and deletion of checkpoints, private memory, logs and replicas, including **non-cooperating** destinations, without false assurances?
12. **Normative interoperability:** Which minimal lifecycle observation could be shared across A2A, orchestration systems and forensics **without** redefining their existing task states?

## 11. Source mapping and scope

**Externally supported building blocks:**

- [A2A Protocol v1.0 specification](https://a2a-protocol.org/v1.0.0/specification/): defined **task** states, identifiers and auth-required semantics. It does *not* define this project's agent-instance "death" predicate.
- [Kubernetes Pod lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/): separates Pod phases, runtime/container states, and UNKNOWN when status cannot be determined. Its "Failed" or "Succeeded" observations are about Kubernetes workload objects, not globally erased agents.
- [Chandra & Toueg, Unreliable Failure Detectors for Reliable Distributed Systems, JACM 1996](https://research.google/pubs/unreliable-failure-detectors-for-reliable-distributed-systems/): foundational framework for reasoning about unreliable failure suspicion under asynchronous communications.
- [Martin Kleppmann, How to do distributed locking (2016)](https://martin.kleppmann.com/2016/02/08/how-to-do-distributed-locking.html): explains stale lease holders, monotonically increasing fencing tokens and the need for storage/target enforcement.
- [SPIFFE, Working with SVIDs](https://spiffe.io/docs/latest/deploying/svids/): explains authenticated workload identity; authentication alone is not a liveness, correctness or identity-continuity guarantee.

**Proposal versus fact:** Everything labeled project states, operational predicates, invariants, JSON, timers, tests or roadmap in this document is proposed Agent Movement design. No production deployment, empirical test results, universal death proof, protocol extension or verified cross-framework migration is claimed.

Related repository research: [how it works](how-it-works.md), [security and trust](security-and-trust.md), [forensics](agent-forensics-and-fingerprints.md), [open questions](open-questions.md) and [roadmap](roadmap.md).
