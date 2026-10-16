"""Research-only, fail-closed continuity admission *decision* (not an enforcement point).

A caller must derive ``Policy`` from an independent authority and ``ObservedFacts``
from independently authenticated sources, never from the agent's proposal.
Call again at each protected effect/disclosure boundary: an admission decision
cannot fence code, prevent an unmediated tool call or establish trusted facts.

The stdlib-only checker does not verify signatures, enforce external actions,
prove absence of prompt injection or guarantee global revocation.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from typing import Literal

_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9._:-]{0,127}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
AdmissionState = Literal["eligible", "suspect", "quarantined", "unknown"]


@dataclass(frozen=True)
class Obligations:
    """Portable commitments; lower retention cutoff is stricter."""

    retain_until: int
    allow_onward: bool
    audit_required: bool
    notify_user: bool


@dataclass(frozen=True)
class Proposal:
    """Untrusted requested transfer; no authorizations originate here."""

    destination: str
    scopes: frozenset[str]
    policy_epoch: int
    manifest_digest: str
    obligations: Obligations


@dataclass(frozen=True)
class ConsentGrant:
    """A record already verified by an independent approval authority."""

    principal: str
    destination: str
    scopes: frozenset[str]
    policy_epoch: int
    expires_at: int
    verified: bool
    revoked: bool = False


@dataclass(frozen=True)
class Observation:
    """Fact observed at an external source, not self-reported by the agent."""

    name: str
    observed_at: int
    valid_until: int
    verified: bool


@dataclass(frozen=True)
class Policy:
    """Trusted policy snapshot (including mandatory independent principals)."""

    required_principals: frozenset[str]
    allowed_destinations: frozenset[str]
    allowed_scopes: frozenset[str]
    policy_epoch: int
    required_obligations: Obligations
    approved_manifest_digest: str
    required_observations: frozenset[str]


@dataclass(frozen=True)
class ObservedFacts:
    """Evidence acquired out of band, NOT extracted from the handoff envelope.

    ``recipient_ack_digest`` is a digest of a *verified* recipient acceptance;
    the caller must authenticate that acceptance. A bare digest is forgeable.
    """

    grants: tuple[ConsentGrant, ...]
    recipient_ack_digest: str
    measured_manifest_digest: str
    admission_state: AdmissionState
    observations: tuple[Observation, ...]


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reasons: tuple[str, ...]


def _token(value: object) -> bool:
    return isinstance(value, str) and _TOKEN.fullmatch(value) is not None


def _tokens(value: object, *, nonempty: bool) -> bool:
    return (isinstance(value, frozenset)
            and (not nonempty or bool(value))
            and all(_token(s) for s in value))


def _digest(value: object) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _int(value: object) -> bool:
    return type(value) is int and value >= 0


def _obligations_ok(value: object) -> bool:
    return (isinstance(value, Obligations) and _int(value.retain_until)
            and type(value.allow_onward) is bool
            and type(value.audit_required) is bool
            and type(value.notify_user) is bool)


def _valid_policy(policy: Policy) -> bool:
    return (isinstance(policy, Policy)
            and _tokens(policy.required_principals, nonempty=True)
            and _tokens(policy.allowed_destinations, nonempty=True)
            and _tokens(policy.allowed_scopes, nonempty=True)
            and _int(policy.policy_epoch)
            and _obligations_ok(policy.required_obligations)
            and _digest(policy.approved_manifest_digest)
            and _tokens(policy.required_observations, nonempty=False))


def _valid_proposal(proposal: Proposal) -> bool:
    return (isinstance(proposal, Proposal) and _token(proposal.destination)
            and _tokens(proposal.scopes, nonempty=True)
            and _int(proposal.policy_epoch) and _digest(proposal.manifest_digest)
            and _obligations_ok(proposal.obligations))


def _tuple(value: object) -> bool:
    return isinstance(value, tuple)


def _valid_facts(facts: object) -> bool:
    if not isinstance(facts, ObservedFacts):
        return False
    if not _tuple(facts.grants) or not _tuple(facts.observations):
        return False
    if not _digest(facts.measured_manifest_digest):
        return False
    if not _digest(facts.recipient_ack_digest):
        return False
    if facts.admission_state not in ("eligible", "suspect", "quarantined", "unknown"):
        return False
    for grant in facts.grants:
        if not (isinstance(grant, ConsentGrant) and _token(grant.principal)
                and _token(grant.destination) and _tokens(grant.scopes, nonempty=True)
                and _int(grant.policy_epoch) and _int(grant.expires_at)
                and type(grant.verified) is bool and type(grant.revoked) is bool):
            return False
    for observation in facts.observations:
        if not (isinstance(observation, Observation) and _token(observation.name)
                and _int(observation.observed_at) and _int(observation.valid_until)
                and type(observation.verified) is bool):
            return False
    return True


def obligation_ack_digest(proposal: Proposal) -> str:
    """Fingerprint of *what* recipient must accept, NOT a signature/proof of acceptance.

    Binds the ack to the destination, scopes, policy epoch, approved manifest
    declaration and exact obligations. The independent verifier must establish
    the identity and authority of the source before using the returned digest.
    """
    payload = {
        "domain": "agent-movement/continuity-ack/v1",
        "destination": proposal.destination,
        "manifest_digest": proposal.manifest_digest,
        "policy_epoch": proposal.policy_epoch,
        "scopes": sorted(proposal.scopes),
        "obligations": {
            "retain_until": proposal.obligations.retain_until,
            "allow_onward": proposal.obligations.allow_onward,
            "audit_required": proposal.obligations.audit_required,
            "notify_user": proposal.obligations.notify_user,
        },
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def evaluate(proposal: Proposal, policy: Policy, facts: ObservedFacts, *, now: int) -> Decision:
    """Return deterministic refusal reasons; never infer authorization from proposal.

    Call separately at disclosure AND at protected-effect commitment, providing
    newly verified facts/clock each time. A successful result alone does nothing.
    """
    if not _int(now) or not _valid_policy(policy) or not _valid_proposal(proposal) or not _valid_facts(facts):
        return Decision(False, ("invalid_inputs",))

    reasons: list[str] = []
    if proposal.destination not in policy.allowed_destinations:
        reasons.append("destination_denied")
    if proposal.policy_epoch != policy.policy_epoch:
        reasons.append("epoch_stale")
    if not proposal.scopes <= policy.allowed_scopes:
        reasons.append("scope_denied")

    grant_by_principal: dict[str, ConsentGrant] = {}
    ambiguous = False
    for grant in facts.grants:
        if grant.principal in grant_by_principal:
            ambiguous = True
        grant_by_principal[grant.principal] = grant
    if ambiguous:
        reasons.append("ambiguous_grants")
    for principal in sorted(policy.required_principals):
        approval = grant_by_principal.get(principal)
        if approval is None:
            reasons.append("principal_missing")
        elif (not approval.verified or approval.revoked or approval.destination != proposal.destination
              or approval.policy_epoch != policy.policy_epoch or approval.expires_at <= now
              or not proposal.scopes <= approval.scopes):
            reasons.append("principal_denied")

    required = policy.required_obligations
    proposed = proposal.obligations
    if proposed.retain_until <= now or required.retain_until <= now:
        reasons.append("retention_expired")
    if (proposed.retain_until > required.retain_until or
            (not required.allow_onward and proposed.allow_onward) or
            (required.audit_required and not proposed.audit_required) or
            (required.notify_user and not proposed.notify_user)):
        reasons.append("obligations_relaxed")
    if not hmac.compare_digest(obligation_ack_digest(proposal), facts.recipient_ack_digest):
        reasons.append("obligations_unacknowledged")
    if (not hmac.compare_digest(proposal.manifest_digest, policy.approved_manifest_digest)
            or not hmac.compare_digest(facts.measured_manifest_digest, policy.approved_manifest_digest)):
        reasons.append("configuration_drift")
    if facts.admission_state != "eligible":
        reasons.append("state_not_cleared")

    observations: dict[str, Observation] = {}
    for observation in facts.observations:
        if observation.name in observations:
            reasons.append("ambiguous_observations")
        observations[observation.name] = observation
    for name in sorted(policy.required_observations):
        observed = observations.get(name)
        if observed is None:
            reasons.append("evidence_missing")
        elif (not observed.verified or observed.observed_at > now
              or observed.valid_until <= now or observed.valid_until <= observed.observed_at):
            reasons.append("evidence_stale")

    unique_reasons = tuple(dict.fromkeys(reasons))
    return Decision(not unique_reasons, unique_reasons)


def approval_preview(proposal: Proposal, policy: Policy) -> dict[str, object]:
    """An untrusted-proposal *preview*, not proof of any grant or a UI usability test."""
    if not _valid_proposal(proposal) or not _valid_policy(policy):
        raise ValueError("invalid proposal or policy for preview")
    return {
        "destination": proposal.destination,
        "requested_scopes": sorted(proposal.scopes),
        "mandatory_approvers": sorted(policy.required_principals),
        "retention_cutoff_epoch_seconds": proposal.obligations.retain_until,
        "onward_delegation_requested": proposal.obligations.allow_onward,
        "audit_required": proposal.obligations.audit_required,
        "notify_user": proposal.obligations.notify_user,
        "configuration_matches_policy": proposal.manifest_digest == policy.approved_manifest_digest,
        "warning": "An approval does not undo effects already committed or prove downstream deletion.",
        "status": "preview_only_not_authorized",
    }
