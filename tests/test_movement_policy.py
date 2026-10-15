"""Deterministic decisions, *not* proof of non-bypassable runtime enforcement."""
import copy
import hashlib
import json
import unittest
from pathlib import Path

from tools.movement_policy import decide

POLICY = json.loads((Path(__file__).resolve().parents[1] / "examples" / "movement-policy.v0.json").read_text())


def digest(policy):
    return hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
REQUEST = {
    "movement_id": "movement-fixture-001",
    "origin": "spiffe://lab.example/agent/origin",
    "destination": "spiffe://lab.example/agent/reviewer",
    "operation": "delegate",
    "data_classification": "public",
    "capabilities": ["artifact.read"],
    "hop_count": 1,
    "new_instances": 0,
    "duration_seconds": 60,
    "budget_units": 1,
}
# In a real gateway, only trusted services may create these facts. Tests fabricate them.
FACTS = {
    "authenticated_origin": REQUEST["origin"],
    "authenticated_destination": REQUEST["destination"],
    "registry_region": "eu-test-1",
    "verified_data_classification": "public",
    "grant_signature_valid": True,
    "grant_issuer": "https://auth.lab.example",
    "grant_subject": REQUEST["origin"],
    "grant_audience": REQUEST["destination"],
    "grant_movement_id": REQUEST["movement_id"],
    "grant_operation": "delegate",
    "grant_policy_id": POLICY["policy_id"],
    "grant_policy_sha256": digest(POLICY),
    "grant_scopes": ["artifact.read"],
    "grant_expires_at": 1800000120,
    "grant_revoked": False,
    "now_unix": 1800000000,
    "approval_valid": False,
    "approval_movement_id": None,
    "approval_destination": None,
    "approval_origin": None,
    "approval_operation": None,
    "verified_hop_count": 1,
}


class PolicyTests(unittest.TestCase):
    def evaluate(self, p=None, r=None, f=None):
        return decide(POLICY if p is None else p, REQUEST if r is None else r, FACTS if f is None else f)

    def deny(self, reason, p=None, r=None, f=None):
        result = self.evaluate(p, r, f)
        self.assertFalse(result.allow)
        self.assertEqual(result.reason, reason)

    def test_allows_narrow_public_delegation(self):
        result = self.evaluate()
        self.assertTrue(result.allow)
        self.assertEqual(result.reason, "allow")

    def test_default_denies_unlisted_destination(self):
        r = {**REQUEST, "destination": "spiffe://lab.example/agent/evil"}
        f = {**FACTS, "authenticated_destination": r["destination"], "grant_audience": r["destination"]}
        self.deny("destination_not_allowed", r=r, f=f)

    def test_denies_impersonated_origin(self):
        self.deny("origin_identity_mismatch", f={**FACTS, "authenticated_origin": "spiffe://lab.example/agent/other"})

    def test_denies_impersonated_destination(self):
        self.deny("destination_identity_mismatch", f={**FACTS, "authenticated_destination": "spiffe://lab.example/agent/other"})

    def test_denies_wrong_region(self):
        self.deny("region_mismatch", f={**FACTS, "registry_region": "us-test-1"})

    def test_denies_confidential_data(self):
        r = {**REQUEST, "data_classification": "confidential"}
        f = {**FACTS, "verified_data_classification": "confidential"}
        self.deny("data_classification_not_allowed", r=r, f=f)

    def test_denies_unverified_classification(self):
        self.deny("classification_not_verified", f={**FACTS, "verified_data_classification": "confidential"})

    def test_denies_extra_capability(self):
        self.deny("capability_not_allowed", r={**REQUEST, "capabilities": ["artifact.read", "shell.exec"]})

    def test_denies_grant_scope_attenuation_violation(self):
        self.deny("grant_scope_not_allowed", f={**FACTS, "grant_scopes": []})

    def test_denies_unverified_grant(self):
        self.deny("invalid_or_revoked_grant", f={**FACTS, "grant_signature_valid": False})

    def test_denies_revoked_grant(self):
        self.deny("invalid_or_revoked_grant", f={**FACTS, "grant_revoked": True})

    def test_denies_wrong_grant_audience(self):
        self.deny("grant_binding_mismatch", f={**FACTS, "grant_audience": "spiffe://lab.example/agent/other"})

    def test_denies_movement_id_not_bound_to_grant(self):
        self.deny("grant_binding_mismatch", r={**REQUEST, "movement_id": "other-movement"})

    def test_denies_wrong_grant_operation(self):
        self.deny("grant_binding_mismatch", f={**FACTS, "grant_operation": "clone"})

    def test_denies_untrusted_issuer(self):
        self.deny("grant_issuer_not_allowed", f={**FACTS, "grant_issuer": "https://evil.example"})

    def test_denies_grant_policy_version_mismatch(self):
        self.deny("grant_policy_mismatch", f={**FACTS, "grant_policy_id": "old-policy"})

    def test_denies_expired_grant(self):
        self.deny("grant_expired_or_too_long", f={**FACTS, "grant_expires_at": FACTS["now_unix"]})

    def test_denies_overlong_grant(self):
        self.deny("grant_expired_or_too_long", f={**FACTS, "grant_expires_at": FACTS["now_unix"] + 181})

    def test_denies_grant_shorter_than_action(self):
        self.deny("grant_expired_or_too_long", f={**FACTS, "grant_expires_at": FACTS["now_unix"] + 30})

    def test_denies_extra_hops(self):
        self.deny("limit_exceeded", r={**REQUEST, "hop_count": 2}, f={**FACTS, "verified_hop_count": 2})

    def test_denies_extra_budget(self):
        self.deny("limit_exceeded", r={**REQUEST, "budget_units": 11})

    def test_denies_undeclared_cloning(self):
        r = {**REQUEST, "operation": "clone", "new_instances": 1}
        f = {**FACTS, "grant_operation": "clone"}
        self.deny("operation_not_allowed", r=r, f=f)

    def test_high_risk_operation_requires_scoped_human_approval(self):
        p = copy.deepcopy(POLICY)
        p["destinations"][REQUEST["destination"]]["operations"].append("clone")
        p["max_new_instances"] = 1
        r = {**REQUEST, "operation": "clone", "new_instances": 1}
        f = {**FACTS, "grant_operation": "clone", "grant_policy_sha256": digest(p)}
        self.deny("approval_missing_or_wrong_scope", p=p, r=r, f=f)
        f["approval_valid"] = True
        f["approval_movement_id"] = "wrong-movement"
        f["approval_destination"] = REQUEST["destination"]
        f["approval_origin"] = REQUEST["origin"]
        f["approval_operation"] = "clone"
        self.deny("approval_missing_or_wrong_scope", p=p, r=r, f=f)
        f["approval_movement_id"] = REQUEST["movement_id"]
        self.assertTrue(self.evaluate(p=p, r=r, f=f).allow)

    def test_denies_unverified_hop_count(self):
        self.deny("hop_count_not_verified", r={**REQUEST, "hop_count": 0})

    def test_denies_policy_config_change_with_old_grant(self):
        p = copy.deepcopy(POLICY)
        p["max_budget_units"] = 11
        self.deny("grant_policy_mismatch", p=p)

    def test_denies_extra_request_fields_even_when_benign(self):
        self.deny("incomplete_or_extra_fields", r={**REQUEST, "unknown": "value"})

    def test_denies_missing_trusted_facts(self):
        f = dict(FACTS)
        f.pop("grant_signature_valid")
        self.deny("incomplete_or_extra_fields", f=f)

    def test_denies_false_type_int_overrides(self):
        self.deny("malformed_request", r={**REQUEST, "budget_units": True})

    def test_denies_unknown_policy_schema(self):
        self.deny("unsupported_policy", p={**POLICY, "schema_version": "999.0"})

    def test_denies_invalid_policy_classification(self):
        p = copy.deepcopy(POLICY)
        p["destinations"][REQUEST["destination"]]["max_data_classification"] = "unrestricted"
        self.deny("malformed_policy", p=p)


if __name__ == "__main__":
    unittest.main()
