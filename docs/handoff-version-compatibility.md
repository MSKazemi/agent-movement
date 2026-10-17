# Handoff envelope compatibility decision (issue #96)

**Decision date:** 2026-10-17. **Status:** implemented *narrow conversion helper*, not a new wire protocol or an authorization system.

## Decision: preserve the deployed 0.1 runtime; allow only explicit, loss-intolerant 0.2 projection

There are two independent version concepts:

- **Runtime handoff envelope:** `core.SCHEMA_VERSION == "0.1.0-draft"`. The real `core.validate_envelope`, legacy localhost HTTP handler, synthetic authenticated peer receiver and A2A SDK adapter use this **one strict 11-field shape**. It permits a pure `delegate` of `word_count` / `sha256` over `synthetic` / `public` data. This has **not** been bumped to 0.2.
- **Canonical proposed envelope:** `schemas/handoff-envelope.schema.json` documents `"0.2.0-draft"`, with optional portability/context/authority fields and conditional checkpoint-relocation requirements. It remains **documentation/schema only**; those optional fields, `relocate`, and additional classifications are not implemented in the 0.1 runtime.
- **A2A extension profile:** `a2a_profile.PROFILE_VERSION == "0.2.0-draft"` is a **different** version namespace. Its `Message.metadata.schema_version` still reflects the **runtime** envelope version, 0.1. A new A2A extension URI does not imply 0.2 envelope support.
- **Python package** version (see `pyproject.toml`) is yet another independent namespace.

We choose **explicit conversion, not silent downgrade and not automatic dual-version acceptance**. A receiver can continue requiring 0.1 without changing existing wire fixtures, receipts, digests, idempotency keys, A2A framing, or peer-authenticated grants.

## Compatibility matrix

| Sender content | Destination authenticated advertisement | Local operator option | Result |
| --- | --- | --- | --- |
| Strict 0.1 `delegate` | Includes 0.1 | irrelevant | Validate with current core; send unchanged |
| Strict minimal 0.2 `delegate` | Includes 0.1 | explicitly permit minimal conversion | Replace **only** `schema_version`; revalidate full 0.1 shape |
| Minimal 0.2 `delegate` | Includes 0.1 | conversion not enabled | **DENY** (no silent downgrade) |
| Canonical 0.2 with any extra member at any level | Includes 0.1 | enabled | **DENY**, never discard fields |
| Canonical 0.2 `relocate` or unsupported task/data class | Includes 0.1 | enabled | **DENY**, even if shape otherwise matches |
| Strict 0.1 or minimal 0.2 | Only 0.2 or unknown versions | enabled | **DENY**; no deployed receiver implements 0.2 |
| Unknown version or incomplete/malformed advertisement | any | enabled | **DENY** |

The proposed 0.2 Schema intentionally allows broader shapes than the deployed runtime. **Do not** mark a broader shape as compatible just because a schema validator accepts it.

## Field-by-field crosswalk

Only these exact 11 top-level 0.2 minimal-profile members can be projected to the 0.1 runtime; every value is preserved byte-for-byte at its logical field (although canonical serialization changes its version marker).

| Canonical 0.2 member | Runtime 0.1 member | Rule |
| --- | --- | --- |
| `schema_version` | `schema_version` | **Only rewritten field:** 0.2.0-draft -> 0.1.0-draft |
| `movement_id` | `movement_id` | Preserve |
| `logical_task_id` | `logical_task_id` | Preserve |
| `operation` | `operation` | Must be `delegate`; `relocate` refuses |
| `origin.agent_id` | `origin.agent_id` | Preserve as a *claim*, not identity proof |
| `destination.agent_id` | `destination.agent_id` | Preserve as a *claim*, not destination authentication |
| `task.kind`, `task.text` | same | Require exact members; only core's two pure task kinds; text <= 2048 **UTF-8 bytes** |
| `context.classification` | same | Only `synthetic` and `public` |
| `authority.approval_ref` | same | Required reference; a separate authorization mechanism still verifies it |
| `execution.idempotency_key` | same | Preserve; no implicit retry or grant issuance |
| `observability.trace_id` | same | Preserve; correlation is not authentication |

Canonical-only `parent_movement_id`, `requirements`, `message`, `integrity`, `origin.execution_id`, `destination.endpoint_id`, `task.goal`, `task.deadline`, `context.purpose`, `context.artifact_refs`, `authority.grant_ref`, `authority.expires_at`, `authority.delegation_depth`, `execution.checkpoint_ref`, `execution.fencing_epoch`, execution budgets, `observability.traceparent`, and all other expanded fields are **rejected if present**, even if null. No authority/approval/trust claims are inferred.

## Integration API (stdlib-only)

```python
from agent_movement.envelope_compat import prepare_handoff

prepared = prepare_handoff(
    candidate_canonical_minimal_envelope,
    receiver_versions=("0.1.0-draft",),  # from an AUTHENTICATED destination descriptor
    allow_minimal_conversion=True,      # from independent/operator-controlled policy
)
wire = prepared.envelope
assert prepared.wire_version == "0.1.0-draft"
```

The caller must **not** trust a self-reported agent version array. It must derive `receiver_versions` from independently authenticated discovery and require a higher-level authority for the explicit conversion. The adapter **does not** verify signatures, credentials, approval, sender identity, human intent or policy; retain independent `PeerReceiver` preflight/delivery/effect validation. Avoid translating signed grants or receipts based only on the version string.

For traceability, `PreparedHandoff.source_digest` is the hash of the **original candidate**, while `wire_digest` is the hash of the converted wire envelope. They differ for 0.2->0.1 conversion. Persist both with a **trusted mapping assertion** if an application needs cross-version audit; do not relabel a wire digest as a source digest. Replacing a version in an already signed serialized envelope invalidates its signature: conversion must precede any envelope signing/commitments.

The A2A adapter's mapping can be used on the resulting **strict 0.1** `wire`; it must still reject an unconverted 0.2. The peer path uses the existing separate signed grant, which this conversion deliberately does not alter. The existing `relocation.py` remains a distinct application-specific checkpoint prototype, not a 0.2 envelope receiver.

## Reproducible tests

```sh
python -m pip install -e . pytest
python -m pytest -q tests/test_envelope_compat.py tests/test_handoff_envelope_schema.py tests/test_a2a_profile.py tests/test_peer.py
```

Positive controls assert core and A2A roundtrip for 0.1 and **opt-in minimal** 0.2 conversion. Negative controls cover unsupported versions, receiver advertisements, opaque optional members, relocation, wrong classification/kind, invalid text, and no silent mutation of the source. Existing peer and A2A tests continue to enforce 0.1 at ingress. The suite **does not prove** actual cross-framework portable resume, cryptographic issuer security, lossless 0.2 relocation, or production policy enforcement.

## Why this is the safe choice

- A single runtime contract remains the implementation source of truth.
- Semantic-loss refusal makes any expanded 0.2 field a deliberate engineering decision instead of a silently discarded user constraint.
- The signed/verified runtime admission and effect layers remain responsible for authority, not the envelope adapter.
- More capable 0.2 transport can be developed in a separate, versioned implementation and introduced through authenticated capability negotiation with its own conformance tests.

**Follow-up to #50:** A secure-test deployment needs operator-owned version allowlists and comprehensive enforcement across all enabled transports; this syntactic bridge alone does not provide that boundary.
