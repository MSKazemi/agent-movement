# Verifiable movement receipts and an independent forensic timeline (experiment)

**Status (2026-10-16):** Tested experimental profile `agent-movement.receipt/0.1-draft`. **Not a standard, not production-secure, not A2A.** It covers synthetic fixtures and a local offline verifier only. Tracking issue: #11. It builds on the unsigned PR #6 receipts in [local-implementation.md](local-implementation.md) and the research design in [agent-forensics-and-fingerprints.md](agent-forensics-and-fingerprints.md).

PR #6 receipts carry digests but no signature or attestation field, so nobody outside the receiver can check them. This experiment adds three things:

1. A signed receipt profile.
2. Independent, tool-side records.
3. An offline verifier that rebuilds a sanitized timeline and keeps the uncertainty explicit.

It is deliberately **separate from trace correlation**. A trace ID helps you find related records; it never tells you who did something.

## Run it

```sh
python -m pip install -e ".[signing]"     # optional extra: cryptography>=50.0.2 (Ed25519)
python -m agent_movement.receipts verify tests/fixtures/movement-receipts                     # all 9 bundles
python -m agent_movement.receipts verify tests/fixtures/movement-receipts/04-forged-identity --json
python -m agent_movement.receipts timeline tests/fixtures/movement-receipts/09-clock-skew
python -m agent_movement.receipts make-fixtures /tmp/regenerated   # byte-identical to the committed set
python -m unittest discover -s tests -v
```

The core package stays dependency-free. Without the `signing` extra:

- the verifier still checks schema, body digests, exact replays, credential-like content, subject digests and redaction;
- every signature is reported as `UNCHECKED`, and the run exits with code 3;
- the 13 tests that need Ed25519 skip.

| Exit code | Meaning |
| --- | --- |
| 0 | No receipt was rejected and nothing conflicts. **This does not mean the evidence is complete.** Claims can still be `UNKNOWN`, and gaps can exist. |
| 1 | At least one receipt was rejected (`TAMPERED`, `REPLAYED`, `UNTRUSTED` or `MALFORMED`), a statement conflicts, or a subject digest does not match. |
| 2 | Usage or I/O error, for example no trust anchors. |
| 3 | Verification is incomplete: signatures were not checked, or no receipt is valid. |

## Event schema: claims are not principals

A receipt body is a strict JSON object. Every field must be present. An unknown value is an explicit `null`, and the verifier reports it as `UNKNOWN`; it never guesses.

| Field | Meaning | Who vouches for it |
| --- | --- | --- |
| `issuer.key_id` | Key that signed the body | The signature, checked against the trust anchors |
| `issuer.claimed_principal`, `issuer.claimed_agent_id` | What the signer says it is | **Claims.** A principal that differs from the key's anchor principal makes the receipt `UNTRUSTED`. Agent labels are never bound to keys. |
| `source`, `destination` (`claimed_agent_id`, `claimed_principal`, `execution_id`) | One party's statement about the two ends of a movement | **Claims** by the signer. A dispatch names the destination. The destination principal becomes `VERIFIED` only when that principal signs the response itself. |
| `logical_task_id` | Application-level continuity of the work | Signed claim |
| `execution` (`execution_id`, `parent_execution_id`, `agent_instance_id`, `definition_digest`) | The runtime attempt, kept apart from the logical task | Signed claim. Two executions that share a `definition_digest` stay **distinct**. |
| `movement` (`movement_id`, `parent_movement_id`, `lineage_relation`) | One directed transfer and its ancestry: `delegate`, `relocate`, `clone`, `fork`, `replicate` or `fan_out` | Signed claim, shown as lineage edges |
| `correlation` (`trace_id`, `span_id`) | W3C-shaped correlation hints | **Correlation only.** Never authentication, never a reason to merge two movements. |
| `subjects[]` (`role`, `ref`, `digest`) | `sha256:` JCS digests of **salted commitment documents** `{"commitment_salt", "value"}` for the envelope, artifact, checkpoint or effect payload. They can also reference an external `revocation_notice` or `policy_decision` by digest only. | Integrity against the signed reference. This does not establish authorship or correctness, and referenced external notices are not parsed or verified here. |
| `effect` (`effect_id`, `tool_principal`, `status`, `fencing_epoch`) | An effect the agent claims, or the tool-side record of it | Confirmed only by an independent `tool.effect_recorded` receipt signed by a key with role `tool` |
| `seq`, `prev_receipt_digest`, `nonce`, `issued_at`, `audience` | Per-signer chain, replay protection, **claimed** time, intended reader | The signer, see the limits below |

Receipt types: `movement.dispatched`, `movement.accepted`, `movement.rejected`, `execution.started`, `execution.completed`, `tool.effect_recorded`. Data classification must be `synthetic` or `public`.

**Claim statuses in the verifier report:**

| Status | Meaning |
| --- | --- |
| `VERIFIED` | The principal is bound by a trusted signature and is consistent with the other side. |
| `SIGNED_CLAIM` | A trusted signer said it, but no one else corroborated it. |
| `UNVERIFIED_CLAIM` | The signer is untrusted, or the signature was not checked. |
| `UNKNOWN` | There is no evidence. |
| `CONFLICTING` | Verified statements disagree. |
| `CORRELATION_ONLY` | Applies to trace IDs. |

**Evidence grades.** These are an ordinal operationalization of the proposal in the forensics doc. They are **not probabilities**.

| Grade | Assigned when |
| --- | --- |
| **E3** | A valid trusted signature, corroborated by an independent trusted party: a paired dispatch and response, or an agent effect claim that matches a tool-side record. |
| **E2** | A single-source valid trusted signature. |
| **E1** | Unsigned telemetry, an untrusted signer, or a signature that was not checked. |
| **E0** | Inference only. **The verifier never assigns it**, because it never infers events. |

## Canonicalization and signature scheme

- **Canonical bytes:** a documented subset of [RFC 8785 JCS](https://www.rfc-editor.org/rfc/rfc8785.html), implemented in `src/agent_movement/jcs.py`.
  - Members are sorted by UTF-16 code units.
  - There is no whitespace.
  - Only `"`, `\` and U+0000..U+001F are escaped, using JCS short forms and otherwise lowercase `\u00xx`.
  - Integers must be within ±(2^53−1).
  - **Floats are rejected** rather than serialized, so the ECMAScript number formatting rules are never needed.
  - Lone surrogates are rejected.

  Inside this subset the output is byte-identical to RFC 8785. Tests check the RFC 8785 §3.2.3 sort example and the §3.2.2.2 string example. For valid PR #6 envelopes, `jcs_digest(x) == "sha256:" + core.digest(x)`, including non-ASCII text.
- **Wire format:** `{"receipt": <body>, "body_digest": "sha256:<hex of JCS(body)>", "signature": {"alg": "Ed25519", "key_id": ..., "value": <base64url>}}`. The signature sits **outside** the signed body. `signature.key_id` must equal the signed `issuer.key_id`.
- **Signed message:** `b"agent-movement/receipt/v0.1\x00" || JCS(body)`. The domain separation prevents a signature from being reused across protocols or versions.
- **Algorithm:** Ed25519 ([RFC 8032](https://www.rfc-editor.org/rfc/rfc8032)) via the optional extra `cryptography>=50.0.2`. That was the latest stable release on PyPI when checked on 2026-10-16; it was uploaded 2026-09-30. Ed25519 signatures are deterministic, which makes the fixture set reproducible byte for byte.
- **Why not stdlib HMAC:** a MAC key lets every holder create valid tags. An "independent" verifier would therefore need the same secret, and could then forge receipts itself. HMAC gives no non-repudiation and no separation between signer and verifier. Public-key signatures were chosen for that reason. Core stays dependency-free, and signature checking is the only part that needs the extra.

## Trust anchors and synthetic key management

`trust.json` (`agent-movement.trust/0.1-draft`) binds each `key_id` to a principal, a role (`agent` or `tool`), a validity window and an optional `revoked_at`. The verifier evaluates validity at the receipt's **claimed** `issued_at`.

**Revocation:**

- An anchor can also carry `revocation_ref`: the digest of an **external** signed revocation notice, for example one produced by a peer-authentication component.
- The verifier cites that reference in its rejection reason, but neither fetches nor verifies the notice. This profile does not depend on any revocation implementation.
- PR #6's `Approval.revoked` is a static configuration flag with no runtime revoke API. Its `handoff.denied` audit events are **not** evidence that a revocation mechanism exists or ran.

- **Fixture keys:** derived as `sha256("agent-movement/SYNTHETIC-PUBLIC-TEST-KEY/v1/" + name)`. Their private halves are public by construction, so they are test vectors, never credentials. No private key is stored in any file.
- **Anchor lookup:** the verifier uses `--trust FILE` or, by default, a `trust.json` in the bundle directory or its parent. **Anchors shipped with the evidence prove nothing.** A test shows that an attacker who adds their own key to a bundle-local `trust.json` gets `VALID` under default lookup, and `UNTRUSTED` once the real anchors are passed with `--trust`. In real use, obtain anchors out of band, for example from a SPIFFE trust bundle. That is not implemented here.
- **Role separation:** a `tool.effect_recorded` receipt must be signed by a `tool` key, and movement and execution receipts by an `agent` key. An agent that "confirms" its own effect is rejected.

## Verification algorithm

Records are processed per bundle in ingestion order: `receipts.jsonl`, then `tool-records.jsonl` (independent tool-side records), then unsigned `telemetry.jsonl`.

1. Parse with strict JSON: duplicate keys are rejected, and a line is limited to 16 KiB.
2. Check the exact wire format. **A credential-like value makes the receipt `MALFORMED`, and its content is withheld from the report.**
3. Validate the schema strictly → `MALFORMED`.
4. Check `body_digest` against the canonical body, then the signature block's `key_id` and algorithm → `TAMPERED`.
5. Look up the key in the trust anchors → `UNTRUSTED` if it is unknown.
6. Verify Ed25519 → `TAMPERED` on failure. Without the extra → `UNCHECKED`.
7. Check key validity and revocation at the claimed time, issuer principal consistency, and signer role → `UNTRUSTED`.
8. Detect replays. Replay keys are always **per issuer**, `(key_id, nonce)` and `(key_id, receipt_id)`, never a global key. That differs from PR #6's idempotency keys, which are global rather than per sender. Only receipts whose signature passed enter the replay table, so a forger cannot pre-register a nonce:
   - an identical body seen again under the same `(key_id, nonce)` or `(key_id, receipt_id)` → `REPLAYED`, deduplicated;
   - the same nonce or receipt_id with a *different* body from the same key → both receipts `CONFLICTING`, because that is signer equivocation and not something an outsider could replay.

   `ReplayGuard(max_age=...)` adds a freshness window for live acceptance.
9. Cross-check valid receipts:
   - per-signer `seq` and `prev_receipt_digest` chains: gaps, forks, broken links;
   - dispatch versus response: destination swap, contradictory responses, `logical_task_id` mismatch;
   - agent effect claim versus tool record;
   - subject files in `subjects/<ref>.json` versus their signed digests.

Verdicts: `VALID`, `UNCHECKED`, `UNTRUSTED`, `TAMPERED`, `REPLAYED`, `MALFORMED`.

**Timeline:**

- **Included:** `VALID`, `UNCHECKED` and `UNTRUSTED` receipts, telemetry spans, and `evidence.gap_detected` entries. Tampered, replayed and malformed records are listed as rejected and kept out of the timeline.
- **Status:** each entry is `VERIFIABLE`, `UNVERIFIABLE` or `CONFLICTING`.
- **Ordering:** causal edges (per-signer sequence; dispatch → response → execution; parent response → child dispatch) take precedence over claimed timestamps. `ordering_basis` says which one placed an entry.
- **Clock disagreements:** when a claimed time precedes a causal predecessor, a note flags clock skew or a false timestamp, and the causal order is kept.

## Reproducible fixture set (`tests/fixtures/movement-receipts/`)

The set is generated by `src/agent_movement/receipt_fixtures.py` and uses the real PR #6 `HandoffReceiver` and `EffectGateway` for the envelope, the artifact and the fencing epochs. The expected results are hand-written in `expected.json`, and a test regenerates the whole set and compares it byte for byte.

| Bundle | What it exercises | Exit |
| --- | --- | --- |
| `01-valid-delegation` | Paired dispatch and accept (E3), started, completed, a tool-side record that confirms the effect, matching envelope and artifact digests, 3 telemetry spans | 0 |
| `02-tampered-receipts` | Executor swapped with the digest recomputed (signature fails); outcome edited without recomputing the digest; artifact file altered after signing | 1 |
| `03-replayed-receipts` | An exact duplicate dispatch in the same log; the accept replayed through the tool-record source | 1 |
| `04-forged-identity` | Unknown attacker key claiming agent/b; trusted agent/c claiming to be agent/b; a revoked key; an agent self-confirming a tool effect; a forged telemetry span with a matching trace ID | 1 |
| `05-missing-claims` | Null destination and trace; no response; seq 2..3 missing (a gap); an effect claim with no tool record. **Exit 0 with UNKNOWNs.** | 0 |
| `06-conflicting-accounts` | Receiver signs both accept and reject; destination swap (agent/c answers a dispatch to agent/b); the agent says the effect was committed while the tool says it was rejected (stale epoch) | 1 |
| `07-fork-lineage` | A delegate followed by two `fork` children; two executions that share one definition digest and stay distinct | 0 |
| `08-privacy-canaries` | A token-shaped ID inside a signed receipt; an extra `prompt` field; telemetry carrying credential-like canaries in attributes, keys and span names | 1 |
| `09-clock-skew` | The accept claims an earlier time than its dispatch; causal order is kept and the skew is noted | 0 |

**Verifier output, abbreviated, for `06-conflicting-accounts`:**

```text
movement mov-conflict-1 [delegate] grade=E2
    destination_principal     VERIFIED          spiffe://synthetic.test/agent/b
    outcome                   CONFLICTING       ['accepted', 'rejected']
movement mov-conflict-2 [delegate] grade=E2
    destination_principal     CONFLICTING       spiffe://synthetic.test/agent/c
effect effect-conflict-1 (task task-conflict-1): CONFLICTING agent=['committed'] tool=['rejected']
timeline: 1 VERIFIABLE, 0 UNVERIFIABLE, 6 CONFLICTING
```

## Privacy and retention

**Receipts:**

- Receipts carry IDs, principals, digests, statuses and claimed times only. The schema has no free-text field.
- The signer refuses to sign, and the verifier rejects, values that look like credentials: bearer, basic or JWT-shaped tokens, PEM private keys, common API-key prefixes, and `token=`, `secret=` or `password=` assignments.
- Subjects are referenced by digest. Raw envelopes are only needed when someone wants to check a digest.
- **Never publish unsalted digests of task content.** A digest of short or guessable text can be confirmed by brute force.
  - PR #6's `envelope_digest`, `artifact_digest` and the `audit_events.info_digest` column are unsalted hashes over the full envelope, task text included.
  - This profile therefore never copies them. Every fixture subject, and the PR #6 bridge `body_from_handoff(..., salt=...)`, signs the digest of a salted commitment `{"commitment_salt": <128-bit hex>, "value": ...}`.
  - The commitment document stays with the evidence holder.
  - A test asserts that no unsalted subject digest appears in any published receipt.

**Telemetry:**

- Telemetry is untrusted input.
- Sensitive attribute names (authorization, cookie, token, secret, password, api key, credential, prompt, message, content, completion, baggage, header) are redacted.
- Credential-like values and invalid span names are redacted.
- Only `agent.claimed_id`, `movement_id`, `logical_task_id`, `execution_id` and `outcome` are kept. Everything else is dropped and counted.
- Tests assert that no canary reaches either the text or the JSON output.

**Retention:**

- The verifier stores nothing; its reports are derived and sanitized.
- For real deployments, keep the original evidence separate from analytic reports, record chain of custody ([NIST SP 800-86](https://csrc.nist.gov/pubs/sp/800/86/final)), and apply bounded, purpose-limited retention.
- Treat movement and trace IDs as linkable metadata, and never propagate secrets in `traceparent` or `baggage` ([W3C Baggage](https://www.w3.org/TR/baggage/)).
- The profile has no retention-policy field yet; that is an open question.

## Trust assumptions

1. Trust anchors are authentic and obtained independently of the evidence.
2. Signing keys were not compromised during their validity window.
3. The `cryptography` Ed25519 implementation is correct.
4. The tool-side signer really is the effect target, and it authenticated its caller correctly. That authentication is outside this profile.
5. The verifier runs on an untampered host.
6. Fixtures are synthetic. No real principal, credential, prompt or message appears in them.

## Evidence limits (read before citing results)

- **A signature does not make a statement true.** It shows that a trusted key holder signed it. A lying or compromised receiver can sign false claims; equivocation is detected only when both versions reach the verifier.
- **Logs are not guaranteed complete.** A missing receipt is `UNKNOWN`, never proof that nothing happened. Sequence gaps are detected only between receipts the verifier can see. A signer can rewrite its whole chain, because nothing anchors it independently: there is no transparency log or external checkpoint.
- **Timestamps are claims.** There is no trusted timestamping, so backdating inside a key's validity window, or before a revocation, cannot be detected. Ordering uses causal links first.
- **Replay detection is per verifier run.** `ReplayGuard` is in memory. A persistent, cross-bundle replay ledger is not implemented.
- **Agent labels and trace IDs are never authenticated.** Principals are only as meaningful as the trust anchor file.
- **Not implemented:** SPIFFE/SVID verification, key rotation protocols, in-toto/Sigstore envelopes, a transparency log, receipt emission inside the live HTTP path (the PR #6 bridge `body_from_handoff` wraps receipts after the fact), and production key storage.

## Files

- `src/agent_movement/jcs.py`: canonical JSON subset.
- `src/agent_movement/receipts.py`: schema, signer, trust anchors, `ReplayGuard`, verifier, timeline, CLI, and the PR #6 bridge `body_from_handoff`.
- `src/agent_movement/receipt_fixtures.py`: deterministic synthetic keys and scenarios, and the hand-written expectations.
- `tests/test_movement_receipts.py`: canonicalization, schema, redaction, the path without the extra, fixture expectations, adversarial mutation, replay, trace-as-correlation, trust-anchor limits, and the PR #6 bridge, salted commitments and the external revocation reference.

References: [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785.html), [RFC 8032](https://www.rfc-editor.org/rfc/rfc8032), [W3C Trace Context](https://www.w3.org/TR/trace-context/), [SPIFFE SVIDs](https://spiffe.io/docs/latest/deploying/svids/), [in-toto attestation](https://github.com/in-toto/attestation), [NIST SP 800-86](https://csrc.nist.gov/pubs/sp/800/86/final), [cryptography on PyPI](https://pypi.org/project/cryptography/).
