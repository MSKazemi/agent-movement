"""Fail-closed *decision-only* reference for proposed Agent Movement rules.

This module cannot authenticate callers, validate token signatures, inspect
payloads, enforce network/tool access, prevent replay, or reserve quotas.
The gateway must supply `facts` from trusted independent services and enforce
this decision at dispatch, destination ingress, and side-effect boundaries.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

SCHEMA_VERSION = "0.1-research"
CLASSIFICATIONS = {"synthetic": 0, "public": 1, "internal": 2, "confidential": 3, "restricted": 4}
OPERATIONS = {"delegate", "relocate", "clone", "replicate", "fork", "fan_out"}
MUST_APPROVE = {"relocate", "clone", "replicate", "fork", "fan_out"}
REQUEST_KEYS = {
    "movement_id", "origin", "destination", "operation", "data_classification",
    "capabilities", "hop_count", "new_instances", "duration_seconds", "budget_units",
}
FACT_KEYS = {
    "authenticated_origin", "authenticated_destination", "registry_region",
    "verified_data_classification", "verified_hop_count", "grant_signature_valid",
    "grant_issuer", "grant_subject", "grant_audience", "grant_movement_id",
    "grant_operation", "grant_policy_id", "grant_policy_sha256", "grant_scopes",
    "grant_expires_at", "grant_revoked", "now_unix", "approval_valid",
    "approval_movement_id", "approval_destination", "approval_origin", "approval_operation",
}
POLICY_KEYS = {
    "schema_version", "policy_id", "allowed_origins", "destinations", "trusted_issuers",
    "max_hops", "max_new_instances", "max_duration_seconds", "max_budget_units",
    "max_grant_ttl_seconds", "human_approval_operations",
}
DESTINATION_KEYS = {"region", "operations", "max_data_classification", "capabilities"}


@dataclass(frozen=True)
class Decision:
    allow: bool
    reason: str
    policy_id: str


def _string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _int(value: Any) -> bool:
    return type(value) is int and value >= 0


def _string_list(value: Any) -> bool:
    return isinstance(value, list) and all(_string(item) for item in value) and len(set(value)) == len(value)


def policy_sha256(policy: Mapping[str, Any]) -> str:
    """Deterministic digest of test policy JSON, not a signature or canonical wire standard."""
    return hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def decide(policy: Mapping[str, Any], request: Mapping[str, Any], facts: Mapping[str, Any]) -> Decision:
    """Evaluate preflight metadata and *trusted* verifier facts. No side effects."""
    policy_id = policy.get("policy_id", "invalid") if isinstance(policy, Mapping) else "invalid"
    safe_id = policy_id if _string(policy_id) else "invalid"

    def deny(reason: str) -> Decision:
        return Decision(False, reason, safe_id)

    if not all(isinstance(item, Mapping) for item in (policy, request, facts)):
        return deny("malformed_input")
    if set(policy) != POLICY_KEYS or policy.get("schema_version") != SCHEMA_VERSION:
        return deny("unsupported_policy")
    if not _string(policy_id) or not _string_list(policy["allowed_origins"]):
        return deny("malformed_policy")
    if not _string_list(policy["trusted_issuers"]) or not _string_list(policy["human_approval_operations"]):
        return deny("malformed_policy")
    if not set(policy["human_approval_operations"]).issubset(OPERATIONS):
        return deny("malformed_policy")
    if not all(_int(policy[key]) for key in ("max_hops", "max_new_instances", "max_duration_seconds",
                                                "max_budget_units", "max_grant_ttl_seconds")):
        return deny("malformed_policy")
    destinations = policy["destinations"]
    if not isinstance(destinations, Mapping):
        return deny("malformed_policy")
    for name, rules in destinations.items():
        if not _string(name) or not isinstance(rules, Mapping) or set(rules) != DESTINATION_KEYS:
            return deny("malformed_policy")
        if (not _string(rules["region"]) or not _string_list(rules["operations"])
                or not set(rules["operations"]).issubset(OPERATIONS)
                or not _string(rules["max_data_classification"])
                or rules["max_data_classification"] not in CLASSIFICATIONS
                or not _string_list(rules["capabilities"])):
            return deny("malformed_policy")
    if set(request) != REQUEST_KEYS or set(facts) != FACT_KEYS:
        return deny("incomplete_or_extra_fields")
    if not all(_string(request[k]) for k in ("movement_id", "origin", "destination",
                                              "operation", "data_classification")):
        return deny("malformed_request")
    if request["operation"] not in OPERATIONS or request["data_classification"] not in CLASSIFICATIONS:
        return deny("unsupported_request")
    if not _string_list(request["capabilities"]):
        return deny("malformed_request")
    if not all(_int(request[k]) for k in ("hop_count", "new_instances", "duration_seconds", "budget_units")):
        return deny("malformed_request")
    if not all(_string(facts[k]) for k in ("authenticated_origin", "authenticated_destination", "registry_region",
                                            "verified_data_classification", "grant_issuer", "grant_subject",
                                            "grant_audience", "grant_movement_id", "grant_operation",
                                            "grant_policy_id", "grant_policy_sha256")):
        return deny("missing_verified_evidence")
    if not _string_list(facts["grant_scopes"]):
        return deny("missing_verified_evidence")
    if not all(type(facts[k]) is bool for k in ("grant_signature_valid", "grant_revoked", "approval_valid")):
        return deny("missing_verified_evidence")
    if not all(_int(facts[k]) for k in ("grant_expires_at", "now_unix", "verified_hop_count")):
        return deny("missing_verified_evidence")
    for key in ("approval_movement_id", "approval_destination", "approval_origin", "approval_operation"):
        if facts[key] is not None and not _string(facts[key]):
            return deny("missing_verified_evidence")
    if request["hop_count"] != facts["verified_hop_count"]:
        return deny("hop_count_not_verified")
    if request["origin"] not in policy["allowed_origins"]:
        return deny("origin_not_allowed")
    if request["origin"] != facts["authenticated_origin"]:
        return deny("origin_identity_mismatch")
    if request["destination"] != facts["authenticated_destination"]:
        return deny("destination_identity_mismatch")
    destination = destinations.get(request["destination"])
    if destination is None:
        return deny("destination_not_allowed")
    if destination["region"] != facts["registry_region"]:
        return deny("region_mismatch")
    if request["operation"] not in destination["operations"]:
        return deny("operation_not_allowed")
    if request["data_classification"] != facts["verified_data_classification"]:
        return deny("classification_not_verified")
    if CLASSIFICATIONS[request["data_classification"]] > CLASSIFICATIONS[destination["max_data_classification"]]:
        return deny("data_classification_not_allowed")
    if not set(request["capabilities"]).issubset(destination["capabilities"]):
        return deny("capability_not_allowed")
    limits = (("hop_count", "max_hops"), ("new_instances", "max_new_instances"),
              ("duration_seconds", "max_duration_seconds"), ("budget_units", "max_budget_units"))
    if any(request[r] > policy[p] for r, p in limits):
        return deny("limit_exceeded")
    if request["operation"] in {"clone", "replicate", "fork", "fan_out"} and request["new_instances"] < 1:
        return deny("invalid_instance_count")
    if request["operation"] == "delegate" and request["new_instances"] != 0:
        return deny("invalid_instance_count")
    if not facts["grant_signature_valid"] or facts["grant_revoked"]:
        return deny("invalid_or_revoked_grant")
    if facts["grant_issuer"] not in policy["trusted_issuers"]:
        return deny("grant_issuer_not_allowed")
    claims = (("grant_subject", "origin"), ("grant_audience", "destination"),
              ("grant_movement_id", "movement_id"), ("grant_operation", "operation"))
    if any(facts[fact] != request[key] for fact, key in claims):
        return deny("grant_binding_mismatch")
    if facts["grant_policy_id"] != policy_id or facts["grant_policy_sha256"] != policy_sha256(policy):
        return deny("grant_policy_mismatch")
    if not set(request["capabilities"]).issubset(facts["grant_scopes"]):
        return deny("grant_scope_not_allowed")
    ttl = facts["grant_expires_at"] - facts["now_unix"]
    if ttl <= 0 or ttl > policy["max_grant_ttl_seconds"] or request["duration_seconds"] > ttl:
        return deny("grant_expired_or_too_long")
    if request["operation"] in MUST_APPROVE.union(policy["human_approval_operations"]):
        if (not facts["approval_valid"] or facts["approval_movement_id"] != request["movement_id"]
                or facts["approval_destination"] != request["destination"]
                or facts["approval_origin"] != request["origin"]
                or facts["approval_operation"] != request["operation"]):
            return deny("approval_missing_or_wrong_scope")
    return Decision(True, "allow", safe_id)
