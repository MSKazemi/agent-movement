# Security, privacy, and trust (research threat model)

**Status:** Design recommendations, not a security certification.

## Trust boundaries

User <-> origin agent <-> destination discovery <-> remote agent <-> tools/artifacts <-> telemetry storage. Each boundary has independent identity, policy, data and availability risks. A2A/MCP messages are not automatically trusted because they use a protocol.

## Major threats

| Threat | Abuse example | Initial controls |
|---|---|---|
| Impersonation / fake Agent Card | Attacker advertises a trusted specialist | Authenticated allowlist; TLS and identity verification; validate advertised metadata |
| Privilege escalation | Recipient uses origin's admin token | Short-lived, audience-bound delegated grants; no raw credential copying |
| Prompt / tool-output injection | Retrieved webpage directs agent to exfiltrate files | Treat external text as data; approval and allowlisted actions |
| Data exfiltration | Private transcript included in handoff | Default-deny data classifications, redaction, explicit sharing scopes |
| Replay / duplicate side effect | Retried task double-purchases | Operation IDs, idempotency where tools support it, reconcile uncertain status |
| Tampering | Artifact/checkpoint altered in transit | Authenticated transport, immutable digests, signed metadata where required |
| Malicious destination | Agent obeys tasks but retains data | Contracted trust, retention limits, isolation; use synthetic test data |
| Excessive autonomy | Agent launches unlimited workers/tools | Budget ceilings, policy gates, cancellation, rate limits |
| Trace leakage | Sensitive prompts stored in observability backend | Minimal event fields, redaction and retention policies |
| Non-reproducible resume | Tool/memory changes corrupt behavior | Version pins, capability checks, fail closed on incompatible state |

## Non-negotiable prototype rules

- Use synthetic/public fixtures only, no production secrets or private chat transcripts.
- Do not serialize provider-private chain of thought or pretend it is portable.
- Never export raw OAuth access tokens, API keys or browser cookies inside an envelope.
- Do not allow arbitrary destination URLs to pull internal metadata endpoints (SSRF).
- Human approval for any irreversible external tool action; initial demo should simulate such actions instead.
- Differentiate **request received**, **accepted**, **executing**, **completed**, **failed**, **canceled** and **unknown**.
- Treat "exactly once" as unproven absent end-to-end guarantees.
- Adopt threat modeling and tests before enabling remote execution in untrusted domains.

## Recommended assurance tests

Unauthenticated A2A endpoint; forged Agent Card; expired and wrong-audience delegation; revoked grant; replayed task ID; tool output injection; mismatched artifact digest; destination crash at each lifecycle transition; network partition; state-version incompatibility; trace redaction.

## Normative sources

A2A: https://a2a-protocol.org/v1.0.0/specification/
MCP: https://modelcontextprotocol.io/specification/2026-07-28
OAuth token exchange: https://www.rfc-editor.org/rfc/rfc8693
SPIFFE: https://spiffe.io/docs/latest/spire-about/spire-concepts/
OPA: https://www.openpolicyagent.org/docs
OpenTelemetry: https://opentelemetry.io/docs/specs/semconv/gen-ai/
