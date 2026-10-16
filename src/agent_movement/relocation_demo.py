"""One-command checkpoint-relocation experiment and crash/duplicate fault matrix.

    python -m pip install -e '.[relocation]'
    python -m agent_movement.relocation_demo [--json results.json]
    python -m agent_movement.relocation_demo --two-store [--json results.json]
    python -m agent_movement.relocation_demo reconcile --help   # operator CLI (issue #30)

The default mode shares one SQLite file between coordinator and workers. ``--two-store``
gives each worker its own store and copies the checkpoint as a digest-verified bundle
(scenarios in :mod:`agent_movement.relocation_demo_two_store`). Both modes end with the
operator-reconciliation rows that resolve the effects parked by C13/C14
(:mod:`agent_movement.relocation_demo_reconcile`).

Every actor action (origin worker, coordinator, receiver worker) runs in a
freshly forked OS process that shares nothing with the next action except the
SQLite file. An injected crash is ``os._exit`` at the named transition: no
``finally`` blocks, no SQLite commit, no LangGraph error bookkeeping. POSIX only.
All data are synthetic; there are no model calls and no network access.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path
from typing import Any, Callable

from .core import EffectGateway, SQLiteStore
from .relocation import (CRASH_EXIT, EXPORTED_STATE, PINNED_RUNTIME, UNSUPPORTED_STATE, Coordinator,
                         EffectLedger, Faults, Worker, effect_payload, init_store, local_profile,
                         observe, runtime_versions)

TASK = "task-report-1"
EFFECT_ID = "publish-report"
ITEMS = [
    "synthetic invoice alpha for relocation test",
    "second synthetic record",
    "third record has five words",
    "fourth",
    "fifth synthetic entry with six words",
    "sixth and final synthetic line",
]
EXPECTED_WORDS = sum(len(item.split()) for item in ITEMS)
DENIED = ("PolicyDenied", "Conflict", "Incompatible", "ContractError")


def constraints(tool: str = "gateway") -> dict[str, Any]:
    return {"classification": "synthetic", "effect_tool": tool, "effect_id": EFFECT_ID,
            "max_gated_effects": 1}


def run_actor(action: Callable[[], Any]) -> dict[str, Any]:
    """Run one actor action in a forked child; only its SQLite writes survive it."""
    sys.stdout.flush()
    sys.stderr.flush()
    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:  # child
        os.close(read_fd)
        code = 0
        try:
            outcome = {"ok": True, "value": action()}
        except BaseException as exc:  # report every failure to the parent as data
            code = 0 if type(exc).__name__ in DENIED else 1
            outcome = {"ok": False, "error": type(exc).__name__, "message": str(exc),
                       "report": getattr(exc, "report", None)}
        with os.fdopen(write_fd, "wb") as pipe:
            pipe.write(json.dumps(outcome, default=str).encode("utf-8"))
        os._exit(code)
    os.close(write_fd)
    with os.fdopen(read_fd, "rb") as pipe:
        data = pipe.read()
    _, status = os.waitpid(pid, 0)
    exit_code = os.waitstatus_to_exitcode(status)
    result = json.loads(data) if data else {"ok": False, "error": "process_crashed"}
    result["exit_code"] = exit_code
    result["crashed"] = exit_code == CRASH_EXIT
    return result


class Run:
    """One scenario: a fresh SQLite store plus helpers that run each actor out of process."""

    def __init__(self, root: str, name: str, tool: str = "gateway"):
        self.path = str(Path(root) / f"{name}.sqlite")
        self.tool = tool
        self.steps: list[str] = []
        init_store(self.path)

    def act(self, label: str, action: Callable[[], Any]) -> dict[str, Any]:
        result = run_actor(action)
        if result["crashed"]:
            outcome = "CRASH"
        elif result["ok"]:
            outcome = "ok"
        else:
            outcome = result["error"]
        self.steps.append(f"{label}: {outcome}")
        if result["exit_code"] not in (0, CRASH_EXIT):
            raise RuntimeError(f"{label} failed unexpectedly: {result}")
        return result

    def observe(self) -> dict[str, Any]:
        return observe(self.path, TASK, EFFECT_ID)

    def worker(self, worker: str, incarnation: int = 1, crash: str | None = None) -> Worker:
        return Worker(self.path, worker, incarnation, faults=Faults(crash))

    # --- actor actions -------------------------------------------------
    def start_a(self, supersteps: int = 3) -> dict[str, Any]:
        path, tool = self.path, self.tool
        return self.act("A starts and runs 3 supersteps", lambda: Worker(path, "worker-a").start(
            TASK, ITEMS, constraints(tool), max_supersteps=supersteps))

    def export(self, movement: str = "move-1", to: str = "worker-b.1", crash: str | None = None):
        path = self.path
        return self.act(f"A exports {movement}", lambda: Worker(
            path, "worker-a", faults=Faults(crash)).attach(TASK, 1).export(movement, to))

    def transfer(self, movement: str = "move-1", profile: dict[str, Any] | None = None,
                 crash: str | None = None):
        path = self.path
        return self.act(f"coordinator transfers {movement}", lambda: Coordinator(
            path, Faults(crash)).transfer(movement, profile or local_profile()))

    def accept(self, worker: str = "worker-b", incarnation: int = 1, movement: str = "move-1",
               crash: str | None = None):
        path = self.path
        return self.act(f"{worker}.{incarnation} accepts {movement}", lambda: Worker(
            path, worker, incarnation, faults=Faults(crash)).accept(movement))

    def run(self, worker: str = "worker-b", incarnation: int = 1, epoch: int = 2,
            supersteps: int | None = None, crash: str | None = None, check: bool = True):
        path = self.path
        return self.act(f"{worker}.{incarnation}@{epoch} runs", lambda: Worker(
            path, worker, incarnation, faults=Faults(crash)).attach(TASK, epoch).run(
                supersteps, check_ownership=check))

    def failover(self, movement: str, to: str):
        path = self.path
        return self.act(f"coordinator failover {movement} -> {to}", lambda: Coordinator(path).failover(
            movement, TASK, to, local_profile()))

    def relocate(self) -> None:
        """Happy-path cooperative relocation A -> worker-b.1 (no faults)."""
        self.export()
        self.transfer()
        self.accept()

    def recover_to_b2(self, movement: str = "move-2", epoch: int = 3) -> None:
        """Standard recovery after a receiver-side crash: new execution, new epoch."""
        self.failover(movement, "worker-b.2")
        self.accept("worker-b", 2, movement)
        self.run("worker-b", 2, epoch)


def completed(obs: dict[str, Any]) -> bool:
    values = obs["values"] or {}
    return (values.get("status") == "done" and values.get("word_total") == EXPECTED_WORDS
            and sorted(a["index"] for a in values.get("artifacts", [])) == list(range(len(ITEMS)))
            and values.get("constraints") == constraints(values.get("constraints", {}).get("effect_tool", ""))
            and len(obs["gateway_commits"]) + obs["opaque_invocations"] == 1)


def unchanged(before: dict[str, Any], after: dict[str, Any]) -> bool:
    keys = ("owner", "head_checkpoint_id", "gateway_commits", "opaque_invocations", "relocations",
            "reconciliations")
    # Two-store observations also summarize every worker store (absent = single store).
    return all(before[k] == after[k] for k in keys) and before.get("stores") == after.get("stores")


def evidence(obs: dict[str, Any]) -> dict[str, Any]:
    values = obs["values"] or {}
    return {"final_status": values.get("status"),
            "final_owner": None if obs["owner"] is None else
            f"{obs['owner']['execution_id']}@{obs['owner']['epoch']}",
            "gateway_commits": len(obs["gateway_commits"]),
            "opaque_invocations": obs["opaque_invocations"],
            "item_reexecutions": obs["item_reexecutions"],
            "effect_ledger": (obs["effect_intent"] or {}).get("status")}


# --- scenarios --------------------------------------------------------------
# Each returns (observed_outcome, recovery_description, final_observation).

def _crash_then(run: Run, crashed: dict[str, Any], recover: Callable[[], None]) -> None:
    if not crashed["crashed"]:
        raise RuntimeError(f"fault did not fire: {run.steps}")
    recover()


def c_origin_before_export(run: Run):
    run.start_a()
    _crash_then(run, run.export(crash="origin.before_export"), lambda: (
        run.failover("move-1", "worker-b.1"), run.accept(), run.run()))
    return "failover from durable head", run.observe()


def c_origin_after_export(run: Run):
    run.start_a()
    _crash_then(run, run.export(crash="origin.after_export"), lambda: (
        run.transfer(), run.accept(), run.run()))
    return "coordinator continues recorded request", run.observe()


def c_coordinator_before_transfer(run: Run):
    run.start_a()
    run.export()
    _crash_then(run, run.transfer(crash="coordinator.before_transfer"), lambda: (
        run.transfer(), run.accept(), run.run()))
    return "transaction rolled back; restarted coordinator retries", run.observe()


def c_coordinator_after_transfer(run: Run):
    run.start_a()
    run.export()
    _crash_then(run, run.transfer(crash="coordinator.after_transfer"), lambda: (
        run.transfer(), run.accept(), run.run()))
    return "grant re-delivered from durable record (no 2nd epoch bump)", run.observe()


def c_receiver_before_accept(run: Run):
    run.start_a()
    run.export()
    run.transfer()
    _crash_then(run, run.accept(crash="receiver.before_accept"), run.recover_to_b2)
    return "failover worker-b.1 -> worker-b.2 (epoch 3)", run.observe()


def c_receiver_after_accept(run: Run):
    run.start_a()
    run.export()
    run.transfer()
    _crash_then(run, run.accept(crash="receiver.after_accept"), run.recover_to_b2)
    return "failover worker-b.1 -> worker-b.2 (epoch 3)", run.observe()


def c_checkpoint_before_commit(run: Run):
    run.start_a()
    run.relocate()
    _crash_then(run, run.run(crash="checkpoint.before_commit"), run.recover_to_b2)
    return "failover; LangGraph re-applies durable pending writes", run.observe()


def c_checkpoint_after_commit(run: Run):
    run.start_a()
    run.relocate()
    _crash_then(run, run.run(crash="checkpoint.after_commit"), run.recover_to_b2)
    return "failover from B's newer checkpoint", run.observe()


def _effect_crash(point: str, note: str):
    def scenario(run: Run):
        run.start_a()
        run.relocate()
        _crash_then(run, run.run(crash=point), run.recover_to_b2)
        return note, run.observe()
    return scenario


def c_ack_after(run: Run):
    run.start_a()
    run.export()
    run.transfer()
    _crash_then(run, run.accept(crash="ack.after"), run.recover_to_b2)
    return "failover worker-b.1 -> worker-b.2 (epoch 3)", run.observe()


def _injected(run: Run, label: str, action: Callable[[], Any], expect: str,
              finish: Callable[[], None]) -> tuple[str, str, dict[str, Any]]:
    before = run.observe()
    result = run.act(label, action)
    after = run.observe()
    value = result.get("value")
    replayed = isinstance(value, dict) and value.get("replayed") is True or value is False
    if not unchanged(before, after):
        observed = "VIOLATION: state changed"
    elif not result["ok"] and result["error"] in DENIED:
        observed = "denied"
    elif result["ok"] and replayed:
        observed = "deduplicated"
    else:
        observed = f"UNEXPECTED: {result}"
    finish()
    return observed, f"{label} -> {result.get('error') or 'ok'}", run.observe()


def d_origin_duplicate(run: Run):
    run.start_a()
    run.relocate()
    path = run.path
    manifest = Coordinator(path).get("move-1")["manifest_json"]
    return _injected(run, "duplicate request move-1", lambda: Coordinator(path).request(json.loads(manifest)),
                     "deduplicated", lambda: run.run())


def d_origin_stale(run: Run):
    run.start_a()
    run.relocate()
    return _injected(run, "fenced A exports move-9", lambda: Worker(run.path, "worker-a").attach(
        TASK, 1).export("move-9", "worker-c.1"), "denied", lambda: run.run())


def d_coordinator_duplicate(run: Run):
    run.start_a()
    run.relocate()
    return _injected(run, "duplicate transfer move-1", lambda: Coordinator(run.path).transfer(
        "move-1", local_profile()), "deduplicated", lambda: run.run())


def d_receiver_duplicate(run: Run):
    run.start_a()
    run.relocate()
    run.run(supersteps=1)
    return _injected(run, "duplicate grant move-1 after B progressed", lambda: Worker(
        run.path, "worker-b").accept("move-1"), "deduplicated", lambda: run.run())


def d_receiver_stale(run: Run):
    run.start_a()
    run.export()
    run.transfer()
    run.failover("move-2", "worker-b.2")
    run.accept("worker-b", 2, "move-2")
    return _injected(run, "delayed grant move-1 to worker-b.1", lambda: Worker(
        run.path, "worker-b").accept("move-1"), "denied", lambda: run.run("worker-b", 2, 3))


def d_checkpoint_partition(run: Run):
    run.start_a()
    run.relocate()
    return _injected(run, "partitioned A keeps stepping", lambda: Worker(run.path, "worker-a").attach(
        TASK, 1).run(1, check_ownership=False), "denied", lambda: run.run())


def d_intent_stale(run: Run):
    run.start_a()
    run.relocate()
    return _injected(run, "fenced A records effect intent", lambda: EffectLedger(SQLiteStore(run.path))
                     .record_intent(TASK, EFFECT_ID, "0" * 64, "gateway", "worker-a.1", 1),
                     "denied", lambda: run.run())


def d_commit_stale(run: Run):
    run.start_a()
    run.relocate()
    return _injected(run, "fenced A commits gated effect", lambda: EffectGateway(SQLiteStore(run.path))
                     .commit(TASK, "worker-a.1", 1, EFFECT_ID, "stale"), "denied", lambda: run.run())


def d_commit_duplicate(run: Run):
    run.start_a()
    run.relocate()
    run.run()
    path = run.path

    def duplicate() -> bool:
        values = observe(path, TASK)["values"]
        return EffectGateway(SQLiteStore(path)).commit(TASK, "worker-b.1", 2, EFFECT_ID,
                                                       effect_payload(TASK, values))
    return _injected(run, "duplicate commit by B (same effect ID)", duplicate, "deduplicated", lambda: None)


def d_ack_duplicate(run: Run):
    run.start_a()
    run.relocate()
    return _injected(run, "duplicate ack from worker-b.1", lambda: Coordinator(run.path).acknowledge(
        "move-1", "worker-b.1", 2), "deduplicated", lambda: run.run())


def d_ack_stale(run: Run):
    run.start_a()
    run.relocate()
    return _injected(run, "stale ack from fenced A", lambda: Coordinator(run.path).acknowledge(
        "move-1", "worker-a.1", 1), "denied", lambda: run.run())


def _mismatch(field: str, change: Callable[[dict[str, Any]], None]):
    def scenario(run: Run):
        run.start_a()
        run.export()
        profile = local_profile()
        change(profile)
        before = run.observe()
        result = run.transfer(profile=profile)
        after = run.observe()
        value = result.get("value") or {}
        report = value.get("report") or {}
        refused = value.get("status") == "refused" and not report.get("compatible", True)
        same_owner = before["owner"] == after["owner"] and before["head_checkpoint_id"] == after["head_checkpoint_id"]
        observed = "denied" if refused and same_owner else f"UNEXPECTED: {result}"
        run.run("worker-a", 1, 1)  # fail closed but not lost: A still owns and finishes
        note = (f"refused ({field}); lost={report.get('lost_state')}, "
                f"unavailable={len(report.get('unavailable_state', []))} channels; A keeps epoch 1")
        return observed, note, run.observe(), report
    return scenario


def v_digest_mismatch(run: Run):
    run.start_a()
    run.export()
    run.transfer()
    with closing(sqlite3.connect(run.path)) as db:  # simulate manifest/checkpoint divergence
        raw = json.loads(db.execute("SELECT manifest_json FROM relocations WHERE movement_id='move-1'")
                         .fetchone()[0])
        raw["checkpoint"]["digest"] = "0" * 64
        db.execute("UPDATE relocations SET manifest_json=? WHERE movement_id='move-1'", (json.dumps(raw),))
        db.commit()
    result = run.accept()
    report = result.get("report") or {}
    observed = "denied" if result.get("error") == "Incompatible" else f"UNEXPECTED: {result}"
    run.failover("move-2", "worker-a.2")
    run.accept("worker-a", 2, "move-2")
    run.run("worker-a", 2, 3)
    return (observed, "receiver refuses; failover back to worker-a.2 (epoch 3) completes",
            run.observe(), report)


MATRIX: list[dict[str, Any]] = [
    {"id": "C1", "transition": "origin", "fault": "crash before export request", "expected": "allowed",
     "scenario": c_origin_before_export},
    {"id": "C2", "transition": "origin", "fault": "crash after export request recorded", "expected": "allowed",
     "scenario": c_origin_after_export},
    {"id": "C3", "transition": "coordinator", "fault": "crash inside transfer txn (before commit)",
     "expected": "allowed", "scenario": c_coordinator_before_transfer},
    {"id": "C4", "transition": "coordinator", "fault": "crash after transfer commit (reply lost)",
     "expected": "allowed", "scenario": c_coordinator_after_transfer},
    {"id": "C5", "transition": "receiver", "fault": "crash before reading grant", "expected": "allowed",
     "scenario": c_receiver_before_accept},
    {"id": "C6", "transition": "receiver", "fault": "crash after verifying checkpoint, before ack",
     "expected": "allowed", "scenario": c_receiver_after_accept},
    {"id": "C7", "transition": "checkpoint", "fault": "crash before B's first checkpoint commits",
     "expected": "allowed", "scenario": c_checkpoint_before_commit},
    {"id": "C8", "transition": "checkpoint", "fault": "crash after B's first checkpoint commits",
     "expected": "allowed", "scenario": c_checkpoint_after_commit},
    {"id": "C9", "transition": "effect-intent", "fault": "crash before intent is durable",
     "expected": "allowed", "scenario": _effect_crash("effect_intent.before", "failover; intent re-recorded")},
    {"id": "C10", "transition": "effect-intent", "fault": "crash after intent is durable",
     "expected": "allowed", "scenario": _effect_crash("effect_intent.after", "failover; intent idempotent")},
    {"id": "C11", "transition": "effect-commit", "fault": "gateway tool: crash after attempt mark, before call",
     "expected": "reconciled", "scenario": _effect_crash(
         "effect_commit.before", "reconcile: no commit record -> retry SAME effect ID (gateway dedups)")},
    {"id": "C12", "transition": "effect-commit", "fault": "gateway tool: crash after commit, before checkpoint",
     "expected": "reconciled", "scenario": _effect_crash(
         "effect_commit.after", "reconcile: commit record found -> adopt, no new commit")},
    {"id": "C13", "transition": "effect-commit", "fault": "opaque tool: crash after attempt mark, before call",
     "expected": "unknown", "tool": "opaque", "scenario": _effect_crash(
         "effect_commit.before", "no lookup possible -> parked reconcile_required, no blind retry")},
    {"id": "C14", "transition": "effect-commit", "fault": "opaque tool: crash after call, before checkpoint",
     "expected": "unknown", "tool": "opaque", "scenario": _effect_crash(
         "effect_commit.after", "no lookup possible -> parked reconcile_required, no blind retry")},
    {"id": "C15", "transition": "acknowledgement", "fault": "crash after ack recorded, before first step",
     "expected": "allowed", "scenario": c_ack_after},
    {"id": "D1", "transition": "origin", "fault": "delayed duplicate of the same export request",
     "expected": "deduplicated", "scenario": d_origin_duplicate},
    {"id": "D2", "transition": "origin", "fault": "fenced A sends a NEW export request", "expected": "denied",
     "scenario": d_origin_stale},
    {"id": "D3", "transition": "coordinator", "fault": "duplicate transfer command after ack",
     "expected": "deduplicated", "scenario": d_coordinator_duplicate},
    {"id": "D4", "transition": "receiver", "fault": "duplicate grant after B progressed",
     "expected": "deduplicated", "scenario": d_receiver_duplicate},
    {"id": "D5", "transition": "receiver", "fault": "delayed grant to superseded worker-b.1",
     "expected": "denied", "scenario": d_receiver_stale},
    {"id": "D6", "transition": "checkpoint", "fault": "partitioned A keeps stepping after transfer",
     "expected": "denied", "scenario": d_checkpoint_partition},
    {"id": "D7", "transition": "effect-intent", "fault": "delayed intent from fenced A", "expected": "denied",
     "scenario": d_intent_stale},
    {"id": "D8", "transition": "effect-commit", "fault": "delayed gated commit from fenced A (epoch 1)",
     "expected": "denied", "scenario": d_commit_stale},
    {"id": "D9", "transition": "effect-commit", "fault": "duplicate commit by B with same effect ID",
     "expected": "deduplicated", "scenario": d_commit_duplicate},
    {"id": "D10", "transition": "acknowledgement", "fault": "duplicate ack from B", "expected": "deduplicated",
     "scenario": d_ack_duplicate},
    {"id": "D11", "transition": "acknowledgement", "fault": "stale ack from fenced A", "expected": "denied",
     "scenario": d_ack_stale},
    {"id": "V1", "transition": "coordinator", "fault": "receiver graph_version 2", "expected": "denied",
     "scenario": _mismatch("graph_version", lambda p: p.update(graph_version="2"))},
    {"id": "V2", "transition": "coordinator", "fault": "receiver langgraph 1.3.0", "expected": "denied",
     "scenario": _mismatch("runtime", lambda p: p["runtime"].update(langgraph="1.3.0"))},
    {"id": "V3", "transition": "coordinator", "fault": "receiver lacks state channel step_log",
     "expected": "denied", "scenario": _mismatch(
         "channels", lambda p: p.update(channels=[c for c in p["channels"] if c != "step_log"]))},
    {"id": "V4", "transition": "receiver", "fault": "checkpoint digest != manifest (corruption)",
     "expected": "denied", "scenario": v_digest_mismatch},
]


def row_kind(row: dict[str, Any]) -> str:
    """'crash' rows are judged on the recovered end state, 'inject' rows on the injected message."""
    return row.get("kind", "crash" if row["id"].startswith("C") else "inject")


def classify(row: dict[str, Any], observed: str, obs: dict[str, Any]) -> str:
    """Crash rows are judged on the recovered end state; D/V rows on the injected message."""
    if row_kind(row) == "crash":
        values = obs["values"] or {}
        effect = values.get("effect", {})
        if row["expected"] == "unknown":
            ok = (values.get("status") == "reconcile_required" and effect.get("status") == "unknown"
                  and (obs["effect_intent"] or {}).get("status") == "unknown"
                  and obs["opaque_invocations"] <= 1 and not obs["gateway_commits"])
            return "unknown" if ok else "VIOLATION"
        if not completed(obs) or len(obs["gateway_commits"]) != 1:
            return "VIOLATION"
        if effect.get("reconciled"):
            ledger = (obs["effect_intent"] or {}).get("status")
            return "reconciled" if ledger == "reconciled_committed" else "VIOLATION"
        return "allowed"
    return observed


def run_matrix(root: str, matrix: list[dict[str, Any]] | None = None,
               run_class: type[Run] = Run) -> list[dict[str, Any]]:
    rows = []
    for spec in MATRIX if matrix is None else matrix:
        run = run_class(root, spec["id"], spec.get("tool", "gateway"))
        outcome = spec["scenario"](run)
        report = None
        if row_kind(spec) == "crash":
            recovery, obs = outcome
            observed = classify(spec, "", obs)
        else:
            observed, recovery, obs, *rest = outcome
            report = rest[0] if rest else None
            observed = classify(spec, observed, obs)
            if not completed(obs):
                observed = f"{observed} (VIOLATION: task did not complete)"
        rows.append({"id": spec["id"], "transition": spec["transition"], "fault": spec["fault"],
                     "tool": spec.get("tool", "gateway"), "expected": spec["expected"],
                     "observed": observed, "match": observed == spec["expected"],
                     "recovery": recovery, "evidence": evidence(obs), "report": report,
                     "steps": run.steps})
    return rows


def headline(root: str) -> dict[str, Any]:
    """A runs 3 of 6 items, moves to B, B finishes; compare against a B restart baseline."""
    run = Run(root, "headline")
    a = run.start_a()
    exported = run.export()
    grant = run.transfer()
    accepted = run.accept()
    fenced_step = run.act("partitioned A tries one more superstep", lambda: Worker(
        run.path, "worker-a").attach(TASK, 1).run(1, check_ownership=False))
    fenced_commit = run.act("fenced A tries a gated commit", lambda: EffectGateway(
        SQLiteStore(run.path)).commit(TASK, "worker-a.1", 1, EFFECT_ID, "stale"))
    b = run.run()
    obs = run.observe()
    baseline = Run(root, "restart-baseline")
    restart = baseline.act("restart baseline: B runs task from scratch", lambda: Worker(
        baseline.path, "worker-b").start(TASK, ITEMS, constraints()))
    manifest = exported["value"]["manifest"]
    values = obs["values"]
    by_execution: dict[str, list[int]] = {}
    for entry in values["step_log"]:
        if entry["node"] == "process_item":
            by_execution.setdefault(entry["execution_id"], []).append(entry["index"])
    b_first = next(c for c in obs["lineage"] if c["written_by"] == "worker-b.1")
    return {
        "steps": run.steps,
        "manifest": {k: manifest[k] for k in ("profile", "mode", "logical_task_id", "from_execution",
                                              "from_epoch", "to_execution", "checkpoint", "runtime",
                                              "graph_id", "graph_version", "uncertain_effects")},
        "grant": grant["value"], "accept": accepted["value"],
        "fenced_a_step": fenced_step.get("error"), "fenced_a_commit": fenced_commit.get("error"),
        "items_by_execution": by_execution,
        "process_item_runs": {"origin worker-a.1": a["value"]["node_runs"].get("process_item", 0),
                              "receiver worker-b.1": b["value"]["node_runs"].get("process_item", 0),
                              "restart baseline": restart["value"]["node_runs"].get("process_item", 0)},
        "fenced_a_attempts": obs["node_runs"]["worker-a.1"]["process_item"] - a["value"]["node_runs"]["process_item"],
        "b_first_checkpoint_parent_is_exported": b_first["parent"] == manifest["checkpoint"]["checkpoint_id"],
        "lineage_writers": [f"step {c['step']}: {c['written_by']}" for c in obs["lineage"]],
        "task_identity": TASK,
        "execution_identities": sorted({c["written_by"] for c in obs["lineage"]}),
        "constraints_preserved": values["constraints"] == constraints(),
        "artifacts_from_origin_preserved": [x["index"] for x in values["artifacts"]] == list(range(len(ITEMS))),
        "word_total": values["word_total"], "expected_word_total": EXPECTED_WORDS,
        "gateway_commits": obs["gateway_commits"], "final_owner": obs["owner"],
        "final_status": values["status"],
    }


def headline_ok(h: dict[str, Any]) -> bool:
    runs = h["process_item_runs"]
    return (h["fenced_a_step"] == "PolicyDenied" and h["fenced_a_commit"] == "PolicyDenied"
            and h["items_by_execution"] == {"worker-a.1": [0, 1, 2], "worker-b.1": [3, 4, 5]}
            and runs["origin worker-a.1"] == 3 and runs["receiver worker-b.1"] == 3
            and runs["restart baseline"] == len(ITEMS) and h["b_first_checkpoint_parent_is_exported"]
            and h["constraints_preserved"] and h["artifacts_from_origin_preserved"]
            and h["word_total"] == EXPECTED_WORDS and h["final_status"] == "done"
            and h["gateway_commits"] == [{"effect_id": EFFECT_ID, "epoch": 2}])


def markdown(rows: list[dict[str, Any]]) -> str:
    lines = ["| ID | Transition | Injected fault | Expected | Observed | Recovery / handling | "
             "Gated commits | Opaque calls | Item re-exec | Final |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        e = r["evidence"]
        lines.append(f"| {r['id']} | {r['transition']} | {r['fault']} | {r['expected']} | "
                     f"{r['observed']}{'' if r['match'] else ' **MISMATCH**'} | {r['recovery']} | "
                     f"{e['gateway_commits']} | {e['opaque_invocations']} | {e['item_reexecutions']} | "
                     f"{e['final_status']} @ {e['final_owner']} |")
    return "\n".join(lines)


def experiment(root: str, two_store: bool = False, reconciliation: bool = True) -> dict[str, Any]:
    """Headline + fault matrix; ``reconciliation`` adds the operator rows that resolve C13/C14."""
    if two_store:
        from . import relocation_demo_two_store as two
        results = two.experiment(root)
    else:
        h = headline(root)
        rows = run_matrix(root)
        results = {"mode": "single-store", "runtime": runtime_versions(), "pinned": PINNED_RUNTIME,
                   "python": sys.version.split()[0],
                   "exported_state": EXPORTED_STATE, "unsupported_state": UNSUPPORTED_STATE,
                   "headline": h, "headline_ok": headline_ok(h), "matrix": rows,
                   "all_rows_match": all(r["match"] for r in rows)}
    if reconciliation:
        from . import relocation_demo_reconcile as rec
        rows = rec.run_matrix(root, two_store)
        results["reconciliation"] = rows
        results["all_reconciliation_rows_match"] = all(r["match"] for r in rows)
    return results


HEADLINE_KEYS = ("items_by_execution", "process_item_runs", "fenced_a_step", "fenced_a_commit",
                 "fenced_a_attempts", "b_first_checkpoint_parent_is_exported", "lineage_writers",
                 "execution_identities", "task_identity", "constraints_preserved",
                 "artifacts_from_origin_preserved", "gateway_commits", "final_owner", "final_status")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    # Under the unified CLI sys.argv[0] is "agent-movement relocate"; keep that name in usage.
    invoked = os.path.basename(sys.argv[0]) if sys.argv and sys.argv[0] else ""
    prog = invoked if invoked.startswith("agent-movement") else "python -m agent_movement.relocation_demo"
    if argv[:1] == ["reconcile"]:  # the operator CLI owns everything after the subcommand
        from .relocation_reconcile import main as reconcile_main
        return reconcile_main(argv[1:], prog=f"{prog} reconcile")
    parser = argparse.ArgumentParser(prog=prog,
                                     description="Synthetic same-runtime checkpoint relocation experiment")
    parser.add_argument("--json", type=Path, help="also write full results as JSON")
    parser.add_argument("--two-store", action="store_true",
                        help="give each worker its own SQLite store and copy the checkpoint as a "
                             "digest-verified bundle (copy-specific fault matrix)")
    # Listed for --help only: "reconcile" is dispatched above, before this parser runs.
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("reconcile", add_help=False,
                        help="operator reconciliation of parked unknown-outcome effects (see 'reconcile --help')")
    options = parser.parse_args(argv)
    if not hasattr(os, "fork"):
        print("This experiment needs os.fork (Linux/macOS).", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="agent-relocation-") as root:
        results = experiment(root, two_store=options.two_store)
    h = results["headline"]
    print(f"runtime: {results['runtime']} (pinned: {results['runtime'] == results['pinned']}), "
          f"python {results['python']}")
    if options.two_store:
        print("\n== Headline (two stores): copy the checkpoint into Worker B's own store ==")
        keys = HEADLINE_KEYS + tuple(results["headline_two_store_keys"])
    else:
        print("\n== Headline: relocate task at a persisted checkpoint ==")
        keys = HEADLINE_KEYS
    print(json.dumps({k: h[k] for k in keys}, indent=2))
    print(f"headline_ok: {results['headline_ok']}")
    print("\n== Two-store bundle copy fault matrix ==" if options.two_store
          else "\n== Crash / duplicate / version fault matrix ==")
    print(markdown(results["matrix"]))
    print(f"\nrows: {len(results['matrix'])}, matching expectation: "
          f"{sum(r['match'] for r in results['matrix'])}")
    from . import relocation_demo_reconcile as rec
    print("\n== Operator reconciliation of the parked C13/C14 effects (issue #30) ==")
    print(rec.markdown(results["reconciliation"]))
    print(f"\nreconciliation rows: {len(results['reconciliation'])}, matching expectation: "
          f"{sum(r['match'] for r in results['reconciliation'])}")
    if options.json:
        options.json.write_text(json.dumps(results, indent=2, default=str) + "\n", encoding="utf-8")
    return 0 if results["headline_ok"] and results["all_rows_match"] and \
        results["all_reconciliation_rows_match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
