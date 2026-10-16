"""MobilityBench v0.1/v0.2 baselines that need an optional extra (deterministic, LLM-free).

* ``a2a_delegate`` (B2, extra ``a2a``): the B2-local shape, but every pure step
  crosses the official A2A v1 SDK. The issue #7 destination worker
  (``a2a_server.build_app``) is served by uvicorn on a 127.0.0.1 ephemeral port in
  a background thread, and the origin calls the public ``a2a_client.delegate``, so
  the steps travel as real A2A JSON-RPC over loopback HTTP (never off the host).
* ``checkpoint_relocate`` (B3, extra ``relocation``): the plan runs as a LangGraph
  graph whose state is checkpointed in the issue #9 ``FencedSqliteSaver``. At the
  movement point the issue #9 ``Coordinator`` moves the ownership epoch to the
  destination, which verifies the exported checkpoint and resumes from it with the
  same effect IDs. A pre-empted origin is relocated by failover from the durable head.
  Under the v0.2 mid-step crashes, a crashed origin is relocated by failover from its
  last durable checkpoint and a crashed destination resumes from its own; either way
  the interrupted step runs again under the same effect ID, which the gateway dedups.

``mobilitybench_v01`` reports a mode as ``unavailable`` when its extra is missing, so
these runners are only called when their imports can succeed. Each runner imports
its extra lazily, so one extra works without the other. Records stay sanitized:
counts and enums only, never checkpoint IDs, A2A task IDs, ports or timings.
"""
from __future__ import annotations

import asyncio
import socket
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, TypedDict

from .core import Conflict, ContractError, PolicyDenied, SQLiteStore
from .mobilitybench_v01 import (TRANSFERABLE, AgentState, Attempt, Outcome, Pure, SimulatedCrash,
                                delegate_tail, delegation_approvals, delegation_envelope,
                                deliver_with_receipts, stale_origin_retry)

# --------------------------------------------------------------------------- B2: A2A v1 delegate

A2A_REJECTIONS: dict[str, type[Exception]] = {"approval_denied": PolicyDenied,
                                              "idempotency_conflict": Conflict}


@contextmanager
def loopback_a2a_worker(att: Attempt, start_timeout: float = 10.0) -> Iterator[str]:
    """Serve the issue #7 destination worker for one attempt on 127.0.0.1; yield its base URL."""
    import uvicorn

    from .a2a_profile import KINDS
    from .a2a_server import build_app

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))  # loopback only, as in a2a_server.main
        sock.listen(64)
        base_url = f"http://127.0.0.1:{sock.getsockname()[1]}"
        app = build_app(db=att.workdir / "receiver.sqlite", base_url=base_url, receiver_id="agent-b",
                        approvals=delegation_approvals(att), kinds=list(KINDS))
        server = uvicorn.Server(uvicorn.Config(app, log_level="warning", access_log=False))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True,
                                  name="mobilitybench-a2a-worker")
        thread.start()
        deadline = time.monotonic() + start_timeout
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError("A2A destination worker did not start")
            time.sleep(0.005)
        try:
            yield base_url
        finally:
            server.should_exit = True
            thread.join(start_timeout)
    finally:
        sock.close()


def a2a_receipt(result: dict[str, Any]) -> dict[str, Any]:
    """Map an ``a2a_client.delegate`` result to its verified receipt or to the harness exceptions."""
    if "error" in result:  # A2A protocol error: refused before any task existed
        raise ContractError("A2A request rejected: " + result["error"]["type"])
    if result["final_state"] != "TASK_STATE_COMPLETED":
        raise A2A_REJECTIONS.get(result.get("reason"), ContractError)("A2A task ended " + result["final_state"])
    return result["receipt"]


@contextmanager
def _a2a_remote(att: Attempt) -> Iterator[Pure]:
    from .a2a_client import delegate
    from .a2a_profile import envelope_to_a2a

    with loopback_a2a_worker(att) as base_url, asyncio.Runner() as runner:
        def remote(step: int, kind: str, text: str) -> int | str:
            envelope = delegation_envelope(att, step, kind, text)
            # The A2A-bound projection is validated client-side before anything is sent.
            mapped = envelope_to_a2a(envelope)
            # Each copy (and each retry after a lost receipt) is a new A2A task; the
            # receiver answers a repeat with the replayed receipt.
            return deliver_with_receipts(
                att, {"metadata": mapped["metadata"], "data": mapped["data"]},
                lambda: a2a_receipt(runner.run(delegate(base_url, envelope, binding="JSONRPC", streaming=False))),
                verify_against=envelope)

        yield remote


def run_a2a_delegate(att: Attempt) -> Outcome:
    """B2: origin keeps ownership and delegates the pure remainder over A2A v1 (official SDK)."""
    return delegate_tail(att, _a2a_remote)


# --------------------------------------------------------------------------- B3: checkpoint relocation

GRAPH_ID = "mobilitybench-v0.1-plan"
GRAPH_VERSION = "1"
CHANNELS = ("cursor", "files", "inventory", "original_files", "out", "rules", "sections")


class PlanState(TypedDict):
    """Everything an executor knows, as JSON-plain LangGraph channels (no identity, no epoch)."""

    cursor: int
    files: dict[str, str]
    inventory: dict[str, int]
    original_files: dict[str, str]
    out: list[str]
    rules: list[dict[str, Any]]
    sections: dict[str, str]


def plan_channels(state: AgentState, cursor: int) -> dict[str, Any]:
    return {"cursor": cursor, "files": dict(state.files), "inventory": dict(state.inventory),
            "original_files": dict(state.original_files), "out": list(state.out),
            "rules": [dict(r) for r in state.rules], "sections": dict(state.sections)}


def restore_state(task: dict[str, Any], name: str, epoch: int, values: dict[str, Any]) -> AgentState:
    """Rebuild an executor's state from checkpoint channels; identity and epoch come from the executor."""
    state = AgentState(name, task, epoch)
    state.rules = [dict(r) for r in values["rules"]]
    state.sections = dict(values["sections"])
    state.original_files = dict(values["original_files"])
    state.files = dict(values["files"])
    state.inventory = dict(values["inventory"])
    state.out = list(values["out"])
    return state


def receiver_profile() -> dict[str, Any]:
    """What the destination can resume: the pinned issue #9 runtime plus this benchmark graph."""
    from . import relocation
    return {"profile": relocation.PROFILE, "runtime": relocation.runtime_versions(), "graph_id": GRAPH_ID,
            "graph_version": GRAPH_VERSION, "checkpoint_format": relocation.CHECKPOINT_FORMAT,
            "channels": list(CHANNELS)}


class PlanRuntime:
    """One execution of the plan graph, checkpointed by the issue #9 fenced saver.

    ``execution_id=None`` opens a read-only view (the saver refuses every write).
    """

    def __init__(self, att: Attempt, path: Path, execution_id: str | None, epoch: int | None):
        from langgraph.graph import END, START, StateGraph

        from .relocation import FencedSqliteSaver

        self.att, self.execution_id, self.epoch = att, execution_id, epoch
        self.config = {"configurable": {"thread_id": att.gw_task, "checkpoint_ns": ""}}
        self.conn = sqlite3.connect(str(path), check_same_thread=False, timeout=10)
        self.conn.execute("PRAGMA busy_timeout = 10000")
        self.saver = FencedSqliteSaver(self.conn, att.gw_task, execution_id, epoch)
        plan_length = len(att.plan)

        def step(values: PlanState) -> dict[str, Any]:
            if self.execution_id is None or self.epoch is None:
                raise PolicyDenied("read-only view cannot execute plan steps")
            index = values["cursor"]
            state = restore_state(att.task, self.execution_id, self.epoch, values)
            att.hear(state, index)  # live session events reach whoever executes this step
            att.run_step(state, index)
            return plan_channels(state, index + 1)

        def route(values: PlanState) -> str:
            return "step" if values["cursor"] < plan_length else END

        builder = StateGraph(PlanState)
        builder.add_node("step", step)
        builder.add_edge(START, "step")
        builder.add_conditional_edges("step", route, ["step", END])
        self.graph = builder.compile(checkpointer=self.saver)

    def close(self) -> None:
        self.conn.close()

    def advance(self, task_input: dict[str, Any] | None = None, limit: int | None = None) -> None:
        """One plan step per superstep; every boundary is a durable, fenced checkpoint."""
        steps = 0
        while limit is None or steps < limit:
            if task_input is None and not self.graph.get_state(self.config).tasks:
                return
            self.graph.invoke(task_input, self.config, interrupt_after="*", durability="sync")
            task_input = None
            steps += 1

    def head(self) -> Any:
        head = self.saver.get_tuple(self.config)
        if head is None:
            raise Conflict("no durable checkpoint for task")
        return head

    def values(self) -> dict[str, Any]:
        return {name: self.head().checkpoint["channel_values"][name] for name in CHANNELS}

    def manifest(self, movement_id: str, from_execution: str, from_epoch: int, to_execution: str,
                 mode: str) -> dict[str, Any]:
        """Issue #9 relocation manifest for the head checkpoint (same fields as relocation.build_manifest)."""
        from . import relocation

        head = self.head()
        snapshot = self.graph.get_state(self.config)
        pending = sorted({f"{task}:{channel}" for task, channel, _value in head.pending_writes})
        if pending and mode == "cooperative":
            raise Conflict("unsafe boundary: checkpoint has pending writes")
        scheduled = [t.name for t in snapshot.tasks]
        if snapshot.interrupts or scheduled != ["step"]:
            raise Conflict("unsafe boundary: interrupt, unknown node or finished task")
        checkpoint, meta = head.checkpoint, head.metadata or {}
        return {
            "profile": relocation.PROFILE, "movement_id": movement_id, "mode": mode,
            "logical_task_id": self.att.gw_task, "from_execution": from_execution, "from_epoch": from_epoch,
            "to_execution": to_execution,
            "checkpoint": {"thread_id": self.att.gw_task, "checkpoint_ns": "", "checkpoint_id": checkpoint["id"],
                           "parent_checkpoint_id": (head.parent_config or {}).get("configurable", {})
                           .get("checkpoint_id"), "format": checkpoint["v"], "step": meta.get("step"),
                           "next": scheduled, "digest": relocation.checkpoint_digest(checkpoint),
                           "exported_channels": list(CHANNELS), "pending_writes": pending},
            "runtime": relocation.runtime_versions(), "graph_id": GRAPH_ID, "graph_version": GRAPH_VERSION,
            "channels": list(CHANNELS), "uncertain_effects": [],
            "exported_state": sorted(relocation.EXPORTED_STATE),
            "unsupported_state": sorted(relocation.UNSUPPORTED_STATE),
        }


@contextmanager
def plan_runtime(att: Attempt, path: Path, execution_id: str | None = None,
                 epoch: int | None = None) -> Iterator[PlanRuntime]:
    runtime = PlanRuntime(att, path, execution_id, epoch)
    try:
        yield runtime
    finally:
        runtime.close()


def accept_grant(att: Attempt, path: Path, grant: dict[str, Any], manifest: dict[str, Any]) -> bool:
    """Destination side of issue #9 ``Worker.accept`` for this graph; returns the ack's replay flag."""
    from . import relocation

    coordinator = relocation.Coordinator(path)
    row = coordinator.get(grant["movement_id"])
    if row is None or row["to_execution"] != "agent-b":
        raise PolicyDenied("grant is unknown or addressed to another execution")
    if relocation.owner_of(SQLiteStore(path), att.gw_task) != ("agent-b", row["to_epoch"]):
        raise PolicyDenied("grant superseded by a newer epoch")
    if row["status"] == "transferred":  # first delivery: verify before resuming
        with plan_runtime(att, path) as view:
            exported = view.saver.get_tuple({"configurable": {
                "thread_id": att.gw_task, "checkpoint_ns": "",
                "checkpoint_id": manifest["checkpoint"]["checkpoint_id"]}})
            if exported is None or relocation.checkpoint_digest(exported.checkpoint) != manifest["checkpoint"]["digest"]:
                raise relocation.Incompatible("exported checkpoint is missing or altered",
                                              {"unavailable_state": list(CHANNELS)})
            if view.head().checkpoint["id"] != exported.checkpoint["id"]:
                raise Conflict("head moved after transfer")
    return coordinator.acknowledge(grant["movement_id"], "agent-b", row["to_epoch"])["replayed"]


def run_checkpoint_relocate(att: Attempt) -> Outcome:
    """B3: the origin's checkpoint and ownership move; the destination resumes at the movement point."""
    from . import relocation

    path = att.workdir / "effects.sqlite"  # one store: owners, effects, relocations, checkpoints
    relocation.init_store(path)
    epoch = att.gateway.claim(att.gw_task, "agent-a")
    initial = plan_channels(AgentState("agent-a", att.task, epoch), 0)
    crashed = False
    with plan_runtime(att, path, "agent-a", epoch) as origin_runtime:
        try:
            origin_runtime.advance(task_input=initial, limit=att.m)
        except SimulatedCrash:  # v0.2: the origin died inside a step; its head is the last boundary
            crashed = True
        origin = restore_state(att.task, "agent-a", epoch, origin_runtime.values())
    if att.task["classification"] not in TRANSFERABLE:
        return origin, "refused", "classification_not_transferable"
    mode = "cooperative"
    if att.fault == "origin_preempted" or crashed:
        if att.fault == "origin_preempted":
            att.fault_applied = True
        mode = "failover"  # the origin is gone: the coordinator fails over from the durable head
    movement_id = f"{att.gw_task}.relocate"
    with plan_runtime(att, path) as view:  # read-only export of the head checkpoint
        manifest = view.manifest(movement_id, "agent-a", epoch, "agent-b", mode)
        exported = view.values()
    coordinator = relocation.Coordinator(path)

    def request() -> None:
        if coordinator.request(manifest)["replayed"]:  # idempotent by movement ID
            att.metrics["duplicate_deliveries_suppressed"] += 1

    # Message 1: manifest + checkpoint state (in a cross-host deployment the state bytes travel too).
    message = {"manifest": manifest, "state": exported}
    copies = att.send(message)
    late = att.take_late()
    for _ in range(copies - late):
        request()
        if att.reply_lost():  # the origin never learns the request was recorded: it re-sends
            att.resend(message)
            request()
    grant = coordinator.transfer(movement_id, receiver_profile())
    if grant["status"] != "transferred":
        return origin, "refused", "incompatible_checkpoint"
    if att.fault == "stale_origin_returns":
        stale_origin_retry(att, epoch)
    # Message 2: the coordinator's grant to the destination; a duplicate is acknowledged as a replay.
    try:
        grant_message = {k: grant[k] for k in ("movement_id", "logical_task_id", "to_execution", "to_epoch",
                                               "checkpoint_id")}
        for _ in range(att.send(grant_message)):
            if accept_grant(att, path, grant, manifest):
                att.metrics["duplicate_deliveries_suppressed"] += 1
    except relocation.Incompatible:
        return origin, "refused", "incompatible_checkpoint"
    for _ in range(late):  # the held original arrives after the destination accepted the grant
        request()
    for run in (1, 2):
        with plan_runtime(att, path, "agent-b", grant["to_epoch"]) as destination:
            try:
                destination.advance()
            except SimulatedCrash:
                if run == 2:
                    raise RuntimeError("a scheduled crash fired twice") from None
                continue  # v0.2: the destination process restarts from its own durable head
            values = destination.values()
            break
    if values["cursor"] != len(att.plan):
        raise RuntimeError("destination did not finish the plan")
    return restore_state(att.task, "agent-b", grant["to_epoch"], values), "completed", None


OPTIONAL_RUNNERS: dict[str, Callable[[Attempt], Outcome]] = {
    "a2a_delegate": run_a2a_delegate,
    "checkpoint_relocate": run_checkpoint_relocate,
}
