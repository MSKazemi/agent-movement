# Underexplored dimensions of agent movement: gap audit and proposed experiments

**Reviewed:** 2026-10-16  
**Status:** Research-gap assessment and proposed studies. No new feature, assurance claim, experiment score, legal conclusion, or proof of novelty is implied.  
**Repository:** [MSKazemi/agent-movement](https://github.com/MSKazemi/agent-movement), default branch "main" reviewed on 2026-10-16.  
**Scope:** Authorized movement of software-agent tasks, selected state and capabilities among runtimes, devices and administrative domains. Physical actuation is only considered through controlled simulations.

## Executive finding

> **Implementation status (2026-10-16):** [PR #84](https://github.com/MSKazemi/agent-movement/pull/84) adds a research-only continuity admission checker, a 10-case synthetic oracle and negative unit tests for several of the priority gaps. It is not integrated with an independently controlled runtime policy enforcement point.

The project already treats *how* agent work moves unusually thoroughly: definitions and operations; lifecycle, death and replication; A2A/MCP; checkpointing; peer authentication; authorization; hidden/unauthorized movement; fingerprints and receipts; safety and human-impact questions; device compatibility; and synthetic MobilityBench baselines.

The more important *underweighted dimensions* concern the **control and meaning of movement over time**:

1. **Multiple legitimate principals**, with potentially conflicting authority, consent and duties.
2. **Obligations that must survive transfers**, not just permissions that may be exercised.
3. **Self-modification and material configuration change** while an agent is running or moving.
4. **State contamination, compromise recovery and quarantine**, especially across descendant branches.
5. **Real human supervision**, including comprehensible consent, revocation and recourse.
6. **Freshness of facts about the world** when a checkpoint resumes elsewhere.
7. **Operational, legal and cross-organization validation** beyond a local synthetic laboratory.

These themes should be added as falsifiable studies, not marketed as unsolved research or guaranteed security properties.

## Audit method and limitations

Reviewed the repository tree, README, roadmap, existing major research documents, prototype/module list and issue/PR backlog as visible on 2026-10-16. In particular:

- [Open questions](open-questions.md): AM-01–AM-16 already name identity, state portability, fencing, revocation, safe context, model changes and benchmark validity.
- [2031 agenda](2031-frontier-research-agenda.md): FM-01–FM-20 already cover intent drift, fork/merge, descendant closure, memory infection, budgeting, offline safety, collective outcomes and sustainability.
- [Communication policy](agent-communication-and-policy.md), [lifecycle](agent-lifecycle-liveness-and-death.md), [forensics](agent-forensics-and-fingerprints.md) and [unnoticed movement](unnoticed-and-unauthorized-agent-movement.md) address several related threats.
- [MobilityBench](mobilitybench-v0.1.md) and [local implementation](local-implementation.md) explicitly limit current evidence to synthetic/local experiments.
- Existing tickets cover aspects of interoperability [#28](https://github.com/MSKazemi/agent-movement/issues/28), prompt injection [#35](https://github.com/MSKazemi/agent-movement/issues/35), economics [#36](https://github.com/MSKazemi/agent-movement/issues/36), runtime revocation [#38](https://github.com/MSKazemi/agent-movement/issues/38), retention [#39](https://github.com/MSKazemi/agent-movement/issues/39) and fault injection [#40](https://github.com/MSKazemi/agent-movement/issues/40).

**Important distinction:** "New emphasis" means a first-class threat model or study is not readily apparent in the reviewed main-branch materials; it does **not** mean the subject has never been mentioned or studied elsewhere. "Partial" means the repository already discusses a related dimension, but a measurable end-to-end test or operational contract remains to be defined. Open pull requests can change the picture. This is a qualitative assessment, not a systematic external literature review.

## Ranked gap map

| ID | Priority | Dimension and example question | Coverage assessment | Minimum research deliverable |
| --- | --- | --- | --- | --- |
| **G01** | **P0** | **Multi-principal authority.** If a task user approves movement but the data owner, device owner or destination organization refuses, who can authorize what? | New first-class test area. Existing grant/delegation research is mostly framed around a single authority root. | Explicit principals, mandatory consent predicates, conflict policy, denial-before-disclosure matrix. |
| **G02** | **P0** | **Obligation continuity.** Do deletion duties, retention ceilings, audit commitments, spending limits and notification requirements survive every handoff and fork? | Partial: grants, deletion and budgets exist separately; obligations are not a unified portability contract. | Versioned obligation manifest and downstream acknowledgment/violation test. |
| **G03** | **P0** | **Material self-change.** Can a moved agent update its tools, system instructions, code, model, plugins or policy engine without invalidating previously approved authority? | New first-class test area. Model compatibility on planned moves is documented, but agent-initiated change is not central. | Immutable declared-component manifest, change classification, reapproval rules and mutation tests. |
| **G04** | **P0** | **Compromise and contaminated-state recovery.** How does a previously trusted checkpoint become untrusted after a malicious recipient, poisoned retrieval result or compromised tool? | Partial: memory propagation and prompt injection are documented; recovery/admission from suspect state is less developed. | Quarantine/admission protocol with synthetic taint provenance, uncertainty and independent enforcement. |
| **G05** | **P0** | **Usable human control.** Can a person understand the recipient, data exposure, tool authority, cost and revocation limits in time to make a meaningful decision? | New first-class human-factors evaluation. Approval is specified more than approval quality is measured. | Comprehension and decision-quality study; readable move receipts and descendant view. |
| **G06** | **P0** | **Time and environmental freshness.** Which carried facts expire when an agent resumes later or on another device? | New first-class test area. General timeouts/deadlines exist; freshness of individual assertions is underdeveloped. | Typed evidence TTL, source and re-observation rule; simulated stale-world fault matrix. |
| **G07** | P1 | **Cross-domain legal/data/IP constraints.** What restrictions on purpose, geographic storage, licenses and onward sharing remain enforceable after a move? | Partial: privacy, retention and data residency are mentioned; there is no scenario-specific legal requirements matrix. | Constraint provenance and a jurisdiction-agnostic contract vocabulary, with expert/legal review before claims. |
| **G08** | P1 | **Security operations and recovery.** How are running descendants affected by key rotation, certificate expiry, incident declarations, policy upgrades and emergency isolation? | Partial: identity, liveness and revocation are discussed; complete runbooks and drills are not yet demonstrated. | Operational tabletop and executable synthetic emergency drill; record unknown/unreachable participants. |
| **G09** | P1 | **Identity repair after compromise.** How are trustworthy lineage and grants re-established when a signing key, issuer or runtime attestation source is compromised? | Partial: forensics and signatures exist; root-of-trust recovery is a separate exercise. | Key-compromise fixture; scope-bounded recovery, distrust and reissuance report. |
| **G10** | P1 | **Incentives, collusion and agent marketplaces.** Can agents manipulate rankings, form resource-cartels, misreport capability or transfer costs to a different stakeholder? | Partial: registry reputation and collective governance appear in existing agendas. | Small adversarial allocation game with Sybil-resistant assumptions made explicit, false claims and measurable damage. |
| **G11** | P1 | **Remedy after irreversible effects.** Who handles a wrong purchase, data disclosure or physical command when stopping the agent cannot undo it? | Partial: AM-04/AM-10 explicitly reject simplistic rollback and describe unknown outcomes; actual compensation/appeal is not tested. | Synthetic compensation saga with human escalation, residual-harm report and at-least-once caveats. |
| **G12** | P1 | **Supply-chain admission and compatibility drift.** Do approved image, package, prompt, model, skill and tool versions remain trustworthy after relocation and future updates? | Partial: version/capability pinning and broad supply-chain threats exist. | Signed/versioned manifest plus verification at admission and at a material-change boundary. |
| **G13** | P1 | **External validity.** Which results survive a second independent implementation, distinct organizations, realistic outages and different human operators? | Recognized but not completed: [#28](https://github.com/MSKazemi/agent-movement/issues/28) and [#40](https://github.com/MSKazemi/agent-movement/issues/40) already support parts. | Pre-registered multi-implementation comparative report; mark unsupported cases instead of guessing. |
| **G14** | P2 | **Fairness, accessibility and unequal power.** Who is excluded by complex approval interfaces, expensive trusted hardware or contractual prerequisites for safe mobility? | Partial: general societal impacts are in [human-impact questions](top-20-human-impact-questions-for-agentic-ai.md). | Accessibility and policy-disparity evaluation for distinct stakeholder scenarios. |

## A crucial distinction: authority, obligations and evidence

A sound transfer needs **three different ledgers**, which should not be conflated:

1. **Authority:** what a recipient is allowed to do now, under whose grant, for which resources, until when. Neither a signed message nor the agent's own statement creates this permission.
2. **Obligations:** what the recipient must continue to honor, including purpose limitations, deletion deadlines, limits on further delegation, and user-visible notices. Carrying text that describes a duty is not proof the recipient will fulfill it.
3. **Evidence:** what independently checkable records establish about a specific event or control decision. Missing events must remain "unknown"; a digest does not make contaminated content true or safe.

**Candidate invariant:** for each protected effect and disclosure, all required principal authorizations must be valid, the destination must satisfy applicable obligations, and the effect-side enforcement point must verify the grant; if any mandatory input is unknown, the tested protected effect is denied or parked for reconciliation. This is an **architecture-specific condition**, not a proof that arbitrary agent code on arbitrary devices cannot bypass a gateway.

A proposed portability object may therefore include *references*, not reusable credentials:

| Field family | Example | Guardrail |
| --- | --- | --- |
| Principals | Task requester, data controller, device owner, deploying organization and policy issuer | Never infer authorization merely from organizational affiliation. |
| Delegable authority | Audience, action/resource scopes, maximum depth, expiry, epoch and grant reference | Reissue narrow downstream grants; independent effect-side enforcement. |
| Portable obligations | Purpose, data class, retention/deletion deadline, no-redisclosure flag, audit duty, human escalation route | Enforce where technically possible; record unenforceable/unknown duties. |
| State provenance | Source class, signature/digest reference, trust status, source time, validation time and taint flags | Source integrity differs from semantic correctness. |
| Configuration evidence | Versioned model, code, tool and policy manifest plus change epoch | Material changes trigger compatibility and authorization review. |
| Resolution status | Granted, denied, disputed, awaiting consent or unknown/reconcile | Never silently translate missing permission into yes. |

## Proposed experiments (none are implemented by this document)

### Study 1 — MultiPrincipalBench: conflicting humans and organizations (G01 + G02)

**Question:** When users, dataset owners, device owners and hosting administrators disagree, can the system reject prohibited moves without hiding the reason or carrying an invalid obligation?

**Design:** Create synthetic 2–4-principal fixtures covering affirmative consent, absent consent, explicit denial, expiring grants, user withdrawal, mixed retention duties, descendant delegation and contradictory destination policy. Use a separate oracle that specifies which principals are mandatory for each operation; do not hard-code "one principal always wins" without an actual rights model.

**Measurements:** violation count at a simulated protected disclosure/effect gateway; mandatory-approval recall; false denials; missing/altered obligation rate after 1–4 handoffs; quality of machine-readable rejection reasons.

**Falsifier:** any accepted protected operation without a required approval, or any silently broadened right/relaxed obligation.

### Study 2 — MutationGate: permissions under agent self-change (G03 + G12)

**Question:** Does a previously authorized agent retain authority after changing the components that justified trust?

**Design:** Synthetic changes to prompt/config, model identifier, model version, tool manifest, executable digest, safety policy and allowed capabilities between prepare/dispatch/resume/effect. Freeze one declared manifest per authorization epoch, classify changes by materiality and require a new decision before protected effects if materially changed.

**Measurements:** unauthorized-change acceptance rate, false reapproval requests, upgrade recovery, dependency drift, ability to explain exactly what changed.

**Falsifier:** an unapproved material configuration change uses the old grant to perform a protected action.

**Limit:** a manifest proves which configuration was declared/checked at a boundary, not that the model's output is safe or a hostile host is honest.

### Study 3 — QuarantineBench: tainted checkpoints (G04 + G09)

**Question:** Can safe-looking serialized state spread untrusted instructions, compromised preferences or false evidence after a move, clone and resume?

**Design:** Only benign, synthetic poison markers and fake tool/output fixtures; compare naive import, provenance filters, taint-labeled summaries and quarantine/manual re-admission. Add a case where the signing key itself is no longer trusted. Include useful but imperfect state that a defense should not simply delete.

**Measurements:** fraction of prohibited synthetic effects attempted/accepted; taint propagation by hop; useful-memory retention; false quarantine; percentage of uncertainty explicitly reported.

**Falsifier:** suspect state is considered safe solely because its bytes match a previously signed digest.

**Limit:** absence of marker propagation in a fixed suite does not establish detection of arbitrary prompt injection or compromised models.

### Study 4 — HumanControlBench: understandable consent and revocation (G05 + G14)

**Question:** Can people tell delegation from relocation, identify who receives which data, locate active descendants and stop future authorized actions?

**Design:** Prototype an approval summary, movement timeline, revocation view and independent observation panel for synthetic scenarios; test comprehension before implementation and, subject to appropriate ethics/privacy procedures, with consenting participants.

**Measurements:** correct identification of recipient, disclosure and authority; unsafe approvals; false beliefs that cancellation undoes past actions; time to revoke; perceived workload and accessibility barriers.

**Falsifier:** a "safe" technical workflow systematically causes people to approve transfers they misunderstand or believe they can reverse when they cannot.

### Study 5 — FreshnessBench: stale world-state after movement (G06)

**Question:** Which context survives a delay, a model change or a move from cloud to edge without causing an unsafe decision?

**Design:** Simulated sensor/price/location/capability inputs with separately stamped observation times, validity windows and source reliability; inject partitions, clocks with skew, destination state changes and stale cached artifacts. Require re-observation before a protected effect when the evidence is too old or unverifiable.

**Measurements:** stale-data acceptance, revalidation cost, task quality, false refusals, missed deadlines and unsafe synthetic effect attempts.

**Falsifier:** a destination treats an expired, materially relevant observation as current solely because the checkpoint is valid.

### Study 6 — EmergencyRestore: incident and compensation practice (G07–G11 + G13)

**Question:** Can an operator isolate known descendants, rotate compromised keys, discover what remained outside reach, and reconcile or compensate already committed simulated actions?

**Design:** Sandbox disaster drill with one unreachable receiver, one revoked grant, one compromised issuer, an ambiguous tool acknowledgment and one synthetic irreversible action. Compare actual tool-side records with coordinator and forensics claims.

**Measurements:** time to fence covered sinks, false claim of global shutdown, unresolved-effects count, compromised-key acceptance, human interventions and residual effects after compensation.

**Falsifier:** a "complete" incident report ignores unknown descendants or reports an irreversible effect as undone.

## Prioritization and next 90 days (proposal)

### Days 1–30: define what must not be lost

- Adopt a single **multi-principal authorization + obligation continuity** threat model; enumerate rights and duties, with explicit authority sources.
- Define a versioned **material-change manifest** and pin configuration at grant time.
- Create frozen synthetic fixtures and expected oracle decisions for Study 1, Study 2 and Study 5.
- Cross-reference existing FM/AM research questions rather than renumber or replace them. Coordinate with pending policy PRs and existing issues.

**Exit gate:** every synthetic fixture has a stated mandatory permission, obligation, source-freshness assumption, expected outcome and an independent fake effect-side oracle.

### Days 31–60: implement independent tests

- Add tests to the existing Python/MobilityBench harness without a new general-purpose transport protocol.
- Refuse protected effects when authority or crucial context cannot be validated.
- Compare against a deliberately naive baseline, publish false positives and false refusals, and keep all side effects simulated.
- Add adversarial component-manifest changes and poisoned-state admission cases.

**Exit gate:** repeatable negative cases pass; intentionally unsafe baseline cases fail; limitations are recorded.

### Days 61–90: study humans and cross-boundary repair

- Prototype transparent approval/revocation/descendant views and conduct an ethics-reviewed study if humans are involved.
- Run a sandbox incident drill with key compromise, network partitions and incomplete evidence.
- Use a second independent SDK/worker when feasible; compare costs and outcomes with keep/restart/delegate/relocate baseline arms.
- Decide whether multi-principal obligation continuity or self-change gating merits a standalone paper/working group.

**Exit gate:** a pre-registered, version-pinned report with per-case results, unsuccessful cases, measured human effort and no unsupported blanket security claims.

## Do not count these as forgotten topics

The following are **already substantially recognized** in this repository and should be **implemented or measured** before creating redundant agenda sections:

- Delegation versus copying versus cloning versus relocation versus live migration: [movement taxonomy](agent-movement-vs-copy-replication-multiplication.md).
- Lifecycle, liveness, death, orphaned descendants and inability to prove arbitrary global erasure: [lifecycle](agent-lifecycle-liveness-and-death.md).
- Multi-hop intent drift, authority conservation, memory propagation, descendant inventories, offline safety and sustainability: [2031 agenda](2031-frontier-research-agenda.md).
- Network/transport interoperability, A2A/MCP boundaries and hardware/device families: [protocol guide](protocols-and-networks/README.md), [device matrix](device-compatibility-and-capability-matrix.md).
- Forensic grades, signed receipts, missing evidence and behavioral-fingerprint limits: [forensics](agent-forensics-and-fingerprints.md), [movement receipts](movement-receipts.md).
- Basic prompt-injection, revocation, budget, data-classification and no-secret-transfer concerns: [security](security-and-trust.md), [communication policy](agent-communication-and-policy.md), [open questions](open-questions.md).

A local signed receipt, a successful simulated fence test or a declared capability profile **does not prove safety in an independently administered deployment**.

## Recommended backlog strategy

Before opening duplicate GitHub issues, check the status of existing work including [#28](https://github.com/MSKazemi/agent-movement/issues/28), [#35](https://github.com/MSKazemi/agent-movement/issues/35), [#36](https://github.com/MSKazemi/agent-movement/issues/36), [#38](https://github.com/MSKazemi/agent-movement/issues/38), [#39](https://github.com/MSKazemi/agent-movement/issues/39), [#40](https://github.com/MSKazemi/agent-movement/issues/40) and the [movement-policy proposal PR #16](https://github.com/MSKazemi/agent-movement/pull/16). The most distinct future issue candidates are **Study 1 multi-principal and obligation continuity**, **Study 2 material-change gating**, **Study 3 quarantine/admission**, **Study 4 human control usability** and **Study 5 evidence freshness**.

## Relevant guidance to evaluate (not proof of implementation)

- NIST AI RMF Playbook: voluntary Govern/Map/Measure/Manage guidance, including oversight, impact and risk management.
- NIST AI RMF Govern guidance: human roles, responsibilities, monitoring and incident/appeal processes; supports treating UX and real governance as engineering requirements.
- NIST SP 800-207A: zero-trust application identity and granular enforcement in multi-cloud settings; does not establish semantics of migrating agent intent.
- OWASP Top 10 for Agentic Applications 2026: relevant security-risk taxonomy; map individual risks to threat cases and actual executable tests before claiming coverage.

**Review note (2026-10-16):** These named frameworks are contextual leads for future source validation. No new external URLs are introduced here until they can be added to the repository's generated URL index; they are not evidence that the proposed studies are novel, implemented, certified or empirically validated.

---

**Bottom line:** The next differentiating research contribution should be **obligation- and authority-preserving mobility under conflicting stakeholders and changing agent behavior**, tested against a genuinely independent enforcement boundary. It is a sharper focus than introducing another wire protocol or a generic agent marketplace.
