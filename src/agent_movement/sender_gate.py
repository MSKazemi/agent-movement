"""Operator-pinned pre-disclosure sender check for the synthetic peer client.

This gate is enforced by PeerClient.handoff only when explicitly configured.
It does not constrain a malicious Python caller using a different client,
direct sockets, other server adapters, or privileged OS access. Issue #50
requires independent process/egress enforcement for those paths.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .core import ContractError
from .trust import (
    CLASSIFICATIONS,
    TASK_KINDS,
    TrustStore,
    Unauthorized,
    check_grant_live,
    check_grant_scope,
    endpoint,
    verify_card,
    verify_grant,
)


@dataclass(frozen=True)
class OutboundGate:
    """Allowlist and revocation source installed by a *trusted operator*.

    The checker verifies signed card and grant material itself; no caller
    supplied ``authenticated=True`` or ``policy_passed=True`` is trusted.
    An independent operator must keep ``is_revoked`` current; when it fails,
    malformed results or exceptions **deny** the attempt. The recipient still
    verifies everything again at preflight, delivery and effect commit.
    """

    allowed_destinations: frozenset[tuple[str, str]]
    allowed_capabilities: frozenset[str]
    allowed_classifications: frozenset[str]
    is_revoked: Callable[[str], bool]
    require_confidentiality: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.allowed_destinations) is not frozenset
            or not self.allowed_destinations
            or any(
                not isinstance(item, tuple)
                or len(item) != 2
                or not all(isinstance(part, str) for part in item)
                for item in self.allowed_destinations
            )
        ):
            raise ContractError("invalid outbound destination allowlist")
        for identity, address in self.allowed_destinations:
            if not identity or not address:
                raise ContractError("invalid outbound destination")
            endpoint(address)
        if (
            type(self.allowed_capabilities) is not frozenset
            or not self.allowed_capabilities
            or not self.allowed_capabilities <= TASK_KINDS
        ):
            raise ContractError("invalid outbound capability allowlist")
        if (
            type(self.allowed_classifications) is not frozenset
            or not self.allowed_classifications
            or not self.allowed_classifications <= CLASSIFICATIONS
        ):
            raise ContractError("invalid outbound classification allowlist")
        if not callable(self.is_revoked) or type(self.require_confidentiality) is not bool:
            raise ContractError("invalid outbound trust configuration")

    def check(
        self, *, trust: TrustStore, origin_card: dict[str, Any], origin_key: Any,
        destination_id: str, url: str, task_id: str, kind: str,
        classification: str, grant: Any, now: int, operation: str = "delegate",
    ) -> None:
        """Validate **before discovery**: no request or protected grant is sent.

        This is a stateless sender decision. Grant use counts and concurrent
        revocation/effect races remain the receiver's transactional responsibility.
        """
        if operation != "delegate":
            raise Unauthorized("outbound_unsupported_operation")
        if (destination_id, url) not in self.allowed_destinations:
            raise Unauthorized("outbound_destination_denied")
        if kind not in self.allowed_capabilities:
            raise Unauthorized("outbound_capability_denied")
        if classification not in self.allowed_classifications:
            raise Unauthorized("outbound_classification_denied")
        origin = verify_card(origin_card, trust, now)
        # Binding only the key ID is insufficient: a forged local signer can
        # reuse a pinned kid. Prove possession against the verified card key.
        proof = b"agent-movement/outbound-gate/key-binding/v1"
        try:
            key_ok = origin.key.kid == origin_key.kid and origin.key.verify(
                proof, origin_key.sign(proof),
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise Unauthorized("outbound_origin_key_mismatch") from exc
        if not key_ok:
            raise Unauthorized("outbound_origin_key_mismatch")
        verified = verify_grant(grant, trust)
        check_grant_scope(
            verified, actor=origin.agent_id, audience=destination_id,
            task_id=task_id, kind=kind, classification=classification,
        )
        try:
            revoked = self.is_revoked(verified["grant_id"])
        except Exception as exc:
            raise Unauthorized("outbound_revocation_source_unavailable") from exc
        if type(revoked) is not bool:
            raise Unauthorized("outbound_revocation_source_unavailable")
        check_grant_live(verified, now=now, revoked=revoked)
