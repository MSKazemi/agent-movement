"""Explicit compatibility gate for the *proposal* 0.2 vs live 0.1 handoff.

No 0.2 network ingress is enabled by this module.  An operator may convert a
lossless synthetic 0.2 delegate proposal to the strict 0.1 local envelope. The
conversion refuses every 0.2-only field, relocate, privileged classification,
unverified integrity/signature reference, and unknown operation/version.

It NEVER produces or verifies identity, permission, signature or policy facts.
Those require a separately pinned verifier at the receiving effect/authority
boundary. Merely advertising 0.2 does not make a peer support it.
"""

from __future__ import annotations

import copy
from collections.abc import Sequence
from typing import Any

from .core import ContractError, SCHEMA_VERSION, validate_envelope

DRAFT_VERSION = "0.2.0-draft"
LIVE_VERSIONS = (SCHEMA_VERSION,)
PROPOSED_VERSIONS = (DRAFT_VERSION,)
_ALLOWED_FIELDS = frozenset({
    "schema_version", "movement_id", "logical_task_id", "operation",
    "origin", "destination", "task", "context", "authority",
    "execution", "observability",
})
_CHILD_FIELDS: dict[str, frozenset[str]] = {
    "origin": frozenset({"agent_id"}),
    "destination": frozenset({"agent_id"}),
    "task": frozenset({"kind", "text"}),
    "context": frozenset({"classification"}),
    "authority": frozenset({"approval_ref"}),
    "execution": frozenset({"idempotency_key"}),
    "observability": frozenset({"trace_id"}),
}


class IncompatibleContract(ContractError):
    """The operation or explicit fields cannot be represented without loss."""


def runtime_capabilities() -> dict[str, Any]:
    """Describe what is actually executable, distinct from the draft schema."""
    return {
        "runtime_wire_versions": list(LIVE_VERSIONS),
        "draft_schema_versions": list(PROPOSED_VERSIONS),
        "runtime_operations": ["delegate"],
        "draft_projection": "explicit-lossless-delegate-only",
        "automatic_downgrade": False,
        "identity_authentication": False,
    }


def negotiate_wire_version(peer_versions: Sequence[str]) -> str:
    """Return the only executable version if both endpoints explicitly offer it.

    Never return the draft version, even if both sides list it. The caller
    supplies a VERIFIED capability advertisement, not a raw untrusted claim.
    """
    if isinstance(peer_versions, (str, bytes)) or not isinstance(peer_versions, (list, tuple)):
        raise IncompatibleContract("verified peer versions must be a non-empty list or tuple")
    if not peer_versions or len(peer_versions) > 16:
        raise IncompatibleContract("invalid number of peer versions")
    if any(not isinstance(v, str) for v in peer_versions):
        raise IncompatibleContract("invalid peer version entry")
    if len(set(peer_versions)) != len(peer_versions):
        raise IncompatibleContract("duplicate peer version")
    if SCHEMA_VERSION in peer_versions:
        return SCHEMA_VERSION
    raise IncompatibleContract("no mutually executable handoff envelope version")


def project_runtime_to_draft(envelope: Any) -> dict[str, Any]:
    """Lossless *documentation-only* projection of one 0.1 envelope to 0.2.

    The returned draft envelope must not be fed directly into a receiver.
    """
    live = copy.deepcopy(validate_envelope(envelope))
    live["schema_version"] = DRAFT_VERSION
    return live


def project_draft_to_runtime(proposal: Any, *, allow_projection: bool = False) -> dict[str, Any]:
    """Explicit opt-in 0.2->0.1 projection; refuses every dropped obligation.

    A raw draft payload MUST NOT be silently rewritten at a network endpoint.
    The proposal's lack of an additional field is meaningful: the operator
    must independently verify destination identity, grant and approvals.
    """
    if allow_projection is not True:
        raise IncompatibleContract("explicit operator opt-in required for draft projection")
    if not isinstance(proposal, dict):
        raise IncompatibleContract("draft envelope must be a plain object")
    if proposal.get("schema_version") != DRAFT_VERSION:
        raise IncompatibleContract("unsupported draft envelope version")
    if set(proposal) != _ALLOWED_FIELDS:
        raise IncompatibleContract("0.2-only, missing, or unknown envelope fields cannot be projected")
    if proposal.get("operation") != "delegate":
        raise IncompatibleContract("relocate and non-delegate operations have no runtime projection")
    for field, expected in _CHILD_FIELDS.items():
        obj = proposal.get(field)
        if not isinstance(obj, dict) or set(obj) != expected:
            raise IncompatibleContract(f"draft {field} has unsupported or missing fields")
    live = copy.deepcopy(proposal)
    live["schema_version"] = SCHEMA_VERSION
    try:
        validate_envelope(live)
    except (ContractError, TypeError, ValueError) as exc:
        raise IncompatibleContract("draft values cannot be represented by the runtime") from exc
    return live
