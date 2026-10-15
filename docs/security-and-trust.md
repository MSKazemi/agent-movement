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

"Excessive autonomy" is this repository's own label. It is close to **Excessive Agency**, which is item **LLM06:2025** of the OWASP Top 10 for *LLM Applications* 2025 ([OWASP LLM06:2025](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/), accessed 2026-10-16). Excessive Agency is **not** an entry of the OWASP Top 10 for *Agentic Applications* 2026. In that list, the OWASP document says ASI02 Tool Misuse and Exploitation "builds on the mitigations of LLM06:2025 (Excessive Agency)", and ASI10 Rogue Agents is described as distinct from it. Keep the two lists apart: LLM Top 10 IDs read `LLMnn:2025` and Agentic Top 10 IDs read `ASInn`.

## OWASP Top 10 for Agentic Applications 2026: mapping

**Source.** OWASP GenAI Security Project, Agentic Security Initiative, *OWASP Top 10 for Agentic Applications 2026*, "Version 2026, December 2025", CC BY-SA 4.0. Resource page: <https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/>. PDF: <https://genai.owasp.org/download/52117/?tmstv=1765059207> (57 pages, SHA-256 `a2db94cd00b08e0b3a5e5b619afe024bdbcd74503111085705e4f3dd886fcb5c`). Both were accessed 2026-10-16.

**Names.** All ten names below are copied from the section headings of the official PDF, so none relies on a secondary source. The OWASP announcement post of 2025-12-09 (AMN-057, accessed 2026-10-16) shortens two of them, to "ASI02 – Tool Misuse" and "ASI05 – Unexpected Code Execution", and writes "Identity & Privilege Abuse" for ASI03. The PDF's own cross-mapping table also writes "&" in place of "and" for ASI02 and ASI03. This page uses the section headings.

**Scope of the mapping.** Each row names a threat to agent movement, the repository code that controls it, and the test that exercises that code. Every code and test reference was checked by `git grep` against the agent-movement code stack (`src/agent_movement/`, `tests/`) before it was merged to `main`. Tests are given as pytest node IDs. The relocation tests need the `[relocation]` extra, the A2A tests need the `[a2a]` extra and the receipt tests need the `[signing]` extra. Without the extra they are skipped. A control here means only what the test proves in a local, synthetic setting. It is not a production guarantee.

<!-- Code paths and test IDs verified against main at ba77c1c (2026-10-16). -->

| ASI ID and official name | Agent-movement threat | Repository control | Test that exercises it |
|---|---|---|---|
| **ASI01** Agent Goal Hijack | Delegated task text, an Agent Card or tool output carries instructions that redirect the receiving agent, or the goal is swapped between approval and delivery. | **Partial, by construction.** `src/agent_movement/core.py` `validate_envelope` accepts only two deterministic, LLM-free task kinds (`word_count`, `sha256`), so task text is processed as data and never read as instructions. `src/agent_movement/a2a_server.py` `decode_message` admits exactly one structured data part. `src/agent_movement/peer.py` `PeerReceiver._deliver` refuses a task that does not match the salted commitment admitted at preflight. | `tests/test_core.py::ContractTests::test_bad_contracts`; `tests/test_a2a_adapter.py::A2AAdapterTests::test_foreign_message_shapes_cannot_trigger_execution`; `tests/test_peer.py::PeerAuthTests::test_delivery_must_match_admitted_commitment` |
| **ASI02** Tool Misuse and Exploitation | The receiver uses delegated authority for an effect outside its grant, repeats an effect on retry, or a stale executor keeps acting after a move. | `src/agent_movement/peer.py` `AuthorizedEffectGateway.commit` re-checks grant liveness, audience and task inside the effect transaction and makes effects idempotent by payload digest. `src/agent_movement/core.py` `EffectGateway.commit` fences commits by owner epoch. `src/agent_movement/relocation.py` `EffectLedger.record_intent` accepts only the allowlisted `EFFECT_TOOLS` and records a write-ahead intent. | `tests/test_peer.py::PeerAuthTests::test_effect_gateway_scope_checks`; `tests/test_peer.py::PeerAuthTests::test_revocation_between_admission_and_effect_commit`; `tests/test_core.py::EffectGatewayTests::test_fences_stale_executor`; `tests/test_relocation.py::RelocationExperimentTests::test_never_more_than_one_gated_effect` |
| **ASI03** Identity and Privilege Abuse | A genuine peer reuses a grant issued to another agent, a grant is used for the wrong audience, task or capability, or the origin's credentials are copied into the handoff. | `src/agent_movement/trust.py` `verify_grant`, `check_grant_scope` and `check_grant_live`. `src/agent_movement/core.py` `Approval.allows`. `src/agent_movement/peer.py` `PeerClient._send_check` blocks held secrets before any request is sent. `src/agent_movement/receipts.py` `Ed25519Signer.seal` refuses to sign credential-like values. | `tests/test_peer.py::PeerAuthTests::test_insider_sender_with_stolen_grant`; `tests/test_peer.py::PeerAuthTests::test_wrong_audience`; `tests/test_peer.py::PeerAuthTests::test_capability_not_granted`; `tests/test_peer.py::PeerAuthTests::test_sender_guard_blocks_held_credential_before_any_post`; `tests/test_core.py::ReceiverTests::test_wrong_approvals_denied_before_execution`; `tests/test_movement_receipts.py::AdversarialTests::test_signer_refuses_credential_like_values` |
| **ASI04** Agentic Supply Chain Vulnerabilities | A discovered destination agent or its Agent Card is malicious, or the runtime that resumes a checkpoint differs from the one that wrote it. | `src/agent_movement/trust.py` `verify_card` checks cards against a pinned `TrustStore`. `src/agent_movement/peer.py` `PeerClient.discover` requires the identity, endpoint, schema and capability to match. `src/agent_movement/a2a_client.py` `check_card` does the same for A2A cards. `src/agent_movement/relocation.py` `compatibility` refuses any deviation from `PINNED_RUNTIME`. | `tests/test_peer.py::PeerAuthTests::test_fake_receiver_card_from_untrusted_ca`; `tests/test_peer.py::PeerAuthTests::test_fake_receiver_card_from_unknown_ca_kid`; `tests/test_a2a_adapter.py::A2AAdapterTests::test_client_refuses_foreign_agent_card`; `tests/test_relocation.py::RelocationExperimentTests::test_version_mismatch_fails_closed_and_reports_state` |
| **ASI05** Unexpected Code Execution (RCE) | A handoff smuggles a `shell` or tool task kind, or a malformed body that the receiver could turn into executable behaviour. | **Partial, by construction.** No task kind executes code (`src/agent_movement/core.py` `validate_envelope`). `src/agent_movement/core.py` `parse_json` rejects duplicate keys, NaN, oversized bodies and deep nesting. `src/agent_movement/a2a_profile.py` `a2a_to_envelope` rejects unknown kinds and extra fields. | `tests/test_core.py::ContractTests::test_bad_contracts`; `tests/test_core.py::ContractTests::test_duplicate_json_field_and_invalid_numbers`; `tests/test_review_regressions.py::MalformedInputIsContractError::test_deep_nesting`; `tests/test_a2a_profile.py::ProfileMappingTests::test_receiver_side_rejections` |
| **ASI06** Memory & Context Poisoning | A relocated checkpoint is corrupted, a stale executor writes into the shared checkpoint store, or provider-private session state is smuggled across the handoff. | `src/agent_movement/relocation.py` `Worker.accept` fails closed when the checkpoint digest does not match the manifest. `src/agent_movement/relocation.py` `FencedSqliteSaver` commits writes only for the current owner epoch. `src/agent_movement/a2a_profile.py` `envelope_to_a2a` never maps provider-private state. | `tests/test_relocation.py::RelocationExperimentTests::test_version_mismatch_fails_closed_and_reports_state` (row V4 is the digest mismatch); `tests/test_relocation.py::RelocationUnitTests::test_fenced_saver_rejects_stale_and_read_only_writes`; `tests/test_a2a_profile.py::ProfileMappingTests::test_provider_private_state_is_never_mapped` |
| **ASI07** Insecure Inter-Agent Communication | Handoff messages between origin and destination are spoofed, tampered with, replayed or sent to the wrong destination. | `src/agent_movement/peer.py` `PeerReceiver._preflight` and `PeerReceiver._deliver` require a CA-endorsed card and a signature on every message, check nonces and clock skew, and bind the destination. `src/agent_movement/trust.py` `seal` / `unseal`. `src/agent_movement/receipts.py` `verify_bundle` and `ReplayGuard`. | `tests/test_peer.py::PeerAuthTests::test_tampered_preflight_rejected`; `tests/test_peer.py::PeerAuthTests::test_replayed_and_stale_preflight`; `tests/test_peer.py::PeerAuthTests::test_delivery_signed_by_other_peer_rejected`; `tests/test_peer.py::PeerAuthTests::test_wrong_destination_binding_in_preflight`; `tests/test_movement_receipts.py::AdversarialTests::test_every_leaf_mutation_is_rejected`; `tests/test_movement_receipts.py::AdversarialTests::test_replay_guard` |
| **ASI08** Cascading Failures | A crash, duplicate delivery or effect of uncertain outcome during a move is retried blindly and multiplies effects across executions. | `src/agent_movement/core.py` `SQLiteStore.receive` is idempotent, with one execution per movement. `src/agent_movement/relocation.py` `Coordinator.transfer` and `EffectLedger` park an uncertain effect as `unknown` for reconciliation instead of retrying it. | `tests/test_core.py::ReceiverTests::test_concurrent_deliveries_one_execution`; `tests/test_relocation.py::RelocationExperimentTests::test_crash_and_duplicate_for_every_transition`; `tests/test_relocation.py::RelocationExperimentTests::test_uncertain_opaque_effect_is_parked_not_retried` |
| **ASI09** Human-Agent Trust Exploitation | A human approves a movement, or accepts an agent's account of where work ran, without independent evidence. | **Not addressed.** Indirect support only: `src/agent_movement/receipts.py` `verify_bundle` reports missing or unverifiable claims as unknown rather than trusting the agent's account. | None for the human-facing risk. Indirect only: `tests/test_movement_receipts.py::FixtureSetTests::test_gap_and_unknowns_are_reported_not_filled`; `tests/test_movement_receipts.py::WithoutSignatureSupportTests::test_unchecked_is_reported_not_trusted` |
| **ASI10** Rogue Agents | An agent keeps acting after its authority is revoked or its task has moved, or forks into undeclared executions. | `src/agent_movement/peer.py` `PeerLedger.revoke` records signed revocations, serialized with effect commits. `src/agent_movement/relocation.py` `_fence` and `FencedSqliteSaver` deny a superseded execution. `src/agent_movement/receipts.py` `verify_bundle` surfaces fork lineage and conflicting accounts. | `tests/test_peer.py::PeerAuthTests::test_revoked_grant_via_signed_notice`; `tests/test_peer.py::PeerAuthTests::test_concurrent_revocation_race_is_linearized`; `tests/test_relocation.py::RelocationExperimentTests::test_worker_a_is_fenced_after_transfer`; `tests/test_movement_receipts.py::FixtureSetTests::test_fork_keeps_executions_with_same_definition_distinct` |

### Gaps (future work)

These gaps are open. None of the controls above closes them.

- **ASI01, ASI05:** the protection comes from having no LLM in the receiver. It ends as soon as an agent interprets task text. The repository has no prompt-injection defence and no sandbox for generated or downloaded code.
- **ASI02:** every effect is simulated in SQLite and no real tool is called. There are no budget ceilings, rate limits or caps on spawned workers. The "Excessive autonomy" controls in the threat table are still recommendations.
- **ASI03:** the CA and keys are synthetic, and the default peer mode uses a shared HMAC key. There is no OAuth token exchange (RFC 8693) and no workload identity (SPIFFE).
- **ASI04:** there is no hash-pinned lockfile, no SBOM and no package-signature check. The A2A Agent Card is unsigned and the A2A path is unauthenticated. MCP tool metadata is not vetted.
- **ASI06:** the checkpoint digest proves integrity, not benign content, so content poisoned before export arrives intact. The relocation manifest is not signed, and there is no long-term memory or retrieval store to protect.
- **ASI07:** there is no TLS or channel binding. `tests/test_peer.py::PeerAuthTests::test_limitation_on_path_relay_sees_payload_without_channel_security` documents that an on-path relay can read the delivery. The A2A adapter declares no security scheme.
- **ASI08:** only a single hop between two agents is tested. There are no multi-hop propagation tests and no circuit breakers.
- **ASI09:** there is no human approval UI, no confirmation step for sensitive actions and no work on explainability.
- **ASI10:** there is no behavioural monitoring, drift detection or kill switch outside the local store, and no limit on self-replication or child creation.

**Prompt injection across agent boundaries.** Injection can arrive through artifacts, tool outputs, tool metadata, Agent Cards and delegated results. The published evidence does not show any detector to be reliable against adaptive attacks. See [cross-agent prompt injection](cross-agent-prompt-injection.md) for the taxonomy, the evidence behind each defense, what this repository's controls do and do not cover, and a proposed synthetic experiment.

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
OpenTelemetry: https://github.com/open-telemetry/semantic-conventions-genai
OWASP Top 10 for Agentic Applications 2026 (ASI01–ASI10): https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/ (accessed 2026-10-16)
OWASP Top 10 for LLM Applications 2025, LLM06:2025 Excessive Agency: https://genai.owasp.org/llmrisk/llm062025-excessive-agency/ (accessed 2026-10-16)
