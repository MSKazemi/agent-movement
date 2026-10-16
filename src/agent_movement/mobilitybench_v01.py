"""MobilityBench v0.1 and v0.2: frozen synthetic task-continuity baselines (deterministic, LLM-free).

  python -m agent_movement.mobilitybench verify --suite v0.1
  python -m agent_movement.mobilitybench run --suite v0.1 --out results.jsonl
  python -m agent_movement.mobilitybench run --suite v0.2 --out results-v0.2.jsonl
  python -m agent_movement.mobilitybench report --in results.jsonl --out report.md

A scripted interpreter executes frozen synthetic plans; there are no model calls,
network requests or real side effects. Effects are simulated commits to the PR #6
fenced SQLite gateway, and the local delegate baseline uses the PR #6
HandoffReceiver in-process. Two baselines need an optional extra and are scored
only when it is installed (see mobilitybench_optional): B2 delegates over the
official A2A v1 SDK to a loopback worker (extra ``a2a``), and B3 relocates a LangGraph
checkpoint on one pinned runtime (extra ``relocation``). Without its extra, a mode
is emitted as an explicit ``unavailable`` record, as is cross-framework
reconstruction (B4), which is not implemented.

Suite v0.2 (issue #40) runs the same 18 tasks with its own frozen release: five
more fault kinds (two mid-step crashes inside an effect step, three origin<->destination
partitions), a frozen seeded schedule (schedule.jsonl), the ``restart_stable_ids``
variant of B1 that reuses deterministic effect IDs, and an explicit
``fault_not_applied_reason`` on every record whose mode cannot be faulted that way.
v0.1 records and fixtures are unchanged.
Protocol, rubrics and validity threats: docs/mobilitybench-v0.1.md, docs/mobilitybench-v0.2.md.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import platform
import re
import shutil
import sqlite3
import statistics
import sys
import tempfile
import textwrap
import time
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

from .core import (
    ID,
    SCHEMA_VERSION,
    Approval,
    Conflict,
    ContractError,
    EffectGateway,
    HandoffReceiver,
    PolicyDenied,
    SQLiteStore,
    canonical,
    digest,
    parse_json,
)
from .mobilitybench import CANARY, exception_outcome
from .trust import HmacKey, issue_revocation

SUITE_VERSION = "mobilitybench-v0.1"
SUITE_VERSION_V02 = "mobilitybench-v0.2"
# 0.2.0 (issue #31): B2 (A2A) and B3 (checkpoint relocation) are scored when their extra is
# installed. Tasks, rubrics, interpreter and ground truth are unchanged, so the frozen
# fixture release (and SUITE_VERSION) stays the same.
# 0.3.0 (issue #40): adds suite v0.2 (its own frozen release). Every v0.1 outcome
# fingerprint is unchanged; v0.2 records carry the extra fields listed in V02_RECORD_FIELDS.
HARNESS_VERSION = "0.3.0"
EXECUTOR = "deterministic-interpreter-v0.1"
MODEL = "none"
FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"
FIXTURE_FILES = ("tasks.jsonl", "ground_truth.jsonl", "negative.jsonl", "seeds.json")
MANIFEST_NAME = "MANIFEST.json"
FAMILIES = ("document", "coding", "tools")
FAULT_KINDS = ("none", "origin_preempted", "effect_ack_lost", "duplicate_delivery", "stale_origin_returns")
# v0.2 fault kinds. A crash fires once, inside the first execution of the scheduled effect
# step that forms an effect intent: before the commit reaches the ledger, or after it is
# durable but before its acknowledgement reaches the executor. A partition acts once, on the
# first message between origin and destination (or on the first reply to it).
CRASH_KINDS = ("crash_before_effect_commit", "crash_after_effect_commit")
PARTITION_KINDS = ("partition_drop_request", "partition_drop_reply", "partition_delay")
FAULT_KINDS_V02 = FAULT_KINDS + CRASH_KINDS + PARTITION_KINDS
TRANSFERABLE = ("synthetic", "public")


@dataclass(frozen=True)
class Suite:
    """One frozen suite release: its fixture files, fault kinds, extra modes and extra metrics."""

    key: str
    version: str
    files: tuple[str, ...]
    fault_kinds: tuple[str, ...]
    extra_modes: tuple[str, ...] = ()
    extra_metrics: tuple[str, ...] = ()
    doc: str = "docs/mobilitybench-v0.1.md"


V02_METRIC_KEYS = ("effect_id_conflicts", "messages_dropped", "messages_delayed", "retries")
V02_RECORD_FIELDS = ("crash_step", "fault_not_applied_reason", *V02_METRIC_KEYS)
SUITE_SPECS: dict[str, Suite] = {
    "v0.1": Suite("v0.1", SUITE_VERSION, FIXTURE_FILES, FAULT_KINDS),
    "v0.2": Suite("v0.2", SUITE_VERSION_V02, (*FIXTURE_FILES, "schedule.jsonl"), FAULT_KINDS_V02,
                  extra_modes=("restart_stable_ids",), extra_metrics=V02_METRIC_KEYS,
                  doc="docs/mobilitybench-v0.2.md"),
}
SUITES = {key: spec.version for key, spec in SUITE_SPECS.items()}
SUITE_BY_VERSION = {spec.version: spec for spec in SUITE_SPECS.values()}


def suite_spec(suite: str) -> Suite:
    if suite not in SUITE_SPECS:
        raise FixtureError(f"unknown suite {suite!r}; available: {', '.join(SUITE_SPECS)}")
    return SUITE_SPECS[suite]

# Optional extras a baseline needs: pyproject extra -> import names and distributions to report.
EXTRAS: dict[str, dict[str, tuple[str, ...]]] = {
    "a2a": {"modules": ("a2a", "httpx", "starlette", "uvicorn", "google.protobuf"),
            "distributions": ("a2a-sdk",)},
    "relocation": {"modules": ("langgraph", "langgraph.checkpoint.sqlite"),
                   "distributions": ("langgraph", "langgraph-checkpoint", "langgraph-checkpoint-sqlite")},
}
# Baseline modes. `extra` names the optional extra a mode needs; `implemented: False` marks a
# baseline with no implementation. Unavailable modes are emitted as explicit records, never dropped.
MODE_SPECS: dict[str, dict[str, Any]] = {
    "keep_on_origin": {"baseline": "B0", "tracking": "-"},
    "restart_on_destination": {"baseline": "B1", "tracking": "-"},
    "local_delegate": {"baseline": "B2-local", "tracking": "PR #6 HandoffReceiver, in-process; not A2A"},
    "a2a_delegate": {"baseline": "B2", "extra": "a2a",
                     "tracking": "issue #31: issue #7 A2A v1 adapter (official a2a-sdk), loopback HTTP"},
    "checkpoint_relocate": {"baseline": "B3", "extra": "relocation",
                            "tracking": "issue #31: issue #9 fenced LangGraph checkpoint relocation"},
    "cross_framework_reconstruct": {"baseline": "B4", "implemented": False,
                                    "tracking": "not scheduled (AM-14; after issue #9)"},
}


def extra_available(extra: str) -> bool:
    """True when every module the extra provides can be found."""
    try:
        return all(importlib.util.find_spec(name) is not None for name in EXTRAS[extra]["modules"])
    except (ImportError, ValueError):  # a parent package is missing or broken
        return False


def mode_table(available: Callable[[str], bool] = extra_available) -> dict[str, dict[str, str]]:
    """Resolve each mode's status in this environment; `available(extra)` is injectable for tests."""
    table = {}
    for mode, spec in MODE_SPECS.items():
        extra = spec.get("extra")
        if spec.get("implemented", True) is False:
            status, reason = "unavailable", "baseline_not_implemented"
        elif extra is not None and not available(extra):
            status, reason = "unavailable", f"extra_not_installed:{extra}"
        else:
            status, reason = "implemented", None
        row = {"baseline": spec["baseline"], "status": status, "tracking": spec["tracking"]}
        if extra is not None:
            row["extra"] = extra
        if reason is not None:
            row["unavailable_reason"] = reason
        table[mode] = row
    return table


MODES: dict[str, dict[str, str]] = mode_table()

# Modes a later suite adds after an existing mode (v0.1 runs never include them).
SUITE_MODE_SPECS: dict[str, dict[str, Any]] = {
    "restart_stable_ids": {"baseline": "B1-stable", "after": "restart_on_destination",
                           "tracking": "issue #40: B1 with deterministic effect IDs (ledger wins on conflict)"},
}
MODE_ORDER = ("keep_on_origin", "restart_on_destination", "restart_stable_ids", "local_delegate",
              "a2a_delegate", "checkpoint_relocate", "cross_framework_reconstruct")


def modes_for(suite: str = "v0.1") -> dict[str, dict[str, str]]:
    """The suite's mode table in baseline order; built from MODES, so test patches of it apply."""
    extra = suite_spec(suite).extra_modes
    table: dict[str, dict[str, str]] = {}
    for mode, info in MODES.items():
        table[mode] = info
        for added in extra:
            if SUITE_MODE_SPECS[added]["after"] == mode:
                spec = SUITE_MODE_SPECS[added]
                table[added] = {"baseline": spec["baseline"], "status": "implemented", "tracking": spec["tracking"]}
    return table


def extras_versions() -> dict[str, dict[str, str] | None]:
    """Installed distribution versions per extra (None when the extra is missing), for run_version."""
    found: dict[str, dict[str, str] | None] = {}
    for extra, spec in EXTRAS.items():
        try:
            found[extra] = ({name: metadata.version(name) for name in spec["distributions"]}
                            if extra_available(extra) else None)
        except metadata.PackageNotFoundError:
            found[extra] = None
    return found

# Pure ops that map onto the PR #6 0.1.0-draft envelope task kinds.
DELEGABLE = {"count_words": "word_count", "count_words_out": "word_count",
             "count_words_file": "word_count", "sha256_out": "sha256", "sha256_file": "sha256"}
OPS = set(DELEGABLE) | {"extract", "replace", "append_line", "check_contains", "lookup", "effect", "reserve"}
CONSTRAINT_RULES = ("redact_terms", "forbid_path", "max_line_length", "require_label")
POLICY_RULES = ("forbid_tool", "allowed_recipients")
TASK_FIELDS = {"task_id", "family", "title", "classification", "input", "initial_constraints",
               "plan", "session_events", "movement_at"}
SENTENCE = re.compile(r"(?<=[.!?])\s+")
VERDICTS = ("pass", "known_gap", "gap_closed", "fail")
VOLATILE = {"elapsed_ms", "run_id", "repeat", "outcome_fingerprint", "record_type", "run_version"}


class FixtureError(ValueError):
    """Frozen fixtures are missing, malformed or do not match the release manifest."""


class SimulatedCrash(Exception):
    """A v0.2 mid-step crash: the executor's process dies inside plan step ``step``."""

    def __init__(self, step: int, kind: str):
        super().__init__(f"simulated {kind} at step {step}")
        self.step = step
        self.kind = kind


# --------------------------------------------------------------------------- fixtures

def fixture_dir(suite: str = "v0.1", override: str | Path | None = None) -> Path:
    suite_spec(suite)
    return Path(override) if override is not None else FIXTURE_ROOT / SUITES[suite]


def file_digests(directory: Path, files: tuple[str, ...] = FIXTURE_FILES) -> dict[str, str]:
    try:
        return {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in files}
    except OSError as exc:
        raise FixtureError("missing fixture file") from exc


def release_digest(files: dict[str, str]) -> str:
    """SHA-256 over a `sha256sum`-format listing of the fixture files."""
    listing = "".join(f"{files[name]}  {name}\n" for name in sorted(files))
    return hashlib.sha256(listing.encode("utf-8")).hexdigest()


def verify_fixtures(directory: Path, suite: str = "v0.1") -> dict[str, Any]:
    """Fail closed unless every frozen file matches the committed release manifest."""
    spec = suite_spec(suite)
    try:
        manifest = json.loads((directory / MANIFEST_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FixtureError("missing or unreadable release manifest") from exc
    if not isinstance(manifest, dict) or manifest.get("suite_version") != spec.version:
        raise FixtureError("manifest suite version mismatch")
    expected = manifest.get("files")
    if not isinstance(expected, dict) or set(expected) != set(spec.files):
        raise FixtureError("manifest file list mismatch")
    actual = file_digests(directory, spec.files)
    bad = sorted(name for name in spec.files if actual[name] != expected[name])
    if bad:
        raise FixtureError("fixture digest mismatch: " + ", ".join(bad))
    if release_digest(actual) != manifest.get("release_digest"):
        raise FixtureError("release digest mismatch")
    return manifest


def _jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        return [parse_json(line.encode("utf-8")) for line in lines if line.strip()]
    except (OSError, ContractError) as exc:
        raise FixtureError(f"unreadable fixture {path.name}") from exc


def _rule(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("rule") not in CONSTRAINT_RULES + POLICY_RULES:
        raise FixtureError("unknown rule")
    return value


def validate_task(task: Any) -> dict[str, Any]:
    if not isinstance(task, dict) or set(task) != TASK_FIELDS:
        raise FixtureError("invalid task fields")
    if not isinstance(task["task_id"], str) or not ID.fullmatch(task["task_id"]):
        raise FixtureError("invalid task_id")
    if task["family"] not in FAMILIES:
        raise FixtureError("unknown family")
    plan = task["plan"]
    if not isinstance(plan, list) or not plan or any(
            not isinstance(op, dict) or op.get("op") not in OPS for op in plan):
        raise FixtureError(f"invalid plan in {task['task_id']}")
    if type(task["movement_at"]) is not int or not 1 <= task["movement_at"] < len(plan):
        raise FixtureError("movement_at must fall strictly inside the plan")
    for rule in task["initial_constraints"]:
        _rule(rule)
    for event in task["session_events"]:
        if (not isinstance(event, dict) or set(event) != {"at", "rule"} or type(event["at"]) is not int
                or not 0 <= event["at"] < len(plan)):
            raise FixtureError("invalid session event")
        _rule(event["rule"])
    return task


@dataclass(frozen=True)
class Fixtures:
    directory: Path
    manifest: dict[str, Any]
    tasks: list[dict[str, Any]]
    truth: dict[str, dict[str, Any]]
    negatives: list[dict[str, Any]]
    seeds: dict[str, Any]
    suite: str = "v0.1"
    # v0.2+: the frozen schedule, (seed, task_id) -> {"fault": kind, "crash_step": int | None}.
    schedule: dict[tuple[int, str], dict[str, Any]] | None = None


def load_fixtures(suite: str = "v0.1", directory: str | Path | None = None,
                  verify: bool = True, check_schedule: bool = True) -> Fixtures:
    """`check_schedule=False` skips comparing schedule.jsonl with the generator (freeze tool only)."""
    spec = suite_spec(suite)
    root = fixture_dir(suite, directory)
    manifest = verify_fixtures(root, suite) if verify else {}
    tasks = [validate_task(t) for t in _jsonl(root / "tasks.jsonl")]
    ids = [t["task_id"] for t in tasks]
    if len(ids) != len(set(ids)):
        raise FixtureError("duplicate task_id")
    truth_path = root / "ground_truth.jsonl"
    truth = {g["task_id"]: g for g in _jsonl(truth_path)} if truth_path.exists() else {}
    negatives = _jsonl(root / "negative.jsonl")
    for case in negatives:
        if (not isinstance(case.get("case_id"), str) or not isinstance(case.get("expected"), str)
                or type(case.get("known_gap")) is not bool
                or (case["known_gap"] and not isinstance(case.get("closed_observation"), str))):
            raise FixtureError("invalid negative fixture")
        if case.get("task") is not None:
            validate_task(case["task"])
    try:
        seeds = json.loads((root / "seeds.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FixtureError("unreadable seed manifest") from exc
    if tuple(seeds.get("fault_kinds", ())) != spec.fault_kinds:
        raise FixtureError("seed manifest fault kinds differ from this harness")
    schedule = None
    if "schedule.jsonl" in spec.files and check_schedule:
        frozen = _jsonl(root / "schedule.jsonl")
        if frozen != schedule_rows(tasks, seeds["seeds"], suite):
            raise FixtureError("frozen fault schedule differs from the seeded generator")
        schedule = {(row["seed"], row["task_id"]): row for row in frozen}
    return Fixtures(root, manifest, tasks, truth, negatives, seeds, suite, schedule)


# --------------------------------------------------------------------------- interpreter

def pure_value(kind: str, text: str) -> int | str:
    """Mirror of the PR #6 receiver's pure task semantics (core.SQLiteStore.receive)."""
    if kind == "word_count":
        return len(text.split())
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sentences(text: str, n: int) -> str:
    """First n sentences; a sentence ends at . ! or ? followed by whitespace."""
    return " ".join(SENTENCE.split(text.strip())[:n])


class AgentState:
    """Everything one executor knows: initial request plus session events it heard."""

    def __init__(self, name: str, task: dict[str, Any], epoch: int):
        self.name = name
        self.epoch = epoch
        self.rules: list[dict[str, Any]] = [dict(r) for r in task["initial_constraints"]]
        data = task["input"]
        self.sections: dict[str, str] = dict(data.get("sections", {}))
        self.original_files: dict[str, str] = dict(data.get("files", {}))
        self.files: dict[str, str] = dict(self.original_files)
        self.inventory: dict[str, int] = dict(data.get("inventory", {}))
        self.out: list[str] = []

    def _of(self, kind: str) -> list[dict[str, Any]]:
        return [r for r in self.rules if r["rule"] == kind]

    def redact(self, text: str) -> str:
        for rule in self._of("redact_terms"):
            for term in rule["terms"]:
                text = text.replace(term, "[REDACTED]")
        return text

    def emit(self, line: str) -> None:
        self.out.append(self.redact(line))

    def label(self, payload: str) -> str:
        for rule in self._of("require_label"):
            if not payload.startswith(rule["label"]):
                payload = f"{rule['label']} {payload}"
        return payload

    def wrap(self, text: str) -> str:
        limits = [r["n"] for r in self._of("max_line_length")]
        if not limits:
            return text
        lines: list[str] = []
        for line in text.split("\n"):
            lines.extend(textwrap.wrap(line, min(limits), break_on_hyphens=False) or [""])
        return "\n".join(lines)

    def path_allowed(self, path: str) -> bool:
        return all(r["path"] != path for r in self._of("forbid_path"))

    def tool_allowed(self, tool: str, to: str) -> bool:
        if any(r["tool"] == tool for r in self._of("forbid_tool")):
            return False
        return all(r["tool"] != tool or to in r["recipients"] for r in self._of("allowed_recipients"))

    def output(self) -> dict[str, Any]:
        return {"out": self.out,
                "files": {p: hashlib.sha256(c.encode("utf-8")).hexdigest() for p, c in sorted(self.files.items())},
                "inventory": dict(sorted(self.inventory.items()))}


def pure_input(state: AgentState, op: dict[str, Any]) -> tuple[str, str, str]:
    name = op["op"]
    if name == "count_words":
        return "word_count", state.sections[op["section"]], f"words({op['section']})"
    if name in ("count_words_out", "sha256_out"):
        return DELEGABLE[name], "\n".join(state.out), ("words(out)" if name == "count_words_out" else "sha256(out)")
    return DELEGABLE[name], state.files[op["path"]], f"{'sha256' if name == 'sha256_file' else 'words'}({op['path']})"


def effect_payload(state: AgentState, op: dict[str, Any]) -> str:
    if op["body"] == "out":
        text = "\n".join(state.out)
    elif op["body"] == "files":
        changed = [f"{p}@{hashlib.sha256(c.encode('utf-8')).hexdigest()[:12]}"
                   for p, c in sorted(state.files.items()) if c != state.original_files.get(p)]
        text = "changed: " + (", ".join(changed) or "none")
    else:
        text = op["body"]
    return state.label(state.redact(text))


Pure = Callable[[int, str, str], "int | str"]


class Attempt:
    """One (task, mode, fault) attempt with its own ephemeral SQLite ledger."""

    def __init__(self, task: dict[str, Any], fault: str, workdir: Path, crash_step: int | None = None,
                 extra_metrics: tuple[str, ...] = ()):
        self.task = task
        self.plan = task["plan"]
        self.m = task["movement_at"]
        self.fault = fault
        self.workdir = workdir
        self.gw_task = task["task_id"]
        self.gateway = EffectGateway(SQLiteStore(workdir / "effects.sqlite"))
        self.committed: list[dict[str, Any]] = []
        self.fault_applied = False
        self._ack_dropped = False
        self.crash_step = crash_step if fault in CRASH_KINDS else None
        self._crashed = False
        self._partitioned = False  # a partition fault acts once per attempt
        self.late_deliveries = 0  # partition_delay: copies the destination receives late
        # "raise" (default): a different payload under an existing effect ID is a Conflict.
        # "ledger_wins" (restart_stable_ids): the ledger keeps the first payload; counted.
        self.conflict_policy = "raise"
        self.step_runs: Counter[int] = Counter()
        self.metrics = dict.fromkeys((
            "unknown_events", "reconciled_events", "stale_commits_fenced", "stale_commits_accepted",
            "duplicate_deliveries_suppressed", "transfer_bytes", "transfer_messages",
            "sensitive_transfers", "steps_executed", "steps_reexecuted", *extra_metrics), 0)
        self.sensitive = sorted({t for r in all_rules(task) if r["rule"] == "redact_terms" for t in r["terms"]})

    def hear(self, state: AgentState, step: int, min_at: int = 0) -> None:
        for event in self.task["session_events"]:
            if event["at"] == step and event["at"] >= min_at:
                state.rules.append(dict(event["rule"]))

    def _account(self, raw: str, copies: int) -> None:
        self.metrics["transfer_bytes"] += len(raw.encode("utf-8")) * copies
        self.metrics["transfer_messages"] += copies
        if any(term in raw for term in self.sensitive):
            self.metrics["sensitive_transfers"] += copies

    def send(self, message: dict[str, Any]) -> int:
        """Account one logical transfer and return how many copies the destination receives.

        duplicate_delivery delivers every message twice. On the first message only,
        partition_drop_request loses the original (the sender retries after its timeout:
        1 copy received, 2 sent) and partition_delay holds it past the timeout (the retry is
        received first, the original arrives late: 2 copies, the last in `late_deliveries`).
        """
        raw = canonical(message)
        copies = 2 if self.fault == "duplicate_delivery" else 1
        if copies == 2:
            self.fault_applied = True
        sent = copies
        if self.fault in ("partition_drop_request", "partition_delay") and not self._partitioned:
            self._partitioned = self.fault_applied = True
            sent = 2  # the original that was lost or held, plus the sender's retry
            self.metrics["retries"] += 1
            if self.fault == "partition_drop_request":
                self.metrics["messages_dropped"] += 1
            else:
                self.metrics["messages_delayed"] += 1
                copies, self.late_deliveries = 2, 1
        self._account(raw, sent)
        return copies

    def resend(self, message: dict[str, Any]) -> None:
        """Account the sender's retry of `message` after its reply was lost."""
        self._account(canonical(message), 1)

    def reply_lost(self) -> bool:
        """partition_drop_reply: True for the first reply only (the destination acted; the sender never hears)."""
        if self.fault != "partition_drop_reply" or self._partitioned:
            return False
        self._partitioned = self.fault_applied = True
        self.metrics["messages_dropped"] += 1
        self.metrics["retries"] += 1
        return True

    def take_late(self) -> int:
        """Copies held by partition_delay that the caller must deliver after the destination acted."""
        late, self.late_deliveries = self.late_deliveries, 0
        return late

    def _crash_now(self, step: int) -> str | None:
        """The scheduled crash kind if this effect intent is the first one formed at the crash step."""
        if self.crash_step is None or self._crashed or step != self.crash_step:
            return None
        self._crashed = self.fault_applied = True
        return self.fault

    def commit(self, state: AgentState, step: int, tool: str, to: str, payload: str, suffix: str) -> None:
        effect_id = f"{self.gw_task}.e{step}{suffix}"
        crash = self._crash_now(step)
        if crash == "crash_before_effect_commit":  # intent formed, nothing reached the ledger
            raise SimulatedCrash(step, crash)
        try:
            new = self.gateway.commit(self.gw_task, state.name, state.epoch, effect_id, payload)
        except Conflict:
            if self.conflict_policy != "ledger_wins":
                raise
            # A deterministic ID already holds a different payload (an earlier owner committed it
            # with context this executor lost): the ledger wins, nothing is overwritten.
            self.metrics["effect_id_conflicts"] += 1
            new = False
        if self.fault == "effect_ack_lost" and not self._ack_dropped:
            # The commit reached the ledger but its acknowledgement was lost: the
            # executor must reconcile, never assume failure and blindly re-send.
            self._ack_dropped = True
            self.fault_applied = True
            self.metrics["unknown_events"] += 1
            if self.gateway.reconcile(self.gw_task, effect_id) != "committed":
                raise RuntimeError("reconcile lost a committed simulated effect")
            self.metrics["reconciled_events"] += 1
        if new:
            self.committed.append({"step": step, "tool": tool, "to": to, "payload": payload})
        if crash == "crash_after_effect_commit":  # durable in the ledger; the ack dies with the process
            raise SimulatedCrash(step, crash)

    def run_step(self, state: AgentState, step: int, suffix: str = "", pure: Pure | None = None) -> None:
        op = self.plan[step]
        name = op["op"]
        self.metrics["steps_executed"] += 1
        self.step_runs[step] += 1
        if name in DELEGABLE:
            kind, text, label = pure_input(state, op)
            value = pure(step, kind, text) if pure else pure_value(kind, text)
            state.emit(f"{label}={value}")
        elif name == "extract":
            state.emit(f"{op['section']}: {_sentences(state.sections[op['section']], op['sentences'])}")
        elif name == "lookup":
            state.emit(f"stock({op['item']})={state.inventory.get(op['item'], 0)}")
        elif name == "check_contains":
            state.emit(f"check({op['path']})={'pass' if op['text'] in state.files[op['path']] else 'fail'}")
        elif name in ("replace", "append_line"):
            path = op["path"]
            if not state.path_allowed(path):
                state.emit(f"skipped({name},{path})")
            elif name == "replace":
                if op["old"] in state.files[path]:
                    state.files[path] = state.wrap(state.files[path].replace(op["old"], op["new"]))
                else:
                    state.emit(f"nomatch({path})")
            else:
                state.files[path] = state.files[path] + state.wrap(op["line"]) + "\n"
        elif name == "effect":
            if not state.tool_allowed(op["tool"], op["to"]):
                state.emit(f"skipped({op['tool']},{op['to']})")
                return
            self.commit(state, step, op["tool"], op["to"], effect_payload(state, op), suffix)
            state.emit(f"effect({op['tool']},{op['to']})=ok")
        elif name == "reserve":
            item, qty = op["item"], op["qty"]
            if not state.tool_allowed("reserve", "inventory-service"):
                state.emit(f"skipped(reserve,{item})")
            elif state.inventory.get(item, 0) < qty:
                state.emit(f"insufficient({item})")
            else:
                self.commit(state, step, "reserve", "inventory-service",
                            state.label(f"reserve {item} x{qty}"), suffix)
                state.inventory[item] -= qty
                state.emit(f"reserved({item})={qty}")

    def run_origin_until_movement(self) -> AgentState:
        origin = AgentState("agent-a", self.task, self.gateway.claim(self.gw_task, "agent-a"))
        for step in range(self.m):
            self.hear(origin, step)
            self.run_step(origin, step)
        return origin


def all_rules(task: dict[str, Any]) -> list[dict[str, Any]]:
    return list(task["initial_constraints"]) + [e["rule"] for e in task["session_events"]]


def _active_rules(task: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    return [(0, r) for r in task["initial_constraints"]] + [(e["at"], e["rule"]) for e in task["session_events"]]


Outcome = tuple[AgentState, str, "str | None"]


def run_keep(att: Attempt) -> Outcome:
    """B0: the origin keeps the task; no transfer. Origin preemption leaves it incomplete."""
    origin = AgentState("agent-a", att.task, att.gateway.claim(att.gw_task, "agent-a"))
    try:
        for step in range(len(att.plan)):
            if att.fault == "origin_preempted" and step == att.m:
                att.fault_applied = True
                return origin, "incomplete", "origin_preempted_no_transfer"
            att.hear(origin, step)
            att.run_step(origin, step)
    except SimulatedCrash:  # v0.2: the only executor died mid-step and nothing recovers the task
        return origin, "incomplete", "origin_crashed_no_recovery"
    return origin, "completed", None


def stale_origin_retry(att: Attempt, origin_epoch: int) -> None:
    """After ownership moved, the old-epoch origin retries its next effect: fenced or accepted."""
    att.fault_applied = True
    effect_steps = [i for i, op in enumerate(att.plan) if op["op"] in ("effect", "reserve")]
    later = [i for i in effect_steps if i >= att.m]
    step = later[0] if later else effect_steps[-1]
    try:
        att.gateway.commit(att.gw_task, "agent-a", origin_epoch, f"{att.gw_task}.e{step}",
                           "stale origin retry")
        att.metrics["stale_commits_accepted"] += 1
        att.committed.append({"step": step, "tool": att.plan[step].get("tool", "reserve"),
                              "to": "stale-origin", "payload": "stale origin retry"})
    except PolicyDenied:
        att.metrics["stale_commits_fenced"] += 1


def run_restart(att: Attempt, stable_ids: bool = False) -> Outcome:
    """B1: destination re-runs the original request from step 0; session context is lost.

    B1 issues fresh effect IDs (``…r1``; ``…r2`` after a destination crash) because it
    cannot know the origin's. ``stable_ids=True`` is the v0.2 ``restart_stable_ids``
    variant: the same deterministic IDs as the origin, so the gateway deduplicates a
    re-issued effect and keeps the first payload when the re-issued one differs.
    v0.2 crashes: an origin crash inside step k moves the task at once (events up to k
    are lost with the origin); a destination crash restarts it from step 0 (no checkpoint).
    """
    origin = AgentState("agent-a", att.task, att.gateway.claim(att.gw_task, "agent-a"))
    heard_until = att.m  # B hears only the session events that arrive after the movement
    try:
        for step in range(att.m):
            att.hear(origin, step)
            att.run_step(origin, step)
    except SimulatedCrash as crash:
        heard_until = crash.step + 1  # the crashed origin had already heard the events up to k
    if att.task["classification"] not in TRANSFERABLE:
        return origin, "refused", "classification_not_transferable"
    request = {"movement_id": f"restart-{att.gw_task}", "task_id": att.gw_task,
               "classification": att.task["classification"], "input": att.task["input"],
               "initial_constraints": att.task["initial_constraints"], "plan": att.plan}
    intake: set[str] = set()

    def receive_request() -> None:
        if request["movement_id"] in intake:  # destination intake dedup by movement ID
            att.metrics["duplicate_deliveries_suppressed"] += 1
        intake.add(request["movement_id"])

    copies = att.send(request)
    late = att.take_late()
    for _ in range(copies - late):
        receive_request()
    epoch = att.gateway.transfer(att.gw_task, "agent-a", origin.epoch, "agent-b")
    if att.fault == "origin_preempted":
        att.fault_applied = True  # origin is gone, restart does not depend on it
    if att.fault == "stale_origin_returns":
        stale_origin_retry(att, origin.epoch)
    if stable_ids:
        att.conflict_policy = "ledger_wins"
    run = 1
    while True:
        dest = AgentState("agent-b", att.task, epoch)
        try:
            for step in range(len(att.plan)):
                att.hear(dest, step, min_at=heard_until)  # only live events after the movement reach B
                # fresh run: no knowledge of origin's effect IDs (unless stable_ids)
                att.run_step(dest, step, suffix="" if stable_ids else f".r{run}")
            break
        except SimulatedCrash as crash:
            if run > 1:
                raise RuntimeError("a scheduled crash fired twice") from crash
            # Same owner and epoch, new process, from step 0; the events the crashed
            # process heard (up to the crash step) are lost with it.
            run, heard_until = 2, max(heard_until, crash.step + 1)
    for _ in range(late):  # the held original arrives after B already started
        receive_request()
    return dest, "completed", None


def delegation_envelope(att: Attempt, step: int, kind: str, text: str) -> dict[str, Any]:
    """The PR #6 0.1.0-draft envelope delegating one pure plan step (shared by B2-local and B2)."""
    tid = att.gw_task
    return {
        "schema_version": SCHEMA_VERSION, "movement_id": f"{tid}.m{step}",
        "logical_task_id": tid, "operation": "delegate",
        "origin": {"agent_id": "agent-a"}, "destination": {"agent_id": "agent-b"},
        "task": {"kind": kind, "text": text},
        "context": {"classification": att.task["classification"]},
        "authority": {"approval_ref": f"approval-{tid}"},
        "execution": {"idempotency_key": f"{tid}.k{step}"},
        "observability": {"trace_id": f"{tid}.t{step}"},
    }


def delegation_approvals(att: Attempt) -> list[Approval]:
    """Receiver-side grants: one per pure task kind, scoped to this task and these two agents."""
    tid = att.gw_task
    approval_class = att.task["classification"] if att.task["classification"] in TRANSFERABLE else "synthetic"
    return [Approval(f"approval-{tid}", tid, "agent-a", "agent-b", kind, classification=approval_class)
            for kind in ("word_count", "sha256")]


def check_receipts(att: Attempt, envelope: dict[str, Any], receipts: list[dict[str, Any]],
                   reply_lost: bool = False) -> int | str:
    """The first receipt must answer `envelope`; every duplicate delivery must replay it.

    `reply_lost` (v0.2 partition_drop_reply): the first receipt never reached the origin,
    which re-sent the same envelope, so the first receipt it holds must be a replay.
    """
    first = receipts[0]
    if (first["status"] != "completed" or first["replayed"] is not reply_lost
            or first["artifact_digest"] != digest(first["artifact"])
            or first["envelope_digest"] != digest(envelope)):
        raise RuntimeError("receipt failed verification")
    if reply_lost:
        att.metrics["duplicate_deliveries_suppressed"] += 1
    for extra in receipts[1:]:
        if not extra["replayed"] or extra["artifact"] != first["artifact"]:
            raise RuntimeError("duplicate delivery executed twice")
        att.metrics["duplicate_deliveries_suppressed"] += 1
    value: int | str = first["artifact"]["value"]
    return value


def deliver_with_receipts(att: Attempt, message: dict[str, Any], call: Callable[[], dict[str, Any]],
                          verify_against: dict[str, Any] | None = None) -> int | str:
    """Deliver one delegation message over the faulted channel and verify its receipts.

    `call()` delivers one copy of `message` to the destination and returns its receipt;
    receipts are verified against `verify_against` (default: `message`, the envelope).
    Shared by B2-local and B2 (A2A); see Attempt.send for the copies and partition rules.
    """
    envelope = message if verify_against is None else verify_against
    copies = att.send(message)
    att.take_late()  # a held original is the last copy: it arrives after the retry was answered
    receipts, lost = [], False
    for _ in range(copies):
        receipt = call()
        att.metrics["transfer_bytes"] += len(canonical(receipt).encode("utf-8"))
        att.metrics["transfer_messages"] += 1
        if not lost and att.reply_lost():  # the receipt never reaches the origin; it retries
            lost = True
            att.resend(message)
            receipt = call()
            att.metrics["transfer_bytes"] += len(canonical(receipt).encode("utf-8"))
            att.metrics["transfer_messages"] += 1
        receipts.append(receipt)
    return check_receipts(att, envelope, receipts, reply_lost=lost)


def delegate_tail(att: Attempt, remote_for: Callable[[Attempt], Any]) -> Outcome:
    """Shared B2 shape: the origin keeps ownership and delegates the pure remainder.

    `remote_for(att)` is a context manager yielding `remote(step, kind, text) -> value`. It is
    entered only after the refusal and pre-emption checks, so nothing is set up or sent before.
    """
    try:
        origin = att.run_origin_until_movement()
    except SimulatedCrash:  # v0.2: the owner died before the movement point; nothing took over
        return AgentState("agent-a", att.task, 1), "incomplete", "origin_crashed_owner_not_transferred"
    blocked = sorted({att.plan[i]["op"] for i in range(att.m, len(att.plan))
                      if att.plan[i]["op"] not in DELEGABLE})
    if blocked:
        return origin, "refused", "incompatible_state:" + "+".join(blocked)
    if att.fault == "origin_preempted":
        att.fault_applied = True
        return origin, "incomplete", "origin_preempted_owner_not_transferred"
    try:
        with remote_for(att) as remote:
            for step in range(att.m, len(att.plan)):
                att.hear(origin, step)
                att.run_step(origin, step, pure=remote)
    except ContractError:
        return origin, "refused", "contract_rejected"
    except PolicyDenied:
        return origin, "refused", "policy_denied"
    except Conflict:
        return origin, "refused", "conflict"
    return origin, "completed", None


@contextmanager
def _local_remote(att: Attempt) -> Iterator[Pure]:
    receiver = HandoffReceiver("agent-b", SQLiteStore(att.workdir / "receiver.sqlite"),
                               delegation_approvals(att))

    def remote(step: int, kind: str, text: str) -> int | str:
        envelope = delegation_envelope(att, step, kind, text)
        return deliver_with_receipts(att, envelope, lambda: receiver.receive(json.loads(canonical(envelope))))

    yield remote


def run_local_delegate(att: Attempt) -> Outcome:
    """B2-local: origin keeps ownership and delegates the pure remainder via PR #6 handoffs."""
    return delegate_tail(att, _local_remote)


def run_restart_stable_ids(att: Attempt) -> Outcome:
    """B1-stable (v0.2): B1 with the origin's deterministic effect IDs."""
    return run_restart(att, stable_ids=True)


RUNNERS: dict[str, Callable[[Attempt], Outcome]] = {
    "keep_on_origin": run_keep,
    "restart_on_destination": run_restart,
    "restart_stable_ids": run_restart_stable_ids,
    "local_delegate": run_local_delegate,
}


def runner_for(mode: str) -> Callable[[Attempt], Outcome]:
    """Stdlib runners live here; optional-extra runners are imported only when their mode runs."""
    if mode in RUNNERS:
        return RUNNERS[mode]
    from .mobilitybench_optional import OPTIONAL_RUNNERS
    return OPTIONAL_RUNNERS[mode]


# --------------------------------------------------------------------------- evaluation

def check_constraint(rule: dict[str, Any], task: dict[str, Any], state: AgentState,
                     committed: list[dict[str, Any]]) -> bool:
    payloads = [c["payload"] for c in committed]
    kind = rule["rule"]
    if kind == "redact_terms":
        blob = "\n".join(state.out + payloads)
        return not any(term in blob for term in rule["terms"])
    if kind == "forbid_path":
        return bool(state.files.get(rule["path"]) == task["input"].get("files", {}).get(rule["path"]))
    if kind == "max_line_length":
        return all(len(line) <= rule["n"] for content in state.files.values() for line in content.split("\n"))
    if kind == "require_label":
        return all(p.startswith(rule["label"]) for p in payloads)
    raise FixtureError(f"no evaluator for {kind}")


def count_policy_violations(task: dict[str, Any], committed: list[dict[str, Any]]) -> int:
    """A committed effect violates a policy rule active at (or before) its plan step."""
    violations = 0
    for effect in committed:
        for at, rule in _active_rules(task):
            if effect["step"] < at:
                continue
            if rule["rule"] == "forbid_tool" and effect["tool"] == rule["tool"]:
                violations += 1
                break
            if (rule["rule"] == "allowed_recipients" and effect["tool"] == rule["tool"]
                    and effect["to"] not in rule["recipients"]):
                violations += 1
                break
    return violations


def evaluate(task: dict[str, Any], truth: dict[str, Any], state: AgentState, att: Attempt,
             completed: bool) -> dict[str, Any]:
    committed = att.committed
    expected = {(e["step"], e["tool"], e["to"], e["payload_digest"]) for e in truth["expected_effects"]}
    keys = [(c["step"], c["tool"], c["to"], hashlib.sha256(c["payload"].encode("utf-8")).hexdigest())
            for c in committed]
    per_step = Counter(c["step"] for c in committed)
    duplicates = sum(n - 1 for n in per_step.values())
    unexpected = sum(1 for k in keys if k not in expected)
    policy = count_policy_violations(task, committed) + att.metrics["stale_commits_accepted"]
    constraint_rules = [r for r in all_rules(task) if r["rule"] in CONSTRAINT_RULES]
    result: dict[str, Any] = {
        "constraints_total": len(constraint_rules),
        "policy_violations": policy,
        "duplicate_effects": duplicates,
        "unexpected_effects": unexpected,
        "effects_committed": len(committed),
        "output_correct": None, "constraints_preserved": None, "missing_effects": None, "task_correct": None,
    }
    if completed:
        output_ok = digest(state.output()) == truth["output_digest"]
        preserved = sum(check_constraint(r, task, state, committed) for r in constraint_rules)
        missing = len(expected - set(keys))
        result.update(output_correct=output_ok, constraints_preserved=preserved, missing_effects=missing,
                      task_correct=bool(output_ok and preserved == len(constraint_rules) and policy == 0
                                        and duplicates == 0 and unexpected == 0 and missing == 0))
    return result


def _ledger_rows(path: Path) -> int:
    db = sqlite3.connect(path)
    try:
        count: int = db.execute("SELECT COUNT(*) FROM effects").fetchone()[0]
        return count
    finally:
        db.close()


METRIC_KEYS = ("task_correct", "output_correct", "constraints_preserved", "constraints_total",
               "policy_violations", "duplicate_effects", "unexpected_effects", "missing_effects",
               "effects_committed", "unknown_events", "reconciled_events", "stale_commits_fenced",
               "stale_commits_accepted", "duplicate_deliveries_suppressed", "steps_executed",
               "steps_reexecuted", "transfer_bytes", "transfer_messages", "sensitive_transfers")


# Fault kinds a mode cannot experience by construction (v0.2 records name the reason).
_TRANSFERLESS = ("duplicate_delivery", *PARTITION_KINDS)
NOT_APPLICABLE: dict[tuple[str, str], str] = {
    **{("keep_on_origin", f): "no_transfer_channel" for f in _TRANSFERLESS},
    ("keep_on_origin", "stale_origin_returns"): "no_ownership_transfer",
    ("restart_on_destination", "partition_drop_reply"): "no_reply_message",
    ("restart_stable_ids", "partition_drop_reply"): "no_reply_message",
    ("local_delegate", "stale_origin_returns"): "origin_remains_owner",
    ("a2a_delegate", "stale_origin_returns"): "origin_remains_owner",
}


def fault_not_applied_reason(mode: str, fault: str, status: str, outcome: str, applied: bool) -> str | None:
    """Why a scheduled fault did not act on this attempt (None when it did, or for `none`)."""
    if fault == "none" or applied:
        return None
    if status != "implemented":
        return "mode_unavailable"
    if outcome == "harness_error":
        return "harness_error"
    if (mode, fault) in NOT_APPLICABLE:
        return NOT_APPLICABLE[(mode, fault)]
    if outcome in ("refused", "incomplete"):
        return "attempt_ended_before_fault_point"
    if fault in CRASH_KINDS:
        return "no_effect_intent_at_crash_step"  # e.g. the effect was skipped by an active policy
    if fault == "effect_ack_lost":
        return "no_effect_committed"
    return "fault_point_not_reached"


def run_attempt(task: dict[str, Any], truth: dict[str, Any] | None, mode: str, fault: str,
                workdir: Path, suite: str = "v0.1", crash_step: int | None = None) -> dict[str, Any]:
    """Run one attempt and return a sanitized record (IDs, enums, counts, digests only).

    v0.1 records keep exactly their v0.1 fields; v0.2 records add V02_RECORD_FIELDS.
    """
    spec = suite_spec(suite)
    if fault not in spec.fault_kinds:
        raise FixtureError(f"fault {fault!r} is not part of suite {suite}")
    info = modes_for(suite)[mode]
    record: dict[str, Any] = {"task_id": task["task_id"], "family": task["family"], "mode": mode,
                              "baseline": info["baseline"], "mode_status": info["status"],
                              "tracking": info["tracking"], "fault": fault, "fault_applied": False,
                              "outcome": "unavailable", "reason": info.get("unavailable_reason"),
                              "model_calls": 0}
    metric_keys = METRIC_KEYS + spec.extra_metrics
    record.update(dict.fromkeys(metric_keys))
    if spec.extra_metrics:
        record.update(crash_step=crash_step if fault in CRASH_KINDS else None, fault_not_applied_reason=None)
    t0 = time.perf_counter_ns()
    if info["status"] == "implemented":
        try:
            workdir.mkdir(parents=True, exist_ok=False)
            att = Attempt(task, fault, workdir, crash_step, spec.extra_metrics)
            state, outcome, reason = runner_for(mode)(att)
            if _ledger_rows(workdir / "effects.sqlite") != len(att.committed):
                raise RuntimeError("harness effect list disagrees with ledger")
            att.metrics["steps_reexecuted"] = sum(n - 1 for n in att.step_runs.values())
            record.update(outcome=outcome, reason=reason, fault_applied=att.fault_applied)
            record.update(att.metrics)
            if truth is not None:
                record.update(evaluate(task, truth, state, att, outcome == "completed"))
        except Exception as exc:  # noqa: BLE001 - recorded as a harness error, never as a baseline success
            record.update(dict.fromkeys(metric_keys))
            record.update(outcome="harness_error", reason=type(exc).__name__)
    if spec.extra_metrics:
        record["fault_not_applied_reason"] = fault_not_applied_reason(
            mode, fault, info["status"], record["outcome"], record["fault_applied"])
    record["elapsed_ms"] = round((time.perf_counter_ns() - t0) / 1_000_000, 3)
    record["outcome_fingerprint"] = digest({k: v for k, v in record.items() if k not in VOLATILE})
    return record


def build_ground_truth(task: dict[str, Any]) -> dict[str, Any]:
    """Full-knowledge, fault-free reference execution (B0 hearing every event)."""
    with tempfile.TemporaryDirectory(prefix="mobilitybench-truth-") as directory:
        att = Attempt(task, "none", Path(directory))
        state, outcome, _ = run_keep(att)
        if outcome != "completed":
            raise FixtureError("reference execution did not complete")
        return {
            "task_id": task["task_id"],
            "expected_output": state.out,
            "expected_files_sha256": state.output()["files"],
            "expected_inventory": state.output()["inventory"],
            "output_digest": digest(state.output()),
            "expected_effects": [{"step": c["step"], "tool": c["tool"], "to": c["to"],
                                  "payload_digest": hashlib.sha256(c["payload"].encode("utf-8")).hexdigest()}
                                 for c in att.committed],
            "constraints_total": len([r for r in all_rules(task) if r["rule"] in CONSTRAINT_RULES]),
        }


# --------------------------------------------------------------------------- negative / security cases

def _security_task(case: dict[str, Any], fx: Fixtures) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if case.get("task") is not None:
        task = case["task"]
        return task, build_ground_truth(task) if task["classification"] in TRANSFERABLE else None
    task = next(t for t in fx.tasks if t["task_id"] == case["task_ref"])
    return task, fx.truth.get(task["task_id"])


def _envelope(suffix: str, **override: Any) -> dict[str, Any]:
    env = {"schema_version": SCHEMA_VERSION, "movement_id": f"neg-{suffix}",
           "logical_task_id": "neg-task", "operation": "delegate",
           "origin": {"agent_id": "agent-a"}, "destination": {"agent_id": "agent-b"},
           "task": {"kind": "word_count", "text": "synthetic negative fixture"},
           "context": {"classification": "synthetic"},
           "authority": {"approval_ref": "neg-approval"},
           "execution": {"idempotency_key": f"neg-key-{suffix}"},
           "observability": {"trace_id": f"neg-trace-{suffix}"}}
    env.update(override)
    return env


def _neg_receiver(workdir: Path, revoked: bool = False) -> HandoffReceiver:
    return HandoffReceiver("agent-b", SQLiteStore(workdir / "neg.sqlite"), [
        Approval("neg-approval", "neg-task", "agent-a", "agent-b", "word_count", revoked=revoked)])


def _sec_classification_gate(case: dict[str, Any], fx: Fixtures, workdir: Path) -> tuple[str, dict[str, Any]]:
    task, truth = _security_task(case, fx)
    rec = run_attempt(task, truth, case["mode"], case.get("fault", "none"), workdir / "attempt",
                      fx.suite, case.get("crash_step"))
    if rec["outcome"] != "refused":
        observed = rec["outcome"]
    else:
        observed = "refused_before_transfer" if rec["transfer_bytes"] == 0 else "disclosed_before_refusal"
    return observed, {"reason": rec["reason"] or "none", "transfer_bytes_before_refusal": rec["transfer_bytes"] or 0}


def _sec_run_task(case: dict[str, Any], fx: Fixtures, workdir: Path) -> tuple[str, dict[str, Any]]:
    task, truth = _security_task(case, fx)
    rec = run_attempt(task, truth, case["mode"], case.get("fault", "none"), workdir / "attempt",
                      fx.suite, case.get("crash_step"))
    if case["expected"] == "fenced":
        fenced = rec["stale_commits_fenced"] == 1 and rec["stale_commits_accepted"] == 0
        return ("fenced" if fenced else "unfenced"), {
            "stale_commits_fenced": rec["stale_commits_fenced"] or 0,
            "stale_commits_accepted": rec["stale_commits_accepted"] or 0}
    return rec["outcome"], {"reason": rec["reason"] or "none", "transfer_bytes": rec["transfer_bytes"] or 0}


def _sec_canary(case: dict[str, Any], fx: Fixtures, workdir: Path) -> tuple[str, dict[str, Any]]:
    task, truth = _security_task(case, fx)
    rec = run_attempt(task, truth, case["mode"], "none", workdir / "attempt", fx.suite)
    receiver_db = workdir / "attempt" / "receiver.sqlite"
    audit = SQLiteStore(receiver_db).audit() if receiver_db.exists() else []
    leaked = CANARY in canonical(rec) or CANARY in canonical(audit)
    observed = "leaked" if leaked else ("absent_from_records_and_audit" if rec["outcome"] == "completed"
                                        else rec["outcome"])
    return observed, {"attempt_outcome": rec["outcome"], "audit_events": len(audit),
                      "canary_sent_to_receiver": rec["sensitive_transfers"] is not None
                      and rec["sensitive_transfers"] > 0}


def _sec_forged_destination(case: dict[str, Any], fx: Fixtures, workdir: Path) -> tuple[str, dict[str, Any]]:
    receiver = _neg_receiver(workdir)
    try:
        receiver.receive(_envelope("forged", destination={"agent_id": "agent-x"}))
    except PolicyDenied:
        return "denied", {"denial_type": "PolicyDenied"}
    return "accepted", {"denial_type": "none"}


def _sec_movement_id_reuse(case: dict[str, Any], fx: Fixtures, workdir: Path) -> tuple[str, dict[str, Any]]:
    receiver = _neg_receiver(workdir)
    receiver.receive(_envelope("reuse"))
    try:
        receiver.receive(_envelope("reuse", execution={"idempotency_key": "neg-key-other"}))
    except Conflict:
        return "denied", {"denial_type": "Conflict"}
    return "accepted", {"denial_type": "none"}


def _sec_effect_conflict(case: dict[str, Any], fx: Fixtures, workdir: Path) -> tuple[str, dict[str, Any]]:
    gateway = EffectGateway(SQLiteStore(workdir / "neg.sqlite"))
    epoch = gateway.claim("neg-effects", "agent-a")
    gateway.commit("neg-effects", "agent-a", epoch, "neg-effect-1", "synthetic payload")
    try:
        gateway.commit("neg-effects", "agent-a", epoch, "neg-effect-1", "different payload")
    except Conflict:
        return "denied", {"denial_type": "Conflict"}
    return "accepted", {"denial_type": "none"}


def _sec_data_not_instructions(case: dict[str, Any], fx: Fixtures, workdir: Path) -> tuple[str, dict[str, Any]]:
    task, truth = _security_task(case, fx)
    rec = run_attempt(task, truth, case["mode"], "none", workdir / "attempt", fx.suite)
    declared = {op["to"] for op in task["plan"] if op["op"] == "effect"}
    ok = (rec["outcome"] == "completed" and rec["task_correct"] is True
          and rec["unexpected_effects"] == 0 and rec["effects_committed"] == len(declared))
    return ("not_executed" if ok else "executed_or_failed"), {
        "task_correct": bool(rec["task_correct"]), "unexpected_effects": rec["unexpected_effects"] or 0}


def _sec_tampered_fixture(case: dict[str, Any], fx: Fixtures, workdir: Path) -> tuple[str, dict[str, Any]]:
    copy = workdir / "fixtures"
    shutil.copytree(fx.directory, copy)
    target = copy / "tasks.jsonl"
    data = bytearray(target.read_bytes())
    data[-2] = ord("X") if data[-2] != ord("X") else ord("Y")
    target.write_bytes(bytes(data))
    try:
        verify_fixtures(copy, fx.suite)
    except FixtureError:
        return "rejected", {"error_type": "FixtureError"}
    return "accepted", {"error_type": "none"}


def _sec_unknown(case: dict[str, Any], fx: Fixtures, workdir: Path) -> tuple[str, dict[str, Any]]:
    gateway = EffectGateway(SQLiteStore(workdir / "neg.sqlite"))
    gateway.claim("neg-effects", "agent-a")
    return gateway.reconcile("neg-effects", "never-committed"), {"local_ledger_authoritative_only": True}


def _sec_revocation(case: dict[str, Any], fx: Fixtures, workdir: Path) -> tuple[str, dict[str, Any]]:
    receiver = _neg_receiver(workdir)
    receiver.receive(_envelope("before-revocation"))  # approved work starts on agent-b
    gateway = EffectGateway(receiver.store)
    epoch = gateway.claim("neg-task", "agent-b")
    revoked = _neg_receiver(workdir, revoked=True)  # the user revokes the grant
    new_handoff, _ = exception_outcome(lambda: revoked.receive(_envelope("after-revocation")), PolicyDenied)
    if new_handoff != "denied":
        return "revocation_not_enforced_at_receiver", {"new_handoff_denied": False}
    # Attack: the executor keeps going and commits its next simulated effect anyway.
    try:
        committed = gateway.commit("neg-task", "agent-b", epoch, "neg-after-revocation", "synthetic")
    except PolicyDenied:
        committed = False
    return ("committed_without_grant_recheck" if committed else "rejected"), {
        "new_handoff_denied": True, "simulated_commit_after_revocation": committed}


def _sec_stable_id_conflict(case: dict[str, Any], fx: Fixtures, workdir: Path) -> tuple[str, dict[str, Any]]:
    """v0.2: a restart with deterministic IDs re-issues an origin effect with a different payload."""
    task, truth = _security_task(case, fx)
    rec = run_attempt(task, truth, case["mode"], "none", workdir / "attempt", fx.suite)
    conflicts = rec.get("effect_id_conflicts") or 0
    kept = conflicts > 0 and rec["duplicate_effects"] == 0 and rec["unexpected_effects"] == 0
    observed = ("ledger_kept_first_payload" if kept else "overwritten_or_duplicated") \
        if rec["outcome"] == "completed" else rec["outcome"]
    return observed, {"effect_id_conflicts": conflicts, "duplicate_effects": rec["duplicate_effects"] or 0,
                      "unexpected_effects": rec["unexpected_effects"] or 0}


def _sec_lost_receipt(case: dict[str, Any], fx: Fixtures, workdir: Path) -> tuple[str, dict[str, Any]]:
    """v0.2: the receipt of a delegated step is lost; the origin's retry must be a replay."""
    task, truth = _security_task(case, fx)
    rec = run_attempt(task, truth, case["mode"], "partition_drop_reply", workdir / "attempt", fx.suite)
    replayed = (rec["outcome"] == "completed" and rec["task_correct"] is True and rec.get("messages_dropped") == 1
                and (rec["duplicate_deliveries_suppressed"] or 0) >= 1)
    observed = "replayed_not_reexecuted" if replayed else rec["outcome"]
    return observed, {"messages_dropped": rec.get("messages_dropped") or 0,
                      "duplicate_deliveries_suppressed": rec["duplicate_deliveries_suppressed"] or 0}


def _sec_crash_zombie(case: dict[str, Any], fx: Fixtures, workdir: Path) -> tuple[str, dict[str, Any]]:
    """v0.2: the origin 'crashed' inside an effect step but was only paused; after the task
    moved it wakes up and sends its in-flight commit with its old epoch."""
    task, truth = _security_task(case, fx)
    step = case["crash_step"]
    rec = run_attempt(task, truth, case["mode"], "crash_before_effect_commit", workdir / "attempt", fx.suite, step)
    if not rec["fault_applied"]:
        return "crash_not_applied", {"zombie_commit_attempted": False}
    gateway = EffectGateway(SQLiteStore(workdir / "attempt" / "effects.sqlite"))
    try:
        gateway.commit(task["task_id"], "agent-a", 1, f"{task['task_id']}.e{step}", "synthetic zombie commit")
    except PolicyDenied:
        return "fenced", {"zombie_commit_attempted": True}
    return "committed", {"zombie_commit_attempted": True}


def _sec_runtime_revocation(case: dict[str, Any], fx: Fixtures, workdir: Path) -> tuple[str, dict[str, Any]]:
    """v0.2: as `neg-revocation-not-at-effect`, but the grant is revoked at runtime with a signed
    notice (issue #38), which the core gateway rechecks at the effect commit."""
    authority = HmacKey.generate("authority-mobilitybench-v02")  # synthetic, fresh per run
    receiver = HandoffReceiver("agent-b", SQLiteStore(workdir / "neg.sqlite"), [
        Approval("neg-approval", "neg-task", "agent-a", "agent-b", "word_count")],
        revocation_authorities=[authority])
    receiver.receive(_envelope("before-revocation"))  # approved work starts on agent-b
    gateway = EffectGateway(receiver.store)
    epoch = gateway.claim("neg-task", "agent-b")
    receiver.revoke(issue_revocation(authority, "neg-approval", 1_792_000_000))
    new_handoff, _ = exception_outcome(lambda: receiver.receive(_envelope("after-revocation")), PolicyDenied)
    if new_handoff != "denied":
        return "revocation_not_enforced_at_receiver", {"new_handoff_denied": False}
    try:  # Attack: the executor keeps going and commits its next simulated effect anyway.
        committed = gateway.commit("neg-task", "agent-b", epoch, "neg-after-revocation", "synthetic")
    except PolicyDenied:
        committed = False
    return ("committed_without_grant_recheck" if committed else "rejected"), {
        "new_handoff_denied": True, "simulated_commit_after_revocation": committed}


SECURITY: dict[str, Callable[[dict[str, Any], Fixtures, Path], tuple[str, dict[str, Any]]]] = {
    "runtime_revocation_at_effect": _sec_runtime_revocation,
    "stable_id_conflict": _sec_stable_id_conflict,
    "lost_receipt_replay": _sec_lost_receipt,
    "crash_zombie_commit": _sec_crash_zombie,
    "classification_gate": _sec_classification_gate,
    "run_task": _sec_run_task,
    "canary_redaction": _sec_canary,
    "forged_destination": _sec_forged_destination,
    "movement_id_reuse": _sec_movement_id_reuse,
    "effect_conflict": _sec_effect_conflict,
    "data_not_instructions": _sec_data_not_instructions,
    "tampered_fixture": _sec_tampered_fixture,
    "unknown_not_failed": _sec_unknown,
    "revocation_not_rechecked": _sec_revocation,
}


def run_security_cases(fx: Fixtures, root: Path, timing: bool = True) -> list[dict[str, Any]]:
    records = []
    for case in fx.negatives:
        workdir = root / f"security-{case['case_id']}"
        workdir.mkdir(parents=True)
        t0 = time.perf_counter_ns()
        try:
            observed, evidence = SECURITY[case["attack"]](case, fx, workdir)
            if any(not isinstance(k, str) or type(v) not in (str, int, bool) for k, v in evidence.items()):
                raise TypeError("invalid evidence schema")
        except Exception as exc:  # noqa: BLE001 - observed research failure, not silent success
            observed, evidence = "unexpected_exception", {"exception_type": type(exc).__name__}
        if observed == case["expected"]:
            verdict = "known_gap" if case["known_gap"] else "pass"
        elif case["known_gap"] and observed == case.get("closed_observation"):
            verdict = "gap_closed"  # control now present: rewrite this case in the next suite version
        else:
            verdict = "fail"
        records.append({"record_type": "security", "case_id": case["case_id"], "attack": case["attack"],
                        "mode": case["mode"], "question_ids": case["question_ids"],
                        "expected": case["expected"], "observed": observed, "verdict": verdict,
                        "known_gap": case["known_gap"], "evidence": evidence,
                        "elapsed_ms": round((time.perf_counter_ns() - t0) / 1_000_000, 3) if timing else None})
    return records


# --------------------------------------------------------------------------- suite

def fault_schedule(task_ids: list[str], seeds: list[int], suite: str = "v0.1") -> dict[tuple[int, str], str]:
    """Seeded, balanced, auditable: no global RNG state, identical on every Python version."""
    spec = suite_spec(suite)
    kinds = spec.fault_kinds
    schedule = {}
    for seed in seeds:
        order = sorted(task_ids, key=lambda t: hashlib.sha256(f"{spec.version}:{seed}:{t}".encode()).hexdigest())
        for position, task_id in enumerate(order):
            schedule[(seed, task_id)] = kinds[(position + seed) % len(kinds)]
    return schedule


def effect_steps(task: dict[str, Any]) -> list[int]:
    return [i for i, op in enumerate(task["plan"]) if op["op"] in ("effect", "reserve")]


def crash_step_for(task: dict[str, Any], seed: int, suite: str = "v0.2") -> int:
    """Seeded choice among the plan's effect steps (every frozen task has at least one)."""
    steps = effect_steps(task)
    if not steps:
        raise FixtureError(f"task {task['task_id']} has no effect step to crash in")
    key = f"{suite_spec(suite).version}:{seed}:{task['task_id']}:crash_step"
    return steps[int(hashlib.sha256(key.encode()).hexdigest(), 16) % len(steps)]


def schedule_rows(tasks: list[dict[str, Any]], seeds: list[int], suite: str) -> list[dict[str, Any]]:
    """The full (seed, task) schedule as frozen in schedule.jsonl (task order as in tasks.jsonl)."""
    kinds = fault_schedule([t["task_id"] for t in tasks], seeds, suite)
    return [{"seed": seed, "task_id": task["task_id"], "fault": kinds[(seed, task["task_id"])],
             "crash_step": (crash_step_for(task, seed, suite) if kinds[(seed, task["task_id"])] in CRASH_KINDS
                            else None)}
            for seed in seeds for task in tasks]


def planned_faults(fx: Fixtures, seeds: list[int]) -> dict[tuple[int, str], dict[str, Any]]:
    """(seed, task) -> {"fault", "crash_step"}: the frozen schedule, or the generator for other seeds."""
    rows = {(r["seed"], r["task_id"]): r for r in schedule_rows(fx.tasks, seeds, fx.suite)}
    if fx.schedule is not None:
        rows.update({k: v for k, v in fx.schedule.items() if k[0] in seeds})
    return rows


def _selection(fx: Fixtures, subset: str, seeds: list[int] | None,
               repeats: int | None) -> tuple[list[dict[str, Any]], list[int], int]:
    plan = fx.seeds["smoke"] if subset == "smoke" else fx.seeds
    tasks = [t for t in fx.tasks if subset != "smoke" or t["task_id"] in plan["tasks"]]
    return tasks, list(seeds or plan["seeds"]), int(repeats or plan["repeats"])


def sensitive_strings(fx: Fixtures) -> list[str]:
    tasks = fx.tasks + [c["task"] for c in fx.negatives if c.get("task")]
    terms = {t for task in tasks for r in all_rules(task) if r["rule"] == "redact_terms" for t in r["terms"]}
    return sorted(terms | {CANARY})


def run_suite(suite: str = "v0.1", subset: str = "full", seeds: list[int] | None = None,
              repeats: int | None = None, fixtures: str | Path | None = None,
              timing: bool = True) -> list[dict[str, Any]]:
    """timing=False omits wall-clock fields so the JSONL is byte-identical across runs."""
    spec = suite_spec(suite)
    fx = load_fixtures(suite, fixtures)
    tasks, seeds, repeats = _selection(fx, subset, seeds, repeats)
    schedule = planned_faults(fx, seeds)
    modes = modes_for(suite)
    run_version = {"suite_version": spec.version, "fixture_release_digest": fx.manifest["release_digest"],
                   "contract_version": SCHEMA_VERSION, "harness_version": HARNESS_VERSION,
                   "executor": EXECUTOR, "model": MODEL, "python": platform.python_version(),
                   "extras": extras_versions()}
    run_id = digest({"run_version": run_version, "subset": subset, "seeds": seeds, "repeats": repeats})[:16]
    manifest: dict[str, Any] = {
        "record_type": "run_manifest", "run_id": run_id, "run_version": run_version, "subset": subset,
        "seeds": seeds, "repeats": repeats, "tasks": [t["task_id"] for t in tasks],
        "modes": {m: dict(v) for m, v in modes.items()}, "fault_kinds": list(spec.fault_kinds),
        "fault_assignment": fx.seeds["fault_assignment"],
        "started_at": datetime.now(UTC).replace(microsecond=0).isoformat() if timing else None}
    if spec.extra_metrics:
        manifest["crash_step_assignment"] = fx.seeds["crash_step_assignment"]
    records: list[dict[str, Any]] = [manifest]
    with tempfile.TemporaryDirectory(prefix=f"mobilitybench-{suite}-") as directory:
        root = Path(directory)
        for repeat in range(repeats):
            for seed in seeds:
                for task in tasks:
                    planned = schedule[(seed, task["task_id"])]
                    fault = planned["fault"]
                    for mode in modes:
                        record = run_attempt(task, fx.truth.get(task["task_id"]), mode, fault,
                                             root / f"r{repeat}-s{seed}-{task['task_id']}-{mode}",
                                             suite, planned["crash_step"])
                        if not timing:
                            record["elapsed_ms"] = None
                        records.append({"record_type": "attempt", "run_id": run_id, "run_version": run_version,
                                        "seed": seed, "repeat": repeat, **record})
        records.extend({**record, "run_id": run_id, "run_version": run_version}
                       for record in run_security_cases(fx, root, timing))
    blob = canonical(records)
    leaked = [s for s in sensitive_strings(fx) if s in blob]
    if leaked:
        raise RuntimeError(f"{len(leaked)} sensitive fixture string(s) leaked into benchmark records")
    return records


# --------------------------------------------------------------------------- summary and report

def _attempts(records: list[dict[str, Any]], repeat: int | None = 0) -> list[dict[str, Any]]:
    return [r for r in records if r.get("record_type") == "attempt" and (repeat is None or r["repeat"] == repeat)]


def _sum(rows: list[dict[str, Any]], key: str) -> int:
    return sum(r[key] or 0 for r in rows)


def mode_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    done = [r for r in rows if r["outcome"] == "completed"]
    elapsed = [r["elapsed_ms"] for r in rows if r["mode_status"] == "implemented" and r["elapsed_ms"] is not None]
    return {
        "attempts": len(rows),
        **{k: sum(r["outcome"] == k for r in rows)
           for k in ("completed", "incomplete", "refused", "unavailable", "harness_error")},
        "task_correct": sum(r["task_correct"] is True for r in rows),
        "output_correct": sum(r["output_correct"] is True for r in rows),
        "constraints_preserved": _sum(done, "constraints_preserved"),
        "constraints_total_completed": _sum(done, "constraints_total"),
        **{k: _sum(rows, k) for k in ("policy_violations", "duplicate_effects", "unexpected_effects",
                                       "unknown_events", "reconciled_events", "stale_commits_fenced",
                                       "stale_commits_accepted", "duplicate_deliveries_suppressed",
                                       "transfer_bytes", "transfer_messages", "sensitive_transfers",
                                       "steps_reexecuted")},
        "missing_effects_completed": _sum(done, "missing_effects"),
        "median_elapsed_ms": round(statistics.median(elapsed), 3) if elapsed else None,
        # v0.2 records only, so v0.1 summaries keep their v0.1 keys.
        **({k: _sum(rows, k) for k in V02_METRIC_KEYS}
           | {"faults_applied": sum(r["fault_applied"] is True for r in rows)}
           if rows and "effect_id_conflicts" in rows[0] else {}),
    }


def reproducibility(records: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple[Any, ...], set[str]] = {}
    for r in _attempts(records, None):
        groups.setdefault((r["seed"], r["task_id"], r["mode"]), set()).add(r["outcome_fingerprint"])
    repeats = {r["repeat"] for r in _attempts(records, None)}
    mismatched = sorted(f"{s}/{t}/{m}" for (s, t, m), fps in groups.items() if len(fps) > 1)
    return {"repeats": len(repeats), "groups": len(groups), "mismatched": mismatched}


def outcome_digest(records: list[dict[str, Any]]) -> str:
    """Timing-free digest of all deterministic results; compare it across machines and runs."""
    attempts = sorted((r["repeat"], r["seed"], r["task_id"], r["mode"], r["outcome_fingerprint"])
                      for r in _attempts(records, None))
    security = sorted((r["case_id"], r["observed"], r["verdict"], canonical(r["evidence"]))
                      for r in records if r.get("record_type") == "security")
    return digest({"attempts": attempts, "security": security})


def run_modes(records: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    """Mode table of the run that produced `records` (not of the environment rendering them)."""
    manifest = next((r for r in records if r.get("record_type") == "run_manifest"), {})
    modes = manifest.get("modes") or MODES
    order = list(MODE_ORDER)  # JSONL keys are sorted; report in baseline order (B0, B1, B1-stable, ...)
    return {m: modes[m] for m in sorted(modes, key=lambda m: (order.index(m) if m in order else len(order), m))}


def run_suite_spec(records: list[dict[str, Any]]) -> Suite:
    """The suite that produced `records`, from its run manifest (v0.1 for older JSONL)."""
    manifest = next((r for r in records if r.get("record_type") == "run_manifest"), {})
    version = (manifest.get("run_version") or {}).get("suite_version", SUITE_VERSION)
    return SUITE_BY_VERSION.get(version, SUITE_SPECS["v0.1"])


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    attempts = _attempts(records)
    security = [r for r in records if r.get("record_type") == "security"]
    manifest = next((r for r in records if r.get("record_type") == "run_manifest"), {})
    repro = reproducibility(records)
    return {
        "suite_version": run_suite_spec(records).version, "run_id": manifest.get("run_id"),
        "subset": manifest.get("subset"),
        "outcome_digest": outcome_digest(records),
        "attempts_repeat0": len(attempts),
        "harness_errors": sum(r["outcome"] == "harness_error" for r in _attempts(records, None)),
        "modes": {m: mode_summary([r for r in attempts if r["mode"] == m]) for m in run_modes(records)},
        "security": {v: sum(r["verdict"] == v for r in security) for v in VERDICTS},
        "security_total": len(security),
        "reproducibility": {"repeats": repro["repeats"], "groups": repro["groups"],
                            "mismatched": len(repro["mismatched"])},
    }


def _frac(n: int, d: int) -> str:
    return f"{n}/{d}"


def _cell(value: Any) -> str:
    if value is None:
        return "–"
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return str(value)


def build_report(records: list[dict[str, Any]]) -> str:
    manifest = next((r for r in records if r.get("record_type") == "run_manifest"), None)
    if manifest is None:
        raise ValueError("results have no run_manifest record")
    attempts = _attempts(records)
    summary = summarize(records)
    modes = run_modes(records)
    spec = run_suite_spec(records)
    v02 = bool(spec.extra_metrics)
    fault_kinds = tuple(manifest.get("fault_kinds") or spec.fault_kinds)
    rv = manifest["run_version"]
    lines = [
        f"# MobilityBench {spec.key} report — run `{manifest['run_id']}`",
        "",
        ("> **Pilot, deterministic, LLM-free.** A scripted interpreter executed frozen synthetic tasks; "
         "effects are simulated SQLite commits. Outcomes are deterministic functions of (task, mode, fault), "
         "so repeats test reproducibility, not sampling variance: no confidence intervals or significance "
         "claims are made, and none should be inferred from these counts. Unavailable baselines are listed, "
         f"not scored. See `{spec.doc}` for rubrics and validity threats."),
        "",
        "## Run manifest",
        "",
        "| field | value |", "| --- | --- |",
        *[f"| {k} | `{canonical(v) if isinstance(v, (dict, list)) else v}` |" for k, v in rv.items()],
        f"| subset | `{manifest['subset']}` |",
        f"| seeds | `{', '.join(map(str, manifest['seeds']))}` |",
        f"| repeats | `{manifest['repeats']}` |",
        f"| tasks | {len(manifest['tasks'])} |",
        f"| started_at | `{manifest['started_at']}` |",
        f"| outcome_digest (timing-free) | `{summary['outcome_digest']}` |",
        "",
        "## Denominators",
        "",
        (f"- Attempt records (all repeats): **{len(_attempts(records, None))}**; summary tables use repeat 0 only: "
         f"**{len(attempts)}** = {len(manifest['tasks'])} tasks × {len(manifest['seeds'])} seeds "
         f"× {len(modes)} modes."),
        (f"- Implemented-mode attempts (repeat 0): **{sum(r['mode_status'] == 'implemented' for r in attempts)}**; "
         f"unavailable-mode records: **{sum(r['mode_status'] == 'unavailable' for r in attempts)}** (not scored)."),
        f"- Harness errors (all repeats): **{summary['harness_errors']}**.",
        (f"- Security/negative cases: **{summary['security_total']}** "
         f"({summary['security']['pass']} pass, {summary['security']['known_gap']} known gap, "
         f"{summary['security']['gap_closed']} gap closed, {summary['security']['fail']} fail)."),
        "",
        "## Baseline summary (repeat 0)",
        "",
        ("`correct` requires completed + exact output digest + all constraints + no policy violation, "
         "duplicate, unexpected or missing effect. Each fraction shows its own denominator."),
        "",
        ("| mode | baseline | status | completed | correct / attempts | correct / completed | constraints kept "
         "(completed) | policy violations | duplicate effects | unexpected effects | unknown→reconciled | "
         "stale fenced | transfer bytes | refused | incomplete | median ms |"),
        ("| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: "
         "| ---: | ---: | ---: | ---: | ---: | ---: |"),
    ]
    for mode, info in modes.items():
        s = summary["modes"][mode]
        if info["status"] != "implemented":
            lines.append(f"| {mode} | {info['baseline']} | **UNAVAILABLE** ({info['tracking']}) | – | "
                         f"not scored ({s['unavailable']} records) | – | – | – | – | – | – | – | – | – | – | – |")
            continue
        lines.append(
            f"| {mode} | {info['baseline']} | implemented | {_frac(s['completed'], s['attempts'])} | "
            f"{_frac(s['task_correct'], s['attempts'])} | {_frac(s['task_correct'], s['completed'])} | "
            f"{_frac(s['constraints_preserved'], s['constraints_total_completed'])} | {s['policy_violations']} | "
            f"{s['duplicate_effects']} | {s['unexpected_effects']} | "
            f"{s['unknown_events']}→{s['reconciled_events']} | {s['stale_commits_fenced']} | "
            f"{s['transfer_bytes']} | {s['refused']} | {s['incomplete']} | {_cell(s['median_elapsed_ms'])} |")
    implemented = [m for m, i in modes.items() if i["status"] == "implemented"]
    if v02:
        lines += ["", "## Fault-path evidence (repeat 0)", "",
                  ("`faults applied` counts attempts on which the scheduled fault actually acted; the others are "
                   "listed with their reason under *Fault applicability*. Effect-ID conflicts are re-issued effects "
                   "whose deterministic ID already held a different payload (the ledger kept the first one)."), "",
                  ("| mode | faults applied / attempts | effect-ID conflicts | messages dropped | messages delayed "
                   "| retries | duplicate deliveries suppressed | steps re-executed |"),
                  "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for mode in [m for m, i in modes.items() if i["status"] == "implemented"]:
            s = summary["modes"][mode]
            lines.append(f"| {mode} | {_frac(s['faults_applied'], s['attempts'])} | {s['effect_id_conflicts']} | "
                         f"{s['messages_dropped']} | {s['messages_delayed']} | {s['retries']} | "
                         f"{s['duplicate_deliveries_suppressed']} | {s['steps_reexecuted']} |")
    for title, key, values in (("By fault (repeat 0): correct / attempts", "fault", fault_kinds),
                               ("By family (repeat 0): correct / attempts", "family", FAMILIES)):
        lines += ["", f"## {title}", "", "| mode | " + " | ".join(values) + " |",
                  "| --- |" + " ---: |" * len(values)]
        for mode in implemented:
            cells = []
            for value in values:
                rows = [r for r in attempts if r["mode"] == mode and r[key] == value]
                cells.append(_frac(sum(r["task_correct"] is True for r in rows), len(rows)))
            lines.append(f"| {mode} | " + " | ".join(cells) + " |")
    if v02:
        lines += ["", "## Fault applicability (repeat 0): applied / scheduled", "",
                  ("A fault that cannot act on a mode is reported, never silently dropped: every scheduled but "
                   "unapplied fault carries a `fault_not_applied_reason` (table below)."), "",
                  "| mode | " + " | ".join(f for f in fault_kinds if f != "none") + " |",
                  "| --- |" + " ---: |" * (len(fault_kinds) - 1)]
        for mode in modes:
            cells = []
            for fault in fault_kinds[1:]:
                rows = [r for r in attempts if r["mode"] == mode and r["fault"] == fault]
                cells.append(_frac(sum(r["fault_applied"] is True for r in rows), len(rows)))
            lines.append(f"| {mode} | " + " | ".join(cells) + " |")
        unapplied = Counter((r["mode"], r["fault"], r["fault_not_applied_reason"]) for r in attempts
                            if r["fault_not_applied_reason"] is not None)
        lines += ["", "| mode | fault | not applied because | count |", "| --- | --- | --- | ---: |"]
        lines += [f"| {m} | {f} | `{why}` | {n} |" for (m, f, why), n in sorted(unapplied.items())] \
            or ["| – | – | – | 0 |"]
    reasons = Counter((r["mode"], r["outcome"], r["reason"]) for r in attempts
                      if r["outcome"] in ("refused", "incomplete", "harness_error"))
    lines += ["", "## Refusals, incomplete attempts and harness errors (repeat 0)", "",
              "| mode | outcome | reason | count |", "| --- | --- | --- | ---: |"]
    lines += [f"| {m} | {o} | `{why}` | {n} |" for (m, o, why), n in sorted(reasons.items())] or ["| – | – | – | 0 |"]
    lines += ["", "## Unavailable baselines", "",
              ("An unavailable mode is never scored. `extra_not_installed:<extra>` means the run's environment "
               "lacked that optional extra (`pip install -e '.[<extra>]'`); `baseline_not_implemented` means "
               "no implementation exists."), "",
              "| mode | baseline | reason | tracking | records |", "| --- | --- | --- | --- | ---: |"]
    unavailable = [f"| {m} | {i['baseline']} | `{i.get('unavailable_reason', 'baseline_not_implemented')}` | "
                   f"{i['tracking']} | {summary['modes'][m]['unavailable']} |"
                   for m, i in modes.items() if i["status"] != "implemented"]
    lines += unavailable or ["| – | – | – | – | 0 |"]
    security = [r for r in records if r.get("record_type") == "security"]
    lines += ["", "## Negative and security fixtures", "",
              ("A `known_gap` reproduces a deliberately documented missing control; it is **not** a pass. "
               "`gap_closed` means the control now exists: the case must be rewritten in the next suite version."), "",
              "| case | mode | questions | expected | observed | verdict |", "| --- | --- | --- | --- | --- | --- |"]
    lines += [f"| {r['case_id']} | {r['mode']} | {', '.join(r['question_ids'])} | `{r['expected']}` | "
              f"`{r['observed']}` | **{r['verdict']}** |" for r in security]
    repro = reproducibility(records)
    lines += ["", "## Reproducibility", "",
              f"- Repeats: {repro['repeats']}; (seed, task, mode) groups: {repro['groups']}; groups with differing "
              f"outcome fingerprints: **{len(repro['mismatched'])}**" +
              (": " + ", ".join(repro["mismatched"]) if repro["mismatched"] else "."),
              ("- Fingerprints exclude wall-clock time, which is machine-dependent and not a fair cross-mode "
               "latency comparison."), "",
              "## Raw per-case results (repeat 0)", "",
              "| seed | task | family | mode | fault | applied | outcome | reason | correct | output | constraints "
              "| policy | dup | unexp | missing | unknown | fenced | bytes | ms |"
              + (" crash step | not applied because | conflicts | dropped | delayed | retries | re-executed |"
                 if v02 else ""),
              "| ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: "
              "| ---: | ---: | ---: |" + (" ---: | --- | ---: | ---: | ---: | ---: | ---: |" if v02 else "")]
    for r in attempts:
        constraints = ("–" if r["constraints_preserved"] is None
                       else _frac(r["constraints_preserved"], r["constraints_total"]))
        lines.append(" | ".join([
            f"| {r['seed']}", r["task_id"], r["family"], r["mode"], r["fault"], _cell(r["fault_applied"]),
            r["outcome"], f"`{r['reason']}`" if r["reason"] else "–", _cell(r["task_correct"]),
            _cell(r["output_correct"]), constraints, _cell(r["policy_violations"]), _cell(r["duplicate_effects"]),
            _cell(r["unexpected_effects"]), _cell(r["missing_effects"]), _cell(r["unknown_events"]),
            _cell(r["stale_commits_fenced"]), _cell(r["transfer_bytes"]), f"{_cell(r['elapsed_ms'])} |"])
            + ("" if not v02 else " " + " | ".join([
                _cell(r["crash_step"]), f"`{r['fault_not_applied_reason']}`" if r["fault_not_applied_reason"] else "–",
                _cell(r["effect_id_conflicts"]), _cell(r["messages_dropped"]), _cell(r["messages_delayed"]),
                _cell(r["retries"]), f"{_cell(r['steps_reexecuted'])} |"])))
    return "\n".join(lines) + "\n"


def read_records(path: str | Path) -> list[dict[str, Any]]:
    text = sys.stdin.read() if str(path) == "-" else Path(path).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def run_exit_code(records: list[dict[str, Any]]) -> int:
    summary = summarize(records)
    bad = summary["harness_errors"] or summary["security"]["fail"] or summary["reproducibility"]["mismatched"]
    return 1 if bad else 0


# --------------------------------------------------------------------------- CLI

def _write(path: str, data: str) -> None:
    if path == "-":
        sys.stdout.write(data)
    else:
        Path(path).write_text(data, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agent_movement.mobilitybench",
                                     description="MobilityBench v0.1 and v0.2 (deterministic, LLM-free, synthetic). "
                                                 "v0.2 adds mid-step crashes, partitions and the "
                                                 "restart_stable_ids baseline.")
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify", help="check frozen fixtures against the release SHA-256 manifest")
    run = sub.add_parser("run", help="run baselines, faults and negative fixtures; write sanitized JSONL")
    schedule = sub.add_parser("schedule", help="print the seeded fault schedule as JSONL")
    for p in (verify, run, schedule):
        p.add_argument("--suite", default="v0.1", choices=sorted(SUITES),
                       help="frozen suite release (default: v0.1)")
        p.add_argument("--fixtures", default=None, help="fixture directory (default: packaged release)")
    for p in (run, schedule):
        p.add_argument("--subset", default="full", choices=["full", "smoke"])
        p.add_argument("--seeds", default=None, help="comma-separated override of the seed manifest")
    run.add_argument("--repeats", type=int, default=None, help="override manifest repeats")
    run.add_argument("--out", required=True, help="JSONL destination; '-' = stdout")
    run.add_argument("--no-timing", action="store_true",
                     help="omit wall-clock fields so the JSONL is byte-identical across runs")
    report = sub.add_parser("report", help="render a Markdown report with denominators and raw per-case rows")
    report.add_argument("--in", dest="input", required=True, help="results JSONL; '-' = stdin")
    report.add_argument("--out", default="-", help="Markdown destination; '-' = stdout")
    args = parser.parse_args(argv)
    seeds = [int(s) for s in args.seeds.split(",")] if getattr(args, "seeds", None) else None
    try:
        if args.command == "verify":
            manifest = verify_fixtures(fixture_dir(args.suite, args.fixtures), args.suite)
            print(json.dumps({"verified": True, "suite_version": manifest["suite_version"],
                              "release_digest": manifest["release_digest"], "files": manifest["files"]},
                             indent=2, sort_keys=True))
            return 0
        if args.command == "schedule":
            fx = load_fixtures(args.suite, args.fixtures)
            tasks, seeds, _ = _selection(fx, args.subset, seeds, None)
            plan = planned_faults(fx, seeds)
            for seed in seeds:
                for task in tasks:
                    row = {"seed": seed, "task_id": task["task_id"], "fault": plan[(seed, task["task_id"])]["fault"]}
                    if suite_spec(args.suite).extra_metrics:
                        row["crash_step"] = plan[(seed, task["task_id"])]["crash_step"]
                    print(json.dumps(row, sort_keys=True))
            return 0
        if args.command == "run":
            if args.repeats is not None and args.repeats < 1:
                parser.error("--repeats must be >= 1")
            records = run_suite(args.suite, args.subset, seeds, args.repeats, args.fixtures,
                                timing=not args.no_timing)
            _write(args.out, "".join(json.dumps(r, sort_keys=True) + "\n" for r in records))
            print(json.dumps(summarize(records), sort_keys=True), file=sys.stderr)
            return run_exit_code(records)
        _write(args.out, build_report(read_records(args.input)))
        return 0
    except FixtureError as exc:
        print(json.dumps({"error": "fixture_verification_failed", "detail": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
