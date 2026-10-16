"""The canonical handoff envelope (issue #33): schema, doc examples and core compatibility.

Every JSON block in docs/ preceded by `<!-- envelope-example -->` must validate
against schemas/handoff-envelope.schema.json with the stdlib-only validator in
tools/schema_subset.py. The core strict profile (src/agent_movement/core.py) must
stay a subset of the schema, apart from its schema_version (divergence D1).
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

import schema_subset as ss
from agent_movement import core

REPO = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO / "schemas" / "handoff-envelope.schema.json"
DOCS = REPO / "docs"
CORPORA = ("news-corpus", "paper-corpus")
MARKER = "<!-- envelope-example -->"
MARKER_LINE = re.compile(r"^" + re.escape(MARKER) + r"[ \t]*$", re.M)
FENCE = re.compile(r"\A[ \t]*\n*(```|~~~)json[ \t]*\n(.*?)\n\1[ \t]*$", re.S | re.M)
RECEIPT_ENV = REPO / "tests/fixtures/movement-receipts/01-valid-delegation/subjects/env-mov-valid-1.json"

SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
VALIDATOR = ss.Validator(SCHEMA)
VERSION = SCHEMA["properties"]["schema_version"]["const"]


def doc_files() -> list[Path]:
    return sorted(p for p in DOCS.rglob("*.md") if not any(c in p.parts for c in CORPORA))


def marked_examples() -> list[tuple[str, dict]]:
    found = []
    for path in doc_files():
        text = path.read_text(encoding="utf-8")
        for n, chunk in enumerate(MARKER_LINE.split(text)[1:], 1):
            m = FENCE.match(chunk)
            assert m, f"{path.relative_to(REPO)}: marker #{n} is not followed by a ```json block"
            found.append((f"{path.relative_to(REPO)}#{n}", json.loads(m.group(2))))
    return found


EXAMPLES = marked_examples()


def core_envelope(**over) -> dict:
    env = {
        "schema_version": core.SCHEMA_VERSION, "movement_id": "mov-1", "logical_task_id": "task-1",
        "operation": "delegate", "origin": {"agent_id": "agent-a"}, "destination": {"agent_id": "agent-b"},
        "task": {"kind": "word_count", "text": "a b c"}, "context": {"classification": "synthetic"},
        "authority": {"approval_ref": "approval-1"}, "execution": {"idempotency_key": "op-1"},
        "observability": {"trace_id": "trace-1"},
    }
    env.update(over)
    return env


def canonical_version(env: dict) -> dict:
    return {**copy.deepcopy(env), "schema_version": VERSION}


# --------------------------------------------------------------------------- doc examples


def test_docs_carry_marked_examples_in_each_owner_document():
    sources = {name.split("#")[0] for name, _ in EXAMPLES}
    assert {"docs/how-it-works.md", "docs/agent-communication-and-policy.md",
            "docs/protocols-and-networks/handoff-and-relocation-contract.md"} <= sources
    assert len(EXAMPLES) >= 5


@pytest.mark.parametrize("name,envelope", EXAMPLES, ids=[n for n, _ in EXAMPLES])
def test_doc_example_validates_against_schema(name, envelope):
    assert VALIDATOR.errors(envelope) == []


def test_doc_example_integrity_digests_are_correct():
    signed = [(name, env) for name, env in EXAMPLES if "integrity" in env]
    assert signed, "at least one doc example should show the integrity block"
    for name, env in signed:
        body = {k: val for k, val in env.items() if k != "integrity"}
        assert env["integrity"]["envelope_digest"] == core.digest(body), name


def test_every_canonical_json_block_in_docs_is_marked():
    """A block that claims the canonical version but is not marked would escape validation."""
    for path in doc_files():
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r"^(```|~~~)json[ \t]*\n(.*?)\n\1[ \t]*$", text, re.S | re.M):
            if f'"schema_version": "{VERSION}"' in m.group(2):
                before = text[:m.start()].rstrip()
                assert before.endswith(MARKER), f"{path.relative_to(REPO)}: unmarked {VERSION} example"


def test_retired_envelope_names_are_gone_from_owner_documents():
    for rel in ("docs/how-it-works.md", "docs/agent-communication-and-policy.md",
                "docs/protocols-and-networks/handoff-and-relocation-contract.md",
                "docs/protocols-and-networks/security-reliability-and-observability.md"):
        blocks = re.findall(r"^(?:```|~~~)json[ \t]*\n(.*?)\n(?:```|~~~)", (REPO / rel).read_text(encoding="utf-8"),
                            re.S | re.M)
        for block in blocks:
            for old in ('"fence_epoch"', '"lease_epoch"', '"approval_id"', '"delegation_ref"', '"run_id"',
                        '"authorization"', '"manifest_digest"', '"agent-communication/0.1-proposal"'):
                assert old not in block, f"{rel}: retired name {old} in a JSON example"


# --------------------------------------------------------------------------- core compatibility


def test_minimal_doc_example_is_accepted_by_core_with_its_version():
    minimal = dict(EXAMPLES)["docs/how-it-works.md#1"]
    core.validate_envelope({**minimal, "schema_version": core.SCHEMA_VERSION})


def test_core_accepted_envelopes_are_schema_valid_apart_from_version():
    for env in (core_envelope(), core_envelope(task={"kind": "sha256", "text": ""}),
                core_envelope(context={"classification": "public"}),
                json.loads(RECEIPT_ENV.read_text(encoding="utf-8"))["value"]):
        core.validate_envelope(env)
        assert VALIDATOR.errors(canonical_version(env)) == []
        assert VALIDATOR.errors(env) == ["/schema_version: must equal \"0.2.0-draft\""]


def test_schema_id_pattern_matches_core_id():
    core_body = core.ID.pattern.removesuffix(r"\Z")
    for name in ("id", "nullable_id"):
        assert SCHEMA["$defs"][name]["pattern"] == f"^{core_body}$"


def test_schema_required_set_matches_core_exact_fields():
    assert set(SCHEMA["required"]) == set(core_envelope())


def test_core_rejects_the_canonical_version_divergence_d1():
    with pytest.raises(core.ContractError):
        core.validate_envelope(canonical_version(core_envelope()))


# --------------------------------------------------------------------------- envelope rules


def test_retired_field_name_is_rejected():
    env = canonical_version(core_envelope(execution={"idempotency_key": "op-1", "fence_epoch": 1}))
    assert "/execution: unexpected property 'fence_epoch'" in VALIDATOR.errors(env)


def test_relocate_requires_checkpoint_and_fencing_epoch():
    env = canonical_version(core_envelope(operation="relocate"))
    errs = VALIDATOR.errors(env)
    assert "(root): missing required property 'requirements'" in errs
    assert "/execution: missing required property 'fencing_epoch'" in errs
    assert "/origin: missing required property 'execution_id'" in errs
    relocate = dict(EXAMPLES)["docs/how-it-works.md#3"]
    bad = copy.deepcopy(relocate)
    bad["execution"]["fencing_epoch"] = None
    assert VALIDATOR.errors(bad) == ["/execution/fencing_epoch: expected type integer, got null"]


def test_delegate_allows_null_fencing_epoch_but_not_zero():
    env = canonical_version(core_envelope(execution={"idempotency_key": "op-1", "fencing_epoch": None}))
    assert VALIDATOR.errors(env) == []
    env["execution"]["fencing_epoch"] = 0
    assert VALIDATOR.errors(env) == ["/execution/fencing_epoch: below minimum 1"]


def test_ids_reject_trailing_newline_like_core():
    env = canonical_version(core_envelope(movement_id="mov-1\n"))
    assert any(e.startswith("/movement_id: does not match") for e in VALIDATOR.errors(env))
    with pytest.raises(core.ContractError):
        core.validate_envelope(core_envelope(movement_id="mov-1\n"))


# --------------------------------------------------------------------------- validator subset


def v(schema: dict) -> ss.Validator:
    return ss.Validator(schema)


@pytest.mark.parametrize("schema,good,bad", [
    ({"type": "string"}, "x", 1),
    ({"type": "integer"}, 3, True),
    ({"type": "integer"}, 3, 3.0),
    ({"type": "number"}, 3, "3"),
    ({"type": ["string", "null"]}, None, 0),
    ({"type": "object", "required": ["a"]}, {"a": 1}, {"b": 1}),
    ({"properties": {"a": {"type": "string"}}}, {"a": "x"}, {"a": 1}),
    ({"additionalProperties": False, "properties": {"a": {}}}, {"a": 1}, {"a": 1, "b": 2}),
    ({"additionalProperties": {"type": "integer"}}, {"z": 1}, {"z": "1"}),
    ({"enum": ["a", 1]}, 1, True),
    ({"const": 1}, 1, True),
    ({"const": {"a": [1]}}, {"a": [1]}, {"a": [True]}),
    ({"pattern": "^a+$"}, "aaa", "aaa\n"),
    ({"type": "array", "items": {"type": "integer"}}, [1, 2], [1, "2"]),
    ({"minLength": 2}, "ab", "a"),
    ({"maxLength": 1}, "a", "ab"),
    ({"minimum": 1}, 1, 0),
    ({"$defs": {"n": {"type": "integer"}}, "$ref": "#/$defs/n"}, 1, "1"),
    ({"$defs": {"a": {"$ref": "#/$defs/b"}, "b": {"const": 2}}, "items": {"$ref": "#/$defs/a"}}, [2], [3]),
    ({"if": {"const": 1}, "then": False, "else": {"type": "integer"}}, 2, 1),
])
def test_validator_keyword(schema, good, bad):
    val = v(schema)
    assert val.errors(good) == []
    assert val.errors(bad) != []


@pytest.mark.parametrize("schema", [
    {"oneOf": [{}]},
    {"format": "date-time"},
    {"$ref": "other.json#/x"},
    {"$ref": "#/$defs/missing"},
    {"items": [{}]},
    {"type": "int"},
    {"pattern": "("},
    {"properties": {"a": {"anyOf": []}}},
])
def test_validator_rejects_unsupported_or_malformed_schema(schema):
    with pytest.raises(ss.SchemaError):
        v(schema)


def test_cli_exit_codes(tmp_path):
    good = tmp_path / "good.json"
    bad = tmp_path / "bad.json"
    good.write_text(json.dumps(dict(EXAMPLES)["docs/how-it-works.md#1"]), encoding="utf-8")
    bad.write_text(json.dumps(core_envelope()), encoding="utf-8")
    assert ss.main([str(SCHEMA_PATH), str(good)]) == 0
    assert ss.main([str(SCHEMA_PATH), str(good), str(bad)]) == 1
    assert ss.main([str(SCHEMA_PATH)]) == 2
