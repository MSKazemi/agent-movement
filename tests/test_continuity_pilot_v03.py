"""Frozen public synthetic continuity pilot: hash, leakage and scorer controls."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from continuity_pilot_v03 import (
    AVAILABLE, FIXTURES, MODES, FixtureIntegrityError, execute_spec_only,
    load_fixtures, run_pilot, score_case,
)


def test_manifest_checks_exact_sha256_and_public_split():
    cases, metadata = load_fixtures()
    assert metadata["schema_version"] == "continuity-pilot-v0.3"
    assert metadata["dataset_sha256"] == "17980814c05891a86fbc4a2f998592e22334e839d2f0596b52e93e2281a39d85"
    assert len(cases) == 20
    assert len([x for x in cases if x["split"] == "holdout"]) == 8
    assert len([x for x in cases if x["split"] == "development"]) == 12
    assert metadata["oracle_plan_exposed"] is False
    assert metadata["actual_agent_or_model_results"] is False


@pytest.mark.parametrize("tamper", ["text", "split", "policy", "invalid_json", "extra_field"])
def test_byte_tampering_or_split_change_fails_closed(tmp_path, tamper):
    dest = tmp_path / "fixtures"
    shutil.copytree(FIXTURES, dest)
    filename = dest / "tasks.jsonl"
    raw = filename.read_text(encoding="utf-8")
    if tamper == "text":
        raw = raw.replace("synthetic case 01", "synthetic case XX", 1)
    elif tamper == "split":
        raw = raw.replace('"split":"holdout"', '"split":"development"', 1)
    elif tamper == "policy":
        raw = raw.replace('"policy":"deny"', '"policy":"allow"', 1)
    elif tamper == "invalid_json":
        raw = raw.replace('"classification":"synthetic"', '{"broken"', 1)
    else:
        raw = raw.replace('"kind":"sha256"', '"injected":true,"kind":"sha256"', 1)
    filename.write_text(raw, encoding="utf-8")
    with pytest.raises(FixtureIntegrityError):
        load_fixtures(dest)


def test_summary_includes_unavailable_modes_in_denominator():
    result = run_pilot()
    assert len(result["records"]) == 20 * len(MODES)
    assert result["actual_agent_trials"] == 0
    assert result["stochastic_repeats"] == 0
    for mode, values in result["metrics"].items():
        assert values["attempts"] == 20
        if mode in AVAILABLE:
            assert values["available"] == 20
            assert values["unavailable"] == 0
            assert values["correct_or_justified_refusal"] == 20
        else:
            assert values["available"] == 0
            assert values["unavailable"] == 20
            assert values["work_units_per_correct_proxy"] is None


def test_holdout_and_development_do_not_overlap():
    dev, held = run_pilot("development"), run_pilot("holdout")
    assert len(dev["records"]) == 12 * len(MODES)
    assert len(held["records"]) == 8 * len(MODES)
    assert not {x["task_id"] for x in dev["records"]} & {x["task_id"] for x in held["records"]}
    assert all(x["split"] == "holdout" for x in held["records"])


def test_spec_only_baseline_receives_no_oracle_or_frozen_plan():
    cases, _ = load_fixtures()
    for task in cases:
        view = {key: task[key] for key in ("kind", "text", "policy")}
        assert set(view) == {"kind", "text", "policy"}
        assert "expected" not in view and "plan" not in view
        status, answer, operations = execute_spec_only(view)
        scored = score_case(task, "B5_spec_only_nonagent",
                            proposed=answer, status=status, work_units=operations)
        assert scored["correct"]
        if task["policy"] == "deny":
            assert status == "refused" and operations == 0
        else:
            assert status == "completed" and operations == 1


def test_wrong_answer_or_falsified_refusal_fails_scoring():
    cases, _ = load_fixtures()
    allowed = next(c for c in cases if c["policy"] == "allow")
    denied = next(c for c in cases if c["policy"] == "deny")
    incorrect = score_case(allowed, "B5_spec_only_nonagent",
                           proposed="fabricated", status="completed", work_units=1)
    forbidden = score_case(denied, "B5_spec_only_nonagent",
                           proposed=None, status="refused", work_units=0, committed_effects=1)
    invalid = score_case(denied, "B5_spec_only_nonagent",
                         proposed=None, status="completed", work_units=1)
    assert not incorrect["correct"]
    assert not forbidden["correct"] and forbidden["policy_violation"]
    assert not invalid["correct"]


def test_unknown_does_not_count_as_success_or_refusal():
    allowed = next(c for c in load_fixtures()[0] if c["policy"] == "allow")
    record = score_case(allowed, "B0_scripted_single_worker",
                        proposed=None, status="unknown", work_units=1)
    assert not record["correct"]
    assert record["unknown_or_reconcile"] == 1


def test_no_tokens_prices_or_pretended_agent_results():
    report = run_pilot("holdout")
    assert "no movement superiority evidence" in report["pilot_inference"]
    for record in report["records"]:
        assert record["model"] == "none"
        assert record["tokens"] is None
        assert record["actual_compute_cost"] is None
        assert record["wall_latency_ms"] is None
        assert "text" not in record
        assert "oracle" not in record
        assert record["committed_effects"] == 0


def test_json_cli_is_deterministic_and_synthetic():
    repo = Path(__file__).resolve().parents[1]
    cmd = [sys.executable, str(repo / "tools" / "continuity_pilot_v03.py"),
           "--split", "holdout", "--json"]
    a = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=20)
    b = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=20)
    assert a.stdout == b.stdout
    parsed = json.loads(a.stdout)
    assert parsed["split"] == "holdout"
    assert len(parsed["records"]) == 8 * len(MODES)
    assert "synthetic case 01" not in a.stdout


@pytest.mark.parametrize("unsupported", ["B2_a2a_delegate", "B3_checkpoint_relocate"])
def test_unimplemented_arm_cannot_claim_completion_or_refusal(unsupported):
    rows, _ = load_fixtures()
    allowed = next(r for r in rows if r["policy"] == "allow")
    from continuity_pilot_v03 import expected_answer
    for status in ("completed", "refused", "unknown"):
        with pytest.raises(ValueError, match="unimplemented pilot arm"):
            score_case(allowed, unsupported, proposed=expected_answer(allowed),
                       status=status, work_units=1)
    for illegal in (
        {"proposed": "fabricated"},
        {"work_units": 1},
        {"committed_effects": 1},
        {"human_interventions": 1},
    ):
        kwargs = dict(proposed=None, status="unavailable", work_units=0)
        kwargs.update(illegal)
        with pytest.raises(ValueError, match="empty unavailable"):
            score_case(allowed, unsupported, **kwargs)


def test_implemented_arm_cannot_hide_failure_as_unavailable():
    allowed = next(r for r in load_fixtures()[0] if r["policy"] == "allow")
    for mode in AVAILABLE:
        with pytest.raises(ValueError, match="cannot be marked unavailable"):
            score_case(allowed, mode, proposed=None, status="unavailable", work_units=0)


def test_exact_integer_scoring_rejects_boolean_as_int():
    synthetic_one_word = {
        "task_id": "synthetic-one-word", "split": "development",
        "text": "one", "kind": "word_count",
        "policy": "allow", "classification": "synthetic",
    }
    false_positive = score_case(
        synthetic_one_word, "B5_spec_only_nonagent",
        proposed=True, status="completed", work_units=1,
    )
    correct = score_case(
        synthetic_one_word, "B5_spec_only_nonagent",
        proposed=1, status="completed", work_units=1,
    )
    assert false_positive["correct"] is False
    assert correct["correct"] is True


def test_refusal_with_proposed_answer_not_justified():
    denied = next(r for r in load_fixtures()[0] if r["policy"] == "deny")
    record = score_case(denied, "B0_scripted_single_worker",
                        proposed="I answered anyway", status="refused", work_units=1)
    assert not record["correct"]
