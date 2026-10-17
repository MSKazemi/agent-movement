"""Actual legacy and official A2A listeners tested inside one broker-only UID profile.

The independent A2A process remains reachable to an unfenced root host. The
bounded claim is that the particular operator-owned unprivileged worker cannot
reach either live listener, not that the listeners are globally disabled.
"""
from __future__ import annotations

import json
import os
import threading
import unittest
import urllib.parse
import urllib.request
from pathlib import Path

from agent_movement.core import Approval, HandoffReceiver, SQLiteStore
from agent_movement.egress_sandbox import supported
from agent_movement.http import make_server
from agent_movement.secure_profile import load_operator_profile
from agent_movement.trust import HS256
from test_a2a_adapter import HAVE_A2A, SKIP_REASON, _A2AServerCase, envelope
from test_core import fixture
from test_peer import World
from test_secure_broker_profile import PROBE, manifest, save_evidence
from test_sender_gate import client


@unittest.skipUnless(
    HAVE_A2A and supported() and hasattr(os, "geteuid") and os.geteuid() == 0,
    SKIP_REASON + "; Linux x86_64 container-root supervisor required",
)
class TestBrokerProfileAgainstTwoActualListeners(_A2AServerCase):
    """The root-owned A2A server and legacy listener really execute during the test."""

    def test_actual_a2a_jsonrpc_rest_and_legacy_are_blocked_from_uid_worker(self):
        base = Path(self.tmp.name)
        profile = load_operator_profile(manifest(base / "operator-profile.json"))

        # Start an *independent*, intentionally unauthenticated legacy route.
        legacy = SQLiteStore(base / "legacy-route.sqlite")
        legacy_server = make_server(HandoffReceiver(
            "agent-b", legacy, [Approval("approval-1", "task-1", "agent-a", "agent-b", "word_count")],
        ))
        legacy_thread = threading.Thread(target=legacy_server.serve_forever, daemon=True)
        legacy_thread.start()
        try:
            # RED: independent unfenced clients can successfully use both
            # official-SDK A2A bindings and the real legacy HTTP handler.
            for binding, suffix in (("JSONRPC", "jsonrpc"), ("HTTP+JSON", "rest")):
                result = self.delegate(
                    envelope(f"movement-profile-{suffix}", f"op-profile-{suffix}"),
                    binding=binding, streaming=False,
                )
                self.assertEqual(result["final_state"], "TASK_STATE_COMPLETED")
                self.assertEqual(len(self.completed_movements(f"movement-profile-{suffix}")), 1)

            request = urllib.request.Request(
                f"http://127.0.0.1:{legacy_server.server_port}/v0/handoffs",
                data=json.dumps(fixture()).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=3) as response:
                self.assertEqual(response.status, 200)
            self.assertTrue(any(e["event_type"] == "handoff.accepted" for e in legacy.audit()))

            a2a_before = SQLiteStore(self.db).audit()
            legacy_before = legacy.audit()

            # GREEN: Two instances of the same untrusted UID worker probe both
            # REAL live ports while the trusted callback holds all authorities.
            # A2A JSON-RPC+REST are reached by the second worker's probe_port;
            # legacy HTTP by the first. This is not all-process isolation.
            world_dir = base / "trusted-world"
            world_dir.mkdir()
            world = World(HS256, world_dir)
            callback = {"task-1": lambda: world.handoff(client=client(world))["effect"]}
            legacy_probe = profile.run(PROBE, callback, probe_port=legacy_server.server_port,
                                       effect_store=world.store)
            a2a_port = urllib.parse.urlsplit(self.url).port
            self.assertIsNotNone(a2a_port)
            a2a_probe = profile.run(PROBE, callback, probe_port=a2a_port,
                                    effect_store=world.store)

            for result in (legacy_probe, a2a_probe):
                self.assertEqual(result.exit_code, 0, result.stderr)
                self.assertEqual(result.request_count, 1)
                self.assertIn(result.broker_status, ("committed", "replayed"))
                observation = json.loads(result.stdout)
                self.assertEqual(observation["uid"], 65534)
                self.assertEqual(observation["gid"], 65534)
                for route in ("legacy_http", "a2a_jsonrpc", "a2a_rest",
                              "peer_preflight", "tool_service", "tcp", "udp", "unix", "spawn"):
                    self.assertEqual(observation[route], "blocked", (route, observation))

            # Verify from the listener-owned SQLite stores, not the worker's
            # own statement that a syscall was denied.
            self.assertEqual(SQLiteStore(self.db).audit(), a2a_before)
            self.assertEqual(legacy.audit(), legacy_before)
            self.assertEqual(len(world.receiver.ledger.effects()), 1)
            save_evidence("profile-live-a2a", {
                "scope": "two live listener ports, only the UID-fenced worker",
                "unfenced_legacy_accepted": True,
                "unfenced_a2a_jsonrpc_accepted": True,
                "unfenced_a2a_rest_accepted": True,
                "worker_legacy_blocked": True,
                "worker_a2a_jsonrpc_blocked": True,
                "worker_a2a_rest_blocked": True,
                "independent_legacy_audit_unchanged": True,
                "independent_a2a_audit_unchanged": True,
                "trusted_peer_effect_count": 1,
            })
        finally:
            legacy_server.shutdown()
            legacy_server.server_close()
            legacy_thread.join(timeout=5)
