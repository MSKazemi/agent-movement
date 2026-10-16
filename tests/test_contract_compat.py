"""Compatibility contract: no implicit 0.2 ingress or semantic-loss downgrade."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from agent_movement import core
from agent_movement.a2a_profile import envelope_to_a2a
from agent_movement.contract_compat import (
    DRAFT_VERSION,
    IncompatibleContract,
    negotiate_wire_version,
    project_draft_to_runtime,
    project_runtime_to_draft,
    runtime_capabilities,
)


def live() -> dict:
    return {
        "schema_version": core.SCHEMA_VERSION,
        "movement_id": "mov-test-1", "logical_task_id": "task-test-1",
        "operation": "delegate",
        "origin": {"agent_id": "agent-a"},
        "destination": {"agent_id": "agent-b"},
        "task": {"kind": "word_count", "text": "synthetic task"},
        "context": {"classification": "synthetic"},
        "authority": {"approval_ref": "approved-1"},
        "execution": {"idempotency_key": "key-1"},
        "observability": {"trace_id": "trace-1"},
    }


def draft() -> dict:
    return project_runtime_to_draft(live())


def test_only_the_implemented_version_is_executable():
    caps = runtime_capabilities()
    assert caps["runtime_wire_versions"] == [core.SCHEMA_VERSION]
    assert caps["draft_schema_versions"] == [DRAFT_VERSION]
    assert not caps["automatic_downgrade"]
    assert caps["runtime_operations"] == ["delegate"]
    assert negotiate_wire_version([DRAFT_VERSION, core.SCHEMA_VERSION]) == core.SCHEMA_VERSION


@pytest.mark.parametrize("unsupported", [
    [DRAFT_VERSION], ["3.0.0"], [], [core.SCHEMA_VERSION, core.SCHEMA_VERSION],
    "0.1.0-draft", None, [1], [True], [{"schema": core.SCHEMA_VERSION}],
    [DRAFT_VERSION] * 17,
])
def test_negotiate_rejects_non_executable_or_unverified_shapes(unsupported):
    with pytest.raises(IncompatibleContract):
        negotiate_wire_version(unsupported)


def test_roundtrip_is_exact_for_both_implemented_kinds():
    for task in ({"kind": "word_count", "text": "words"},
                 {"kind": "sha256", "text": ""}):
        original = {**live(), "task": task}
        proposal = project_runtime_to_draft(original)
        assert proposal["schema_version"] == DRAFT_VERSION
        assert project_draft_to_runtime(proposal, allow_projection=True) == original
        assert original == core.validate_envelope(original)


def test_conversion_never_mutates_input_or_writes_any_policy_truth():
    proposed = draft()
    saved = copy.deepcopy(proposed)
    live_env = project_draft_to_runtime(proposed, allow_projection=True)
    assert proposed == saved
    assert set(live_env) == set(live())
    assert "authenticated" not in json.dumps(live_env)
    assert live_env["schema_version"] == core.SCHEMA_VERSION


def test_default_denies_even_the_lossless_projection():
    with pytest.raises(IncompatibleContract, match="opt-in"):
        project_draft_to_runtime(draft())
    with pytest.raises(IncompatibleContract, match="opt-in"):
        project_draft_to_runtime(draft(), allow_projection=1)


@pytest.mark.parametrize("path,value", [
    (("parent_movement_id",), None),
    (("requirements",), {"capabilities": ["word_count"]}),
    (("message",), {"message_id": "message-1"}),
    (("integrity",), {"envelope_digest": "0" * 64}),
    (("task", "goal"), "continue investigation"),
    (("context", "purpose"), "planning"),
    (("context", "artifact_refs"), []),
    (("context", "classification"), "internal"),
    (("origin", "execution_id"), "run-1"),
    (("destination", "endpoint_id"), "endpoint-1"),
    (("authority", "grant_ref"), "opaque-grant-1"),
    (("authority", "delegation_depth"), 0),
    (("authority", "expires_at"), "2030-01-01T00:00:00Z"),
    (("execution", "fencing_epoch"), 1),
    (("execution", "max_runtime_seconds"), 100),
    (("execution", "checkpoint_ref"), None),
    (("observability", "traceparent"), "00-" + "0" * 32 + "-" + "0" * 16 + "-01"),
    (("operation",), "relocate"),
    (("task", "kind"), "unauthorized_operation"),
    (("task", "text"), {"unexpected": "data"}),
    (("schema_version",), "0.3.0-draft"),
    (("unrecognized",), True),
])
def test_projection_refuses_unsupported_or_semantically_lossy_fields(path, value):
    payload = draft()
    cursor = payload
    for segment in path[:-1]:
        cursor = cursor[segment]
    cursor[path[-1]] = value
    with pytest.raises(IncompatibleContract):
        project_draft_to_runtime(payload, allow_projection=True)


@pytest.mark.parametrize("path", [
    ("movement_id",), ("origin",), ("task", "text"),
    ("authority", "approval_ref"), ("observability", "trace_id"),
])
def test_projection_rejects_missing_required_fields(path):
    payload = draft()
    cursor = payload
    for segment in path[:-1]:
        cursor = cursor[segment]
    del cursor[path[-1]]
    with pytest.raises(IncompatibleContract):
        project_draft_to_runtime(payload, allow_projection=True)


def test_legacy_core_and_a2a_profile_reject_unconverted_draft():
    proposal = draft()
    with pytest.raises(core.ContractError, match="unsupported schema"):
        core.validate_envelope(proposal)
    with pytest.raises(core.ContractError, match="unsupported schema"):
        envelope_to_a2a(proposal)
    projected = project_draft_to_runtime(proposal, allow_projection=True)
    assert envelope_to_a2a(projected)["metadata"]["schema_version"] == core.SCHEMA_VERSION


def test_live_to_draft_requires_fully_valid_runtime_shape():
    bad = live()
    bad["authority"] = {"approval_ref": "approved-1", "approved": True}
    with pytest.raises(core.ContractError):
        project_runtime_to_draft(bad)


def test_reproducible_migration_demo_uses_only_synthetic_inputs():
    root = Path(__file__).resolve().parents[1]
    cmd = [sys.executable, str(root / "tools" / "contract_migration_demo.py"), "--json"]
    first = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=15)
    second = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=15)
    assert first.stdout == second.stdout
    report = json.loads(first.stdout)
    assert report["identical_runtime_roundtrip"]
    assert report["original_fingerprint"] == report["roundtrip_fingerprint"]
    assert report["executed_version"] == core.SCHEMA_VERSION
    assert not report["runtime_capabilities"]["automatic_downgrade"]
    assert "synthetic task" not in first.stdout
