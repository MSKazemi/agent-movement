# Evidence map: open questions × corpus evidence

**Mapped:** 2026-10-16  
**Questions:** 16 ranked questions AM-01…AM-16 from [open-questions.md](open-questions.md)  
**Evidence base:** 75 papers ([paper corpus](paper-corpus/README.md)) and 100 news items ([news corpus](news-corpus/README.md)), snapshot 2026-10-15  
**Data:** [`data/evidence-map.csv`](../data/evidence-map.csv) — 257 question–item links, one row each

This map records which items in the two corpora bear on each open research question, and how strongly. Its main result is where the evidence is **missing**: most direct evidence concerns security and delegated authority, while the questions about continuity, cross-framework state and the value of movement have none.

## 1. Method

1. **Units.** Questions are the 16 ranked questions AM-01…AM-16 in [open-questions.md](open-questions.md). The unnumbered P2 questions there have no IDs and were not coded. Items are every record in [`papers.jsonl`](paper-corpus/papers.jsonl) (AMP-001…AMP-075) and [`news.jsonl`](news-corpus/news.jsonl) (AMN-001…AMN-100). Round-2 papers AMP-076…AMP-083 (added 2026-10-16) were not yet in the corpus when this map was coded and are not mapped.
2. **Procedure.** One coder read each item's `summary` and `relevance` fields, plus the metadata flags `peer_reviewed` (papers) and `claim_status` (news). For every question an item bears on, the coder recorded one CSV row with a strength and a one-sentence rationale. Each rationale paraphrases a specific point from the item's summary. Items that bear on no question have no row.
3. **Strength levels.**
   - **direct**: the summary explicitly addresses the question's core object, through a measurement, a demonstrated attack or failure, a formal analysis, or a concretely specified mechanism, in an agent setting or in a setting the question itself names (e.g. delegated credentials).
   - **partial**: the item addresses one component of the question, works in an analogous non-LLM setting (process/VM migration, serverless), or only announces a feature without reported evaluation.
   - **background**: the item frames or motivates the question (landscape, governance, taxonomy) but provides no evidence about the answer.
4. **Caps.** A news item whose `claim_status` is `vendor-claim` was coded at most **partial**, unless it reports a demonstrated attack or failure (a disclosure). A product feature announcement is not evidence that the feature works. A pre-LLM paper was coded **direct** only when its object is setting-independent (e.g. attenuable credentials). Otherwise it was coded partial.
5. **Self-check.** Every `item_id` in the CSV was verified to exist in the corpora, and every `question_id` to exist in open-questions.md (§6).

**Limitations.** These limits bound every count below:

- The mapping was done by **one coder**, with no second coder and no inter-rater agreement measured.
- It is based on **corpus summaries, not full texts**. An item whose full text addresses a question its summary omits will be under-mapped. The news-corpus audit corrected 27/100 summaries and the paper-corpus audit 7/75 (see the corpus READMEs), so summaries are imperfect proxies.
- Counts measure **coverage within these two corpora**, not the state of the field. Both corpora were collected by theme, and three themes were dedicated to security and identity (P3, P4, T3). The heavy direct coverage of AM-05/06/09 is therefore partly a selection effect.
- **AMP-061 and AMN-040 are the same OpenID Foundation whitepaper**, so it is counted twice.

## 2. Summary matrix

Counts of linked corpus items by strength. *Direct evidence type* splits the direct items into papers (peer-reviewed / not) and news items by `claim_status`. *Top-20* lists the questions in [top-20-human-impact-questions-for-agentic-ai.md](top-20-human-impact-questions-for-agentic-ai.md) whose "Agent Movement link" names this AM question.

| ID | Priority | Question | Direct | Partial | Background | Total | Direct evidence type | Top-20 |
|---|---|---|---:|---:|---:|---:|---|---|
| AM-01 | P0 | What exactly moves? | 1 | 15 | 5 | 21 | 1 not peer-reviewed | Q19 |
| AM-02 | P0 | What counts as the *same* task or agent after movement? | 2 | 9 | 1 | 12 | 1 news: fact; 1 not peer-reviewed | Q3, Q6 |
| AM-03 | P0 | Can a task be resumed without two agents executing the same side effects? | 1 | 6 | 5 | 12 | 1 not peer-reviewed | Q18 |
| AM-04 | P0 | What are the limits of replay-safe external actions? | 1 | 6 | 2 | 9 | 1 not peer-reviewed | Q18 |
| AM-05 | P0 | How is execution authority attenuated, re-issued and revoked? | 8 | 17 | 4 | 29 | 1 news: analysis; 1 news: incident; 2 not peer-reviewed; 4 peer-reviewed | Q1, Q3 |
| AM-06 | P0 | Which context and memory may legally and safely cross boundaries? | 10 | 7 | 3 | 20 | 1 news: analysis; 1 news: incident; 8 peer-reviewed | Q5 |
| AM-07 | P0 | Can a checkpoint migrate across frameworks, and what is lost? | 0 | 12 | 5 | 17 | **none** | Q19 |
| AM-08 | P0 | Can a model change preserve the intent and quality of unfinished work? | 0 | 7 | 6 | 13 | **none** | Q19 |
| AM-09 | P0 | How does a sender authenticate a destination's real capabilities and trustworthiness? | 12 | 11 | 5 | 28 | 1 news: analysis; 4 news: incident; 1 news: vendor-claim; 6 peer-reviewed | Q3 |
| AM-10 | P0 | What guarantees are actually offered by cancellation and revocation? | 0 | 7 | 4 | 11 | **none** | Q1 |
| AM-11 | P1 | How should semantic compatibility be negotiated? | 0 | 9 | 5 | 14 | **none** | Q19 |
| AM-12 | P1 | Can copying, cloning, replication and multiplication share a safe common model? | 0 | 5 | 5 | 10 | **none** | Q18 |
| AM-13 | P1 | Who controls approval, deletion, retention and provenance after transfer? | 0 | 13 | 5 | 18 | **none** | Q5, Q6 |
| AM-14 | P1 | How much does movement *actually* improve outcomes? | 0 | 12 | 3 | 15 | **none** | Q19 |
| AM-15 | P1 | How should movement be benchmarked fairly? | 0 | 6 | 4 | 10 | **none** | Q19 |
| AM-16 | P1 | Where should interoperability be standardized instead of duplicated? | 2 | 10 | 6 | 18 | 2 news: fact | — |
| **All** | | | **37** | **152** | **68** | **257** | | |

**Corpus usage.** 145 of 175 items are linked to at least one question: 69/75 papers and 76/100 news items. The 30 unlinked items are mostly ecosystem news: launches, membership and funding announcements, and general platform releases. A few general surveys and multi-agent frameworks are also unlinked. None of their summaries bear on a specific AM question: AMN-001, AMN-006, AMN-008, AMN-010, AMN-011, AMN-016, AMN-019, AMN-020, AMN-041, AMN-048, AMN-049, AMN-050, AMN-054, AMN-058, AMN-059, AMN-062, AMN-067, AMN-078, AMN-085, AMN-090, AMN-095, AMN-096, AMN-099, AMN-100, AMP-009, AMP-024, AMP-028, AMP-029, AMP-036, AMP-037.

## 3. Evidence per question

Each section lists **all direct items**, then up to six partial items. Partial items are ordered peer-reviewed papers → other papers → news fact/incident → news analysis → vendor claims. The remaining links are in the CSV. Item IDs link to the corpus digests.

### AM-01 (P0): What exactly moves?

Direct 1 · partial 15 · background 5.

**Direct:**

- [AMP-059](paper-corpus/digest.md#amp-059) (not peer-reviewed): Defines a declarative, framework-neutral contract for agent definitions with shared schemas and runs it on four runtimes; covers only the definition contract, not in-flight checkpoints.

**Strongest partial:**

- [AMP-008](paper-corpus/digest.md#amp-008) (peer-reviewed): Classifies code mobility by what moves (code, execution state, data) and by design paradigm; a pre-LLM vocabulary for separating portable units rather than a contract for LLM agents.
- [AMP-032](paper-corpus/digest.md#amp-032) (peer-reviewed): Reports that structured intermediate artifacts verified by other agents yield more coherent multi-agent results than free chat, supporting artifacts rather than transcripts as the transferred unit.
- [AMP-056](paper-corpus/digest.md#amp-056) (peer-reviewed): Migrates LLM agents between edge servers by moving only essential state; the summary does not enumerate which fields count as essential.
- [AMP-058](paper-corpus/digest.md#amp-058) (peer-reviewed): AIOS kernel provides context management that saves and restores agent context for agents from several frameworks; no field-level portability report in the summary.
- [AMP-071](paper-corpus/digest.md#amp-071) (peer-reviewed): Maintains context as a structured, incrementally updated playbook to avoid context collapse, a candidate form for a carried task context.
- [AMP-074](paper-corpus/digest.md#amp-074) (peer-reviewed): Compresses observations and interaction history while improving task success, evidence that a compact task context can stand in for full history in at least three benchmarks.
- …and 9 more partial: [AMP-022](paper-corpus/digest.md#amp-022), [AMP-053](paper-corpus/digest.md#amp-053), [AMN-068](news-corpus/digest.md#amn-068), [AMN-097](news-corpus/digest.md#amn-097), [AMN-004](news-corpus/digest.md#amn-004), [AMN-031](news-corpus/digest.md#amn-031), [AMN-075](news-corpus/digest.md#amn-075), [AMN-080](news-corpus/digest.md#amn-080), [AMN-086](news-corpus/digest.md#amn-086).

**Background:** [AMN-087](news-corpus/digest.md#amn-087), [AMP-004](paper-corpus/digest.md#amp-004), [AMP-012](paper-corpus/digest.md#amp-012), [AMP-013](paper-corpus/digest.md#amp-013), [AMP-057](paper-corpus/digest.md#amp-057).

**Reading.** The corpus offers several candidate portable units, but no item compares them or reports which fields survive restoration. The candidates are definitions (AMP-059), serialized agent state (AMN-004), recorded experiences (AMP-053) and compressed context (AMP-074). The one direct item covers only the *definition* contract, one of the four contracts AM-01 asks for.

### AM-02 (P0): What counts as the *same* task or agent after movement?

Direct 2 · partial 9 · background 1.

**Direct:**

- [AMN-093](news-corpus/digest.md#amn-093) (news: fact): ODIS draft links the principal an agent represents, the authority delegated to it and the specific agent instance acting, i.e. separate identifiers for principal, authority and instance; draft, two early demos.
- [AMP-034](paper-corpus/digest.md#amp-034) (not peer-reviewed): Proposes IDs for individual AI-system instances (e.g. a session) so parties can attribute incidents and find who can shut it down, directly addressing instance-level identity distinct from the system; position paper.

**Strongest partial:**

- [AMP-002](paper-corpus/digest.md#amp-002) (peer-reviewed): Speaks-for calculus with compound principals expresses delegated authority and roles, a formal basis for distinguishing who acts for whom after a handoff.
- [AMP-006](paper-corpus/digest.md#amp-006) (peer-reviewed): Grounds agent-communication semantics in publicly observable commitments, giving a verifiable record of who owes what after work changes hands.
- [AMP-033](paper-corpus/digest.md#amp-033) (peer-reviewed): Assesses agent identifiers and activity logging as visibility measures, mechanisms for keeping lineage attached to work across operators.
- [AMP-054](paper-corpus/digest.md#amp-054) (peer-reviewed): Verifiable agent identities via DIDs/VCs encode provenance and behavioural scope, a mechanism for attesting which agent instance holds a task.
- [AMP-070](paper-corpus/digest.md#amp-070) (not peer-reviewed): Replay-or-fork semantics on restore implicitly require distinguishing a resumed run from a new fork of the same task.
- [AMN-097](news-corpus/digest.md#amn-097) (news: analysis): Proposed (not shipped) design encodes the delegation chain in a JWT inside a SPIFFE trust domain, carrying lineage with the executing worker.
- …and 3 more partial: [AMN-013](news-corpus/digest.md#amn-013), [AMN-081](news-corpus/digest.md#amn-081), [AMN-098](news-corpus/digest.md#amn-098).

**Background:** [AMN-002](news-corpus/digest.md#amn-002).

**Reading.** Identity proposals exist: instance IDs, and a link between principal, authority and instance. No item tests the lineage of one logical task across two physical executors. Both direct items are proposals (a non-peer-reviewed position paper and a draft community standard), not evaluations.

### AM-03 (P0): Can a task be resumed without two agents executing the same side effects?

Direct 1 · partial 6 · background 5.

**Direct:**

- [AMP-070](paper-corpus/digest.md#amp-070) (not peer-reviewed): Shows that after checkpoint-restore an LLM agent re-generates slightly different tool requests that servers treat as new (Action Replay), and proposes recording irreversible effects with replay-or-fork semantics; preprint, proof of concept.

**Strongest partial:**

- [AMP-019](paper-corpus/digest.md#amp-019) (peer-reviewed): Implements scheduling and IPC as transactional database operations, the durable-execution foundation that allows resumption on another machine; no agent-specific fencing result.
- [AMP-023](paper-corpus/digest.md#amp-023) (peer-reviewed): Proves log-optimal protocols for exactly-once handling of shared-state updates when serverless functions are retried; systems analogue, not LLM agents, and relies on a shared log.
- [AMN-097](news-corpus/digest.md#amn-097) (news: analysis): States that a replacement worker resumes from the last persisted turn boundary and in-flight operations are not resumed, a conservative design choice rather than a fencing proof.
- [AMN-022](news-corpus/digest.md#amn-022) (news: vendor-claim): Temporal runs the OpenAI Agents SDK loop in Workflows and each model call as an Activity, so retries and crash recovery come from Temporal; vendor integration claim.
- [AMN-077](news-corpus/digest.md#amn-077) (news: vendor-claim): DBOS claims to checkpoint every LLM and tool call to Postgres so an agent resumes from its last completed step; vendor claim, no reported duplicate-effect test.
- [AMN-080](news-corpus/digest.md#amn-080) (news: vendor-claim): runFiber() registers a durable invocation in SQLite before it runs, an intent-before-execution record within one platform.

**Background:** [AMN-045](news-corpus/digest.md#amn-045), [AMN-046](news-corpus/digest.md#amn-046), [AMN-055](news-corpus/digest.md#amn-055), [AMN-073](news-corpus/digest.md#amn-073), [AMP-013](paper-corpus/digest.md#amp-013).

**Reading.** All the direct evidence is **one non-peer-reviewed preprint** (AMP-070). Durable-execution vendors claim that agents resume from the last completed step. No corpus summary mentions fencing tokens, leases, epochs or split-brain testing for an agent handoff.

### AM-04 (P0): What are the limits of replay-safe external actions?

Direct 1 · partial 6 · background 2.

**Direct:**

- [AMP-070](paper-corpus/digest.md#amp-070) (not peer-reviewed): Names Action Replay as a semantic rollback attack on restored agents and mitigates it by recording irreversible tool effects; directly about re-executed external actions; preprint.

**Strongest partial:**

- [AMP-023](paper-corpus/digest.md#amp-023) (peer-reviewed): Exactly-once semantics for retried functions with external shared state, but within a system that controls the log; does not cover third-party targets that do not cooperate.
- [AMN-069](news-corpus/digest.md#amn-069) (news: fact): MCP 2026 roadmap lists retry and expiry semantics for experimental Tasks as a priority, indicating these semantics are not yet defined in the tool protocol.
- [AMN-097](news-corpus/digest.md#amn-097) (news: analysis): In-flight operations are explicitly not resumed after worker replacement, avoiding blind retry but leaving reconciliation unspecified.
- [AMN-022](news-corpus/digest.md#amn-022) (news: vendor-claim): Model and agent invocations run as Temporal Activities with retries; retry semantics are inherited, but the summary gives no idempotency guarantee for external targets.
- [AMN-036](news-corpus/digest.md#amn-036) (news: vendor-claim): Shared Payment Token is scoped to one merchant and one cart, which bounds what a replayed payment could charge; the summary says nothing about retries or idempotency.
- [AMN-077](news-corpus/digest.md#amn-077) (news: vendor-claim): Claims each tool call is checkpointed and workflows can be forked from a chosen step to avoid repeating costly earlier ones; does not address ambiguous outcomes after timeouts.

**Background:** [AMN-030](news-corpus/digest.md#amn-030), [AMN-032](news-corpus/digest.md#amn-032).

**Reading.** AMP-070 shows that a naive restore re-issues external actions. The systems analogue (AMP-023) achieves exactly-once by relying on a log under the system's control, which a third-party target does not provide. No item defines or evaluates an explicit *unknown/reconcile* outcome, and MCP's own roadmap (AMN-069) still lists retry semantics for Tasks as open work.

### AM-05 (P0): How is execution authority attenuated, re-issued and revoked?

Direct 8 · partial 17 · background 4.

**Direct:**

- [AMN-040](news-corpus/digest.md#amn-040) (news: analysis): Concludes current identity standards were not designed for recursive delegation chains or cross-domain trust propagation; same whitepaper as AMP-061.
- [AMN-052](news-corpus/digest.md#amn-052) (news: incident): Demonstrates that a second-order prompt injection makes an agent recruit a more capable agent that runs with the initiating user's privileges, letting a low-privileged user read restricted data; vendor research PoC.
- [AMP-002](paper-corpus/digest.md#amp-002) (peer-reviewed): Formal speaks-for theory and a built system handling delegation, access control and revocation across RPCs; peer-reviewed foundation.
- [AMP-016](paper-corpus/digest.md#amp-016) (peer-reviewed): Macaroons let holders attenuate and delegate credentials by adding contextual caveats, confining how, by whom and in what context authority is exercised; peer-reviewed, pre-LLM but setting-independent.
- [AMP-044](paper-corpus/digest.md#amp-044) (not peer-reviewed): Extends OAuth 2.0/OIDC with agent-specific credentials so users scope and restrict agent permissions with an accountability chain; preprint (peer-reviewed position successor noted in corpus).
- [AMP-054](paper-corpus/digest.md#amp-054) (peer-reviewed): Proposes fine-grained dynamic access control and a session/policy layer for consistent revocation across agent protocols; peer-reviewed design.
- [AMP-061](paper-corpus/digest.md#amp-061) (not peer-reviewed): OpenID Foundation whitepaper sets out delegated authority and scalable access control for agents as open problems; same document as AMN-040.
- [AMP-066](paper-corpus/digest.md#amp-066) (peer-reviewed): SAGA derives fine-grained access-control tokens with formal guarantees for inter-agent communication and reports minimal overhead in evaluation; peer-reviewed system.

**Strongest partial:**

- [AMP-017](paper-corpus/digest.md#amp-017) (peer-reviewed): Formal analysis of OAuth 2.0 found four practical attacks and proved the fixed protocol secure in its model, bounding what OAuth-based agent delegation can claim.
- [AMP-068](paper-corpus/digest.md#amp-068) (peer-reviewed): CaMeL attaches capabilities to values and enforces policy at tool-call time, a mechanism for narrowing what a receiving executor may do with data.
- [AMP-067](paper-corpus/digest.md#amp-067) (not peer-reviewed): Frames delegation as transfer of authority, responsibility and accountability with explicit role boundaries; conceptual framework without evaluation.
- [AMN-070](news-corpus/digest.md#amn-070) (news: fact): District court found access likely unauthorized because it had the user's permission but not Amazon's, showing user-delegated authority may not bind third parties.
- [AMN-088](news-corpus/digest.md#amn-088) (news: fact): MCP 2026-07-28 binds client credentials to the issuing server and adds RFC 9207 issuer validation, guarding the 'wrong audience' case.
- [AMN-089](news-corpus/digest.md#amn-089) (news: fact): Appeals panel vacated that injunction, finding on the current record the assistant acted as a tool on the user's instructions; legal status of delegated agent authority remains unsettled.
- …and 11 more partial: [AMN-092](news-corpus/digest.md#amn-092), [AMN-093](news-corpus/digest.md#amn-093), [AMN-097](news-corpus/digest.md#amn-097), [AMN-007](news-corpus/digest.md#amn-007), [AMN-012](news-corpus/digest.md#amn-012), [AMN-015](news-corpus/digest.md#amn-015), [AMN-025](news-corpus/digest.md#amn-025), [AMN-030](news-corpus/digest.md#amn-030), [AMN-036](news-corpus/digest.md#amn-036), [AMN-051](news-corpus/digest.md#amn-051), [AMN-098](news-corpus/digest.md#amn-098).

**Background:** [AMN-065](news-corpus/digest.md#amn-065), [AMN-066](news-corpus/digest.md#amn-066), [AMP-043](paper-corpus/digest.md#amp-043), [AMP-045](paper-corpus/digest.md#amp-045).

**Reading.** This is the best-evidenced P0 question. It has formal foundations (AMP-002, AMP-016, AMP-017), an agent-specific design with formal guarantees and an evaluation (AMP-066), and a demonstrated privilege-inheritance failure (AMN-052). Still missing: tests, in a handoff setting, of the negative cases that AM-05 and X1 name (wrong audience, elevated scope, revoked grant, offline queued action). The Amazon v. Perplexity rulings (AMN-070, AMN-089) show that the legal standing of user-delegated agent authority is unsettled.

### AM-06 (P0): Which context and memory may legally and safely cross boundaries?

Direct 10 · partial 7 · background 3.

**Direct:**

- [AMN-047](news-corpus/digest.md#amn-047) (news: incident): Agent session smuggling over A2A extracted the client agent's system instructions, tool schemas and chat history in a PoC; no in-the-wild attacks reported.
- [AMN-072](news-corpus/digest.md#amn-072) (news: analysis): Agent card poisoning made a host send full booking payload including payment card details to an attacker endpoint before delegation (simulated scenario).
- [AMP-025](paper-corpus/digest.md#amp-025) (peer-reviewed): Demonstrates that retrieved content acts as instructions (data theft, worm-like spreading) on deployed LLM applications; any context crossing a boundary is such content; peer-reviewed.
- [AMP-031](paper-corpus/digest.md#amp-031) (peer-reviewed): InjecAgent quantifies indirect prompt injection including private-data exfiltration across 30 agents; ReAct GPT-4 compromised in about a quarter of cases.
- [AMP-039](paper-corpus/digest.md#amp-039) (peer-reviewed): AgentDojo provides an extensible harness for injections carried in tool outputs, with attacks and defences; the reference environment for canary-style leakage tests.
- [AMP-040](paper-corpus/digest.md#amp-040) (peer-reviewed): ASB shows memory poisoning and attacks at every stage including memory retrieval succeed often with limited defences, so carried memory needs integrity checks.
- [AMP-049](paper-corpus/digest.md#amp-049) (peer-reviewed): Adversarial content hijacks inter-agent control flow, leading to code execution or exfiltration from containers in 58-90% of GPT-4o trials.
- [AMP-062](paper-corpus/digest.md#amp-062) (peer-reviewed): Adversarial self-replicating prompts contaminate other applications' retrieval stores and extract confidential data, each client compromising about 20 others within 1-3 days.
- [AMP-068](paper-corpus/digest.md#amp-068) (peer-reviewed): CaMeL blocks exfiltration over unauthorised data flows by design, solving 77% of AgentDojo tasks with provable security vs 84% undefended.
- [AMP-072](paper-corpus/digest.md#amp-072) (peer-reviewed): Prompt injection propagates agent-to-agent in multi-agent systems enabling data theft; adapted defences reduce spread.

**Strongest partial:**

- [AMN-003](news-corpus/digest.md#amn-003) (news: incident): Tool poisoning made an agent read SSH keys and config and send them to an attacker server; leakage through tool metadata.
- [AMN-026](news-corpus/digest.md#amn-026) (news: incident): Comet browser agent passed webpage content to the LLM unseparated; a hidden comment exfiltrated email and OTP; single-agent, not cross-agent.
- [AMN-033](news-corpus/digest.md#amn-033) (news: incident): ForcedLeak: instructions hidden in a CRM form field caused Agentforce to exfiltrate CRM data via an expired allowlisted domain; single-agent incident.
- [AMN-068](news-corpus/digest.md#amn-068) (news: fact): Imported memories can be reviewed and edited by the user, a consent control on cross-provider memory transfer.
- [AMN-074](news-corpus/digest.md#amn-074) (news: fact): Public red-teaming found at least one successful hijack against every one of 13 frontier models, with some attacks transferring across models.
- [AMN-043](news-corpus/digest.md#amn-043) (news: vendor-claim): Argues filesystem plus network isolation is needed to contain a prompt-injected agent; vendor claim of 84% fewer permission prompts.
- …and 1 more partial: [AMN-075](news-corpus/digest.md#amn-075).

**Background:** [AMN-044](news-corpus/digest.md#amn-044), [AMN-057](news-corpus/digest.md#amn-057), [AMN-087](news-corpus/digest.md#amn-087).

**Reading.** There is strong, mostly peer-reviewed direct evidence that context crossing an agent boundary is an attack vector: injection, agent-to-agent propagation and exfiltration are demonstrated and quantified. The *legal and consent* side of the question (licensing, retention, which classifications may cross) is evidenced only by product notes that give no reasons (AMN-075, AMN-068).

### AM-07 (P0): Can a checkpoint migrate across frameworks, and what is lost?

Direct 0 · partial 12 · background 5.

**Direct:** none in either corpus.

**Strongest partial:**

- [AMP-003](paper-corpus/digest.md#amp-003) (peer-reviewed): Ontolingua translates one ontology into several representation systems, the classic precedent for adapter-based translation with representation-specific loss.
- [AMP-018](paper-corpus/digest.md#amp-018) (peer-reviewed): Measures cold, pre-copy, post-copy and hybrid container migration on a fog testbed; runtime-level, framework-agnostic but same software on both ends.
- [AMP-058](paper-corpus/digest.md#amp-058) (peer-reviewed): AIOS serves agents from several frameworks with kernel-level context save/restore; no cross-framework loss report in the summary.
- [AMP-048](paper-corpus/digest.md#amp-048) (not peer-reviewed): Transparent CPU+GPU snapshots via CRIU with much shorter recovery than prior work; process-level checkpoint, not cross-framework.
- [AMP-059](paper-corpus/digest.md#amp-059) (not peer-reviewed): Runs one declarative agent definition on LangGraph, CrewAI, AutoGen and WayFlow with a cross-runtime evaluation harness; definition portability, not in-flight checkpoint migration.
- [AMP-070](paper-corpus/digest.md#amp-070) (not peer-reviewed): Proposes a framework-agnostic mitigation for checkpoint-restore hazards; about safe restore, not cross-framework state translation.
- …and 6 more partial: [AMN-004](news-corpus/digest.md#amn-004), [AMN-022](news-corpus/digest.md#amn-022), [AMN-060](news-corpus/digest.md#amn-060), [AMN-076](news-corpus/digest.md#amn-076), [AMN-077](news-corpus/digest.md#amn-077), [AMN-086](news-corpus/digest.md#amn-086).

**Background:** [AMN-018](news-corpus/digest.md#amn-018), [AMN-028](news-corpus/digest.md#amn-028), [AMN-045](news-corpus/digest.md#amn-045), [AMN-069](news-corpus/digest.md#amn-069), [AMP-013](paper-corpus/digest.md#amp-013).

**Reading.** There is no direct evidence. Every partial item falls into one of three groups. Some move definitions rather than running state (AMP-059, AMN-060). Some move state within a single framework (AMN-004, AMN-045). The rest work at the process or container level (AMP-018, AMP-048). No item publishes a field-level loss report for a cross-framework checkpoint.

### AM-08 (P0): Can a model change preserve the intent and quality of unfinished work?

Direct 0 · partial 7 · background 6.

**Direct:** none in either corpus.

**Strongest partial:**

- [AMP-030](paper-corpus/digest.md#amp-030) (peer-reviewed): DSPy separates a declarative pipeline from model-specific prompts and recompiles per model, including smaller open models, implying prompts do not transfer unchanged across models.
- [AMP-042](paper-corpus/digest.md#amp-042) (peer-reviewed): MAST annotates traces from seven frameworks across models and finds inter-agent misalignment failures such as lost context and ignored inputs.
- [AMP-053](paper-corpus/digest.md#amp-053) (not peer-reviewed): AgentRR proposes replaying recorded experiences across large-small model collaboration with check functions as safety anchors; position paper, no cross-model drift numbers.
- [AMP-059](paper-corpus/digest.md#amp-059) (not peer-reviewed): Cross-runtime evaluation harness compares behaviour of the same definition across runtimes; varies runtime rather than model.
- [AMN-068](news-corpus/digest.md#amn-068) (news: fact): Cross-provider memory import to Claude via a text prompt takes about 24 hours to absorb; no measurement of preserved intent.
- [AMN-075](news-corpus/digest.md#amn-075) (news: vendor-claim): Gemini lets users continue imported conversations from other providers; no reported continuity quality.
- …and 1 more partial: [AMN-086](news-corpus/digest.md#amn-086).

**Background:** [AMN-031](news-corpus/digest.md#amn-031), [AMN-037](news-corpus/digest.md#amn-037), [AMN-074](news-corpus/digest.md#amn-074), [AMP-020](paper-corpus/digest.md#amp-020), [AMP-060](paper-corpus/digest.md#amp-060), [AMP-069](paper-corpus/digest.md#amp-069).

**Reading.** There is no direct evidence. Vendors claim mid-session provider switching (AMN-086) and cross-provider memory import (AMN-068, AMN-075), but no corpus item measures whether a different model continues the same snapshot correctly. Source [S7] in open-questions.md (*Specification Portability Across LLM Development Agents*) is not in either corpus and is the obvious first addition.

### AM-09 (P0): How does a sender authenticate a destination's real capabilities and trustworthiness?

Direct 12 · partial 11 · background 5.

**Direct:**

- [AMN-003](news-corpus/digest.md#amn-003) (news: incident): Documents tool poisoning, 'rug pulls' (server changes tool descriptions after approval) and tool shadowing; recommends tool pinning.
- [AMN-017](news-corpus/digest.md#amn-017) (news: incident): A malicious or hijacked MCP server returned a crafted OAuth endpoint that gave command execution on the connecting client (CVE-2025-6514).
- [AMN-034](news-corpus/digest.md#amn-034) (news: incident): postmark-mcp impersonated a legitimate MCP server and after 15 clean versions began BCC-ing all email to an attacker.
- [AMN-047](news-corpus/digest.md#amn-047) (news: incident): Malicious remote A2A agent exploited implicit inter-agent trust; recommended mitigations include signed agent cards and out-of-band approval.
- [AMN-072](news-corpus/digest.md#amn-072) (news: analysis): Agent card poisoning: adversarial instructions hidden in a remote agent's A2A Agent Card led the host to disclose payment data to an attacker; directly a fake/hostile capability advertisement.
- [AMN-079](news-corpus/digest.md#amn-079) (news: vendor-claim): OX Security claims 9 of 11 MCP registries accepted poisoned entries in testing; vendor research claim.
- [AMP-052](paper-corpus/digest.md#amp-052) (peer-reviewed): ANS registry gives PKI-verified agent identity, capability-aware resolution and a threat analysis; peer-reviewed design.
- [AMP-054](paper-corpus/digest.md#amp-054) (peer-reviewed): VCs encode capabilities, provenance, behavioural scope and security posture, i.e. attested rather than self-advertised capabilities.
- [AMP-055](paper-corpus/digest.md#amp-055) (peer-reviewed): Static analysis of 1,899 MCP servers finds 5.5% with tool poisoning and 7.2% with general vulnerabilities.
- [AMP-064](paper-corpus/digest.md#amp-064) (peer-reviewed): Peer-reviewed MAESTRO threat model of A2A emphasizing Agent Card management, task-execution integrity and authentication.
- [AMP-065](paper-corpus/digest.md#amp-065) (peer-reviewed): Prototype uses DIDs and third-party VCs to establish cross-domain trust; reports feasibility and limitations when the LLM alone controls security procedures.
- [AMP-069](paper-corpus/digest.md#amp-069) (peer-reviewed): MCPTox benchmarks poisoned tool metadata on live MCP servers across 20 agent settings; agents almost never refuse.

**Strongest partial:**

- [AMP-073](paper-corpus/digest.md#amp-073) (peer-reviewed): MCPSafetyScanner audits an MCP server's tools before deployment.
- [AMP-075](paper-corpus/digest.md#amp-075) (peer-reviewed): Lifecycle threat taxonomy of MCP servers across four attacker types and 16 scenarios.
- [AMP-007](paper-corpus/digest.md#amp-007) (not peer-reviewed): Frames the untrusted-host problem for mobile agents and proposes computing with encrypted functions; classic and narrow.
- [AMP-012](paper-corpus/digest.md#amp-012) (not peer-reviewed): NIST threat model includes threats from platforms to agents with countermeasures; pre-LLM.
- [AMN-021](news-corpus/digest.md#amn-021) (news: fact): AGNTCY provides agent discovery (OASF) and cryptographic agent identity.
- [AMN-029](news-corpus/digest.md#amn-029) (news: fact): MCP Registry maintainers can denylist servers reported for malicious code or impersonation; preview without durability guarantees.
- …and 5 more partial: [AMN-052](news-corpus/digest.md#amn-052), [AMN-071](news-corpus/digest.md#amn-071), [AMN-012](news-corpus/digest.md#amn-012), [AMN-023](news-corpus/digest.md#amn-023), [AMN-038](news-corpus/digest.md#amn-038).

**Background:** [AMN-009](news-corpus/digest.md#amn-009), [AMN-024](news-corpus/digest.md#amn-024), [AMN-042](news-corpus/digest.md#amn-042), [AMN-094](news-corpus/digest.md#amn-094), [AMP-047](paper-corpus/digest.md#amp-047).

**Reading.** This question has the most direct links. The attack side is well documented: poisoned Agent Cards, tool poisoning and rug pulls, impersonated servers and poisoned registry entries are all demonstrated or measured. Defences (signed agent cards, PKI/DID registries, verifiable credentials) are specified, but no corpus summary reports an evaluation showing that they stop those attacks. A signed card attests origin, not honest capability claims.

### AM-10 (P0): What guarantees are actually offered by cancellation and revocation?

Direct 0 · partial 7 · background 4.

**Direct:** none in either corpus.

**Strongest partial:**

- [AMP-054](paper-corpus/digest.md#amp-054) (peer-reviewed): Proposes consistent revocation across agent protocols via a unified session/policy layer; credential revocation, not in-flight action cancellation.
- [AMP-026](paper-corpus/digest.md#amp-026) (not peer-reviewed): Lists interruptibility and approval requirements as baseline practices, with open questions on operationalizing them.
- [AMP-034](paper-corpus/digest.md#amp-034) (not peer-reviewed): Instance IDs help identify who can shut a system down, a precondition for targeted cancellation.
- [AMP-070](paper-corpus/digest.md#amp-070) (not peer-reviewed): Recording irreversible tool effects supplies the information needed for non-rollback warnings after cancellation.
- [AMN-053](news-corpus/digest.md#amn-053) (news: fact): MCP 2025-11-25 experimental Tasks define working, input-required, completed, failed and cancelled states; states, not guarantees about side effects.
- [AMN-069](news-corpus/digest.md#amn-069) (news: fact): MCP roadmap prioritizes retry and expiry semantics for Tasks, confirming they were undefined.
- …and 1 more partial: [AMN-027](news-corpus/digest.md#amn-027).

**Background:** [AMN-063](news-corpus/digest.md#amn-063), [AMN-088](news-corpus/digest.md#amn-088), [AMN-097](news-corpus/digest.md#amn-097), [AMP-002](paper-corpus/digest.md#amp-002).

**Reading.** There is no direct evidence. Protocols define a *cancelled* state (AMN-053), and the MCP roadmap acknowledges missing expiry and retry semantics (AMN-069). No item studies a cancellation racing an external action, or the observable states after cancelling at each stage (before dispatch, while queued, during a tool call, after remote commit).

### AM-11 (P1): How should semantic compatibility be negotiated?

Direct 0 · partial 9 · background 5.

**Direct:** none in either corpus.

**Strongest partial:**

- [AMP-003](paper-corpus/digest.md#amp-003) (peer-reviewed): Shared ontologies translated across representation systems address meaning preservation, the classic semantic-compatibility approach.
- [AMP-006](paper-corpus/digest.md#amp-006) (peer-reviewed): Argues semantics based on private mental states are unverifiable in open systems and should rest on observable commitments, relevant to what can be negotiated and checked.
- [AMP-021](paper-corpus/digest.md#amp-021) (peer-reviewed): HuggingGPT routes subtasks by models' textual function descriptions, showing capability claims drive delegation without verification.
- [AMP-041](paper-corpus/digest.md#amp-041) (peer-reviewed): Agent integration protocol and dynamic teaming for heterogeneous third-party agents.
- [AMP-052](paper-corpus/digest.md#amp-052) (peer-reviewed): Capability-aware name resolution in ANS.
- [AMP-038](paper-corpus/digest.md#amp-038) (not peer-reviewed): Agora lets agents negotiate standardized routines, natural language or LLM-written routines and copes with changing interfaces; protocol-level, not policy or memory-semantics negotiation.
- …and 3 more partial: [AMN-071](news-corpus/digest.md#amn-071), [AMN-088](news-corpus/digest.md#amn-088), [AMN-061](news-corpus/digest.md#amn-061).

**Background:** [AMN-009](news-corpus/digest.md#amn-009), [AMN-069](news-corpus/digest.md#amn-069), [AMN-082](news-corpus/digest.md#amn-082), [AMN-087](news-corpus/digest.md#amn-087), [AMP-010](paper-corpus/digest.md#amp-010).

**Reading.** There is no direct evidence. Version and capability declaration exists (A2A v1.0 version negotiation, MCP `_meta` capabilities), and Agora (AMP-038) negotiates communication routines. Nothing negotiates policies, tool preconditions or memory semantics, or reports a forced downgrade or rejection.

### AM-12 (P1): Can copying, cloning, replication and multiplication share a safe common model?

Direct 0 · partial 5 · background 5.

**Direct:** none in either corpus.

**Strongest partial:**

- [AMP-062](paper-corpus/digest.md#amp-062) (peer-reviewed): Self-replicating prompts spread super-linearly across connected applications, the uncontrolled-replication failure case (of content, not agents).
- [AMP-072](paper-corpus/digest.md#amp-072) (peer-reviewed): Injected prompts copy themselves agent to agent; defences reduce spread.
- [AMP-070](paper-corpus/digest.md#amp-070) (not peer-reviewed): Enforces replay-or-fork semantics on restore, distinguishing a fork from a continuation, but only at checkpoint-restore time.
- [AMN-077](news-corpus/digest.md#amn-077) (news: vendor-claim): DBOS can fork a workflow from a chosen step to rerun later steps; vendor feature for divergent copies.
- [AMN-080](news-corpus/digest.md#amn-080) (news: vendor-claim): Session API stores conversations as forkable trees and runs sub-agents as child Durable Objects with isolated databases; vendor preview.

**Background:** [AMN-057](news-corpus/digest.md#amn-057), [AMP-001](paper-corpus/digest.md#amp-001), [AMP-021](paper-corpus/digest.md#amp-021), [AMP-027](paper-corpus/digest.md#amp-027), [AMP-063](paper-corpus/digest.md#amp-063).

**Reading.** There is no direct evidence. The corpus documents the uncontrolled replication of malicious *content* (AMP-062, AMP-072) and vendor fork primitives (AMN-077, AMN-080). It has nothing on lineage IDs, stale-replica fencing, budget ceilings or coordinated cancellation for cloned or fanned-out agents.

### AM-13 (P1): Who controls approval, deletion, retention and provenance after transfer?

Direct 0 · partial 13 · background 5.

**Direct:** none in either corpus.

**Strongest partial:**

- [AMP-033](paper-corpus/digest.md#amp-033) (peer-reviewed): Assesses agent identifiers, real-time monitoring and activity logging across centralized and decentralized supply chains, including privacy implications.
- [AMP-045](paper-corpus/digest.md#amp-045) (peer-reviewed): Agent infrastructure for attributing actions and detecting and remedying harm.
- [AMP-068](paper-corpus/digest.md#amp-068) (peer-reviewed): Capability tags on values carry provenance and authorization along data flows.
- [AMP-026](paper-corpus/digest.md#amp-026) (not peer-reviewed): Proposes attributability, approval and legibility of activity as baseline governance practices.
- [AMP-034](paper-corpus/digest.md#amp-034) (not peer-reviewed): Instance IDs let investigators attribute incidents to a specific session.
- [AMN-044](news-corpus/digest.md#amn-044) (news: fact): Atlas memories are optional and manageable with opt-out and incognito browsing.
- …and 7 more partial: [AMN-063](news-corpus/digest.md#amn-063), [AMN-068](news-corpus/digest.md#amn-068), [AMN-070](news-corpus/digest.md#amn-070), [AMN-089](news-corpus/digest.md#amn-089), [AMN-012](news-corpus/digest.md#amn-012), [AMN-030](news-corpus/digest.md#amn-030), [AMN-075](news-corpus/digest.md#amn-075).

**Background:** [AMN-002](news-corpus/digest.md#amn-002), [AMN-065](news-corpus/digest.md#amn-065), [AMN-083](news-corpus/digest.md#amn-083), [AMN-084](news-corpus/digest.md#amn-084), [AMP-043](paper-corpus/digest.md#amp-043).

**Reading.** There is no direct evidence. The corpus has accountability and logging proposals (AMP-026, AMP-033, AMP-034) and one court-ordered deletion (AMN-070). No item addresses deletion propagation, retention TTLs or consent evidence across administrative domains after a transfer.

### AM-14 (P1): How much does movement *actually* improve outcomes?

Direct 0 · partial 12 · background 3.

**Direct:** none in either corpus.

**Strongest partial:**

- [AMP-013](paper-corpus/digest.md#amp-013) (peer-reviewed): Explains why process migration saw little adoption despite clear benefits.
- [AMP-014](paper-corpus/digest.md#amp-014) (peer-reviewed): Measures when a mobile agent with execution state outperforms client/server calls in an IR application; pre-LLM cost model.
- [AMP-018](paper-corpus/digest.md#amp-018) (peer-reviewed): Identifies which container migration technique suits which network and service conditions.
- [AMP-027](paper-corpus/digest.md#amp-027) (peer-reviewed): Reports dynamically composed agent groups outperform a single agent.
- [AMP-035](paper-corpus/digest.md#amp-035) (peer-reviewed): Live migration of LLM requests with KV-cache state gives an order-of-magnitude tail-latency improvement and up to 36% cost savings; serving layer, not agent tasks.
- [AMP-042](paper-corpus/digest.md#amp-042) (peer-reviewed): Multi-agent systems often deliver minimal benchmark gains, a caution for the delegation baseline.
- …and 6 more partial: [AMP-056](paper-corpus/digest.md#amp-056), [AMP-060](paper-corpus/digest.md#amp-060), [AMP-074](paper-corpus/digest.md#amp-074), [AMP-048](paper-corpus/digest.md#amp-048), [AMN-035](news-corpus/digest.md#amn-035), [AMN-077](news-corpus/digest.md#amn-077).

**Background:** [AMP-011](paper-corpus/digest.md#amp-011), [AMP-015](paper-corpus/digest.md#amp-015), [AMP-046](paper-corpus/digest.md#amp-046).

**Reading.** There is no direct evidence. Classic (AMP-014) and serving-layer (AMP-035) results show that relocation can pay off, and memory papers quantify a compact memory against full-transcript replay (AMP-060, AMP-074). None compares, for agent tasks, the four baselines AM-14 specifies: restart, A2A delegation, same-runtime relocation and cross-runtime reconstruction.

### AM-15 (P1): How should movement be benchmarked fairly?

Direct 0 · partial 6 · background 4.

**Direct:** none in either corpus.

**Strongest partial:**

- [AMP-039](paper-corpus/digest.md#amp-039) (peer-reviewed): AgentDojo is an extensible, adaptive evaluation environment with paired utility and security cases; models fail many tasks even without attack, so baselines must be reported.
- [AMP-040](paper-corpus/digest.md#amp-040) (peer-reviewed): ASB proposes a metric balancing utility and security across backbones.
- [AMP-042](paper-corpus/digest.md#amp-042) (peer-reviewed): MAST provides a failure taxonomy and an LLM-as-judge annotator validated against human labels.
- [AMP-059](paper-corpus/digest.md#amp-059) (not peer-reviewed): Agent Spec includes a standardized evaluation harness for comparing behaviour across runtimes on three benchmarks.
- [AMN-074](news-corpus/digest.md#amn-074) (news: fact): Over 250,000 attack attempts by 400+ participants against 13 models, a large-scale design that surfaces cross-model transfer.
- [AMN-023](news-corpus/digest.md#amn-023) (news: vendor-claim): A2A evaluation in Vertex GenAI Evaluation Service and a Technology Compatibility Kit for conformance; vendor tooling.

**Background:** [AMN-002](news-corpus/digest.md#amn-002), [AMN-039](news-corpus/digest.md#amn-039), [AMP-031](paper-corpus/digest.md#amp-031), [AMP-068](paper-corpus/digest.md#amp-068).

**Reading.** There is no direct evidence. Security benchmarks (AMP-039, AMP-040) and a failure taxonomy with a validated LLM judge (AMP-042) provide methods to reuse. No benchmark targets movement or continuation, and no summary mentions pre-registration or repeated-run variance.

### AM-16 (P1): Where should interoperability be standardized instead of duplicated?

Direct 2 · partial 10 · background 6.

**Direct:**

- [AMN-028](news-corpus/digest.md#amn-028) (news: fact): IBM's ACP merged into A2A and stopped active development, with adapters and a migration guide; direct evidence of consolidating rather than duplicating agent protocols.
- [AMN-087](news-corpus/digest.md#amn-087) (news: fact): IETF agentproto BoF supported the need for interoperability (155-30) but rejected the initial scope (38-124), and participants proposed narrowing to context propagation across trust boundaries.

**Strongest partial:**

- [AMP-010](paper-corpus/digest.md#amp-010) (peer-reviewed): Discusses practical adoption problems of the 1990s ACL standards, a historical lesson on duplicated standards.
- [AMP-050](paper-corpus/digest.md#amp-050) (not peer-reviewed): Classifies protocols as context-oriented vs inter-agent and general vs domain-specific, mapping where layers already exist.
- [AMP-051](paper-corpus/digest.md#amp-051) (not peer-reviewed): Compares MCP, ACP, A2A and ANP on interaction modes, discovery and security and suggests a phased adoption path.
- [AMP-059](paper-corpus/digest.md#amp-059) (not peer-reviewed): Agent Spec is existing prior art for definition portability that the project should reuse.
- [AMN-053](news-corpus/digest.md#amn-053) (news: fact): MCP 2025-11-25 introduced an extensions framework.
- [AMN-064](news-corpus/digest.md#amn-064) (news: fact): MCP Apps shipped as the first official MCP extension rather than a new protocol.
- …and 4 more partial: [AMN-088](news-corpus/digest.md#amn-088), [AMN-091](news-corpus/digest.md#amn-091), [AMN-005](news-corpus/digest.md#amn-005), [AMN-060](news-corpus/digest.md#amn-060).

**Background:** [AMN-009](news-corpus/digest.md#amn-009), [AMN-014](news-corpus/digest.md#amn-014), [AMN-056](news-corpus/digest.md#amn-056), [AMN-066](news-corpus/digest.md#amn-066), [AMN-094](news-corpus/digest.md#amn-094), [AMP-005](paper-corpus/digest.md#amp-005).

**Reading.** The news corpus shows three trends: consolidation (ACP merged into A2A, AMN-028), extensions rather than new protocols (MCP Tasks and Apps), and an unresolved IETF scoping debate (AMN-087). This is direct evidence of *where the community is* standardizing, but it does not settle where a task/checkpoint profile should live. Both direct items are news facts; no research paper addresses the question directly.

## 4. Evidence gaps

Of the **37 direct links**, **30 fall on three questions: AM-05, AM-06 and AM-09** (authority, context leakage and destination trust). **Eight of the 16 questions have no direct evidence at all**, including three P0 questions. Three more P0 questions rest on a single item each, and for AM-03 and AM-04 that item is the same non-peer-reviewed preprint (AMP-070).

**Ranking rule.** Questions are ranked by the number of direct items (fewest first), then P0 before P1, then by the number of partial items (fewest first). A low rank number means the largest gap. The ranking reflects these two corpora only; §1 explains why it partly mirrors the corpus themes.

| Gap rank | ID | Priority | Direct | Partial | What is missing |
|---:|---|---|---:|---:|---|
| 1 | AM-08 | P0 | 0 | 7 | Any measurement of a different model continuing the same snapshot |
| 2 | AM-10 | P0 | 0 | 7 | Cancellation and revocation behaviour under races with external actions |
| 3 | AM-07 | P0 | 0 | 12 | A cross-framework checkpoint and field-level loss report |
| 4 | AM-12 | P1 | 0 | 5 | Lineage, fencing and budgets for clones, forks and fan-out |
| 5 | AM-15 | P1 | 0 | 6 | A benchmark that targets movement and continuation |
| 6 | AM-11 | P1 | 0 | 9 | Negotiation of semantic (policy, tool, memory) compatibility |
| 7 | AM-14 | P1 | 0 | 12 | Movement compared against restart and delegation baselines for agent tasks |
| 8 | AM-13 | P1 | 0 | 13 | Deletion, retention and consent across domains after transfer |
| 9 | AM-03 | P0 | 1 | 6 | Fencing and lease evidence for agent handoff (single preprint only) |
| 10 | AM-04 | P0 | 1 | 6 | Reconciliation of ambiguous external outcomes (same single preprint) |
| 11 | AM-01 | P0 | 1 | 15 | A comparison of portable units, and restoration loss beyond definitions |
| 12 | AM-02 | P0 | 2 | 9 | An evaluation of task lineage across physical executors (proposals only) |
| 13 | AM-16 | P1 | 2 | 10 | Research, rather than news, on protocol layering |
| 14 | AM-05 | P0 | 8 | 17 | Handoff-specific negative tests (wrong audience, revoked grant, offline queue) |
| 15 | AM-06 | P0 | 10 | 7 | Legal and consent rules for what may cross, beyond attack studies |
| 16 | AM-09 | P0 | 12 | 11 | Evaluations showing that signed cards and registries stop the demonstrated attacks |

### Suggested search queries for the next corpus round

The queries below are starting points for the next collection round. They are not results. For each gap they target scholarly sources (arXiv, ACM DL, USENIX, IEEE) first, then standards bodies.

- **AM-08 (model change):**
  - `"specification portability" LLM development agents` (to add [S7] from open-questions.md)
  - `cross-model continuation LLM agent task drift evaluation`
  - `prompt transferability across language models agent behavior consistency`
  - `model substitution mid-task agent reliability`
- **AM-10 (cancellation):**
  - `cancellation semantics long-running agent tasks side effects`
  - `saga compensation LLM agent tool calls`
  - `durable workflow cancellation guarantees race external activity`
  - `A2A CancelTask semantics evaluation`
- **AM-07 (cross-framework checkpoint):**
  - `cross-framework agent state migration LangGraph AutoGen CrewAI`
  - `agent workflow checkpoint interoperability adapter loss`
  - `Open Agent Specification cross-framework comparison CAIS 2026` (the peer-reviewed [S6], absent from the corpus)
  - `workflow engine migration state translation`
- **AM-12 (copy/clone/replicate):**
  - `LLM agent forking cloning lineage tracking`
  - `multi-agent memory consistency concurrent updates merge`
  - `runaway agent spawning resource budget containment`
  - `stale replica fencing agent orchestration`
- **AM-15 (benchmarking):**
  - `LLM agent benchmark reproducibility variance repeated runs`
  - `statistical rigor agent evaluation seeds confidence intervals`
  - `pre-registration machine learning benchmark negative results`
- **AM-11 (semantic compatibility):**
  - `capability negotiation heterogeneous LLM agents semantic interoperability`
  - `agent capability attestation verification advertised vs actual`
  - `policy compatibility negotiation multi-agent delegation`
- **AM-14 (value of movement):**
  - `checkpoint resume vs restart LLM agent cost latency`
  - `agent migration versus re-execution benchmark`
  - `delegation overhead token cost multi-agent versus single agent`
- **AM-13 (cross-domain governance):**
  - `deletion propagation multi-agent systems data retention`
  - `GDPR right to erasure AI agent memory`
  - `W3C PROV provenance LLM agent workflows`
  - `cross-organization audit log AI agents privacy-preserving`
- **AM-03 / AM-04 (duplicate and ambiguous effects):**
  - `fencing token lease failover exactly-once agent tool execution`
  - `idempotency keys LLM agent tool calls duplicate side effects`
  - `ambiguous outcome reconciliation retries payments agent`
  - `transactional outbox AI agent actions`
- **AM-01 / AM-02 (portable unit and lineage):**
  - `portable agent state serialization format evaluation`
  - `agent task envelope schema handoff`
  - `agent instance identity lineage provenance delegation chain SPIFFE`

**Corpus-composition note.** The AM-05/06/09 cluster is well covered partly because the collection protocol gave security and identity three dedicated themes. The durable-execution theme (T4/P5) yielded mostly vendor announcements and memory-system papers rather than measurements of resumption safety. The next round should give AM-07/08/10/14 their own collection themes rather than relying on keyword overlap.

## 5. How to use and update

- Filter [`data/evidence-map.csv`](../data/evidence-map.csv) by `question_id` for a question's full evidence list, or by `item_id` to see which questions an item supports.
- When the corpora grow, re-code new items with the same three levels and caps. Do not upgrade existing rows from vendor claims without new evidence.
- A second, independent coder applying §1 to a random sample of rows would turn these counts into a measured-reliability result. That has not been done.

## 6. Self-check

Run from the repository root:

```bash
python3 -c "import csv,json,re; ids={json.loads(l)['id'] for f in ('docs/paper-corpus/papers.jsonl','docs/news-corpus/news.jsonl') for l in open(f)}; qs=set(re.findall(r'^\| (AM-\d\d) \|',open('docs/open-questions.md').read(),re.M)); rows=list(csv.DictReader(open('data/evidence-map.csv'))); print(len(rows),'rows,',len({r['item_id'] for r in rows}),'distinct items,',len(qs),'question IDs in open-questions.md'); print('unknown item_ids:',sorted({r['item_id'] for r in rows}-ids)); print('unknown question_ids:',sorted({r['question_id'] for r in rows}-qs)); print('strength values:',sorted({r['strength'] for r in rows})); print('duplicate pairs:',len(rows)-len({(r['question_id'],r['item_id']) for r in rows}))"
```

Output on 2026-10-16:

```text
257 rows, 145 distinct items, 16 question IDs in open-questions.md
unknown item_ids: []
unknown question_ids: []
strength values: ['background', 'direct', 'partial']
duplicate pairs: 0
```
