import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from agent_movement.core import Approval, HandoffReceiver, SQLiteStore
from agent_movement.http import make_server
from test_core import fixture


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = SQLiteStore(Path(self.tmp.name) / "http.sqlite")
        approval = Approval("approval-1", "task-1", "agent-a", "agent-b", "word_count")
        self.server = make_server(HandoffReceiver("agent-b", self.store, [approval]))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/v0/handoffs"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.tmp.cleanup()

    def send(self, data, content_type="application/json"):
        if not isinstance(data, bytes):
            data = json.dumps(data).encode("utf-8")
        request = urllib.request.Request(self.url, data=data, headers={"Content-Type": content_type})
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as exc:
            return exc.code, json.load(exc)

    def test_success_replay_and_denial(self):
        first = self.send(fixture())
        replay = self.send(fixture())
        self.assertEqual(first[0], 200)
        self.assertEqual(first[1]["artifact"]["value"], 3)
        self.assertFalse(first[1]["replayed"])
        self.assertTrue(replay[1]["replayed"])
        denied = fixture()
        denied["authority"]["approval_ref"] = "unauthorized"
        self.assertEqual(self.send(denied)[0], 403)

    def test_strict_protocol_errors(self):
        self.assertEqual(self.send(fixture(), "text/plain")[0], 415)
        self.assertEqual(self.send(b'{"x":1,"x":2}')[0], 400)
        self.assertEqual(self.send(b'not json')[0], 400)
        self.assertEqual(self.send(b' ' * 16385)[0], 413)
        bad = fixture()
        bad["operation"] = "relocate"
        self.assertEqual(self.send(bad)[0], 400)

    def test_conflict(self):
        self.assertEqual(self.send(fixture())[0], 200)
        changed = fixture()
        changed["task"]["text"] = "colliding content"
        self.assertEqual(self.send(changed)[0], 409)

    def test_binds_loopback_only(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
