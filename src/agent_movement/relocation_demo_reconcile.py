"""Operator reconciliation rows: resolve the effects that rows C13/C14 park (issue #30).

    python -m agent_movement.relocation_demo               # printed after the 30-row matrix
    python -m agent_movement.relocation_demo --two-store   # same rows, one store per worker

Rows C13/C14 end with the task parked as ``reconcile_required``: an opaque tool cannot be
queried, so the worker cannot know whether its call happened. These rows replay both
crashes, let a simulated operator record ``confirmed_done`` or ``confirmed_absent``
(:meth:`agent_movement.relocation.Coordinator.reconcile`), resume the owner
(:meth:`agent_movement.relocation.Worker.resume_reconciled`) and judge the end state.

The operator's out-of-band check of the external system is simulated by the harness
reading the opaque tool's ground truth, which workers never read. Rows where the operator's
claim is FALSE are included on purpose: they show what the protocol cannot prevent (a lost
or a duplicated effect). As elsewhere, every actor action runs in a freshly forked process
and a crash is ``os._exit`` at the named point. Synthetic data only; no model calls.
"""

from __future__ import annotations

from typing import Any, Callable

from .relocation import RETRY_SUFFIX, Coordinator
from .relocation_demo import (EFFECT_ID, EXPECTED_WORDS, ITEMS, TASK, Run, _injected, completed, constraints,
                              evidence)
from .relocation_demo_two_store import TwoStoreRun

OPERATOR = "ops-alice"
RETRY_ID = EFFECT_ID + RETRY_SUFFIX
OUTCOMES = ("resolved", "misresolved", "denied", "deduplicated")


def reason(effect_id: str) -> str:
    return f"synthetic out-of-band check of the opaque tool for {effect_id}"


def out_of_band_check(obs: dict[str, Any], effect_id: str) -> str:
    """The simulated operator's view of the external system (harness ground truth)."""
    return "done" if obs["opaque_calls_by_effect"].get(effect_id, 0) else "absent"


# --- actor actions (each in a forked process) ---------------------------------------

def failover_to(run: Run, movement: str, incarnation: int, epoch: int) -> dict[str, Any]:
    """Replace worker-b's crashed execution: new incarnation, new epoch, from the durable head."""
    to = f"worker-b.{incarnation}"
    if isinstance(run, TwoStoreRun):
        run.failover(movement, to, "worker-b")
        run.copy(movement, "coordinator")
    else:
        run.failover(movement, to)
    run.accept("worker-b", incarnation, movement)
    return run.run("worker-b", incarnation, epoch)


def park(run: Run, point: str) -> dict[str, Any]:
    """Rows C13 (crash before the opaque call) and C14 (after it): worker-b.2@3 parks the task."""
    run.start_a()
    run.relocate()
    if not run.run(crash=point)["crashed"]:
        raise RuntimeError(f"fault did not fire: {run.steps}")
    failover_to(run, "move-2", 2, 3)
    obs = run.observe()
    if (obs["values"] or {}).get("status") != "reconcile_required":
        raise RuntimeError(f"task was not parked: {run.steps}")
    return obs


def reconcile_action(run: Run, decision: str, epoch: int = 3, effect_id: str = EFFECT_ID,
                     operator: str = OPERATOR) -> Callable[[], Any]:
    path = run.path
    return lambda: Coordinator(path).reconcile(TASK, effect_id, decision, operator=operator,
                                               reason=reason(effect_id), epoch=epoch)


def decide(run: Run, decision: str, epoch: int = 3, effect_id: str = EFFECT_ID,
           operator: str = OPERATOR) -> dict[str, Any]:
    return run.act(f"{operator} records {decision} for {effect_id} at epoch {epoch}",
                   reconcile_action(run, decision, epoch, effect_id, operator))


def resume(run: Run, incarnation: int = 2, epoch: int = 3, crash: str | None = None) -> dict[str, Any]:
    return run.act(f"worker-b.{incarnation}@{epoch} resumes after the decision", lambda: run.worker(
        "worker-b", incarnation, crash).attach(TASK, epoch).resume_reconciled())


# --- scenarios ----------------------------------------------------------------------

def resolution(point: str, decision: str):
    """Park, let the operator decide (truthfully or not), resume; judged on the end state."""
    def scenario(run: Run):
        truth = out_of_band_check(park(run, point), EFFECT_ID)
        decide(run, decision)
        resume(run)
        return truth, run.observe()
    return scenario


def r_stale_epoch(run: Run):
    park(run, "effect_commit.after")

    def finish() -> None:
        decide(run, "confirmed_done")
        resume(run)
    return _injected(run, "decision made at epoch 2 arrives at epoch 3",
                     reconcile_action(run, "confirmed_done", epoch=2), "denied", finish)


def r_duplicate(run: Run):
    park(run, "effect_commit.after")
    decide(run, "confirmed_done")
    resume(run)
    return _injected(run, "identical decision re-sent after resume",
                     reconcile_action(run, "confirmed_done"), "deduplicated", lambda: None)


def r_conflicting(run: Run):
    park(run, "effect_commit.after")
    decide(run, "confirmed_done")
    return _injected(run, "ops-bob records confirmed_absent",
                     reconcile_action(run, "confirmed_absent", operator="ops-bob"), "denied",
                     lambda: resume(run))


def r_not_parked(run: Run):
    run.start_a()
    run.relocate()
    run.run()
    return _injected(run, "confirmed_absent for a settled effect",
                     reconcile_action(run, "confirmed_absent", epoch=2), "denied", lambda: None)


def r_retry_budget(run: Run):
    park(run, "effect_commit.before")
    decide(run, "confirmed_absent")
    if not resume(run, crash="effect_commit.after")["crashed"]:
        raise RuntimeError(f"fault did not fire: {run.steps}")
    failover_to(run, "move-3", 3, 4)
    obs = run.observe()
    if (obs["values"] or {}).get("effect", {}).get("effect_id") != RETRY_ID:
        raise RuntimeError(f"the retry was not parked: {run.steps}")

    def finish() -> None:
        decide(run, "confirmed_done", epoch=4, effect_id=RETRY_ID)
        resume(run, 3, 4)
    return _injected(run, f"confirmed_absent for {RETRY_ID}",
                     reconcile_action(run, "confirmed_absent", epoch=4, effect_id=RETRY_ID), "denied", finish)


MATRIX: list[dict[str, Any]] = [
    {"id": "C13a", "extends": "C13", "kind": "resolution", "decision": "confirmed_absent", "truth": "absent",
     "fault": "operator: confirmed_absent (true)", "expected": "resolved",
     "scenario": resolution("effect_commit.before", "confirmed_absent")},
    {"id": "C13d", "extends": "C13", "kind": "resolution", "decision": "confirmed_done", "truth": "absent",
     "fault": "operator: confirmed_done (FALSE)", "expected": "misresolved",
     "scenario": resolution("effect_commit.before", "confirmed_done")},
    {"id": "C14d", "extends": "C14", "kind": "resolution", "decision": "confirmed_done", "truth": "done",
     "fault": "operator: confirmed_done (true)", "expected": "resolved",
     "scenario": resolution("effect_commit.after", "confirmed_done")},
    {"id": "C14a", "extends": "C14", "kind": "resolution", "decision": "confirmed_absent", "truth": "done",
     "fault": "operator: confirmed_absent (FALSE)", "expected": "misresolved",
     "scenario": resolution("effect_commit.after", "confirmed_absent")},
    {"id": "R1", "extends": "C14", "kind": "inject", "fault": "stale-epoch decision (epoch 2 after failover to 3)",
     "expected": "denied", "scenario": r_stale_epoch},
    {"id": "R2", "extends": "C14", "kind": "inject", "fault": "double resolution: identical decision replayed",
     "expected": "deduplicated", "scenario": r_duplicate},
    {"id": "R3", "extends": "C14", "kind": "inject",
     "fault": "double resolution: second operator, opposite decision", "expected": "denied",
     "scenario": r_conflicting},
    {"id": "R4", "extends": "-", "kind": "inject", "fault": "decision for an effect that was never parked",
     "expected": "denied", "scenario": r_not_parked},
    {"id": "R5", "extends": "C13", "kind": "inject",
     "fault": "confirmed_absent for the retry (retry crashed too)", "expected": "denied",
     "scenario": r_retry_budget},
]


def task_finished(values: dict[str, Any]) -> bool:
    return (values.get("status") == "done" and values.get("word_total") == EXPECTED_WORDS
            and sorted(a["index"] for a in values.get("artifacts", [])) == list(range(len(ITEMS)))
            and values.get("constraints") == constraints("opaque"))


def judge_resolution(row: dict[str, Any], truth: str, obs: dict[str, Any]) -> str:
    """resolved = a true decision gives exactly one effect; misresolved = a false one gives 0 or 2."""
    if truth != row["truth"]:
        return f"VIOLATION: ground truth {truth}, expected {row['truth']}"
    values = obs["values"] or {}
    decision = row["decision"]
    correct = (decision == "confirmed_done") == (truth == "done")
    expected_calls = 1 if correct else (0 if decision == "confirmed_done" else 2)
    record = next((r for r in obs["reconciliations"] if r["effect_id"] == EFFECT_ID), {})
    retried = obs["opaque_calls_by_effect"].get(RETRY_ID, 0)
    ok = (task_finished(values) and not obs["gateway_commits"]
          and obs["opaque_invocations"] == expected_calls
          and record.get("status") == decision and record.get("operator") == OPERATOR
          and record.get("applied_by") == "worker-b.2"
          and (obs["effect_intent"] or {}).get("status") == decision
          and retried == (1 if decision == "confirmed_absent" else 0)
          and values["effect"]["effect_id"] == (RETRY_ID if decision == "confirmed_absent" else EFFECT_ID))
    if not ok:
        return "VIOLATION"
    return "resolved" if correct else "misresolved"


def recovery_note(row: dict[str, Any]) -> str:
    if row["decision"] == "confirmed_done":
        return "continue without re-execution" + ("" if row["truth"] == "done" else " -> effect LOST")
    return f"retry once as {RETRY_ID}" + ("" if row["truth"] == "absent" else " -> effect DUPLICATED")


def run_matrix(root: str, two_store: bool = False) -> list[dict[str, Any]]:
    run_class = TwoStoreRun if two_store else Run
    rows = []
    for spec in MATRIX:
        run = run_class(root, f"reconcile-{spec['id']}", "opaque")
        if spec["kind"] == "resolution":
            truth, obs = spec["scenario"](run)
            observed, recovery = judge_resolution(spec, truth, obs), recovery_note(spec)
        else:
            observed, recovery, obs = spec["scenario"](run)
            if not completed(obs):
                observed = f"{observed} (VIOLATION: task did not complete)"
        rows.append({"id": spec["id"], "extends": spec["extends"], "transition": "operator-reconcile",
                     "fault": spec["fault"], "tool": "opaque", "expected": spec["expected"],
                     "observed": observed, "match": observed == spec["expected"], "recovery": recovery,
                     "evidence": {**evidence(obs), "opaque_calls_by_effect": obs["opaque_calls_by_effect"],
                                  "reconciliations": obs["reconciliations"]},
                     "steps": run.steps})
    return rows


def markdown(rows: list[dict[str, Any]]) -> str:
    lines = ["| ID | Extends | Injected fault / operator decision | Expected | Observed | Recovery / handling | "
             "Opaque calls by effect ID | Original effect ledger | Final |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        e = r["evidence"]
        calls = ", ".join(f"{k}: {v}" for k, v in sorted(e["opaque_calls_by_effect"].items())) or "none"
        lines.append(f"| {r['id']} | {r['extends']} | {r['fault']} | {r['expected']} | "
                     f"{r['observed']}{'' if r['match'] else ' **MISMATCH**'} | {r['recovery']} | {calls} | "
                     f"{e['effect_ledger']} | {e['final_status']} @ {e['final_owner']} |")
    return "\n".join(lines)
