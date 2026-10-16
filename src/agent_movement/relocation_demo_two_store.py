"""Two-store relocation experiment: copy the checkpoint into Worker B's OWN store.

    python -m agent_movement.relocation_demo --two-store [--json results.json]

Worker A and Worker B each own a SQLite file (LangGraph checkpoints, effect ledger,
node journal). The coordinator file holds only owners/epochs, relocation records and
the simulated external systems. A writes a self-describing bundle to its outbox; the
harness "transport" copies it into B's inbox; B verifies it against the manifest the
coordinator recorded and imports it in one fenced transaction. As in the single-store
experiment every actor action runs in a freshly forked process and a crash is
``os._exit`` at the named point. Synthetic data only; no model calls, no network.
"""

from __future__ import annotations

import base64
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from typing import Any, Callable

from .core import EffectGateway, SQLiteStore, canonical
from .relocation import (BUNDLE_EXPORTED_STATE, BUNDLE_UNSUPPORTED_STATE, PINNED_RUNTIME, Coordinator,
                         Faults, Worker, bundle_name, build_bundle, bundles, init_authority,
                         init_worker_store, local_profile, observe, runtime_versions)
from .relocation_demo import (DENIED, EFFECT_ID, ITEMS, TASK, Run, constraints, headline_ok,
                              run_matrix, unchanged)

WORKERS = ("worker-a", "worker-b")


class TwoStoreRun(Run):
    """One scenario with a coordinator file, one store per worker, and bundle directories."""

    def __init__(self, root: str, name: str, tool: str = "gateway"):  # noqa: D107 - no Run.__init__
        base = Path(root) / name
        base.mkdir(parents=True)
        self.base = base
        self.path = str(base / "coordinator.sqlite")
        self.stores = {worker: str(base / f"{worker}.sqlite") for worker in WORKERS}
        self.outbox = {"worker-a": str(base / "outbox-worker-a"), "coordinator": str(base / "outbox-coordinator")}
        self.inbox = base / "inbox-worker-b"
        self.tool = tool
        self.steps: list[str] = []
        init_authority(self.path)
        for store in self.stores.values():
            init_worker_store(store)

    def observe(self) -> dict[str, Any]:
        return observe(self.path, TASK, EFFECT_ID, stores=self.stores)

    def worker(self, worker: str, incarnation: int = 1, crash: str | None = None) -> Worker:
        return Worker(self.path, worker, incarnation, faults=Faults(crash), store=self.stores[worker])

    def inbox_copy(self, movement: str = "move-1") -> Path:
        return self.inbox / bundle_name(movement)

    def store_rows(self, worker: str) -> int:
        """Harness ground truth: checkpoint rows for the task in one worker store."""
        with closing(sqlite3.connect(self.stores[worker])) as db:
            return db.execute("SELECT COUNT(*) FROM checkpoints WHERE thread_id=?", (TASK,)).fetchone()[0]

    # --- actor actions -------------------------------------------------
    def start_a(self, supersteps: int = 3) -> dict[str, Any]:
        tool = self.tool
        return self.act(f"A starts and runs {supersteps} supersteps", lambda: self.worker("worker-a").start(
            TASK, ITEMS, constraints(tool), max_supersteps=supersteps))

    def export(self, movement: str = "move-1", to: str = "worker-b.1", crash: str | None = None):
        outbox = self.outbox["worker-a"]
        return self.act(f"A exports bundle {movement}", lambda: self.worker("worker-a", crash=crash).attach(
            TASK, 1).export_bundle(movement, to, outbox))

    def copy(self, movement: str = "move-1", origin: str = "worker-a"):
        source = Path(self.outbox[origin]) / bundle_name(movement)
        target = self.inbox_copy(movement)
        return self.act(f"copy {movement} bundle {origin} -> worker-b inbox",
                        lambda: bundles.copy(source, target))

    def accept(self, worker: str = "worker-b", incarnation: int = 1, movement: str = "move-1",
               crash: str | None = None):
        bundle = self.inbox_copy(movement)
        return self.act(f"{worker}.{incarnation} imports {movement}", lambda: self.worker(
            worker, incarnation, crash).accept(movement, bundle))

    def run(self, worker: str = "worker-b", incarnation: int = 1, epoch: int = 2,
            supersteps: int | None = None, crash: str | None = None, check: bool = True):
        return self.act(f"{worker}.{incarnation}@{epoch} runs", lambda: self.worker(
            worker, incarnation, crash).attach(TASK, epoch).run(supersteps, check_ownership=check))

    def failover(self, movement: str, to: str, source: str = "worker-a"):
        path, store, outbox = self.path, self.stores[source], self.outbox["coordinator"]
        return self.act(f"coordinator failover {movement} -> {to} from {source} store", lambda: Coordinator(
            path).failover(movement, TASK, to, local_profile(), source_store=store, outbox=outbox))

    def relocate(self) -> None:
        """Happy-path bundle relocation A -> worker-b.1 (no faults)."""
        self.export()
        self.transfer()
        self.copy()
        self.accept()

    def recover_to_b2(self, movement: str = "move-2", epoch: int = 3, source: str = "worker-a") -> None:
        """Receiver crashed before acknowledging: new execution, new epoch, fresh bundle."""
        self.failover(movement, "worker-b.2", source)
        self.copy(movement, "coordinator")
        self.accept("worker-b", 2, movement)
        self.run("worker-b", 2, epoch)


# --- scenarios --------------------------------------------------------------

def _crashed(run: TwoStoreRun, result: dict[str, Any]) -> None:
    if not result["crashed"]:
        raise RuntimeError(f"fault did not fire: {run.steps}")


def b_export_before_request(run: TwoStoreRun):
    run.start_a()
    _crashed(run, run.export(crash="origin.before_export"))
    run.failover("move-1", "worker-b.1")
    run.copy("move-1", "coordinator")
    run.accept()
    run.run()
    return "failover: coordinator re-exports from A's store; B imports", run.observe()


def b_export_after_request(run: TwoStoreRun):
    run.start_a()
    _crashed(run, run.export(crash="origin.after_export"))
    run.transfer()
    run.copy()
    run.accept()
    run.run()
    return "coordinator continues recorded request; B imports A's bundle", run.observe()


def b_import_before_commit(run: TwoStoreRun):
    run.start_a()
    run.export()
    run.transfer()
    run.copy()
    _crashed(run, run.accept(crash="import.before_commit"))
    left = run.store_rows("worker-b")
    run.recover_to_b2()
    return (f"import rolled back (B store: {left} checkpoint rows); failover worker-b.2 (epoch 3) "
            "re-imports", run.observe())


def b_import_after_commit(run: TwoStoreRun):
    run.start_a()
    run.export()
    run.transfer()
    run.copy()
    _crashed(run, run.accept(crash="import.after_commit"))
    left = run.store_rows("worker-b")
    run.recover_to_b2()
    return (f"import durable, not acked (B store: {left} checkpoint row); worker-b.2 re-import "
            "is idempotent", run.observe())


def _inject(run: TwoStoreRun, label: str, action: Callable[[], Any],
            finish: Callable[[], None]) -> tuple[str, str, dict[str, Any], Any]:
    before = run.observe()
    result = run.act(label, action)
    after = run.observe()
    value = result.get("value")
    replayed = isinstance(value, dict) and value.get("replayed") is True
    if not unchanged(before, after):
        observed = "VIOLATION: state changed"
    elif not result["ok"] and result["error"] in DENIED:
        observed = "denied"
    elif result["ok"] and replayed:
        observed = "deduplicated"
    else:
        observed = f"UNEXPECTED: {result}"
    finish()
    return observed, f"{label} -> {result.get('error') or 'ok'}", run.observe(), result.get("report")


def b_frozen_origin(run: TwoStoreRun):
    run.start_a()
    run.export()

    def finish() -> None:
        run.transfer()
        run.copy()
        run.accept()
        run.run()
    return _inject(run, "A steps after its export request", lambda: run.worker("worker-a").attach(
        TASK, 1).run(1, check_ownership=False), finish)


def _tampered(note: str, tamper: Callable[[TwoStoreRun], None]):
    """Corrupt B's local copy after a legitimate transfer; B must refuse and import nothing."""
    def scenario(run: TwoStoreRun):
        run.start_a(2)
        stale = run.act("A writes an earlier, unrecorded bundle for move-1", lambda: build_bundle(
            run.stores["worker-a"], TASK, "move-1", "worker-a.1", 1, "worker-b.1", "cooperative")[1].decode())
        (run.base / "stale-move-1.bundle.json").write_text(stale["value"], encoding="utf-8")
        run.run("worker-a", 1, 1, supersteps=1)
        run.export()
        run.transfer()
        run.copy()
        tamper(run)

        def finish() -> None:
            run.copy()
            run.accept()
            run.run()
        observed, _recovery, obs, report = _inject(run, f"worker-b.1 imports {note}", lambda: run.worker(
            "worker-b").accept("move-1", run.inbox_copy()), finish)
        report = report or {}
        if report.get("decision") != "refuse_fail_closed":
            observed = f"UNEXPECTED: {report}"
        recovery = (f"refused ({report.get('reason')}); corrupt={report.get('corrupt_sections')}; "
                    f"unavailable={len(report.get('unavailable_state', []))} items; re-copy -> completes")
        return observed, recovery, obs, report
    return scenario


def truncate(run: TwoStoreRun) -> None:
    path = run.inbox_copy()
    data = path.read_bytes()
    path.write_bytes(data[:len(data) // 2])


def flip_channel_byte(run: TwoStoreRun) -> None:
    """Length-preserving one-byte change inside the `items` channel of the checkpoint blob."""
    path = run.inbox_copy()
    bundle = json.loads(path.read_bytes())
    row = bundle["payload"]["checkpoint"]
    blob = base64.b64decode(row["checkpoint_b64"])
    needle = ITEMS[0].encode("utf-8")
    if blob.count(needle) != 1:
        raise RuntimeError("tamper target not found exactly once in the checkpoint blob")
    row["checkpoint_b64"] = base64.b64encode(blob.replace(needle, needle[:-1] + b"X")).decode("ascii")
    path.write_bytes(canonical(bundle).encode("utf-8"))


def substitute_stale(run: TwoStoreRun) -> None:
    """Replace the copy with a valid, self-consistent bundle the coordinator never granted."""
    run.inbox_copy().write_bytes((run.base / "stale-move-1.bundle.json").read_bytes())


def b_duplicate_import(run: TwoStoreRun):
    run.start_a()
    run.relocate()
    run.run(supersteps=1)
    return _inject(run, "duplicate import of move-1 after B progressed", lambda: run.worker(
        "worker-b").accept("move-1", run.inbox_copy()), lambda: run.run())


def b_superseded_import(run: TwoStoreRun):
    run.start_a()
    run.export()
    run.transfer()
    run.copy()
    run.failover("move-2", "worker-b.2")
    run.copy("move-2", "coordinator")
    run.accept("worker-b", 2, "move-2")
    return _inject(run, "delayed import of move-1 by worker-b.1", lambda: run.worker(
        "worker-b").accept("move-1", run.inbox_copy()), lambda: run.run("worker-b", 2, 3))


def b_partitioned_origin(run: TwoStoreRun):
    run.start_a()
    run.relocate()
    return _inject(run, "partitioned A steps in its own store", lambda: run.worker("worker-a").attach(
        TASK, 1).run(1, check_ownership=False), lambda: run.run())


MATRIX: list[dict[str, Any]] = [
    {"id": "B1", "kind": "crash", "transition": "export", "fault": "crash after bundle written, before request",
     "expected": "allowed", "scenario": b_export_before_request},
    {"id": "B2", "kind": "crash", "transition": "export", "fault": "crash after request recorded",
     "expected": "allowed", "scenario": b_export_after_request},
    {"id": "B3", "kind": "inject", "transition": "export", "fault": "A checkpoints after its export request",
     "expected": "denied", "scenario": b_frozen_origin},
    {"id": "B4", "kind": "inject", "transition": "copy", "fault": "truncated bundle (half the bytes)",
     "expected": "denied", "scenario": _tampered("a truncated copy", truncate)},
    {"id": "B5", "kind": "inject", "transition": "copy", "fault": "one byte changed in a channel (digest mismatch)",
     "expected": "denied", "scenario": _tampered("a bit-flipped copy", flip_channel_byte)},
    {"id": "B6", "kind": "inject", "transition": "copy", "fault": "valid but ungranted (stale) bundle substituted",
     "expected": "denied", "scenario": _tampered("a substituted stale bundle", substitute_stale)},
    {"id": "B7", "kind": "crash", "transition": "import", "fault": "crash inside import txn (partial import)",
     "expected": "allowed", "scenario": b_import_before_commit},
    {"id": "B8", "kind": "crash", "transition": "import", "fault": "crash after import commit, before ack",
     "expected": "allowed", "scenario": b_import_after_commit},
    {"id": "B9", "kind": "inject", "transition": "import", "fault": "duplicate import after B progressed",
     "expected": "deduplicated", "scenario": b_duplicate_import},
    {"id": "B10", "kind": "inject", "transition": "import", "fault": "delayed import by superseded worker-b.1",
     "expected": "denied", "scenario": b_superseded_import},
    {"id": "B11", "kind": "inject", "transition": "checkpoint",
     "fault": "partitioned A keeps stepping in its own store", "expected": "denied", "scenario": b_partitioned_origin},
]

HEADLINE_TWO_STORE_KEYS = ("stores_distinct", "coordinator_tables", "receiver_rows_before_import",
                           "imported", "bundle_verified", "receiver_checkpoints_from_origin",
                           "origin_head_unchanged_after_transfer", "store_checkpoints")


def headline(root: str) -> dict[str, Any]:
    """A runs 3 of 6 items in its store, the head is copied to B's store, B finishes."""
    run = TwoStoreRun(root, "headline-two-store")
    a = run.start_a()
    exported = run.export()
    grant = run.transfer()
    run.copy()
    rows_before = run.store_rows("worker-b")
    accepted = run.accept()
    fenced_step = run.act("partitioned A tries one more superstep", lambda: run.worker("worker-a").attach(
        TASK, 1).run(1, check_ownership=False))
    fenced_commit = run.act("fenced A tries a gated commit", lambda: EffectGateway(
        SQLiteStore(run.path)).commit(TASK, "worker-a.1", 1, EFFECT_ID, "stale"))
    origin_head = observe(run.path, TASK, EFFECT_ID, stores={"worker-a": run.stores["worker-a"]})
    b = run.run()
    obs = run.observe()
    baseline = TwoStoreRun(root, "restart-baseline-two-store")
    restart = baseline.act("restart baseline: B runs task from scratch", lambda: baseline.worker(
        "worker-b").start(TASK, ITEMS, constraints()))
    manifest = exported["value"]["manifest"]
    values = obs["values"]
    by_execution: dict[str, list[int]] = {}
    for entry in values["step_log"]:
        if entry["node"] == "process_item":
            by_execution.setdefault(entry["execution_id"], []).append(entry["index"])
    b_first = next(c for c in obs["lineage"] if c["written_by"] == "worker-b.1")
    with closing(sqlite3.connect(run.path)) as db:
        tables = sorted(r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' "
                                                 "AND name NOT LIKE 'sqlite_%'"))
    with closing(sqlite3.connect(run.stores["worker-b"])) as db:
        from_origin = db.execute("SELECT COUNT(*) FROM checkpoints WHERE thread_id=? AND "
                                 "json_extract(metadata, '$.execution_id')='worker-a.1'", (TASK,)).fetchone()[0]
    return {
        "steps": run.steps,
        "manifest": {k: manifest[k] for k in ("profile", "mode", "transport", "logical_task_id",
                                              "from_execution", "from_epoch", "to_execution", "checkpoint",
                                              "runtime", "graph_id", "graph_version", "channels",
                                              "uncertain_effects", "bundle")},
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
        "word_total": values["word_total"], "expected_word_total": sum(len(i.split()) for i in ITEMS),
        "gateway_commits": obs["gateway_commits"], "final_owner": obs["owner"],
        "final_status": values["status"],
        # two-store evidence
        "stores_distinct": len({run.path, *run.stores.values()}) == 3,
        "coordinator_tables": tables,
        "receiver_rows_before_import": rows_before,
        "imported": accepted["value"]["imported"],
        "bundle_verified": accepted["value"]["bundle_sha256"] == exported["value"]["bundle_sha256"],
        "receiver_checkpoints_from_origin": from_origin,
        "origin_head_unchanged_after_transfer":
            origin_head["stores"]["worker-a"]["head_checkpoint_id"] == manifest["checkpoint"]["checkpoint_id"],
        "store_checkpoints": {w: s["checkpoints"] for w, s in obs["stores"].items()},
    }


def headline_two_store_ok(h: dict[str, Any]) -> bool:
    return (headline_ok(h) and h["stores_distinct"] and "checkpoints" not in h["coordinator_tables"]
            and "effect_intents" not in h["coordinator_tables"] and h["receiver_rows_before_import"] == 0
            and h["imported"] == {"replayed": False, "checkpoints": 1, "writes": 0, "effect_intents": 0}
            and h["bundle_verified"] and h["receiver_checkpoints_from_origin"] == 1
            and h["origin_head_unchanged_after_transfer"])


def experiment(root: str) -> dict[str, Any]:
    h = headline(root)
    rows = run_matrix(root, MATRIX, TwoStoreRun)
    return {"mode": "two-store", "runtime": runtime_versions(), "pinned": PINNED_RUNTIME,
            "python": sys.version.split()[0],
            "exported_state": BUNDLE_EXPORTED_STATE, "unsupported_state": BUNDLE_UNSUPPORTED_STATE,
            "headline": h, "headline_ok": headline_two_store_ok(h),
            "headline_two_store_keys": list(HEADLINE_TWO_STORE_KEYS), "matrix": rows,
            "all_rows_match": all(r["match"] for r in rows)}
