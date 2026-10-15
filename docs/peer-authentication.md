# Peer authentication and pre-disclosure authorization (synthetic, local)

**Status:** Tested experimental software for [issue #8](https://github.com/MSKazemi/agent-movement/issues/8). **Synthetic test keys only. Not A2A, not OAuth/RFC 8693, not a PKI, not production-secure.** It builds on the [local proof of concept](local-implementation.md) and the [threat model](security-and-trust.md).

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
| **User authorization** | A grant signed by a **separate** synthetic user authority. Fields: `subject` (user), `actor` (origin agent), `audience` (destination agent), `task_id`, `capabilities`, `classification`, `not_before`/`expires_at`, plus revocation | The user authority key, pinned by the receiver | That the user understood the task. It is a synthetic stand-in for a consent step |

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
 |                                   nonce single-use      -> else 400/401/403/409
 |  <---------------- admission [signed by agent-b key]: echoes client_nonce,
 |                    preflight digest, destination, short expiry
 |  verify admission with the key in the card       -> else ABORT (no text sent)
 |  (3) POST /v0/deliveries [signed by agent-a key] -------->  | task text + salt
 |                                   same peer as admitted, admission not expired,
 |                                   commitment matches, grant live/not revoked,
 |                                   pure computation (idempotent, SQLiteStore),
 |                                   simulated effect: grant re-verified IN the
 |                                   same BEGIN IMMEDIATE transaction as the insert
 |  <-------------------------------------- receipt [signed by agent-b key]
```

Design points:

- **Domain-separated signatures.** Each signature covers `purpose || canonical JSON`, so a card signature can never verify as a grant, an admission or a delivery.
- **Salted commitment.** The preflight binds the task (`sha256(domain || 32-byte salt || canonical(task))`) without disclosing it. A plain hash of short text could be brute-forced. The salt is sent only with the delivery.
- **Sender-constrained grant.** A stolen grant is useless without the actor's key, because every preflight and delivery must carry the actor's own signature (a proof-of-possession idea similar to DPoP).
- **Coarse errors to peers.** Peers see only `400 invalid_contract|unsupported_schema`, `401 unauthenticated`, `403 forbidden` or `409 conflict`. The precise reason goes only to the receiver's local, sanitized trace.
- **Loopback/in-process endpoints only.** Cards may name only `http://127.0.0.1:<port>` or `local://<name>`. A forged card therefore cannot point a sender at an arbitrary host (SSRF).

### Signature backends

| Mode | Dependency | Property | Use |
|---|---|---|---|
| `HS256` (default) | stdlib `hmac` | Symmetric. **Anyone who can verify a key can also sign with it.** In this mode every verifier holds the CA key and could mint cards | Outsider-attacker model only. Keeps the package and CI dependency-free |
| `Ed25519` | optional extra `pip install -e '.[ed25519]'` (`cryptography>=50.0.2`) | Asymmetric. Verifiers hold public keys only and cannot forge | Insider model. Every peer test also runs in this mode, and those tests are skipped cleanly when the extra is absent |

`cryptography` 50.0.2 was the latest stable release on PyPI when this was written: version metadata from `https://pypi.org/pypi/cryptography/json` was checked on 2026-10-16, and the release was uploaded 2026-09-30.

## Run it

~~~sh
python -m pip install -e .                 # or: pip install -e '.[ed25519]'
python -m pytest -q
python -m agent_movement.peer_demo         # add --alg Ed25519 with the extra installed
~~~

The demo starts `agent-b` as a **separate OS process** on loopback. It provisions that process with a per-run JSON file (mode 0600, in a temp directory that is deleted afterwards) written by the parent, which plays the test CA and the user authority. A rogue-CA "agent-b" impostor runs on a second port. The demo exits non-zero if any denied scenario carried the task canary or a delivery request, if any scenario carried the provider canary, or if the task canary appears in the receiver's SQLite files.

## Negative tests (`tests/test_peer.py`)

Every row in `PeerAuthTests` runs twice, once with `HS256` and once with `Ed25519`. "Before disclosure" means that the recorded transport has **no `/v0/deliveries` request** and that **no canary** appears in the wire bytes, the receiver trace, the `agent_movement.peer` log records, the core audit table, or the raw SQLite/WAL files.

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
| Capability not allowlisted | client (not advertised) **and** receiver (`capability_not_allowlisted`) | yes |
| Unsupported schema | client (not advertised) **and** receiver 400 `unsupported_schema` | yes |
| Preflight addressed to another endpoint (relay to the real receiver) | receiver 403 (`wrong_destination`) | yes |
| Delivery signed by a different peer / not matching the commitment / without an admission | receiver 401 / 403 / 403 | text sent by the attacker's own choice. **Not persisted or logged** |
| Revocation **between admission and delivery** | receiver, delivery 403 (`grant_revoked`) | **no, this is a documented window.** Text was sent, then neither executed nor persisted |
| Revocation / expiry **between delivery and effect commit** | effect gateway, same transaction (`effect_grant_revoked` / `effect_grant_expired`) | no effect recorded |
| Concurrent revocation vs. 8 parallel commits | `authority_log` shows every committed effect sequenced **before** the revocation | linearized |
| Provider token canary placed in the task text | sender guard `DisclosureBlocked` before any POST | yes |

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
6. The loopback network carries no confidentiality or integrity protection: **no TLS and no channel binding**.
7. Task kinds are pure functions, and the "external effect" is a row in a local SQLite table.

## Limitations (documented, not solved)

- **On-path relay / no channel security.** An attacker who controls the *real endpoint address* can relay the preflight and admission verbatim and then read the delivered text. `test_limitation_on_path_relay_sees_payload_without_channel_security` demonstrates this on purpose. The defences are mTLS with keys bound to the card (TLS channel binding, e.g. [RFC 9266](https://www.rfc-editor.org/rfc/rfc9266)) or encrypting the delivery to the card's key (for example HPKE). Neither is implemented. What *is* prevented is misdirection to an endpoint that the destination card does not name.
- **Replay.** Each preflight nonce is single-use for each origin. Nonces are pruned after 2× the skew window, and stale `issued_at` values are rejected, so replay is impossible outside the window. Inside the window, an observer who copied a preflight can replay it to the real receiver once. That creates an orphan admission and burns the movement ID (squatting/DoS), but it cannot be completed without the origin's key. An identical delivery can be replayed while its admission is valid, but it is idempotent (`replayed: true`, effect `replayed`). Signed receipts can be replayed as evidence. They are bound to an admission ID, not to a verifier challenge.
- **Cancellation.** There is no cancel operation. Revoking the grant is the only way to stop a transfer. It prevents *future* deliveries and effect commits but does not undo a committed effect. An admission that is never used simply expires (TTL ≤ 60 s, also capped by grant and card expiry).
- **Partitions.** A receiver that is cut off from the user authority never learns about a revocation and keeps honouring the grant until `expires_at`. The bound is therefore the grant lifetime, so keep grants short. A sender that loses the receipt cannot tell whether the effect committed. It can retry the identical delivery within the admission TTL and get the idempotent answer. After that, the outcome must be reconciled out of band. There is no `unknown` lifecycle state for a peer handoff yet.
- **Revocation races.** These are linearized **only inside this receiver's SQLite database**: a revocation that commits first always wins at the effect gateway. Three gaps remain:
  - A revocation that lands between admission and delivery still lets the text cross the wire. It is then refused and not persisted.
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
  - Grants can be reused for several movements of the *same* task until expiry. There is no use counter.
  - In HS256 mode, any verifier could forge cards and messages.
  - The peer protocol and A2A message framing are separate. An official A2A adapter remains a different issue.

## Code map

- `src/agent_movement/trust.py`: keys (HS256/Ed25519), domain-separated sealing, `TrustStore`, agent cards, grants, revocation notices, commitments.
- `src/agent_movement/peer.py`: `PeerReceiver` (preflight/delivery/revocation), `PeerClient` (discover → preflight → deliver, plus the disclosure guard), `PeerLedger` (nonces, admissions, revocations, sanitized trace), `AuthorizedEffectGateway` (grant recheck at commit), and in-process, HTTP and recording transports.
- `src/agent_movement/peer_http.py`: loopback-only HTTP wrapper and a provisioning-file entry point.
- `src/agent_movement/peer_demo.py`: two-process demo with captured sanitized traces.
- `tests/test_peer.py`: the negative tests above, plus a loopback HTTP run.
