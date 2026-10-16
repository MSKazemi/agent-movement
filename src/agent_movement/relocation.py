"""Same-runtime checkpoint relocation on ONE pinned durable runtime (LangGraph + SQLite).

Requires the optional extra: ``python -m pip install -e '.[relocation]'``.

Experimental and synthetic only. The graph is deterministic and LLM-free. Two
store topologies are supported:

* **single store** (default): one local SQLite file is the durable store shared by
  the coordinator and the workers; the checkpoint is exported *by reference*.
* **two stores** (``Worker(..., store=...)``): each worker keeps its checkpoints and
  effect ledger in its OWN SQLite file. The coordinator file (the *authority*) keeps
  only owners/epochs, relocation records and the simulated external systems. The
  head checkpoint is *copied* as a digest-verified bundle
  (:mod:`agent_movement.relocation_bundle`).

Exclusive ownership of a *logical task* is the core ``owners`` epoch row used by
:class:`agent_movement.core.EffectGateway`, always in the authority file;
checkpoint writes, effect intents and gated effects all re-check that epoch inside
their own SQLite transaction (in two-store mode the authority file is ATTACHed, so
``BEGIN IMMEDIATE`` holds both files' write locks while the check and the write run).

No exactly-once claim is made for arbitrary tools. Node execution is
at-least-once; an effect whose outcome cannot be queried is reported as
``unknown`` and parked for reconciliation instead of being retried blindly.
"""

from __future__ import annotations

import hashlib
import json
import operator
import os
import sqlite3
import threading
from collections import Counter
from contextlib import closing, contextmanager
from importlib import metadata
from pathlib import Path
from typing import Annotated, Any, Iterator, TypedDict

try:
    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.graph import END, START, StateGraph
except ImportError as exc:  # pragma: no cover - only without the optional extra
    raise ImportError("agent_movement.relocation needs the optional extra: "
                      "python -m pip install -e '.[relocation]'") from exc

from . import relocation_bundle as bundles
from .core import Conflict, ContractError, EffectGateway, PolicyDenied, SQLiteStore, _id, canonical, digest

PROFILE = "am-checkpoint-relocation/0.1.0-draft"
GRAPH_ID = "synthetic-batch-report"
GRAPH_VERSION = "1"
# checkpoint["v"] written by the pinned runtime (langgraph/pregel/_checkpoint.py LATEST_VERSION).
CHECKPOINT_FORMAT = 4
# Exact pins: FencedSqliteSaver relies on SqliteSaver.cursor() being the single write path.
PINNED_RUNTIME = {"langgraph": "1.2.15", "langgraph-checkpoint": "4.3.0",
                  "langgraph-checkpoint-sqlite": "3.1.2"}
STATE_CHANNELS = ("artifacts", "constraints", "cursor", "effect", "items", "status",
                  "step_log", "word_total")
NODES = ("process_item", "effect_intent", "effect_commit", "finalize")
EFFECT_TOOLS = ("gateway", "opaque")
CRASH_EXIT = 86
CRASH_POINTS = (
    "origin.before_export", "origin.after_export",
    "coordinator.before_transfer", "coordinator.after_transfer",
    "receiver.before_accept", "receiver.after_accept",
    "import.before_commit", "import.after_commit",
    "checkpoint.before_commit", "checkpoint.after_commit",
    "effect_intent.before", "effect_intent.after",
    "effect_commit.before", "effect_commit.after",
    "ack.after",
)
EXPORTED_STATE = {
    "thread_id": "the logical task ID (task identity; unchanged by relocation)",
    "checkpoint_id/parent_checkpoint_id": "head checkpoint of the root namespace and its parent",
    "channel_values": "all declared state channels: " + ", ".join(STATE_CHANNELS),
    "channel_versions/versions_seen": "LangGraph scheduling bookkeeping needed to compute the next node",
    "next": "node(s) the receiver will run first",
    "metadata": "step, source, and the execution_id/epoch that wrote the checkpoint",
    "effect_ledger": "intent rows for the task (by reference in the same store)",
}
UNSUPPORTED_STATE = {
    "in_flight_node_execution": "Python stack, locals and partial node output are lost; the node "
                                "re-runs from the last durable checkpoint (at-least-once).",
    "pending_writes_or_interrupts": "checkpoints with pending writes, interrupts or Send packets are "
                                    "refused for export",
    "subgraph_namespaces": "only checkpoint_ns='' is exported; subgraph checkpoints are refused",
    "non_json_channel_values": "channel values must be JSON-plain; other serde types are refused",
    "langgraph_store_memory": "LangGraph Store (cross-thread memory) is not used and not exported",
    "process_local_resources": "caches, counters, connections, sockets, file handles and thread pools",
    "credentials_and_grants": "never exported; the receiver gets a NEW ownership epoch",
    "external_tool_state": "never in the checkpoint; only the simulated gateway can be queried",
    "model_or_conversation_state": "none exists (LLM-free graph); model continuation is untested",
    "other_runtimes_or_graph_versions": "refused fail-closed; no cross-framework translation",
    "cross_host_byte_transfer": "not implemented; origin and receiver share one local SQLite file",
}
# Two-store mode: the head checkpoint is COPIED into the receiver's own store.
BUNDLE_EXPORTED_STATE = {
    **{k: v for k, v in EXPORTED_STATE.items() if k != "effect_ledger"},
    "pending_writes": "durable writes of the head checkpoint (failover only; cooperative export has none)",
    "effect_ledger": "the task's effect-intent rows, copied verbatim (pending and settled)",
}
BUNDLE_UNSUPPORTED_STATE = {
    **{k: v for k, v in UNSUPPORTED_STATE.items() if k != "cross_host_byte_transfer"},
    "checkpoint_history": "only the head checkpoint is copied; its ancestors stay in the origin store",
    "cross_host_byte_transfer": "the bundle is copied between local directories; no network transport",
    "shared_authority": "owners/epochs, relocation records and the simulated external systems stay "
                        "in ONE coordinator file that every worker reaches",
}

# Coordinator / authority file: ownership, relocation records, and the simulated
# outside world (opaque tool ground truth; the core EffectGateway's `effects`).
AUTHORITY_SCHEMA = """
CREATE TABLE IF NOT EXISTS relocations (
    movement_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    from_execution TEXT NOT NULL,
    from_epoch INTEGER NOT NULL,
    to_execution TEXT NOT NULL,
    to_epoch INTEGER,
    checkpoint_id TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    manifest_digest TEXT NOT NULL,
    status TEXT NOT NULL,
    report_json TEXT,
    transport TEXT NOT NULL DEFAULT 'shared'
);
CREATE TABLE IF NOT EXISTS opaque_effects (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    effect_id TEXT NOT NULL,
    payload_digest TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    epoch INTEGER NOT NULL
);
"""
# Worker state: what a worker's OWN store holds in two-store mode (plus LangGraph's
# checkpoints/writes tables). In single-store mode both schemas share one file.
STATE_SCHEMA = """
CREATE TABLE IF NOT EXISTS effect_intents (
    task_id TEXT NOT NULL,
    effect_id TEXT NOT NULL,
    payload_digest TEXT NOT NULL,
    tool TEXT NOT NULL,
    status TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    epoch INTEGER NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (task_id, effect_id)
);
CREATE TABLE IF NOT EXISTS node_runs (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    epoch INTEGER NOT NULL,
    node TEXT NOT NULL,
    item_index INTEGER
);
CREATE TABLE IF NOT EXISTS bundle_imports (
    movement_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    checkpoint_id TEXT NOT NULL,
    manifest_digest TEXT NOT NULL,
    bundle_sha256 TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    epoch INTEGER NOT NULL
);
"""
SCHEMA = AUTHORITY_SCHEMA + STATE_SCHEMA


class SimulatedCrash(BaseException):
    """Soft crash for in-process use; the experiment uses hard process exits instead."""


class Incompatible(Conflict):
    """Checkpoint cannot be resumed here; carries a lost/unavailable-state report."""

    def __init__(self, message: str, report: dict[str, Any]):
        super().__init__(message)
        self.report = report


class Faults:
    """Crash injection at a named transition. ``hard`` exits the process with no cleanup."""

    def __init__(self, crash_at: str | None = None, nth: int = 1, hard: bool = True):
        if crash_at is not None and crash_at not in CRASH_POINTS:
            raise ContractError("unknown crash point")
        self.crash_at, self.nth, self.hard, self.seen = crash_at, nth, hard, 0

    def hit(self, point: str) -> None:
        if point != self.crash_at:
            return
        self.seen += 1
        if self.seen == self.nth:
            if self.hard:
                os._exit(CRASH_EXIT)  # like SIGKILL: no finally blocks, no SQLite commit
            raise SimulatedCrash(point)


def runtime_versions() -> dict[str, str]:
    return {name: metadata.version(name) for name in PINNED_RUNTIME}


def local_profile() -> dict[str, Any]:
    """What this worker can resume. Compared field by field against a manifest."""
    return {"profile": PROFILE, "runtime": runtime_versions(), "graph_id": GRAPH_ID,
            "graph_version": GRAPH_VERSION, "checkpoint_format": CHECKPOINT_FORMAT,
            "channels": list(STATE_CHANNELS)}


def init_store(path: str | Path) -> SQLiteStore:
    """Create core (owners/effects), relocation and LangGraph checkpoint tables in one file."""
    store = SQLiteStore(path)
    with store._connection() as db:
        db.executescript(SCHEMA)
    with closing(sqlite3.connect(str(path))) as conn:
        SqliteSaver(conn).setup()
    return store


# --- two-store topology ---------------------------------------------------------

AUTHORITY = "authority"  # schema name under which a worker store ATTACHes the coordinator file


def init_authority(path: str | Path) -> SQLiteStore:
    """Two-store mode: the coordinator file. It holds NO checkpoints and NO effect ledger."""
    store = SQLiteStore(path)
    with store._connection() as db:
        db.executescript(AUTHORITY_SCHEMA)
    return store


def init_worker_store(path: str | Path) -> str:
    """Two-store mode: a worker's own file (LangGraph checkpoints, effect ledger, journal)."""
    with closing(sqlite3.connect(str(path), timeout=10, isolation_level=None)) as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(STATE_SCHEMA)
    with closing(sqlite3.connect(str(path))) as conn:
        SqliteSaver(conn).setup()
    return str(path)


def _attach(conn: sqlite3.Connection, authority: str | None) -> str:
    """ATTACH the coordinator file when the state lives elsewhere; return the owners' schema."""
    if authority is None:
        return "main"
    conn.execute(f"ATTACH DATABASE ? AS {AUTHORITY}", (authority,))
    return AUTHORITY


@contextmanager
def _state_connection(state: str, authority: str | None) -> Iterator[tuple[sqlite3.Connection, str]]:
    """Connection to a state store; with ``authority`` the coordinator file is attached.

    ``BEGIN IMMEDIATE`` on such a connection takes the write lock of EVERY attached
    file, so a fenced write here and the coordinator's epoch transfer serialize.
    """
    db = sqlite3.connect(state, timeout=10, isolation_level=None)
    try:
        db.execute("PRAGMA busy_timeout = 10000")
        schema = _attach(db, authority)
        yield db, schema
        if db.in_transaction:
            db.commit()
    except BaseException:
        if db.in_transaction:
            db.rollback()
        raise
    finally:
        db.close()


def _fence(db: Any, task_id: str, execution_id: str, epoch: int, schema: str = "main", *,
           frozen_ok: bool = False) -> None:
    """Deny unless (execution_id, epoch) owns the task in the authority ``schema``.

    Two-store mode adds an export freeze: once an owner has recorded a bundle export
    request, its writes are denied until the coordinator transfers or refuses it, so the
    copied head checkpoint cannot silently fall behind the origin's store. Coordinator
    failover (``frozen_ok``) may still record a request for a frozen owner.
    """
    if schema not in ("main", AUTHORITY):
        raise ContractError("unknown authority schema")
    owner = db.execute(f"SELECT agent_id, epoch FROM {schema}.owners WHERE task_id=?", (task_id,)).fetchone()
    if owner is None or tuple(owner) != (execution_id, epoch):
        raise PolicyDenied(f"stale or unauthorized execution {execution_id}@{epoch}")
    if not frozen_ok:
        frozen = db.execute(f"SELECT movement_id FROM {schema}.relocations WHERE task_id=? AND "
                            "from_execution=? AND from_epoch=? AND status='requested' AND "
                            "transport='bundle' LIMIT 1", (task_id, execution_id, epoch)).fetchone()
        if frozen is not None:
            raise PolicyDenied(f"execution {execution_id}@{epoch} is frozen by export {frozen[0]}")


def owner_of(store: SQLiteStore, task_id: str) -> tuple[str, int] | None:
    with store._connection() as db:
        row = db.execute("SELECT agent_id, epoch FROM owners WHERE task_id=?", (task_id,)).fetchone()
    return None if row is None else (row[0], row[1])


class FencedSqliteSaver(SqliteSaver):
    """SqliteSaver whose writes commit only while (execution_id, epoch) owns the task.

    The ownership check runs in the SAME ``BEGIN IMMEDIATE`` transaction as the
    checkpoint/writes insert, so a coordinator epoch transfer and a stale
    checkpoint write are serialized by SQLite. With ``execution_id=None`` the
    saver is a read-only view. Relies on ``SqliteSaver.cursor()`` being the only
    write path in the pinned langgraph-checkpoint-sqlite release.
    """

    def __init__(self, conn: sqlite3.Connection, task_id: str, execution_id: str | None = None,
                 epoch: int | None = None, faults: Faults | None = None, authority_schema: str = "main"):
        super().__init__(conn)
        self.task_id, self.execution_id, self.epoch = task_id, execution_id, epoch
        self.authority_schema = authority_schema
        self.faults = faults or Faults()
        # LangGraph calls put/put_writes from background threads; the flag must be
        # per-thread so a checkpoint fault never fires on a concurrent put_writes.
        self._local = threading.local()

    @contextmanager
    def cursor(self, transaction: bool = True) -> Iterator[sqlite3.Cursor]:
        with self.lock:
            self.setup()
            cur = self.conn.cursor()
            try:
                if transaction:
                    if self.execution_id is None or self.epoch is None:
                        raise PolicyDenied("read-only checkpoint view")
                    cur.execute("BEGIN IMMEDIATE")
                    _fence(cur, self.task_id, self.execution_id, self.epoch, self.authority_schema)
                yield cur
                if transaction:
                    putting = getattr(self._local, "putting", False)
                    if putting:
                        self.faults.hit("checkpoint.before_commit")
                    self.conn.commit()
                    if putting:
                        self.faults.hit("checkpoint.after_commit")
            except BaseException:
                if transaction and self.conn.in_transaction:
                    self.conn.rollback()
                raise
            finally:
                cur.close()

    def _own_thread(self, config: dict[str, Any]) -> None:
        conf = config["configurable"]
        if str(conf["thread_id"]) != self.task_id or conf.get("checkpoint_ns", "") != "":
            raise ContractError("only the bound task's root namespace may be written")

    def put(self, config, checkpoint, metadata, new_versions):  # type: ignore[override]
        self._own_thread(config)
        self._local.putting = True
        try:
            return super().put(config, checkpoint, metadata, new_versions)
        finally:
            self._local.putting = False

    def put_writes(self, config, writes, task_id, task_path=""):  # type: ignore[override]
        self._own_thread(config)
        return super().put_writes(config, writes, task_id, task_path)


class EffectLedger:
    """Write-ahead effect intents with an explicit ``unknown`` outcome (synthetic).

    ``store`` is the file holding the ledger (a :class:`SQLiteStore` or a path). In
    two-store mode pass the coordinator file as ``authority``: the ledger stays in the
    worker's store and every write is fenced against the attached owners table.
    """

    def __init__(self, store: SQLiteStore | str | Path, authority: str | Path | None = None):
        self.store = store
        self.path = store.path if isinstance(store, SQLiteStore) else str(store)
        self.authority = None if authority is None else str(authority)

    def _connection(self):
        return _state_connection(self.path, self.authority)

    def get(self, task_id: str, effect_id: str) -> dict[str, Any] | None:
        with self._connection() as (db, _schema):
            row = db.execute("SELECT payload_digest,tool,status,execution_id,epoch,attempts "
                             "FROM effect_intents WHERE task_id=? AND effect_id=?",
                             (task_id, effect_id)).fetchone()
        keys = ("payload_digest", "tool", "status", "execution_id", "epoch", "attempts")
        return None if row is None else dict(zip(keys, row))

    def uncertain(self, task_id: str) -> list[str]:
        with self._connection() as (db, _schema):
            rows = db.execute("SELECT effect_id FROM effect_intents WHERE task_id=? AND "
                              "status IN ('attempt_started','unknown') ORDER BY effect_id",
                              (task_id,)).fetchall()
        return [r[0] for r in rows]

    def record_intent(self, task_id: str, effect_id: str, payload_digest: str, tool: str,
                      execution_id: str, epoch: int) -> str:
        if tool not in EFFECT_TOOLS:
            raise ContractError("unsupported effect tool")
        with self._connection() as (db, schema):
            db.execute("BEGIN IMMEDIATE")
            _fence(db, task_id, execution_id, epoch, schema)
            row = db.execute("SELECT payload_digest,status FROM effect_intents WHERE task_id=? "
                             "AND effect_id=?", (task_id, effect_id)).fetchone()
            if row is not None:
                if row[0] != payload_digest:
                    raise Conflict("effect ID reused with a different payload")
                db.commit()
                return row[1]
            db.execute("INSERT INTO effect_intents(task_id,effect_id,payload_digest,tool,status,"
                       "execution_id,epoch) VALUES(?,?,?,?,'intent',?,?)",
                       (task_id, effect_id, payload_digest, tool, execution_id, epoch))
            db.commit()
            return "intent"

    def mark(self, task_id: str, effect_id: str, status: str, execution_id: str, epoch: int) -> None:
        if status not in ("attempt_started", "committed", "reconciled_committed", "unknown"):
            raise ContractError("invalid effect status")
        with self._connection() as (db, schema):
            db.execute("BEGIN IMMEDIATE")
            _fence(db, task_id, execution_id, epoch, schema)
            bump = 1 if status == "attempt_started" else 0
            updated = db.execute("UPDATE effect_intents SET status=?, execution_id=?, epoch=?, "
                                 "attempts=attempts+? WHERE task_id=? AND effect_id=?",
                                 (status, execution_id, epoch, bump, task_id, effect_id))
            if updated.rowcount != 1:
                raise Conflict("no recorded intent for effect")
            db.commit()


class OpaqueTool:
    """Simulated external tool with NO idempotency key and NO status lookup.

    Ownership is still checked at the boundary (it is gated), but a caller that
    crashes after invoking it cannot learn whether the effect happened. Only the
    experiment harness reads ``opaque_effects`` as ground truth.
    """

    def __init__(self, store: SQLiteStore):
        self.store = store

    def invoke(self, task_id: str, effect_id: str, execution_id: str, epoch: int, payload: str) -> None:
        with self.store._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            _fence(db, task_id, execution_id, epoch)
            db.execute("INSERT INTO opaque_effects(task_id,effect_id,payload_digest,execution_id,epoch) "
                       "VALUES(?,?,?,?,?)", (task_id, effect_id,
                                             hashlib.sha256(payload.encode("utf-8")).hexdigest(),
                                             execution_id, epoch))
            db.commit()


class TaskState(TypedDict):
    items: list[str]
    constraints: dict[str, Any]
    cursor: int
    word_total: int
    artifacts: Annotated[list[dict[str, Any]], operator.add]
    step_log: Annotated[list[dict[str, Any]], operator.add]
    effect: dict[str, Any]
    status: str


def initial_state(items: list[str], constraints: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(items, list) or not 1 <= len(items) <= 32 or not all(
            isinstance(x, str) and len(x.encode("utf-8")) <= 512 for x in items):
        raise ContractError("items must be 1..32 short synthetic strings")
    expected = {"classification", "effect_tool", "effect_id", "max_gated_effects"}
    if not isinstance(constraints, dict) or set(constraints) != expected:
        raise ContractError("invalid constraints fields")
    if constraints["classification"] != "synthetic" or constraints["effect_tool"] not in EFFECT_TOOLS \
            or constraints["max_gated_effects"] != 1:
        raise ContractError("unsupported constraints")
    _id(constraints["effect_id"], "effect_id")
    return {"items": items, "constraints": constraints, "cursor": 0, "word_total": 0,
            "artifacts": [], "step_log": [],
            "effect": {"effect_id": constraints["effect_id"], "status": "planned"},
            "status": "running"}


def effect_payload(task_id: str, state: dict[str, Any]) -> str:
    return canonical({"task_id": task_id, "word_total": state["word_total"],
                      "artifacts_digest": digest(state["artifacts"])})


def build_graph(worker: Worker | None, saver: SqliteSaver):
    """Deterministic, LLM-free graph. ``worker=None`` builds a read-only inspection graph."""

    def log(node: str, index: int | None = None) -> list[dict[str, Any]]:
        assert worker is not None, "read-only graph cannot execute nodes"
        worker.journal(node, index)
        return [{"node": node, "index": index, "execution_id": worker.execution_id,
                 "epoch": worker.epoch}]

    def process_item(state: TaskState) -> dict[str, Any]:
        index = state["cursor"]
        text = state["items"][index]
        artifact = {"index": index, "words": len(text.split()),
                    "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
        return {"cursor": index + 1, "word_total": state["word_total"] + artifact["words"],
                "artifacts": [artifact], "step_log": log("process_item", index)}

    def effect_intent(state: TaskState) -> dict[str, Any]:
        assert worker is not None
        steps = log("effect_intent")
        effect_id, tool = state["effect"]["effect_id"], state["constraints"]["effect_tool"]
        payload_digest = digest(effect_payload(worker.task_id, state))
        worker.faults.hit("effect_intent.before")
        worker.ledger.record_intent(worker.task_id, effect_id, payload_digest, tool,
                                    worker.execution_id, worker.epoch)
        worker.faults.hit("effect_intent.after")
        return {"effect": {"effect_id": effect_id, "payload_digest": payload_digest,
                           "status": "intent_recorded"}, "step_log": steps}

    def effect_commit(state: TaskState) -> dict[str, Any]:
        assert worker is not None
        steps = log("effect_commit")
        task, effect = worker.task_id, dict(state["effect"])
        effect_id, tool = effect["effect_id"], state["constraints"]["effect_tool"]
        payload = effect_payload(task, state)
        intent = worker.ledger.get(task, effect_id)
        if intent is None or intent["payload_digest"] != digest(payload):
            raise Conflict("effect commit without a matching durable intent")
        if intent["status"] in ("committed", "reconciled_committed"):
            return {"effect": {**effect, "status": "committed"}, "step_log": steps}
        reconciled = False
        if intent["status"] in ("attempt_started", "unknown"):
            # A previous execution started the external call; its outcome is uncertain.
            if tool == "opaque":
                worker.ledger.mark(task, effect_id, "unknown", worker.execution_id, worker.epoch)
                return {"effect": {**effect, "status": "unknown"}, "status": "reconcile_required",
                        "step_log": steps}
            if worker.gateway.reconcile(task, effect_id) == "committed":
                worker.ledger.mark(task, effect_id, "reconciled_committed",
                                   worker.execution_id, worker.epoch)
                return {"effect": {**effect, "status": "committed", "reconciled": "found_committed"},
                        "step_log": steps}
            # No commit record in the system of record: retrying with the SAME effect ID is
            # safe only because this simulated gateway deduplicates by effect ID.
            reconciled = True
        worker.ledger.mark(task, effect_id, "attempt_started", worker.execution_id, worker.epoch)
        worker.faults.hit("effect_commit.before")
        if tool == "gateway":
            worker.gateway.commit(task, worker.execution_id, worker.epoch, effect_id, payload)
        else:
            worker.opaque.invoke(task, effect_id, worker.execution_id, worker.epoch, payload)
        worker.faults.hit("effect_commit.after")
        worker.ledger.mark(task, effect_id, "reconciled_committed" if reconciled else "committed",
                           worker.execution_id, worker.epoch)
        result = {**effect, "status": "committed"}
        if reconciled:
            result["reconciled"] = "retried_same_effect_id"
        return {"effect": result, "step_log": steps}

    def finalize(state: TaskState) -> dict[str, Any]:
        return {"status": "done", "step_log": log("finalize")}

    def after_item(state: TaskState) -> str:
        return "process_item" if state["cursor"] < len(state["items"]) else "effect_intent"

    def after_commit(state: TaskState) -> str:
        return "finalize" if state["effect"]["status"] == "committed" else END

    builder = StateGraph(TaskState)
    builder.add_node("process_item", process_item)
    builder.add_node("effect_intent", effect_intent)
    builder.add_node("effect_commit", effect_commit)
    builder.add_node("finalize", finalize)
    builder.add_edge(START, "process_item")
    builder.add_conditional_edges("process_item", after_item, ["process_item", "effect_intent"])
    builder.add_edge("effect_intent", "effect_commit")
    builder.add_conditional_edges("effect_commit", after_commit, ["finalize", END])
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=saver)


@contextmanager
def _runtime(path: str, task_id: str, worker: Worker | None = None,
             authority: str | None = None) -> Iterator[tuple[Any, FencedSqliteSaver]]:
    """Graph + saver on the store at ``path``; ``authority`` attaches a separate coordinator file."""
    conn = sqlite3.connect(path, check_same_thread=False, timeout=10)
    try:
        conn.execute("PRAGMA busy_timeout = 10000")
        schema = _attach(conn, authority)
        saver = FencedSqliteSaver(conn, task_id,
                                  worker.execution_id if worker else None,
                                  worker.epoch if worker else None,
                                  worker.faults if worker else None, schema)
        yield build_graph(worker, saver), saver
    finally:
        conn.close()


def checkpoint_digest(checkpoint: dict[str, Any]) -> str:
    try:
        return digest({"id": checkpoint["id"], "channel_values": checkpoint["channel_values"],
                       "channel_versions": checkpoint["channel_versions"],
                       "versions_seen": checkpoint["versions_seen"]})
    except (TypeError, ValueError) as exc:
        raise Incompatible("non-JSON checkpoint state is unsupported",
                           {"unavailable_state": ["channel_values"]}) from exc


def build_manifest(path: str | Path, task_id: str, movement_id: str, from_execution: str,
                   from_epoch: int, to_execution: str, mode: str) -> dict[str, Any]:
    """Describe exactly what is exported from the head checkpoint, and what is not."""
    for value, label in ((task_id, "task_id"), (movement_id, "movement_id"),
                         (from_execution, "from_execution"), (to_execution, "to_execution")):
        _id(value, label)
    if mode not in ("cooperative", "failover"):
        raise ContractError("invalid relocation mode")
    with _runtime(str(path), task_id) as (graph, saver):
        config = {"configurable": {"thread_id": task_id, "checkpoint_ns": ""}}
        head = saver.get_tuple(config)
        if head is None:
            raise Conflict("no durable checkpoint for task")
        snapshot = graph.get_state(config)
    # Pending writes = successful node outputs of a superstep whose checkpoint never
    # committed (the executor crashed). LangGraph re-applies them on resume, so a
    # failover may carry them; a cooperative export must sit on a clean boundary.
    pending = sorted({f"{task}:{channel}" for task, channel, _value in head.pending_writes})
    if pending and mode == "cooperative":
        raise Conflict("unsafe boundary: checkpoint has pending writes")
    # snapshot.next omits tasks whose outputs are already durable pending writes,
    # so the scheduled nodes are read from snapshot.tasks.
    scheduled = [t.name for t in snapshot.tasks]
    if snapshot.interrupts or set(scheduled) - set(NODES) or not scheduled:
        raise Conflict("unsafe boundary: interrupt, unknown node or finished task")
    checkpoint = head.checkpoint
    meta = head.metadata or {}
    uncertain = EffectLedger(str(path)).uncertain(task_id)
    return {
        "profile": PROFILE, "movement_id": movement_id, "mode": mode,
        "logical_task_id": task_id, "from_execution": from_execution, "from_epoch": from_epoch,
        "to_execution": to_execution,
        "checkpoint": {"thread_id": task_id, "checkpoint_ns": "", "checkpoint_id": checkpoint["id"],
                       "parent_checkpoint_id": (head.parent_config or {}).get("configurable", {})
                       .get("checkpoint_id"), "format": checkpoint["v"], "step": meta.get("step"),
                       "written_by": meta.get("execution_id"), "next": scheduled,
                       "digest": checkpoint_digest(checkpoint),
                       "exported_channels": sorted(checkpoint["channel_values"]),
                       "pending_writes": pending},
        "runtime": runtime_versions(), "graph_id": GRAPH_ID, "graph_version": GRAPH_VERSION,
        "channels": list(STATE_CHANNELS), "uncertain_effects": uncertain,
        "exported_state": sorted(EXPORTED_STATE), "unsupported_state": sorted(UNSUPPORTED_STATE),
    }


def bundle_name(movement_id: str) -> str:
    return f"{_id(movement_id, 'movement_id')}.bundle.json"


def build_bundle(state_path: str | Path, task_id: str, movement_id: str, from_execution: str,
                 from_epoch: int, to_execution: str, mode: str) -> tuple[dict[str, Any], bytes]:
    """Two-store export: manifest plus a self-describing bundle of the head checkpoint (read only)."""
    manifest = build_manifest(state_path, task_id, movement_id, from_execution, from_epoch,
                              to_execution, mode)
    checkpoint_id = manifest["checkpoint"]["checkpoint_id"]
    with _runtime(str(state_path), task_id) as (_graph, saver):
        head = saver.get_tuple({"configurable": {"thread_id": task_id, "checkpoint_ns": "",
                                                 "checkpoint_id": checkpoint_id}})
    with closing(sqlite3.connect(str(state_path), timeout=10)) as db:
        payload = bundles.read_payload(db, task_id, checkpoint_id)
    manifest = {**manifest, "transport": "bundle",
                "exported_state": sorted(BUNDLE_EXPORTED_STATE),
                "unsupported_state": sorted(BUNDLE_UNSUPPORTED_STATE),
                "bundle": bundles.describe(payload, head.checkpoint["channel_values"])}
    return manifest, bundles.encode(manifest, payload)


def export_bundle(state_path: str | Path, outbox: str | Path, task_id: str, movement_id: str,
                  from_execution: str, from_epoch: int, to_execution: str,
                  mode: str) -> tuple[dict[str, Any], str]:
    """Build the bundle and write it atomically to ``outbox/<movement>.bundle.json``."""
    manifest, data = build_bundle(state_path, task_id, movement_id, from_execution, from_epoch,
                                  to_execution, mode)
    return manifest, bundles.write_atomic(Path(outbox) / bundle_name(movement_id), data)


def compatibility(manifest: dict[str, Any], receiver: dict[str, Any]) -> dict[str, Any]:
    """Fail closed on ANY mismatch and say which exported state would be lost or unavailable."""
    mismatches = []
    for name, origin_value, receiver_value in (
            ("profile", manifest["profile"], receiver["profile"]),
            ("runtime", manifest["runtime"], receiver["runtime"]),
            ("graph_id", manifest["graph_id"], receiver["graph_id"]),
            ("graph_version", manifest["graph_version"], receiver["graph_version"]),
            ("checkpoint_format", manifest["checkpoint"]["format"], receiver["checkpoint_format"])):
        if origin_value != receiver_value:
            mismatches.append({"field": name, "origin": origin_value, "receiver": receiver_value})
    if receiver["runtime"] != PINNED_RUNTIME:
        mismatches.append({"field": "receiver_runtime_pin", "origin": PINNED_RUNTIME,
                           "receiver": receiver["runtime"]})
    lost = sorted(set(manifest["channels"]) - set(receiver["channels"]))
    if lost:
        mismatches.append({"field": "channels", "origin": manifest["channels"],
                           "receiver": receiver["channels"]})
    compatible = not mismatches
    structural = any(m["field"] != "channels" for m in mismatches)
    return {"compatible": compatible, "decision": "accept" if compatible else "refuse_fail_closed",
            "mismatches": mismatches, "lost_state": lost,
            "unavailable_state": [] if compatible else (sorted(manifest["channels"]) if structural else lost),
            "always_unsupported": sorted(UNSUPPORTED_STATE)}


class Coordinator:
    """Records relocation requests and moves the ownership epoch atomically with the head check.

    ``path`` is the authority file. In single-store mode it is also the checkpoint store.
    """

    def __init__(self, path: str | Path, faults: Faults | None = None):
        self.path = str(path)
        self.store = SQLiteStore(path)
        self.faults = faults or Faults()

    def _row(self, db: sqlite3.Connection, movement_id: str, schema: str = "main") -> dict[str, Any] | None:
        if schema not in ("main", AUTHORITY):
            raise ContractError("unknown authority schema")
        row = db.execute("SELECT task_id,mode,from_execution,from_epoch,to_execution,to_epoch,"
                         "checkpoint_id,manifest_json,manifest_digest,status,report_json,transport "
                         f"FROM {schema}.relocations WHERE movement_id=?", (movement_id,)).fetchone()
        keys = ("task_id", "mode", "from_execution", "from_epoch", "to_execution", "to_epoch",
                "checkpoint_id", "manifest_json", "manifest_digest", "status", "report_json", "transport")
        return None if row is None else dict(zip(keys, row))

    def get(self, movement_id: str) -> dict[str, Any] | None:
        with self.store._connection() as db:
            return self._row(db, movement_id)

    def _record_request(self, db: sqlite3.Connection, manifest: dict[str, Any],
                        schema: str = "main") -> dict[str, Any]:
        """Insert the request inside the CALLER's ``BEGIN IMMEDIATE`` transaction (idempotent)."""
        fingerprint = digest(manifest)
        row = self._row(db, manifest["movement_id"], schema)
        if row is not None:
            if row["manifest_digest"] != fingerprint:
                raise Conflict("movement ID reused with a different manifest")
            return {"status": row["status"], "replayed": True}
        _fence(db, manifest["logical_task_id"], manifest["from_execution"], manifest["from_epoch"], schema,
               frozen_ok=manifest["mode"] == "failover")
        transport = "bundle" if manifest.get("transport") == "bundle" else "shared"
        db.execute(f"INSERT INTO {schema}.relocations(movement_id,task_id,mode,from_execution,from_epoch,"
                   "to_execution,checkpoint_id,manifest_json,manifest_digest,status,transport) "
                   "VALUES(?,?,?,?,?,?,?,?,?,'requested',?)",
                   (manifest["movement_id"], manifest["logical_task_id"], manifest["mode"],
                    manifest["from_execution"], manifest["from_epoch"], manifest["to_execution"],
                    manifest["checkpoint"]["checkpoint_id"], canonical(manifest), fingerprint, transport))
        return {"status": "requested", "replayed": False}

    def request(self, manifest: dict[str, Any]) -> dict[str, Any]:
        """Origin -> coordinator. Idempotent by movement ID; only the current owner may ask."""
        if manifest.get("transport") == "bundle":
            raise ContractError("bundle manifests are recorded with request_bundle()")
        with self.store._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            result = self._record_request(db, manifest)
            db.commit()
            return result

    def request_bundle(self, manifest: dict[str, Any], source_store: str | Path) -> dict[str, Any]:
        """Two-store request: record it only while the bundled checkpoint is still the source head.

        One ``BEGIN IMMEDIATE`` holds the source store and the attached coordinator file,
        so no checkpoint can land between the head check and the request; from then on the
        export freeze in :func:`_fence` keeps the origin from writing until transfer/refusal.
        """
        if manifest.get("transport") != "bundle":
            raise ContractError("not a bundle manifest")
        with _state_connection(str(source_store), self.path) as (db, schema):
            db.execute("BEGIN IMMEDIATE")
            head = db.execute("SELECT checkpoint_id FROM main.checkpoints WHERE thread_id=? AND "
                              "checkpoint_ns='' ORDER BY checkpoint_id DESC LIMIT 1",
                              (manifest["logical_task_id"],)).fetchone()
            replay = self._row(db, manifest["movement_id"], schema)
            if replay is None and (head is None or head[0] != manifest["checkpoint"]["checkpoint_id"]):
                raise Conflict("bundled checkpoint is no longer the source head; re-export")
            result = self._record_request(db, manifest, schema)
            db.commit()
            return result

    def transfer(self, movement_id: str, receiver_profile: dict[str, Any]) -> dict[str, Any]:
        """Compatibility check, head check and epoch bump in ONE SQLite transaction."""
        with self.store._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._row(db, movement_id)
            if row is None:
                raise Conflict("unknown movement")
            grant = {"movement_id": movement_id, "logical_task_id": row["task_id"],
                     "to_execution": row["to_execution"], "checkpoint_id": row["checkpoint_id"]}
            if row["status"] in ("transferred", "acknowledged"):
                db.commit()
                return {**grant, "status": row["status"], "to_epoch": row["to_epoch"], "replayed": True}
            if row["status"] == "refused":
                db.commit()
                return {**grant, "status": "refused", "report": canonical_load(row["report_json"]),
                        "replayed": True}
            if row["status"] != "requested":
                raise Conflict(f"movement is {row['status']}")
            manifest = canonical_load(row["manifest_json"])
            report = compatibility(manifest, receiver_profile)
            if not report["compatible"]:
                db.execute("UPDATE relocations SET status='refused', report_json=? WHERE movement_id=?",
                           (canonical(report), movement_id))
                db.commit()
                return {**grant, "status": "refused", "report": report, "replayed": False}
            if row["transport"] == "shared":
                head = db.execute("SELECT checkpoint_id FROM checkpoints WHERE thread_id=? AND "
                                  "checkpoint_ns='' ORDER BY checkpoint_id DESC LIMIT 1",
                                  (row["task_id"],)).fetchone()
                if head is None or head[0] != row["checkpoint_id"]:
                    raise Conflict("manifest checkpoint is no longer the head; re-export")
            # Bundle transport: the coordinator never reads a worker store. request_bundle()
            # checked the head under lock and the export freeze has kept it there since.
            self.faults.hit("coordinator.before_transfer")
            moved = db.execute("UPDATE owners SET agent_id=?, epoch=epoch+1 WHERE task_id=? AND "
                               "agent_id=? AND epoch=?", (row["to_execution"], row["task_id"],
                                                          row["from_execution"], row["from_epoch"]))
            if moved.rowcount != 1:
                raise Conflict("stale or missing owner/epoch")
            to_epoch = row["from_epoch"] + 1
            db.execute("UPDATE relocations SET status='superseded' WHERE task_id=? AND "
                       "movement_id<>? AND status IN ('requested','transferred')",
                       (row["task_id"], movement_id))
            db.execute("UPDATE relocations SET status='transferred', to_epoch=? WHERE movement_id=?",
                       (to_epoch, movement_id))
            db.commit()
        self.faults.hit("coordinator.after_transfer")
        return {**grant, "status": "transferred", "to_epoch": to_epoch, "replayed": False}

    def acknowledge(self, movement_id: str, execution_id: str, epoch: int) -> dict[str, Any]:
        """Receiver -> coordinator: resumed at the manifest checkpoint. Idempotent."""
        with self.store._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._row(db, movement_id)
            if row is None:
                raise Conflict("unknown movement")
            if (row["to_execution"], row["to_epoch"]) != (execution_id, epoch):
                raise PolicyDenied("acknowledgement from an execution that holds no grant")
            _fence(db, row["task_id"], execution_id, epoch)
            if row["status"] == "acknowledged":
                db.commit()
                return {"status": "acknowledged", "replayed": True}
            if row["status"] != "transferred":
                raise Conflict(f"movement is {row['status']}")
            db.execute("UPDATE relocations SET status='acknowledged' WHERE movement_id=?", (movement_id,))
            db.commit()
            return {"status": "acknowledged", "replayed": False}

    def failover(self, movement_id: str, task_id: str, to_execution: str,
                 receiver_profile: dict[str, Any], *, source_store: str | Path | None = None,
                 outbox: str | Path | None = None) -> dict[str, Any]:
        """Relocate without origin cooperation (origin/receiver crashed) from the durable head.

        Two-store mode: ``source_store`` is the store holding the task's durable head (the
        last acknowledged receiver's, else the origin's) and must be readable by the
        recovering operator; the bundle is written to ``outbox``.
        """
        owner = owner_of(self.store, task_id)
        if owner is None:
            raise Conflict("task has no owner")
        if source_store is None:
            manifest = build_manifest(self.path, task_id, movement_id, owner[0], owner[1],
                                      to_execution, "failover")
            self.request(manifest)
            return self.transfer(movement_id, receiver_profile)
        if outbox is None:
            raise ContractError("two-store failover needs an outbox for the bundle")
        manifest, path = export_bundle(source_store, outbox, task_id, movement_id, owner[0], owner[1],
                                       to_execution, "failover")
        self.request_bundle(manifest, source_store)
        return {**self.transfer(movement_id, receiver_profile), "bundle": path}


def canonical_load(raw: str | None) -> Any:
    return None if raw is None else json.loads(raw)


class Worker:
    """One *execution* (worker_id + incarnation) of a *logical task* (LangGraph thread_id).

    ``path`` is the authority (coordinator) file. ``store`` selects two-store mode: the
    worker's checkpoints, effect ledger and node journal then live in that file instead.
    """

    def __init__(self, path: str | Path, worker_id: str, incarnation: int = 1, *,
                 faults: Faults | None = None, profile: dict[str, Any] | None = None,
                 store: str | Path | None = None):
        _id(worker_id, "worker_id")
        if type(incarnation) is not int or incarnation < 1:
            raise ContractError("invalid incarnation")
        self.path = str(path)
        self.state_path = self.path if store is None else str(store)
        if self.state_path != self.path and Path(self.state_path).resolve() == Path(self.path).resolve():
            raise ContractError("a separate worker store must be a different file")
        # None = single store; otherwise the coordinator file to ATTACH for fencing.
        self.authority = None if self.state_path == self.path else self.path
        self.worker_id = worker_id
        self.execution_id = f"{worker_id}.{incarnation}"
        self.store = SQLiteStore(path)
        self.gateway = EffectGateway(self.store)
        self.ledger = EffectLedger(self.store) if self.authority is None else \
            EffectLedger(self.state_path, self.authority)
        self.opaque = OpaqueTool(self.store)
        self.faults = faults or Faults()
        self.profile = profile or local_profile()
        self.task_id: str | None = None
        self.epoch: int | None = None
        self.node_runs: Counter[str] = Counter()

    def attach(self, task_id: str, epoch: int) -> Worker:
        """Continue an execution in a fresh process; authority is still checked by the fence."""
        self.task_id, self.epoch = _id(task_id, "task_id"), epoch
        return self

    def journal(self, node: str, index: int | None) -> None:
        """Harness instrumentation (not protocol): every node *attempt*, even if later fenced."""
        self.node_runs[node] += 1
        with closing(sqlite3.connect(self.state_path, timeout=10)) as db:
            db.execute("INSERT INTO node_runs(task_id,execution_id,epoch,node,item_index) "
                       "VALUES(?,?,?,?,?)", (self.task_id, self.execution_id, self.epoch, node, index))
            db.commit()

    def owns(self) -> bool:
        return owner_of(self.store, self.task_id) == (self.execution_id, self.epoch)

    def _config(self) -> dict[str, Any]:
        return {"configurable": {"thread_id": self.task_id, "execution_id": self.execution_id,
                                 "epoch": self.epoch}}

    def start(self, task_id: str, items: list[str], constraints: dict[str, Any],
              max_supersteps: int | None = None) -> dict[str, Any]:
        state = initial_state(items, constraints)
        self.task_id = _id(task_id, "task_id")
        self.epoch = self.gateway.claim(task_id, self.execution_id)
        return self.run(max_supersteps, task_input=state)

    def run(self, max_supersteps: int | None = None, *, task_input: dict[str, Any] | None = None,
            check_ownership: bool = True) -> dict[str, Any]:
        """Advance one superstep per invoke; each boundary is a durable checkpoint."""
        if self.task_id is None or self.epoch is None:
            raise ContractError("worker is not attached to a task")
        steps = 0
        with _runtime(self.state_path, self.task_id, self, self.authority) as (graph, _saver):
            config = self._config()
            while max_supersteps is None or steps < max_supersteps:
                if check_ownership and not self.owns():
                    raise PolicyDenied("execution no longer owns the task; paused")
                if task_input is None and not graph.get_state(config).tasks:
                    break
                graph.invoke(task_input, config, interrupt_after="*", durability="sync")
                task_input = None
                steps += 1
            snapshot = graph.get_state(config)
        return {"execution_id": self.execution_id, "epoch": self.epoch, "supersteps": steps,
                "next": [t.name for t in snapshot.tasks], "status": snapshot.values.get("status"),
                "checkpoint_id": snapshot.config["configurable"]["checkpoint_id"],
                "node_runs": dict(self.node_runs)}

    def export(self, movement_id: str, to_execution: str) -> dict[str, Any]:
        """Origin side: pause at the current safe boundary and ask the coordinator to relocate."""
        if self.authority is not None:
            raise ContractError("a worker with its own store exports with export_bundle()")
        if not self.owns():
            raise PolicyDenied("only the current owner may export")
        manifest = build_manifest(self.path, self.task_id, movement_id, self.execution_id,
                                  self.epoch, to_execution, "cooperative")
        if manifest["uncertain_effects"]:
            raise Conflict("unsafe boundary: an effect outcome is uncertain; reconcile first")
        self.faults.hit("origin.before_export")
        result = Coordinator(self.path).request(manifest)
        self.faults.hit("origin.after_export")
        return {**result, "manifest": manifest}

    def export_bundle(self, movement_id: str, to_execution: str, outbox: str | Path) -> dict[str, Any]:
        """Two-store origin side: write a digest-described bundle, then request relocation.

        The request is recorded only while the bundled checkpoint is still this store's
        head; from then on this execution is frozen (its writes are denied) until the
        coordinator transfers or refuses the movement.
        """
        if self.authority is None:
            raise ContractError("export_bundle() needs a worker with its own store")
        if not self.owns():
            raise PolicyDenied("only the current owner may export")
        manifest, path = export_bundle(self.state_path, outbox, self.task_id, movement_id,
                                       self.execution_id, self.epoch, to_execution, "cooperative")
        if manifest["uncertain_effects"]:
            Path(path).unlink(missing_ok=True)
            raise Conflict("unsafe boundary: an effect outcome is uncertain; reconcile first")
        self.faults.hit("origin.before_export")
        result = Coordinator(self.path).request_bundle(manifest, self.state_path)
        self.faults.hit("origin.after_export")
        return {**result, "manifest": manifest, "bundle": path, "bundle_sha256": bundles.sha256_file(path)}

    def accept(self, movement_id: str, bundle: str | Path | None = None) -> dict[str, Any]:
        """Receiver side: verify grant, compatibility and checkpoint digest, then acknowledge.

        For a bundle movement, ``bundle`` is the receiver's local copy; it is verified and
        imported atomically into this worker's own store before the acknowledgement.
        """
        self.faults.hit("receiver.before_accept")
        coordinator = Coordinator(self.path)
        row = coordinator.get(movement_id)
        if row is None:
            raise Conflict("unknown movement")
        if row["to_execution"] != self.execution_id:
            raise PolicyDenied("grant addressed to another execution")
        if row["status"] not in ("transferred", "acknowledged"):
            raise PolicyDenied(f"movement is {row['status']}")
        if owner_of(self.store, row["task_id"]) != (self.execution_id, row["to_epoch"]):
            raise PolicyDenied("grant superseded by a newer epoch")
        self.task_id, self.epoch = row["task_id"], row["to_epoch"]
        manifest = canonical_load(row["manifest_json"])
        if row["transport"] == "bundle":
            return self._accept_bundle(coordinator, movement_id, row, manifest, bundle)
        if self.authority is not None:
            raise ContractError("a worker with its own store accepts bundle movements only")
        with _runtime(self.path, self.task_id, self) as (_graph, saver):
            head = saver.get_tuple({"configurable": {"thread_id": self.task_id, "checkpoint_ns": ""}})
            if row["status"] == "acknowledged":
                # Duplicate grant: never rewind to the transfer checkpoint.
                return {"accepted": True, "replayed": True, "head_checkpoint_id": head.checkpoint["id"]}
            report = compatibility(manifest, self.profile)
            if not report["compatible"]:
                raise Incompatible("receiver cannot resume this checkpoint", report)
            exported = saver.get_tuple({"configurable": {
                "thread_id": self.task_id, "checkpoint_ns": "",
                "checkpoint_id": manifest["checkpoint"]["checkpoint_id"]}})
            if exported is None:
                raise Incompatible("exported checkpoint is missing",
                                   {**report, "unavailable_state": sorted(manifest["channels"])})
            if checkpoint_digest(exported.checkpoint) != manifest["checkpoint"]["digest"]:
                raise Incompatible("checkpoint digest does not match manifest",
                                   {**report, "compatible": False, "decision": "refuse_fail_closed",
                                    "unavailable_state": sorted(manifest["channels"])})
            if head is None or head.checkpoint["id"] != exported.checkpoint["id"]:
                raise Conflict("head moved after transfer")
        self.faults.hit("receiver.after_accept")
        ack = coordinator.acknowledge(movement_id, self.execution_id, self.epoch)
        self.faults.hit("ack.after")
        return {"accepted": True, "replayed": False, "checkpoint_id": manifest["checkpoint"]["checkpoint_id"],
                "step": manifest["checkpoint"]["step"], "ack": ack}

    # --- two-store receiver ----------------------------------------------------
    def _refuse(self, manifest: dict[str, Any], reason: str, message: str, **extra: Any) -> Incompatible:
        """Fail closed: nothing was imported; name everything the receiver cannot resume."""
        report = {"compatible": False, "decision": "refuse_fail_closed", "reason": reason,
                  "mismatches": [], "lost_state": [],
                  "unavailable_state": sorted(manifest["channels"]) + ["effect_ledger"],
                  "always_unsupported": sorted(BUNDLE_UNSUPPORTED_STATE),
                  "corrupt_sections": [], "corrupt_channels": [], **extra}
        return Incompatible(message, report)

    def _accept_bundle(self, coordinator: Coordinator, movement_id: str, row: dict[str, Any],
                       manifest: dict[str, Any], bundle: str | Path | None) -> dict[str, Any]:
        if self.authority is None:
            raise ContractError("bundle movements need a receiver with its own store")
        checkpoint_id = manifest["checkpoint"]["checkpoint_id"]
        with _runtime(self.state_path, self.task_id, self, self.authority) as (_graph, saver):
            if row["status"] == "acknowledged":
                # Duplicate grant or import: never rewind, never re-read the bundle.
                head = saver.get_tuple({"configurable": {"thread_id": self.task_id, "checkpoint_ns": ""}})
                return {"accepted": True, "replayed": True,
                        "head_checkpoint_id": None if head is None else head.checkpoint["id"]}
            if bundle is None:
                raise self._refuse(manifest, "bundle_missing", "no local bundle copy was supplied")
            # 1. bytes -> canonical, size-bounded, duplicate-key-free JSON of the known format
            try:
                parsed, bundle_sha = bundles.parse(bundle)
            except bundles.BundleRejected as exc:
                raise self._refuse(manifest, exc.reason, str(exc)) from exc
            # 2. it must be exactly the manifest the coordinator recorded (the trust anchor)
            if digest(parsed["manifest"]) != row["manifest_digest"]:
                raise self._refuse(manifest, "manifest_not_granted",
                                   "bundle manifest is not the manifest recorded for this movement")
            # 3. runtime/graph/channel compatibility, as for the single-store receiver
            report = compatibility(manifest, self.profile)
            if not report["compatible"]:
                raise Incompatible("receiver cannot resume this checkpoint", report)
            # 4. section digests BEFORE any deserialization of the payload
            try:
                corrupt = bundles.corrupt_sections(manifest, parsed["payload"])
            except bundles.BundleRejected as exc:
                raise self._refuse(manifest, exc.reason, str(exc)) from exc
            if corrupt:
                raise self._refuse(manifest, "digest_mismatch", "bundle section digest mismatch",
                                   corrupt_sections=corrupt)
            payload = parsed["payload"]
            # 5. decode with the pinned serializer; semantic and per-channel digests
            try:
                checkpoint = bundles.decode_checkpoint(payload, saver.serde)
            except bundles.BundleRejected as exc:
                raise self._refuse(manifest, exc.reason, str(exc)) from exc
            channels = bundles.channel_digests(checkpoint.get("channel_values", {}))
            expected = manifest["bundle"]["channel_digests"]
            bad = sorted(n for n in set(channels) | set(expected) if channels.get(n) != expected.get(n))
            if checkpoint.get("id") != checkpoint_id or bad or \
                    checkpoint_digest(checkpoint) != manifest["checkpoint"]["digest"]:
                raise self._refuse(manifest, "digest_mismatch", "decoded checkpoint does not match manifest",
                                   corrupt_channels=bad)
            if sorted(e["effect_id"] for e in payload["effect_ledger"]
                      if e["status"] in ("attempt_started", "unknown")) != manifest["uncertain_effects"]:
                raise self._refuse(manifest, "digest_mismatch", "effect records disagree with manifest",
                                   corrupt_sections=["effect_ledger"])
            imported = self._import_rows(movement_id, row, payload, bundle_sha)
            head = saver.get_tuple({"configurable": {"thread_id": self.task_id, "checkpoint_ns": ""}})
            if head is None or head.checkpoint["id"] != checkpoint_id or \
                    checkpoint_digest(head.checkpoint) != manifest["checkpoint"]["digest"]:
                raise Conflict("imported checkpoint is not the head of the receiver store")
        self.faults.hit("receiver.after_accept")
        ack = coordinator.acknowledge(movement_id, self.execution_id, self.epoch)
        self.faults.hit("ack.after")
        return {"accepted": True, "replayed": False, "checkpoint_id": checkpoint_id,
                "step": manifest["checkpoint"]["step"], "bundle_sha256": bundle_sha,
                "imported": imported, "ack": ack}

    def _import_rows(self, movement_id: str, row: dict[str, Any], payload: dict[str, Any],
                     bundle_sha: str) -> dict[str, Any]:
        """ONE fenced transaction in this worker's store: all rows and the import record, or nothing."""
        with _state_connection(self.state_path, self.authority) as (db, schema):
            db.execute("BEGIN IMMEDIATE")
            _fence(db, self.task_id, self.execution_id, self.epoch, schema)
            prior = db.execute("SELECT manifest_digest, bundle_sha256 FROM bundle_imports WHERE movement_id=?",
                               (movement_id,)).fetchone()
            if prior is not None:
                if tuple(prior) != (row["manifest_digest"], bundle_sha):
                    raise Conflict("movement already imported from a different bundle")
                db.commit()
                return {"replayed": True}
            local_head = db.execute("SELECT MAX(checkpoint_id) FROM checkpoints WHERE thread_id=? AND "
                                    "checkpoint_ns=''", (self.task_id,)).fetchone()[0]
            if local_head is not None and local_head > row["checkpoint_id"]:
                raise Conflict("receiver store already holds a newer checkpoint; refusing to rewind")
            counts = bundles.insert_payload(db, self.task_id, payload)
            db.execute("INSERT INTO bundle_imports(movement_id, task_id, checkpoint_id, manifest_digest, "
                       "bundle_sha256, execution_id, epoch) VALUES(?,?,?,?,?,?,?)",
                       (movement_id, self.task_id, row["checkpoint_id"], row["manifest_digest"], bundle_sha,
                        self.execution_id, self.epoch))
            self.faults.hit("import.before_commit")
            db.commit()
        self.faults.hit("import.after_commit")
        return {"replayed": False, **counts}


def _store_view(path: str, task_id: str) -> dict[str, Any]:
    """Read-only harness view of ONE state store: journal, head and checkpoint lineage."""
    with closing(sqlite3.connect(path, timeout=10)) as db:
        runs = db.execute("SELECT execution_id, node, COUNT(*) FROM node_runs WHERE task_id=? "
                          "GROUP BY execution_id, node ORDER BY execution_id, node", (task_id,)).fetchall()
        item_runs = db.execute("SELECT item_index, COUNT(*) FROM node_runs WHERE task_id=? AND "
                               "node='process_item' GROUP BY item_index", (task_id,)).fetchall()
        effects = db.execute("SELECT COUNT(*) FROM effect_intents WHERE task_id=?", (task_id,)).fetchone()[0]
        imports = db.execute("SELECT COUNT(*) FROM bundle_imports WHERE task_id=?", (task_id,)).fetchone()[0]
    with _runtime(path, task_id) as (_graph, saver):
        head = saver.get_tuple({"configurable": {"thread_id": task_id, "checkpoint_ns": ""}})
        lineage = [{"checkpoint_id": c.checkpoint["id"], "step": (c.metadata or {}).get("step"),
                    "written_by": (c.metadata or {}).get("execution_id"),
                    "parent": (c.parent_config or {}).get("configurable", {}).get("checkpoint_id")}
                   for c in saver.list({"configurable": {"thread_id": task_id, "checkpoint_ns": ""}})]
    lineage.reverse()
    return {"runs": runs, "item_runs": item_runs, "head": head, "lineage": lineage,
            "effect_records": effects, "imports": imports}


def observe(path: str | Path, task_id: str, effect_id: str = "publish-report",
            stores: dict[str, str | Path] | None = None) -> dict[str, Any]:
    """Ground truth for the experiment harness (reads only).

    ``stores`` (two-store mode) maps worker_id -> that worker's own store. The head,
    values and effect record are then read from the CURRENT OWNER's store; journals
    and lineage are merged across all stores (a copied checkpoint is listed once).
    """
    store = SQLiteStore(path)
    with store._connection() as db:
        commits = db.execute("SELECT effect_id, epoch FROM effects WHERE task_id=? ORDER BY effect_id",
                             (task_id,)).fetchall()
        opaque = db.execute("SELECT COUNT(*) FROM opaque_effects WHERE task_id=?", (task_id,)).fetchone()[0]
        relocations = db.execute("SELECT movement_id, mode, from_execution, from_epoch, to_execution, "
                                 "to_epoch, status FROM relocations WHERE task_id=? ORDER BY rowid",
                                 (task_id,)).fetchall()
    owner = owner_of(store, task_id)
    if stores is None:
        views = {"": _store_view(str(path), task_id)}
        head_view = views[""]
        ledger_path: str | None = str(path)
    else:
        views = {worker: _store_view(str(p), task_id) for worker, p in sorted(stores.items())}
        owner_worker = None if owner is None else owner[0].rsplit(".", 1)[0]
        head_view = views.get(owner_worker) if owner_worker else None
        ledger_path = str(stores[owner_worker]) if head_view is not None else None
    run_counts: Counter[tuple[str, str]] = Counter()
    item_counts: Counter[int] = Counter()
    lineage_by_id: dict[str, dict[str, Any]] = {}
    for view in views.values():
        for execution, node, count in view["runs"]:
            run_counts[(execution, node)] += count
        for index, count in view["item_runs"]:
            item_counts[index] += count
        for entry in view["lineage"]:
            lineage_by_id.setdefault(entry["checkpoint_id"], entry)
    node_runs: dict[str, dict[str, int]] = {}
    for (execution, node), count in sorted(run_counts.items()):
        node_runs.setdefault(execution, {})[node] = count
    head = None if head_view is None else head_view["head"]
    result = {
        "owner": None if owner is None else {"execution_id": owner[0], "epoch": owner[1]},
        "gateway_commits": [{"effect_id": e, "epoch": ep} for e, ep in commits],
        "opaque_invocations": opaque,
        "effect_intent": None if ledger_path is None else EffectLedger(ledger_path).get(task_id, effect_id),
        "node_runs": node_runs,
        "process_item_runs": sum(v.get("process_item", 0) for v in node_runs.values()),
        "item_reexecutions": sum(count - 1 for count in item_counts.values()),
        "relocations": [dict(zip(("movement_id", "mode", "from_execution", "from_epoch",
                                   "to_execution", "to_epoch", "status"), r)) for r in relocations],
        "head_checkpoint_id": None if head is None else head.checkpoint["id"],
        "values": None if head is None else head.checkpoint["channel_values"],
        "lineage": [lineage_by_id[k] for k in sorted(lineage_by_id)],
    }
    if stores is not None:
        result["stores"] = {worker: {"checkpoints": len(v["lineage"]), "effect_records": v["effect_records"],
                                     "imports": v["imports"],
                                     "head_checkpoint_id": None if v["head"] is None else v["head"].checkpoint["id"]}
                            for worker, v in views.items()}
    return result
