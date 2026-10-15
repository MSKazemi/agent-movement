# Sources and evidence log

Reviewed on **2026-10-15**; links and corpus counts fact-checked 2026-10-16. This is a selective standards/documentation survey, not a comprehensive systematic review. Verify specific upstream release dates and implementation behavior before claiming conformance. All architecture and envelope design in this repository are **proposals**.

| Topic | Primary source | Evidence scope |
|---|---|---|
| A2A protocol | https://a2a-protocol.org/v1.0.0/specification/ | Agent communication, task and artifact interfaces |
| MCP spec | https://modelcontextprotocol.io/specification/2026-07-28 | Model/agent interface to tools, resources, prompts |
| AG-UI | https://github.com/ag-ui-protocol/ag-ui | Agent-user interaction/event protocol |
| LangGraph persistence | https://docs.langchain.com/oss/python/langgraph/persistence | Checkpoint/threads persistence in LangGraph |
| Temporal workflows | https://docs.temporal.io/workflow-execution | Durable execution semantics in Temporal |
| OCI image spec | https://specs.opencontainers.org/image-spec/ | Container image portability |
| Kubernetes Job | https://kubernetes.io/docs/concepts/workloads/controllers/job/ | Batch workload execution/retries |
| OAuth 2.0 Token Exchange | https://www.rfc-editor.org/rfc/rfc8693 | Standard token exchange mechanism, not automatic delegation trust |
| SPIFFE / SPIRE | https://spiffe.io/docs/latest/spire-about/spire-concepts/ | Workload identity concepts |
| Open Policy Agent | https://www.openpolicyagent.org/docs | Policy-as-code engine |
| OpenTelemetry GenAI | https://github.com/open-telemetry/semantic-conventions-genai | GenAI trace/metric convention family (moved from opentelemetry.io; status Development, checked 2026-10-16) |

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

## Paper corpus

Scholarly papers (75 items, 1980–2026), including the classic mobile-agent, process-migration and delegation literature, are collected and independently audited in [paper-corpus/](paper-corpus/README.md). 73 of the 75 papers have a DOI and/or arXiv ID (the other two, a USENIX NSDI 2005 paper and an OpenAI white paper, are identified by their canonical URL); each has a peer-review flag, a paraphrased summary and a biblatex entry in [papers.bib](paper-corpus/papers.bib).

## News corpus

Dated industry, standards and security news (100 items, 2024-11 to 2026-10) is collected under a documented protocol in [news-corpus/](news-corpus/README.md). Every item has a paraphrased summary, coded movement operations, a verification flag and a biblatex entry in [news.bib](news-corpus/news.bib). Cite the original sources, not the corpus summaries.

Related documents: [landscape](research-landscape.md), [questions](open-questions.md), [roadmap](roadmap.md).
