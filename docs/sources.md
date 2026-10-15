# Sources and evidence log

Reviewed on **2026-10-15**; links and corpus counts fact-checked 2026-10-16. This is a selective standards/documentation survey, not a comprehensive systematic review. Verify specific upstream release dates and implementation behavior before claiming conformance. All architecture and envelope design in this repository are **proposals**.

This file indexes every external reference cited in the README and the core research documents listed in the *Document key* below. Documents that keep their own dated source lists are not repeated here: [standards-tracker](standards-tracker.md), [glossary](glossary.md), [device compatibility](device-compatibility-and-capability-matrix.md), [top-20 human-impact questions](top-20-human-impact-questions-for-agentic-ai.md) and [how-to-cite](how-to-cite.md). News items in [news-corpus/](news-corpus/README.md) and papers in [paper-corpus/](paper-corpus/README.md) are indexed separately in their own [news.bib](news-corpus/news.bib) and [papers.bib](paper-corpus/papers.bib) and are not repeated here. When a research document adds a new source, add it here too.

## Protocols and interoperability

| Topic | Primary source | Evidence scope | Cited in |
|---|---|---|---|
| A2A protocol v1.0 | https://a2a-protocol.org/v1.0.0/specification/ | Agent discovery, messages, tasks, artifacts; server-generated task IDs; `contextId` grouping; optional idempotency | README, landscape, security, taxonomy, questions, forensics |
| MCP specification 2026-07-28 | https://modelcontextprotocol.io/specification/2026-07-28 | Model/agent interface to tools, resources, prompts; stateless core; opt-in Tasks extension | README, landscape, security, taxonomy, questions |
| MCP 2026-07-28 release announcement | https://blog.modelcontextprotocol.io/posts/2026-07-28/ | Summary of the stateless core, Tasks extension and authorization changes | questions |
| AG-UI | https://github.com/ag-ui-protocol/ag-ui | Agent–user interaction/event protocol | README, landscape |

## Agent definition portability (research)

| Topic | Primary source | Evidence scope | Cited in |
|---|---|---|---|
| Open Agent Specification (Agent Spec): A Unified Representation for AI Agents (2025; v1 titled "Technical Report") | https://arxiv.org/abs/2510.04173 | Declarative, framework-neutral agent/workflow definitions and an evaluation harness | questions [S5] |
| Open Agent Specification, CAIS 2026 | https://doi.org/10.1145/3786335.3813130 | Cross-framework comparison using a shared representation; same author group as the 2025 report | questions [S6] |
| Specification Portability Across LLM Development Agents (2026) | https://arxiv.org/abs/2608.21208 | Oracle→PostgreSQL migration study: specifications written for one coding agent often transfer poorly to another | questions [S7] |

## Durable execution and orchestration

| Topic | Primary source | Evidence scope | Cited in |
|---|---|---|---|
| LangGraph persistence | https://docs.langchain.com/oss/python/langgraph/persistence | Checkpointers, threads and stores within LangGraph | README, landscape, taxonomy, questions |
| Temporal workflow execution | https://docs.temporal.io/workflow-execution | Event history, replay and durable execution semantics | README, landscape, questions |
| Temporal workflows | https://docs.temporal.io/workflows | Workflow model overview | taxonomy |
| Temporal child workflows | https://docs.temporal.io/child-workflows | Parent/child workflow composition | taxonomy |
| AWS Durable Execution SDK: idempotency and retries | https://docs.aws.amazon.com/durable-execution/patterns/best-practices/idempotency/ | At-least-once vs at-most-once per retry attempt; neither is end-to-end exactly-once by itself | questions [S8] |

## Packaging and scheduling

| Topic | Primary source | Evidence scope | Cited in |
|---|---|---|---|
| OCI image specification | https://specs.opencontainers.org/image-spec/ | Container image portability | README, landscape |
| Kubernetes Jobs | https://kubernetes.io/docs/concepts/workloads/controllers/job/ | Batch workload execution and retries | README, landscape |
| Kubernetes Deployments | https://kubernetes.io/docs/concepts/workloads/controllers/deployment/ | Replicated workloads | taxonomy |
| Kubernetes Horizontal Pod Autoscaler | https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/ | Horizontal resource-based scaling | taxonomy |

## Identity, authorization and policy

| Topic | Primary source | Evidence scope | Cited in |
|---|---|---|---|
| OAuth 2.0 Token Exchange (RFC 8693) | https://www.rfc-editor.org/rfc/rfc8693 | Standard token exchange mechanism, not automatic delegation trust | README, landscape, security, taxonomy |
| SPIFFE / SPIRE concepts | https://spiffe.io/docs/latest/spire-about/spire-concepts/ | Workload identity and attestation concepts | README, landscape, security, forensics |
| SPIFFE Workload API | https://spiffe.io/docs/latest/spiffe-specs/spiffe_workload_api/ | How workloads obtain identities | taxonomy |
| SPIFFE: working with SVIDs | https://spiffe.io/docs/latest/deploying/svids/ | X.509/JWT SVID usage and validation | forensics |
| Open Policy Agent | https://www.openpolicyagent.org/docs | Policy-as-code engine | README, landscape, security |

## Observability, provenance and forensics

| Topic | Primary source | Evidence scope | Cited in |
|---|---|---|---|
| OpenTelemetry GenAI semantic conventions | https://github.com/open-telemetry/semantic-conventions-genai | GenAI trace/metric convention family (moved from opentelemetry.io; status Development, checked 2026-10-16) | README, landscape, security |
| OpenTelemetry GenAI agent spans | https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md | Span conventions for agent creation/invocation, workflows and tool execution | forensics |
| OpenTelemetry tracing SDK (sampling) | https://opentelemetry.io/docs/specs/otel/trace/sdk/ | Sampling can omit spans, so traces are not complete evidence | forensics |
| W3C Trace Context | https://www.w3.org/TR/trace-context/ | `traceparent` correlation; not identity | forensics |
| W3C Baggage | https://www.w3.org/TR/baggage/ | Context propagation and its privacy considerations | forensics |
| OpenLineage specification | https://github.com/OpenLineage/OpenLineage/blob/main/spec/OpenLineage.md | Job/run/dataset lineage; candidate for artifact lineage | forensics |
| in-toto attestation framework | https://github.com/in-toto/attestation | Signed, typed attestations | forensics |
| Sigstore/Cosign attestation verification | https://docs.sigstore.dev/cosign/verifying/attestation/ | Verifying signer, trust root and predicate | forensics |
| JSON Canonicalization Scheme (RFC 8785) | https://www.rfc-editor.org/rfc/rfc8785.html | Repeatable JSON representation for hashing/signing | forensics |
| NIST SP 800-86 | https://csrc.nist.gov/pubs/sp/800/86/final | Forensic evidence handling and chain of custody | forensics |

**Document key:** README = [README](../README.md); landscape = [research-landscape](research-landscape.md); security = [security-and-trust](security-and-trust.md); taxonomy = [movement vs copy/replication](agent-movement-vs-copy-replication-multiplication.md); questions = [open-questions](open-questions.md); forensics = [agent-forensics-and-fingerprints](agent-forensics-and-fingerprints.md).

## Spot-check log

Existence and the specific claim attributed in these docs were checked against the live source on **2026-10-15** for:

| Source | Claim checked | Result |
|---|---|---|
| A2A v1.0.0 | Task IDs server-generated (§3.4.2); `contextId` groups related tasks/messages (§3.4.1); Send Message *MAY* be idempotent (§3.3.1) | Confirmed |
| MCP 2026-07-28 | Stateless, self-contained requests; Tasks is an opt-in extension; protocol cannot enforce consent/authorization itself | Confirmed |
| arXiv 2510.04173 | Title, authors, declarative cross-framework agent representation | Confirmed |
| CAIS 2026 / DOI 10.1145/3786335.3813130 | Title "Open Agent Specification: Enabling Cross-Framework Comparison of AI Agents"; ACM DL identifier | Confirmed via the CAIS 2026 program page |
| arXiv 2608.21208 | Title, Aug 2026 submission, cross-agent specification portability in a migration case study | Confirmed |
| AWS Durable Execution idempotency page | At-least-once default; at-most-once per attempt; neither alone is end-to-end single execution | Confirmed |
| OTel GenAI agent spans file | File exists; covers agent, workflow and tool spans | Confirmed |

The remaining sources are long-standing standards and documentation and were **not** re-checked in this pass. URLs can move; a broken link is a reason to re-verify the claim, not to assume it still holds.

## Evidence and assumptions

- **Documented by the source:** A2A provides agent communication; MCP defines tool/context integration; durability frameworks persist execution within their designs.
- **Inferred integration opportunity:** A movement envelope, adapters, policy and trace correlation could integrate these standards.
- **Not verified:** universally resumable execution across unrelated frameworks; unrestricted portability of model internals, reasoning, secrets or running processes; exactly-once remote tool actions.
- **Scope limit:** No comparative experiments, SDK interoperability tests, penetration tests, legal compliance review or performance benchmarks have been executed for this repository.

## Research methodology

1. Prefer the standard's official specification or maintainer documentation.
2. Treat marketing claims as hypotheses until tested.
3. Map each capability to its actual abstraction level: messaging, state, deployment, identity or UI.
4. Record incompatibilities and security assumptions.
5. Only upgrade proposals to verified implementation claims after reproducible tests with pinned versions.
6. When adding a citation to any research document, add it to this index and, if checked, to the spot-check log with the date.

## Paper corpus

Scholarly papers (83 items, 1980–2026; 75 from round 1 and 8 added in round 2 on 2026-10-16), including the classic mobile-agent, process-migration and delegation literature, are collected and independently audited in [paper-corpus/](paper-corpus/README.md). 81 of the 83 papers have a DOI and/or arXiv ID (the other two, a USENIX NSDI 2005 paper and an OpenAI white paper, are identified by their canonical URL); each has a peer-review flag, a paraphrased summary and a biblatex entry in [papers.bib](paper-corpus/papers.bib).

## News corpus

Dated industry, standards and security news (100 items, 2024-11 to 2026-10) is collected under a documented protocol in [news-corpus/](news-corpus/README.md). Every item has a paraphrased summary, coded movement operations, a verification flag and a biblatex entry in [news.bib](news-corpus/news.bib). Cite the original sources, not the corpus summaries.

Related documents: [landscape](research-landscape.md), [questions](open-questions.md), [roadmap](roadmap.md), [forensics](agent-forensics-and-fingerprints.md), [news corpus](news-corpus/README.md), [paper corpus](paper-corpus/README.md).
