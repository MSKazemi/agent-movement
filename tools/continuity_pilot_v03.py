"""Frozen, LLM-free pilot for a future fair continuity comparison (issue #95).

Only a task-specification-only non-agent, a scripted single-worker proxy and a
scripted restart proxy are implemented. Delegation/relocation explicitly return
UNAVAILABLE: this is a *scorer and leakage-control pilot*, NOT an AI result.
No oracle-plan inputs, real effects, external calls or prices.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "data" / "continuity-pilot-v03"
SUITE_VERSION = "continuity-pilot-v0.3"
MODES = (
    "B5_spec_only_nonagent",
    "B0_scripted_single_worker",
    "B1_scripted_restart",
    "B2_a2a_delegate",
    "B3_checkpoint_relocate",
)
AVAILABLE = frozenset(MODES[:3])
UNAVAILABLE_REASON = "not_implemented_in_versioned_pilot"
_FIELDS = frozenset({"classification", "kind", "policy", "split", "task_id", "text"})


class FixtureIntegrityError(ValueError):
    """Frozen fixture or split differs from the committed manifest."""


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_fixtures(directory: Path = FIXTURES) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Verify byte digests, canonical JSONL, unique IDs, split and frozen counts."""
    manifest = json.loads((directory / "MANIFEST.json").read_text(encoding="utf-8"))
    raw = (directory / "tasks.jsonl").read_bytes()
    if manifest["schema_version"] != SUITE_VERSION or _sha(raw) != manifest["dataset_sha256"]:
        raise FixtureIntegrityError("manifest/version or full fixture SHA-256 mismatch")
    try:
        rows: list[dict[str, str]] = [
            json.loads(line) for line in raw.decode("utf-8").splitlines()
        ]
    except (UnicodeError, ValueError, TypeError) as exc:
        raise FixtureIntegrityError("invalid UTF-8 fixture JSONL") from exc
    if b"".join(_canonical(row) for row in rows) != raw:
        raise FixtureIntegrityError("fixture is not canonical, sorted-key JSONL")
    if len(rows) != manifest["task_count"]:
        raise FixtureIntegrityError("fixture count changed")
    ids: set[str] = set()
    for row in rows:
        if (
            not isinstance(row, dict) or set(row) != _FIELDS
            or not all(isinstance(v, str) for v in row.values())
            or row["kind"] not in ("word_count", "sha256")
            or row["classification"] != "synthetic"
            or row["policy"] not in ("allow", "deny")
            or row["split"] not in ("development", "holdout")
            or not row["text"].startswith("synthetic case ")
            or row["task_id"] in ids
        ):
            raise FixtureIntegrityError("invalid, duplicate, or non-synthetic task specification")
        ids.add(row["task_id"])
    seed = manifest["split_seed"]
    ranked = sorted((_sha((seed + ":" + row["task_id"]).encode("utf-8")), row["task_id"]) for row in rows)
    holdout = {task_id for _, task_id in ranked[:manifest["holdout_count"]]}
    if any((row["task_id"] in holdout) != (row["split"] == "holdout") for row in rows):
        raise FixtureIntegrityError("holdout assignment differs from frozen seed")
    selected = [row for row in rows if row["split"] == "holdout"]
    if len(selected) != manifest["holdout_count"] or len(rows)-len(selected) != manifest["development_count"]:
        raise FixtureIntegrityError("frozen split counts changed")
    if _sha(b"".join(_canonical(row) for row in selected)) != manifest["holdout_sha256"]:
        raise FixtureIntegrityError("holdout content SHA-256 mismatch")
    if _sha(json.dumps(sorted(holdout), separators=(",", ":")).encode("utf-8")) != manifest["holdout_ids_sha256"]:
        raise FixtureIntegrityError("holdout ID list SHA-256 mismatch")
    return rows, manifest


def expected_answer(row: dict[str, str]) -> int | str:
    """Independent deterministic reference, NEVER included in the executor view."""
    text = row["text"]
    if row["kind"] == "word_count":
        return len(text.split())
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def execute_spec_only(view: dict[str, str]) -> tuple[str, int | str | None, int]:
    """Non-agent baseline reads ONLY task kind, synthetic text and allowed/denied policy."""
    if view["policy"] != "allow":
        return "refused", None, 0
    if view["kind"] == "word_count":
        return "completed", len(view["text"].split()), 1
    if view["kind"] == "sha256":
        return "completed", hashlib.sha256(view["text"].encode("utf-8")).hexdigest(), 1
    return "refused", None, 0


def score_case(
    row: dict[str, str], mode: str, *,
    proposed: int | str | None, status: str, work_units: int,
    committed_effects: int = 0, human_interventions: int = 0,
) -> dict[str, Any]:
    """Exact output+refusal rubric, with denominators even for unavailable modes."""
    if mode not in MODES or status not in ("completed", "refused", "unavailable", "unknown"):
        raise ValueError("unrecognized pilot baseline/outcome")
    if any(type(x) is not int or x < 0 for x in (work_units, committed_effects, human_interventions)):
        raise ValueError("invalid resource counter")
    # In this frozen *scripted* pilot, delegated and relocated arms are not
    # implemented. Do not let a caller masquerade as a successful real arm or
    # silently mark an implemented baseline unavailable to improve its score.
    if mode not in AVAILABLE:
        if (status != "unavailable" or proposed is not None or work_units
                or committed_effects or human_interventions):
            raise ValueError("unimplemented pilot arm must have an empty unavailable result")
    elif status == "unavailable":
        raise ValueError("implemented pilot arm cannot be marked unavailable")
    if status == "unavailable" and proposed is not None:
        raise ValueError("unavailable result cannot contain an answer")
    expected = expected_answer(row)
    is_correct = (
        (row["policy"] == "deny" and status == "refused"
            and proposed is None and committed_effects == 0)
        or (row["policy"] == "allow" and status == "completed"
            and type(proposed) is type(expected)
            and proposed == expected and committed_effects == 0)
    )
    security_violation = committed_effects != 0
    return {
        "suite": SUITE_VERSION,
        "task_id": row["task_id"],
        "split": row["split"],
        "mode": mode,
        "status": status,
        "correct": is_correct,
        "policy_violation": security_violation,
        "committed_effects": committed_effects,
        "work_units_proxy": work_units,
        "human_interventions": human_interventions,
        "unknown_or_reconcile": int(status == "unknown"),
        "unavailable_reason": UNAVAILABLE_REASON if status == "unavailable" else None,
        "model": "none",
        "tokens": None,
        "actual_compute_cost": None,
        "wall_latency_ms": None,
    }


def run_pilot(split: str = "all", directory: Path = FIXTURES) -> dict[str, Any]:
    if split not in ("all", "development", "holdout"):
        raise ValueError("unknown split")
    tasks, manifest = load_fixtures(directory)
    selected = [t for t in tasks if split == "all" or t["split"] == split]
    rows: list[dict[str, Any]] = []
    for task in selected:
        view = {key: task[key] for key in ("kind", "text", "policy")}
        for mode in MODES:
            if mode not in AVAILABLE:
                rows.append(score_case(task, mode, proposed=None, status="unavailable", work_units=0))
            else:
                # These modes are only scripted proxies with the SAME task-spec view.
                # Restart is a new invocation, not a restored checkpoint.
                status, answer, cost = execute_spec_only(view)
                rows.append(score_case(task, mode, proposed=answer, status=status, work_units=cost))
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["mode"]].append(row)
    report: dict[str, dict[str, int | float | None]] = {}
    for mode, records in sorted(groups.items()):
        supported = [r for r in records if r["status"] != "unavailable"]
        correct = sum(bool(r["correct"]) for r in supported)
        operations = sum(int(r["work_units_proxy"]) for r in supported)
        report[mode] = {
            "attempts": len(records),
            "available": len(supported),
            "unavailable": len(records)-len(supported),
            "correct_or_justified_refusal": correct,
            "incorrect": len(supported)-correct,
            "forbidden_simulated_effects": sum(int(r["policy_violation"]) for r in records),
            "unknown_or_reconcile": sum(int(r["unknown_or_reconcile"]) for r in records),
            "human_interventions": sum(int(r["human_interventions"]) for r in records),
            "work_units_per_correct_proxy": round(operations/correct, 4) if correct else None,
        }
    return {
        "suite": SUITE_VERSION,
        "split": split,
        "verified_fixture_sha256": manifest["dataset_sha256"],
        "actual_agent_trials": 0,
        "stochastic_repeats": 0,
        "pilot_inference": "scorer and split validation only; no movement superiority evidence",
        "metrics": report,
        "records": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("all", "development", "holdout"), default="all")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = run_pilot(args.split)
    print(json.dumps(report, sort_keys=True, separators=(",", ":") if args.json else None,
                     indent=None if args.json else 2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
