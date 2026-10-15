"""Regression tests for defects found in the PR #6 / #14 review (2026-10-16)."""
import contextlib
import gc
import io
import json
import socket
import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import warnings
from pathlib import Path

from agent_movement.core import (Approval, ContractError, EffectGateway, HandoffReceiver,
                                 SQLiteStore, parse_json, validate_envelope)
from agent_movement.http import make_server
from test_core import fixture


class MalformedInputIsContractError(unittest.TestCase):
    """parse_json/validate_envelope must only ever raise ContractError on bad input."""

    def test_int_over_digit_limit(self):
        with self.assertRaises(ContractError):
            parse_json(b'{"a":' + b"1" * 5000 + b"}")

    def test_deep_nesting(self):
        with self.assertRaises(ContractError):
            parse_json(b"[" * 16000)

    def test_lone_surrogate_text(self):
        envelope = fixture()
        envelope["task"]["text"] = "\ud800"
        with self.assertRaises(ContractError):
            validate_envelope(envelope)

    def test_lone_surrogate_effect_payload(self):
        with tempfile.TemporaryDirectory() as d:
            gateway = EffectGateway(SQLiteStore(Path(d) / "e.sqlite"))
            gateway.claim("task-1", "agent-a")
            with self.assertRaises(ContractError):
                gateway.commit("task-1", "agent-a", 1, "effect-1", "\ud800")


class HttpBoundary(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        store = SQLiteStore(Path(self.tmp.name) / "http.sqlite")
        approval = Approval("approval-1", "task-1", "agent-a", "agent-b", "word_count")
        self.receiver = HandoffReceiver("agent-b", store, [approval])
        self.server = make_server(self.receiver, read_timeout=0.5)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/v0/handoffs"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.tmp.cleanup()

    def send(self, data: bytes):
        request = urllib.request.Request(self.url, data=data,
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as exc:
            with exc:
                return exc.code, json.load(exc)

    def test_malformed_bodies_get_400_not_a_dropped_connection(self):
        surrogate = json.dumps({**fixture(), "task": {"kind": "word_count", "text": "\ud800"}})
        for body in (b'{"a":' + b"1" * 5000 + b"}", b"[" * 16000, surrogate.encode()):
            with self.subTest(body=body[:20]):
                self.assertEqual(self.send(body), (400, {"error": "invalid_contract"}))

    def test_unexpected_server_error_gets_500(self):
        def boom(_message):
            raise sqlite3.OperationalError("database is locked")
        self.receiver.receive = boom
        self.assertEqual(self.send(json.dumps(fixture()).encode()),
                         (500, {"error": "internal_error"}))

    def test_stalled_body_is_timed_out(self):
        with socket.create_connection(("127.0.0.1", self.server.server_port)) as s:
            s.sendall(b"POST /v0/handoffs HTTP/1.1\r\nHost: x\r\n"
                      b"Content-Type: application/json\r\nContent-Length: 100\r\n\r\n{")
            s.settimeout(5)
            start = time.monotonic()
            self.assertEqual(s.recv(100), b"")  # server closed the connection
            self.assertLess(time.monotonic() - start, 4)


if __name__ == "__main__":
    unittest.main()
