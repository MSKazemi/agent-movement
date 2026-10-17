# Continuity Runtime v0.1: bounded enforcement for the peer experiment

**Reviewed:** 2026-10-16. **Status:** Experimental enforcement for one explicitly opted-in synthetic peer receiver. **Not** a host sandbox, confidential network gateway, production authorization system or proof of complete mediation. This extends the [decision-only Continuity Guard](continuity-guard-v0.md) and the [peer handoff prototype](peer-authentication.md).

## Verified control boundaries

The new Python module, src/agent_movement/continuity_runtime.py, is attached to the existing authenticated peer receiver only when explicitly provisioned.

1. **Preflight, before task text is sent:** the existing receiver verifies the origin peer signature and user grant. The continuity profile then requires independently signed, task/movement-scoped consents from every mandatory principal, an explicitly installed receiver-signed acknowledgment, a pinned policy epoch, a local manifest measurement, eligible admission state and fresh independently signed observations. Missing or forged facts deny the admission.
2. **Delivery:** the receiver re-verifies the signed request/grant and stored admission epoch and rechecks current continuity facts. A revocation, changed policy, quarantine or manifest drift may deny the delivered task. **Task bytes may already have been transmitted** when denial occurs here.
3. **Simulated effect commitment:** the existing SQLite AuthorizedEffectGateway requires a stored admission whose task/movement/grant/effect route matches the request, and it rechecks continuity facts **inside the same BEGIN IMMEDIATE transaction** that records a simulated effect. A revocation or policy epoch change committed before this transaction wins.

The existing peer protocol continues to verify its own grant, identity and scope. This addition does not replace those checks.

## Trusted sources of facts

- **Principal approval:** each mandatory principal has a *different pinned verifier key*. An independent signed consent binds principal, destination, scope, policy epoch, task ID, movement ID and expiry. Signed revocations persist as tombstones and are serialized against effect commits.
- **Acknowledgment:** the destination key signs its acceptance of the exact policy/obligation digest for a movement, task and capability. This authenticates an acknowledgment, **not actual downstream compliance**.
- **Observation:** a separately pinned issuer signs source time, validity end time and task/movement identity. The runtime re-verifies signature and freshness at each guarded stage.
- **Manifest:** a trusted receiver-operator-provided measurement callback is re-evaluated at the boundary. A manifest digest is **not** remote attestation and does not prove the receiver host is honest.
- **Policy and admission state:** the receiver operator provisions the policy and a pinned digest. State defaults to unknown and requires explicit operator clearance to become eligible. Policy epoch increases invalidate old authority. State and epoch mutations use the same SQLite write lock as protected effects.

The signer verification is deliberately independent of the untrusted agent task envelope: the agent cannot supply its own validated=True flag. Synthetic HS256 keys in tests are shared secrets; they are not a suitable basis for independently administered real organizations.

## Focused checks

~~~sh
python -m pip install -e . pytest
python -m pytest -q tests/test_continuity_runtime.py tests/test_continuity_guard.py tests/test_peer.py
~~~

The new deterministic cases include admitted/replayed handoffs, missing/forged/wrong-task/wrong-scope/expired consent, missing or altered acknowledgment, stale observation, configuration drift, quarantine, policy epoch rollover, revocation between stages, direct/unadmitted effect gateway calls, tampered stored signatures and attempts at non-peer receiver routes.

**Bounded research claim:** within the *enabled and explicitly provisioned peer receiver and simulated SQLite effect interface*, a protected effect cannot commit if the required consent, obligation acknowledgment, freshness, configuration or active-epoch conditions are false at effect-commit time, under the stated trusted-host/ledger assumptions. Test results do not establish global agent containment.

## Opt-in runtime contract

The operator builds a ContinuityRuntime over the **same** SQLiteStore and pins a Policy, principal verifiers, observation verifiers, recipient verifier and trusted manifest measurer. No external HTTP request can install or modify these facts. The operator explicitly installs verified evidence and sets admission state eligible before receiving task data.

~~~python
PeerReceiver(card, receiver_key, trust, store, ["word_count"],
             continuity=continuity_runtime, secure_test_mode=True)
~~~

The secure_test_mode flag fails constructor validation without a bound continuity authority. It does **not** globally disable other Python modules or independently hosted servers. See tests/test_continuity_runtime.py for the complete synthetic setup and signed evidence fixtures.

## Open security and operational gaps

Issue [#50](https://github.com/MSKazemi/agent-movement/issues/50) **remains open**:

- Legacy HTTP, A2A, relocation, arbitrary tools and additional network listeners are separate routes: not globally disabled or automatically gated. This work protects only its opted-in peer receiver, not an arbitrary device or fleet.
- No OS sandbox, separate attacker process with independently controlled egress, real production tool-side enforcement or globally complete audit. A hostile process with SQLite write privileges or arbitrary receiver-code execution can bypass this test model.
- The normal sender does not independently collect all third-party consents. It waits for the signed receiver preflight before sending task text, but a dishonest sender can still disclose data to an unauthorized endpoint.
- Retention, audit and notification **duties** are required in the contract but not proved fulfilled or propagated to other organizations. Revocation cannot undo effects that already committed.
- No general strong attestation, cross-system exactly-once promise or independent verification of every authorized task result. A result-effect ID constraint does not prove the result payload is correct.
- Without HPKE, the peer delivery transport is plaintext. No reliance on TLS or protected external network is implied.
- The provisioning methods are trusted local operator interfaces; peer_http.load_receiver does not yet expose a secure external provisioning process or authenticated management plane.
- Need to reconcile the importable policy contract with [PR #16](https://github.com/MSKazemi/agent-movement/pull/16), add sender-side trusted policy and independently blocked alternative paths and implement red/green mutation tests under OS isolation.

The next step is a **separate unprivileged process + network gate experiment**, then cross-domain recovery, operational key rotation, verified duty fulfillment and a second independent peer implementation. No claims of production safety should precede those experiments.
