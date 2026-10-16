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

from agent_movement.a2a_profile import (CLIENT_CONTEXT_BOUND, EXTENSION_URI, LEGACY_EXTENSION_URI,
                                        PROFILE_VERSION, A2ACorrelationLog)
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


class _A2AServerCase(unittest.TestCase):
    """Starts one destination worker process per test class (no test methods of its own)."""

    SERVER_ARGS: tuple[str, ...] = ()

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = Path(cls.tmp.name) / "receiver.sqlite"
        cls.server = subprocess.Popen([
            sys.executable, "-m", "agent_movement.a2a_server", "--db", str(cls.db),
            "--task-id", "task-1", "--approval", "approval-1", "--kind", "word_count",
            *cls.SERVER_ARGS,
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

    def mapped_message_dict(self, value, **options):
        from google.protobuf.json_format import MessageToDict
        from agent_movement.a2a_client import build_message
        return MessageToDict(build_message(value, **options))

    def card(self):
        with urllib.request.urlopen(self.url + "/.well-known/agent-card.json", timeout=10) as response:
            return json.load(response)

    def completed_movements(self, movement_id):
        return [e for e in SQLiteStore(self.db).audit()
                if e["movement_id"] == movement_id and e["event_type"] == "handoff.completed"]


@unittest.skipUnless(HAVE_A2A, SKIP_REASON)
class A2AAdapterTests(_A2AServerCase):
    """Default server: server-generated contextId; a client-supplied one is rejected."""

    # --- Agent Card / capability advertisement -------------------------------------------

    def test_agent_card_wire_format(self):
        card = self.card()
        for field in ("name", "description", "version", "supportedInterfaces", "capabilities",
                      "defaultInputModes", "defaultOutputModes", "skills"):
            self.assertIn(field, card)
        self.assertEqual({(i["protocolBinding"], i["protocolVersion"]) for i in card["supportedInterfaces"]},
                         {("JSONRPC", "1.0"), ("HTTP+JSON", "1.0")})
        self.assertTrue(all(i["url"].startswith("http://127.0.0.1:") for i in card["supportedInterfaces"]))
        self.assertEqual([s["id"] for s in card["skills"]], ["agent-movement.word_count"])
        self.assertNotIn("securitySchemes", card)  # authentication: experimental / absent

    def test_agent_card_advertises_resolvable_profile_uri_and_deprecated_alias(self):
        extensions = self.card()["capabilities"]["extensions"]
        self.assertEqual([(e["uri"], e.get("required", False)) for e in extensions],
                         [(EXTENSION_URI, True), (LEGACY_EXTENSION_URI, False)])
        self.assertTrue(EXTENSION_URI.startswith("https://github.com/MSKazemi/agent-movement/blob/main/"))
        params = extensions[0]["params"]
        self.assertEqual((params["profile_version"], params["context_id"], params["client_context_id"],
                          params["deprecated_aliases"]),
                         (PROFILE_VERSION, "server-generated", "rejected", [LEGACY_EXTENSION_URI]))
        self.assertEqual((extensions[1]["params"]["deprecated"], extensions[1]["params"]["replaced_by"]),
                         (True, EXTENSION_URI))
        self.assertIn("DEPRECATED", extensions[1]["description"])

    # --- Positive delegation, lifecycle, correlation -------------------------------------

    def test_jsonrpc_streaming_delegation_correlates_with_receiver_audit(self):
        value = envelope("movement-stream", "op-stream")
        result = self.delegate(value, binding="JSONRPC", streaming=True)
        self.assertEqual(result["final_state"], "TASK_STATE_COMPLETED")
        self.assertEqual(result["observed_states"],
                         ["TASK_STATE_SUBMITTED", "TASK_STATE_WORKING", "TASK_STATE_COMPLETED"])
        self.assertEqual(result["receipt"]["artifact"], {"kind": "word_count", "value": 3})
        self.assertFalse(result["receipt"]["replayed"])
        self.assertEqual(result["context_id_source"], "server")
        rows = self.correlation(a2a_task_id=result["a2a_task_id"])
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["movement_id"], rows[0]["outcome"], rows[0]["a2a_message_id"],
                          rows[0]["a2a_context_id"]),
                         ("movement-stream", "completed", result["a2a_message_id"], result["a2a_context_id"]))
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

    # --- contextId policy (A2A v1.0 sec. 3.4.1) ----------------------------------------------

    def test_context_id_is_server_generated_by_default(self):
        self.assertNotIn("contextId", self.mapped_message_dict(envelope("movement-ctx0", "op-ctx0")))
        first = self.delegate(envelope("movement-ctx1", "op-ctx1"))
        second = self.delegate(envelope("movement-ctx2", "op-ctx2"), binding="HTTP+JSON", streaming=False)
        for result in (first, second):
            self.assertEqual((result["final_state"], result["context_id_source"]),
                             ("TASK_STATE_COMPLETED", "server"))
            self.assertTrue(result["a2a_context_id"])
            self.assertNotEqual(result["a2a_context_id"], "task-1")  # not derived from the logical task
            rows = self.correlation(a2a_task_id=result["a2a_task_id"])
            self.assertEqual([r["a2a_context_id"] for r in rows], [result["a2a_context_id"]])
        self.assertNotEqual(first["a2a_context_id"], second["a2a_context_id"])

    def test_client_context_id_refused_unless_server_opts_in(self):
        from agent_movement.a2a_client import CapabilityMismatch
        value = envelope("movement-ctx-client", "op-ctx-client")
        with self.assertRaisesRegex(CapabilityMismatch, "client-supplied context IDs"):
            self.delegate(value, context_id="task-1")  # the card says "rejected": nothing is sent
        result = self.delegate(value, context_id="task-1", check_capabilities=False)
        self.assertEqual(result["error"]["type"], "InvalidParamsError")
        self.assertIn("client-supplied contextId is not accepted", result["error"]["message"])
        self.assertEqual([(r["outcome"], r["a2a_task_id"])
                          for r in self.correlation(a2a_message_id=result["a2a_message_id"])],
                         [("rejected.InvalidParamsError", None)])
        self.assertEqual(self.completed_movements("movement-ctx-client"), [])

    # --- Deprecated URN alias (profile 0.1), accepted for one profile version ------------------

    def test_deprecated_urn_alias_keeps_profile_01_behaviour(self):
        value = envelope("movement-legacy", "op-legacy")
        result = self.delegate(value, extension_uri=LEGACY_EXTENSION_URI, context_id="task-1")
        self.assertEqual((result["final_state"], result["a2a_context_id"], result["extension_uri"]),
                         ("TASK_STATE_COMPLETED", "task-1", LEGACY_EXTENSION_URI))
        self.assertEqual(result["receipt"]["movement_id"], "movement-legacy")  # verified under the URN key
        mismatch = self.delegate(envelope("movement-legacy-x", "op-legacy-x"),
                                 extension_uri=LEGACY_EXTENSION_URI, context_id="other-task")
        self.assertEqual(mismatch["error"]["type"], "InvalidParamsError")
        self.assertIn("does not match logical task ID", mismatch["error"]["message"])
        generated = self.delegate(envelope("movement-legacy-g", "op-legacy-g"),
                                  extension_uri=LEGACY_EXTENSION_URI)
        self.assertEqual(generated["context_id_source"], "server")
        self.assertNotEqual(generated["a2a_context_id"], "task-1")

    def test_profile_01_wire_message_is_still_accepted(self):
        # Exactly what the profile 0.1 client sent: URN header, URN-keyed metadata, contextId = task.
        message = self.mapped_message_dict(envelope("movement-v01", "op-v01"),
                                           extension_uri=LEGACY_EXTENSION_URI, context_id="task-1")
        reply = self.raw_rpc({"jsonrpc": "2.0", "id": "v01", "method": "SendMessage",
                              "params": {"message": message}}, extensions=LEGACY_EXTENSION_URI)
        task = reply["result"]["task"]
        self.assertEqual((task["status"]["state"], task["contextId"]), ("TASK_STATE_COMPLETED", "task-1"))
        self.assertEqual(task["artifacts"][0]["extensions"], [LEGACY_EXTENSION_URI])
        self.assertEqual(set(task["artifacts"][0]["metadata"]), {LEGACY_EXTENSION_URI})

    def test_profile_uri_must_match_activation_and_be_unique(self):
        new_uri_message = self.mapped_message_dict(envelope("movement-uri1", "op-uri1"))
        both = json.loads(json.dumps(new_uri_message))
        both["extensions"] = [EXTENSION_URI, LEGACY_EXTENSION_URI]
        foreign = json.loads(json.dumps(new_uri_message))
        foreign["extensions"] = ["urn:example:other-profile"]
        cases = [("activated alias, declared new URI", new_uri_message, LEGACY_EXTENSION_URI),
                 ("two profile URIs", both, f"{EXTENSION_URI},{LEGACY_EXTENSION_URI}"),
                 ("foreign profile URI", foreign, EXTENSION_URI)]
        for name, message, header in cases:
            with self.subTest(name=name):
                reply = self.raw_rpc({"jsonrpc": "2.0", "id": name, "method": "SendMessage",
                                      "params": {"message": message}}, extensions=header)
                self.assertEqual(reply["error"]["code"], -32602)
        reply = self.raw_rpc({"jsonrpc": "2.0", "id": "foreign-only", "method": "SendMessage",
                              "params": {"message": foreign}}, extensions="urn:example:other-profile")
        self.assertEqual(reply["error"]["code"], -32008)  # required profile not activated
        self.assertEqual(self.completed_movements("movement-uri1"), [])


@unittest.skipUnless(HAVE_A2A, SKIP_REASON)
class A2AClientContextOptInTests(_A2AServerCase):
    """Server started with --accept-client-context-id (opt-in, bound to logical_task_id)."""

    SERVER_ARGS = ("--accept-client-context-id",)

    def test_card_advertises_opt_in(self):
        params = self.card()["capabilities"]["extensions"][0]["params"]
        self.assertEqual((params["context_id"], params["client_context_id"]),
                         ("server-generated", CLIENT_CONTEXT_BOUND))

    def test_bound_client_context_id_is_accepted_and_preserved(self):
        result = self.delegate(envelope("movement-optin", "op-optin"), context_id="task-1")
        self.assertEqual((result["final_state"], result["a2a_context_id"], result["context_id_source"]),
                         ("TASK_STATE_COMPLETED", "task-1", "client"))
        rows = self.correlation(a2a_task_id=result["a2a_task_id"])
        self.assertEqual([(r["outcome"], r["a2a_context_id"]) for r in rows], [("completed", "task-1")])

    def test_unbound_client_context_id_is_rejected(self):
        result = self.delegate(envelope("movement-optin-x", "op-optin-x"), context_id="other-task")
        self.assertEqual(result["error"]["type"], "InvalidParamsError")
        self.assertIn("does not match logical task ID", result["error"]["message"])
        self.assertEqual(self.completed_movements("movement-optin-x"), [])

    def test_server_generated_context_remains_the_default(self):
        result = self.delegate(envelope("movement-optin-g", "op-optin-g"))
        self.assertEqual((result["final_state"], result["context_id_source"]),
                         ("TASK_STATE_COMPLETED", "server"))
        self.assertNotEqual(result["a2a_context_id"], "task-1")


@unittest.skipIf(HAVE_A2A, "extra installed; the skip path is exercised in the core-only CI job")
class A2AOptionalTests(unittest.TestCase):
    def test_demo_reports_missing_extra(self):
        done = subprocess.run([sys.executable, "-m", "agent_movement.a2a_demo"],
                              capture_output=True, text=True, timeout=60, env=child_env())
        self.assertEqual(done.returncode, 2)
        self.assertIn("pip install -e '.[a2a]'", done.stderr)


if __name__ == "__main__":
    unittest.main()
