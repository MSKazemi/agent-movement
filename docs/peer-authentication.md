# Peer authentication and pre-disclosure authorization (synthetic, local)

**Status:** Tested experimental software for [issue #8](https://github.com/MSKazemi/agent-movement/issues/8), with HPKE-sealed delivery from [issue #19](https://github.com/MSKazemi/agent-movement/issues/19) and counted (single-use by default) grants from [issue #29](https://github.com/MSKazemi/agent-movement/issues/29). **Synthetic test keys only. Not A2A, not OAuth/RFC 8693, not a PKI, not production-secure.** It builds on the [local proof of concept](local-implementation.md) and the [threat model](security-and-trust.md).

> **Two delivery modes.** With the optional `hpke` extra and an `enc_key` in the receiver's card, the task text and the receipt cross the wire **only as ciphertext** (see [Delivery confidentiality](#delivery-confidentiality-hpke-issue-19)). The stdlib-only mode (no extra, no `enc_key`) still works but has **no confidentiality**: anyone who controls the receiver's address can read the delivered text.

## What problem this closes

The PR #6 receiver (`HandoffReceiver`) validates a **self-declared** `agent_id` and a receiver-local approval **after** the full envelope, including task text, has arrived. That proves nothing about who sent it and discloses the task to whoever listens on the port.

This slice adds an explicit trust model in new modules (`trust.py`, `peer.py`, `peer_http.py`, `peer_demo.py`). The existing `core.py` and `http.py` are unchanged. The slice enforces three rules:

1. **Metadata first, payload last.** Task text leaves the sender only after the destination has been authenticated *and* the receiver has authorized the specific grant.
2. **Authority is rechecked where it matters.** Checks run at preflight, again at delivery, and again *inside the SQLite transaction that records the simulated external effect*. This closes the PR #6 gap "receiver grant not rechecked at simulated effect commit".
3. **No reusable credentials travel.** The envelope carries a task-bound, audience-bound, sender-constrained grant. It never carries a user or provider token. A sender-side guard refuses to transmit any byte string it was told it holds as a secret.

## Three things that are not the same

| Concept | What it is here | Who vouches | What it does **not** prove |
|---|---|---|---|
| **Peer identity** | Proof of possession of the key named in a card, shown by a signature over a fresh, nonce-bearing message | The pinned synthetic **test CA** (binding) plus the peer's own signature (possession) | That the agent is benign, or what software or model runs behind the key |
| **Claimed agent metadata** | `endpoint`, `capabilities` and `schema_versions` inside the CA-signed card | The test CA endorses the binding. The values are still the agent's *claims* | That the agent really implements or limits itself to those capabilities. The receiver enforces its own allowlist separately |
| **User authorization** | A grant signed by a **separate** synthetic user authority. Fields: `subject` (user), `actor` (origin agent), `audience` (destination agent), `task_id`, `capabilities`, `classification`, `not_before`/`expires_at`, `max_uses` (default 1), plus revocation | The user authority key, pinned by the receiver | That the user understood the task. It is a synthetic stand-in for a consent step |

The receiver's sanitized trace records **two separate fields**. `peer` is set only after signature verification. `claimed_peer` is the unauthenticated claim. A forged request therefore shows `peer: null, claimed_peer: "agent-a"`.

The grant semantics follow the delegation vocabulary of [RFC 8693](https://www.rfc-editor.org/rfc/rfc8693): `sub` for the subject, the `act` (actor) claim in §4.1, and `audience`/`scope` as request parameters in §2.1. This is **not** an RFC 8693 token exchange and has no security token service.

## Protocol

```
origin agent-a                                                receiver agent-b
 |  (1) GET /v0/agent-card ---------------------------------->  | public metadata only
 |  <------------------------------ CA-signed card (endpoint, caps, schemas, key)
 |  verify: pinned CA, agent_id == intended, endpoint == URL contacted,
 |          schema + capability advertised          -> else ABORT (nothing sent)
 |  (2) POST /v0/preflight  [signed by agent-a key] -------->  | NO task text:
 |      origin card, destination{agent_id,endpoint}, task{kind,classification,
 |      commitment=H(salt||task)}, grant, client_nonce, issued_at, ids
 |                                   verify card + signature (identity), freshness,
 |                                   destination binding, receiver allowlist,
 |                                   grant signature/scope/liveness/revocation,
 |                                   nonce single-use, one grant use consumed
 |                                   (max_uses) in the admission transaction
 |                                                         -> else 400/401/403/409
 |  <---------------- admission [signed by agent-b key]: echoes client_nonce,
 |                    preflight digest, destination, short expiry
 |  verify admission with the key in the card       -> else ABORT (no text sent)
 |  (3) POST /v0/deliveries [signed by agent-a key] -------->  | HPKE mode: enc{suite,kid,ct}
 |      ct = HPKE-Seal(card.enc_key, info=transcript,            |   (task text + salt + response
 |                     {task, salt, response_key})            |    key inside ct only)
 |                                                            | plaintext mode: task text + salt
 |                                   same peer as admitted (signature covers ct),
 |                                   admission not expired, then HPKE-Open (AEAD tag
 |                                   checked before any plaintext exists),
 |                                   commitment matches, grant live/not revoked,
 |                                   pure computation (idempotent, SQLiteStore),
 |                                   simulated effect: grant re-verified IN the
 |                                   same BEGIN IMMEDIATE transaction as the insert
 |  <------------- receipt [signed by agent-b key; HPKE mode: encrypted under response_key]
```

Design points:

- **Domain-separated signatures.** Each signature covers `purpose || canonical JSON`, so a card signature can never verify as a grant, an admission or a delivery.
- **Salted commitment.** The preflight binds the task (`sha256(domain || 32-byte salt || canonical(task))`) without disclosing it. A plain hash of short text could be brute-forced. The salt is sent only with the delivery.
- **Sender-constrained grant.** A stolen grant is useless without the actor's key, because every preflight and delivery must carry the actor's own signature (a proof-of-possession idea similar to DPoP).
- **Counted grants (issue #29).** See [Grant uses and retries](#grant-uses-and-retries-issue-29).

### Grant uses and retries (issue #29)

A grant admits at most `max_uses` distinct movements. `max_uses` is an integer from 1 to 1,000,000 inside the signed grant payload, so nobody but the user authority can change it. `issue_grant` defaults it to **1**. A grant signed before issue #29 has no `max_uses` field and verifies as single-use, the most restrictive value. The field cannot be stripped from a newer grant, because the signature covers it.

- **Where a use is consumed.** At preflight, inside the same `BEGIN IMMEDIATE` transaction that checks liveness and revocation, records the nonce and writes the admission. The use (a `grant_uses` row) and the admission therefore commit or roll back together. Concurrent preflights for one grant serialize on the SQLite write lock, so a single-use grant admits exactly one movement even when many threads or processes race (`test_single_use_grant_admits_one_movement_under_thread_concurrency`, `CountedGrantProcessTests`). Beyond the limit, the receiver answers 403 with the trace reason `grant_uses_exhausted`. That happens at preflight, so the refused task's text is never sent.
- **Retries do not consume uses.** A use is counted per `(grant_id, movement_id)`.
  - An identical **delivery** retry does not touch the grant counter. It returns the idempotent receipt (`replayed: true`, effect `replayed`).
  - A **preflight retry of an admitted movement**, for example after the admission reply was lost, is also allowed. It carries a fresh nonce and salt. The receiver issues a new admission that **supersedes** the old one (the old admission ID then gets 403 `unknown_admission`), records the trace reason `readmitted` and consumes no use. It does this even when the grant is otherwise exhausted. The retry must match the admitted movement's origin, logical task, grant ID, task kind, classification, idempotency key and trace ID; any difference is a 409 conflict, and no use is consumed.
- **Idempotency keys are per sender.** Delivery deduplication in the core store is keyed by `(authenticated origin, idempotency_key)`, so two peers can use the same key. Movement IDs remain unique across senders.
- **Upgrading a ledger.** When `PeerLedger` opens a file without `grant_uses`, it creates the table and backfills one use for every existing admission, in one transaction. An upgrade therefore never hands a grant extra uses.

What this does **not** do: a use is consumed at admission, not at effect commit. An admission that expires unused still holds its use, although the same movement can be re-admitted with a retry. Uses are counted per receiver database, so a grant whose audience runs several receivers on separate databases is counted separately on each one. Counts are keyed by `grant_id` alone, as revocations are, so two issuers that sign the same `grant_id` share one counter (this fails closed). There is no API to inspect or reset counts other than `PeerLedger.grant_uses()`.
- **Coarse errors to peers.** Peers see only `400 invalid_contract|unsupported_schema`, `401 unauthenticated`, `403 forbidden` or `409 conflict`. The precise reason goes only to the receiver's local, sanitized trace.
- **Loopback/in-process endpoints only.** Cards may name only `http://127.0.0.1:<port>` or `local://<name>`. A forged card therefore cannot point a sender at an arbitrary host (SSRF).

### Signature backends

| Mode | Dependency | Property | Use |
|---|---|---|---|
| `HS256` (default) | stdlib `hmac` | Symmetric. **Anyone who can verify a key can also sign with it.** In this mode every verifier holds the CA key and could mint cards | Outsider-attacker model only. Keeps the package and CI dependency-free |
| `Ed25519` | optional extra `pip install -e '.[ed25519]'` (`cryptography>=50.0.2`) | Asymmetric. Verifiers hold public keys only and cannot forge | Insider model. Every peer test also runs in this mode, and those tests are skipped cleanly when the extra is absent |

`cryptography` 50.0.2 was the latest stable release on PyPI when this was written: version metadata from `https://pypi.org/pypi/cryptography/json` was checked on 2026-10-16, and the release was uploaded 2026-09-30.

## Delivery confidentiality (HPKE, issue #19)

Issue #8 left one gap open on purpose: an attacker who controls the receiver's *real* address can relay the preflight and admission verbatim and then read the delivered text. Issue #19 closes it for the payload by encrypting the delivery to a key that the test CA signs into the receiver's card.

| Element | What is implemented |
|---|---|
| Receiver key | An X25519 key in the card as `enc_key: {suite, kid, public}`. The test CA's card signature covers it, so a relay cannot swap in its own key (that fails as `bad_card_signature`). It is separate from the signing key. `PeerReceiver` refuses to start unless it holds exactly the private key that its card advertises |
| Cipher suite | [RFC 9180](https://www.rfc-editor.org/rfc/rfc9180) HPKE, base mode, single-shot: DHKEM(X25519, HKDF-SHA256), HKDF-SHA256 and ChaCha20-Poly1305 (KEM 0x0020, KDF 0x0001, AEAD 0x0003). It uses `cryptography`'s own HPKE API (`cryptography.hazmat.primitives.hpke.Suite`), not a hand-built composition. `Rfc9180KnownAnswerTests` decrypts the RFC 9180 Appendix A.2.1 test vector with this exact suite |
| Transcript binding | The `info` input binds the suite, the `enc_key` kid, the SHA-256 of the receiver's signed card (the descriptor digest), the movement ID, the origin ID, the audience (the receiver's agent ID), the endpoint, the client nonce, the admission ID and the preflight digest. The receiver rebuilds `info` from its own admission record only. If any field differs, HPKE derives a different key and decryption fails |
| Sender authentication | HPKE base mode does not authenticate the sender. The origin signs the delivery *including the ciphertext* (encrypt-then-sign), and the receiver checks that signature before it decrypts anything |
| Receipt | The receipt contains the result and unsalted content digests, so it is encrypted too. The sender puts a fresh 256-bit `response_key` inside the HPKE plaintext. The receiver returns its signed receipt encrypted with ChaCha20-Poly1305 under that key, using the same transcript (plus a `response` label) as associated data. This is comparable to [RFC 9458 §4.4](https://www.rfc-editor.org/rfc/rfc9458#section-4.4) response encapsulation but is not that construction: RFC 9458 derives the key with the HPKE exporter, which the single-shot API does not expose |
| No downgrade | If the destination card has an `enc_key`, the client always seals to it. Without HPKE support the client aborts at discovery (`encryption_unavailable`) instead of falling back to plaintext. An encrypting receiver refuses a plaintext delivery (`plaintext_delivery_refused`). `PeerClient(require_confidentiality=True)` also refuses destinations whose card has no `enc_key` (`no_confidentiality_key`) |

**Why `info` and not the AEAD `aad`.** RFC 9180 §8.1 says that applications that use only the single-shot APIs "should use the Setup info parameter for specifying auxiliary authenticated information". The `cryptography` documentation repeats this, and its public single-shot API takes `info` but has no `aad` argument. The effect on the transcript is the same: a mismatch makes the AEAD open fail, and no plaintext is produced.

| Mode | How you get it | Confidentiality of task text and receipt |
|---|---|---|
| Plaintext (stdlib-only) | No extra and no `enc_key` in the receiver card. The default for `HS256` | **None.** Labelled `plaintext_no_confidentiality` in the client trace and `"delivery_confidentiality": "none (...)"` in the demo output |
| HPKE | `pip install -e '.[hpke]'` and the receiver card has an `enc_key`. Works with `HS256` or `Ed25519` signatures. The demo default for `Ed25519` | Only ciphertext on the wire, in both directions |

`hpke` is its own optional extra (`cryptography>=50.0.2`, the same package and pin as `ed25519`). The core package stays dependency-free.

## Run it

~~~sh
python -m pip install -e .                 # stdlib only: plaintext delivery, no confidentiality
python -m pip install -e '.[ed25519,hpke]' # optional: Ed25519 signatures and HPKE-sealed delivery
python -m pytest -q
python -m agent_movement.peer_demo                      # HS256, plaintext (labelled)
python -m agent_movement.peer_demo --delivery hpke      # HS256 signatures, HPKE delivery
python -m agent_movement.peer_demo --alg Ed25519        # Ed25519 signatures, HPKE delivery (auto)
~~~

The demo starts `agent-b` as a **separate OS process** on loopback. It provisions that process with a per-run JSON file (mode 0600, in a temp directory that is deleted afterwards) written by the parent, which plays the test CA and the user authority. A rogue-CA "agent-b" impostor runs on a second port. The demo exits non-zero if any denied scenario carried the task canary or a delivery request, if any scenario carried the provider canary, or if the task canary appears in the receiver's SQLite files. In HPKE mode it also exits non-zero if the task canary appears in the captured bytes of **any** scenario, including the successful handoff and the revoked-in-flight delivery.

## Negative tests (`tests/test_peer.py`)

Every row in `PeerAuthTests` runs three times:
- `PeerAuthTests`: `HS256` with plaintext delivery, the stdlib-only mode.
- `PeerAuthHpkeTests`: `HS256` with HPKE delivery.
- `PeerAuthEd25519Tests`: `Ed25519` with HPKE delivery.

The two HPKE classes are skipped cleanly when the extra is absent. "Before disclosure" means that the recorded transport has **no `/v0/deliveries` request** and that **no canary** appears in the wire bytes, the receiver trace, the `agent_movement.peer` log records, the core audit table, or the raw SQLite/WAL files.

| Attack / condition | Where it is stopped | Before disclosure? |
|---|---|---|
| Fake receiver: card from rogue CA reusing the pinned kid / unknown CA kid | client, discovery (`bad_card_signature` / `untrusted_card_issuer`) | yes, only the GET was sent |
| Fake receiver replays the stolen real card but lacks the key | client, admission signature (`admission_bad_signature`) | yes, only metadata was sent |
| Other genuine agent (`agent-c`) answers at agent-b's address | client, discovery (`wrong_destination_identity`) | yes |
| Real card served from another endpoint | client, discovery (`endpoint_mismatch`) | yes |
| Expired receiver card | client, discovery (`card_expired`) | yes |
| Fake sender: rogue-CA card / stolen card without key | receiver, preflight 401 (`bad_card_signature` / `bad_signature`) | yes |
| Genuine insider presents another agent's grant | receiver, preflight 403 (`wrong_actor`) | yes |
| Self-declared PR #6 envelope sent to `/v0/preflight` | receiver 400 | yes |
| Tampered / replayed / stale preflight | 401 / 409 / 401 | yes |
| Expired, not-yet-valid, revoked (signed notice), untrusted-issuer grant | receiver, preflight 403/401 | yes |
| Forged revocation notice | receiver 401; the grant keeps working | n/a |
| Wrong audience, wrong task, capability not granted | receiver, preflight 403 | yes |
| Second movement under a single-use grant / a third under `max_uses=2` (`tests/test_grant_uses_and_sender_keys.py`) | receiver, preflight 403 (`grant_uses_exhausted`) | yes |
| Preflight retry of an admitted movement with a changed idempotency key or grant | receiver, preflight 409; no use consumed | yes |
| Tampered `max_uses` / re-signed invalid `max_uses` | receiver 401 (`bad_grant_signature`) / 403 (`malformed_grant`) | yes |
| Capability not allowlisted | client (not advertised) **and** receiver (`capability_not_allowlisted`) | yes |
| Unsupported schema | client (not advertised) **and** receiver 400 `unsupported_schema` | yes |
| Preflight addressed to another endpoint (relay to the real receiver) | receiver 403 (`wrong_destination`) | yes |
| Delivery signed by a different peer / not matching the commitment / without an admission | receiver 401 / 403 / 403 | text sent by the attacker's own choice. **Not persisted or logged** |
| Revocation **between admission and delivery** | receiver, delivery 403 (`grant_revoked`) | **no, this is a documented window.** Text was sent, then neither executed nor persisted |
| Revocation / expiry **between delivery and effect commit** | effect gateway, same transaction (`effect_grant_revoked` / `effect_grant_expired`) | no effect recorded |
| Concurrent revocation vs. 8 parallel commits | `authority_log` shows every committed effect sequenced **before** the revocation | linearized |
| Provider token canary placed in the task text | sender guard `DisclosureBlocked` before any POST | yes |

HPKE-only rows (`SealedDeliveryCases`, run in both HPKE classes). The tests check the tamper, transcript, moved-ciphertext and wrong-key rejections the same way each time:
- A patched `SQLiteStore.receive` proves that the task was never executed.
- There is no audit row and no effect, and no canary appears in storage.
- Afterwards an honest delivery against the same admission still succeeds.

| Attack / condition | Where it is stopped |
|---|---|
| **On-path relay that owns agent-b's real address** and records every byte in both directions (`test_on_path_relay_sees_only_ciphertext_with_hpke`) | Not stopped. The handoff completes, but the relay captures **ciphertext only**: no canary, no `text`, `salt`, `artifact` or `envelope_digest` field. In plaintext mode the same test asserts that the relay *does* read the text (no confidentiality) |
| Relay replaces the card's `enc_key` with its own | client, discovery (`bad_card_signature`) |
| Ciphertext tampered and re-signed by the genuine origin / truncated | receiver 401 `delivery_decrypt_failed` |
| Ciphertext tampered by anyone else | receiver 401 `bad_signature` (the signature covers the ciphertext) |
| Transcript mismatch: movement ID, origin, audience, endpoint, client nonce, admission ID, preflight digest, card digest or kid | receiver 401 `delivery_decrypt_failed` (one subtest per field) |
| Valid ciphertext moved to another admission | receiver 401 `delivery_decrypt_failed` |
| Sealed to a rogue X25519 key that reuses the kid / addressed to a kid the receiver does not hold | receiver 401 `delivery_decrypt_failed` / `wrong_enc_key` |
| Plaintext delivery to an encrypting receiver | receiver 403 `plaintext_delivery_refused`. The text was exposed by the sender, but it is not executed |
| Sealed delivery to a receiver without an `enc_key` | receiver 400 |
| Client without HPKE support facing a card with an `enc_key` | client, discovery (`encryption_unavailable`). It never downgrades |
| `require_confidentiality=True` facing a card without an `enc_key` | client, discovery (`no_confidentiality_key`) |
| Encrypted receipt tampered in transit | client `unverified_receipt` (the effect already committed) |

**Red-green evidence (issue #19).** I temporarily removed `admission_id` from the HPKE transcript, and the `admission_id` subtest of `test_hpke_transcript_mismatch_rejected` failed in both HPKE classes. Restoring the code made all tests pass again.

**Red-green evidence.** I temporarily deleted the in-transaction grant recheck in `AuthorizedEffectGateway.commit`, and six tests failed: the revocation, expiry and concurrent-race tests in both modes. I temporarily disabled the client's identity and endpoint binding, and four tests failed. Restoring the code made all tests pass again.

## Sanitized denial trace (captured from `python -m agent_movement.peer_demo`, HS256, 2026-10-16)

The receiver persists only these fields. It never stores task text, salts, signatures or key material:

```json
{"seq": 3, "stage": "preflight", "outcome": "denied", "reason": "bad_signature",   "movement_id": "mv-fake-sender",         "peer": null,      "claimed_peer": "agent-a", "admission_id": null}
{"seq": 4, "stage": "preflight", "outcome": "denied", "reason": "wrong_actor",     "movement_id": "mv-insider-wrong-actor", "peer": "agent-c", "claimed_peer": "agent-c", "admission_id": null}
{"seq": 5, "stage": "preflight", "outcome": "denied", "reason": "grant_expired",   "movement_id": "mv-expired-grant",       "peer": "agent-a", "claimed_peer": "agent-a", "admission_id": null}
{"seq": 7, "stage": "preflight", "outcome": "denied", "reason": "grant_revoked",   "movement_id": "mv-revoked-grant",       "peer": "agent-a", "claimed_peer": "agent-a", "admission_id": null}
{"seq": 8, "stage": "preflight", "outcome": "denied", "reason": "wrong_audience",  "movement_id": "mv-wrong-audience",      "peer": "agent-a", "claimed_peer": "agent-a", "admission_id": null}
{"seq": 9, "stage": "preflight", "outcome": "denied", "reason": "wrong_task",      "movement_id": "mv-wrong-task",          "peer": "agent-a", "claimed_peer": "agent-a", "admission_id": null}
{"seq": 12, "stage": "delivery", "outcome": "denied", "reason": "grant_revoked",   "movement_id": "mv-revoked-in-flight",   "peer": "agent-a", "claimed_peer": "agent-a", "admission_id": "adm-…"}
```

The fake-receiver and unsupported-schema scenarios produce **no receiver trace at all**, because the sender aborted at discovery and nothing reached agent-b. Instead they appear in the sender-side trace (`PeerClient.trace`) as `discovery / aborted / bad_card_signature` and `unsupported_schema`, with `payload_sent: false`. In both the HS256 and Ed25519 runs, the demo reported `task_canary_on_wire: false` for every scenario that was denied before delivery, `provider_canary_on_wire: false` for every scenario, and `task_canary_in_receiver_db: false`.

## Trust assumptions (explicit)

1. The test CA and user-authority verification keys are **pinned out of band** before any exchange. Nothing about trust is learned from a peer.
2. In HS256 mode, peer verification keys are provisioned out of band by the test CA. Every participant holding a key is trusted not to sign with it (outsider model only).
3. Private keys stay in process memory, or in the demo's temporary 0600 provisioning file. There is no HSM, rotation, key revocation or card revocation list.
4. The receiver's SQLite file and clock are trusted. Expiry uses the receiver's wall clock with an allowed preflight skew of 120 s.
5. Revocation notices are **pushed** by the user authority and applied synchronously. There is no status list or introspection pull.
6. The loopback network carries no confidentiality or integrity protection: **no TLS and no channel binding**. In HPKE mode, the delivery body and receipt are end-to-end encrypted to the receiver's card key. Everything else stays readable: discovery, the preflight (task kind, classification, IDs, cards, the grant) and the admission.
7. The receiver's X25519 private key is held only by the receiver process (in the demo, inside the same 0600 provisioning file). Whoever holds it can read every delivery sealed to it.
8. Task kinds are pure functions, and the "external effect" is a row in a local SQLite table.

## Limitations (documented, not solved)

- **On-path relay: closed for the payload in HPKE mode only.** An attacker who controls the *real endpoint address* can still relay every message verbatim. In HPKE mode it sees only ciphertext of the task and the receipt (`test_on_path_relay_sees_only_ciphertext_with_hpke`). Some gaps remain in every mode:
  - **Plaintext mode has no confidentiality.** The same test shows that the relay reads the text there.
  - **The relay can still observe and disrupt.** It sees all preflight metadata, and the ciphertext length reveals the approximate text length, because there is no padding. It can also drop or delay messages.
  - **No forward secrecy against the receiver's static key.** HPKE base mode uses a fresh ephemeral key per delivery, but anyone who later obtains the receiver's X25519 private key can decrypt recorded deliveries.
  - **No key rotation or revocation.** Neither the encryption key nor the signing key can be rotated or revoked.
  - **Library, not a certified HPKE.** The suite comes from `cryptography`'s HPKE implementation, which this repository has only checked against one RFC 9180 test vector. It has not been audited here.
  - **Not TLS.** This is not mTLS or TLS channel binding (e.g. [RFC 9266](https://www.rfc-editor.org/rfc/rfc9266)).
  - **Misdirection.** As before, misdirection to an endpoint that the destination card does not name is prevented in both modes.
- **Replay.** Each preflight nonce is single-use for each origin. Nonces are pruned after 2× the skew window, and stale `issued_at` values are rejected, so replay is impossible outside the window. Inside the window, an observer who copied a preflight can replay it to the real receiver once. That creates an orphan admission and consumes the grant's use for that movement, but it cannot be completed without the origin's key. The genuine origin can still finish the same movement with a preflight retry, which is re-admitted without consuming another use. An identical delivery can be replayed while its admission is valid, but it is idempotent (`replayed: true`, effect `replayed`). Signed receipts can be replayed as evidence. They are bound to an admission ID, not to a verifier challenge.
- **Cancellation.** There is no cancel operation. Revoking the grant is the only way to stop a transfer. It prevents *future* deliveries and effect commits but does not undo a committed effect. An admission that is never used simply expires (TTL ≤ 60 s, also capped by grant and card expiry).
- **Partitions.** A receiver that is cut off from the user authority never learns about a revocation and keeps honouring the grant until `expires_at`. The bound is therefore the grant lifetime, so keep grants short. A sender that loses the receipt cannot tell whether the effect committed. It can retry the identical delivery within the admission TTL and get the idempotent answer. After that, the outcome must be reconciled out of band. There is no `unknown` lifecycle state for a peer handoff yet.
- **Revocation races.** These are linearized **only inside this receiver's SQLite database**: a revocation that commits first always wins at the effect gateway. Three gaps remain:
  - A revocation that lands between admission and delivery still lets the text cross the wire. It is then refused and not persisted. In HPKE mode only ciphertext crosses, and the receiver decrypts it only after its admission checks pass. The grant recheck comes *after* decryption, so the receiver process does briefly hold the text in memory.
  - A revocation that arrives after commit does not undo the commit.
  - A real third-party tool would need the same check *on its own side* of the boundary.
- **Retention.** The receiver keeps the following data **with no expiry or deletion API**:
  - **`peer_admissions` rows:** the origin card and the full signed grant.
  - **`peer_trace` and `authority_log` rows.**
  - **Core `audit_events` and `deliveries` rows.** These pre-date this work. `audit_events.info_digest` is an *unsalted* SHA-256 over the full envelope, and the `sha256` task kind stores the hash of the text as its result. Both let an observer confirm guesses about low-entropy text. Only nonces are pruned.
- **Other.**
  - No card revocation or key rotation.
  - Clock skew is assumed small.
  - Preflight verification costs CPU before authentication succeeds, so DoS is not addressed.
  - Grant uses are counted per receiver database and consumed at admission. See [Grant uses and retries](#grant-uses-and-retries-issue-29) for what that leaves open.
  - In HS256 mode, any verifier could forge cards and messages.
  - The peer protocol and A2A message framing are separate. An official A2A adapter remains a different issue.

## Code map

- `src/agent_movement/trust.py`: keys (HS256/Ed25519), domain-separated sealing, `TrustStore`, agent cards (with the optional signed `enc_key`), grants, revocation notices and commitments. It also holds the HPKE pieces: `HpkeKey`, `delivery_info` (the transcript) and `seal_response`/`open_response`.
- `src/agent_movement/peer.py`: `PeerReceiver` (preflight/delivery/revocation, plus opening sealed deliveries), `PeerClient` (discover → preflight → deliver, the disclosure guard and the no-downgrade rule), `DeliverySeal`, `PeerLedger` (nonces, admissions, grant uses, revocations, sanitized trace), `AuthorizedEffectGateway` (grant recheck at commit), and in-process, HTTP and recording transports.
- `src/agent_movement/peer_http.py`: loopback-only HTTP wrapper and a provisioning-file entry point (with an optional `enc_key`).
- `src/agent_movement/peer_demo.py`: two-process demo with captured sanitized traces (`--delivery auto|plaintext|hpke`).
- `tests/test_peer.py`: the negative tests above, loopback HTTP runs in both delivery modes, and the RFC 9180 known-answer test.
- `tests/test_grant_uses_and_sender_keys.py`: issue #29. It covers per-sender idempotency keys and the store migration, and counted grants in the HS256/plaintext and Ed25519/HPKE modes, under thread and process concurrency.
