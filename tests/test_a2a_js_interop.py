"""Cross-SDK interop: an @a2a-js/sdk client completes a handoff against the Python server (issue #28).

The client is interop/js/handoff.mjs. It uses only the official JavaScript A2A SDK (exact pin in
interop/js/package.json and package-lock.json) and re-implements the profile mapping, the
canonical-JSON digests and the receipt check from docs/a2a-profile-extension.md.

Skipped cleanly unless all of these are available: the optional Python extra
(pip install -e '.[a2a]'), Node.js >= 20 on PATH, and the JS dependencies
(npm ci --prefix interop/js). Set A2A_INTEROP_REQUIRED=1 (the interop CI job does) to turn a
missing prerequisite into a failure instead of a skip.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from agent_movement.core import digest
from test_a2a_adapter import HAVE_A2A, _A2AServerCase, envelope

JS_DIR = Path(__file__).resolve().parents[1] / "interop" / "js"
CLIENT = JS_DIR / "handoff.mjs"
NODE = shutil.which("node")
REQUIRED = os.environ.get("A2A_INTEROP_REQUIRED") == "1"


def _node_major() -> int:
    try:
        done = subprocess.run([NODE, "--version"], capture_output=True, text=True, timeout=30)
        return int(done.stdout.strip().lstrip("v").split(".")[0])
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0


def missing_prerequisite() -> str:
    if not HAVE_A2A:
        return "optional A2A extra not installed (pip install -e '.[a2a]')"
    if NODE is None:
        return "node not found on PATH (Node.js >= 20 is needed for the @a2a-js/sdk interop client)"
    if _node_major() < 20:
        return "Node.js >= 20 is needed for the @a2a-js/sdk interop client"
    if not (JS_DIR / "node_modules" / "@a2a-js" / "sdk" / "package.json").is_file():
        return "JS dependencies not installed (npm ci --prefix interop/js)"
    return ""


MISSING = missing_prerequisite()


class A2AJsInteropPrerequisiteTests(unittest.TestCase):
    def test_prerequisites_present_when_required(self):
        if not REQUIRED:
            self.skipTest("A2A_INTEROP_REQUIRED is not set")
        self.assertEqual(MISSING, "", "A2A_INTEROP_REQUIRED=1 but: " + MISSING)


@unittest.skipIf(MISSING, MISSING or "prerequisites present")
class A2AJsInteropTests(_A2AServerCase):
    """Python a2a-sdk 1.2.2 server <-> @a2a-js/sdk client, over both A2A bindings."""

    def run_js(self, value, *args):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
            json.dump(value, handle)
        try:
            done = subprocess.run([NODE, str(CLIENT), "--url", self.url, "--envelope", handle.name, *args],
                                  capture_output=True, text=True, timeout=120, cwd=JS_DIR)
        finally:
            os.unlink(handle.name)
        self.assertTrue(done.stdout.strip(), "JS client printed nothing; stderr: " + done.stderr)
        return done.returncode, json.loads(done.stdout)

    def test_js_client_jsonrpc_streaming_handoff(self):
        value = envelope("movement-js-stream", "op-js-stream")
        code, result = self.run_js(value)
        self.assertEqual(code, 0, result)
        self.assertTrue(result["sdk"].startswith("@a2a-js/sdk "))
        self.assertEqual((result["binding"], result["streaming"]), ("JSONRPC", True))
        self.assertEqual(result["observed_states"],
                         ["TASK_STATE_SUBMITTED", "TASK_STATE_WORKING", "TASK_STATE_COMPLETED"])
        receipt = result["receipt"]
        self.assertEqual(receipt["artifact"], {"kind": "word_count", "value": 3})
        self.assertFalse(receipt["replayed"])
        # The JS canonical-JSON digest equals the Python one: both ends agree on the profile.
        self.assertEqual(receipt["envelope_digest"], digest(value))
        self.assertEqual(receipt["artifact_digest"], digest(receipt["artifact"]))
        rows = self.correlation(a2a_task_id=result["a2a_task_id"])
        self.assertEqual([(r["movement_id"], r["outcome"], r["a2a_message_id"], r["a2a_context_id"])
                          for r in rows],
                         [("movement-js-stream", "completed", result["a2a_message_id"],
                           result["a2a_context_id"])])

    def test_js_client_http_json_blocking_retry_is_replayed(self):
        value = envelope("movement-js-rest", "op-js-rest")
        code, first = self.run_js(value, "--binding", "HTTP+JSON", "--no-stream")
        self.assertEqual(code, 0, first)
        code, retry = self.run_js(value, "--binding", "HTTP+JSON", "--no-stream")
        self.assertEqual(code, 0, retry)
        self.assertEqual(first["binding"], "HTTP+JSON")
        self.assertEqual((first["receipt"]["replayed"], retry["receipt"]["replayed"]), (False, True))
        self.assertEqual(first["receipt"]["artifact_digest"], retry["receipt"]["artifact_digest"])
        self.assertNotEqual(first["a2a_task_id"], retry["a2a_task_id"])
        self.assertEqual(len(self.completed_movements("movement-js-rest")), 1)

    def test_js_client_sees_required_extension_error(self):
        code, result = self.run_js(envelope("movement-js-noext", "op-js-noext"), "--no-extension")
        self.assertEqual(code, 3)
        self.assertIn("ExtensionSupportRequired", result["error"]["type"])
        self.assertEqual(self.completed_movements("movement-js-noext"), [])

    def test_js_client_sees_rejected_task_for_unapproved_handoff(self):
        code, result = self.run_js(envelope("movement-js-denied", "op-js-denied", approval="not-approved"))
        self.assertEqual(code, 3)
        self.assertEqual(result["final_state"], "TASK_STATE_REJECTED")
        self.assertNotIn("receipt", result)


if __name__ == "__main__":
    unittest.main()
