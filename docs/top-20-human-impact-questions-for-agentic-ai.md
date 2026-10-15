# Twenty high-impact research questions for AI agents and human life

**Reviewed:** 2026-10-15  
**Scope:** AI systems that plan, use tools, make decisions, delegate or execute tasks; effects on humans during approximately 2026-2035, with longer-term risks explicitly marked.  
**Status:** A reasoned, evidence-informed research agenda, **not** a systematic review, measured global ranking, prediction, or claim that the Agent Movement project already implements solutions.

## Executive conclusion

The most important question is not "Can an AI agent do more?" It is **"Can AI systems act usefully on people's behalf while people remain safe, informed, empowered, and able to contest the outcome?"** For a moving/copying agent, human consent, bounded authority, continuity, privacy and an auditable chain of responsibility must survive every boundary.

This ranking deliberately covers both benefits (health, learning, science, accessibility, prosperity) and dangers (uncontrolled actions, security abuse, job disruption, information manipulation and exclusion). It is **human-impact ranking**, not a ranking of what this particular codebase can solve.

### Why these twenty?

Selection criteria, assessed qualitatively rather than with invented numerical scores:

1. **Reach:** How many people, communities or institutions could be affected?
2. **Consequence:** Death, injury, freedom, rights, economic security, knowledge, or life opportunities.
3. **Likelihood and time horizon:** Plausible exposure this decade; explicitly distinguish uncertain longer-term scenarios.
4. **Irreversibility and propagation:** Could one error spread, be difficult to undo, or undermine an entire system?
5. **Research leverage:** Would a scientific answer improve many systems and sectors rather than one application?

The exact ordering is contestable; ranks 1-10 in particular are close, interconnected, and sensitive to assumptions. The rank of a research problem is **not** the likelihood of its worst-case outcome.

### Evidence anchoring the prioritization

- Stanford's **2026 AI Index** reports large gains in agent computer-use performance but still about a third of tasks failed on the OSWorld benchmark, demonstrating why competence cannot be equated with dependable autonomy [S1].
- The **International AI Safety Report 2026** highlights agent reliability limitations and notes profound disagreement about future loss-of-control likelihood; it explicitly does not conclude that current agents can cause such loss of control [S2].
- **OWASP's 2026 agentic-security risks** include goal hijack, tool misuse, identity/privilege abuse and supply-chain compromise [S3]. NIST's **2026 AI Agent Standards Initiative** explicitly prioritizes trusted, secure, interoperable agents [S4].
- The **ILO's 2025 global index** finds roughly one quarter of workers are in occupations with some generative-AI exposure, but stresses transformation rather than universal job replacement [S5].
- **WHO** highlights healthcare opportunities and dangers of inaccurate or biased outputs [S6]. **UNESCO** stresses human-centred education and learning [S7]; **UNICEF** focuses on children's safety, development, privacy and participation [S8].
- The **IEA's 2025 Energy and AI analysis** projects substantial growth in data-centre electricity demand, with large uncertainties [S9]. Stanford's **2026 science chapter** documents the distance between scientific-task performance and reliable end-to-end reproduction [S10].
- The **OECD's 2026 due-diligence guidance** frames organizational responsibility for AI risks and impacts [S11].

## Ranked questions, human consequences, and falsifiable studies

### 1. Can humans genuinely control, interrupt, and reverse consequential agent actions?

**Why it affects life:** An agent with access to accounts, medicine, transport, finances or workplace systems can cause real loss before anyone sees its answer. Human control is more than a "stop" button: a person must understand the intended action, authorize its scope, withdraw future authority, and learn what cannot be reversed. This is a prerequisite for ordinary people's confidence and autonomy.

**Research:** Define observable checkpoints for permission, pause, cancellation and compensation. **First study:** Simulate 100 high-impact actions with approvals, revocation races and delayed messages; measure unauthorized committed actions, time to stop and accurate warnings about irreversibility. **Agent Movement link:** Preserve user consent and honor cancellation across a handoff (AM-05/10).

### 2. How can high-stakes agents be demonstrably reliable and know when not to act?

**Why it affects life:** Plausible but wrong decisions in healthcare, emergency response, finance, infrastructure or legal assistance can be materially harmful. High task-benchmark scores do not establish reliability under distribution shift, unusual situations, tool outages, malicious content, or uncertainty.

**Research:** Calibrated abstention, escalation thresholds, adversarial scenario testing, out-of-distribution evaluation and independent validation. **First study:** Run the same human-reviewed high-stakes *synthetic* cases with and without a stop/escalation policy; compare severe-error rate, false confidence and timely handoff to a qualified human. **Agent Movement link:** A destination must not silently drop safety constraints when resuming.

### 3. Can we prove **who** an agent represents and constrain its delegated authority?

**Why it affects life:** A person may allow an assistant to book one appointment, not read all emails or spend an unlimited amount. If a task is passed to an unknown organization or copied onto a new device, the recipient must not inherit hidden permissions or impersonate its origin. Without this, routine delegated agents become an attack and fraud surface.

**Research:** Authenticated origin/destination, audience-bound short-lived delegated grants, capability attestation, revocation and per-action authorization. **First study:** Try forged agent identity, expired/wrong-audience grants, privilege escalation and transfer after revocation; measure whether any restricted simulated operation succeeds. **Agent Movement link:** Core authority-transfer protocol (AM-02/05/09).

### 4. Can agents resist goal hijacking, prompt injection and compromised tools?

**Why it affects life:** Ordinary documents, websites, emails or tool outputs may contain malicious instructions. A successful hijack can exfiltrate personal data, manipulate payments, leak secrets or corrupt records at machine speed. An agent's intelligence does not make untrusted input trustworthy.

**Research:** Typed trust boundaries, independent policy enforcement, tool sandboxing, injection detection evaluated against adaptive attackers and provenance of tools. **First study:** Use a corpus of hostile webpages/tool messages against a synthetic agent; count unauthorized tool effects and secrets released, not just whether the model *said* it refused. **Agent Movement link:** Verify the recipient and preserve input classification across transfers.

### 5. Who owns an agent's memory, and can people control what follows them?

**Why it affects life:** Personal assistants can accumulate intimate information about health, work, family, contacts and behavior. Copying or moving an agent multiplies exposure, retention and surveillance risks; some data involve other people who never consented.

**Research:** Field-level purpose limitation, consent and minimization, local-first options, cryptographic integrity, retention/deletion attestations, third-party data policies. **First study:** Seed synthetic records with secret canaries; transfer only permitted fields and test retention/deletion reporting at all destinations. **Agent Movement link:** Portable, privacy-checked task context (AM-06/13). A deletion attestation is not proof of universal deletion.

### 6. If an agent causes harm, can we determine what happened and provide meaningful redress?

**Why it affects life:** A denial of benefits, wrongful accusation, harmful recommendation or irreversible financial action requires a way to challenge the decision and identify responsible deployers/operators. Without evidence, human rights and insurance/legal remedies may be impossible to exercise.

**Research:** Tamper-evident event provenance, trace minimization, human-readable explanations, dispute workflows and explicit accountability allocation. **First study:** Generate synthetic cross-organization incident scenarios and test whether independent reviewers can reconstruct authorizations, side effects, uncertainty and corrective steps without revealing private data. **Agent Movement link:** Executor lineage and movement forensics (AM-02/13).

### 7. Will agentic automation improve livelihoods broadly, or concentrate gains and erode opportunity?

**Why it affects life:** Pay, access to jobs, junior career pathways and skill formation affect billions of people. Productivity gains may enrich workers and customers, but displacement, deskilling and unequal bargaining power are possible; exposure is not equivalent to job loss.

**Research:** Credible causal measurements of job tasks, wages, productivity, transitions, distribution of gains and new firm creation across industries and demographics. **First study:** Pre-register a longitudinal workplace comparison with agent-assisted and conventional workflows; measure job quality, hours, wages, training and error correction, not just output per hour. **Agent Movement link:** Portable agents could reduce tool lock-in, but this repo alone cannot solve labor policy.

### 8. Can medical and care agents measurably improve health without unsafe recommendations or widening disparities?

**Why it affects life:** Better triage, documentation, access, follow-up and discovery could improve health and save lives. Clinical errors, unsupported certainty, privacy breaches or unequal performance on underrepresented groups could also worsen outcomes.

**Research:** Prospective clinical validation, referral and escalation, representative performance, physician oversight and outcome rather than chatbot-satisfaction measures. **First study:** In a non-clinical, de-identified/synthetic simulation, evaluate escalation accuracy across demographics and adverse cases; any real patient deployment requires formal clinical oversight. **Agent Movement link:** Secure, consent-controlled handoff between settings; no production patient data in this repo.

### 9. Can we prevent agents from scaling fraud, cyber abuse and other harmful misuse?

**Why it affects life:** Automation can lower the effort needed to impersonate, scam, harass, or attack many targets simultaneously. Security and public safety impacts can become systemic, including higher-stakes dual-use domains.

**Research:** Abuse-resistant identity, rates/budgets, scoped tool access, anomaly detection, incident response and responsible access controls. **First study:** Test contained synthetic fraud/cyber scenarios with no real targets; evaluate rapid isolation and prevention of privilege propagation. **Agent Movement link:** Do not let a compromised task silently replicate privileges into new execution domains.

### 10. Can future long-horizon agents stay aligned with human purposes under changing conditions?

**Why it affects life:** As systems perform longer sequences, optimize goals, recruit other agents and interact with more tools, apparent short-term compliance is not enough. Goal drift, reward hacking or resistance to correction could cause severe harm. Very extreme loss-of-control scenarios remain uncertain and contested; current systems are not known to possess the full abilities those scenarios require [S2].

**Research:** Persistent goal fidelity, adversarial oversight, hidden-failure detection, model evaluations for long-horizon actions and robust interruptibility. **First study:** Bounded simulated workflows with changing authorized objectives, hidden adversarial incentives and independent audits; measure concealment, constraint drift and shutdown compliance. **Agent Movement link:** A migrated task must not silently gain new goals or broader autonomy.

### 11. Can society preserve shared facts, authentic identity and democratic choice in an agent-filled information environment?

**Why it affects life:** Automated persuasion, impersonation, deepfake production and mass-posting can weaken trust in institutions, journalists, scientific evidence and elections. Attribution needs care: not all online falsehoods are AI-made, and technical provenance alone cannot decide what is true.

**Research:** Content-origin verification, trustworthy source chains, platform governance, civic literacy, privacy-preserving authenticity and evidence of real-world impact. **First study:** Test whether people and independent investigators can distinguish authenticated from unauthenticated synthetic public statements using provenance signals. **Agent Movement link:** Auditable agent identity/lineage can help attribution but does not solve misinformation.

### 12. Can people obtain fair, contestable outcomes when agents participate in consequential decisions?

**Why it affects life:** AI involvement in hiring, benefits, education access, credit and public administration can amplify existing inequities, particularly where people lack the power to appeal. A seemingly accurate average result can hide unacceptable harms to small groups.

**Research:** Group and individual harms, procedural fairness, appeals, accessible explanations, human review and accountability for affected third parties. **First study:** Evaluate synthetic decisions across protected-context scenarios using independent fairness measures and a simulated appeal path. **Agent Movement link:** Keep decision constraints and appeal/audit references intact when cases cross organizations.

### 13. Can AI tutors improve **real learning** without undermining independence or child development?

**Why it affects life:** Personalized tutoring might reach students who lack teachers or resources, but instant answers can also replace reasoning, distort assessment and expose children's private data. Long-term outcomes matter more than engagement or homework completion.

**Research:** Randomized or robust quasi-experimental measurements of delayed retention, transfer of skills, student agency and teacher workload, with age-appropriate safeguards. **First study:** Measure independent performance weeks after tutoring compared with ordinary instruction. **Agent Movement link:** Portable student consent and scoped learning context, never broad student dossiers by default.

### 14. Who gets access to beneficial agents, and who controls their infrastructure?

**Why it affects life:** Language, disability, income, geography, connectivity and cloud/vendor concentration could determine who benefits from automation. Unequal access can intensify social and economic divides even if global averages improve.

**Research:** Accessibility and underrepresented-language evaluation; low-connectivity operation; transparency of pricing; competition, governance and public-interest infrastructure. **First study:** Benchmark identical tasks on low-cost/offline devices and low-resource languages while measuring cost, errors and accessibility. **Agent Movement link:** Interoperability and local-first transfer can reduce some technical lock-in; social inequity requires broader solutions.

### 15. How can agents safely interact with robots, infrastructure and the physical world?

**Why it affects life:** In homes, transport, factories, power grids and hospitals, errors can injure people or disrupt essential services. Real-world safety requires more than the ability to issue an API call; physical constraints, operator responsibility, fallbacks and certification matter.

**Research:** Runtime safety envelopes, deterministic emergency stops, independently verified action boundaries, simulation-to-real validation and human supervision. **First study:** Sandboxed digital-twin scenarios with controlled failures and hard external safety interlocks before any physical deployment. **Agent Movement link:** No task should carry authorization to actuate physical systems just because its state migrates.

### 16. Can scientific agents produce reproducible, verifiable discoveries rather than plausible-looking claims?

**Why it affects life:** Faster validated discoveries could improve treatments, food security, materials, energy and public health. Incorrect analyses, fabricated citations and irreproducible work waste resources and may misdirect policy or clinical research.

**Research:** Evidence provenance, executable experiments, independent replications, calibrated claims and human domain review. **First study:** Give agents public reproducibility tasks with pinned inputs; independently run code, check outputs and measure failure/false-discovery rates. **Agent Movement link:** Signed artifact references and workflow/checkpoint provenance for collaborative labs.

### 17. How can personal/companion agents support well-being without harmful dependence or manipulation?

**Why it affects life:** Assistive conversation can increase accessibility and perceived support, but unhealthy attachment, over-reliance, exploitation and developmental effects raise concerns, especially for children and vulnerable people. The evidence is still developing and context-specific.

**Research:** Longitudinal outcomes, disclosure, user autonomy, escalating to human support, age suitability and non-manipulative incentives. **First study:** Ethics-reviewed, consent-based evaluation of autonomy and well-being outcomes, with stronger safeguards for minors; do not conduct vulnerable-user experiments in this repo. **Agent Movement link:** Personal relationship memory requires stricter consent than ordinary task context.

### 18. Can networks of cooperating, copying and replicating agents remain stable and bounded?

**Why it affects life:** A small erroneous instruction replicated across many agents could cause simultaneous financial actions, outages, load spikes or conflicting decisions. Copy, fork, delegation and movement are not equivalent; global consistency is not free.

**Research:** Unique identities and lineage, execution fencing, coordinated cancellation, quorum/lease behavior, bounded budgets and containment under partitions. **First study:** Synthetic fan-out of many agents under injected crashes and partitions; quantify duplicate effects, delayed cancellation, runaway spawn count and total resource use. **Agent Movement link:** Core AM-03/04/12 questions.

### 19. Can an agent's task move between devices, models, frameworks and organizations without losing its intent, safety policy or state integrity?

**Why it affects life:** People should be able to switch devices or providers, recover from failures, and use agents across services without repeating work or sacrificing control. Unsafe transfer can leak data, duplicate purchases or falsely claim that a task completed.

**Research:** Portable task envelopes, semantic compatibility checks, replay-safe side-effect ledgers, explicit lossy-state reports, bounded authority and independent cross-implementation tests. **First study:** Compare normal delegation, same-runtime checkpoint relocation and cross-framework reconstruction using two synthetic agents; measure correctness, privacy leaks, duplicate external effects, explicit incompatibility and cost. **Agent Movement link:** The central thesis of this repository (AM-01/07/08/11/14/15). No universal live-process migration is claimed.

### 20. Can society obtain AI's benefits with sustainable energy, compute and material costs?

**Why it affects life:** Data-center growth affects electricity grids, costs and infrastructure investment; hardware supply chains and cooling also impose resource demands. Conversely, useful AI can help optimize science, energy systems and public services. The net outcome is workload- and region-dependent.

**Research:** Complete workload accounting per successful task, energy/carbon/water where data are available, marginal impact, efficient scheduling and benefit-cost comparisons. **First study:** Benchmark completion-quality-adjusted model/agent workflows at several budget tiers; report energy estimates with uncertainty and actual power measurements when available. **Agent Movement link:** Adaptive edge/cloud placement should be chosen for quality, privacy, resilience and total resource cost rather than movement for its own sake.

## What this means for Agent Movement: choose a focused, falsifiable contribution

The repository already studies delegation, task-context portability, checkpoint relocation, replication and cross-framework reconstruction. It does **not** presently contain a working implementation (see the repository README and roadmap).

**The strongest practical research niche is a "human-authority-preserving handoff" contract**, not a claim of universal agent teleportation:

1. **Intent + consent:** Explicit user-approved intent, task constraints, permissible recipients, retention and expiry.
2. **Authority + identity:** Separate origin/destination identities, short-lived least-privilege grants and verifiable execution ownership.
3. **Context minimization:** Only approved inputs and artifact references, not hidden model state, passwords or raw provider credentials.
4. **Side-effect safety:** Stable operation identifiers, explicit states including "unknown/reconcile", fencing after handoff, and no unsupported claim of exactly-once external actions.
5. **Proof of lineage:** Privacy-preserving audit facts, source/destination runtime versions, policy decisions, checksums and transfer reason.
6. **Honest compatibility:** Refuse unsafe continuation; report missing/lost state if a different model/framework resumes.

This would generate evidence directly relevant to questions **1, 3, 4, 5, 6, 18 and 19**, while leaving clinical, legal, democratic and economic judgments to domain experts.

### Three priority experiments

| Experiment | Question(s) | Simulated setup | Publishable metric and necessary negative case |
| --- | --- | --- | --- |
| **HX1 Consent-bound transfer** | 1, 3, 5, 19 | Two locally controlled agents; approved synthetic task; policy envelope; bounded credential reference | Unauthorized simulated operations, blocked disallowed data/secret canaries, accurate cancellation; reject a forged destination |
| **HX2 Crash-safe ownership** | 1, 6, 18, 19 | Two executors and a mock irreversible-payment tool supporting idempotency; crash/partition at every handoff state | Duplicate committed mock actions, correctness of ownership fencing, "unknown/reconcile" cases; demonstrate unsafe retry refusal |
| **HX3 Meaningful continuation** | 2, 6, 16, 19, 20 | Source/destination framework or model differences; pinned synthetic multistep tasks and human-checked rubric | Success vs delegation/restart baselines, missing constraints, hallucinated progress, latency/cost and openly published failures |

**Suggested acceptance criteria for synthetic fixtures (proposals, not achieved results):** zero unauthorized simulated effects in the scripted negative-test matrix; zero canary secret fields in transmitted envelopes/logs; every high-impact simulated action attributable to an approval and operation ID; every ambiguous commit marked "unknown/reconcile"; all compatibility refusals reported rather than quietly continued. These passing cases do **not** constitute an unrestricted security guarantee.

### Practical 90-day direction (proposal, not scheduled work)

- **Weeks 1-2:** Freeze terminology, consent/authorization model, privacy classifications and human-harm scenarios; publish JSON Schema and negative-test cases.
- **Weeks 3-6:** Build a minimal two-local-agent A2A task handoff using **synthetic data only**; implement revocation, side-effect simulator and redacted audit records.
- **Weeks 7-12:** Add crash/partition fault injection, a second pinned execution adapter, benchmark baselines and a transparent evidence report with all failure cases.
- **Avoid:** Real-world payments, hospital records, surveillance, autonomous security exploitation, physical actuation, private user data, and public claims that mobility/continuation has been proven before implementation.

## Scope limitations and scientific honesty

- This is a **proposed normative ranking** by human-impact considerations, not a quantified actuarial model or expert consensus vote. Population reach and severity differ dramatically by deployment.
- The most important **human problem** and the most tractable **technical experiment** are not always the same. For example, job transitions and medical harms cannot be solved by transport protocols alone.
- Security benchmark "zero leaks" means zero within defined synthetic cases only; it is not a universal or legal compliance guarantee.
- A2A is primarily an agent interaction protocol, MCP addresses tools/context, and durable frameworks manage state within their own semantics. None alone guarantees lossless arbitrary-state migration or exactly-once side effects.
- Extreme autonomous loss-of-control impacts are potentially large but their probabilities and timelines are disputed [S2].
- This document recommends **research directions**, not production deployments, regulatory interpretations, or certified technical guarantees.

## Sources (primary/authoritative; accessed 2026-10-15)

- **[S1]** Stanford HAI, [2026 AI Index Report](https://hai.stanford.edu/ai-index/2026-ai-index-report), especially Technical Performance, Responsible AI, Economy, Medicine and Science.
- **[S2]** [International AI Safety Report 2026](https://internationalaisafetyreport.org/publication/international-ai-safety-report-2026), sections on malfunction, agent reliability and loss of control.
- **[S3]** OWASP, [Top 10 for Agentic Applications 2026](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/).
- **[S4]** NIST, [AI Agent Standards Initiative](https://www.nist.gov/news-events/news/2026/02/announcing-ai-agent-standards-initiative-interoperable-and-secure) (2026-02-17).
- **[S5]** International Labour Organization, [Generative AI and jobs: a 2025 update](https://www.ilo.org/publications/generative-ai-and-jobs-2025-update) (2025-05-20).
- **[S6]** WHO, [Ethics and governance of artificial intelligence for health: large multi-modal models](https://www.who.int/news/item/18-01-2024-who-releases-ai-ethics-and-governance-guidance-for-large-multi-modal-models).
- **[S7]** UNESCO, [Guidance for generative AI in education and research](https://www.unesco.org/en/articles/guidance-generative-ai-education-and-research?hub=253682).
- **[S8]** UNICEF Innocenti, [Guidance on AI and children, v3.0](https://www.unicef.org/innocenti/reports/policy-guidance-ai-children) (2025-12).
- **[S9]** IEA, [Energy and AI: Energy demand from AI](https://www.iea.org/reports/energy-and-ai/energy-demand-from-ai) (2025).
- **[S10]** Stanford HAI, [2026 AI Index: Science](https://hai.stanford.edu/ai-index/2026-ai-index-report/science).
- **[S11]** OECD, [Due Diligence Guidance for Responsible AI](https://www.oecd.org/en/publications/oecd-due-diligence-guidance-for-responsible-ai_41671712-en.html) (2026-02-19).

**Related local research:** [Open technical questions](open-questions.md), [Agent safety and trust](security-and-trust.md), [Movement taxonomy](research-landscape.md), [Proposed roadmap](roadmap.md), [Forensics and tracking](agent-forensics-and-fingerprints.md).
