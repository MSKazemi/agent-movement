"""Bounded trace refinement from abstract movement state to the real SQLite gateway.

Only epoch fencing, effect deduplication and signed revocation after a synthetic
admission are mapped. Preparation, grants and activation remain abstract markers.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import tempfile
from collections import Counter, deque
from contextlib import closing
from pathlib import Path

from agent_movement.core import (
    Approval, ApprovalRevoked, Conflict, EffectGateway, HandoffReceiver,
    PolicyDenied, SCHEMA_VERSION, SQLiteStore,
)
from agent_movement.trust import HmacKey, issue_revocation
from movement_modelcheck import State, transitions

TASK = "task-1"
ABSTRACT_ONLY = frozenset({
    "prepare_destination", "issue_separate_destination_grant", "resume_destination",
})
SUPPORTED = ABSTRACT_ONLY | {"atomic_fence_and_transfer", "revoke_authority"}


def envelope():
    return {
        "schema_version": SCHEMA_VERSION, "movement_id": "movement-1",
        "logical_task_id": TASK, "operation": "delegate",
        "origin": {"agent_id": "agent-a"}, "destination": {"agent_id": "agent-b"},
        "task": {"kind": "word_count", "text": "synthetic baseline"},
        "context": {"classification": "synthetic"},
        "authority": {"approval_ref": "approval-1"},
        "execution": {"idempotency_key": "op-1"},
        "observability": {"trace_id": "trace-1"},
    }


def observe(path):
    """Independent committed-state observation, not a gateway return-value oracle."""
    with closing(sqlite3.connect(path)) as db:
        owner = db.execute(
            "SELECT agent_id,epoch FROM owners WHERE task_id=?", (TASK,)
        ).fetchone()
        effects = tuple(db.execute(
            "SELECT effect_id,epoch FROM effects WHERE task_id=? ORDER BY effect_id", (TASK,)
        ).fetchall())
        revoked = db.execute(
            "SELECT 1 FROM approval_revocations WHERE approval_ref=?", ("approval-1",)
        ).fetchone() is not None
    return (owner[0], owner[1], effects, revoked)


def expected(state):
    return (
        "agent-a" if state.owner == "A" else "agent-b",
        state.epoch,
        tuple(sorted((e.effect_id, e.epoch_at_commit) for e in state.effects)),
        state.revoked,
    )


def abstract_traces():
    """One shortest witness for each reachable state in the supported subgraph."""
    queue = deque([(State(), ())])
    seen = {State()}
    paths = []
    while queue:
        state, trace = queue.popleft()
        paths.append(trace)
        for edge in transitions(state):
            if edge.name not in SUPPORTED and not edge.name.startswith("commit_"):
                continue
            if edge.state not in seen:
                seen.add(edge.state)
                queue.append((edge.state, (*trace, edge.name)))
    return tuple(paths)


def _payload(effect):
    return "synthetic:" + effect


def replay_trace(trace):
    """Replay modeled commits and transfer in fresh real SQLite transactions."""
    with tempfile.TemporaryDirectory(prefix="am-refinement-") as directory:
        path = Path(directory) / "effects.sqlite"
        store = SQLiteStore(path)
        authority = HmacKey.generate("refinement-issuer")
        receiver = HandoffReceiver(
            "agent-b", store, [Approval("approval-1", TASK, "agent-a", "agent-b", "word_count")],
            revocation_authorities=[authority],
        )
        if receiver.receive(envelope())["replayed"]:
            raise AssertionError("admission unexpectedly replayed")
        gateway = EffectGateway(store)
        if gateway.claim(TASK, "agent-a") != 1:
            raise AssertionError("claim failed")
        state = State()
        covered = Counter()
        probes = Counter()
        if observe(path) != expected(state):
            raise AssertionError("initial state mismatch")
        for action in trace:
            choices = {edge.name: edge.state for edge in transitions(state)}
            if action not in choices or (action not in SUPPORTED and not action.startswith("commit_")):
                raise ValueError("unsupported or non-enabled model action: " + action)
            successor = choices[action]
            if action == "atomic_fence_and_transfer":
                assert gateway.transfer(TASK, "agent-a", 1, "agent-b") == 2
                covered["atomic_fence_and_transfer"] += 1
            elif action == "revoke_authority":
                assert not receiver.revoke(
                    issue_revocation(authority, "approval-1", 1_792_000_000)
                )["replayed"]
                covered["signed_revocation"] += 1
            elif action.startswith("commit_"):
                _, symbol, effect = action.split("_", 2)
                who = "agent-a" if symbol == "A" else "agent-b"
                assert gateway.commit(TASK, who, 1 if symbol == "A" else 2,
                                      effect, _payload(effect)) is True
                covered["protected_effect_commit"] += 1
            else:
                covered["abstract_only:" + action] += 1
            if observe(path) != expected(successor):
                raise AssertionError("durable SQL diverged after " + action)
            state = successor
        before = observe(path)
        who = "agent-a" if state.owner == "A" else "agent-b"
        epoch = state.epoch
        if state.owner == "B":
            try:
                gateway.commit(TASK, "agent-a", 1, "stale-probe", "synthetic")
                raise AssertionError("stale effect allowed")
            except PolicyDenied:
                probes["stale_origin_denied"] += 1
            try:
                gateway.transfer(TASK, "agent-a", 1, "agent-c")
                raise AssertionError("stale transfer allowed")
            except Conflict:
                probes["stale_transfer_denied"] += 1
        if state.revoked:
            try:
                gateway.commit(TASK, who, epoch, "after-revocation", "synthetic")
                raise AssertionError("revoked effect allowed")
            except ApprovalRevoked:
                probes["post_revocation_denied"] += 1
            if state.effects:
                e = state.effects[0]
                try:
                    gateway.commit(TASK, who, epoch, e.effect_id, _payload(e.effect_id))
                    raise AssertionError("revoked replay allowed")
                except ApprovalRevoked:
                    probes["revoked_replay_denied"] += 1
        elif state.effects:
            e = state.effects[0]
            if gateway.commit(TASK, who, epoch, e.effect_id, _payload(e.effect_id)) is not False:
                raise AssertionError("duplicate effect allowed")
            probes["stable_id_replay_deduplicated"] += 1
            try:
                gateway.commit(TASK, who, epoch, e.effect_id, "different-payload")
                raise AssertionError("effect ID collision allowed")
            except Conflict:
                probes["payload_collision_denied"] += 1
        if observe(path) != before:
            raise AssertionError("negative probe modified durable effects")
        for effect in state.effects:
            assert gateway.reconcile(TASK, effect.effect_id) == "committed"
        assert gateway.reconcile(TASK, "unknown-remote-effect") == "unknown"
        return {"covered": dict(covered), "probes": dict(probes), "final": observe(path)}


def run_suite():
    traces = abstract_traces()
    counts, probes = Counter(), Counter()
    for trace in traces:
        report = replay_trace(trace)
        counts.update(report["covered"])
        probes.update(report["probes"])
    assert counts["atomic_fence_and_transfer"] and counts["protected_effect_commit"]
    assert probes["stale_origin_denied"] and probes["post_revocation_denied"]
    return {
        "model": "bounded-abstract-to-real-SQLite-EffectGateway",
        "traces": len(traces),
        "covered": dict(sorted(counts.items())),
        "negative_probes": dict(sorted(probes.items())),
        "excluded": [
            "destination grants and activation ordering",
            "network partitions and runtime crashes",
            "core approval expiry after admission",
            "external side effects and bypass paths",
            "cross-framework semantic compatibility",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="compact deterministic JSON")
    args = parser.parse_args()
    report = run_suite()
    print(json.dumps(report, sort_keys=True) if args.json else json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
