# Technology landscape (reviewed 2026-10-15)

## Taxonomy: six operations in the agent-movement research scope

Of these rows, only checkpoint relocation and strong migration are *moves* in the strict sense (ownership of the same task transfers). Delegation keeps the origin as the owner. Copy, replication and multiplication create additional executions and are never automatically a move ([movement vs copy](agent-movement-vs-copy-replication-multiplication.md)).

| Mode | Example | State transferred? | Key issue |
|---|---|---|---|
| Delegation | Planner asks specialist to analyze file | Task input only | Ownership and authority |
| Copy (clone if from a snapshot) | Start another instance from same agent package | Config; memory only for an approved snapshot clone | Divergence, duplicate effects |
| Replication | Keep N equivalent instances of one logical service for availability or throughput | Shared durable state, not blind memory copying | Unsafe failover, split brain |
| Multiplication / scaling | Launch N worker agents | Usually shared queue/context pointers | Coordination and cost |
| Checkpoint relocation | Persist safe checkpoint and resume on new worker | Portable workflow checkpoint | Compatibility and recovery |
| Strong migration | Move live process incl. stack/in-flight operations | Live execution state | Generally not available across unrelated AI frameworks |

A model's private internal state, chain-of-thought, temporary tool runtime, or browser session cannot be presumed exportable. Agent "memory" can mean stored messages, retrieved documents, summaries or application state; each needs distinct handling.

## Technology-by-technology

### A2A: agent-to-agent communication
Primary specification: https://a2a-protocol.org/v1.0.0/specification/

A2A provides an interface for interoperating with independently hosted agents through capabilities/discovery, structured messages, tasks, artifacts and updates. A2A is the leading candidate for **remote delegation**, not a general process-checkpoint standard. Authentication and trust policies still need to be enforced in deployment.

### MCP: model/agent-to-tool interoperability
Spec: https://modelcontextprotocol.io/specification/2026-07-28

MCP servers expose tools, resources and prompts to clients, allowing a moved/delegated agent to use eligible tools without custom integration for each tool. MCP does not provide a portable runtime checkpoint or automatic authority transfer. Treat remote tool output as untrusted.

### AG-UI: agent-to-frontend interaction
Code and docs: https://github.com/ag-ui-protocol/ag-ui

Useful for user-visible streaming, approvals, event/state synchronization and a live movement timeline; not a replacement for A2A.

### Durability: LangGraph and Temporal
LangGraph: https://docs.langchain.com/oss/python/langgraph/persistence
Temporal: https://docs.temporal.io/workflow-execution

LangGraph checkpoints support persistence and resumption within its execution model. Temporal offers durable workflows and retryable activities, subject to deterministic workflow and external side-effect discipline. Neither alone ensures byte-for-byte migration between different agent frameworks.

### Hosting: OCI + Kubernetes
OCI image specification: https://specs.opencontainers.org/image-spec/
Kubernetes Jobs: https://kubernetes.io/docs/concepts/workloads/controllers/job/

Packaging makes deployment portable, not agent state. Pods may be restarted or replaced; ephemeral runtime state and external resources require additional design. Use versioned containers and compatible checkpoint formats.

### Trust: identity, delegation and observability
OAuth 2.0 token exchange: https://www.rfc-editor.org/rfc/rfc8693
SPIFFE / SPIRE: https://spiffe.io/docs/latest/spire-about/spire-concepts/
OPA: https://www.openpolicyagent.org/docs
OpenTelemetry GenAI conventions: https://github.com/open-telemetry/semantic-conventions-genai

These are building blocks, not proof of end-to-end security. Verify token audiences, resource scopes, recipient identity, tool authorization and trace privacy separately.

## Research gaps / hypotheses

1. Portable minimal **task envelope** across vendors (goals, task/trace IDs, capability needs, safe artifact references, checkpoint pointer, provenance).
2. **Compatibility negotiation**: what is mandatory vs optional, what may be lost and when to refuse.
3. **Trust-preserving delegation** with short-lived delegated identity and explicit user approval.
4. **Replay-safe resumption** for external actions, including partially complete operations.
5. **Portable evaluation**: reproducible success, data leakage, duplicate side effects, latency and operational cost.

## What the project should not claim

Do not equate A2A with migration, MCP with authentication for all connected services, multiple replicas with a single migrating agent, or a serialized transcript with a correct execution checkpoint. Avoid promising exact-once behavior for arbitrary external tools.

## Procedural packaging and browser/computer-use interfaces (added 2026-10-16)

All sources in this section were accessed on 2026-10-16. Versions, dates and governance for the three that are open specifications (Agent Skills, WebMCP, WebDriver BiDi) and for AGENTS.md are also recorded in the [standards tracker](standards-tracker.md). CDP, Playwright MCP and the two vendor computer-use APIs are not standards, so they are compared here but not tracked there.

These interfaces fall into two groups. **Procedural packaging** (Agent Skills, AGENTS.md) moves instructions and, for skills, code to wherever an agent runs. **Browser and computer-use interfaces** (WebMCP, WebDriver BiDi, CDP, Playwright MCP, vendor computer-use tools) carry *UI actions* to a browser or desktop that stays where it is. None of them carries an execution checkpoint.

| Interface | What it moves | What it does **not** move | Version and governance (2026-10-16) | Relevance to agent movement (project interpretation) |
|---|---|---|---|---|
| **Agent Skills** | A skill folder: `SKILL.md` (YAML frontmatter + Markdown instructions) and optional `scripts/` ("executable code that agents can run"), `references/` and `assets/` [S1] | Execution state. The spec defines no credential or delegation mechanism. `allowed-tools` only lists tools "pre-approved to run", is marked experimental, and its "support … may vary between agent implementations" [S1] | No version number on the spec page. No tags or releases in [agentskills/agentskills](https://github.com/agentskills/agentskills) (Apache-2.0). The spec file last changed on 2026-08-04 (commit `217be54`). "Originally developed by Anthropic, released as an open standard" and open to contributions [S2]. It is not listed on the [AAIF projects page](https://aaif.io/projects/) | Portable *procedure*: the same capability can be installed at a destination. Runnability is not guaranteed there: the `compatibility` field states environment requirements, and supported script languages "depend on the agent implementation" [S1] |
| **AGENTS.md** | Free-form Markdown guidance for coding agents, such as build, test and style instructions. "The closest AGENTS.md to the edited file wins", and explicit user chat prompts override it [S3] | Code, state and authority. It has no required fields or schema [S3] | Unversioned. No tags or releases in [agentsmd/agents.md](https://github.com/agentsmd/agents.md) (MIT). Latest commit 2026-09-10. "Stewarded by the Agentic AI Foundation" under the Linux Foundation [S3] | Travels with the repository, so a coding task handed to another agent sees the same guidance. Whether the receiver applies it depends on that agent's support |
| **WebMCP** | A web page registers JavaScript tools (`name`, `description`, `inputSchema`, `execute`, optional `annotations` such as `readOnlyHint`) through `document.modelContext.registerTool()`. An agent invokes them, and they run in the page [S4] | The page, its tools and its session do not leave the browser. Authority is *inherited*: per the spec's own threat analysis, an agent "carries the user's logged-in credentials and session state" [S4] | Draft Community Group Report, 15 October 2026, Web Machine Learning Community Group. "Not a W3C Standard nor … on the W3C Standards Track" [S4]. The repository's implementation-status file lists an origin trial in Chrome 149 and in Edge 150 [S5]. Those trials were not checked against browser-vendor pages | Turns UI actions into named, typed tool calls. Because the tools are bound to a live page and the user's session, the agent must reach the browser that holds them. A moved agent cannot take them along |
| **WebDriver BiDi** | Bidirectional commands and events for "remote control of user agents" [S6]. Modules include `browsingContext` (navigation, screenshots), `script`, `input` (`input.performActions`), `network` and `storage` | Agent state of any kind. However, `storage.getCookies` and `storage.setCookie` let a controller read and write cookies, which can be session credentials [S6] | W3C Working Draft, 8 October 2026, Browser Testing and Tools Working Group [S6]. Not a Recommendation | The standards-track way to drive a browser remotely. Cookie access means a controller can copy a logged-in session, so it is an authority-transfer path that needs policy (see the security note) |
| **Chrome DevTools Protocol (CDP)** | JSON commands and events across domains such as DOM, Network and Debugger, for "trusted debug and automation clients" [S7] | Stability. CDP "is not a public or supported API for Chrome, and it does not guarantee backwards compatibility". Tip-of-tree "can break at any time"; "Stable 1.3" is "a historical snapshot tagged at Chrome 64" [S7] | Vendor protocol defined in Chromium. Not a standard. Google directs third-party automation to "Chrome DevTools for agents, Puppeteer, or ChromeDriver" instead of raw CDP [S7] | Agent tools built directly on CDP are tied to Chromium versions. Pin the browser version in any experiment that depends on it |
| **Playwright MCP** | Browser actions exposed as MCP tools. It works on "structured accessibility snapshots", not screenshots [S8] | The browser and its session stay on the host running the MCP server | v0.0.83 (2026-09-28), pre-1.0, Microsoft, Apache-2.0 [S8]. Its README suggests that coding agents may prefer the separate Playwright CLI "exposed as SKILLs" because it uses fewer tokens [S8] | Any MCP client can drive a browser through it. Delegating a task to it moves *requests for actions*, not the browser |
| **Anthropic computer use** | Screenshots in, mouse and keyboard actions out. The current toolset is `computer_toolset_20260801` and "needs no beta header". Earlier versions such as `computer_20251124` remain available in beta [S9] | The environment. "Claude doesn't directly connect to this environment"; the developer's application executes each action [S9] | Vendor API, not a standard | Each action runs where the application runs. Relocating the agent does not relocate the desktop, its files or its logins |
| **OpenAI computer use** | A `computer` tool that requests `click`, `double_click`, `drag`, `move`, `scroll`, `keypress`, `type`, `wait` or `screenshot`. A code-execution alternative uses libraries such as PyAutoGUI or Playwright [S10] | The environment. "You provide the environment and execute the model's requests" [S10] | Vendor API, not a standard. The guide has no preview, beta or GA label. The examples call `client.responses.create`. The Operator product was not reviewed | Same as above: the agent sends actions, and the environment that holds state and sessions stays put |

### Security note: skills carry code, browser controllers carry sessions

- **Agent Skills can bundle executable scripts** [S1]. Installing or moving a skill therefore installs code. Anthropic's documentation says to "use Skills only from trusted sources" and to treat a skill "like installing software". It warns that a malicious skill "can direct Claude to invoke tools or execute code in ways that don't match the Skill's stated purpose", and that skills fetching external URLs remain at risk if their dependencies change [S11]. The client-implementation guide notes that project-level skills "may be untrusted (e.g., a freshly cloned open-source project)". It suggests loading them only from folders the user has marked as trusted [S12]. *Project interpretation:* a task envelope that references a skill should pin it by content digest and record its provenance, as for any other artifact. `allowed-tools` pre-approval must not be honoured across a trust boundary without the receiver's own policy check. See [security-and-trust](security-and-trust.md).
- **AGENTS.md** adds no code, but its text enters the agent's context. *Project interpretation:* a planted or altered AGENTS.md is a case of indirect prompt injection through files ([glossary](glossary.md#prompt-injection-indirect-prompt-injection-tool-poisoning)).
- **Browser and computer-use interfaces** run with the privileges of the session they control. WebMCP's threat analysis lists prompt injection, misrepresentation of intent, privacy leakage through over-parameterization and same-origin violations [S4]. Both vendor guides recommend an isolated VM or browser, an allow-list of sites and human confirmation of consequential actions [S9][S10]. OpenAI's guide adds that on-screen text "cannot grant permission or override the user's instructions" [S10].

### Hypotheses for this repository (not established findings)

1. **H-PKG-1:** Agent Skills are a candidate unit for *partial deployment* ("P", [glossary](glossary.md#partial-deployment-p)): installing a narrowly scoped procedure at a destination without moving a task. A test would install the same skill on two different clients and compare outcomes.
2. **H-PKG-2:** In browser-based agents, authority is bound to *location*, because it sits in the user's browser session. Movement would then mean re-establishing a session at the destination under new consent, not copying cookies. A test would compare a relocated run that re-authenticates with one that copies cookies through `storage.setCookie`, measuring audit and revocation properties.
3. **H-PKG-3:** For coding agents, version pinning of AGENTS.md and skills (by commit or digest) is needed for a reproducible handoff, because neither format carries a version number.

### Sources for this section (accessed 2026-10-16)

- [S1] Agent Skills specification: https://agentskills.io/specification
- [S2] Agent Skills overview ("Open development"): https://agentskills.io/home; repository https://github.com/agentskills/agentskills
- [S3] AGENTS.md: https://agents.md/; repository https://github.com/agentsmd/agents.md
- [S4] WebMCP, Draft Community Group Report, 15 October 2026: https://webmachinelearning.github.io/webmcp/; source https://github.com/webmachinelearning/webmcp/blob/main/index.bs
- [S5] WebMCP implementation status: https://github.com/webmachinelearning/webmcp/blob/main/implementation-status.md
- [S6] WebDriver BiDi, W3C Working Draft, 8 October 2026: https://www.w3.org/TR/webdriver-bidi/
- [S7] Chrome DevTools Protocol, "Scope and support": https://chromedevtools.github.io/devtools-protocol/
- [S8] Playwright MCP README and release v0.0.83: https://github.com/microsoft/playwright-mcp; https://github.com/microsoft/playwright-mcp/releases
- [S9] Anthropic, computer use tool: https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool
- [S10] OpenAI, computer use guide: https://developers.openai.com/api/docs/guides/tools-computer-use
- [S11] Anthropic, Agent Skills overview, "Security considerations": https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview
- [S12] Agent Skills, "How to add skills support to your agent", "Trust considerations": https://agentskills.io/client-implementation/adding-skills-support

See [sources](sources.md), [security](security-and-trust.md), [questions](open-questions.md), and the [standards tracker](standards-tracker.md).
