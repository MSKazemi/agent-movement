"""Actual legacy/A2A listener reachability under the Linux experimental egress fence.

Unlike the generic '/legacy' and '/a2a' labels in egress_experiment, the
test starts real application handlers. It does NOT make those handlers
authenticated, close OS filesystem/IPC routes, or establish universal
complete mediation: Issue #50 remains open.
"""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.parse
import urllib.request
from pathlib import Path

from agent_movement.core import Approval, HandoffReceiver, SQLiteStore
from agent_movement.egress_lab import run_guarded_agent
from agent_movement.egress_sandbox import supported
from agent_movement.http import make_server
from test_a2a_adapter import HAVE_A2A, SKIP_REASON, _A2AServerCase, envelope
from test_core import fixture

PROBE = Path(__file__).resolve().parents[1] / "src/agent_movement/real_adapter_probe.py"
ROUTES = ("legacy_http", "a2a_http", "peer_http")


def _probe_actual_listener(port: int) -> dict[str, str]:
    """A limited child cannot reach any direct adapter path; the parent owns the broker."""
    result = run_guarded_agent(
        PROBE, {"task-1": lambda: "committed"}, probe_port=port,
    )
    assert result.exit_code == 0, result.stderr
    assert result.request_count == 1
    assert result.broker_status == "committed"
    observed = json.loads(result.stdout)
    assert set(observed) == {*ROUTES, "broker"}
    assert observed["broker"] == "committed"
    for route in ROUTES:
        assert observed[route] == "blocked", (route, observed)
    return observed


class TestActualLegacyAdapterBoundary(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = SQLiteStore(Path(self.tmp.name) / "legacy.sqlite")
        approval = Approval("approval-1", "task-1", "agent-a", "agent-b", "word_count")
        self.server = make_server(HandoffReceiver("agent-b", self.store, [approval]))
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=5)
        self.tmp.cleanup()

    def test_unfenced_real_legacy_accepts_self_declared_origin(self) -> None:
        # Positive observation control: the actual legacy HTTP listener is reachable.
        # It has no peer signature: a matching self-declared identity is sufficient
        # under a receiver-local approval. This is NOT a secure movement route.
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.server.server_port}/v0/handoffs",
            data=json.dumps(fixture()).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(json.load(response)["artifact"]["value"], 3)
        self.assertEqual(
            [e["event_type"] for e in self.store.audit() if e["movement_id"] == "movement-1"],
            ["handoff.accepted", "handoff.completed"],
        )

    @unittest.skipUnless(supported(), "Linux x86_64 seccomp required for actual-listener egress test")
    def test_fenced_child_cannot_post_to_actual_legacy_listener(self) -> None:
        before = self.store.audit()
        _probe_actual_listener(self.server.server_port)
        # Read from the receiver's durable audit DB, not from the child's claimed output.
        self.assertEqual(self.store.audit(), before)


@unittest.skipUnless(HAVE_A2A and supported(), SKIP_REASON + "; Linux x86_64 seccomp required")
class TestActualA2AAdapterBoundary(_A2AServerCase):
    def test_fenced_child_cannot_post_to_actual_a2a_listener(self) -> None:
        # Real official-SDK positive control (and public Agent Card), not a fake
        # HTTP listener that merely responds to a path called '/a2a'.
        value = envelope("movement-live-adapter-control", "op-live-adapter-control")
        result = self.delegate(value)
        self.assertEqual(result["final_state"], "TASK_STATE_COMPLETED")
        self.assertEqual(len(self.completed_movements("movement-live-adapter-control")), 1)
        before = SQLiteStore(self.db).audit()
        port = urllib.parse.urlsplit(self.url).port
        self.assertIsNotNone(port)
        _probe_actual_listener(port)
        self.assertEqual(SQLiteStore(self.db).audit(), before)
