"""MobilityBench v0.1: frozen synthetic task-continuity baselines (deterministic, LLM-free).

  python -m agent_movement.mobilitybench verify --suite v0.1
  python -m agent_movement.mobilitybench run --suite v0.1 --out results.jsonl
  python -m agent_movement.mobilitybench report --in results.jsonl --out report.md

A scripted interpreter executes frozen synthetic plans; there are no model calls,
network requests or real side effects. Effects are simulated commits to the PR #6
fenced SQLite gateway, and the local delegate baseline uses the PR #6
HandoffReceiver in-process. This is NOT A2A, checkpoint relocation or
cross-framework reconstruction: those baselines are reported as unavailable.
Protocol, rubrics and validity threats: docs/mobilitybench-v0.1.md.
"""
from __future__ import annotations

import argparse
import hashlib
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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .core import (ID, SCHEMA_VERSION, Approval, Conflict, ContractError, EffectGateway,
                   HandoffReceiver, PolicyDenied, SQLiteStore, canonical, digest, parse_json)
from .mobilitybench import CANARY, exception_outcome

SUITE_VERSION = "mobilitybench-v0.1"
SUITES = {"v0.1": SUITE_VERSION}
HARNESS_VERSION = "0.1.0"
EXECUTOR = "deterministic-interpreter-v0.1"
MODEL = "none"
FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"
FIXTURE_FILES = ("tasks.jsonl", "ground_truth.jsonl", "negative.jsonl", "seeds.json")
MANIFEST_NAME = "MANIFEST.json"
FAMILIES = ("document", "coding", "tools")
FAULT_KINDS = ("none", "origin_preempted", "effect_ack_lost", "duplicate_delivery", "stale_origin_returns")
TRANSFERABLE = ("synthetic", "public")

# Baseline modes. Unavailable modes are emitted as explicit records, never dropped.
MODES: dict[str, dict[str, str]] = {
    "keep_on_origin": {"baseline": "B0", "status": "implemented", "tracking": "-"},
    "restart_on_destination": {"baseline": "B1", "status": "implemented", "tracking": "-"},
    "local_delegate": {"baseline": "B2-local", "status": "implemented",
                       "tracking": "PR #6 HandoffReceiver, in-process; not A2A"},
    "a2a_delegate": {"baseline": "B2", "status": "unavailable", "tracking": "issue #7"},
    "checkpoint_relocate": {"baseline": "B3", "status": "unavailable", "tracking": "issue #9"},
    "cross_framework_reconstruct": {"baseline": "B4", "status": "unavailable",
                                    "tracking": "not scheduled (AM-14; after issue #9)"},
}

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


# --------------------------------------------------------------------------- fixtures

def fixture_dir(suite: str = "v0.1", override: str | Path | None = None) -> Path:
    if suite not in SUITES:
        raise FixtureError(f"unknown suite {suite!r}; available: {', '.join(SUITES)}")
    return Path(override) if override is not None else FIXTURE_ROOT / SUITES[suite]


def file_digests(directory: Path) -> dict[str, str]:
    try:
        return {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in FIXTURE_FILES}
    except OSError as exc:
        raise FixtureError("missing fixture file") from exc


def release_digest(files: dict[str, str]) -> str:
    """SHA-256 over a `sha256sum`-format listing of the fixture files."""
    listing = "".join(f"{files[name]}  {name}\n" for name in sorted(files))
    return hashlib.sha256(listing.encode("utf-8")).hexdigest()


def verify_fixtures(directory: Path) -> dict[str, Any]:
    """Fail closed unless every frozen file matches the committed release manifest."""
    try:
        manifest = json.loads((directory / MANIFEST_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FixtureError("missing or unreadable release manifest") from exc
    if not isinstance(manifest, dict) or manifest.get("suite_version") != SUITE_VERSION:
        raise FixtureError("manifest suite version mismatch")
    expected = manifest.get("files")
    if not isinstance(expected, dict) or set(expected) != set(FIXTURE_FILES):
        raise FixtureError("manifest file list mismatch")
    actual = file_digests(directory)
    bad = sorted(name for name in FIXTURE_FILES if actual[name] != expected[name])
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


def load_fixtures(suite: str = "v0.1", directory: str | Path | None = None,
                  verify: bool = True) -> Fixtures:
    root = fixture_dir(suite, directory)
    manifest = verify_fixtures(root) if verify else {}
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
    if tuple(seeds.get("fault_kinds", ())) != FAULT_KINDS:
        raise FixtureError("seed manifest fault kinds differ from this harness")
    return Fixtures(root, manifest, tasks, truth, negatives, seeds)


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

    def __init__(self, task: dict[str, Any], fault: str, workdir: Path):
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
        self.metrics = {k: 0 for k in (
            "unknown_events", "reconciled_events", "stale_commits_fenced", "stale_commits_accepted",
            "duplicate_deliveries_suppressed", "transfer_bytes", "transfer_messages",
            "sensitive_transfers", "steps_executed", "steps_reexecuted")}
        self.sensitive = sorted({t for r in all_rules(task) if r["rule"] == "redact_terms" for t in r["terms"]})

    def hear(self, state: AgentState, step: int, min_at: int = 0) -> None:
        for event in self.task["session_events"]:
            if event["at"] == step and event["at"] >= min_at:
                state.rules.append(dict(event["rule"]))

    def send(self, message: dict[str, Any]) -> int:
        """Account one logical transfer; duplicate_delivery delivers it twice."""
        raw = canonical(message)
        copies = 2 if self.fault == "duplicate_delivery" else 1
        if copies == 2:
            self.fault_applied = True
        self.metrics["transfer_bytes"] += len(raw.encode("utf-8")) * copies
        self.metrics["transfer_messages"] += copies
        if any(term in raw for term in self.sensitive):
            self.metrics["sensitive_transfers"] += copies
        return copies

    def commit(self, state: AgentState, step: int, tool: str, to: str, payload: str, suffix: str) -> None:
        effect_id = f"{self.gw_task}.e{step}{suffix}"
        new = self.gateway.commit(self.gw_task, state.name, state.epoch, effect_id, payload)
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

    def run_step(self, state: AgentState, step: int, suffix: str = "", pure: Pure | None = None) -> None:
        op = self.plan[step]
        name = op["op"]
        self.metrics["steps_executed"] += 1
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
    for step in range(len(att.plan)):
        if att.fault == "origin_preempted" and step == att.m:
            att.fault_applied = True
            return origin, "incomplete", "origin_preempted_no_transfer"
        att.hear(origin, step)
        att.run_step(origin, step)
    return origin, "completed", None


def run_restart(att: Attempt) -> Outcome:
    """B1: destination re-runs the original request from step 0; session context is lost."""
    origin = att.run_origin_until_movement()
    if att.task["classification"] not in TRANSFERABLE:
        return origin, "refused", "classification_not_transferable"
    request = {"movement_id": f"restart-{att.gw_task}", "task_id": att.gw_task,
               "classification": att.task["classification"], "input": att.task["input"],
               "initial_constraints": att.task["initial_constraints"], "plan": att.plan}
    intake: set[str] = set()
    for _ in range(att.send(request)):
        if request["movement_id"] in intake:  # destination intake dedup by movement ID
            att.metrics["duplicate_deliveries_suppressed"] += 1
        intake.add(request["movement_id"])
    epoch = att.gateway.transfer(att.gw_task, "agent-a", origin.epoch, "agent-b")
    if att.fault == "origin_preempted":
        att.fault_applied = True  # origin is gone, restart does not depend on it
    if att.fault == "stale_origin_returns":
        att.fault_applied = True
        effect_steps = [i for i, op in enumerate(att.plan) if op["op"] in ("effect", "reserve")]
        later = [i for i in effect_steps if i >= att.m]
        step = later[0] if later else effect_steps[-1]
        try:
            att.gateway.commit(att.gw_task, "agent-a", origin.epoch, f"{att.gw_task}.e{step}",
                               "stale origin retry")
            att.metrics["stale_commits_accepted"] += 1
            att.committed.append({"step": step, "tool": att.plan[step].get("tool", "reserve"),
                                  "to": "stale-origin", "payload": "stale origin retry"})
        except PolicyDenied:
            att.metrics["stale_commits_fenced"] += 1
    dest = AgentState("agent-b", att.task, epoch)
    for step in range(len(att.plan)):
        att.hear(dest, step, min_at=att.m)  # only live events after the movement reach B
        att.run_step(dest, step, suffix=".r1")  # fresh run: no knowledge of origin's effect IDs
    att.metrics["steps_reexecuted"] = att.m
    return dest, "completed", None


def run_local_delegate(att: Attempt) -> Outcome:
    """B2-local: origin keeps ownership and delegates the pure remainder via PR #6 handoffs."""
    origin = att.run_origin_until_movement()
    blocked = sorted({att.plan[i]["op"] for i in range(att.m, len(att.plan))
                      if att.plan[i]["op"] not in DELEGABLE})
    if blocked:
        return origin, "refused", "incompatible_state:" + "+".join(blocked)
    if att.fault == "origin_preempted":
        att.fault_applied = True
        return origin, "incomplete", "origin_preempted_owner_not_transferred"
    tid = att.gw_task
    approval_class = att.task["classification"] if att.task["classification"] in TRANSFERABLE else "synthetic"
    receiver = HandoffReceiver("agent-b", SQLiteStore(att.workdir / "receiver.sqlite"), [
        Approval(f"approval-{tid}", tid, "agent-a", "agent-b", kind, classification=approval_class)
        for kind in ("word_count", "sha256")])

    def remote(step: int, kind: str, text: str) -> int | str:
        envelope = {
            "schema_version": SCHEMA_VERSION, "movement_id": f"{tid}.m{step}",
            "logical_task_id": tid, "operation": "delegate",
            "origin": {"agent_id": "agent-a"}, "destination": {"agent_id": "agent-b"},
            "task": {"kind": kind, "text": text},
            "context": {"classification": att.task["classification"]},
            "authority": {"approval_ref": f"approval-{tid}"},
            "execution": {"idempotency_key": f"{tid}.k{step}"},
            "observability": {"trace_id": f"{tid}.t{step}"},
        }
        copies = att.send(envelope)
        receipts = [receiver.receive(json.loads(canonical(envelope))) for _ in range(copies)]
        for receipt in receipts:
            att.metrics["transfer_bytes"] += len(canonical(receipt).encode("utf-8"))
            att.metrics["transfer_messages"] += 1
        first = receipts[0]
        if (first["status"] != "completed" or first["replayed"]
                or first["artifact_digest"] != digest(first["artifact"])
                or first["envelope_digest"] != digest(envelope)):
            raise RuntimeError("receipt failed verification")
        for extra in receipts[1:]:
            if not extra["replayed"] or extra["artifact"] != first["artifact"]:
                raise RuntimeError("duplicate delivery executed twice")
            att.metrics["duplicate_deliveries_suppressed"] += 1
        return first["artifact"]["value"]

    try:
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


RUNNERS: dict[str, Callable[[Attempt], Outcome]] = {
    "keep_on_origin": run_keep,
    "restart_on_destination": run_restart,
    "local_delegate": run_local_delegate,
}


# --------------------------------------------------------------------------- evaluation

def check_constraint(rule: dict[str, Any], task: dict[str, Any], state: AgentState,
                     committed: list[dict[str, Any]]) -> bool:
    payloads = [c["payload"] for c in committed]
    kind = rule["rule"]
    if kind == "redact_terms":
        blob = "\n".join(state.out + payloads)
        return not any(term in blob for term in rule["terms"])
    if kind == "forbid_path":
        return state.files.get(rule["path"]) == task["input"].get("files", {}).get(rule["path"])
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
        return db.execute("SELECT COUNT(*) FROM effects").fetchone()[0]
    finally:
        db.close()


METRIC_KEYS = ("task_correct", "output_correct", "constraints_preserved", "constraints_total",
               "policy_violations", "duplicate_effects", "unexpected_effects", "missing_effects",
               "effects_committed", "unknown_events", "reconciled_events", "stale_commits_fenced",
               "stale_commits_accepted", "duplicate_deliveries_suppressed", "steps_executed",
               "steps_reexecuted", "transfer_bytes", "transfer_messages", "sensitive_transfers")


def run_attempt(task: dict[str, Any], truth: dict[str, Any] | None, mode: str, fault: str,
                workdir: Path) -> dict[str, Any]:
    """Run one attempt and return a sanitized record (IDs, enums, counts, digests only)."""
    info = MODES[mode]
    record: dict[str, Any] = {"task_id": task["task_id"], "family": task["family"], "mode": mode,
                              "baseline": info["baseline"], "mode_status": info["status"],
                              "tracking": info["tracking"], "fault": fault, "fault_applied": False,
                              "outcome": "unavailable", "reason": "baseline_not_implemented",
                              "model_calls": 0}
    record.update({k: None for k in METRIC_KEYS})
    t0 = time.perf_counter_ns()
    if info["status"] == "implemented":
        try:
            workdir.mkdir(parents=True, exist_ok=False)
            att = Attempt(task, fault, workdir)
            state, outcome, reason = RUNNERS[mode](att)
            if _ledger_rows(workdir / "effects.sqlite") != len(att.committed):
                raise RuntimeError("harness effect list disagrees with ledger")
            record.update(outcome=outcome, reason=reason, fault_applied=att.fault_applied)
            record.update(att.metrics)
            if truth is not None:
                record.update(evaluate(task, truth, state, att, outcome == "completed"))
        except Exception as exc:  # recorded as a harness error, never as a baseline success
            record.update({k: None for k in METRIC_KEYS})
            record.update(outcome="harness_error", reason=type(exc).__name__)
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


def _sec_classification_gate(case, fx, workdir):
    task, truth = _security_task(case, fx)
    rec = run_attempt(task, truth, case["mode"], case.get("fault", "none"), workdir / "attempt")
    if rec["outcome"] != "refused":
        observed = rec["outcome"]
    else:
        observed = "refused_before_transfer" if rec["transfer_bytes"] == 0 else "disclosed_before_refusal"
    return observed, {"reason": rec["reason"] or "none", "transfer_bytes_before_refusal": rec["transfer_bytes"] or 0}


def _sec_run_task(case, fx, workdir):
    task, truth = _security_task(case, fx)
    rec = run_attempt(task, truth, case["mode"], case.get("fault", "none"), workdir / "attempt")
    if case["expected"] == "fenced":
        fenced = rec["stale_commits_fenced"] == 1 and rec["stale_commits_accepted"] == 0
        return ("fenced" if fenced else "unfenced"), {
            "stale_commits_fenced": rec["stale_commits_fenced"] or 0,
            "stale_commits_accepted": rec["stale_commits_accepted"] or 0}
    return rec["outcome"], {"reason": rec["reason"] or "none", "transfer_bytes": rec["transfer_bytes"] or 0}


def _sec_canary(case, fx, workdir):
    task, truth = _security_task(case, fx)
    rec = run_attempt(task, truth, case["mode"], "none", workdir / "attempt")
    receiver_db = workdir / "attempt" / "receiver.sqlite"
    audit = SQLiteStore(receiver_db).audit() if receiver_db.exists() else []
    leaked = CANARY in canonical(rec) or CANARY in canonical(audit)
    observed = "leaked" if leaked else ("absent_from_records_and_audit" if rec["outcome"] == "completed"
                                        else rec["outcome"])
    return observed, {"attempt_outcome": rec["outcome"], "audit_events": len(audit),
                      "canary_sent_to_receiver": rec["sensitive_transfers"] is not None
                      and rec["sensitive_transfers"] > 0}


def _sec_forged_destination(case, fx, workdir):
    receiver = _neg_receiver(workdir)
    try:
        receiver.receive(_envelope("forged", destination={"agent_id": "agent-x"}))
    except PolicyDenied:
        return "denied", {"denial_type": "PolicyDenied"}
    return "accepted", {"denial_type": "none"}


def _sec_movement_id_reuse(case, fx, workdir):
    receiver = _neg_receiver(workdir)
    receiver.receive(_envelope("reuse"))
    try:
        receiver.receive(_envelope("reuse", execution={"idempotency_key": "neg-key-other"}))
    except Conflict:
        return "denied", {"denial_type": "Conflict"}
    return "accepted", {"denial_type": "none"}


def _sec_effect_conflict(case, fx, workdir):
    gateway = EffectGateway(SQLiteStore(workdir / "neg.sqlite"))
    epoch = gateway.claim("neg-effects", "agent-a")
    gateway.commit("neg-effects", "agent-a", epoch, "neg-effect-1", "synthetic payload")
    try:
        gateway.commit("neg-effects", "agent-a", epoch, "neg-effect-1", "different payload")
    except Conflict:
        return "denied", {"denial_type": "Conflict"}
    return "accepted", {"denial_type": "none"}


def _sec_data_not_instructions(case, fx, workdir):
    task, truth = _security_task(case, fx)
    rec = run_attempt(task, truth, case["mode"], "none", workdir / "attempt")
    declared = {op["to"] for op in task["plan"] if op["op"] == "effect"}
    ok = (rec["outcome"] == "completed" and rec["task_correct"] is True
          and rec["unexpected_effects"] == 0 and rec["effects_committed"] == len(declared))
    return ("not_executed" if ok else "executed_or_failed"), {
        "task_correct": bool(rec["task_correct"]), "unexpected_effects": rec["unexpected_effects"] or 0}


def _sec_tampered_fixture(case, fx, workdir):
    copy = workdir / "fixtures"
    shutil.copytree(fx.directory, copy)
    target = copy / "tasks.jsonl"
    data = bytearray(target.read_bytes())
    data[-2] = ord("X") if data[-2] != ord("X") else ord("Y")
    target.write_bytes(bytes(data))
    try:
        verify_fixtures(copy)
    except FixtureError:
        return "rejected", {"error_type": "FixtureError"}
    return "accepted", {"error_type": "none"}


def _sec_unknown(case, fx, workdir):
    gateway = EffectGateway(SQLiteStore(workdir / "neg.sqlite"))
    gateway.claim("neg-effects", "agent-a")
    return gateway.reconcile("neg-effects", "never-committed"), {"local_ledger_authoritative_only": True}


def _sec_revocation(case, fx, workdir):
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


SECURITY: dict[str, Callable[[dict[str, Any], Fixtures, Path], tuple[str, dict[str, Any]]]] = {
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
        except Exception as exc:
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

def fault_schedule(task_ids: list[str], seeds: list[int]) -> dict[tuple[int, str], str]:
    """Seeded, balanced, auditable: no global RNG state, identical on every Python version."""
    schedule = {}
    for seed in seeds:
        order = sorted(task_ids, key=lambda t: hashlib.sha256(f"{SUITE_VERSION}:{seed}:{t}".encode()).hexdigest())
        for position, task_id in enumerate(order):
            schedule[(seed, task_id)] = FAULT_KINDS[(position + seed) % len(FAULT_KINDS)]
    return schedule


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
    fx = load_fixtures(suite, fixtures)
    tasks, seeds, repeats = _selection(fx, subset, seeds, repeats)
    schedule = fault_schedule([t["task_id"] for t in fx.tasks], seeds)
    run_version = {"suite_version": SUITE_VERSION, "fixture_release_digest": fx.manifest["release_digest"],
                   "contract_version": SCHEMA_VERSION, "harness_version": HARNESS_VERSION,
                   "executor": EXECUTOR, "model": MODEL, "python": platform.python_version()}
    run_id = digest({"run_version": run_version, "subset": subset, "seeds": seeds, "repeats": repeats})[:16]
    records: list[dict[str, Any]] = [{
        "record_type": "run_manifest", "run_id": run_id, "run_version": run_version, "subset": subset,
        "seeds": seeds, "repeats": repeats, "tasks": [t["task_id"] for t in tasks],
        "modes": {m: dict(v) for m, v in MODES.items()}, "fault_kinds": list(FAULT_KINDS),
        "fault_assignment": fx.seeds["fault_assignment"],
        "started_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat() if timing else None}]
    with tempfile.TemporaryDirectory(prefix="mobilitybench-v0.1-") as directory:
        root = Path(directory)
        for repeat in range(repeats):
            for seed in seeds:
                for task in tasks:
                    fault = schedule[(seed, task["task_id"])]
                    for mode in MODES:
                        record = run_attempt(task, fx.truth.get(task["task_id"]), mode, fault,
                                             root / f"r{repeat}-s{seed}-{task['task_id']}-{mode}")
                        if not timing:
                            record["elapsed_ms"] = None
                        records.append({"record_type": "attempt", "run_id": run_id, "run_version": run_version,
                                        "seed": seed, "repeat": repeat, **record})
        for record in run_security_cases(fx, root, timing):
            records.append({**record, "run_id": run_id, "run_version": run_version})
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
    }


def reproducibility(records: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple, set[str]] = {}
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


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    attempts = _attempts(records)
    security = [r for r in records if r.get("record_type") == "security"]
    manifest = next((r for r in records if r.get("record_type") == "run_manifest"), {})
    repro = reproducibility(records)
    return {
        "suite_version": SUITE_VERSION, "run_id": manifest.get("run_id"), "subset": manifest.get("subset"),
        "outcome_digest": outcome_digest(records),
        "attempts_repeat0": len(attempts),
        "harness_errors": sum(r["outcome"] == "harness_error" for r in _attempts(records, None)),
        "modes": {m: mode_summary([r for r in attempts if r["mode"] == m]) for m in MODES},
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
    rv = manifest["run_version"]
    lines = [
        f"# MobilityBench v0.1 report — run `{manifest['run_id']}`",
        "",
        "> **Pilot, deterministic, LLM-free.** A scripted interpreter executed frozen synthetic tasks; "
        "effects are simulated SQLite commits. Outcomes are deterministic functions of (task, mode, fault), "
        "so repeats test reproducibility, not sampling variance: no confidence intervals or significance "
        "claims are made, and none should be inferred from these counts. Unavailable baselines are listed, "
        "not scored. See `docs/mobilitybench-v0.1.md` for rubrics and validity threats.",
        "",
        "## Run manifest",
        "",
        "| field | value |", "| --- | --- |",
        *[f"| {k} | `{v}` |" for k, v in rv.items()],
        f"| subset | `{manifest['subset']}` |",
        f"| seeds | `{', '.join(map(str, manifest['seeds']))}` |",
        f"| repeats | `{manifest['repeats']}` |",
        f"| tasks | {len(manifest['tasks'])} |",
        f"| started_at | `{manifest['started_at']}` |",
        f"| outcome_digest (timing-free) | `{summary['outcome_digest']}` |",
        "",
        "## Denominators",
        "",
        f"- Attempt records (all repeats): **{len(_attempts(records, None))}**; summary tables use repeat 0 only: "
        f"**{len(attempts)}** = {len(manifest['tasks'])} tasks × {len(manifest['seeds'])} seeds × {len(MODES)} modes.",
        f"- Implemented-mode attempts (repeat 0): **{sum(r['mode_status'] == 'implemented' for r in attempts)}**; "
        f"unavailable-mode records: **{sum(r['mode_status'] == 'unavailable' for r in attempts)}** (not scored).",
        f"- Harness errors (all repeats): **{summary['harness_errors']}**.",
        f"- Security/negative cases: **{summary['security_total']}** "
        f"({summary['security']['pass']} pass, {summary['security']['known_gap']} known gap, "
        f"{summary['security']['gap_closed']} gap closed, {summary['security']['fail']} fail).",
        "",
        "## Baseline summary (repeat 0)",
        "",
        "`correct` requires completed + exact output digest + all constraints + no policy violation, "
        "duplicate, unexpected or missing effect. Each fraction shows its own denominator.",
        "",
        "| mode | baseline | status | completed | correct / attempts | correct / completed | constraints kept "
        "(completed) | policy violations | duplicate effects | unexpected effects | unknown→reconciled | "
        "stale fenced | transfer bytes | refused | incomplete | median ms |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for mode, info in MODES.items():
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
    implemented = [m for m, i in MODES.items() if i["status"] == "implemented"]
    for title, key, values in (("By fault (repeat 0): correct / attempts", "fault", FAULT_KINDS),
                               ("By family (repeat 0): correct / attempts", "family", FAMILIES)):
        lines += ["", f"## {title}", "", "| mode | " + " | ".join(values) + " |",
                  "| --- |" + " ---: |" * len(values)]
        for mode in implemented:
            cells = []
            for value in values:
                rows = [r for r in attempts if r["mode"] == mode and r[key] == value]
                cells.append(_frac(sum(r["task_correct"] is True for r in rows), len(rows)))
            lines.append(f"| {mode} | " + " | ".join(cells) + " |")
    reasons = Counter((r["mode"], r["outcome"], r["reason"]) for r in attempts
                      if r["outcome"] in ("refused", "incomplete", "harness_error"))
    lines += ["", "## Refusals, incomplete attempts and harness errors (repeat 0)", "",
              "| mode | outcome | reason | count |", "| --- | --- | --- | ---: |"]
    lines += [f"| {m} | {o} | `{why}` | {n} |" for (m, o, why), n in sorted(reasons.items())] or ["| – | – | – | 0 |"]
    lines += ["", "## Unavailable baselines", "",
              "| mode | baseline | tracking | records |", "| --- | --- | --- | ---: |"]
    lines += [f"| {m} | {i['baseline']} | {i['tracking']} | {summary['modes'][m]['unavailable']} |"
              for m, i in MODES.items() if i["status"] != "implemented"]
    security = [r for r in records if r.get("record_type") == "security"]
    lines += ["", "## Negative and security fixtures", "",
              "A `known_gap` reproduces a deliberately documented missing control; it is **not** a pass. "
              "`gap_closed` means the control now exists: the case must be rewritten in the next suite version.", "",
              "| case | mode | questions | expected | observed | verdict |", "| --- | --- | --- | --- | --- | --- |"]
    lines += [f"| {r['case_id']} | {r['mode']} | {', '.join(r['question_ids'])} | `{r['expected']}` | "
              f"`{r['observed']}` | **{r['verdict']}** |" for r in security]
    repro = reproducibility(records)
    lines += ["", "## Reproducibility", "",
              f"- Repeats: {repro['repeats']}; (seed, task, mode) groups: {repro['groups']}; groups with differing "
              f"outcome fingerprints: **{len(repro['mismatched'])}**" +
              (": " + ", ".join(repro["mismatched"]) if repro["mismatched"] else "."),
              "- Fingerprints exclude wall-clock time, which is machine-dependent and not a fair cross-mode "
              "latency comparison.", "",
              "## Raw per-case results (repeat 0)", "",
              "| seed | task | family | mode | fault | applied | outcome | reason | correct | output | constraints "
              "| policy | dup | unexp | missing | unknown | fenced | bytes | ms |",
              "| ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: "
              "| ---: | ---: | ---: |"]
    for r in attempts:
        constraints = ("–" if r["constraints_preserved"] is None
                       else _frac(r["constraints_preserved"], r["constraints_total"]))
        lines.append(" | ".join([
            f"| {r['seed']}", r["task_id"], r["family"], r["mode"], r["fault"], _cell(r["fault_applied"]),
            r["outcome"], f"`{r['reason']}`" if r["reason"] else "–", _cell(r["task_correct"]),
            _cell(r["output_correct"]), constraints, _cell(r["policy_violations"]), _cell(r["duplicate_effects"]),
            _cell(r["unexpected_effects"]), _cell(r["missing_effects"]), _cell(r["unknown_events"]),
            _cell(r["stale_commits_fenced"]), _cell(r["transfer_bytes"]), f"{_cell(r['elapsed_ms'])} |"]))
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
                                     description="MobilityBench v0.1 (deterministic, LLM-free, synthetic).")
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify", help="check frozen fixtures against the release SHA-256 manifest")
    run = sub.add_parser("run", help="run baselines, faults and negative fixtures; write sanitized JSONL")
    schedule = sub.add_parser("schedule", help="print the seeded fault schedule as JSONL")
    for p in (verify, run, schedule):
        p.add_argument("--suite", default="v0.1", choices=sorted(SUITES))
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
            manifest = verify_fixtures(fixture_dir(args.suite, args.fixtures))
            print(json.dumps({"verified": True, "suite_version": manifest["suite_version"],
                              "release_digest": manifest["release_digest"], "files": manifest["files"]},
                             indent=2, sort_keys=True))
            return 0
        if args.command == "schedule":
            fx = load_fixtures(args.suite, args.fixtures)
            tasks, seeds, _ = _selection(fx, args.subset, seeds, None)
            plan = fault_schedule([t["task_id"] for t in fx.tasks], seeds)
            for seed in seeds:
                for task in tasks:
                    print(json.dumps({"seed": seed, "task_id": task["task_id"],
                                      "fault": plan[(seed, task["task_id"])]}, sort_keys=True))
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
