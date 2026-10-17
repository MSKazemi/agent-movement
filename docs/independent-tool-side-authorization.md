# Independent tool-side authorization lab (Issue 102)

**Date:** 2026-10-17. **Status:** Synthetic, opt-in, localhost-only experiment. Requires the optional Ed25519/cryptography dependency. Not production security; not a guarantee of exactly-once external effects or host compromise containment.

## Research question

Can an independently operated simulated tool deny an unauthorized agent action even if the agent bypasses its normal client and calls the tool endpoint directly?

The [human-impact research questions](top-20-human-impact-questions-for-agentic-ai.md) most directly concerned are **HQ-01** (human control), **HQ-03** (agent identity/authority), **HQ-06** (accountability), and **HQ-18** (replication and duplicate effects). This deliberately differs from the existing peer receiver, Continuity Runtime and GuardedAuthority, which enforce their policies on other bounded local paths.

## Trust boundary and state

~~~text
Operator signing key ------signed enrollment/transfer/cancel/policy--\
Issuer signing key --------signed grant/revocation-------------------> [TOOL PROCESS]
Destination worker key ----signed activation and simulated effect----/     |
 (untrusted caller may bypass the official agent client)                  |
                                                   verify scope/epoch/grant/policy
                                                   activation/budget/revocation
                                                   in one BEGIN IMMEDIATE transaction
                                                                          |
                                                       [TOOL-OWNED SQLite ledger]
                                                       [TOOL-signed receipt]
~~~

The tool runs in a **separate OS process** with its own SQLite file and receipt signing key. It has **pinned public Ed25519 verifiers** for the operator, issuer and workers, provided outside the request. A client cannot supply a new trusted issuer, claim that approval is true, or write an effect via this service without the server enforcing current facts. Sender, issuer and service identities are distinct; signatures authenticate **test keys**, not the internal software or human intention.

**Critical OS limit:** Under the test harness the server and clients normally share the same local UID. An attacker capable of reading the server provisioning file or writing its SQLite database might bypass these checks. This is **application/process separation**, not a separately privileged sandbox. That OS-boundary work is tracked in [Issue 98](https://github.com/MSKazemi/agent-movement/issues/98).

## Typed protocol and authoritative decisions

The module is src/agent_movement/tool_authority.py. It exposes four localhost-only POST routes (body up to 16 KiB), all using version 0.1.0-tool-lab:

| Route | Trusted signer | Meaning |
| --- | --- | --- |
| /v0/tool/control | Operator for enrollment, transfer, cancellation, unknown hold and policy rollover; issuer for revocation | Mutate the tool's trusted authority facts, with unique event IDs |
| /v0/tool/activate | Pinned destination worker | Sign a grant-bound readiness request before any protected effect |
| /v0/tool/effect | Pinned destination worker | Attempt only the synthetic increment effect with tool-side grant, actor, owner, epoch, phase, policy, budget and revocation checks |
| /v0/tool/reconcile | Pinned worker | Signed committed/unknown result for a specific effect ID |

The grant is signed by the issuer and binds actor, audience independent-tool, task, movement, action increment, resource synthetic-counter, synthetic classification, expiry, policy epoch and budget. The destination's signed activation has its own shorter expiry, stored by the tool and **rechecked on every simulated effect**; activation never automatically renews. The operator enrolls its digest and an independent maximum budget. Even a valid worker signature is insufficient without the issuer grant and current tool-owned authority state.

~~~text
UNENROLLED
   -> operator enrolled -> PREPARED (A, epoch 1)
   -> operator fencing transfer CAS -> FENCED (B, epoch 2)
   -> B signed activation + verified grant -> ACTIVE
   -> B signed effects -> ACTIVE, bounded by shared budget
   -> operator signed cancel/unknown -> CANCELLED/UNKNOWN (deny effects)
   -> operator policy epoch change -> FENCED (old grant no longer valid)
~~~

A transfer does **not** itself enable effects. Activation proves possession of the destination key at that moment, not real-world agent liveness or semantic continuation. [Issue 103](https://github.com/MSKazemi/agent-movement/issues/103) separately tracks the GuardedAuthority runtime activation barrier.

Every result has a domain-separated Ed25519 tool receipt. The SQLite effect ledger and signed decisions contain only limited sanitized metadata. Unauthenticated denied request IDs are excluded so synthetic confidential strings cannot be laundered into logs.

## Freshness and atomicity assumptions

- **Operator and issuer facts:** updates take effect only once valid signed controls/revocations reach and commit inside the tool's own SQLite database. This is *not distributed atomicity* with the origin system.
- **Revocation gap:** an undelivered revocation cannot be known by this tool. A short grant expiry limits, but does not eliminate, the race. This experiment never claims immediate global revocation.
- **Clock:** each instance reads server-owned Unix time. Unit tests inject a fixed clock, while the separate process tests use its real wall clock.
- **Durable local effects:** the resource is a simulated counter. Effect insert, owner/epoch, current policy, grant validity, activation, and budget are in one SQLite writer transaction. This guarantee cannot be extended to nonparticipating third-party APIs.
- **Timeouts:** after a lost acknowledgement, the client may retry the same signed request (dedup) or request reconciliation. A missing effect record is returned as **unknown**, not asserted to mean no real-world action happened.

## Falsifiable test matrix

| Scenario | Expected tool observation |
| --- | --- |
| Direct anonymous raw HTTP and forged worker signature | 401; zero committed synthetic effects |
| Forged issuer grant, wrong audience, wrong task/movement, wrong resource/action | 401/403; no effect |
| Transfer before signed destination activation | 403; no effect |
| Stale owner/epoch, changed actor or replayed conflicting activation | Denied |
| Identical signed effect request repeated or concurrently duplicated | Exactly one committed effect row, rest replayed |
| Conflicting reuse of the same effect ID with different units | 409; no extra row |
| Received issuer-signed grant revocation before effect | 403, no effect |
| Operator cancellation, unknown hold or policy epoch change | 403, no effect |
| Lost response **and hard tool-process restart** after a committed local effect | Retried identical request after restart yields a signed replay; local effect row is not duplicated; reconciliation can find committed |
| Absent local effect | Signed unknown; not proof of global absence |
| Synthetic canary in a rejected ID | No canary in decision ledger/receipt |
| **Red mutation:** remove tool-side epoch comparison temporarily in a test | Signed stale-epoch request now commits; detector confirms the unmutated check was actually necessary |

A committed effect from an unauthorized request **under the unmutated gateway** falsifies the narrow authorization claim. A duplicate effect row falsifies local idempotency. Failure to observe the deliberate red mutation makes the test ineffective.

## Reproduction

~~~sh
python -m pip install -e '.[ed25519]' 'pytest>=9.1'
python -m pytest -q tests/test_tool_authority.py
~~~

The test module launches one **real separate tool process** plus a third intentionally uncooperative client process that calls the tool endpoint directly. It checks the signed receipts and independently reads the tool's SQLite effect rows. The configuration file contains only disposable **test** keys, is created in a temporary directory with user-only permissions, and must never be committed or reused.

The service can also be started with a manually constructed *synthetic local* config:

~~~sh
python -m agent_movement.tool_authority --config /path/to/local-synthetic-config.json
~~~

It binds only 127.0.0.1 and prints its port; it never provisions trust from an incoming request. The design exposes no real payments, personal records, third-party endpoints, physical device operations or self-installation.

## Explicit limitations / remaining work

1. **No universal mediation:** this adds one new tool path. Existing A2A, peer, legacy HTTP, relocation and arbitrary OS routes are not gated by this tool. Secure-test inventory and route closure remain [Issue 99](https://github.com/MSKazemi/agent-movement/issues/99) and [Issue 50](https://github.com/MSKazemi/agent-movement/issues/50).
2. **No complete OS isolation:** a same-UID process with filesystem access may be able to read test keys or edit the tool ledger; different UID and host-controlled sandbox remain [Issue 98](https://github.com/MSKazemi/agent-movement/issues/98).
3. **No automatic GuardedAuthority bridge:** the operator must separately sign authority changes; a failed or delayed bridge leaves the tool at its last verified facts until expiry. This means operator-signed control receipt does not prove global consistency.
4. **No external truth oracle:** a signed tool receipt proves only what this simulated tool recorded; not that any real external action succeeded or was undone.
5. **No production identities/TLS/availability/rotation:** public keys are pinned in a disposable local config. A real deployment requires managed identity, key rotation, protected provisioning and stronger independent review.

The most promising next experiments are a separately privileged worker [#98](https://github.com/MSKazemi/agent-movement/issues/98), secure-profile all-path conformance [#99](https://github.com/MSKazemi/agent-movement/issues/99), and GuardedAuthority signed activation [#103](https://github.com/MSKazemi/agent-movement/issues/103).

**Related studies:** [peer authentication](peer-authentication.md), [guarded transfer](guarded-authority-transfer.md), [research agenda](human-impact-research-lab.md), [security](security-and-trust.md), [MASM](movement-authority-state-machine.md).

**Standards context:** NIST's AI Agent Standards Initiative and RFC 8032 (Ed25519), already documented in the [source index](sources.md) and [security research](security-and-trust.md).
