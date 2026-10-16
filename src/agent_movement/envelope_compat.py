"""Explicit, loss-intolerant bridge between proposed and implemented handoff envelopes.

Only the 0.1.0-draft *runtime* wire contract is implemented by core, peer and
A2A today. A canonical 0.2.0-draft proposal is not a negotiated wire format.
A caller must opt in to a version-tag-only conversion, and every other field
must already satisfy the strict 0.1 runtime profile. No field is discarded.
Version conversion never authenticates a peer or authorizes a transfer.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Iterable

from .core import SCHEMA_VERSION, ContractError, digest, validate_envelope

PROPOSED_SCHEMA_VERSION = "0.2.0-draft"
RUNTIME_WIRE_VERSIONS = (SCHEMA_VERSION,)


class IncompatibleEnvelope(ContractError):
    """Explicit refusal: no common runtime version or unsafe semantic conversion."""


@dataclass(frozen=True)
class PreparedHandoff:
    """Wire bytes are derived from `envelope`; source and wire digests differ on conversion."""

    envelope: dict[str, Any]
    source_version: str
    wire_version: str
    source_digest: str
    wire_digest: str
    transform: str


def _receiver_versions(versions: Iterable[str]) -> frozenset[str]:
    """Parse versions from an *already authenticated* capability advertisement."""
    if isinstance(versions, (str, bytes)):
        raise IncompatibleEnvelope("receiver versions must be a sequence")
    try:
        entries = tuple(versions)
    except (TypeError, ValueError) as exc:
        raise IncompatibleEnvelope("invalid receiver version advertisement") from exc
    if not entries or len(entries) > 32 or any(
        not isinstance(item, str) or not item or len(item) > 128 for item in entries
    ):
        raise IncompatibleEnvelope("invalid receiver version advertisement")
    return frozenset(entries)


def prepare_handoff(
    candidate: Any,
    receiver_versions: Iterable[str],
    *,
    allow_minimal_conversion: bool = False,
) -> PreparedHandoff:
    """Negotiate one *supported* wire version; never silently downgrade a request.

    The application must get `receiver_versions` from a trusted destination
    descriptor and `allow_minimal_conversion` from an operator-owned decision.
    It must still verify identity, approval and policy in its real sender and
    receiver. The only supported conversion replaces the proposal's version
    tag when **no additional fields** are present and the 0.1 receiver's full
    validation already succeeds. Relocation and extended metadata are refused.
    """
    advertised = _receiver_versions(receiver_versions)
    if not isinstance(candidate, dict):
        raise IncompatibleEnvelope("invalid source envelope")
    source_version = candidate.get("schema_version")
    if source_version == SCHEMA_VERSION:
        if SCHEMA_VERSION not in advertised:
            raise IncompatibleEnvelope("destination does not support runtime envelope")
        try:
            wire = deepcopy(validate_envelope(candidate))
        except ContractError as exc:
            raise IncompatibleEnvelope("invalid runtime envelope") from exc
        operation = "identity"
    elif source_version == PROPOSED_SCHEMA_VERSION:
        if not allow_minimal_conversion:
            raise IncompatibleEnvelope("canonical proposal requires explicit conversion approval")
        if SCHEMA_VERSION not in advertised:
            raise IncompatibleEnvelope("destination has no implemented compatible wire version")
        # Deep copy so even a malicious caller cannot mutate a nested dictionary
        # after the version switch; strict core validation rejects every optional
        # canonical-only field rather than silently dropping information.
        try:
            wire = deepcopy(candidate)
            wire["schema_version"] = SCHEMA_VERSION
            validate_envelope(wire)
        except (ContractError, ValueError, TypeError) as exc:
            raise IncompatibleEnvelope("canonical envelope exceeds lossless runtime profile") from exc
        operation = "version-tag-only"
    else:
        raise IncompatibleEnvelope("unsupported source envelope version")

    try:
        source_digest = digest(candidate)
        wire_digest = digest(wire)
    except (TypeError, ValueError, UnicodeError, OverflowError) as exc:
        raise IncompatibleEnvelope("envelope cannot be canonicalized") from exc
    return PreparedHandoff(
        envelope=wire,
        source_version=source_version,
        wire_version=SCHEMA_VERSION,
        source_digest=source_digest,
        wire_digest=wire_digest,
        transform=operation,
    )
