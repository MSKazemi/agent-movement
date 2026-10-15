# Standards and protocol version tracker

**Accessed:** 2026-10-16. **Machine-readable copy:** [`data/standards-tracker.csv`](../data/standards-tracker.csv) (28 rows, same content plus notes).

This page records, for each standard or protocol this repository relies on, the latest version, its release date, its maturity, who governs it, and where to watch for changes. Every row cites a primary source: a specification site, an official repository release or tag, a standards-body page, or the IETF datatracker. Where a fact could not be confirmed from a primary source it is marked **unverified**.

**Maturity labels used here:**
- **stable**: a released, non-draft version (released spec, final release tag, W3C Recommendation, RFC).
- **beta / pre-1.0**: released but labelled beta or still at version 0.x by its maintainers.
- **draft**: Internet-Draft, W3C Candidate Recommendation, or a spec section marked draft.
- **experimental**: marked "Development" or experimental by the maintainers.
- **archived**: no longer developed.

"What it means for agent movement" is this project's interpretation. It is not a claim made by the upstream source.

## Summary table

| Name | Layer | Latest version | Release date | Maturity | Governing body | Primary source | Change watch |
|---|---|---|---|---|---|---|---|
| A2A | agent-to-agent | v1.0.1 (site labels 1.0.0 as latest released) | 2026-05-28 (v1.0.0: 2026-03-12) | stable | AAIF / Linux Foundation (since 2026-08-17) | [spec](https://a2a-protocol.org/latest/specification/) | [releases](https://github.com/a2aproject/A2A/releases) |
| MCP | agent-to-tool | 2026-07-28 (Current) | 2026-07-28 | stable | AAIF / Linux Foundation (since 2025-12-09) | [spec](https://modelcontextprotocol.io/specification/2026-07-28) | [changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog) |
| AG-UI | agent-to-user | AG-UI 1.0 (`@ag-ui/core` 1.0.2) | 2026-09-17 (1.0.0) | released 1.0 SDK; no formal stability statement found | Community, originated by CopilotKit | [docs](https://docs.ag-ui.com/introduction) | [releases](https://github.com/ag-ui-protocol/ag-ui/releases) |
| ACP (IBM / BeeAI) | agent-to-agent | v1.0.3 (final) | 2025-08-21 | archived, merged into A2A | LF AI & Data | [merger post](https://lfaidata.foundation/communityblog/2025/08/29/acp-joins-forces-with-a2a-under-the-linux-foundations-lf-ai-data/) | [repo](https://github.com/i-am-bee/acp) |
| ANP | agent-to-agent | ANP 1.2 | 2026-09-24 | stable per project; ANP-05/06 draft | ANP open-source community | [repo](https://github.com/agent-network-protocol/AgentNetworkProtocol) | [releases](https://github.com/agent-network-protocol/AgentNetworkProtocol/releases) |
| AGNTCY OASF | agent-to-agent (discovery) | v1.1.0 | 2026-07-10 | stable | AGNTCY / Linux Foundation (since 2025-07-29) | [repo](https://github.com/agntcy/oasf) | [releases](https://github.com/agntcy/oasf/releases) |
| AP2 | identity/authz (payment mandates) | v0.2.0 | 2026-04-28 | pre-1.0 | Google origin; site states donation to FIDO Alliance (date unverified) | [site](https://ap2-protocol.org/) | [releases](https://github.com/google-agentic-commerce/AP2/releases) |
| Agentic Commerce Protocol | agent-to-merchant | 2026-04-17 (dated spec) | 2026-04-17 | beta | OpenAI and Stripe | [site](https://agenticcommerce.dev/) | [changelog](https://github.com/agentic-commerce-protocol/agentic-commerce-protocol/tree/main/changelog) |
| AGENTS.md | agent configuration | unversioned | unverified | living format | AAIF / Linux Foundation | [repo](https://github.com/agentsmd/agents.md) | [commits](https://github.com/agentsmd/agents.md/commits/main) |
| LangGraph persistence | durability | `langgraph-checkpoint` 4.3.0; `langgraph` 1.2.15; `langgraph-checkpoint-postgres` 3.2.0 | 2026-10-12 / 2026-10-12 / 2026-10-14 | stable | LangChain Inc. | [docs](https://docs.langchain.com/oss/python/langgraph/persistence) | [releases](https://github.com/langchain-ai/langgraph/releases) |
| Temporal Server | durability | v1.32.1 | 2026-10-08 | stable | Temporal Technologies | [docs](https://docs.temporal.io/workflow-execution) | [releases](https://github.com/temporalio/temporal/releases) |
| Temporal SDKs | durability | Go v1.50.0; Python 1.34.0 | 2026-10-15 / 2026-09-30 | stable | Temporal Technologies | [Go release](https://github.com/temporalio/sdk-go/releases/tag/v1.50.0) | [Python releases](https://github.com/temporalio/sdk-python/releases) |
| OCI Image Spec | deployment | v1.1.1 | 2025-03-03 | stable | Open Container Initiative | [spec](https://specs.opencontainers.org/image-spec/) | [releases](https://github.com/opencontainers/image-spec/releases) |
| OCI Runtime Spec | deployment | v1.3.0 | 2025-11-04 | stable | Open Container Initiative | [repo](https://github.com/opencontainers/runtime-spec) | [releases](https://github.com/opencontainers/runtime-spec/releases) |
| OCI Distribution Spec | deployment | v1.1.1 | 2025-01-29 | stable | Open Container Initiative | [repo](https://github.com/opencontainers/distribution-spec) | [releases](https://github.com/opencontainers/distribution-spec/releases) |
| Kubernetes | deployment | v1.37.1 | 1.37.0: 2026-08-26; 1.37.1: 2026-09-15 (see discrepancies) | stable (1.38 in alpha) | CNCF | [releases page](https://kubernetes.io/releases/) | [releases](https://github.com/kubernetes/kubernetes/releases) |
| OAuth 2.0 Token Exchange | identity/authz | RFC 8693 | 2020-01 | stable (Proposed Standard) | IETF OAuth WG | [RFC](https://www.rfc-editor.org/rfc/rfc8693) | [datatracker](https://datatracker.ietf.org/doc/rfc8693/) |
| Transaction Tokens | identity/authz | draft-ietf-oauth-transaction-tokens-11 | 2026-08-21 | draft (WG consensus, awaiting write-up) | IETF OAuth WG | [datatracker](https://datatracker.ietf.org/doc/draft-ietf-oauth-transaction-tokens/) | [history](https://datatracker.ietf.org/doc/draft-ietf-oauth-transaction-tokens/history/) |
| Identity and Authorization Chaining | identity/authz | draft-ietf-oauth-identity-chaining-17 | 2026-08-21 | draft (IESG approved, in RFC Editor queue) | IETF OAuth WG | [datatracker](https://datatracker.ietf.org/doc/draft-ietf-oauth-identity-chaining/) | [history](https://datatracker.ietf.org/doc/draft-ietf-oauth-identity-chaining/history/) |
| WIMSE Architecture | identity/authz | draft-ietf-wimse-arch-08 | 2026-07-06 | draft (WG document) | IETF WIMSE WG | [datatracker](https://datatracker.ietf.org/doc/draft-ietf-wimse-arch/) | [history](https://datatracker.ietf.org/doc/draft-ietf-wimse-arch/history/) |
| AI Identity Management System | identity/authz | draft-ietf-wimse-aims-00 | 2026-09-15 | draft (WG document, early) | IETF WIMSE WG | [datatracker](https://datatracker.ietf.org/doc/draft-ietf-wimse-aims/) | [history](https://datatracker.ietf.org/doc/draft-ietf-wimse-aims/history/) |
| OAuth On-Behalf-Of for AI Agents | identity/authz | draft-oauth-ai-agents-on-behalf-of-user-02 | 2026-02-27 | expired individual draft | none (individual submission) | [datatracker](https://datatracker.ietf.org/doc/draft-oauth-ai-agents-on-behalf-of-user/) | [history](https://datatracker.ietf.org/doc/draft-oauth-ai-agents-on-behalf-of-user/history/) |
| SPIFFE / SPIRE | identity/authz | SPIRE v1.15.4 (SPIFFE spec unversioned) | 2026-10-15 | stable (SPIRE CNCF Graduated) | CNCF | [overview](https://spiffe.io/docs/latest/spiffe-about/overview/) | [releases](https://github.com/spiffe/spire/releases) |
| Open Policy Agent | policy | v1.21.2 | 2026-10-12 | stable (CNCF Graduated) | CNCF | [docs](https://www.openpolicyagent.org/docs) | [releases](https://github.com/open-policy-agent/opa/releases) |
| OTel GenAI semantic conventions | observability | no tagged release (main branch of new repo) | moved out of core in v1.42.0 (2026-06-12) | experimental (Status: Development) | OpenTelemetry (CNCF) | [docs](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/README.md) | [commits](https://github.com/open-telemetry/semantic-conventions-genai/commits/main) |
| OTel semantic conventions (core) | observability | v1.44.0 | 2026-08-04 | mixed, per convention | OpenTelemetry (CNCF) | [docs](https://opentelemetry.io/docs/specs/semconv/) | [releases](https://github.com/open-telemetry/semantic-conventions/releases) |
| W3C Verifiable Credentials 2.0 | identity/authz | v2.0 | 2025-05-15 | stable (W3C Recommendation) | W3C | [TR](https://www.w3.org/TR/vc-data-model-2.0/) | [history](https://www.w3.org/standards/history/vc-data-model-2.0/) |
| W3C DIDs | identity/authz | v1.0 (Rec.); v1.1 (CR Snapshot) | 2022-07-19; 2026-03-05 | v1.0 stable; v1.1 draft | W3C | [DID 1.1](https://www.w3.org/TR/did-1.1/), [DID 1.0](https://www.w3.org/TR/did-core/) | [history](https://www.w3.org/standards/history/did-1.1/) |

## What each one means for agent movement

### Agent-to-agent, agent-to-tool, agent-to-user

- **A2A** is the standard interface for delegating a task to an independently hosted agent. It moves task requests, messages and artifacts. It does not move runtime checkpoints. v1.0.0 (tag 2026-03-12) was the first stable specification, according to the [AAIF announcement](https://aaif.io/blog/a2a-joins-aaif). v1.0.1 ([release](https://github.com/a2aproject/A2A/releases/tag/v1.0.1)) is a bug-fix release covering the HTTP binding media type, error transcoding and TaskStatus values. A2A became an AAIF hosted project on 2026-08-17. The [AAIF projects page](https://aaif.io/projects/) lists it next to MCP, goose, AGENTS.md, agentgateway and Agent Router.
- **MCP** 2026-07-28 is the revision marked "Current" on the [versioning page](https://modelcontextprotocol.io/specification/versioning). Its [changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog) removes protocol-level sessions and the `initialize` handshake, and adds a mandatory `server/discover` RPC. It also moves tasks from the core protocol into an official extension (`io.modelcontextprotocol/tasks`), adds the Multi Round-Trip Requests pattern, deprecates Roots, Sampling and Logging, and removes SSE stream resumability. For movement, this means less per-connection state has to follow a relocated client. Long-running work now depends on whether a server supports the tasks extension, and a broken stream loses the in-flight request, which must be re-issued. MCP is a founding AAIF project, announced 2025-12-09 ([LF press release](https://www.linuxfoundation.org/press/linux-foundation-announces-the-formation-of-the-agentic-ai-foundation)).
- **AG-UI** reached a 1.0 SDK line on npm (`@ag-ui/core` 1.0.0 on 2026-09-17, 1.0.2 on 2026-10-05; [registry](https://registry.npmjs.org/@ag-ui/core)). The monorepo publishes date-tagged releases, and `@ag-ui/a2a` 0.0.7 bridges AG-UI 1.0 to A2A. AG-UI keeps a move visible to the user and supports approvals. It does not move execution.
- **ACP (IBM / BeeAI)** has stopped development and been folded into A2A ([LF AI & Data, 2025-08-29](https://lfaidata.foundation/communityblog/2025/08/29/acp-joins-forces-with-a2a-under-the-linux-foundations-lf-ai-data/)). The repository was archived on 2025-08-27. Do not use it for new work. The acronym "ACP" also names the unrelated Agentic Commerce Protocol and Zed's Agent Client Protocol.
- **ANP** 1.2 is a decentralised alternative built on W3C DIDs (`did:wba` and `did:web`). It matters if agent identity must be portable without a central registry. The repository does not state a formal standards body.
- **AGNTCY OASF** v1.1.0 is a schema for describing agent capabilities and metadata. It could serve as input to compatibility negotiation before a handoff. Released schema versions are declared immutable.

### Commerce and authority-carrying extensions

- **AP2** v0.2.0 chains signed checkout and payment mandates, built on verifiable digital credentials. It is a concrete example of user authority for a side-effecting action travelling with a delegated task. The [AP2 site](https://ap2-protocol.org/) states that the protocol was donated to the FIDO Alliance, but the donation date is **unverified**.
- **Agentic Commerce Protocol** (OpenAI and Stripe) is in beta. It publishes dated spec snapshots, the latest being 2026-04-17. It is a vendor-maintained interop spec for one class of side-effecting action, checkout. It is relevant to idempotency and authority, not to general movement.
- **AGENTS.md** is an unversioned format for repository-level instructions to coding agents. It is tracked only because it is an AAIF project. It moves guidance, not state or authority.

### Durability and deployment

- **LangGraph** checkpoints let a graph resume on another worker that runs compatible LangGraph code and the same saver backend. They are not a cross-framework format. The persistence docs do not state whether checkpoints remain compatible across library versions, so pin versions in any experiment.
- **Temporal** lets a workflow continue on any worker polling the same task queue. This depends on deterministic workflow code and idempotent activities. SDK and server versions should be pinned together for replay tests.
- **OCI** (image, runtime and distribution specs) make code and runtime portable. They carry no live agent state. Process checkpoint and restore is outside these specs.
- **Kubernetes** reschedules pods and Jobs after a failure. That is a restart, not a migration, so application-level checkpointing is still required.

### Identity, authorisation, policy and observability

- **RFC 8693** (Proposed Standard, not updated or obsoleted according to datatracker) is the base pattern for exchanging a token for a narrower, audience-bound token that carries actor (`act`) claims.
- **Identity and Authorization Chaining** has been approved by the IESG and is in the RFC Editor queue, but it is **not yet an RFC**. It is the closest IETF pattern for a cross-organisation handoff. **Transaction Tokens** has WG consensus and is awaiting write-up. It propagates user and request context through internal workload chains.
- **WIMSE** drafts are all WG documents and none is an RFC. They comprise `-arch-08`, `-workload-creds-02`, `-wpt-02`, `-http-signature-07`, and `-aims-00`. The AIMS draft is the first WG-adopted IETF draft specifically on AI-agent identity, and it replaces the individual draft `draft-klrc-aiagent-auth`. Expect substantial change.
- **draft-oauth-ai-agents-on-behalf-of-user** is an expired individual draft. Cite it only as a proposal.
- **SPIFFE / SPIRE** issues short-lived identities to the workload that is actually running. Identity is therefore re-attested at the destination rather than copied.
- **OPA** can gate whether a handoff, tool call or destination is allowed.
- **OpenTelemetry GenAI conventions** define agent, model, tool and MCP span attributes. They are still **Development** status and were moved out of the core semantic conventions in v1.42.0 ([release notes](https://github.com/open-telemetry/semantic-conventions/releases/tag/v1.42.0)). Attribute names may still change.
- **W3C VC 2.0** (Recommendation) and **DIDs** (1.0 Recommendation, 1.1 Candidate Recommendation) supply signed claims and provider-independent identifiers. AP2 and ANP each build on one of them.

## How to refresh

Run these checks, update both the CSV and this page, and set the access date. GitHub's unauthenticated API allows 60 requests per hour. Use `gh api` or a token for a full refresh.

1. **GitHub releases** (A2A, MCP, AG-UI, ANP, OASF, AP2, LangGraph, Temporal, OCI, Kubernetes, SPIRE, OPA, OTel):
   `gh api repos/<owner>/<repo>/releases?per_page=5 --jq '.[] | "\(.tag_name) \(.published_at) pre=\(.prerelease)"'`.
   Do not rely on list order. Some repos, such as Temporal and Kubernetes, publish patches for several lines, so take the release marked "latest" (`/releases/latest`) and also record prereleases separately.
2. **MCP:** read the "current" revision on <https://modelcontextprotocol.io/specification/versioning> and the matching `/changelog`.
3. **A2A:** compare the "Latest Released Version" on <https://a2a-protocol.org/latest/specification/> with the GitHub release tags.
4. **IETF drafts:** `curl -s "https://datatracker.ietf.org/api/v1/doc/document/<draft-name>/?format=json"` returns `rev`, `time` and `states`. Resolve each state with `/api/v1/doc/state/<id>/`. Check for replacements with `/api/v1/doc/relateddocument/?target__name=<draft-name>&relationship=replaces`. When a draft becomes an RFC, replace the row with the RFC number.
5. **Python packages:** `https://pypi.org/pypi/<package>/json` (`langgraph`, `langgraph-checkpoint`, `temporalio`).
6. **npm packages:** `https://registry.npmjs.org/@ag-ui/core` (`dist-tags.latest` and `time`).
7. **W3C:** the status line at the top of each `https://www.w3.org/TR/<shortname>/` page.
8. **Kubernetes:** <https://kubernetes.io/releases/> for supported minors and EOL dates.
9. **Governance:** <https://aaif.io/projects/> for AAIF membership, and CNCF project pages for maturity.
10. Record any new conflict under "Discrepancies" instead of silently overwriting.

## Discrepancies with other repo docs

Checked against `README.md`, `docs/research-landscape.md` and `docs/sources.md`, all reviewed 2026-10-15.

1. **MCP 2026-07-28: confirmed.** It is the "Current" revision. None of the three docs mention that this revision removed sessions and the `initialize` handshake, moved tasks to an extension, or deprecated Roots, Sampling and Logging. Each of these affects movement design.
2. **A2A v1.0.0: confirmed, but out of date at patch level.** v1.0.0 is the first stable spec and the version the spec site labels as latest released. A **v1.0.1** bug-fix tag exists (2026-05-28). The docs also do not record governance: A2A moved from a Linux Foundation project (June 2025) to an **AAIF hosted project on 2026-08-17**.
3. **OpenTelemetry GenAI link is stale.** README, research-landscape and sources (and `docs/security-and-trust.md`) link `https://opentelemetry.io/docs/specs/semconv/gen-ai/`. That page now only states that the conventions moved to `open-telemetry/semantic-conventions-genai`. The conventions are **Development** status and have no tagged release. `docs/agent-forensics-and-fingerprints.md` already uses the new repository.
4. **AG-UI version not recorded.** The docs link only the GitHub repository. AG-UI reached a 1.0 SDK line on 2026-09-17.
5. **IBM ACP and ANP absent.** research-landscape does not mention that IBM ACP was merged into A2A and archived, or that ANP exists as a DID-based alternative. This is an omission, not a contradiction.
6. **LangGraph and Temporal unversioned.** sources.md asks readers to "verify specific upstream release dates". The versions above fill that gap. Neither upstream docs page states cross-version checkpoint or replay compatibility.
7. **Kubernetes upstream inconsistency (not a repo error).** kubernetes.io/releases dates 1.37.1 to 2026-09-15, but the GitHub release object was published 2026-09-23. The table uses the kubernetes.io date and notes both.
8. **Review date.** The other docs say "reviewed 2026-10-15". This tracker was accessed on 2026-10-16. No version claimed in those docs changed between the two dates.
