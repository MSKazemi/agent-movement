"""Issue #99: route inventory completeness as a static *planning* gate.

This verifies known source routes are present and unmediated ones are NOT
mislabelled as already protected. It does NOT prove OS/process listener shutdown.
"""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "data" / "secure-route-inventory.csv"
FIELDS = (
    "route_id", "entrypoint", "source_path", "source_anchor",
    "transport", "current_semantics", "proposed_secure_test_policy",
    "gap", "test_reference", "parent_issue",
)
KNOWN_ROUTES = frozenset({
    "legacy_handoff_http", "legacy_revocation_http",
    "peer_card", "peer_preflight", "peer_delivery", "peer_revocation",
    "peer_simulated_effect", "legacy_effect_gateway", "guarded_effect_gateway",
    "a2a_jsonrpc", "a2a_rest", "relocation_coordinator",
    "unified_cli", "egress_child", "generic_unmediated_tools",
    "independent_tool_pilot",
})
KNOWN_INSECURE = frozenset({
    "legacy_handoff_http", "legacy_revocation_http",
    "legacy_effect_gateway", "a2a_jsonrpc", "a2a_rest",
    "relocation_coordinator", "unified_cli",
})


def checked_inventory(content: str) -> list[dict[str, str]]:
    reader = csv.DictReader(content.splitlines())
    if tuple(reader.fieldnames or ()) != FIELDS:
        raise ValueError("secure route inventory column schema changed")
    rows = list(reader)
    if {x["route_id"] for x in rows} != KNOWN_ROUTES or len(rows) != len(KNOWN_ROUTES):
        raise ValueError("missing or duplicated protected-route entrypoints")
    if any(None in item or any(not value.strip() for value in item.values()) for item in rows):
        raise ValueError("missing source, policy, gap or validation field")
    if any(
        item["proposed_secure_test_policy"]
        not in ("must_disable", "gated_candidate", "out_of_scope") for item in rows
    ):
        raise ValueError("unreviewed secure-profile route status")
    if any(item["route_id"] in KNOWN_INSECURE and item["proposed_secure_test_policy"] != "must_disable"
           for item in rows):
        raise ValueError("unmediated route was promoted into a protected profile without independent proof")
    return rows


def test_source_linked_matrix_has_all_declared_paths():
    rows = checked_inventory(INVENTORY.read_text(encoding="utf-8"))
    for item in rows:
        source = ROOT / item["source_path"]
        test_file = ROOT / item["test_reference"]
        assert source.is_file(), item
        assert test_file.is_file(), item
        assert item["source_anchor"] in source.read_text(encoding="utf-8"), item


def test_no_claimed_secure_profile_exists_yet():
    rows = checked_inventory(INVENTORY.read_text(encoding="utf-8"))
    assert {r["proposed_secure_test_policy"] for r in rows} == {
        "must_disable", "gated_candidate", "out_of_scope"
    }
    assert sum(r["proposed_secure_test_policy"] == "must_disable" for r in rows) >= 7
    assert all(
        r["gap"] and r["current_semantics"] and r["parent_issue"] in {
            "50", "93", "98", "99", "102", "103"
        } for r in rows
    )
    assert not any("already_secure" in r["current_semantics"] for r in rows)


def test_manifest_is_deterministic_and_has_reviewable_source_digest():
    content = INVENTORY.read_bytes()
    rows = checked_inventory(content.decode("utf-8"))
    assert len(rows) == 16
    assert content.endswith(b"\n")
    assert hashlib.sha256(content).hexdigest() == hashlib.sha256(INVENTORY.read_bytes()).hexdigest()


@pytest.mark.parametrize("target", [
    "legacy_handoff_http", "a2a_jsonrpc", "relocation_coordinator", "unified_cli",
])
def test_static_red_control_rejects_false_authorization_claim(target):
    raw = INVENTORY.read_text(encoding="utf-8")
    lines = raw.splitlines()
    route_index = next(i for i, line in enumerate(lines) if line.startswith('"' + target + '",'))
    mutated = lines[route_index].replace('"must_disable"', '"gated_candidate"')
    assert mutated != lines[route_index]
    lines[route_index] = mutated
    with pytest.raises(ValueError, match="unmediated route"):
        checked_inventory("\n".join(lines) + "\n")


def test_duplicate_or_omitted_route_refused_as_missing_evidence():
    original = INVENTORY.read_text(encoding="utf-8").splitlines()
    with pytest.raises(ValueError, match="duplicated"):
        checked_inventory("\n".join([*original, original[1]]) + "\n")
    with pytest.raises(ValueError, match="missing"):
        checked_inventory("\n".join([original[0], *original[2:]]) + "\n")
