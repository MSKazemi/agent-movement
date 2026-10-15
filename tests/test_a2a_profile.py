"""Dependency-free tests of the envelope <-> A2A profile mapping (always run)."""

import copy
import tempfile
import unittest
from pathlib import Path

from agent_movement.a2a_profile import (EXTENSION_URI, A2ACorrelationLog, ProfileError,
                                        a2a_to_envelope, envelope_to_a2a, receipt_to_artifact,
                                        safe_token, skill_id, verify_receipt)
from agent_movement.core import (Approval, ContractError, HandoffReceiver, SQLiteStore, canonical,
                                 digest)
from test_core import fixture


class ProfileMappingTests(unittest.TestCase):
    def test_round_trip_and_allowlisted_projection(self):
        mapped = envelope_to_a2a(fixture())
        self.assertEqual(mapped["context_id"], "task-1")
        self.assertEqual(set(mapped["data"]), {"kind", "text"})
        self.assertEqual(set(mapped["metadata"]), {
            "schema_version", "movement_id", "logical_task_id", "operation", "origin_agent_id",
            "destination_agent_id", "classification", "approval_ref", "idempotency_key",
            "trace_id", "envelope_digest"})
        self.assertNotIn("one two three", canonical(mapped["metadata"]))
        self.assertEqual(mapped["metadata"]["envelope_digest"], digest(fixture()))
        self.assertEqual(a2a_to_envelope(mapped["metadata"], mapped["data"], "task-1"), fixture())

    def test_provider_private_state_is_never_mapped(self):
        for where in (None, "task", "context", "origin"):
            with self.subTest(where=where):
                envelope = fixture()
                target = envelope if where is None else envelope[where]
                target["provider_state"] = {"session_token": "synthetic-not-a-secret"}
                with self.assertRaises(ContractError):
                    envelope_to_a2a(envelope)

    def test_receiver_side_rejections(self):
        mapped = envelope_to_a2a(fixture())
        cases = {
            "extra metadata": ({**mapped["metadata"], "provider_state": "x"}, mapped["data"], ""),
            "missing metadata": ({k: v for k, v in mapped["metadata"].items() if k != "trace_id"},
                                 mapped["data"], ""),
            "extra data": (mapped["metadata"], {**mapped["data"], "tool": "shell"}, ""),
            "unknown schema": ({**mapped["metadata"], "schema_version": "9.0"}, mapped["data"], ""),
            "unknown kind": (mapped["metadata"], {**mapped["data"], "kind": "shell"}, ""),
            "migration op": ({**mapped["metadata"], "operation": "relocate"}, mapped["data"], ""),
            "tampered text": (mapped["metadata"], {**mapped["data"], "text": "changed"}, ""),
            "context mismatch": (mapped["metadata"], mapped["data"], "other-task"),
            "not objects": ([], "text", ""),
        }
        for name, (metadata, data, context_id) in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(ContractError):
                    a2a_to_envelope(copy.deepcopy(metadata), copy.deepcopy(data), context_id)

    def test_skill_ids(self):
        self.assertEqual(skill_id("word_count"), "agent-movement.word_count")
        with self.assertRaises(ProfileError):
            skill_id("shell")


class ReceiptArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        store = SQLiteStore(Path(self.tmp.name) / "r.sqlite")
        receiver = HandoffReceiver("agent-b", store, [
            Approval("approval-1", "task-1", "agent-a", "agent-b", "word_count")])
        self.receipt = receiver.receive(fixture())

    def tearDown(self):
        self.tmp.cleanup()

    def widen(self, value):
        """Simulate protobuf Value: every JSON number arrives as a double."""
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return float(value)
        if isinstance(value, dict):
            return {k: self.widen(v) for k, v in value.items()}
        return value

    def test_artifact_round_trip_survives_number_widening(self):
        artifact = receipt_to_artifact(self.receipt)
        self.assertEqual(artifact["artifact_id"], "receipt-movement-1")
        self.assertNotIn("replayed", artifact["data"])
        verified = verify_receipt(fixture(), self.widen(artifact["data"]), artifact["metadata"])
        self.assertEqual(verified["artifact"], {"kind": "word_count", "value": 3})
        self.assertFalse(verified["replayed"])

    def test_receipt_for_another_envelope_is_refused(self):
        artifact = receipt_to_artifact(self.receipt)
        other = fixture()
        other["observability"]["trace_id"] = "trace-2"
        with self.assertRaises(ProfileError):
            verify_receipt(other, artifact["data"], artifact["metadata"])
        forged = {**artifact["data"], "artifact": {"kind": "word_count", "value": 4}}
        with self.assertRaises(ProfileError):
            verify_receipt(fixture(), forged, artifact["metadata"])
        with self.assertRaises(ProfileError):
            verify_receipt(fixture(), artifact["data"], {**artifact["metadata"], "extra": 1})


class CorrelationLogTests(unittest.TestCase):
    def test_ids_only_and_unsafe_ids_hashed(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = A2ACorrelationLog(Path(tmp) / "c.sqlite")
            log.record(message_id="m-1", outcome="completed", task_id="t-1", context_id="task-1",
                       envelope=fixture(), artifact_digest="abc")
            log.record(message_id="../../etc/passwd one two three", outcome="rejected.InvalidParamsError")
            rows = log.rows()
        self.assertEqual(rows[0]["movement_id"], "movement-1")
        self.assertEqual(rows[0]["envelope_digest"], digest(fixture()))
        self.assertTrue(rows[1]["a2a_message_id"].startswith("sha256:"))
        self.assertIsNone(rows[1]["a2a_task_id"])
        self.assertNotIn("one two three", canonical(rows))
        self.assertEqual(safe_token("abc-1"), "abc-1")
        self.assertTrue(EXTENSION_URI.startswith("urn:agent-movement:"))


if __name__ == "__main__":
    unittest.main()
