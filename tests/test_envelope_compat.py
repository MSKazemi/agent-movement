"""Issue #96: canonical proposal != the implemented runtime handoff wire schema.

Every conversion must be opt-in, version-tag-only, and revalidated by core.
The A2A profile is separately versioned; its payload still uses the 0.1 wire.
"""

from __future__ import annotations

from copy import deepcopy

import pytest

from agent_movement.a2a_profile import a2a_to_envelope, envelope_to_a2a
from agent_movement.core import SCHEMA_VERSION, ContractError, digest, validate_envelope
from agent_movement.envelope_compat import (
    PROPOSED_SCHEMA_VERSION,
    RUNTIME_WIRE_VERSIONS,
    IncompatibleEnvelope,
    prepare_handoff,
)


def minimal(version: str = SCHEMA_VERSION) -> dict:
    return {
        "schema_version": version,
        "movement_id": "mov-contract-test",
        "logical_task_id": "task-contract-test",
        "operation": "delegate",
        "origin": {"agent_id": "agent-a"},
        "destination": {"agent_id": "agent-b"},
        "task": {"kind": "word_count", "text": "synthetic one two"},
        "context": {"classification": "synthetic"},
        "authority": {"approval_ref": "approval-test"},
        "execution": {"idempotency_key": "idem-test"},
        "observability": {"trace_id": "trace-test"},
    }


def test_runtime_advertises_only_implemented_wire():
    assert RUNTIME_WIRE_VERSIONS == (SCHEMA_VERSION,)
    assert PROPOSED_SCHEMA_VERSION not in RUNTIME_WIRE_VERSIONS


def test_runtime_01_is_identity_and_a2a_roundtrip():
    source = minimal()
    result = prepare_handoff(source, RUNTIME_WIRE_VERSIONS)
    assert result.transform == "identity"
    assert result.envelope == source
    assert result.envelope is not source
    assert result.source_digest == result.wire_digest == digest(source)
    mapped = envelope_to_a2a(result.envelope)
    assert a2a_to_envelope(mapped["metadata"], mapped["data"]) == source
    assert validate_envelope(result.envelope) == source


def test_explicit_proposal_conversion_changes_only_version_and_roundtrips():
    source = minimal(PROPOSED_SCHEMA_VERSION)
    original = deepcopy(source)
    with pytest.raises(ContractError, match="unsupported schema version"):
        validate_envelope(source)
    with pytest.raises(IncompatibleEnvelope, match="explicit conversion approval"):
        prepare_handoff(source, RUNTIME_WIRE_VERSIONS)
    result = prepare_handoff(source, RUNTIME_WIRE_VERSIONS, allow_minimal_conversion=True)
    assert result.source_version == PROPOSED_SCHEMA_VERSION
    assert result.wire_version == SCHEMA_VERSION
    assert result.transform == "version-tag-only"
    assert source == original  # no in-place downgrade, no secret/authority mutation
    assert result.envelope == minimal()
    assert result.source_digest == digest(source)
    assert result.wire_digest == digest(minimal())
    assert result.source_digest != result.wire_digest
    mapped = envelope_to_a2a(result.envelope)
    assert a2a_to_envelope(mapped["metadata"], mapped["data"]) == minimal()


@pytest.mark.parametrize("extra", [
    {"parent_movement_id": None},
    {"requirements": {"capabilities": ["word_count"]}},
    {"message": {"message_id": "msg-1"}},
    {"integrity": {"envelope_digest": "0" * 64}},
    {"origin": {"agent_id": "agent-a", "execution_id": "exec-1"}},
    {"task": {"kind": "word_count", "text": "a", "deadline": None}},
    {"context": {"classification": "synthetic", "purpose": "research"}},
    {"authority": {"approval_ref": "approval-test", "grant_ref": "grant-1"}},
    {"execution": {"idempotency_key": "idem-test", "fencing_epoch": 1}},
    {"observability": {"trace_id": "trace-test", "traceparent": "00-" + "0" * 32 + "-" + "0" * 16 + "-01"}},
])
def test_proposed_extra_information_is_never_silently_discarded(extra):
    source = minimal(PROPOSED_SCHEMA_VERSION)
    source.update(extra)
    before = deepcopy(source)
    with pytest.raises(IncompatibleEnvelope, match="exceeds lossless runtime profile"):
        prepare_handoff(source, RUNTIME_WIRE_VERSIONS, allow_minimal_conversion=True)
    assert source == before


@pytest.mark.parametrize("changes", [
    {"operation": "relocate"},
    {"task": {"kind": "resume_checkpoint", "text": ""}},
    {"task": {"kind": "word_count", "text": "x" * 2049}},
    {"context": {"classification": "internal"}},
    {"destination": {"agent_id": "agent-b", "endpoint_id": "endpoint-1"}},
    {"movement_id": "invalid\nnewline"},
    {"authority": {"approval_ref": None}},
])
def test_unsupported_semantics_and_invalid_contracts_refused(changes):
    source = minimal(PROPOSED_SCHEMA_VERSION)
    source.update(changes)
    with pytest.raises(IncompatibleEnvelope):
        prepare_handoff(source, RUNTIME_WIRE_VERSIONS, allow_minimal_conversion=True)


@pytest.mark.parametrize("version", ["0.3.0", "0.2", "", None, False])
def test_unrecognized_source_version_cannot_downgrade(version):
    source = minimal()
    source["schema_version"] = version
    with pytest.raises(IncompatibleEnvelope):
        prepare_handoff(source, RUNTIME_WIRE_VERSIONS, allow_minimal_conversion=True)


@pytest.mark.parametrize("advertisement", [
    [],
    ["0.2.0-draft"],
    ["0.3.0"],
])
def test_unsupported_receiver_fails_closed(advertisement):
    with pytest.raises(IncompatibleEnvelope):
        prepare_handoff(minimal(), advertisement)


@pytest.mark.parametrize("advertisement", [None, "0.1.0-draft", b"0.1.0-draft", [None], [10], [""]])
def test_malformed_receiver_versions_fail_closed(advertisement):
    with pytest.raises(IncompatibleEnvelope):
        prepare_handoff(minimal(), advertisement)


def test_proposed_receiver_only_advertising_02_does_not_mean_it_runs_02():
    with pytest.raises(IncompatibleEnvelope, match="no implemented compatible wire"):
        prepare_handoff(
            minimal(PROPOSED_SCHEMA_VERSION),
            [PROPOSED_SCHEMA_VERSION],
            allow_minimal_conversion=True,
        )


def test_copy_is_deep_and_cannot_be_mutated_via_caller_reference():
    source = minimal(PROPOSED_SCHEMA_VERSION)
    result = prepare_handoff(source, RUNTIME_WIRE_VERSIONS, allow_minimal_conversion=True)
    source["task"]["text"] = "changed later"
    assert result.envelope["task"]["text"] == "synthetic one two"
