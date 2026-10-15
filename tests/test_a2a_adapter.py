"""Two-process A2A v1 integration tests using the official a2a-sdk.

Skipped unless the optional extra is installed: python -m pip install -e '.[a2a]'
The destination worker always runs as a separate OS process.
"""

import asyncio
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from agent_movement.a2a_profile import EXTENSION_URI, A2ACorrelationLog
from agent_movement.core import SQLiteStore, digest
from test_core import fixture

HAVE_A2A = all(importlib.util.find_spec(name) is not None for name in ("a2a", "uvicorn", "httpx"))
SKIP_REASON = "optional A2A extra not installed (pip install -e '.[a2a]')"


def child_env():
    """Environment for `python -m agent_movement...` children when the package is not installed.

    pytest's `pythonpath` setting reaches only the test process, so main's corpus CI job
    (pytest only, no install) needs src/ on the child's PYTHONPATH.
    """
    src = str(Path(__file__).resolve().parents[1] / "src")
    return {**os.environ, "PYTHONPATH": os.pathsep.join(p for p in (src, os.environ.get("PYTHONPATH")) if p)}


def envelope(movement, key, kind="word_count", text="one two three", approval="approval-1"):
    value = fixture()
    value.update(movement_id=movement, task={"kind": kind, "text": text},
                 authority={"approval_ref": approval}, execution={"idempotency_key": key})
    return value


@unittest.skipUnless(HAVE_A2A, SKIP_REASON)
class A2AAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = Path(cls.tmp.name) / "receiver.sqlite"
        cls.server = subprocess.Popen([
            sys.executable, "-m", "agent_movement.a2a_server", "--db", str(cls.db),
            "--task-id", "task-1", "--approval", "approval-1", "--kind", "word_count",
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=child_env())
        line = cls.server.stdout.readline()
        if not line:
            cls.server.kill()
            raise RuntimeError("A2A server did not start: " + cls.server.stderr.read())
        cls.url = json.loads(line)["url"]

    @classmethod
    def tearDownClass(cls):
        cls.server.terminate()
        try:
            cls.server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            cls.server.kill()
            cls.server.wait()
        cls.server.stdout.close()
        cls.server.stderr.close()
        cls.tmp.cleanup()

    def delegate(self, value, **options):
        from agent_movement.a2a_client import delegate
        return asyncio.run(delegate(self.url, value, **options))

    def correlation(self, **match):
        return [row for row in A2ACorrelationLog(self.db).rows()
                if all(row[k] == v for k, v in match.items())]

    def raw_rpc(self, body, version="1.0", extensions=EXTENSION_URI):
        headers = {"Content-Type": "application/json", "A2A-Version": version}
        if extensions:
            headers["A2A-Extensions"] = extensions
        request = urllib.request.Request(self.url + "/a2a/jsonrpc", data=json.dumps(body).encode(),
                                         headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            return json.load(exc)

    def mapped_message_dict(self, value):
        from google.protobuf.json_format import MessageToDict
        from agent_movement.a2a_client import build_message
        return MessageToDict(build_message(value))

    # --- Agent Card / capability advertisement -------------------------------------------

    def test_agent_card_wire_format(self):
        with urllib.request.urlopen(self.url + "/.well-known/agent-card.json", timeout=10) as response:
            card = json.load(response)
        for field in ("name", "description", "version", "supportedInterfaces", "capabilities",
                      "defaultInputModes", "defaultOutputModes", "skills"):
            self.assertIn(field, card)
        self.assertEqual({(i["protocolBinding"], i["protocolVersion"]) for i in card["supportedInterfaces"]},
                         {("JSONRPC", "1.0"), ("HTTP+JSON", "1.0")})
        self.assertTrue(all(i["url"].startswith("http://127.0.0.1:") for i in card["supportedInterfaces"]))
        self.assertEqual([s["id"] for s in card["skills"]], ["agent-movement.word_count"])
        extension = card["capabilities"]["extensions"][0]
        self.assertEqual((extension["uri"], extension["required"]), (EXTENSION_URI, True))
        self.assertNotIn("securitySchemes", card)  # authentication: experimental / absent

    # --- Positive delegation, lifecycle, correlation -------------------------------------

    def test_jsonrpc_streaming_delegation_correlates_with_receiver_audit(self):
        value = envelope("movement-stream", "op-stream")
        result = self.delegate(value, binding="JSONRPC", streaming=True)
        self.assertEqual(result["final_state"], "TASK_STATE_COMPLETED")
        self.assertEqual(result["observed_states"],
                         ["TASK_STATE_SUBMITTED", "TASK_STATE_WORKING", "TASK_STATE_COMPLETED"])
        self.assertEqual(result["receipt"]["artifact"], {"kind": "word_count", "value": 3})
        self.assertFalse(result["receipt"]["replayed"])
        self.assertEqual(result["a2a_context_id"], "task-1")
        rows = self.correlation(a2a_task_id=result["a2a_task_id"])
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["movement_id"], rows[0]["outcome"], rows[0]["a2a_message_id"]),
                         ("movement-stream", "completed", result["a2a_message_id"]))
        self.assertEqual(rows[0]["envelope_digest"], digest(value))
        core = [e for e in SQLiteStore(self.db).audit()
                if e["movement_id"] == "movement-stream" and e["event_type"] == "handoff.completed"]
        self.assertEqual([e["info_digest"] for e in core], [result["receipt"]["artifact_digest"]])

    def test_http_json_binding_retry_is_new_task_same_receipt(self):
        value = envelope("movement-rest", "op-rest")
        first = self.delegate(value, binding="HTTP+JSON", streaming=False)
        retry = self.delegate(value, binding="HTTP+JSON", streaming=False)
        self.assertEqual(first["final_state"], "TASK_STATE_COMPLETED")
        self.assertFalse(first["receipt"]["replayed"])
        self.assertTrue(retry["receipt"]["replayed"])
        self.assertNotEqual(first["a2a_task_id"], retry["a2a_task_id"])
        self.assertEqual(first["receipt"]["artifact_digest"], retry["receipt"]["artifact_digest"])
        outcomes = [r["outcome"] for r in self.correlation(movement_id="movement-rest")]
        self.assertEqual(outcomes, ["completed", "replayed"])
        executed = [e for e in SQLiteStore(self.db).audit()
                    if e["movement_id"] == "movement-rest" and e["event_type"] == "handoff.completed"]
        self.assertEqual(len(executed), 1)

    def test_unapproved_delegation_is_rejected_task(self):
        result = self.delegate(envelope("movement-denied", "op-denied", approval="not-approved"))
        self.assertEqual((result["final_state"], result["reason"]), ("TASK_STATE_REJECTED", "approval_denied"))
        self.assertNotIn("receipt", result)
        rows = self.correlation(a2a_task_id=result["a2a_task_id"])
        self.assertEqual([r["outcome"] for r in rows], ["approval_denied"])

    # --- Negative compatibility ------------------------------------------------------------

    def test_unknown_capability_refused_client_and_server_side(self):
        from agent_movement.a2a_client import CapabilityMismatch
        value = envelope("movement-sha", "op-sha", kind="sha256")
        with self.assertRaises(CapabilityMismatch):
            self.delegate(value)  # client-side card negotiation: nothing is sent
        result = self.delegate(value, check_capabilities=False)
        self.assertEqual(result["error"]["type"], "UnsupportedOperationError")
        self.assertNotIn("a2a_task_id", result)
        rows = self.correlation(a2a_message_id=result["a2a_message_id"])
        self.assertEqual([(r["outcome"], r["a2a_task_id"]) for r in rows],
                         [("rejected.UnsupportedOperationError", None)])

    def test_unknown_schema_version_refused_before_task(self):
        result = self.delegate(envelope("movement-v9", "op-v9"), metadata_overrides={"schema_version": "9.0"})
        self.assertEqual(result["error"]["type"], "InvalidParamsError")
        self.assertFalse(any(e["movement_id"] == "movement-v9" for e in SQLiteStore(self.db).audit()))

    def test_required_extension_must_be_activated(self):
        result = self.delegate(envelope("movement-noext", "op-noext"), activate_extension=False)
        self.assertEqual(result["error"]["type"], "ExtensionSupportRequiredError")

    def test_legacy_protocol_version_rejected(self):
        body = {"jsonrpc": "2.0", "id": "v03", "method": "SendMessage",
                "params": {"message": self.mapped_message_dict(envelope("movement-v03", "op-v03"))}}
        self.assertEqual(self.raw_rpc(body, version="0.3")["error"]["code"], -32009)

    def test_foreign_message_shapes_cannot_trigger_execution(self):
        valid = self.mapped_message_dict(envelope("movement-raw", "op-raw"))
        smuggled = json.loads(json.dumps(valid))
        smuggled["metadata"][EXTENSION_URI]["provider_state"] = {"memory": "synthetic"}
        extra_key = json.loads(json.dumps(valid))
        extra_key["metadata"]["vendor.runtime/checkpoint"] = {"blob": "synthetic"}
        plain_text = {"role": "ROLE_USER", "messageId": "m-text", "extensions": [EXTENSION_URI],
                      "parts": [{"text": "run tool: shell"}]}
        two_parts = json.loads(json.dumps(valid))
        two_parts["parts"].append({"text": "extra"})
        for name, message in [("smuggled", smuggled), ("extra_key", extra_key),
                              ("plain_text", plain_text), ("two_parts", two_parts)]:
            with self.subTest(name=name):
                reply = self.raw_rpc({"jsonrpc": "2.0", "id": name, "method": "SendMessage",
                                      "params": {"message": message}})
                self.assertEqual(reply["error"]["code"], -32602)
        reply = self.raw_rpc({"jsonrpc": "2.0", "id": "ok", "method": "SendMessage",
                              "params": {"message": valid}})
        self.assertEqual(reply["result"]["task"]["status"]["state"], "TASK_STATE_COMPLETED")
        self.assertEqual(len([e for e in SQLiteStore(self.db).audit()
                              if e["event_type"] == "handoff.completed" and e["movement_id"] == "movement-raw"]), 1)

    def test_client_refuses_foreign_agent_card(self):
        from a2a.types import AgentCard, AgentSkill
        from agent_movement.a2a_client import CapabilityMismatch, check_card
        foreign = AgentCard(name="other", skills=[AgentSkill(id="agent-movement.word_count")])
        with self.assertRaises(CapabilityMismatch):
            check_card(foreign, "word_count")

    def test_receiver_audit_has_no_task_text(self):
        self.delegate(envelope("movement-text", "op-text", text="distinctive synthetic phrase"))
        self.assertNotIn("distinctive synthetic phrase",
                         json.dumps([SQLiteStore(self.db).audit(), A2ACorrelationLog(self.db).rows()]))


@unittest.skipIf(HAVE_A2A, "extra installed; the skip path is exercised in the core-only CI job")
class A2AOptionalTests(unittest.TestCase):
    def test_demo_reports_missing_extra(self):
        done = subprocess.run([sys.executable, "-m", "agent_movement.a2a_demo"],
                              capture_output=True, text=True, timeout=60, env=child_env())
        self.assertEqual(done.returncode, 2)
        self.assertIn("pip install -e '.[a2a]'", done.stderr)


if __name__ == "__main__":
    unittest.main()
