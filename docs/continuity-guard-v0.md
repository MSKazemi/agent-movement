# Continuity Guard v0.1: synthetic admission research

**Date:** 2026-10-16. **Status:** experimental, standard-library-only *decision function*, **not** a production security system, trusted authorization service, enforcement gateway, mobility protocol, or human-subjects usability study. All example approvals, observations and effects are synthetic.

This is the first executable slice of the [underexplored-dimensions research proposal (PR #83)](https://github.com/MSKazemi/agent-movement/pull/83). It addresses **multiple legitimate principals, obligation continuity, material agent configuration changes, contaminated-state quarantine and context freshness**. It does not purport to solve the other nine research gaps or any general cross-runtime portability problem.

## Run it

From the repository root, with Python 3.11+ and `pytest` installed:

```sh
PYTHONPATH=src python -m agent_movement.continuity_guard_demo
PYTHONPATH=src python -m pytest -q tests/test_continuity_guard.py
```

The demo contains a **frozen 10-case synthetic decision oracle**: one expected allow and nine expected refusals. It prints deterministic JSON, including per-case reasons and oracle matches. The test module checks approvals, disagreement, revocation, expiry, audience/scope binding, weakened duties, stale/poisoned state, configuration drift, freshness, malformed inputs and an admission-to-effect recheck. Neither suite performs real movement, authenticates a person, executes tools or proves security against an uncooperative executor. The fixed clock and digest strings are public fixtures, not credentials.

## Boundary model

The API in [`continuity_guard.py`](../src/agent_movement/continuity_guard.py) separates **three inputs with different provenance**:

| Input | Owner | Must come from | What it contains |
| --- | --- | --- | --- |
| `Proposal` | Agent/requesting application (untrusted) | Parsed/validated request | Destination, requested scopes, epoch, declared config digest, proposed duties |
| `Policy` | Independent policy administrator | Trusted configuration store | Required principals, allowlisted destinations/scopes, inherited duties, approved config digest, required observations, policy epoch |
| `ObservedFacts` | Independent enforcement/verifier adapters | Actual verified observations (not the proposal) | Per-principal verified scoped grants, receiver acceptance reference digest, independently measured config, admission state, time-stamped evidence |

`evaluate(proposal, policy, facts, now=trusted_clock)` returns a `Decision(allowed, reasons)`. An empty set of mandatory principals **cannot** silently mean permission. Each explicitly required principal must have **one** verified, non-revoked, in-scope and unexpired grant for the destination, policy epoch and *every* requested scope. Combining partial grants via their union is forbidden. Duplicate/ambiguous grant records are refused. Missing/unknown/malformed input is refused.

**Crucial limitation:** this code does not verify cryptographic signatures or source identity. The `verified` boolean and `recipient_ack_digest` must be established by an *independent trusted adapter* before constructing `ObservedFacts`; they **must never** be copied from requester-controlled JSON. The SHA-256 obligation digest is a public fingerprint, not a signature, not a receipt, and not evidence of recipient compliance. A caller that trusts arbitrary input can bypass every check.

## Obligations that may not silently weaken

`Obligations` currently includes:

- `retain_until`: absolute Unix second cutoff; an earlier deadline is stricter, and an already expired deadline denies movement.
- `allow_onward`: a previous prohibition on delegation cannot become permission in the next hop.
- `audit_required`: an inherited audit requirement cannot be removed.
- `notify_user`: an inherited notification requirement cannot be removed.

The proposed duties must be **at least as restrictive** as the inherited `Policy` duties. The out-of-band verified recipient acceptance must bind **the exact recipient, scopes, policy epoch, declared configuration and proposed duties** through `obligation_ack_digest`. Changing any one produces a different digest and requires a new, independently verified acknowledgment.

**Acknowledgment is not enforcement.** The prototype cannot guarantee deletion at the cutoff or prevent a malicious recipient from storing private data. Actual retention/delete controls and independent proof are separate future work; see the existing [data retention study](data-retention.md).

## Change and freshness gates

A policy-pinned manifest digest, the proposal's declared digest, and a separately measured runtime/configuration digest must match. This catches declared or observed *material configuration changes* in the **synthetic model**. It is not secure boot, remote attestation, supply-chain assurance, or proof that an LLM is safe.

If the externally recorded checkpoint admission state is `suspect`, `quarantined` or `unknown`, movement is refused. A signed or hash-matching checkpoint can still contain poisoned content, and `eligible` means only that the independently operated admission process cleared the test policy. No automated decontamination is claimed.

Every required observation (for example, a simulated dataset generation or sensor status) must be present, independently verified, observed no later than the trusted clock and not expired. Missing, duplicate, future or stale evidence fails closed. Rechecking at a later time can reverse an earlier allow decision.

## A human-facing approval preview (not a consent interface)

`approval_preview(proposal, policy)` returns a bounded, machine-readable overview of the proposed destination/scopes, mandatory approvers, requested retention and notification requirements, plus an explicit statement that approval cannot undo already executed effects. The preview always includes `preview_only_not_authorized`: **showing it never grants authority**. Comprehension, consent fatigue, accessibility and real operator decision quality remain unmeasured.

## Demonstrated invariants and unproven properties

| Synthetic invariant | Test evidence | What is **not** established |
| --- | --- | --- |
| All mandated principals must approve | One missing/revoked/expired/wrong-audience grant refused | Which principals legally must approve a real transfer |
| Every requested scope needs each mandatory owner's permission | Per-principal scope-subset negative tests | Authorization beyond an independently mediated effect gateway |
| Duties cannot be weakened and acknowledgement binds recipient/config/epoch | Obligation mutation and digest-binding tests | Recipient actually retaining, deleting or notifying as promised |
| Material manifest change and suspect state refuse admission | Runtime-drift, poisoned-state negative tests | Code/model safety, honest host attestations, removal of malicious state |
| Evidence used after its validity window is refused | Expired/future/duplicate/absent observation tests | Real-world clock correctness or accuracy of independently observed facts |
| Earlier allow is not durable permission | Revocation and time-advance reevaluation tests | Atomic check-and-effect, revocation of uncooperative or offline agents |

## Next implementation requirements before claims about enforcement

1. Define and independently authenticate principal roles, actual consent/grant lifecycle and data-owner authority. Make all grants source-bound and time/epoch-checked by a real verifier.
2. Implement an independently controlled policy/enforcement point **before disclosure**, and re-evaluate atomically at every synthetic effect sink. The evaluator alone does not stop code from calling a tool elsewhere.
3. Persist a receiver-side, identity-verified obligation acceptance and independently enforce bounded retention, required notices, audit and onward-transfer restrictions. Handle receiver refusal and unknown outcomes.
4. Define canonical signed configuration manifests, pin material-change epochs and test malicious runtime assertions and key compromise.
5. Extend MobilityBench with explicit frozen multi-owner, quarantine and freshness fixtures plus baseline keep/restart/delegate/relocate comparisons, not just synthetic admission checks.
6. Subject a real human approval UX to accessible comprehension/usability studies under a suitable ethics and privacy plan.

**Overlap with existing work:** do not confuse this module with the movement-policy research in [PR #16](https://github.com/MSKazemi/agent-movement/pull/16) or the independent enforcement integration tracked in [issue #50](https://github.com/MSKazemi/agent-movement/issues/50). This module provides a **complementary typed research condition**, not a second authoritative runtime policy gateway. Reconcile schemas and trust provenance before integrating the two.
