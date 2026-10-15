# Can agents move between devices unnoticed and cause harm?

**Research and defensive threat model | reviewed 2026-10-15 | status: not implemented or experimentally validated here.**

## Executive answer

**Yes, in limited but important senses.** An agent with pre-authorized credentials, network and execution capabilities may call a service, delegate tasks, schedule another worker, or start a new instance without requesting a fresh human decision for every operation. Humans may notice later through policy/audit alerts, or never notice if the infrastructure does not log or report such actions.

A compromised or malicious agent can misuse overly broad privileges and vulnerable integrations to act outside the owner's intent. This is **not** evidence that an LLM has a general capability to infect arbitrary computers: unauthorized cross-device execution ordinarily depends on a previously accessible control plane or account, compromised authorization, a software vulnerability, or an insecure configuration. Also, sending an MCP tool call to another device is *remote tool use*, not agent migration.

**Separate three different questions:**

1. **No real-time human confirmation:** often possible by design in approved unattended automation.
2. **No authorization from the device/system owner:** should be blocked; if it occurs it is an incident, not normal agent movement.
3. **No forensic evidence anywhere:** not a property of any protocol and cannot generally be guaranteed or disproved from one system's logs alone.

The security goal for this repository is **observable, bounded, revocable mobility**, never covert proliferation, uncontrolled agent self-copying, or unapproved device access.

## A precise taxonomy of unnoticed activity

| Situation | What really happens | Human awareness | Necessary conditions | Classification |
| --- | --- | --- | --- | --- |
| Background delegated task | Origin invokes a known agent endpoint with bounded authority | No per-task prompt if authorized in policy; audit should record it | Reachable approved destination and valid grant | Legitimate, unattended **delegation** |
| Remote tool action | Agent invokes an exposed tool controlling a remote service | May have no visible foreground UI | Granted API/tool permission | **Remote action**, not migration |
| Scheduled cloud worker | Orchestrator starts another instance from an approved image | Human may see only later report | Deployment rights, allowed image and budget | **Replication / scaling** |
| Application checkpoint restore | Compatible task state resumes on a different worker | Not necessarily a new human confirmation | Valid checkpoint, compatible runtime, fenced original | **Relocation**, if verified |
| Misconfigured broad authorization | Agent performs an unintended action using an overly powerful allowed token | Owner may not be alerted | Existing broad privilege and weak policy | **Control failure / misuse** |
| Compromised credential or control plane | An attacker-controlled program accesses a second system | Potentially no immediate notice | Credential compromise, vulnerable service or malicious administration | **Unauthorized lateral movement** |
| Poisoned prompt, tool result or memory | Untrusted content redirects agent's behavior toward harmful tool use | May appear to be normal workflow | Model follows malicious instruction and tool policy fails | **Goal hijack / prompt injection** |
| Forged/hostile agent endpoint | A peer impersonates a useful destination and receives work | Owner may not notice | Bad discovery verification / excessive trust | **Inter-agent impersonation** |

**Important:** An agent may cause harm on a *remote account* through an API without installing any software on that account's servers. Conversely, copying a container image creates a new instance but does not automatically preserve identity, context, memory, or permission. "Silent agent movement" must not be used as one undifferentiated technical claim.

## What could go wrong?

| Misbehavior | Consequences | Defensive boundary |
| --- | --- | --- |
| Private data transmitted to an unapproved endpoint | Disclosure, regulatory and contractual exposure | Classification-based sharing control and destination allowlist |
| File deletion/configuration changes through a privileged tool | Irrecoverable data loss, outages | Least-privilege tools, snapshots, reversible staging, mandatory approvals |
| Unauthorized financial, messaging or publication actions | Monetary harm, spam, reputational damage | Independent service-side approval, per-action budgets and allowlists |
| Unauthorized agent spawn or software copy | Uncontrolled workers, costs and new attack surface | Deployment signature verification and creation quotas, owner enrollment |
| Hidden downstream delegation | Origin loses visibility over who actually executed task | Depth-limited delegation and mandatory lineage receipts |
| Cross-tenant/cross-device credential abuse | Expanded access and persistence | Audience-bound per-run identity, rotation, segmentation |
| Malicious device/robot commands | Physical risk | Local safety controller and interlocks; no direct general-agent actuator authority |
| Task replay and duplicate side effects | Double operations after timeout/retry | Idempotency, durable records, exclusive leases and reconciliation |
| Forged compliance report | Human trusts an unverified completion claim | Independent tool/system evidence; never trust agent's own text as proof |

These are risk classes, **not proof of any specific incident** and not evidence that this repository contains a working harmful agent.

## Preconditions and limits

A model cannot make new operating-system rights, network access, cloud roles or device credentials appear merely by asking for them. An agent application can, however, be provisioned with code execution, tool wrappers, cloud/deployment APIs, long-lived credentials, approved remote peers or unsafe host permissions. The **permissions, software controls and network topology** decide what can happen. A2A and MCP are communication interfaces; they do not authorize or guarantee arbitrary device takeover. QUIC connection migration is a network feature, not an AI-agent relocating to another host.

Even when a device is reachable, its OS, owner enrollment, software signing, sandbox, firewall and workload policies may block deployment or access. On an unrelated untrusted network, remote compromise requires an independent security failure; this project neither implements nor endorses such behavior.

## Defensive attack-chain model (conceptual; no exploit procedures)

~~~mermaid
flowchart LR
    I[Untrusted instruction or compromised agent] --> A[Agent has reachable tools or credentials]
    A --> B{Independent policy enforcement?}
    B -->|Allowlisted and scoped| O[Authorized recorded action]
    B -->|Missing or bypassed| U[Unauthorized tool, task or deployment]
    U --> D[Remote service or destination]
    D --> E[Harmful effect or unknown outcome]
    O --> L[Signed/independent audit evidence]
    E --> L
    L --> R[Detection, response and forensic review]
~~~

The attacker might exploit a compromised endpoint, overbroad token, untrusted memory/tool input or forged agent identity. The same technical traffic may resemble legitimate automation, so classifiers must corroborate **identity, owner authority, intent, scope and independent evidence** rather than flagging every remote call as malicious.

## What evidence can reveal unnoticed movement?

**Collect minimum necessary metadata across independently controlled places:**

| Evidence source | Useful fields | What it establishes | Blind spots |
| --- | --- | --- | --- |
| Origin coordinator | Movement ID, origin, intended destination, requested operation, approval ref, time | What was *requested* | Compromised origin can omit/falsify logs |
| Destination service | Verified client/workload identity, acceptance, execution ID | What that service *observed* | Malicious or external destination might not cooperate |
| Network egress / DNS / proxy | Approved domain/service identity, bytes, traffic timing | Connection/use of an endpoint | Encryption and shared networks obscure task semantics |
| IAM / OAuth / token issuer | Token exchange, audience, scope, changes and revocations | Grant provenance and suspicious privilege changes | Token use may not always create issuer event |
| Kubernetes/cloud audit | New job/pod/instance, image digest, deployment principal | Which workloads were created | Does not prove what model decided |
| MCP tool / API gateway | Tool name, requested class of action, approval and result | What tool access occurred | A self-reported success can be wrong |
| Target of side effect | Transaction/action record or device log | Whether an effect actually happened | Incomplete logs or no independent target access |
| Artifact store | Object hash, size, destination ACL and download record | Possible state/data transfer | Does not reveal semantics of encrypted content |

Never treat an IP address, model-writing style, container hash or unverifiable agent self-description as conclusive identity. The related [forensics guide](agent-forensics-and-fingerprints.md) separates verified identities, execution lineage and evidence strength.

### Alert triggers to consider (proposal)

- Any new destination, domain, machine, service account or peer outside the per-task explicit allowlist.
- A new worker, replica, scheduled task or tool endpoint **not linked** to an approved movement or deployment ID.
- Tool usage beyond declared task scope, especially file deletion, permission changes, publishing, finance and device actuation.
- Unexpected OAuth scope expansion, role/permission change, token exchange or failure to revoke grants.
- High-sensitivity artifact sent to a lower-trust destination or residency-incompatible region.
- Sudden fan-out of child agents, unusual delegation depth, rate/cost spike, or unexpected new code/package.
- Destination execution reported without an approved origin/recipient pair or inconsistent signed dispatch/accept receipts.
- Missing telemetry, disabled logging, audit gaps, unusual network egress or conflicting outcome reports.
- Failed fencing and concurrent executors for the same logical task; treat ownership as unknown and stop further effects.

Alerts are **signals for investigation**, not proof of malice. Compare with independent IAM, destination and tool-side records; respect privacy, data minimization and retention.

## Prevention: minimum architecture

1. **Default-deny registration and egress.** Agents can contact only explicitly enrolled, independently authenticated destinations and tools. Apply egress controls outside the agent process; DNS names and Agent Cards are not sufficient authorization.
2. **Short-lived, narrow grants.** New agent instances get new workload identities, audience/resource/action-bound grants and expiration. Never inherit the origin's admin keys, cookies or token cache.
3. **Non-delegable authority by default.** A delegated agent cannot create further agents, delegate onward, widen scopes, install code or send protected artifacts unless explicitly allowed.
4. **Maximum depth, fan-out and resource ceilings.** Enforce quotas in a trusted scheduler/tool gateway, not only in prompts.
5. **Risk-based human control.** Low-risk read-only, authorized automation may run without repeated prompts, but new destinations and irreversible, high-impact actions require independent owner-approved policy or human approval. An LLM must not approve its own privilege increase.
6. **Signed software and constrained execution.** Pin versioned workloads; verify digest/signature; sandbox processes and prohibit unmanaged software installation.
7. **Audit each hop with reciprocal receipts.** Record authorized origin → verified destination → execution → tool/action result, with trace and policy decision IDs. Compare destination and independent target evidence; keep redacted append-only records.
8. **Stop/revoke across every hop.** Kill switch disables new dispatches, revokes grants, stops enrolled workers, fences outstanding task leases and halts risky tools at the gateway. Network egress denial is a separate backstop. Do not claim that revocation undoes completed external actions.
9. **Isolation across trust domains.** Separate tenants, production/admin accounts, devices and robot safety systems. For industrial/robot interfaces start read-only or simulation-only.
10. **Regular fault-injection and incident drills.** Verify denied policy paths, offline destinations, tampered artifacts, compromised credentials, queue replay, audit outages and restoration.

### Proposed policy defaults (illustrative YAML, not implemented)

~~~yaml
policy_version: draft-0.1
agent_egress:
  default: deny
  approved_destinations: []  # explicitly enrolled before use
movement:
  allowed: [remote_tool_read, delegate_read_only]
  copy_to_new_host: deny
  checkpoint_relocation: deny
  auto_delegate_to_new_peers: deny
  maximum_hops: 1
  maximum_children: 1
  require_verified_destination_identity: true
  require_origin_and_receiver_audit: true
authorization:
  default_grant_ttl_seconds: 300
  raw_credential_export: deny
  privilege_escalation: deny
tool_actions:
  destructive_or_high_impact: require_independent_approval
  device_actuation: deny
  unaudited_tool: deny
response:
  revoke_delegated_grants: enabled
  block_new_dispatch: enabled
  fence_active_tasks: enabled
  log_policy_denials: enabled
~~~

This config is a requirements illustration: **there is no policy engine or enforcement code for it in this repository**. A fail-closed enforcement point has to be outside the model's control, and system owners must verify that all real network and deployment routes are covered.

## Detection versus prevention: five common misconceptions

1. **"We turned on logs, so hidden movement is impossible."** Wrong: logs detect only observed and retained events; a compromised source or outside destination may suppress them.
2. **"The agent is behind a VPN, therefore it is safe."** Wrong: reachability or encrypted transport is not tool-level authorization.
3. **"An A2A Agent Card says it is trusted, so it is trusted."** Wrong: verify origin and access policy; signed metadata can help integrity, not make a provider benign.
4. **"MCP allows tools, so the agent owns the device."** Wrong: a tool call exercises only the rights exposed by the tool server; careless tool privileges can still cause major harm.
5. **"Closing the origin stops all copies and side effects."** Wrong: independent workers, queued commands and completed operations require revocation, cancellation, reconciliation and potentially incident response.

## Research plan for this repository

Start with **two sandboxed mock agents and one fake tool** on enrolled test containers. Use public/synthetic data, read-only permissions and simulated harmful operations that never touch real devices/accounts. No probing, infection, credential theft or unattended installation on third-party hosts.

**Suggested independent experiments:**

- E01: background delegation with approved scope generates correct origin, destination and central audit events even without a per-task popup.
- E02: destination not enrolled → independent policy denies before task/context transmission.
- E03: attempted onward delegation outside maximum hop/fan-out → deny and alert.
- E04: unauthorized new container/worker creation through mock scheduler → deny and alert.
- E05: simulated overbroad token → least-privilege gateway rejects access beyond task scope.
- E06: instruction injection in public fixture requests an unapproved tool → policy denies even when model proposes it.
- E07: forged agent identity / metadata → destination verification rejects it.
- E08: fabricated artifact or handoff receipt → verification rejects altered records.
- E09: tool activity without corresponding movement lineage → high-priority investigation alert.
- E10: simulated high-impact action → requires independent approval; no self-authorization.
- E11: kill switch during queued and running tasks → block new dispatch, revoke grants and fence outstanding tasks; report unresolved outcomes.
- E12: duplicated dispatch / partition → at most one authorized logical executor if fencing succeeds; UNKNOWN otherwise.
- E13: source log intentionally missing in test → cross-check with independent destination/gateway logs.
- E14: simulated excessive child creation and egress spike → independent limits activate.
- E15: one authorized agent sends harmless work to another without UI prompt → not automatically misclassified as malicious.

For each trial, publish an event timeline, permitted/blocked decision, independent evidence source, false positives, audit gap visibility, measured detection delay and limitations. See also [agent tracking research](agent-forensics-and-fingerprints.md), [baseline threat model](security-and-trust.md), and [architecture roadmap](roadmap.md).

## Important open scientific questions

- What minimum cryptographic and operational evidence proves that a **particular instance** delegated/relocated a task, rather than merely communicated?
- Can independent network- and policy-level enforcement remain effective when an agent is deceptive or compromised?
- How do we audit child agents across multiple organizations without collecting sensitive task content or violating privacy?
- Can an interoperable grant represent **non-delegable authority**, maximum descendant depth, risk budget and unambiguous revocation?
- How should a coordinator classify **unknown** outcomes after crash or long network partition when side effects cannot be queried?
- What is the lowest false-positive rate for alerts detecting anomalous movement in busy multi-agent systems?
- What evidence is needed to distinguish benign unattended orchestration from unauthorized replication or lateral movement?
- How can a kill switch contain already-deployed independent executors, and what limitations are unavoidable outside controlled trust domains?

## Verified starting references (research, not endorsements)

- [OWASP Top 10 for Agentic Applications](https://genai.owasp.org/2025/12/09/owasp-top-10-for-agentic-applications-the-benchmark-for-agentic-security-in-the-age-of-autonomous-ai/) — ASI01 goal hijack, ASI02 tool misuse, ASI03 identity abuse, ASI04 supply-chain, ASI05 unexpected execution, ASI07 inter-agent communication, ASI10 rogue agents.
- [OWASP Agentic AI Threats and Mitigations](https://genai.owasp.org/resource/agentic-ai-threats-and-mitigations/) — security threats and controls taxonomy.
- [MITRE ATT&CK: Cloud Services (T1021.007)](https://attack.mitre.org/techniques/T1021/007/) — adversary movement through valid cloud accounts/API credentials, with mitigations and detection strategies.
- [MITRE ATT&CK: SSH (T1021.004)](https://attack.mitre.org/techniques/T1021/004/) — remote-service lateral-movement taxonomy; not agent-specific.
- [A2A v1.0.1 specification](https://a2a-protocol.org/v1.0.1/specification/) — agent messaging, discovery, task and security metadata; does not confer trust automatically.
- [A2A enterprise-ready security guidance](https://a2a-protocol.org/v1.0.1/topics/enterprise-ready/) — TLS, authentication and authorization.
- [MCP spec 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28) and [maintainers' release notes](https://blog.modelcontextprotocol.io/posts/2026-07-28/) — tool connection and authorization changes; not universal agent migration.
- [RFC 8693 OAuth Token Exchange](https://www.rfc-editor.org/rfc/rfc8693), [SPIFFE concepts](https://spiffe.io/docs/latest/spire-about/spire-concepts/), [OpenTelemetry GenAI conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/).

**Evidence discipline:** OWASP describes classes of observed and emerging vulnerabilities; MITRE describes real adversary techniques. Neither proves that every AI agent can spread autonomously. A controlled test is required before the repo can claim detection efficacy, revocation completeness or a functioning movement implementation.

**Bottom line:** The important research target is **how to detect, attribute, authorize, contain and revoke cross-device agent activity even when humans are not watching**, rather than how to make agents invisible.
