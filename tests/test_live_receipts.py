"""Issue #32: signed receipts on the live PR #6 HTTP path, and issue #8 revocation notices.

Synthetic and LLM-free. Live keys are ephemeral (fresh per test); the clock is injected,
so issued_at values and revocation times are deterministic.
"""

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from agent_movement import demo, receipts
from agent_movement.core import Approval, HandoffReceiver, PolicyDenied, SQLiteStore, digest
from agent_movement.http import make_server
from agent_movement.jcs import canonicalize, jcs_digest
from agent_movement.live_receipts import (BUNDLE_NAME, TRUST_NAME, ReceiptEmitter, RecordingEffectGateway,
                                          export_run)
from agent_movement.receipts import HAVE_ED25519, ReceiptError, verify_bundle
from agent_movement.trust import HmacKey, issue_revocation
from test_core import fixture

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "movement-receipts"
T0 = datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)
VERIFY_AT = T0 + timedelta(minutes=1)
# A distinctive, guessable task text: it must never reach a receipt, the bundle or the anchors.
TASK_TEXT = "lantern quartz zebra harbor"
needs_ed25519 = unittest.skipUnless(HAVE_ED25519, 'optional extra not installed: pip install -e ".[signing]"')


def run_module(module, *args):
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    return subprocess.run([sys.executable, "-m", module, *args], capture_output=True, text=True,
                          env=env, timeout=120)


def envelope(**changes):
    message = fixture()
    message["task"]["text"] = TASK_TEXT
    message.update(changes)
    return message


def live_run(root: Path, *, revocation_issuers=()):
    """One live HTTP run with receipts on: new delivery, replay, denial, 409, 400 and fencing."""
    clock = lambda: T0  # noqa: E731 - deterministic claimed times
    logs = root / "logs"
    sender = ReceiptEmitter(logs / "agent-a.jsonl", name="agent-a", clock=clock)
    receiver_receipts = ReceiptEmitter(logs / "agent-b.jsonl", name="agent-b", clock=clock)
    tool = ReceiptEmitter(logs / "tool.jsonl", name="effect-gateway", role="tool", clock=clock)
    store = SQLiteStore(root / "ledger.sqlite")
    receiver = HandoffReceiver("agent-b", store, [Approval("approval-1", "task-1", "agent-a", "agent-b",
                                                           "word_count")])
    server = make_server(receiver, receipts=receiver_receipts)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/v0/handoffs"
    to = receiver_receipts.principal
    try:
        first = demo.handoff(url, envelope(), sender, to)
        lines_after_first = receiver_receipts.log_path.read_bytes().count(b"\n")
        replay = demo.handoff(url, envelope(), sender, to)
        conflict = demo.handoff(url, envelope(execution={"idempotency_key": "op-1"},
                                              task={"kind": "word_count", "text": "colliding text"}))
        invalid = demo.handoff(url, {**envelope(), "operation": "relocate"})
        lines_after_replay = receiver_receipts.log_path.read_bytes().count(b"\n")
        denied = demo.handoff(url, envelope(movement_id="movement-denied", authority={"approval_ref": "nope"},
                                            execution={"idempotency_key": "op-denied"}), sender, to)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    effects = RecordingEffectGateway(store, tool)
    old = effects.claim("fenced-task", "agent-a")
    new = effects.transfer("fenced-task", "agent-a", old, "agent-b")
    try:
        effects.commit("fenced-task", "agent-a", old, "effect-1", "synthetic payload")
        raise AssertionError("stale epoch was not fenced")
    except PolicyDenied:
        pass
    committed = effects.commit("fenced-task", "agent-b", new, "effect-1", "synthetic payload")
    again = effects.commit("fenced-task", "agent-b", new, "effect-1", "synthetic payload")  # replay: no record
    bundle, trust = export_run(root / "out", receipt_logs=[sender.log_path, receiver_receipts.log_path],
                               tool_logs=[tool.log_path], not_before=T0 - timedelta(minutes=1),
                               descriptors=[sender.descriptor(), receiver_receipts.descriptor(), tool.descriptor()],
                               revocation_issuers=revocation_issuers)
    return SimpleNamespace(bundle=bundle, trust=trust, sender=sender, receiver=receiver_receipts, tool=tool,
                           first=first, replay=replay, conflict=conflict, invalid=invalid, denied=denied,
                           committed=committed, again=again, lines_after_first=lines_after_first,
                           lines_after_replay=lines_after_replay)


def wires(path):
    return [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]


@needs_ed25519
class LiveHttpReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.run = live_run(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_live_run_exports_a_bundle_that_verifies(self):
        r = self.run
        self.assertEqual((r.first[0], r.replay[0], r.conflict[0], r.invalid[0], r.denied[0]),
                         (200, 200, 409, 400, 403))
        self.assertEqual((r.committed, r.again), (True, False))
        report = verify_bundle(r.bundle, r.trust, VERIFY_AT)
        self.assertEqual(report["exit_code"], 0, json.dumps(report["receipts"], indent=1))
        self.assertEqual({k: v for k, v in report["receipt_verdicts"].items() if v}, {"VALID": 7})
        self.assertEqual(report["trust_anchor_mode"], "explicit")
        accepted, denied = report["movements"]["movement-1"], report["movements"]["movement-denied"]
        for movement, outcome in ((accepted, "accepted"), (denied, "rejected")):
            self.assertEqual(movement["grade"], "E3")  # dispatch and response from two independent signers
            self.assertEqual(movement["source_principal"], {"status": "VERIFIED", "value": r.sender.principal})
            self.assertEqual(movement["destination_principal"]["status"], "VERIFIED")
            self.assertEqual(movement["destination_principal"]["value"], r.receiver.principal)
            self.assertEqual(movement["outcome"], {"status": "SIGNED_CLAIM", "value": outcome})
        self.assertEqual(report["effects"], [{"logical_task_id": "fenced-task", "effect_id": "effect-1",
                                              "status": "TOOL_RECORD_ONLY", "agent_claims": [],
                                              "tool_records": ["committed", "rejected"]}])
        self.assertFalse([e for e in report["timeline"] if e["event_type"] == "evidence.gap_detected"])
        self.assertEqual(report["revocation_notices"], [])
        cli = run_module("agent_movement.receipts", "verify", "--trust", str(r.trust), str(r.bundle))
        self.assertEqual(cli.returncode, 0, cli.stdout + cli.stderr)

    def test_one_receipt_per_event_and_none_for_replay_conflict_or_invalid(self):
        r = self.run
        self.assertEqual(r.lines_after_first, 2)  # movement.accepted + execution.completed
        self.assertEqual(r.lines_after_replay, 2)  # idempotent replay, 409 and 400 sign nothing
        types = [(w["receipt"]["issuer"]["key_id"], w["receipt"]["seq"], w["receipt"]["receipt_type"])
                 for w in wires(r.bundle / "receipts.jsonl") + wires(r.bundle / "tool-records.jsonl")]
        self.assertEqual(types, [
            (r.sender.key_id, 1, "movement.dispatched"), (r.sender.key_id, 2, "movement.dispatched"),
            (r.receiver.key_id, 1, "movement.accepted"), (r.receiver.key_id, 2, "execution.completed"),
            (r.receiver.key_id, 3, "movement.rejected"),
            (r.tool.key_id, 1, "tool.effect_recorded"), (r.tool.key_id, 2, "tool.effect_recorded")])
        tool = [w["receipt"]["effect"] for w in wires(r.bundle / "tool-records.jsonl")]
        self.assertEqual([(e["status"], e["fencing_epoch"]) for e in tool], [("rejected", 1), ("committed", 2)])
        self.assertEqual((r.sender.failures, r.receiver.failures, r.tool.failures), (0, 0, 0))

    def test_tampered_copy_exits_1(self):
        r = self.run
        for label, mutate in (("edited, digest kept", lambda w: w["receipt"].update(outcome="rejected")),
                              ("edited, digest recomputed", lambda w: (
                                  w["receipt"]["destination"].update(claimed_agent_id="agent-c"),
                                  w.update(body_digest=jcs_digest(w["receipt"]))))):
            with self.subTest(label):
                copy_dir = self.root / f"tampered-{len(label)}"
                shutil.copytree(r.bundle, copy_dir)
                lines = wires(copy_dir / "receipts.jsonl")
                mutate(lines[2])  # the receiver's movement.accepted
                (copy_dir / "receipts.jsonl").write_bytes(b"".join(canonicalize(w) + b"\n" for w in lines))
                report = verify_bundle(copy_dir, r.trust, VERIFY_AT)
                self.assertEqual((report["receipt_verdicts"]["TAMPERED"], report["exit_code"]), (1, 1))
                cli = run_module("agent_movement.receipts", "verify", "--trust", str(r.trust), str(copy_dir))
                self.assertEqual(cli.returncode, 1, cli.stdout + cli.stderr)

    def test_trust_file_is_outside_the_bundle_and_refused_inside_it(self):
        r = self.run
        self.assertEqual((r.bundle.name, r.trust.name), (BUNDLE_NAME, TRUST_NAME))
        self.assertFalse(r.trust.resolve().is_relative_to(r.bundle.resolve()))
        self.assertEqual(sorted(p.name for p in r.bundle.iterdir()), ["receipts.jsonl", "tool-records.jsonl"])
        planted = r.bundle / "trust.json"
        shutil.copy(r.trust, planted)
        cli = run_module("agent_movement.receipts", "verify", "--trust", str(planted), str(r.bundle))
        self.assertEqual(cli.returncode, 2, cli.stderr)
        self.assertIn("inside the evidence bundle", cli.stderr)
        anchors = json.loads(r.trust.read_text())
        for key in anchors["keys"]:  # public halves only
            self.assertEqual(set(key), {"key_id", "principal", "role", "alg", "public_key", "not_before",
                                        "not_after", "revoked_at", "revocation_ref"})
        self.assertEqual({k["role"] for k in anchors["keys"]}, {"agent", "tool"})
        with self.assertRaisesRegex(ReceiptError, "already holds evidence"):
            export_run(r.bundle.parent, receipt_logs=[], descriptors=[], not_before=T0)

    def test_no_task_text_only_salted_commitments(self):
        r = self.run
        sent = envelope()
        core = r.first[1]
        published = "".join(p.read_text() for p in (*r.bundle.iterdir(), r.trust))
        for needle in (TASK_TEXT, "lantern", "colliding text", core["envelope_digest"], core["artifact_digest"],
                       digest(sent), jcs_digest(sent).split(":")[1], digest(core["artifact"])):
            self.assertNotIn(needle, published)
        subjects = [s for w in wires(r.bundle / "receipts.jsonl") + wires(r.bundle / "tool-records.jsonl")
                    for s in w["receipt"]["subjects"]]
        self.assertEqual(len(subjects), 7)
        held = {**r.sender.commitments, **r.receiver.commitments, **r.tool.commitments}
        salts = set()
        for subject in subjects:
            doc = held[subject["ref"]]
            self.assertEqual(set(doc), {"commitment_salt", "value"})
            self.assertRegex(doc["commitment_salt"], r"\A[0-9a-f]{32}\Z")
            self.assertEqual(jcs_digest(doc), subject["digest"])
            salts.add(doc["commitment_salt"])
        self.assertEqual(len(salts), 7)  # a fresh salt per subject
        # The holder can still prove a commitment: copying its documents in gives DIGEST_MATCH.
        (r.bundle / "subjects").mkdir()
        for ref, doc in held.items():
            (r.bundle / "subjects" / f"{ref}.json").write_bytes(canonicalize(doc))
        report = verify_bundle(r.bundle, r.trust, VERIFY_AT)
        self.assertEqual({s["status"] for s in report["subjects"]}, {"DIGEST_MATCH"})
        self.assertEqual(report["exit_code"], 0)


@needs_ed25519
class EmitterRobustnessTests(unittest.TestCase):
    def test_emission_failure_never_changes_the_handoff_outcome(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            broken = ReceiptEmitter(root / "b.jsonl", name="agent-b")
            broken.log_path = root  # a directory: every write fails
            receiver = HandoffReceiver("agent-b", SQLiteStore(root / "r.sqlite"),
                                       [Approval("approval-1", "task-1", "agent-a", "agent-b", "word_count")])
            server = make_server(receiver, receipts=broken)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                url = f"http://127.0.0.1:{server.server_port}/v0/handoffs"
                self.assertEqual(demo.handoff(url, fixture())[0], 200)
                denied = fixture()
                denied.update(movement_id="m-2", authority={"approval_ref": "nope"})
                self.assertEqual(demo.handoff(url, denied)[0], 403)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
            self.assertEqual(broken.failures, 2)  # the accept and the reject; nothing was half-chained

    def test_tool_records_need_a_tool_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = ReceiptEmitter(Path(tmp) / "a.jsonl", name="agent-a")
            with self.assertRaisesRegex(ReceiptError, "role 'tool'"):
                RecordingEffectGateway(SQLiteStore(Path(tmp) / "e.sqlite"), agent)
            with self.assertRaises(ReceiptError):
                ReceiptEmitter(Path(tmp) / "x.jsonl", name="bad name")

    def test_http_receiver_advertises_only_a_public_key_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            for extra, expected in (((), {"port", "agent"}), (("--receipts-log", str(Path(tmp) / "r.jsonl")),
                                                               {"port", "agent", "receipt_key"})):
                env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
                process = subprocess.Popen([sys.executable, "-m", "agent_movement.http", "--db",
                                            str(Path(tmp) / f"h{len(extra)}.sqlite"), *extra],
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
                try:
                    advertised = json.loads(process.stdout.readline())
                finally:
                    process.terminate()
                    process.communicate(timeout=10)
                self.assertEqual(set(advertised), expected)
                if "receipt_key" in advertised:
                    self.assertEqual(set(advertised["receipt_key"]), {"key_id", "principal", "role", "public_key"})


class ReceiptsNeedTheExtraTests(unittest.TestCase):
    """Default off, and fail closed (exit 2) when asked for without the signing extra."""

    def test_emitter_and_demo_flag_fail_closed_without_the_extra(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(receipts, "HAVE_ED25519", False):
            with self.assertRaisesRegex(ReceiptError, "optional extra"):
                ReceiptEmitter(Path(tmp) / "a.jsonl", name="agent-a")
            with mock.patch("sys.stderr"), self.assertRaises(SystemExit) as stop:
                demo.main(["--receipts", tmp])
            self.assertEqual(stop.exception.code, 2)
            self.assertEqual(list(Path(tmp).iterdir()), [])


@needs_ed25519
class DemoReceiptsFlagTests(unittest.TestCase):
    def test_demo_receipts_flag_bundle_verifies_and_tampered_copy_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            result = run_module("agent_movement.demo", "--receipts", str(out))
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(set(summary), {"first", "replay", "denied", "fencing", "revocation", "receipts"})
            self.assertEqual(summary["receipts"]["verifier_exit_code"], 0)
            self.assertEqual(summary["receipts"]["receipt_verdicts"], {"VALID": 12})
            self.assertEqual(summary["receipts"]["revocation_notice_subjects"], ["DIGEST_MATCH"])
            bundle, trust = out / BUNDLE_NAME, out / TRUST_NAME
            ok = run_module("agent_movement.receipts", "verify", "--trust", str(trust), str(bundle))
            self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
            tampered = Path(tmp) / "tampered"
            shutil.copytree(bundle, tampered)
            text = (tampered / "receipts.jsonl").read_text()
            (tampered / "receipts.jsonl").write_text(text.replace('"outcome":"accepted"', '"outcome":"rejected"', 1))
            bad = run_module("agent_movement.receipts", "verify", "--trust", str(trust), str(tampered))
            self.assertEqual(bad.returncode, 1, bad.stdout)
            self.assertNotIn("synthetic agent movement test task",
                             "".join(p.read_text() for p in bundle.rglob("*") if p.is_file()))
            again = run_module("agent_movement.demo", "--receipts", str(out))  # never mixes two runs
            self.assertEqual(again.returncode, 2)
            self.assertIn("already holds evidence", again.stderr)

    def test_unified_cli_forwards_the_receipts_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            result = run_module("agent_movement", "demo", "--receipts", str(out))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["receipts"]["verifier_exit_code"], 0)
            ok = run_module("agent_movement", "receipts", "verify", "--trust", str(out / TRUST_NAME),
                            str(out / BUNDLE_NAME))
            self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        self.assertIn("--receipts OUTDIR", run_module("agent_movement", "demo", "--help").stdout)

    def test_demo_default_output_has_no_receipts(self):
        result = run_module("agent_movement.demo")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(json.loads(result.stdout)), {"first", "replay", "denied", "fencing", "revocation"})


# ---------------------------------------------------------------------- revocation notices

def notice_bundle(root: Path, name: str, notices) -> Path:
    """Copy the committed valid fixture bundle and add a revocations.jsonl."""
    bundle = root / name
    shutil.copytree(FIXTURES / "01-valid-delegation", bundle)
    (bundle / "revocations.jsonl").write_bytes(b"".join(
        (n if isinstance(n, bytes) else canonicalize(n)) + b"\n" for n in notices))
    return bundle


def anchors_with(root: Path, issuers, name="anchors.json") -> Path:
    doc = json.loads((FIXTURES / "trust.json").read_text())
    doc["revocation_issuers"] = issuers
    path = root / name
    path.write_text(json.dumps(doc))
    return path


class RevocationNoticeCoreTests(unittest.TestCase):
    """Paths that need no signature check, so they also run without the signing extra."""

    NOW = datetime(2026, 10, 16, tzinfo=timezone.utc)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_hs256_notices_and_authorities_are_refused(self):
        hmac_authority = HmacKey("revocation-authority", b"\x01" * 32)
        notice = issue_revocation(hmac_authority, "synthetic-agent-b-2026", 1760000000)
        bundle = notice_bundle(self.root, "hs256", [notice])
        report = verify_bundle(bundle, FIXTURES / "trust.json", self.NOW)
        [entry] = report["revocation_notices"]
        self.assertEqual((entry["verdict"], entry["applied"], report["exit_code"]), ("UNTRUSTED", False, 1))
        self.assertIn("cannot be verified offline", entry["reasons"][0])
        bad = anchors_with(self.root, [hmac_authority.export()])
        with self.assertRaisesRegex(ReceiptError, "must be Ed25519"):
            verify_bundle(bundle, bad, self.NOW)
        cli = run_module("agent_movement.receipts", "verify", "--trust", str(bad), str(bundle))
        self.assertEqual(cli.returncode, 2)
        self.assertNotIn(hmac_authority.export()["secret"], cli.stdout + cli.stderr)

    def test_malformed_notice_lines_are_rejected(self):
        bundle = notice_bundle(self.root, "malformed", [b"not json", b'{"alg":"Ed25519"}',
                                                        canonicalize({"alg": "Ed25519", "kid": "k", "sig": "AA",
                                                                      "payload": {"token": "Bearer abcdefgh"}})])
        report = verify_bundle(bundle, FIXTURES / "trust.json", self.NOW)
        self.assertEqual([n["verdict"] for n in report["revocation_notices"]], ["MALFORMED"] * 3)
        self.assertEqual(report["exit_code"], 1)
        self.assertNotIn("Bearer", json.dumps(report) + receipts.render_text(report))

    def test_unchecked_without_the_extra_is_not_applied(self):
        unsigned = {"alg": "Ed25519", "kid": "revocation-authority", "sig": "AAAA",
                    "payload": {"type": "revocation", "issuer": "revocation-authority",
                                "grant_id": "synthetic-agent-b-2026", "revoked_at": 0}}
        bundle = notice_bundle(self.root, "unchecked", [unsigned])
        with mock.patch.object(receipts, "HAVE_ED25519", False):
            report = verify_bundle(bundle, FIXTURES / "trust.json", self.NOW)
        [entry] = report["revocation_notices"]
        self.assertEqual((entry["verdict"], entry["applied"], report["exit_code"]), ("UNCHECKED", False, 3))

    def test_revocation_issuer_entries_are_validated(self):
        for issuers, message in (({"kid": "x"}, "must be a list"),
                                 ([{"alg": "Ed25519", "kid": "x", "public": "AAAA"}], "invalid Ed25519 public key"),
                                 ([{"alg": "Ed25519", "kid": "x", "public": "A" * 43, "private": "B"}], "fields")):
            with self.subTest(message):
                with self.assertRaisesRegex(ReceiptError, message):
                    receipts.load_trust_anchors(anchors_with(self.root, issuers))
        self.assertEqual(receipts.load_trust_anchors(FIXTURES / "trust.json").revocation_issuers, {})


@needs_ed25519
class RevocationNoticeTests(unittest.TestCase):
    """Issue #8 signed notices, verified with trust.verify_revocation, applied to receipt keys."""

    def setUp(self):
        from agent_movement.trust import Ed25519Key
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.authority = Ed25519Key.generate("revocation-authority")
        self.run = live_run(self.root, revocation_issuers=[self.authority.export(private=False)])
        self.receiver_key = self.run.receiver.key_id

    def tearDown(self):
        self.tmp.cleanup()

    def revoke(self, seconds, key_id=None, authority=None):
        return issue_revocation(authority or self.authority, key_id or self.receiver_key,
                                int((T0 + timedelta(seconds=seconds)).timestamp()))

    def verify(self, *notices, trust=None, extra=()):
        (self.run.bundle / "revocations.jsonl").write_bytes(b"".join(canonicalize(n) + b"\n" for n in notices))
        return verify_bundle(self.run.bundle, trust or self.run.trust, VERIFY_AT, revocations=extra)

    def receiver_verdicts(self, report):
        return {r["verdict"] for r in report["receipts"] if r["ref"].startswith(f"receipt:{self.receiver_key}.")}

    def test_key_revoked_before_issued_at_is_untrusted(self):
        notice = self.revoke(-60)
        report = self.verify(notice)
        [entry] = report["revocation_notices"]
        self.assertEqual((entry["verdict"], entry["applied"], entry["revoked_key_id"]),
                         ("VALID", True, self.receiver_key))
        self.assertEqual(entry["digest"], jcs_digest(notice))
        self.assertEqual(self.receiver_verdicts(report), {"UNTRUSTED"})
        self.assertEqual(report["receipt_verdicts"]["UNTRUSTED"], 3)
        self.assertEqual(report["receipt_verdicts"]["VALID"], 4)  # the other signers are unaffected
        reasons = [x for r in report["receipts"] for x in r["reasons"]]
        self.assertIn(f"key was revoked before the claimed issue time (verified signed revocation notice "
                      f"{jcs_digest(notice)})", reasons)
        self.assertEqual(report["movements"]["movement-1"]["destination_principal"]["status"], "SIGNED_CLAIM")
        self.assertEqual(report["exit_code"], 1)
        text = receipts.render_text(report)
        self.assertIn(f"revokes {self.receiver_key} from 2026-10-16T11:59:00Z", text)

    def test_revocation_at_issued_at_counts_as_revoked(self):
        self.assertEqual(self.receiver_verdicts(self.verify(self.revoke(0))), {"UNTRUSTED"})

    def test_key_revoked_after_issued_at_stays_valid(self):
        report = self.verify(self.revoke(+60))
        self.assertTrue(report["revocation_notices"][0]["applied"])
        self.assertEqual(self.receiver_verdicts(report), {"VALID"})
        self.assertEqual(report["exit_code"], 0)

    def test_earliest_verified_revocation_wins(self):
        report = self.verify(self.revoke(+60), self.revoke(-60))
        self.assertEqual(self.receiver_verdicts(report), {"UNTRUSTED"})

    def test_forged_and_tampered_notices_are_rejected_and_not_applied(self):
        from agent_movement.trust import Ed25519Key
        impostor = Ed25519Key.generate("revocation-authority")  # same kid, different key
        stranger = Ed25519Key.generate("someone-else")
        tampered = self.revoke(+60)
        tampered["payload"]["revoked_at"] -= 3600  # moved before issued_at without re-signing
        swapped = copy.deepcopy(self.revoke(+60))
        swapped["payload"]["grant_id"] = self.run.sender.key_id
        cases = {"impostor": (self.revoke(-60, authority=impostor), "TAMPERED"),
                 "stranger": (self.revoke(-60, authority=stranger), "UNTRUSTED"),
                 "tampered": (tampered, "TAMPERED"), "swapped": (swapped, "TAMPERED")}
        for label, (notice, verdict) in cases.items():
            with self.subTest(label):
                report = self.verify(notice)
                [entry] = report["revocation_notices"]
                self.assertEqual((entry["verdict"], entry["applied"]), (verdict, False))
                self.assertEqual(report["receipt_verdicts"]["VALID"], 7)  # nothing was revoked
                self.assertEqual(report["exit_code"], 1)  # unauthenticated material is reported

    def test_notice_without_a_pinned_authority_is_untrusted(self):
        doc = json.loads(self.run.trust.read_text())
        del doc["revocation_issuers"]
        plain = self.root / "plain-anchors.json"
        plain.write_text(json.dumps(doc))
        report = self.verify(self.revoke(-60), trust=plain)
        self.assertEqual((report["revocation_notices"][0]["verdict"], report["exit_code"]), ("UNTRUSTED", 1))
        self.assertEqual(self.receiver_verdicts(report), {"VALID"})

    def test_notice_for_an_unknown_key_has_no_effect(self):
        report = self.verify(self.revoke(-60, key_id="live-agent-z-00000000"))
        [entry] = report["revocation_notices"]
        self.assertEqual((entry["verdict"], entry["applied"], report["exit_code"]), ("VALID", False, 0))
        self.assertIn("nothing to revoke", entry["reasons"][0])

    def test_out_of_band_notice_file_and_cli(self):
        external = self.root / "notices.jsonl"
        external.write_bytes(canonicalize(self.revoke(-60)) + b"\n")
        report = self.verify(extra=[external])
        self.assertEqual(report["revocation_notices"][0]["source"], "notices.jsonl:1")
        self.assertEqual(self.receiver_verdicts(report), {"UNTRUSTED"})
        args = ("verify", "--trust", str(self.run.trust), "--now", "2026-10-16T12:01:00Z", str(self.run.bundle))
        self.assertEqual(run_module("agent_movement.receipts", *args).returncode, 0)
        cli = run_module("agent_movement.receipts", *args, "--revocations", str(external))
        self.assertEqual(cli.returncode, 1, cli.stdout + cli.stderr)
        self.assertIn("revocation notice notices.jsonl:1 [VALID] revokes", cli.stdout)
        missing = run_module("agent_movement.receipts", *args, "--revocations", str(self.root / "absent.jsonl"))
        self.assertEqual(missing.returncode, 2)

    def test_notice_corroborates_an_anchor_revocation_ref(self):
        notice = self.revoke(+60)
        doc = json.loads(self.run.trust.read_text())
        for key in doc["keys"]:
            if key["key_id"] == self.receiver_key:
                key.update(revoked_at="2026-10-16T13:00:00Z", revocation_ref=jcs_digest(notice))
        anchored = self.root / "anchored.json"
        anchored.write_text(json.dumps(doc))
        report = self.verify(notice, trust=anchored)
        self.assertIn("corroborates the trust anchor's revocation_ref", report["revocation_notices"][0]["reasons"])
        self.assertEqual(self.receiver_verdicts(report), {"VALID"})  # +60 s is still after issued_at


if __name__ == "__main__":
    unittest.main()
