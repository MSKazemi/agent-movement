"""Issue #38: runtime revocation of PR #6 core approvals by a signed notice (issue #8 format).

Synthetic and LLM-free. Authority keys are fresh HS256 test keys (stdlib-only); one class
repeats the core checks with a public-only Ed25519 authority when the optional extra is
installed. Nothing here is a production revocation service.
"""

import concurrent.futures
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent_movement.core import (Approval, ApprovalRevoked, ContractError, EffectGateway, HandoffReceiver,
                                 PolicyDenied, RevocationRejected, SQLiteStore, digest)
from agent_movement.http import load_authorities, make_server
from agent_movement.receipts import HAVE_ED25519, ReceiptError, validate_body
from agent_movement.trust import Ed25519Key, HmacKey, ed25519_available, issue_revocation, seal
from test_core import fixture

ROOT = Path(__file__).parents[1]
REVOKED_AT = 1_792_000_000  # fixed claimed revocation time (2026-10-15)
needs_ed25519 = unittest.skipUnless(HAVE_ED25519 and ed25519_available(),
                                    'optional extra not installed: pip install -e ".[signing]"')


def approval(ref="approval-1", task="task-1"):
    return Approval(ref, task, "agent-a", "agent-b", "word_count")


def events(store, kind):
    return [e for e in store.audit() if e["event_type"] == kind]


class RevocationFixture(unittest.TestCase):
    """A receiver, a gateway on the same store, and one pinned synthetic authority."""

    def make_authority(self):
        return HmacKey.generate("user-authority")

    def pinned(self, authority):
        return authority

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "receiver.sqlite"
        self.store = SQLiteStore(self.path)
        self.authority = self.make_authority()
        self.receiver = HandoffReceiver("agent-b", self.store, [approval(), approval("approval-2", "task-2")],
                                        revocation_authorities=[self.pinned(self.authority)])
        self.gateway = EffectGateway(self.store)

    def tearDown(self):
        self.tmp.cleanup()

    def notice(self, ref="approval-1", key=None, revoked_at=REVOKED_AT):
        return issue_revocation(key or self.authority, ref, revoked_at)


class CoreRevocationTests(RevocationFixture):
    def test_revoke_between_admission_and_commit_blocks_the_commit(self):
        self.assertFalse(self.receiver.receive(fixture())["replayed"])  # admitted under approval-1
        epoch = self.gateway.claim("task-1", "agent-b")
        self.assertTrue(self.gateway.commit("task-1", "agent-b", epoch, "effect-1", "synthetic"))
        result = self.receiver.revoke(self.notice())
        self.assertEqual((result["status"], result["approval_ref"], result["replayed"]),
                         ("revoked", "approval-1", False))
        with self.assertRaises(ApprovalRevoked) as caught:
            self.gateway.commit("task-1", "agent-b", epoch, "effect-2", "synthetic")
        self.assertEqual(caught.exception.approval_ref, "approval-1")
        with self.assertRaises(ApprovalRevoked):  # an identical replay of a committed effect is refused too
            self.gateway.commit("task-1", "agent-b", epoch, "effect-1", "synthetic")
        self.assertEqual(self.gateway.reconcile("task-1", "effect-2"), "unknown")
        self.assertEqual(self.gateway.reconcile("task-1", "effect-1"), "committed")  # no undo
        # Ownership moves do not launder the revoked authority: the task stays bound to it.
        new_epoch = self.gateway.transfer("task-1", "agent-b", epoch, "agent-c")
        with self.assertRaises(ApprovalRevoked):
            self.gateway.commit("task-1", "agent-c", new_epoch, "effect-3", "synthetic")
        self.assertEqual(len(events(self.store, "approval.revoked")), 1)
        self.assertEqual(len(events(self.store, "effect.denied")), 3)
        self.assertEqual(events(self.store, "approval.revoked")[0]["info_digest"],
                         self.store.keyed_digest(digest(self.notice())))  # audit digests are keyed (#39)

    def test_revocation_blocks_new_and_replayed_handoffs(self):
        self.receiver.receive(fixture())
        self.receiver.revoke(self.notice())
        new = {**fixture(), "movement_id": "movement-2", "execution": {"idempotency_key": "op-2"}}
        for message in (new, fixture()):
            with self.subTest(movement=message["movement_id"]), self.assertRaises(ApprovalRevoked):
                self.receiver.receive(message)
        self.assertEqual(len(events(self.store, "handoff.denied")), 2)
        self.assertEqual(len(events(self.store, "handoff.accepted")), 1)
        # Other approvals and their tasks are unaffected.
        other = {**fixture(), "movement_id": "movement-3", "logical_task_id": "task-2",
                 "authority": {"approval_ref": "approval-2"}, "execution": {"idempotency_key": "op-3"}}
        self.assertFalse(self.receiver.receive(other)["replayed"])
        epoch = self.gateway.claim("task-2", "agent-b")
        self.assertTrue(self.gateway.commit("task-2", "agent-b", epoch, "effect-1", "synthetic"))

    def test_forged_and_unsigned_revocations_are_rejected(self):
        good = self.notice()
        tampered = json.loads(json.dumps(good))
        tampered["payload"]["grant_id"] = "approval-2"  # signed for approval-1, edited to approval-2
        cases = {
            "forged (same kid, other secret)": (self.notice(key=HmacKey.generate("user-authority")),
                                                "bad_revocation_signature"),
            "untrusted issuer": (self.notice(key=HmacKey.generate("rogue-authority")), "untrusted_grant_issuer"),
            "unsigned payload": (good["payload"], "malformed_revocation"),
            "signature stripped": ({**good, "sig": ""}, "bad_revocation_signature"),
            "tampered payload": (tampered, "bad_revocation_signature"),
            "other purpose": (seal("grant", good["payload"], self.authority), "bad_revocation_signature"),
            "algorithm swap": ({**good, "alg": "Ed25519"}, "key_mismatch"),
            "not an object": (["approval-1"], "malformed_revocation"),
        }
        for label, (notice, reason) in cases.items():
            with self.subTest(label), self.assertRaises(RevocationRejected) as caught:
                self.receiver.revoke(notice)
            self.assertEqual(caught.exception.reason, reason, label)
        with self.assertRaises(ContractError):
            self.receiver.revoke({"not": object()})  # not JSON at all
        self.assertEqual(self.store.revocations(), [])
        self.assertEqual(len(events(self.store, "approval.revocation_rejected")), len(cases))
        # Nothing was revoked: the approval and the effect path still work.
        self.assertFalse(self.receiver.receive(fixture())["replayed"])
        epoch = self.gateway.claim("task-1", "agent-b")
        self.assertTrue(self.gateway.commit("task-1", "agent-b", epoch, "effect-1", "synthetic"))

    def test_receiver_without_an_authority_refuses_every_notice(self):
        receiver = HandoffReceiver("agent-b", self.store, [approval()])
        with self.assertRaises(RevocationRejected) as caught:
            receiver.revoke(self.notice())
        self.assertEqual(caught.exception.reason, "no_revocation_authority")
        self.assertEqual(self.store.revocations(), [])
        self.assertFalse(receiver.receive(fixture())["replayed"])

    def test_revocation_is_idempotent(self):
        first = self.receiver.revoke(self.notice())
        again = self.receiver.revoke(self.notice())
        later = self.receiver.revoke(self.notice(revoked_at=REVOKED_AT + 60))  # a second, distinct notice
        self.assertEqual([r["replayed"] for r in (first, again, later)], [False, True, True])
        self.assertEqual({r["approval_ref"] for r in (first, again, later)}, {"approval-1"})
        rows = self.store.revocations()
        self.assertEqual(len(rows), 1)  # the first verified notice stays the record
        self.assertEqual((rows[0]["approval_ref"], rows[0]["issuer"], rows[0]["claimed_revoked_at"],
                          rows[0]["notice_digest"]),
                         ("approval-1", "user-authority", REVOKED_AT, digest(self.notice())))
        self.assertEqual(len(events(self.store, "approval.revoked")), 1)
        with self.assertRaises(ApprovalRevoked):
            self.receiver.receive(fixture())

    def test_concurrent_identical_revocations_record_one(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.receiver.revoke(self.notice()), range(16)))
        self.assertEqual(sum(not r["replayed"] for r in results), 1)
        self.assertEqual(len(events(self.store, "approval.revoked")), 1)

    def test_unknown_approval_is_rejected_after_verification(self):
        with self.assertRaises(RevocationRejected) as caught:
            self.receiver.revoke(self.notice("approval-elsewhere"))
        self.assertEqual(caught.exception.reason, "unknown_approval")
        self.assertEqual(self.store.revocations(), [])

    def test_revocation_persists_across_store_instances(self):
        """The HTTP receiver and the effect gateway run in different processes in the demo."""
        self.receiver.receive(fixture())
        gateway = EffectGateway(SQLiteStore(self.path))  # a separately opened store on the same file
        epoch = gateway.claim("task-1", "agent-b")
        self.receiver.revoke(self.notice())
        with self.assertRaises(ApprovalRevoked):
            gateway.commit("task-1", "agent-b", epoch, "effect-1", "synthetic")
        reopened = HandoffReceiver("agent-b", SQLiteStore(self.path), [approval()])
        with self.assertRaises(PolicyDenied):  # survives a restart without the authority
            reopened.receive(fixture())

    def test_purge_keeps_revocations_enforced(self):
        """Retention (issue #39) deletes history, never a revocation or a task binding."""
        from agent_movement.retention import purge
        self.receiver.receive(fixture())
        epoch = self.gateway.claim("task-1", "agent-b")
        self.receiver.revoke(self.notice())
        purge(self.path, 0)  # everything purgeable is older than "now"
        self.assertEqual([r["approval_ref"] for r in self.store.revocations()], ["approval-1"])
        with self.assertRaises(ApprovalRevoked):
            self.gateway.commit("task-1", "agent-b", epoch, "effect-1", "synthetic")
        with self.assertRaises(ApprovalRevoked):  # the delivery row is gone, so this is a new handoff
            self.receiver.receive(fixture())

    def test_only_tasks_delivered_under_the_approval_are_rechecked(self):
        """Scope limit, stated in the docs: a task that never arrived through a delivery under
        the approval carries no approval, so only its ownership epoch is checked."""
        epoch = self.gateway.claim("local-task", "agent-b")
        self.receiver.revoke(self.notice())
        self.assertTrue(self.gateway.commit("local-task", "agent-b", epoch, "effect-1", "synthetic"))

    def test_static_flag_is_still_honoured(self):
        receiver = HandoffReceiver("agent-b", self.store, [Approval("approval-1", "task-1", "agent-a", "agent-b",
                                                                    "word_count", revoked=True)])
        with self.assertRaises(PolicyDenied):
            receiver.receive(fixture())


@needs_ed25519
class Ed25519AuthorityTests(RevocationFixture):
    """The receiver pins only the public half: it can verify notices but never issue one."""

    def make_authority(self):
        return Ed25519Key.generate("user-authority")

    def pinned(self, authority):
        return Ed25519Key.from_public(authority.kid, authority.public_value())

    def test_signed_notice_revokes_and_forgery_is_rejected(self):
        self.receiver.receive(fixture())
        epoch = self.gateway.claim("task-1", "agent-b")
        with self.assertRaises(RevocationRejected):
            self.receiver.revoke(self.notice(key=Ed25519Key.generate("user-authority")))
        self.assertTrue(self.gateway.commit("task-1", "agent-b", epoch, "effect-1", "synthetic"))
        self.assertFalse(self.receiver.revoke(self.notice())["replayed"])
        with self.assertRaises(ApprovalRevoked):
            self.gateway.commit("task-1", "agent-b", epoch, "effect-2", "synthetic")


class HttpRevocationTests(RevocationFixture):
    def setUp(self):
        super().setUp()
        self.server = make_server(self.receiver)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        super().tearDown()

    def post(self, path, data, content_type="application/json"):
        if not isinstance(data, bytes):
            data = json.dumps(data).encode("utf-8")
        request = urllib.request.Request(self.base + path, data=data, headers={"Content-Type": content_type})
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as exc:
            with exc:
                return exc.code, json.load(exc)

    def test_revocation_endpoint(self):
        self.assertEqual(self.post("/v0/handoffs", fixture())[0], 200)
        good = self.notice()
        self.assertEqual(self.post("/v0/revocations", self.notice(key=HmacKey.generate("user-authority"))),
                         (401, {"error": "unauthenticated"}))
        self.assertEqual(self.post("/v0/revocations", good["payload"]), (401, {"error": "unauthenticated"}))
        self.assertEqual(self.post("/v0/revocations", b'not json')[0], 400)
        self.assertEqual(self.post("/v0/revocations", b'{"a":1,"a":2}')[0], 400)
        self.assertEqual(self.post("/v0/revocations", good, "text/plain")[0], 415)
        self.assertEqual(self.post("/v0/revocations", b' ' * 16385)[0], 413)
        self.assertEqual(self.post("/v0/revocations", self.notice("approval-elsewhere")),
                         (404, {"error": "unknown_approval"}))
        self.assertEqual(self.post("/v0/handoffs", fixture())[0], 200)  # nothing revoked yet: replay works
        status, body = self.post("/v0/revocations", good)
        self.assertEqual((status, body["status"], body["approval_ref"], body["replayed"]),
                         (200, "revoked", "approval-1", False))
        self.assertEqual(self.post("/v0/revocations", good)[1]["replayed"], True)
        self.assertEqual(self.post("/v0/handoffs", fixture()), (403, {"error": "approval_denied"}))
        self.assertEqual(self.post("/v0/revoke", good)[0], 404)

    def test_endpoint_without_an_authority_refuses_every_notice(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.server = make_server(HandoffReceiver("agent-b", self.store, [approval()]))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.assertEqual(self.post("/v0/revocations", self.notice()), (401, {"error": "unauthenticated"}))
        self.assertEqual(self.post("/v0/handoffs", fixture())[0], 200)


class AuthorityFileTests(unittest.TestCase):
    def test_load_authorities_accepts_one_key_or_a_list(self):
        a, b = HmacKey.generate("authority-a"), HmacKey.generate("authority-b")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "authority.json"
            path.write_text(json.dumps(a.export()))
            self.assertEqual([k.kid for k in load_authorities(path)], ["authority-a"])
            path.write_text(json.dumps([a.export(), b.export()]))
            self.assertEqual([k.kid for k in load_authorities(path)], ["authority-a", "authority-b"])
            for bad in ([], [a.export(), a.export()], {"alg": "none", "kid": "x"}):
                path.write_text(json.dumps(bad))
                with self.subTest(bad=bad), self.assertRaises(ContractError):
                    load_authorities(path)

    def test_http_main_exits_2_on_an_unusable_authority_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "authority.json"
            path.write_text("[]")
            env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
            result = subprocess.run([sys.executable, "-m", "agent_movement.http", "--db", str(Path(tmp) / "x.db"),
                                     "--revocation-authority", str(path)], capture_output=True, text=True,
                                    env=env, timeout=60)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("--revocation-authority", result.stderr)


class RevocationReceiptSchemaTests(unittest.TestCase):
    def body(self, subjects):
        return {"schema": "agent-movement.receipt/0.1-draft", "receipt_id": "rcpt-1", "receipt_type": "authority.revoked",
                "issuer": {"key_id": "k-1", "claimed_principal": None, "claimed_agent_id": "agent-b"},
                "audience": None, "nonce": "0" * 32, "issued_at": "2026-10-16T12:00:00Z", "seq": 1,
                "prev_receipt_digest": None, "logical_task_id": "task-1", "movement": None, "source": None,
                "destination": None, "execution": None, "correlation": {"trace_id": None, "span_id": None},
                "subjects": subjects, "effect": None, "outcome": "revoked", "data_classification": "synthetic"}

    def test_authority_revoked_needs_a_revocation_notice_subject(self):
        notice = {"role": "revocation_notice", "ref": "notice-1", "digest": "sha256:" + "a" * 64}
        self.assertEqual(validate_body(self.body([notice]))["receipt_type"], "authority.revoked")
        for subjects in ([], [{**notice, "role": "envelope"}]):
            with self.subTest(subjects=subjects), self.assertRaises(ReceiptError):
                validate_body(self.body(subjects))


@needs_ed25519
class RevocationReceiptTests(unittest.TestCase):
    """With emission on, an applied revocation is signed once and the bundle still verifies."""

    def test_revocation_receipt_and_blocked_effect_record(self):
        from agent_movement import demo
        from agent_movement.live_receipts import (ReceiptEmitter, RecordingEffectGateway, export_run,
                                                  notice_subject_ref)
        from agent_movement.receipts import verify_bundle
        t0 = datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)
        clock = lambda: t0  # noqa: E731
        authority = HmacKey.generate("user-authority")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sender = ReceiptEmitter(root / "a.jsonl", name="agent-a", clock=clock)
            emitter = ReceiptEmitter(root / "b.jsonl", name="agent-b", clock=clock)
            tool = ReceiptEmitter(root / "tool.jsonl", name="effect-gateway", role="tool", clock=clock)
            store = SQLiteStore(root / "ledger.sqlite")
            receiver = HandoffReceiver("agent-b", store, [approval()], revocation_authorities=[authority])
            server = make_server(receiver, receipts=emitter)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            notice = issue_revocation(authority, "approval-1", REVOKED_AT)
            try:
                self.assertEqual(demo.handoff(base + "/v0/handoffs", fixture(), sender, emitter.principal)[0], 200)
                effects = RecordingEffectGateway(store, tool)
                epoch = effects.claim("task-1", "agent-b")
                self.assertTrue(effects.commit("task-1", "agent-b", epoch, "effect-1", "synthetic"))
                lines = emitter.log_path.read_bytes().count(b"\n")
                forged = issue_revocation(HmacKey.generate("user-authority"), "approval-1", REVOKED_AT)
                self.assertEqual(demo.post(base + "/v0/revocations", forged)[0], 401)
                self.assertEqual(emitter.log_path.read_bytes().count(b"\n"), lines)  # a refusal signs nothing
                self.assertEqual(demo.post(base + "/v0/revocations", notice)[0], 200)
                self.assertEqual(demo.post(base + "/v0/revocations", notice)[0], 200)  # replay signs nothing
                self.assertEqual(emitter.log_path.read_bytes().count(b"\n"), lines + 1)
                with self.assertRaises(ApprovalRevoked):
                    effects.commit("task-1", "agent-b", epoch, "effect-2", "synthetic")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
            last = json.loads(emitter.log_path.read_text().splitlines()[-1])["receipt"]
            self.assertEqual((last["receipt_type"], last["outcome"], last["logical_task_id"]),
                             ("authority.revoked", "revoked", "task-1"))
            self.assertEqual([s["ref"] for s in last["subjects"]], [notice_subject_ref(notice)])
            tool_records = [json.loads(x)["receipt"]["effect"] for x in tool.log_path.read_text().splitlines()]
            self.assertEqual([(e["effect_id"], e["status"]) for e in tool_records],
                             [("effect-1", "committed"), ("effect-2", "rejected")])
            bundle, trust = export_run(root / "out", receipt_logs=[sender.log_path, emitter.log_path],
                                       tool_logs=[tool.log_path], not_before=t0 - timedelta(minutes=1),
                                       descriptors=[sender.descriptor(), emitter.descriptor(), tool.descriptor()],
                                       notices=[notice])
            report = verify_bundle(bundle, trust, t0 + timedelta(minutes=1))
            self.assertEqual(report["exit_code"], 0)
            self.assertEqual({k: v for k, v in report["receipt_verdicts"].items() if v}, {"VALID": 6})
            statuses = {s["ref"]: s["status"] for s in report["subjects"] if s["role"] == "revocation_notice"}
            self.assertEqual(statuses, {notice_subject_ref(notice): "DIGEST_MATCH"})
            self.assertNotIn(authority.export()["secret"], "".join(p.read_text() for p in bundle.rglob("*.json*")))


if __name__ == "__main__":
    unittest.main()
