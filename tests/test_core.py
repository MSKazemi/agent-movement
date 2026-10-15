import concurrent.futures
import copy
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent_movement.core import (SCHEMA_VERSION, Approval, Conflict, ContractError,
                                 EffectGateway, HandoffReceiver, PolicyDenied, SQLiteStore,
                                 canonical, digest, parse_json, validate_envelope)


def fixture():
    return {
        "schema_version": SCHEMA_VERSION, "movement_id": "movement-1",
        "logical_task_id": "task-1", "operation": "delegate",
        "origin": {"agent_id": "agent-a"}, "destination": {"agent_id": "agent-b"},
        "task": {"kind": "word_count", "text": "one two three"},
        "context": {"classification": "synthetic"},
        "authority": {"approval_ref": "approval-1"},
        "execution": {"idempotency_key": "op-1"},
        "observability": {"trace_id": "trace-1"},
    }


class ContractTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(validate_envelope(fixture())["task"]["kind"], "word_count")
        self.assertEqual(digest({"a": 1, "b": 2}), digest({"b": 2, "a": 1}))

    def test_bad_contracts(self):
        for path, value in [
            (("schema_version",), "9.0"), (("operation",), "relocate"),
            (("movement_id",), "../../secrets"), (("context", "classification"), "private"),
            (("task", "kind"), "shell"), (("task", "text"), "x" * 2049),
            (("destination", "agent_id"), ""),
        ]:
            with self.subTest(path=path):
                envelope = fixture()
                current = envelope
                for item in path[:-1]:
                    current = current[item]
                current[path[-1]] = value
                with self.assertRaises(ContractError):
                    validate_envelope(envelope)
        envelope = fixture()
        envelope["secrets"] = "never"
        with self.assertRaises(ContractError):
            validate_envelope(envelope)
        with self.assertRaises(ContractError):
            validate_envelope([])

    def test_duplicate_json_field_and_invalid_numbers(self):
        with self.assertRaises(ContractError):
            parse_json(b'{"a":1,"a":2}')
        with self.assertRaises(ContractError):
            parse_json(b'{"a":NaN}')
        with self.assertRaises(ContractError):
            parse_json(b'not json')


class ReceiverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = SQLiteStore(Path(self.tmp.name) / "receiver.sqlite")
        self.approval = Approval("approval-1", "task-1", "agent-a", "agent-b", "word_count")
        self.receiver = HandoffReceiver("agent-b", self.store, [self.approval])

    def tearDown(self):
        self.tmp.cleanup()

    def test_receipt_and_idempotent_replay(self):
        first = self.receiver.receive(fixture())
        second = self.receiver.receive(fixture())
        self.assertEqual(first["artifact"], {"kind": "word_count", "value": 3})
        self.assertEqual(first["artifact_digest"], digest(first["artifact"]))
        self.assertFalse(first["replayed"])
        self.assertTrue(second["replayed"])
        self.assertEqual(len(self.store.audit()), 2)
        self.assertEqual([x["event_type"] for x in self.store.audit()],
                         ["handoff.accepted", "handoff.completed"])
        self.assertFalse(any("one two three" in canonical(x) for x in self.store.audit()))

    def test_wrong_approvals_denied_before_execution(self):
        for change in [
            {"authority": {"approval_ref": "other"}},
            {"origin": {"agent_id": "evil"}},
            {"destination": {"agent_id": "other"}},
            {"context": {"classification": "public"}},
            {"logical_task_id": "another-task"},
        ]:
            with self.subTest(change=change):
                with self.assertRaises(PolicyDenied):
                    self.receiver.receive({**fixture(), **change})
        self.assertEqual(len(self.store.audit()), 5)
        self.assertTrue(all(x["event_type"] == "handoff.denied" for x in self.store.audit()))

    def test_expiry_and_revocation(self):
        old = datetime.now(timezone.utc) - timedelta(seconds=1)
        for approval in [Approval("approval-1", "task-1", "agent-a", "agent-b", "word_count", expires_at=old),
                         Approval("approval-1", "task-1", "agent-a", "agent-b", "word_count", revoked=True)]:
            with self.subTest(approval=approval):
                with self.assertRaises(PolicyDenied):
                    HandoffReceiver("agent-b", self.store, [approval]).receive(fixture())

    def test_idempotency_key_collision(self):
        self.receiver.receive(fixture())
        changed = fixture()
        changed["task"]["text"] = "DIFFERENT INPUT"
        with self.assertRaises(Conflict):
            self.receiver.receive(changed)
        self.assertEqual(len(self.store.audit()), 2)

    def test_movement_id_cannot_be_reused_with_different_key(self):
        self.receiver.receive(fixture())
        other = fixture()
        other["execution"]["idempotency_key"] = "other-key"
        with self.assertRaises(Conflict):
            self.receiver.receive(other)

    def test_concurrent_deliveries_one_execution(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            outcomes = list(pool.map(self.receiver.receive, [fixture() for _ in range(25)]))
        self.assertEqual(sum(not x["replayed"] for x in outcomes), 1)
        self.assertEqual(len(self.store.audit()), 2)

    def test_receipt_persists_reopen(self):
        self.receiver.receive(fixture())
        reopened = HandoffReceiver("agent-b", SQLiteStore(Path(self.tmp.name) / "receiver.sqlite"), [self.approval])
        self.assertTrue(reopened.receive(fixture())["replayed"])


class EffectGatewayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "effects.sqlite"
        self.gateway = EffectGateway(SQLiteStore(self.path))

    def tearDown(self):
        self.tmp.cleanup()

    def test_fences_stale_executor(self):
        epoch = self.gateway.claim("task-1", "agent-a")
        self.assertEqual(epoch, 1)
        self.assertTrue(self.gateway.commit("task-1", "agent-a", 1, "effect-1", "synthetic"))
        self.assertFalse(self.gateway.commit("task-1", "agent-a", 1, "effect-1", "synthetic"))
        new_epoch = self.gateway.transfer("task-1", "agent-a", 1, "agent-b")
        self.assertEqual(new_epoch, 2)
        with self.assertRaises(PolicyDenied):
            self.gateway.commit("task-1", "agent-a", 1, "effect-2", "stale")
        with self.assertRaises(Conflict):
            self.gateway.transfer("task-1", "agent-a", 1, "agent-c")
        self.assertTrue(self.gateway.commit("task-1", "agent-b", 2, "effect-2", "approved"))
        self.assertEqual(self.gateway.reconcile("task-1", "effect-2"), "committed")
        self.assertEqual(self.gateway.reconcile("task-1", "lost-ack"), "unknown")

    def test_collision_and_reopen(self):
        self.gateway.claim("task-2", "agent-a")
        self.gateway.commit("task-2", "agent-a", 1, "effect-1", "A")
        with self.assertRaises(Conflict):
            self.gateway.commit("task-2", "agent-a", 1, "effect-1", "B")
        reopened = EffectGateway(SQLiteStore(self.path))
        self.assertEqual(reopened.reconcile("task-2", "effect-1"), "committed")
        self.assertEqual(reopened.transfer("task-2", "agent-a", 1, "agent-b"), 2)
        with self.assertRaises(PolicyDenied):
            self.gateway.commit("task-2", "agent-a", 1, "effect-2", "stale")

    def test_concurrent_effect_commit_and_racing_transfer(self):
        self.gateway.claim("task-3", "agent-a")
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(self.gateway.commit, "task-3", "agent-a", 1,
                                   "effect-1", "same payload") for _ in range(20)]
            self.assertEqual(sum(f.result() for f in futures), 1)
        self.gateway.transfer("task-3", "agent-a", 1, "agent-b")
        with self.assertRaises(PolicyDenied):
            self.gateway.commit("task-3", "agent-a", 1, "effect-1", "same payload")


if __name__ == "__main__":
    unittest.main()
