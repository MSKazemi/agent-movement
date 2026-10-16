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
| Open Agent Specification (Agent Spec): A Unified Representation for AI Agents (2025; v1 titled "Technical Report") | https://arxiv.org/abs/2510.04173 | Declarative, framework-neutral agent/workflow definitions and an evaluation harness | questions [SRC-5] |
| Open Agent Specification, CAIS 2026 | https://doi.org/10.1145/3786335.3813130 | Cross-framework comparison using a shared representation; same author group as the 2025 report | questions [SRC-6] |
| Specification Portability Across LLM Development Agents (2026) | https://arxiv.org/abs/2608.21208 | Oracle→PostgreSQL migration study: specifications written for one coding agent often transfer poorly to another | questions [SRC-7] |

## Durable execution and orchestration

| Topic | Primary source | Evidence scope | Cited in |
|---|---|---|---|
| LangGraph persistence | https://docs.langchain.com/oss/python/langgraph/persistence | Checkpointers, threads and stores within LangGraph | README, landscape, taxonomy, questions |
| Temporal workflow execution | https://docs.temporal.io/workflow-execution | Event history, replay and durable execution semantics | README, landscape, questions |
| Temporal workflows | https://docs.temporal.io/workflows | Workflow model overview | taxonomy |
| Temporal child workflows | https://docs.temporal.io/child-workflows | Parent/child workflow composition | taxonomy |
| AWS Durable Execution SDK: idempotency and retries | https://docs.aws.amazon.com/durable-execution/patterns/best-practices/idempotency/ | At-least-once vs at-most-once per retry attempt; neither is end-to-end exactly-once by itself | questions [SRC-8] |

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

<!-- sources-index:start -->
<!-- Generated by tools/sources_index.py (`make sources-index`). Edit only the Accessed and Date basis cells; hand-edited dates are kept on regeneration. -->

## URL index by document

Every external URL cited in the README and in `docs/`, grouped by the citing document. Corpus records and generated files are excluded; see `EXCLUDE_GLOBS` in [`tools/sources_index.py`](../tools/sources_index.py). *Cited in* lists every document that cites the URL. *Accessed* is the date stated next to the citation (basis `citation`), else in its section heading (`section`), else in the document header (`document`), else the default 2026-10-15 (`default`). A date stated in a document is the date the source was reviewed for that document. It is not a fresh link check. `make sources` fails when a cited URL is missing here.

**Documents:** 33 · **Citations (document, URL):** 447 · **Unique URLs:** 265

### [README](../README.md)

| URL | Cited in | Accessed | Date basis |
|---|---|---|---|
| <https://a2a-protocol.org/v1.0.0/specification/> | README, 2031-frontier-research-agenda, a2a-adapter, agent-forensics-and-fingerprints, agent-lifecycle-liveness-and-death, agent-movement-vs-copy-replication-multiplication, cross-agent-prompt-injection, device-compatibility-and-capability-matrix, glossary, human-impact-research-lab, local-implementation, mobilitybench-experiment-protocol, open-questions, research-landscape, security-and-trust, sources, strategic-target-and-scientific-agenda | 2026-10-16 | document |
| <https://docs.langchain.com/oss/python/langgraph/persistence> | README, agent-movement-vs-copy-replication-multiplication, checkpoint-relocation, glossary, local-implementation, mobilitybench-experiment-protocol, open-questions, protocols-and-networks/primary-sources, research-landscape, sources, standards-tracker, strategic-target-and-scientific-agenda | 2026-10-16 | document |
| <https://docs.temporal.io/workflow-execution> | README, glossary, mobilitybench-experiment-protocol, open-questions, protocols-and-networks/primary-sources, research-landscape, sources, standards-tracker, strategic-target-and-scientific-agenda | 2026-10-16 | document |
| <https://github.com/ag-ui-protocol/ag-ui> | README, glossary, protocols-and-networks/primary-sources, research-landscape, sources | 2026-10-16 | document |
| <https://github.com/open-telemetry/semantic-conventions-genai> | README, agent-communication-and-policy, glossary, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-16 | document |
| <https://kubernetes.io/docs/concepts/workloads/controllers/job/> | README, protocols-and-networks/primary-sources, research-landscape, sources | 2026-10-16 | document |
| <https://modelcontextprotocol.io/specification/2026-07-28> | README, 2031-frontier-research-agenda, agent-communication-and-policy, agent-movement-vs-copy-replication-multiplication, device-compatibility-and-capability-matrix, glossary, human-impact-research-lab, mobilitybench-experiment-protocol, open-questions, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, standards-tracker, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-16 | document |
| <https://specs.opencontainers.org/image-spec/> | README, glossary, protocols-and-networks/primary-sources, research-landscape, sources, standards-tracker | 2026-10-16 | document |
| <https://spiffe.io/docs/latest/spire-about/spire-concepts/> | README, agent-communication-and-policy, agent-forensics-and-fingerprints, glossary, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-16 | document |
| <https://www.openpolicyagent.org/docs> | README, agent-communication-and-policy, glossary, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, standards-tracker | 2026-10-16 | document |
| <https://www.rfc-editor.org/rfc/rfc8693> | README, agent-communication-and-policy, agent-movement-vs-copy-replication-multiplication, glossary, mobilitybench-experiment-protocol, peer-authentication, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, standards-tracker, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-16 | document |

### [2031-frontier-research-agenda](2031-frontier-research-agenda.md)

| URL | Cited in | Accessed | Date basis |
|---|---|---|---|
| <https://a2a-protocol.org/v1.0.0/specification/> | README, 2031-frontier-research-agenda, a2a-adapter, agent-forensics-and-fingerprints, agent-lifecycle-liveness-and-death, agent-movement-vs-copy-replication-multiplication, cross-agent-prompt-injection, device-compatibility-and-capability-matrix, glossary, human-impact-research-lab, local-implementation, mobilitybench-experiment-protocol, open-questions, research-landscape, security-and-trust, sources, strategic-target-and-scientific-agenda | 2026-10-15 | document |
| <https://aclanthology.org/2026.acl-long.1294/> | 2031-frontier-research-agenda | 2026-10-15 | document |
| <https://aclanthology.org/2026.findings-eacl.268/> | 2031-frontier-research-agenda | 2026-10-15 | document |
| <https://arxiv.org/abs/2601.08815> | 2031-frontier-research-agenda | 2026-10-15 | document |
| <https://arxiv.org/abs/2603.20625> | 2031-frontier-research-agenda, evaluation-plan | 2026-10-15 | document |
| <https://arxiv.org/abs/2603.27771> | 2031-frontier-research-agenda | 2026-10-15 | document |
| <https://arxiv.org/abs/2605.26154> | 2031-frontier-research-agenda | 2026-10-15 | document |
| <https://arxiv.org/abs/2608.11632> | 2031-frontier-research-agenda | 2026-10-15 | document |
| <https://arxiv.org/abs/2608.30387> | 2031-frontier-research-agenda | 2026-10-15 | document |
| <https://arxiv.org/abs/2609.15906> | 2031-frontier-research-agenda | 2026-10-15 | document |
| <https://arxiv.org/abs/2609.21284> | 2031-frontier-research-agenda | 2026-10-15 | document |
| <https://arxiv.org/abs/2610.04083> | 2031-frontier-research-agenda | 2026-10-15 | document |
| <https://datatracker.ietf.org/doc/draft-pidlisnyi-aps/> | 2031-frontier-research-agenda | 2026-10-15 | document |
| <https://datatracker.ietf.org/doc/html/draft-saihm-memory-protocol-00> | 2031-frontier-research-agenda | 2026-10-15 | document |
| <https://doi.org/10.1145/3786335.3813130> | 2031-frontier-research-agenda, mobilitybench-experiment-protocol, open-questions, sources, strategic-target-and-scientific-agenda | 2026-10-15 | document |
| <https://modelcontextprotocol.io/specification/2026-07-28> | README, 2031-frontier-research-agenda, agent-communication-and-policy, agent-movement-vs-copy-replication-multiplication, device-compatibility-and-capability-matrix, glossary, human-impact-research-lab, mobilitybench-experiment-protocol, open-questions, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, standards-tracker, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | document |
| <https://www.ietf.org/archive/id/draft-daniel-ai-agent-internet-architecture-00.html> | 2031-frontier-research-agenda | 2026-10-15 | document |
| <https://www.itu.int/epublications/publication/itu-t-y-4618-2026-06-artificial-intelligence-of-things-reference-model-and-requirements> | 2031-frontier-research-agenda | 2026-10-15 | document |

### [a2a-adapter](a2a-adapter.md)

| URL | Cited in | Accessed | Date basis |
|---|---|---|---|
| <https://a2a-protocol.org/v1.0.0/specification/> | README, 2031-frontier-research-agenda, a2a-adapter, agent-forensics-and-fingerprints, agent-lifecycle-liveness-and-death, agent-movement-vs-copy-replication-multiplication, cross-agent-prompt-injection, device-compatibility-and-capability-matrix, glossary, human-impact-research-lab, local-implementation, mobilitybench-experiment-protocol, open-questions, research-landscape, security-and-trust, sources, strategic-target-and-scientific-agenda | 2026-10-15 | default |
| <https://github.com/a2aproject/a2a-python> | a2a-adapter, language-and-sdk-strategy, local-implementation | 2026-10-15 | default |
| <https://pypi.org/pypi/a2a-sdk/json> | a2a-adapter | 2026-10-15 | default |

### [a2a-profile-extension](a2a-profile-extension.md)

| URL | Cited in | Accessed | Date basis |
|---|---|---|---|
| <https://a2a-protocol.org/v1.0.0/topics/extensions/> | a2a-profile-extension | 2026-10-15 | default |

### [agent-communication-and-policy](agent-communication-and-policy.md)

| URL | Cited in | Accessed | Date basis |
|---|---|---|---|
| <https://a2a-protocol.org/v1.0.1/specification/> | agent-communication-and-policy, protocols-and-networks/README, protocols-and-networks/primary-sources, protocols-and-networks/protocol-catalog, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | section |
| <https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/> | agent-communication-and-policy, human-impact-research-lab, mobilitybench-experiment-protocol, security-and-trust, strategic-target-and-scientific-agenda, top-20-human-impact-questions-for-agentic-ai | 2026-10-15 | section |
| <https://github.com/open-telemetry/semantic-conventions-genai> | README, agent-communication-and-policy, glossary, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | section |
| <https://modelcontextprotocol.io/specification/2026-07-28> | README, 2031-frontier-research-agenda, agent-communication-and-policy, agent-movement-vs-copy-replication-multiplication, device-compatibility-and-capability-matrix, glossary, human-impact-research-lab, mobilitybench-experiment-protocol, open-questions, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, standards-tracker, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | section |
| <https://modelcontextprotocol.io/specification/2026-07-28/server/tools> | agent-communication-and-policy, cross-agent-prompt-injection | 2026-10-16 | citation |
| <https://spiffe.io/docs/latest/spire-about/spire-concepts/> | README, agent-communication-and-policy, agent-forensics-and-fingerprints, glossary, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | section |
| <https://www.nist.gov/artificial-intelligence/ai-agent-standards-initiative> | agent-communication-and-policy | 2026-10-15 | section |
| <https://www.openpolicyagent.org/docs> | README, agent-communication-and-policy, glossary, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, standards-tracker | 2026-10-15 | section |
| <https://www.rfc-editor.org/rfc/rfc8693> | README, agent-communication-and-policy, agent-movement-vs-copy-replication-multiplication, glossary, mobilitybench-experiment-protocol, peer-authentication, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, standards-tracker, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | section |

### [agent-forensics-and-fingerprints](agent-forensics-and-fingerprints.md)

| URL | Cited in | Accessed | Date basis |
|---|---|---|---|
| <https://a2a-protocol.org/v1.0.0/specification/> | README, 2031-frontier-research-agenda, a2a-adapter, agent-forensics-and-fingerprints, agent-lifecycle-liveness-and-death, agent-movement-vs-copy-replication-multiplication, cross-agent-prompt-injection, device-compatibility-and-capability-matrix, glossary, human-impact-research-lab, local-implementation, mobilitybench-experiment-protocol, open-questions, research-landscape, security-and-trust, sources, strategic-target-and-scientific-agenda | 2026-10-15 | section |
| <https://csrc.nist.gov/pubs/sp/800/86/final> | agent-forensics-and-fingerprints, glossary, movement-receipts, sources | 2026-10-15 | section |
| <https://docs.sigstore.dev/cosign/verifying/attestation/> | agent-forensics-and-fingerprints, sources | 2026-10-15 | section |
| <https://github.com/OpenLineage/OpenLineage/blob/main/spec/OpenLineage.md> | agent-forensics-and-fingerprints, glossary, sources | 2026-10-15 | section |
| <https://github.com/in-toto/attestation> | agent-forensics-and-fingerprints, glossary, movement-receipts, sources | 2026-10-15 | section |
| <https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md> | agent-forensics-and-fingerprints, sources | 2026-10-15 | section |
| <https://opentelemetry.io/docs/specs/otel/trace/sdk/> | agent-forensics-and-fingerprints, sources | 2026-10-15 | section |
| <https://spiffe.io/docs/latest/deploying/svids/> | agent-forensics-and-fingerprints, agent-lifecycle-liveness-and-death, glossary, movement-receipts, sources | 2026-10-15 | section |
| <https://spiffe.io/docs/latest/spire-about/spire-concepts/> | README, agent-communication-and-policy, agent-forensics-and-fingerprints, glossary, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | section |
| <https://www.rfc-editor.org/rfc/rfc8785.html> | agent-forensics-and-fingerprints, glossary, movement-receipts, sources | 2026-10-15 | section |
| <https://www.w3.org/TR/baggage/> | agent-forensics-and-fingerprints, glossary, movement-receipts, sources | 2026-10-15 | section |
| <https://www.w3.org/TR/trace-context/> | agent-forensics-and-fingerprints, glossary, how-it-works, movement-receipts, sources | 2026-10-15 | section |

### [agent-lifecycle-liveness-and-death](agent-lifecycle-liveness-and-death.md)

| URL | Cited in | Accessed | Date basis |
|---|---|---|---|
| <https://a2a-protocol.org/v1.0.0/specification/> | README, 2031-frontier-research-agenda, a2a-adapter, agent-forensics-and-fingerprints, agent-lifecycle-liveness-and-death, agent-movement-vs-copy-replication-multiplication, cross-agent-prompt-injection, device-compatibility-and-capability-matrix, glossary, human-impact-research-lab, local-implementation, mobilitybench-experiment-protocol, open-questions, research-landscape, security-and-trust, sources, strategic-target-and-scientific-agenda | 2026-10-15 | document |
| <https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/> | agent-lifecycle-liveness-and-death | 2026-10-15 | document |
| <https://martin.kleppmann.com/2016/02/08/how-to-do-distributed-locking.html> | agent-lifecycle-liveness-and-death, checkpoint-relocation, glossary | 2026-10-15 | document |
| <https://research.google/pubs/unreliable-failure-detectors-for-reliable-distributed-systems/> | agent-lifecycle-liveness-and-death | 2026-10-15 | document |
| <https://spiffe.io/docs/latest/deploying/svids/> | agent-forensics-and-fingerprints, agent-lifecycle-liveness-and-death, glossary, movement-receipts, sources | 2026-10-15 | document |

### [agent-movement-vs-copy-replication-multiplication](agent-movement-vs-copy-replication-multiplication.md)

| URL | Cited in | Accessed | Date basis |
|---|---|---|---|
| <https://a2a-protocol.org/v1.0.0/specification/> | README, 2031-frontier-research-agenda, a2a-adapter, agent-forensics-and-fingerprints, agent-lifecycle-liveness-and-death, agent-movement-vs-copy-replication-multiplication, cross-agent-prompt-injection, device-compatibility-and-capability-matrix, glossary, human-impact-research-lab, local-implementation, mobilitybench-experiment-protocol, open-questions, research-landscape, security-and-trust, sources, strategic-target-and-scientific-agenda | 2026-10-15 | document |
| <https://docs.langchain.com/oss/python/langgraph/persistence> | README, agent-movement-vs-copy-replication-multiplication, checkpoint-relocation, glossary, local-implementation, mobilitybench-experiment-protocol, open-questions, protocols-and-networks/primary-sources, research-landscape, sources, standards-tracker, strategic-target-and-scientific-agenda | 2026-10-15 | document |
| <https://docs.temporal.io/child-workflows> | agent-movement-vs-copy-replication-multiplication, sources | 2026-10-15 | document |
| <https://docs.temporal.io/workflows> | agent-movement-vs-copy-replication-multiplication, sources | 2026-10-15 | document |
| <https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/> | agent-movement-vs-copy-replication-multiplication, glossary, sources | 2026-10-15 | document |
| <https://kubernetes.io/docs/concepts/workloads/controllers/deployment/> | agent-movement-vs-copy-replication-multiplication, glossary, sources | 2026-10-15 | document |
| <https://modelcontextprotocol.io/specification/2026-07-28> | README, 2031-frontier-research-agenda, agent-communication-and-policy, agent-movement-vs-copy-replication-multiplication, device-compatibility-and-capability-matrix, glossary, human-impact-research-lab, mobilitybench-experiment-protocol, open-questions, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, standards-tracker, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | document |
| <https://spiffe.io/docs/latest/spiffe-specs/spiffe_workload_api/> | agent-movement-vs-copy-replication-multiplication, sources | 2026-10-15 | document |
| <https://www.rfc-editor.org/rfc/rfc8693> | README, agent-communication-and-policy, agent-movement-vs-copy-replication-multiplication, glossary, mobilitybench-experiment-protocol, peer-authentication, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, standards-tracker, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | document |

### [checkpoint-relocation](checkpoint-relocation.md)

| URL | Cited in | Accessed | Date basis |
|---|---|---|---|
| <https://docs.langchain.com/oss/python/langgraph/persistence> | README, agent-movement-vs-copy-replication-multiplication, checkpoint-relocation, glossary, local-implementation, mobilitybench-experiment-protocol, open-questions, protocols-and-networks/primary-sources, research-landscape, sources, standards-tracker, strategic-target-and-scientific-agenda | 2026-10-15 | default |
| <https://martin.kleppmann.com/2016/02/08/how-to-do-distributed-locking.html> | agent-lifecycle-liveness-and-death, checkpoint-relocation, glossary | 2026-10-15 | default |
| <https://www.sqlite.org/lang_transaction.html> | checkpoint-relocation, local-implementation | 2026-10-15 | default |

### [cross-agent-prompt-injection](cross-agent-prompt-injection.md)

| URL | Cited in | Accessed | Date basis |
|---|---|---|---|
| <https://a2a-protocol.org/v1.0.0/specification/> | README, 2031-frontier-research-agenda, a2a-adapter, agent-forensics-and-fingerprints, agent-lifecycle-liveness-and-death, agent-movement-vs-copy-replication-multiplication, cross-agent-prompt-injection, device-compatibility-and-capability-matrix, glossary, human-impact-research-lab, local-implementation, mobilitybench-experiment-protocol, open-questions, research-landscape, security-and-trust, sources, strategic-target-and-scientific-agenda | 2026-10-16 | document |
| <https://arxiv.org/abs/2302.12173> | cross-agent-prompt-injection | 2026-10-16 | document |
| <https://arxiv.org/abs/2403.02817> | cross-agent-prompt-injection | 2026-10-16 | document |
| <https://arxiv.org/abs/2403.14720> | cross-agent-prompt-injection | 2026-10-16 | document |
| <https://arxiv.org/abs/2410.07283> | cross-agent-prompt-injection | 2026-10-16 | document |
| <https://arxiv.org/abs/2503.00061> | cross-agent-prompt-injection | 2026-10-16 | document |
| <https://arxiv.org/abs/2504.11358> | cross-agent-prompt-injection | 2026-10-16 | document |
| <https://arxiv.org/abs/2506.08837> | cross-agent-prompt-injection | 2026-10-16 | document |
| <https://arxiv.org/abs/2510.09023> | cross-agent-prompt-injection | 2026-10-16 | document |
| <https://doi.org/10.1145/3605764.3623985> | cross-agent-prompt-injection | 2026-10-16 | document |
| <https://doi.org/10.1145/3719027.3765196> | cross-agent-prompt-injection | 2026-10-16 | citation |
| <https://genai.owasp.org/llmrisk/llm01-prompt-injection/> | cross-agent-prompt-injection, glossary | 2026-10-16 | document |
| <https://modelcontextprotocol.io/specification/2026-07-28/server/tools> | agent-communication-and-policy, cross-agent-prompt-injection | 2026-10-16 | document |

### [device-compatibility-and-capability-matrix](device-compatibility-and-capability-matrix.md)

| URL | Cited in | Accessed | Date basis |
|---|---|---|---|
| <https://a2a-protocol.org/v1.0.0/specification/> | README, 2031-frontier-research-agenda, a2a-adapter, agent-forensics-and-fingerprints, agent-lifecycle-liveness-and-death, agent-movement-vs-copy-replication-multiplication, cross-agent-prompt-injection, device-compatibility-and-capability-matrix, glossary, human-impact-research-lab, local-implementation, mobilitybench-experiment-protocol, open-questions, research-landscape, security-and-trust, sources, strategic-target-and-scientific-agenda | 2026-10-15 | document |
| <https://criu.org/Main_Page> | device-compatibility-and-capability-matrix, glossary | 2026-10-15 | document |
| <https://csrc.nist.gov/pubs/sp/800/82/r3/final> | device-compatibility-and-capability-matrix | 2026-10-15 | document |
| <https://developer.android.com/develop/background-work/background-tasks> | device-compatibility-and-capability-matrix | 2026-10-15 | document |
| <https://developer.apple.com/documentation/backgroundtasks> | device-compatibility-and-capability-matrix | 2026-10-15 | document |
| <https://docs.docker.com/build/building/multi-platform/> | device-compatibility-and-capability-matrix | 2026-10-15 | document |
| <https://docs.ros.org/en/jazzy/> | device-compatibility-and-capability-matrix | 2026-10-15 | document |
| <https://docs.zephyrproject.org/latest/> | device-compatibility-and-capability-matrix | 2026-10-15 | document |
| <https://kubernetes.io/docs/concepts/architecture/> | device-compatibility-and-capability-matrix | 2026-10-15 | document |
| <https://mavlink.io/en/> | device-compatibility-and-capability-matrix | 2026-10-15 | document |
| <https://micro.ros.org/> | device-compatibility-and-capability-matrix | 2026-10-15 | document |
| <https://modelcontextprotocol.io/specification/2026-07-28> | README, 2031-frontier-research-agenda, agent-communication-and-policy, agent-movement-vs-copy-replication-multiplication, device-compatibility-and-capability-matrix, glossary, human-impact-research-lab, mobilitybench-experiment-protocol, open-questions, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, standards-tracker, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | document |
| <https://moveit.ai/> | device-compatibility-and-capability-matrix | 2026-10-15 | document |

### [economic-evaluation](economic-evaluation.md)

| URL | Cited in | Accessed | Date basis |
|---|---|---|---|
| <https://arxiv.org/abs/2406.12045> | economic-evaluation, evaluation-plan | 2026-10-16 | document |
| <https://arxiv.org/abs/2407.01502> | economic-evaluation, evaluation-plan | 2026-10-16 | document |
| <https://arxiv.org/abs/2507.09089> | economic-evaluation | 2026-10-16 | document |
| <https://arxiv.org/abs/2510.00615> | economic-evaluation | 2026-10-16 | citation |
| <https://arxiv.org/abs/2510.11977> | economic-evaluation | 2026-10-16 | document |
| <https://doi.org/10.1002/spe.449> | economic-evaluation | 2026-10-16 | document |
| <https://doi.org/10.1109/icct67417.2025.11373977> | economic-evaluation | 2026-10-16 | citation |
| <https://doi.org/10.1145/295685.298136> | economic-evaluation | 2026-10-16 | document |
| <https://doi.org/10.1145/3183519.3183525> | economic-evaluation | 2026-10-16 | document |
| <https://doi.org/10.1145/3600006.3613154> | economic-evaluation | 2026-10-16 | document |
| <https://dora.dev/guides/dora-metrics/> | economic-evaluation | 2026-10-16 | document |
| <https://sre.google/sre-book/eliminating-toil/> | economic-evaluation | 2026-10-16 | document |
| <https://sre.google/sre-book/postmortem-culture/> | economic-evaluation | 2026-10-16 | document |
| <https://www.usenix.org/conference/osdi24/presentation/sun-biao> | economic-evaluation | 2026-10-16 | document |

### [evaluation-plan](evaluation-plan.md)

| URL | Cited in | Accessed | Date basis |
|---|---|---|---|
| <https://arxiv.org/abs/2308.00352> | evaluation-plan | 2026-10-16 | document |
| <https://arxiv.org/abs/2310.06770> | evaluation-plan | 2026-10-16 | document |
| <https://arxiv.org/abs/2406.12045> | economic-evaluation, evaluation-plan | 2026-10-16 | document |
| <https://arxiv.org/abs/2407.01489> | evaluation-plan | 2026-10-16 | document |
| <https://arxiv.org/abs/2407.01502> | economic-evaluation, evaluation-plan | 2026-10-16 | document |
| <https://arxiv.org/abs/2411.00640> | evaluation-plan | 2026-10-16 | document |
| <https://arxiv.org/abs/2503.13657> | evaluation-plan | 2026-10-16 | document |
| <https://arxiv.org/abs/2603.20625> | 2031-frontier-research-agenda, evaluation-plan | 2026-10-16 | document |
| <https://arxiv.org/html/2406.13352> | evaluation-plan | 2026-10-16 | document |
| <https://doi.org/10.1007/978-3-032-16092-8_28> | evaluation-plan | 2026-10-16 | document |
| <https://doi.org/10.1109/3468.844354> | evaluation-plan | 2026-10-16 | document |
| <https://doi.org/10.18653/v1/2024.acl-long.810> | evaluation-plan | 2026-10-16 | document |
| <https://doi.org/10.18653/v1/2024.findings-acl.624> | evaluation-plan | 2026-10-16 | document |
| <https://help.osf.io/article/158-create-a-preregistration> | evaluation-plan | 2026-10-16 | document |
| <https://openreview.net/forum?id=GEcwtMk1uA> | evaluation-plan | 2026-10-16 | document |
| <https://www.law.cornell.edu/regulations/california/13-CCR-227.50> | evaluation-plan | 2026-10-16 | document |

### [glossary](glossary.md)

| URL | Cited in | Accessed | Date basis |
|---|---|---|---|
| <https://a2a-protocol.org/v1.0.0/specification/> | README, 2031-frontier-research-agenda, a2a-adapter, agent-forensics-and-fingerprints, agent-lifecycle-liveness-and-death, agent-movement-vs-copy-replication-multiplication, cross-agent-prompt-injection, device-compatibility-and-capability-matrix, glossary, human-impact-research-lab, local-implementation, mobilitybench-experiment-protocol, open-questions, research-landscape, security-and-trust, sources, strategic-target-and-scientific-agenda | 2026-10-16 | document |
| <https://agents.md/> | glossary, research-landscape | 2026-10-16 | document |
| <https://agentskills.io/specification> | glossary, research-landscape, standards-tracker | 2026-10-16 | document |
| <https://arxiv.org/abs/2510.04173> | glossary, open-questions, sources | 2026-10-16 | document |
| <https://criu.org/Main_Page> | device-compatibility-and-capability-matrix, glossary | 2026-10-16 | document |
| <https://csrc.nist.gov/glossary/term/attestation> | glossary | 2026-10-16 | document |
| <https://csrc.nist.gov/glossary/term/chain_of_custody> | glossary | 2026-10-16 | document |
| <https://csrc.nist.gov/glossary/term/least_privilege> | glossary | 2026-10-16 | document |
| <https://csrc.nist.gov/glossary/term/message_digest> | glossary | 2026-10-16 | document |
| <https://csrc.nist.gov/glossary/term/policy_decision_point> | glossary | 2026-10-16 | document |
| <https://csrc.nist.gov/pubs/sp/800/86/final> | agent-forensics-and-fingerprints, glossary, movement-receipts, sources | 2026-10-16 | document |
| <https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/> | glossary | 2026-10-16 | document |
| <https://docs.aws.amazon.com/durable-execution/patterns/best-practices/idempotency/> | glossary, open-questions, sources | 2026-10-16 | document |
| <https://docs.langchain.com/oss/python/langgraph/persistence> | README, agent-movement-vs-copy-replication-multiplication, checkpoint-relocation, glossary, local-implementation, mobilitybench-experiment-protocol, open-questions, protocols-and-networks/primary-sources, research-landscape, sources, standards-tracker, strategic-target-and-scientific-agenda | 2026-10-16 | document |
| <https://docs.temporal.io/workflow-execution> | README, glossary, mobilitybench-experiment-protocol, open-questions, protocols-and-networks/primary-sources, research-landscape, sources, standards-tracker, strategic-target-and-scientific-agenda | 2026-10-16 | document |
| <https://doi.org/10.1109/32.685258> | glossary | 2026-10-16 | document |
| <https://doi.org/10.1145/38713.38742> | glossary | 2026-10-16 | document |
| <https://doi.org/10.1145/74850.74870> | glossary | 2026-10-16 | document |
| <https://genai.owasp.org/llmrisk/llm01-prompt-injection/> | cross-agent-prompt-injection, glossary | 2026-10-16 | document |
| <https://github.com/OpenLineage/OpenLineage/blob/main/spec/OpenLineage.md> | agent-forensics-and-fingerprints, glossary, sources | 2026-10-16 | document |
| <https://github.com/ag-ui-protocol/ag-ui> | README, glossary, protocols-and-networks/primary-sources, research-landscape, sources | 2026-10-16 | document |
| <https://github.com/agentsmd/agents.md> | glossary, research-landscape, standards-tracker | 2026-10-16 | document |
| <https://github.com/in-toto/attestation> | agent-forensics-and-fingerprints, glossary, movement-receipts, sources | 2026-10-16 | document |
| <https://github.com/open-telemetry/semantic-conventions-genai> | README, agent-communication-and-policy, glossary, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-16 | document |
| <https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/> | agent-movement-vs-copy-replication-multiplication, glossary, sources | 2026-10-16 | document |
| <https://kubernetes.io/docs/concepts/workloads/controllers/deployment/> | agent-movement-vs-copy-replication-multiplication, glossary, sources | 2026-10-16 | document |
| <https://martin.kleppmann.com/2016/02/08/how-to-do-distributed-locking.html> | agent-lifecycle-liveness-and-death, checkpoint-relocation, glossary | 2026-10-16 | document |
| <https://modelcontextprotocol.io/specification/2026-07-28> | README, 2031-frontier-research-agenda, agent-communication-and-policy, agent-movement-vs-copy-replication-multiplication, device-compatibility-and-capability-matrix, glossary, human-impact-research-lab, mobilitybench-experiment-protocol, open-questions, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, standards-tracker, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-16 | document |
| <https://opentelemetry.io/docs/specs/semconv/gen-ai/> | glossary | 2026-10-16 | document |
| <https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview> | glossary, research-landscape | 2026-10-16 | document |
| <https://sites.cs.ucsb.edu/~vigna/publications/2007_carzaniga_picco_vigna_ICSE.pdf> | glossary | 2026-10-16 | document |
| <https://specs.opencontainers.org/image-spec/> | README, glossary, protocols-and-networks/primary-sources, research-landscape, sources, standards-tracker | 2026-10-16 | document |
| <https://spiffe.io/docs/latest/deploying/svids/> | agent-forensics-and-fingerprints, agent-lifecycle-liveness-and-death, glossary, movement-receipts, sources | 2026-10-16 | document |
| <https://spiffe.io/docs/latest/spiffe-about/spiffe-concepts/> | glossary | 2026-10-16 | document |
| <https://spiffe.io/docs/latest/spire-about/spire-concepts/> | README, agent-communication-and-policy, agent-forensics-and-fingerprints, glossary, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-16 | document |
| <https://webmachinelearning.github.io/webmcp/> | glossary, research-landscape, standards-tracker | 2026-10-16 | document |
| <https://www.openpolicyagent.org/docs> | README, agent-communication-and-policy, glossary, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, standards-tracker | 2026-10-16 | document |
| <https://www.rfc-editor.org/rfc/rfc8693> | README, agent-communication-and-policy, agent-movement-vs-copy-replication-multiplication, glossary, mobilitybench-experiment-protocol, peer-authentication, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, standards-tracker, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-16 | document |
| <https://www.rfc-editor.org/rfc/rfc8785.html> | agent-forensics-and-fingerprints, glossary, movement-receipts, sources | 2026-10-16 | document |
| <https://www.rfc-editor.org/rfc/rfc9110.html> | glossary | 2026-10-16 | document |
| <https://www.w3.org/TR/baggage/> | agent-forensics-and-fingerprints, glossary, movement-receipts, sources | 2026-10-16 | document |
| <https://www.w3.org/TR/prov-dm/> | glossary | 2026-10-16 | document |
| <https://www.w3.org/TR/trace-context/> | agent-forensics-and-fingerprints, glossary, how-it-works, movement-receipts, sources | 2026-10-16 | document |
| <https://www.w3.org/TR/webdriver-bidi/> | glossary, research-landscape, standards-tracker | 2026-10-16 | document |

### [how-it-works](how-it-works.md)

| URL | Cited in | Accessed | Date basis |
|---|---|---|---|
| <https://semver.org/spec/v2.0.0.html> | how-it-works | 2026-10-16 | citation |
| <https://www.w3.org/TR/trace-context/> | agent-forensics-and-fingerprints, glossary, how-it-works, movement-receipts, sources | 2026-10-15 | default |

### [how-to-cite](how-to-cite.md)

| URL | Cited in | Accessed | Date basis |
|---|---|---|---|
| <https://citation-file-format.github.io/> | how-to-cite | 2026-10-15 | default |

### [human-impact-research-lab](human-impact-research-lab.md)

| URL | Cited in | Accessed | Date basis |
|---|---|---|---|
| <https://a2a-protocol.org/v1.0.0/specification/> | README, 2031-frontier-research-agenda, a2a-adapter, agent-forensics-and-fingerprints, agent-lifecycle-liveness-and-death, agent-movement-vs-copy-replication-multiplication, cross-agent-prompt-injection, device-compatibility-and-capability-matrix, glossary, human-impact-research-lab, local-implementation, mobilitybench-experiment-protocol, open-questions, research-landscape, security-and-trust, sources, strategic-target-and-scientific-agenda | 2026-10-16 | document |
| <https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/> | agent-communication-and-policy, human-impact-research-lab, mobilitybench-experiment-protocol, security-and-trust, strategic-target-and-scientific-agenda, top-20-human-impact-questions-for-agentic-ai | 2026-10-16 | document |
| <https://modelcontextprotocol.io/specification/2026-07-28> | README, 2031-frontier-research-agenda, agent-communication-and-policy, agent-movement-vs-copy-replication-multiplication, device-compatibility-and-capability-matrix, glossary, human-impact-research-lab, mobilitybench-experiment-protocol, open-questions, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, standards-tracker, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-16 | document |
| <https://www.nist.gov/news-events/news/2026/02/announcing-ai-agent-standards-initiative-interoperable-and-secure> | human-impact-research-lab, strategic-target-and-scientific-agenda, top-20-human-impact-questions-for-agentic-ai | 2026-10-16 | document |

### [language-and-sdk-strategy](language-and-sdk-strategy.md)

| URL | Cited in | Accessed | Date basis |
|---|---|---|---|
| <https://a2a-protocol.org/latest/sdk/> | language-and-sdk-strategy | 2026-10-15 | section |
| <https://blog.modelcontextprotocol.io/posts/2026-07-28/> | language-and-sdk-strategy, open-questions, sources, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | section |
| <https://github.com/a2aproject/a2a-js> | language-and-sdk-strategy | 2026-10-15 | section |
| <https://github.com/a2aproject/a2a-python> | a2a-adapter, language-and-sdk-strategy, local-implementation | 2026-10-15 | section |
| <https://github.com/a2aproject/a2a-samples> | language-and-sdk-strategy | 2026-10-15 | section |
| <https://modelcontextprotocol.io/docs/sdk> | language-and-sdk-strategy | 2026-10-15 | section |
| <https://py.sdk.modelcontextprotocol.io/> | language-and-sdk-strategy | 2026-10-15 | section |
| <https://ts.sdk.modelcontextprotocol.io/v2/> | language-and-sdk-strategy | 2026-10-15 | section |

### [local-implementation](local-implementation.md)

| URL | Cited in | Accessed | Date basis |
|---|---|---|---|
| <https://a2a-protocol.org/v1.0.0/specification/> | README, 2031-frontier-research-agenda, a2a-adapter, agent-forensics-and-fingerprints, agent-lifecycle-liveness-and-death, agent-movement-vs-copy-replication-multiplication, cross-agent-prompt-injection, device-compatibility-and-capability-matrix, glossary, human-impact-research-lab, local-implementation, mobilitybench-experiment-protocol, open-questions, research-landscape, security-and-trust, sources, strategic-target-and-scientific-agenda | 2026-10-15 | default |
| <https://docs.langchain.com/oss/python/langgraph/persistence> | README, agent-movement-vs-copy-replication-multiplication, checkpoint-relocation, glossary, local-implementation, mobilitybench-experiment-protocol, open-questions, protocols-and-networks/primary-sources, research-landscape, sources, standards-tracker, strategic-target-and-scientific-agenda | 2026-10-15 | default |
| <https://github.com/a2aproject/a2a-python> | a2a-adapter, language-and-sdk-strategy, local-implementation | 2026-10-15 | default |
| <https://www.sqlite.org/lang_transaction.html> | checkpoint-relocation, local-implementation | 2026-10-15 | default |

### [mobilitybench-experiment-protocol](mobilitybench-experiment-protocol.md)

| URL | Cited in | Accessed | Date basis |
|---|---|---|---|
| <https://a2a-protocol.org/v1.0.0/specification/> | README, 2031-frontier-research-agenda, a2a-adapter, agent-forensics-and-fingerprints, agent-lifecycle-liveness-and-death, agent-movement-vs-copy-replication-multiplication, cross-agent-prompt-injection, device-compatibility-and-capability-matrix, glossary, human-impact-research-lab, local-implementation, mobilitybench-experiment-protocol, open-questions, research-landscape, security-and-trust, sources, strategic-target-and-scientific-agenda | 2026-10-15 | document |
| <https://docs.langchain.com/oss/python/langgraph/persistence> | README, agent-movement-vs-copy-replication-multiplication, checkpoint-relocation, glossary, local-implementation, mobilitybench-experiment-protocol, open-questions, protocols-and-networks/primary-sources, research-landscape, sources, standards-tracker, strategic-target-and-scientific-agenda | 2026-10-15 | document |
| <https://docs.temporal.io/workflow-execution> | README, glossary, mobilitybench-experiment-protocol, open-questions, protocols-and-networks/primary-sources, research-landscape, sources, standards-tracker, strategic-target-and-scientific-agenda | 2026-10-15 | document |
| <https://doi.org/10.1145/3786335.3813130> | 2031-frontier-research-agenda, mobilitybench-experiment-protocol, open-questions, sources, strategic-target-and-scientific-agenda | 2026-10-15 | document |
| <https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/> | agent-communication-and-policy, human-impact-research-lab, mobilitybench-experiment-protocol, security-and-trust, strategic-target-and-scientific-agenda, top-20-human-impact-questions-for-agentic-ai | 2026-10-15 | document |
| <https://modelcontextprotocol.io/specification/2026-07-28> | README, 2031-frontier-research-agenda, agent-communication-and-policy, agent-movement-vs-copy-replication-multiplication, device-compatibility-and-capability-matrix, glossary, human-impact-research-lab, mobilitybench-experiment-protocol, open-questions, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, standards-tracker, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | document |
| <https://www.rfc-editor.org/rfc/rfc8693> | README, agent-communication-and-policy, agent-movement-vs-copy-replication-multiplication, glossary, mobilitybench-experiment-protocol, peer-authentication, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, standards-tracker, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | document |

### [movement-receipts](movement-receipts.md)

| URL | Cited in | Accessed | Date basis |
|---|---|---|---|
| <https://csrc.nist.gov/pubs/sp/800/86/final> | agent-forensics-and-fingerprints, glossary, movement-receipts, sources | 2026-10-15 | default |
| <https://github.com/gitleaks/gitleaks> | movement-receipts | 2026-10-15 | default |
| <https://github.com/in-toto/attestation> | agent-forensics-and-fingerprints, glossary, movement-receipts, sources | 2026-10-15 | default |
| <https://pypi.org/project/cryptography/> | movement-receipts | 2026-10-15 | default |
| <https://spiffe.io/docs/latest/deploying/svids/> | agent-forensics-and-fingerprints, agent-lifecycle-liveness-and-death, glossary, movement-receipts, sources | 2026-10-15 | default |
| <https://www.rfc-editor.org/rfc/rfc8032> | movement-receipts | 2026-10-16 | citation |
| <https://www.rfc-editor.org/rfc/rfc8785.html> | agent-forensics-and-fingerprints, glossary, movement-receipts, sources | 2026-10-15 | default |
| <https://www.w3.org/TR/baggage/> | agent-forensics-and-fingerprints, glossary, movement-receipts, sources | 2026-10-15 | default |
| <https://www.w3.org/TR/trace-context/> | agent-forensics-and-fingerprints, glossary, how-it-works, movement-receipts, sources | 2026-10-15 | default |

### [open-questions](open-questions.md)

| URL | Cited in | Accessed | Date basis |
|---|---|---|---|
| <https://a2a-protocol.org/v1.0.0/specification/> | README, 2031-frontier-research-agenda, a2a-adapter, agent-forensics-and-fingerprints, agent-lifecycle-liveness-and-death, agent-movement-vs-copy-replication-multiplication, cross-agent-prompt-injection, device-compatibility-and-capability-matrix, glossary, human-impact-research-lab, local-implementation, mobilitybench-experiment-protocol, open-questions, research-landscape, security-and-trust, sources, strategic-target-and-scientific-agenda | 2026-10-16 | document |
| <https://arxiv.org/abs/2510.04173> | glossary, open-questions, sources | 2026-10-16 | document |
| <https://arxiv.org/abs/2608.21208> | open-questions, sources, strategic-target-and-scientific-agenda | 2026-10-16 | document |
| <https://blog.modelcontextprotocol.io/posts/2026-07-28/> | language-and-sdk-strategy, open-questions, sources, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-16 | document |
| <https://docs.aws.amazon.com/durable-execution/patterns/best-practices/idempotency/> | glossary, open-questions, sources | 2026-10-16 | document |
| <https://docs.langchain.com/oss/python/langgraph/persistence> | README, agent-movement-vs-copy-replication-multiplication, checkpoint-relocation, glossary, local-implementation, mobilitybench-experiment-protocol, open-questions, protocols-and-networks/primary-sources, research-landscape, sources, standards-tracker, strategic-target-and-scientific-agenda | 2026-10-16 | document |
| <https://docs.temporal.io/workflow-execution> | README, glossary, mobilitybench-experiment-protocol, open-questions, protocols-and-networks/primary-sources, research-landscape, sources, standards-tracker, strategic-target-and-scientific-agenda | 2026-10-16 | document |
| <https://doi.org/10.1145/3786335.3813130> | 2031-frontier-research-agenda, mobilitybench-experiment-protocol, open-questions, sources, strategic-target-and-scientific-agenda | 2026-10-16 | document |
| <https://modelcontextprotocol.io/specification/2026-07-28> | README, 2031-frontier-research-agenda, agent-communication-and-policy, agent-movement-vs-copy-replication-multiplication, device-compatibility-and-capability-matrix, glossary, human-impact-research-lab, mobilitybench-experiment-protocol, open-questions, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, standards-tracker, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-16 | document |

### [peer-authentication](peer-authentication.md)

| URL | Cited in | Accessed | Date basis |
|---|---|---|---|
| <https://www.rfc-editor.org/rfc/rfc8693> | README, agent-communication-and-policy, agent-movement-vs-copy-replication-multiplication, glossary, mobilitybench-experiment-protocol, peer-authentication, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, standards-tracker, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | default |
| <https://www.rfc-editor.org/rfc/rfc9180> | peer-authentication | 2026-10-15 | default |
| <https://www.rfc-editor.org/rfc/rfc9266> | peer-authentication | 2026-10-15 | default |
| <https://www.rfc-editor.org/rfc/rfc9458> | peer-authentication | 2026-10-15 | default |

### [protocols-and-networks/README](protocols-and-networks/README.md)

| URL | Cited in | Accessed | Date basis |
|---|---|---|---|
| <https://a2a-protocol.org/v1.0.1/specification/> | agent-communication-and-policy, protocols-and-networks/README, protocols-and-networks/primary-sources, protocols-and-networks/protocol-catalog, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | document |
| <https://github.com/a2aproject/A2A/blob/main/docs/topics/custom-protocol-bindings.md> | protocols-and-networks/README | 2026-10-15 | document |
| <https://modelcontextprotocol.io/specification/2026-07-28/basic/transports> | protocols-and-networks/README, protocols-and-networks/primary-sources | 2026-10-15 | document |
| <https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http> | protocols-and-networks/README | 2026-10-15 | document |

### [protocols-and-networks/primary-sources](protocols-and-networks/primary-sources.md)

| URL | Cited in | Accessed | Date basis |
|---|---|---|---|
| <https://a2a-protocol.org/v1.0.1/specification/> | agent-communication-and-policy, protocols-and-networks/README, protocols-and-networks/primary-sources, protocols-and-networks/protocol-catalog, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | document |
| <https://docs.langchain.com/oss/python/langgraph/persistence> | README, agent-movement-vs-copy-replication-multiplication, checkpoint-relocation, glossary, local-implementation, mobilitybench-experiment-protocol, open-questions, protocols-and-networks/primary-sources, research-landscape, sources, standards-tracker, strategic-target-and-scientific-agenda | 2026-10-15 | document |
| <https://docs.nats.io/nats-concepts/jetstream> | protocols-and-networks/primary-sources | 2026-10-15 | document |
| <https://docs.oasis-open.org/amqp/core/v1.0/os/amqp-core-overview-v1.0-os.html> | protocols-and-networks/primary-sources | 2026-10-15 | document |
| <https://docs.oasis-open.org/mqtt/mqtt/v5.0/mqtt-v5.0.html> | protocols-and-networks/primary-sources | 2026-10-15 | document |
| <https://docs.ros.org/en/rolling/Concepts/Intermediate/About-Different-Middleware-Vendors.html> | protocols-and-networks/primary-sources | 2026-10-15 | document |
| <https://docs.ros.org/en/rolling/Concepts/Intermediate/About-Quality-of-Service-Settings.html> | protocols-and-networks/primary-sources | 2026-10-15 | document |
| <https://docs.temporal.io/workflow-execution> | README, glossary, mobilitybench-experiment-protocol, open-questions, protocols-and-networks/primary-sources, research-landscape, sources, standards-tracker, strategic-target-and-scientific-agenda | 2026-10-15 | document |
| <https://github.com/a2aproject/A2A> | protocols-and-networks/primary-sources | 2026-10-15 | document |
| <https://github.com/ag-ui-protocol/ag-ui> | README, glossary, protocols-and-networks/primary-sources, research-landscape, sources | 2026-10-15 | document |
| <https://github.com/ag-ui-protocol/ag-ui/releases/tag/release/2026-09-17> | protocols-and-networks/primary-sources | 2026-10-15 | document |
| <https://github.com/open-telemetry/semantic-conventions-genai> | README, agent-communication-and-policy, glossary, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | document |
| <https://grpc.io/docs/what-is-grpc/core-concepts/> | protocols-and-networks/primary-sources | 2026-10-15 | document |
| <https://html.spec.whatwg.org/multipage/server-sent-events.html> | protocols-and-networks/primary-sources | 2026-10-15 | document |
| <https://kafka.apache.org/documentation/> | protocols-and-networks/primary-sources | 2026-10-15 | document |
| <https://kubernetes.io/docs/concepts/services-networking/service/> | protocols-and-networks/primary-sources | 2026-10-15 | document |
| <https://kubernetes.io/docs/concepts/workloads/controllers/job/> | README, protocols-and-networks/primary-sources, research-landscape, sources | 2026-10-15 | document |
| <https://libp2p.io/docs/> | protocols-and-networks/primary-sources | 2026-10-15 | document |
| <https://modelcontextprotocol.io/specification/2026-07-28> | README, 2031-frontier-research-agenda, agent-communication-and-policy, agent-movement-vs-copy-replication-multiplication, device-compatibility-and-capability-matrix, glossary, human-impact-research-lab, mobilitybench-experiment-protocol, open-questions, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, standards-tracker, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | document |
| <https://modelcontextprotocol.io/specification/2026-07-28/basic/transports> | protocols-and-networks/README, protocols-and-networks/primary-sources | 2026-10-15 | document |
| <https://opcfoundation.org/about/opc-technologies/opc-ua/> | protocols-and-networks/primary-sources | 2026-10-15 | document |
| <https://registry.npmjs.org/@ag-ui/core> | protocols-and-networks/primary-sources, protocols-and-networks/protocol-catalog, standards-tracker | 2026-10-16 | citation |
| <https://specs.opencontainers.org/image-spec/> | README, glossary, protocols-and-networks/primary-sources, research-landscape, sources, standards-tracker | 2026-10-15 | document |
| <https://spiffe.io/docs/latest/spire-about/spire-concepts/> | README, agent-communication-and-policy, agent-forensics-and-fingerprints, glossary, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | document |
| <https://www.bluetooth.com/learn-about-bluetooth/tech-overview/> | protocols-and-networks/primary-sources | 2026-10-15 | document |
| <https://www.openpolicyagent.org/docs> | README, agent-communication-and-policy, glossary, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, standards-tracker | 2026-10-15 | document |
| <https://www.rfc-editor.org/rfc/rfc6455> | protocols-and-networks/primary-sources | 2026-10-15 | document |
| <https://www.rfc-editor.org/rfc/rfc6762> | protocols-and-networks/primary-sources | 2026-10-15 | document |
| <https://www.rfc-editor.org/rfc/rfc6763> | protocols-and-networks/primary-sources | 2026-10-15 | document |
| <https://www.rfc-editor.org/rfc/rfc7252> | protocols-and-networks/primary-sources | 2026-10-15 | document |
| <https://www.rfc-editor.org/rfc/rfc8445> | protocols-and-networks/primary-sources | 2026-10-15 | document |
| <https://www.rfc-editor.org/rfc/rfc8446> | protocols-and-networks/primary-sources | 2026-10-15 | document |
| <https://www.rfc-editor.org/rfc/rfc8656> | protocols-and-networks/primary-sources | 2026-10-15 | document |
| <https://www.rfc-editor.org/rfc/rfc8693> | README, agent-communication-and-policy, agent-movement-vs-copy-replication-multiplication, glossary, mobilitybench-experiment-protocol, peer-authentication, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, standards-tracker, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | document |
| <https://www.rfc-editor.org/rfc/rfc8705> | protocols-and-networks/primary-sources | 2026-10-15 | document |
| <https://www.rfc-editor.org/rfc/rfc8831> | protocols-and-networks/primary-sources | 2026-10-15 | document |
| <https://www.rfc-editor.org/rfc/rfc9000> | protocols-and-networks/primary-sources | 2026-10-15 | document |
| <https://www.rfc-editor.org/rfc/rfc9113> | protocols-and-networks/primary-sources | 2026-10-15 | document |
| <https://www.rfc-editor.org/rfc/rfc9114> | protocols-and-networks/primary-sources | 2026-10-15 | document |
| <https://www.rfc-editor.org/rfc/rfc9293> | protocols-and-networks/primary-sources | 2026-10-15 | document |
| <https://www.rfc-editor.org/rfc/rfc9449> | protocols-and-networks/primary-sources | 2026-10-15 | document |
| <https://www.threadgroup.org/What-is-Thread> | protocols-and-networks/primary-sources | 2026-10-15 | document |
| <https://www.wireguard.com/> | protocols-and-networks/primary-sources | 2026-10-15 | document |

### [protocols-and-networks/protocol-catalog](protocols-and-networks/protocol-catalog.md)

| URL | Cited in | Accessed | Date basis |
|---|---|---|---|
| <https://a2a-protocol.org/v1.0.1/specification/> | agent-communication-and-policy, protocols-and-networks/README, protocols-and-networks/primary-sources, protocols-and-networks/protocol-catalog, unnoticed-and-unauthorized-agent-movement | 2026-10-16 | citation |
| <https://registry.npmjs.org/@ag-ui/core> | protocols-and-networks/primary-sources, protocols-and-networks/protocol-catalog, standards-tracker | 2026-10-16 | citation |

### [research-landscape](research-landscape.md)

| URL | Cited in | Accessed | Date basis |
|---|---|---|---|
| <https://a2a-protocol.org/v1.0.0/specification/> | README, 2031-frontier-research-agenda, a2a-adapter, agent-forensics-and-fingerprints, agent-lifecycle-liveness-and-death, agent-movement-vs-copy-replication-multiplication, cross-agent-prompt-injection, device-compatibility-and-capability-matrix, glossary, human-impact-research-lab, local-implementation, mobilitybench-experiment-protocol, open-questions, research-landscape, security-and-trust, sources, strategic-target-and-scientific-agenda | 2026-10-15 | document |
| <https://aaif.io/projects/> | research-landscape, standards-tracker | 2026-10-15 | document |
| <https://agents.md/> | glossary, research-landscape | 2026-10-16 | section |
| <https://agentskills.io/client-implementation/adding-skills-support> | research-landscape | 2026-10-16 | section |
| <https://agentskills.io/home> | research-landscape, standards-tracker | 2026-10-16 | section |
| <https://agentskills.io/specification> | glossary, research-landscape, standards-tracker | 2026-10-16 | section |
| <https://chromedevtools.github.io/devtools-protocol/> | research-landscape, standards-tracker | 2026-10-16 | section |
| <https://developers.openai.com/api/docs/guides/tools-computer-use> | research-landscape | 2026-10-16 | section |
| <https://docs.langchain.com/oss/python/langgraph/persistence> | README, agent-movement-vs-copy-replication-multiplication, checkpoint-relocation, glossary, local-implementation, mobilitybench-experiment-protocol, open-questions, protocols-and-networks/primary-sources, research-landscape, sources, standards-tracker, strategic-target-and-scientific-agenda | 2026-10-15 | document |
| <https://docs.temporal.io/workflow-execution> | README, glossary, mobilitybench-experiment-protocol, open-questions, protocols-and-networks/primary-sources, research-landscape, sources, standards-tracker, strategic-target-and-scientific-agenda | 2026-10-15 | document |
| <https://github.com/ag-ui-protocol/ag-ui> | README, glossary, protocols-and-networks/primary-sources, research-landscape, sources | 2026-10-15 | document |
| <https://github.com/agentskills/agentskills> | research-landscape | 2026-10-16 | section |
| <https://github.com/agentsmd/agents.md> | glossary, research-landscape, standards-tracker | 2026-10-16 | section |
| <https://github.com/microsoft/playwright-mcp> | research-landscape | 2026-10-16 | section |
| <https://github.com/microsoft/playwright-mcp/releases> | research-landscape | 2026-10-16 | section |
| <https://github.com/open-telemetry/semantic-conventions-genai> | README, agent-communication-and-policy, glossary, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | document |
| <https://github.com/webmachinelearning/webmcp/blob/main/implementation-status.md> | research-landscape | 2026-10-16 | section |
| <https://github.com/webmachinelearning/webmcp/blob/main/index.bs> | research-landscape | 2026-10-16 | section |
| <https://kubernetes.io/docs/concepts/workloads/controllers/job/> | README, protocols-and-networks/primary-sources, research-landscape, sources | 2026-10-15 | document |
| <https://modelcontextprotocol.io/specification/2026-07-28> | README, 2031-frontier-research-agenda, agent-communication-and-policy, agent-movement-vs-copy-replication-multiplication, device-compatibility-and-capability-matrix, glossary, human-impact-research-lab, mobilitybench-experiment-protocol, open-questions, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, standards-tracker, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | document |
| <https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview> | glossary, research-landscape | 2026-10-16 | section |
| <https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool> | research-landscape | 2026-10-16 | section |
| <https://specs.opencontainers.org/image-spec/> | README, glossary, protocols-and-networks/primary-sources, research-landscape, sources, standards-tracker | 2026-10-15 | document |
| <https://spiffe.io/docs/latest/spire-about/spire-concepts/> | README, agent-communication-and-policy, agent-forensics-and-fingerprints, glossary, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | document |
| <https://webmachinelearning.github.io/webmcp/> | glossary, research-landscape, standards-tracker | 2026-10-16 | section |
| <https://www.openpolicyagent.org/docs> | README, agent-communication-and-policy, glossary, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, standards-tracker | 2026-10-15 | document |
| <https://www.rfc-editor.org/rfc/rfc8693> | README, agent-communication-and-policy, agent-movement-vs-copy-replication-multiplication, glossary, mobilitybench-experiment-protocol, peer-authentication, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, standards-tracker, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | document |
| <https://www.w3.org/TR/webdriver-bidi/> | glossary, research-landscape, standards-tracker | 2026-10-16 | section |

### [security-and-trust](security-and-trust.md)

| URL | Cited in | Accessed | Date basis |
|---|---|---|---|
| <https://a2a-protocol.org/v1.0.0/specification/> | README, 2031-frontier-research-agenda, a2a-adapter, agent-forensics-and-fingerprints, agent-lifecycle-liveness-and-death, agent-movement-vs-copy-replication-multiplication, cross-agent-prompt-injection, device-compatibility-and-capability-matrix, glossary, human-impact-research-lab, local-implementation, mobilitybench-experiment-protocol, open-questions, research-landscape, security-and-trust, sources, strategic-target-and-scientific-agenda | 2026-10-15 | default |
| <https://genai.owasp.org/download/52117/?tmstv=1765059207> | security-and-trust | 2026-10-16 | citation |
| <https://genai.owasp.org/llmrisk/llm062025-excessive-agency/> | security-and-trust | 2026-10-16 | citation |
| <https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/> | agent-communication-and-policy, human-impact-research-lab, mobilitybench-experiment-protocol, security-and-trust, strategic-target-and-scientific-agenda, top-20-human-impact-questions-for-agentic-ai | 2026-10-16 | citation |
| <https://github.com/open-telemetry/semantic-conventions-genai> | README, agent-communication-and-policy, glossary, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | default |
| <https://modelcontextprotocol.io/specification/2026-07-28> | README, 2031-frontier-research-agenda, agent-communication-and-policy, agent-movement-vs-copy-replication-multiplication, device-compatibility-and-capability-matrix, glossary, human-impact-research-lab, mobilitybench-experiment-protocol, open-questions, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, standards-tracker, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | default |
| <https://spiffe.io/docs/latest/spire-about/spire-concepts/> | README, agent-communication-and-policy, agent-forensics-and-fingerprints, glossary, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | default |
| <https://www.openpolicyagent.org/docs> | README, agent-communication-and-policy, glossary, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, standards-tracker | 2026-10-15 | default |
| <https://www.rfc-editor.org/rfc/rfc8693> | README, agent-communication-and-policy, agent-movement-vs-copy-replication-multiplication, glossary, mobilitybench-experiment-protocol, peer-authentication, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, standards-tracker, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | default |

### [sources](sources.md)

| URL | Cited in | Accessed | Date basis |
|---|---|---|---|
| <https://a2a-protocol.org/v1.0.0/specification/> | README, 2031-frontier-research-agenda, a2a-adapter, agent-forensics-and-fingerprints, agent-lifecycle-liveness-and-death, agent-movement-vs-copy-replication-multiplication, cross-agent-prompt-injection, device-compatibility-and-capability-matrix, glossary, human-impact-research-lab, local-implementation, mobilitybench-experiment-protocol, open-questions, research-landscape, security-and-trust, sources, strategic-target-and-scientific-agenda | 2026-10-15 | document |
| <https://arxiv.org/abs/2510.04173> | glossary, open-questions, sources | 2026-10-15 | document |
| <https://arxiv.org/abs/2608.21208> | open-questions, sources, strategic-target-and-scientific-agenda | 2026-10-15 | document |
| <https://blog.modelcontextprotocol.io/posts/2026-07-28/> | language-and-sdk-strategy, open-questions, sources, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | document |
| <https://csrc.nist.gov/pubs/sp/800/86/final> | agent-forensics-and-fingerprints, glossary, movement-receipts, sources | 2026-10-15 | document |
| <https://docs.aws.amazon.com/durable-execution/patterns/best-practices/idempotency/> | glossary, open-questions, sources | 2026-10-15 | document |
| <https://docs.langchain.com/oss/python/langgraph/persistence> | README, agent-movement-vs-copy-replication-multiplication, checkpoint-relocation, glossary, local-implementation, mobilitybench-experiment-protocol, open-questions, protocols-and-networks/primary-sources, research-landscape, sources, standards-tracker, strategic-target-and-scientific-agenda | 2026-10-15 | document |
| <https://docs.sigstore.dev/cosign/verifying/attestation/> | agent-forensics-and-fingerprints, sources | 2026-10-15 | document |
| <https://docs.temporal.io/child-workflows> | agent-movement-vs-copy-replication-multiplication, sources | 2026-10-15 | document |
| <https://docs.temporal.io/workflow-execution> | README, glossary, mobilitybench-experiment-protocol, open-questions, protocols-and-networks/primary-sources, research-landscape, sources, standards-tracker, strategic-target-and-scientific-agenda | 2026-10-15 | document |
| <https://docs.temporal.io/workflows> | agent-movement-vs-copy-replication-multiplication, sources | 2026-10-15 | document |
| <https://doi.org/10.1145/3786335.3813130> | 2031-frontier-research-agenda, mobilitybench-experiment-protocol, open-questions, sources, strategic-target-and-scientific-agenda | 2026-10-15 | document |
| <https://github.com/OpenLineage/OpenLineage/blob/main/spec/OpenLineage.md> | agent-forensics-and-fingerprints, glossary, sources | 2026-10-15 | document |
| <https://github.com/ag-ui-protocol/ag-ui> | README, glossary, protocols-and-networks/primary-sources, research-landscape, sources | 2026-10-15 | document |
| <https://github.com/in-toto/attestation> | agent-forensics-and-fingerprints, glossary, movement-receipts, sources | 2026-10-15 | document |
| <https://github.com/open-telemetry/semantic-conventions-genai> | README, agent-communication-and-policy, glossary, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-16 | citation |
| <https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md> | agent-forensics-and-fingerprints, sources | 2026-10-15 | document |
| <https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/> | agent-movement-vs-copy-replication-multiplication, glossary, sources | 2026-10-15 | document |
| <https://kubernetes.io/docs/concepts/workloads/controllers/deployment/> | agent-movement-vs-copy-replication-multiplication, glossary, sources | 2026-10-15 | document |
| <https://kubernetes.io/docs/concepts/workloads/controllers/job/> | README, protocols-and-networks/primary-sources, research-landscape, sources | 2026-10-15 | document |
| <https://modelcontextprotocol.io/specification/2026-07-28> | README, 2031-frontier-research-agenda, agent-communication-and-policy, agent-movement-vs-copy-replication-multiplication, device-compatibility-and-capability-matrix, glossary, human-impact-research-lab, mobilitybench-experiment-protocol, open-questions, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, standards-tracker, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | document |
| <https://opentelemetry.io/docs/specs/otel/trace/sdk/> | agent-forensics-and-fingerprints, sources | 2026-10-15 | document |
| <https://specs.opencontainers.org/image-spec/> | README, glossary, protocols-and-networks/primary-sources, research-landscape, sources, standards-tracker | 2026-10-15 | document |
| <https://spiffe.io/docs/latest/deploying/svids/> | agent-forensics-and-fingerprints, agent-lifecycle-liveness-and-death, glossary, movement-receipts, sources | 2026-10-15 | document |
| <https://spiffe.io/docs/latest/spiffe-specs/spiffe_workload_api/> | agent-movement-vs-copy-replication-multiplication, sources | 2026-10-15 | document |
| <https://spiffe.io/docs/latest/spire-about/spire-concepts/> | README, agent-communication-and-policy, agent-forensics-and-fingerprints, glossary, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | document |
| <https://www.openpolicyagent.org/docs> | README, agent-communication-and-policy, glossary, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, standards-tracker | 2026-10-15 | document |
| <https://www.rfc-editor.org/rfc/rfc8693> | README, agent-communication-and-policy, agent-movement-vs-copy-replication-multiplication, glossary, mobilitybench-experiment-protocol, peer-authentication, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, standards-tracker, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | document |
| <https://www.rfc-editor.org/rfc/rfc8785.html> | agent-forensics-and-fingerprints, glossary, movement-receipts, sources | 2026-10-15 | document |
| <https://www.w3.org/TR/baggage/> | agent-forensics-and-fingerprints, glossary, movement-receipts, sources | 2026-10-15 | document |
| <https://www.w3.org/TR/trace-context/> | agent-forensics-and-fingerprints, glossary, how-it-works, movement-receipts, sources | 2026-10-15 | document |

### [standards-tracker](standards-tracker.md)

| URL | Cited in | Accessed | Date basis |
|---|---|---|---|
| <https://a2a-protocol.org/latest/specification/> | standards-tracker | 2026-10-16 | document |
| <https://aaif.io/blog/a2a-joins-aaif> | standards-tracker | 2026-10-16 | document |
| <https://aaif.io/projects/> | research-landscape, standards-tracker | 2026-10-16 | document |
| <https://agenticcommerce.dev/> | standards-tracker | 2026-10-16 | document |
| <https://agentskills.io/home> | research-landscape, standards-tracker | 2026-10-16 | document |
| <https://agentskills.io/specification> | glossary, research-landscape, standards-tracker | 2026-10-16 | document |
| <https://ap2-protocol.org/> | standards-tracker | 2026-10-16 | document |
| <https://chromedevtools.github.io/devtools-protocol/> | research-landscape, standards-tracker | 2026-10-16 | document |
| <https://datatracker.ietf.org/doc/draft-ietf-oauth-identity-chaining/> | standards-tracker | 2026-10-16 | document |
| <https://datatracker.ietf.org/doc/draft-ietf-oauth-identity-chaining/history/> | standards-tracker | 2026-10-16 | document |
| <https://datatracker.ietf.org/doc/draft-ietf-oauth-transaction-tokens/> | standards-tracker | 2026-10-16 | document |
| <https://datatracker.ietf.org/doc/draft-ietf-oauth-transaction-tokens/history/> | standards-tracker | 2026-10-16 | document |
| <https://datatracker.ietf.org/doc/draft-ietf-wimse-aims/> | standards-tracker | 2026-10-16 | document |
| <https://datatracker.ietf.org/doc/draft-ietf-wimse-aims/history/> | standards-tracker | 2026-10-16 | document |
| <https://datatracker.ietf.org/doc/draft-ietf-wimse-arch/> | standards-tracker | 2026-10-16 | document |
| <https://datatracker.ietf.org/doc/draft-ietf-wimse-arch/history/> | standards-tracker | 2026-10-16 | document |
| <https://datatracker.ietf.org/doc/draft-oauth-ai-agents-on-behalf-of-user/> | standards-tracker | 2026-10-16 | document |
| <https://datatracker.ietf.org/doc/draft-oauth-ai-agents-on-behalf-of-user/history/> | standards-tracker | 2026-10-16 | document |
| <https://datatracker.ietf.org/doc/rfc8693/> | standards-tracker | 2026-10-16 | document |
| <https://docs.ag-ui.com/introduction> | standards-tracker | 2026-10-16 | document |
| <https://docs.langchain.com/oss/python/langgraph/persistence> | README, agent-movement-vs-copy-replication-multiplication, checkpoint-relocation, glossary, local-implementation, mobilitybench-experiment-protocol, open-questions, protocols-and-networks/primary-sources, research-landscape, sources, standards-tracker, strategic-target-and-scientific-agenda | 2026-10-16 | document |
| <https://docs.temporal.io/workflow-execution> | README, glossary, mobilitybench-experiment-protocol, open-questions, protocols-and-networks/primary-sources, research-landscape, sources, standards-tracker, strategic-target-and-scientific-agenda | 2026-10-16 | document |
| <https://github.com/a2aproject/A2A/releases> | standards-tracker | 2026-10-16 | document |
| <https://github.com/a2aproject/A2A/releases/tag/v1.0.1> | standards-tracker | 2026-10-16 | document |
| <https://github.com/ag-ui-protocol/ag-ui/releases> | standards-tracker | 2026-10-16 | document |
| <https://github.com/agent-network-protocol/AgentNetworkProtocol> | standards-tracker | 2026-10-16 | document |
| <https://github.com/agent-network-protocol/AgentNetworkProtocol/releases> | standards-tracker | 2026-10-16 | document |
| <https://github.com/agentic-commerce-protocol/agentic-commerce-protocol/tree/main/changelog> | standards-tracker | 2026-10-16 | document |
| <https://github.com/agentskills/agentskills/commits/main> | standards-tracker | 2026-10-16 | document |
| <https://github.com/agentsmd/agents.md> | glossary, research-landscape, standards-tracker | 2026-10-16 | document |
| <https://github.com/agentsmd/agents.md/commits/main> | standards-tracker | 2026-10-16 | document |
| <https://github.com/agntcy/oasf> | standards-tracker | 2026-10-16 | document |
| <https://github.com/agntcy/oasf/releases> | standards-tracker | 2026-10-16 | document |
| <https://github.com/google-agentic-commerce/AP2/releases> | standards-tracker | 2026-10-16 | document |
| <https://github.com/i-am-bee/acp> | standards-tracker | 2026-10-16 | document |
| <https://github.com/kubernetes/kubernetes/releases> | standards-tracker | 2026-10-16 | document |
| <https://github.com/langchain-ai/langgraph/releases> | standards-tracker | 2026-10-16 | document |
| <https://github.com/open-policy-agent/opa/releases> | standards-tracker | 2026-10-16 | document |
| <https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/README.md> | standards-tracker | 2026-10-16 | document |
| <https://github.com/open-telemetry/semantic-conventions-genai/commits/main> | standards-tracker | 2026-10-16 | document |
| <https://github.com/open-telemetry/semantic-conventions/releases> | standards-tracker | 2026-10-16 | document |
| <https://github.com/open-telemetry/semantic-conventions/releases/tag/v1.42.0> | standards-tracker | 2026-10-16 | document |
| <https://github.com/opencontainers/distribution-spec> | standards-tracker | 2026-10-16 | document |
| <https://github.com/opencontainers/distribution-spec/releases> | standards-tracker | 2026-10-16 | document |
| <https://github.com/opencontainers/image-spec/releases> | standards-tracker | 2026-10-16 | document |
| <https://github.com/opencontainers/runtime-spec> | standards-tracker | 2026-10-16 | document |
| <https://github.com/opencontainers/runtime-spec/releases> | standards-tracker | 2026-10-16 | document |
| <https://github.com/spiffe/spire/releases> | standards-tracker | 2026-10-16 | document |
| <https://github.com/temporalio/sdk-go/releases/tag/v1.50.0> | standards-tracker | 2026-10-16 | document |
| <https://github.com/temporalio/sdk-python/releases> | standards-tracker | 2026-10-16 | document |
| <https://github.com/temporalio/temporal/releases> | standards-tracker | 2026-10-16 | document |
| <https://github.com/webmachinelearning/webmcp/commits/main> | standards-tracker | 2026-10-16 | document |
| <https://kubernetes.io/releases/> | standards-tracker | 2026-10-16 | document |
| <https://lfaidata.foundation/communityblog/2025/08/29/acp-joins-forces-with-a2a-under-the-linux-foundations-lf-ai-data/> | standards-tracker | 2026-10-16 | document |
| <https://modelcontextprotocol.io/specification/2026-07-28> | README, 2031-frontier-research-agenda, agent-communication-and-policy, agent-movement-vs-copy-replication-multiplication, device-compatibility-and-capability-matrix, glossary, human-impact-research-lab, mobilitybench-experiment-protocol, open-questions, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, standards-tracker, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-16 | document |
| <https://modelcontextprotocol.io/specification/2026-07-28/changelog> | standards-tracker | 2026-10-16 | document |
| <https://modelcontextprotocol.io/specification/versioning> | standards-tracker | 2026-10-16 | document |
| <https://opentelemetry.io/docs/specs/semconv/> | standards-tracker | 2026-10-16 | document |
| <https://registry.npmjs.org/@ag-ui/core> | protocols-and-networks/primary-sources, protocols-and-networks/protocol-catalog, standards-tracker | 2026-10-16 | document |
| <https://specs.opencontainers.org/image-spec/> | README, glossary, protocols-and-networks/primary-sources, research-landscape, sources, standards-tracker | 2026-10-16 | document |
| <https://spiffe.io/docs/latest/spiffe-about/overview/> | standards-tracker | 2026-10-16 | document |
| <https://webmachinelearning.github.io/webmcp/> | glossary, research-landscape, standards-tracker | 2026-10-16 | document |
| <https://www.linuxfoundation.org/press/linux-foundation-announces-the-formation-of-the-agentic-ai-foundation> | standards-tracker | 2026-10-16 | document |
| <https://www.openpolicyagent.org/docs> | README, agent-communication-and-policy, glossary, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, standards-tracker | 2026-10-16 | document |
| <https://www.rfc-editor.org/rfc/rfc8693> | README, agent-communication-and-policy, agent-movement-vs-copy-replication-multiplication, glossary, mobilitybench-experiment-protocol, peer-authentication, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, standards-tracker, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-16 | document |
| <https://www.w3.org/TR/did-1.1/> | standards-tracker | 2026-10-16 | document |
| <https://www.w3.org/TR/did-core/> | standards-tracker | 2026-10-16 | document |
| <https://www.w3.org/TR/vc-data-model-2.0/> | standards-tracker | 2026-10-16 | document |
| <https://www.w3.org/TR/webdriver-bidi/> | glossary, research-landscape, standards-tracker | 2026-10-16 | document |
| <https://www.w3.org/standards/history/did-1.1/> | standards-tracker | 2026-10-16 | document |
| <https://www.w3.org/standards/history/vc-data-model-2.0/> | standards-tracker | 2026-10-16 | document |
| <https://www.w3.org/standards/history/webdriver-bidi/> | standards-tracker | 2026-10-16 | document |

### [strategic-target-and-scientific-agenda](strategic-target-and-scientific-agenda.md)

| URL | Cited in | Accessed | Date basis |
|---|---|---|---|
| <https://a2a-protocol.org/v1.0.0/specification/> | README, 2031-frontier-research-agenda, a2a-adapter, agent-forensics-and-fingerprints, agent-lifecycle-liveness-and-death, agent-movement-vs-copy-replication-multiplication, cross-agent-prompt-injection, device-compatibility-and-capability-matrix, glossary, human-impact-research-lab, local-implementation, mobilitybench-experiment-protocol, open-questions, research-landscape, security-and-trust, sources, strategic-target-and-scientific-agenda | 2026-10-15 | default |
| <https://arxiv.org/abs/2608.21208> | open-questions, sources, strategic-target-and-scientific-agenda | 2026-10-15 | default |
| <https://blog.modelcontextprotocol.io/posts/2026-07-28/> | language-and-sdk-strategy, open-questions, sources, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | default |
| <https://docs.langchain.com/oss/python/langgraph/persistence> | README, agent-movement-vs-copy-replication-multiplication, checkpoint-relocation, glossary, local-implementation, mobilitybench-experiment-protocol, open-questions, protocols-and-networks/primary-sources, research-landscape, sources, standards-tracker, strategic-target-and-scientific-agenda | 2026-10-15 | default |
| <https://docs.temporal.io/workflow-execution> | README, glossary, mobilitybench-experiment-protocol, open-questions, protocols-and-networks/primary-sources, research-landscape, sources, standards-tracker, strategic-target-and-scientific-agenda | 2026-10-15 | default |
| <https://doi.org/10.1145/3786335.3813130> | 2031-frontier-research-agenda, mobilitybench-experiment-protocol, open-questions, sources, strategic-target-and-scientific-agenda | 2026-10-15 | default |
| <https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/> | agent-communication-and-policy, human-impact-research-lab, mobilitybench-experiment-protocol, security-and-trust, strategic-target-and-scientific-agenda, top-20-human-impact-questions-for-agentic-ai | 2026-10-15 | default |
| <https://github.com/open-telemetry/semantic-conventions-genai> | README, agent-communication-and-policy, glossary, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | default |
| <https://github.com/oracle/agent-spec> | strategic-target-and-scientific-agenda | 2026-10-15 | default |
| <https://modelcontextprotocol.io/specification/2026-07-28> | README, 2031-frontier-research-agenda, agent-communication-and-policy, agent-movement-vs-copy-replication-multiplication, device-compatibility-and-capability-matrix, glossary, human-impact-research-lab, mobilitybench-experiment-protocol, open-questions, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, standards-tracker, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | default |
| <https://spiffe.io/docs/latest/spire-about/spire-concepts/> | README, agent-communication-and-policy, agent-forensics-and-fingerprints, glossary, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | default |
| <https://www.nist.gov/news-events/news/2026/02/announcing-ai-agent-standards-initiative-interoperable-and-secure> | human-impact-research-lab, strategic-target-and-scientific-agenda, top-20-human-impact-questions-for-agentic-ai | 2026-10-15 | default |
| <https://www.rfc-editor.org/rfc/rfc8693> | README, agent-communication-and-policy, agent-movement-vs-copy-replication-multiplication, glossary, mobilitybench-experiment-protocol, peer-authentication, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, standards-tracker, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | default |

### [top-20-human-impact-questions-for-agentic-ai](top-20-human-impact-questions-for-agentic-ai.md)

| URL | Cited in | Accessed | Date basis |
|---|---|---|---|
| <https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/> | agent-communication-and-policy, human-impact-research-lab, mobilitybench-experiment-protocol, security-and-trust, strategic-target-and-scientific-agenda, top-20-human-impact-questions-for-agentic-ai | 2026-10-15 | section |
| <https://hai.stanford.edu/ai-index/2026-ai-index-report> | top-20-human-impact-questions-for-agentic-ai | 2026-10-15 | section |
| <https://hai.stanford.edu/ai-index/2026-ai-index-report/science> | top-20-human-impact-questions-for-agentic-ai | 2026-10-15 | section |
| <https://internationalaisafetyreport.org/publication/international-ai-safety-report-2026> | top-20-human-impact-questions-for-agentic-ai | 2026-10-15 | section |
| <https://www.iea.org/reports/energy-and-ai/energy-demand-from-ai> | top-20-human-impact-questions-for-agentic-ai | 2026-10-15 | section |
| <https://www.ilo.org/publications/generative-ai-and-jobs-2025-update> | top-20-human-impact-questions-for-agentic-ai | 2026-10-15 | section |
| <https://www.nist.gov/news-events/news/2026/02/announcing-ai-agent-standards-initiative-interoperable-and-secure> | human-impact-research-lab, strategic-target-and-scientific-agenda, top-20-human-impact-questions-for-agentic-ai | 2026-10-15 | section |
| <https://www.oecd.org/en/publications/oecd-due-diligence-guidance-for-responsible-ai_41671712-en.html> | top-20-human-impact-questions-for-agentic-ai | 2026-10-15 | section |
| <https://www.unesco.org/en/articles/guidance-generative-ai-education-and-research?hub=253682> | top-20-human-impact-questions-for-agentic-ai | 2026-10-15 | section |
| <https://www.unicef.org/innocenti/reports/policy-guidance-ai-children> | top-20-human-impact-questions-for-agentic-ai | 2026-10-15 | section |
| <https://www.who.int/news/item/18-01-2024-who-releases-ai-ethics-and-governance-guidance-for-large-multi-modal-models> | top-20-human-impact-questions-for-agentic-ai | 2026-10-15 | section |

### [unnoticed-and-unauthorized-agent-movement](unnoticed-and-unauthorized-agent-movement.md)

| URL | Cited in | Accessed | Date basis |
|---|---|---|---|
| <https://a2a-protocol.org/v1.0.1/specification/> | agent-communication-and-policy, protocols-and-networks/README, protocols-and-networks/primary-sources, protocols-and-networks/protocol-catalog, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | document |
| <https://a2a-protocol.org/v1.0.1/topics/enterprise-ready/> | unnoticed-and-unauthorized-agent-movement | 2026-10-15 | document |
| <https://arxiv.org/abs/2402.08567> | unnoticed-and-unauthorized-agent-movement | 2026-10-15 | document |
| <https://arxiv.org/abs/2403.02817v2> | unnoticed-and-unauthorized-agent-movement | 2026-10-15 | document |
| <https://arxiv.org/abs/2410.07283v1> | unnoticed-and-unauthorized-agent-movement | 2026-10-15 | document |
| <https://arxiv.org/abs/2503.12188> | unnoticed-and-unauthorized-agent-movement | 2026-10-15 | document |
| <https://attack.mitre.org/techniques/T1021/004/> | unnoticed-and-unauthorized-agent-movement | 2026-10-15 | document |
| <https://attack.mitre.org/techniques/T1021/007/> | unnoticed-and-unauthorized-agent-movement | 2026-10-15 | document |
| <https://blog.modelcontextprotocol.io/posts/2026-07-28/> | language-and-sdk-strategy, open-questions, sources, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | document |
| <https://genai.owasp.org/2025/12/09/owasp-top-10-for-agentic-applications-the-benchmark-for-agentic-security-in-the-age-of-autonomous-ai/> | unnoticed-and-unauthorized-agent-movement | 2026-10-15 | document |
| <https://genai.owasp.org/resource/agentic-ai-threats-and-mitigations/> | unnoticed-and-unauthorized-agent-movement | 2026-10-15 | document |
| <https://github.com/open-telemetry/semantic-conventions-genai> | README, agent-communication-and-policy, glossary, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | document |
| <https://modelcontextprotocol.io/specification/2026-07-28> | README, 2031-frontier-research-agenda, agent-communication-and-policy, agent-movement-vs-copy-replication-multiplication, device-compatibility-and-capability-matrix, glossary, human-impact-research-lab, mobilitybench-experiment-protocol, open-questions, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, standards-tracker, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | document |
| <https://spiffe.io/docs/latest/spire-about/spire-concepts/> | README, agent-communication-and-policy, agent-forensics-and-fingerprints, glossary, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | document |
| <https://www.rfc-editor.org/rfc/rfc8693> | README, agent-communication-and-policy, agent-movement-vs-copy-replication-multiplication, glossary, mobilitybench-experiment-protocol, peer-authentication, protocols-and-networks/primary-sources, research-landscape, security-and-trust, sources, standards-tracker, strategic-target-and-scientific-agenda, unnoticed-and-unauthorized-agent-movement | 2026-10-15 | document |

<!-- sources-index:end -->
