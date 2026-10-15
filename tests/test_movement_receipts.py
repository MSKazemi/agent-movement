import copy
import filecmp
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

from agent_movement import receipts
from agent_movement.core import Approval, HandoffReceiver, SQLiteStore, digest
from agent_movement.jcs import CanonicalizationError, canonicalize, jcs_digest
from agent_movement.receipts import (HAVE_ED25519, ReceiptError, ReplayGuard, contains_token_like, parse_time,
                                     redact, render_text, validate_body, verify_bundle)
from test_core import fixture

FIXTURES = Path(__file__).parent / "fixtures" / "movement-receipts"
TRUST = FIXTURES / "trust.json"
NOW = parse_time("2026-10-16T00:00:00Z")
EXPECTED = json.loads((FIXTURES / "expected.json").read_text())
needs_ed25519 = unittest.skipUnless(HAVE_ED25519, 'optional extra not installed: pip install -e ".[signing]"')


def lines(path):
    return [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]


def write_bundle(root, receipt_wires=(), tool_wires=(), telemetry=()):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    for name, items in (("receipts.jsonl", receipt_wires), ("tool-records.jsonl", tool_wires),
                        ("telemetry.jsonl", telemetry)):
        if items:
            (root / name).write_bytes(b"".join(canonicalize(x) + b"\n" for x in items))
    return root


def cli(*args):
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")}
    return subprocess.run([sys.executable, "-m", "agent_movement.receipts", *args],
                          capture_output=True, text=True, env=env, timeout=60)


class CanonicalJsonTests(unittest.TestCase):
    def test_rfc8785_utf16_member_ordering(self):
        # RFC 8785 section 3.2.3 example: UTF-16 code-unit order, not code-point order.
        value = {"€": "Euro Sign", "\r": "Carriage Return", "דּ": "Hebrew Letter Dalet With Dagesh",
                 "1": "One", "\U0001F600": "Emoji: Grinning Face", "\u0080": "Control",
                 "ö": "Latin Small Letter O With Diaeresis"}
        order = list(json.loads(canonicalize(value)))
        self.assertEqual(order, ["\r", "1", "\u0080", "ö", "€", "\U0001F600", "דּ"])
        self.assertNotEqual(order, sorted(value))  # Python's code-point order differs here

    def test_rfc8785_string_escaping(self):
        # RFC 8785 section 3.2.2.2 example string.
        source = '"\\u20ac$\\u000F\\u000aA\'\\u0042\\u0022\\u005c\\\\\\"\\/"'
        self.assertEqual(canonicalize(json.loads(source)), '"€$\\u000f\\nA\'B\\"\\\\\\\\\\"/"'.encode())
        self.assertEqual(canonicalize({"b": [True, None, -3], "a": "x"}), b'{"a":"x","b":[true,null,-3]}')

    def test_outside_subset_rejected(self):
        for value in (1.5, 2 ** 53, {1: "x"}, "\ud800", {"a": float("nan")}, object()):
            with self.subTest(value=repr(value)):
                with self.assertRaises(CanonicalizationError):
                    canonicalize(value)

    def test_matches_pr6_digest_for_handoff_envelopes(self):
        envelope = fixture()
        envelope["task"]["text"] = "Grüße 世界\t\"quoted\" \U0001F600"
        self.assertEqual(jcs_digest(envelope), "sha256:" + digest(envelope))


class SchemaAndPrivacyTests(unittest.TestCase):
    def body(self):
        return copy.deepcopy(lines(FIXTURES / "01-valid-delegation" / "receipts.jsonl")[0]["receipt"])

    def test_schema_is_strict_and_unknown_is_explicit_null(self):
        validate_body(self.body())
        for mutate in (lambda b: b.update(prompt="free text"), lambda b: b.pop("source"),
                       lambda b: b["issuer"].update(claimed_principal="not a principal"),
                       lambda b: b.update(seq=True), lambda b: b.update(issued_at="2026-10-15 09:00"),
                       lambda b: b["movement"].update(lineage_relation="teleport"),
                       lambda b: b.update(data_classification="private")):
            body = self.body()
            mutate(body)
            with self.assertRaises(ReceiptError):
                validate_body(body)

    def test_redaction(self):
        jwt_shaped = ".".join(["eyJ" + "x" * 10, "eyJ" + "y" * 10, "z" * 8])
        clean, count = redact({"authorization": "anything", "nested": [f"token {jwt_shaped}", "ok"],
                               "note": "Bearer abc.def", "cookie": "a=b", "pem": "-----BEGIN PRIVATE KEY-----",
                               "gen_ai.prompt": "hello", "safe": "agent-b"})
        self.assertEqual(count, 6)
        self.assertEqual(clean["safe"], "agent-b")
        self.assertNotIn(jwt_shaped, json.dumps(clean))
        self.assertTrue(contains_token_like({"x": [f"{jwt_shaped}"]}))
        self.assertFalse(contains_token_like(self.body()))

    def test_privacy_fixture_never_leaks(self):
        report = verify_bundle(FIXTURES / "08-privacy-canaries", TRUST, NOW)
        rendered = json.dumps(report) + render_text(report)
        for needle in ("canary", "Bearer", "eyJhbGci", "prompt text", "session=", "api_key="):
            self.assertNotIn(needle, rendered)
        self.assertEqual(report["telemetry"]["redactions"], 6)
        self.assertEqual(report["receipt_verdicts"]["MALFORMED"], 2)
        for raw in (FIXTURES / "08-privacy-canaries" / "receipts.jsonl").read_text().splitlines()[:2]:
            self.assertNotIn("canary", raw)  # the valid receipts themselves are clean

    def test_runtime_canaries_redacted_from_cli_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            secret = "sk-" + "R" * 24
            write_bundle(tmp, telemetry=[{"trace_id": "a" * 32, "span_id": "b" * 16, "name": "tool.call",
                                          "time": "2026-10-15T09:00:00Z",
                                          "attributes": {"movement_id": secret, "x-api-key": secret,
                                                         "agent.claimed_id": f"Bearer {secret}"}}])
            (Path(tmp) / "receipts.jsonl").write_text(json.dumps({"receipt": {"note": secret}}) + "\n")
            result = cli("verify", tmp, "--trust", str(TRUST), "--json")
            self.assertNotIn(secret, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout)["telemetry"]["redactions"], 3)

    def test_fixtures_publish_no_unsalted_task_digests(self):
        published = "".join(p.read_text() for p in FIXTURES.rglob("*.jsonl"))
        for subject in FIXTURES.rglob("subjects/*.json"):
            doc = json.loads(subject.read_text())
            self.assertEqual(set(doc), {"commitment_salt", "value"})
            for unsalted in (jcs_digest(doc["value"]), digest(doc["value"])):
                self.assertNotIn(unsalted.split(":")[-1], published)

    def test_revocation_references_external_notice(self):
        report = verify_bundle(FIXTURES / "04-forged-identity", TRUST, NOW)
        reasons = {r["ref"]: r["reasons"] for r in report["receipts"]}["receipt:rcpt-mov-forged-2-dispatch"]
        self.assertTrue(any("revocation notice sha256:" in reason for reason in reasons), reasons)

    def test_fixtures_contain_only_synthetic_material(self):
        for path in FIXTURES.rglob("*"):
            if path.is_file():
                text = path.read_text()
                self.assertNotIn("PRIVATE KEY", text)
                for wire in (lines(path) if path.suffix == ".jsonl" and "telemetry" not in path.name else []):
                    if isinstance(wire.get("receipt"), dict) and "data_classification" in wire["receipt"]:
                        self.assertEqual(wire["receipt"]["data_classification"], "synthetic")


class WithoutSignatureSupportTests(unittest.TestCase):
    """Behaviour when the optional cryptography extra is absent (forced here)."""

    def verify(self, name):
        with mock.patch.object(receipts, "HAVE_ED25519", False):
            return verify_bundle(FIXTURES / name, TRUST, NOW)

    def test_unchecked_is_reported_not_trusted(self):
        report = self.verify("01-valid-delegation")
        self.assertEqual(report["receipt_verdicts"]["UNCHECKED"], 5)
        self.assertEqual(report["exit_code"], 3)
        self.assertEqual(report["timeline_status"]["VERIFIABLE"], 0)
        self.assertTrue(report["signature_checking"].startswith("UNAVAILABLE"))

    def test_digest_tampering_and_exact_replay_still_detected(self):
        tampered = {r["ref"]: r["verdict"] for r in self.verify("02-tampered-receipts")["receipts"]}
        self.assertEqual(tampered["receipt:rcpt-mov-tamper-1-started"], "TAMPERED")
        self.assertEqual(tampered["receipt:rcpt-mov-tamper-1-accept"], "UNCHECKED")  # needs the signature
        self.assertEqual(self.verify("03-replayed-receipts")["receipt_verdicts"]["REPLAYED"], 2)
        self.assertEqual(self.verify("08-privacy-canaries")["receipt_verdicts"]["MALFORMED"], 2)


@needs_ed25519
class FixtureSetTests(unittest.TestCase):
    def test_fixtures_regenerate_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(cli("make-fixtures", tmp).returncode, 0)
            compared = filecmp.dircmp(tmp, FIXTURES)

            def assert_same(cmp):
                self.assertEqual((cmp.left_only, cmp.right_only, cmp.diff_files), ([], [], []), cmp.left)
                _, mismatch, errors = filecmp.cmpfiles(cmp.left, cmp.right, cmp.common_files, shallow=False)
                self.assertEqual((mismatch, errors), ([], []))
                for sub in cmp.subdirs.values():
                    assert_same(sub)
            assert_same(compared)

    def test_each_scenario_matches_hand_written_expectations(self):
        self.assertEqual(sorted(EXPECTED), sorted(p.name for p in receipts.bundles_under(FIXTURES)))
        for name, spec in EXPECTED.items():
            with self.subTest(scenario=name):
                report = verify_bundle(FIXTURES / name, TRUST, NOW)
                self.assertEqual(report["exit_code"], spec["exit_code"])
                self.assertEqual({k: v for k, v in report["receipt_verdicts"].items() if v}, spec["receipt_verdicts"])
                self.assertEqual(report["timeline_status"], spec["timeline_status"])
                for mid, claims in spec.get("claims", {}).items():
                    for claim, status in claims.items():
                        got = report["movements"][mid][claim]
                        self.assertEqual(got if claim == "grade" else got["status"], status, (mid, claim))
                for effect, status in spec.get("effects", {}).items():
                    self.assertEqual({e["effect_id"]: e["status"] for e in report["effects"]}[effect], status)
                for ref, status in spec.get("subjects", {}).items():
                    self.assertEqual({s["ref"]: s["status"] for s in report["subjects"]}[ref], status)
                if "lineage" in spec:
                    self.assertEqual(len(report["lineage"]), spec["lineage"])
                if "timeline_order" in spec:
                    refs = [e["ref"].split(":", 1)[1] for e in report["timeline"] if e["ref"].startswith("receipt:")]
                    self.assertEqual(refs, spec["timeline_order"])

    def test_fork_keeps_executions_with_same_definition_distinct(self):
        report = verify_bundle(FIXTURES / "07-fork-lineage", TRUST, NOW)
        twins = [e for e in report["executions"] if e["shares_definition_with"]]
        self.assertEqual(len(twins), 2)
        self.assertEqual(len({e["execution_id"] for e in twins}), 2)
        self.assertEqual({e["relation"] for e in report["lineage"]}, {"fork"})

    def test_gap_and_unknowns_are_reported_not_filled(self):
        report = verify_bundle(FIXTURES / "05-missing-claims", TRUST, NOW)
        gaps = [e for e in report["timeline"] if e["event_type"] == "evidence.gap_detected"]
        self.assertEqual(len(gaps), 1)
        self.assertIn("2..3", gaps[0]["notes"][0])
        self.assertNotIn("E0", {e["grade"] for e in report["timeline"]})
        self.assertEqual(report["movements"]["mov-missing-1"]["trace_ids"]["value"], [])

    def test_cli_exit_codes_and_outputs(self):
        ok = cli("verify", str(FIXTURES / "01-valid-delegation"), "--now", "2026-10-16T00:00:00Z")
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertIn("5 VALID", ok.stdout)
        bad = cli("verify", str(FIXTURES / "02-tampered-receipts"), "--json")
        self.assertEqual(bad.returncode, 1)
        self.assertEqual(json.loads(bad.stdout)["receipt_verdicts"]["TAMPERED"], 2)
        whole = cli("verify", str(FIXTURES))
        self.assertEqual(whole.returncode, 1)
        self.assertEqual(sum(x.startswith("bundle ") for x in whole.stdout.splitlines()), len(EXPECTED))
        timeline = cli("timeline", str(FIXTURES / "09-clock-skew"))
        self.assertEqual([e["order"] for e in json.loads(timeline.stdout)], [1, 2, 3])
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copy(FIXTURES / "01-valid-delegation" / "receipts.jsonl", tmp)
            missing = cli("verify", tmp)
            self.assertEqual(missing.returncode, 2)
            self.assertIn("no trust anchors", missing.stderr)


@needs_ed25519
class AdversarialTests(unittest.TestCase):
    def setUp(self):
        from agent_movement import receipt_fixtures
        self.fx = receipt_fixtures
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.wires = lines(FIXTURES / "01-valid-delegation" / "receipts.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def verdicts(self, wires, name="bundle", tool_wires=(), telemetry=(), trust=TRUST):
        report = verify_bundle(write_bundle(self.root / name, wires, tool_wires, telemetry), trust, NOW)
        return report, [r["verdict"] for r in report["receipts"]]

    def test_every_leaf_mutation_is_rejected(self):
        original = self.wires[3]  # execution.completed: the richest body

        def leaves(value, path=()):
            if isinstance(value, dict):
                for k, v in value.items():
                    yield from leaves(v, path + (k,))
            elif isinstance(value, list):
                for i, v in enumerate(value):
                    yield from leaves(v, path + (i,))
            else:
                yield path, value

        count = 0
        for path, value in leaves(original["receipt"]):
            changed = copy.deepcopy(original)
            target = changed["receipt"]
            for step in path[:-1]:
                target = target[step]
            if isinstance(value, bool) or value is None:
                target[path[-1]] = "x" if value is None else not value
            elif isinstance(value, int):
                target[path[-1]] = value + 1
            else:
                target[path[-1]] = value[:-1] + ("0" if value[-1] != "0" else "1")
            changed["body_digest"] = jcs_digest(changed["receipt"])  # attacker re-computes the digest
            _, verdicts = self.verdicts([changed], name=f"m{count}")
            self.assertIn(verdicts[0], ("TAMPERED", "MALFORMED", "UNTRUSTED"), path)
            count += 1
        self.assertGreater(count, 30)

    def test_signature_block_substitution(self):
        swapped = copy.deepcopy(self.wires[0])
        swapped["signature"] = self.wires[1]["signature"]  # whole block: key_id no longer matches
        value_only = copy.deepcopy(self.wires[0])  # same signer, signature lifted from another receipt
        value_only["signature"]["value"] = lines(FIXTURES / "05-missing-claims" / "receipts.jsonl")[0]["signature"]["value"]
        _, verdicts = self.verdicts([swapped, value_only])
        self.assertEqual(verdicts, ["TAMPERED", "TAMPERED"])

    def test_replay_guard(self):
        guard = ReplayGuard(max_age=timedelta(minutes=5))
        args = ("k", "a" * 32, "r1", "sha256:1", 0, NOW, NOW)
        self.assertEqual(guard.check(*args), (None, None))
        self.assertEqual(guard.check(*args)[0], "duplicate")
        self.assertEqual(guard.check("k", "a" * 32, "r2", "sha256:2", 1, NOW, NOW)[0], "reuse")
        self.assertEqual(guard.check("k", "b" * 32, "r3", "sha256:3", 2, NOW - timedelta(hours=1), NOW)[0], "stale")

    def test_nonce_reuse_by_signer_is_equivocation(self):
        body = copy.deepcopy(self.wires[0]["receipt"])
        other = {**copy.deepcopy(body), "receipt_id": "rcpt-other", "outcome": "unknown"}  # same nonce
        report, verdicts = self.verdicts([self.fx.seal("agent-a", body), self.fx.seal("agent-a", other)])
        self.assertEqual(verdicts, ["VALID", "VALID"])
        self.assertEqual(report["timeline_status"]["CONFLICTING"], 2)
        self.assertEqual(report["exit_code"], 1)

    def test_trace_ids_are_correlation_only(self):
        trace = self.wires[0]["receipt"]["correlation"]["trace_id"]
        attacker = self.fx.Ed25519Signer("synthetic-attacker-key", b"\x01" * 32)
        forged = copy.deepcopy(self.wires[1]["receipt"])
        forged["issuer"]["key_id"] = attacker.key_id
        span = {"trace_id": trace, "span_id": "c" * 16, "name": "movement.accepted", "time": "2026-10-15T09:00:02Z",
                "attributes": {"agent.claimed_id": "agent-b", "movement_id": "mov-valid-1", "outcome": "accepted"}}
        report, verdicts = self.verdicts([self.wires[0], attacker.seal(forged)], telemetry=[span])
        self.assertEqual(verdicts, ["VALID", "UNTRUSTED"])
        movement = report["movements"]["mov-valid-1"]
        self.assertEqual(movement["destination_principal"]["status"], "SIGNED_CLAIM")  # named only, never verified
        self.assertEqual(movement["outcome"]["status"], "UNKNOWN")
        self.assertEqual(movement["trace_ids"]["status"], "CORRELATION_ONLY")
        telemetry = [e for e in report["timeline"] if e["ref"].startswith("telemetry:")]
        self.assertEqual((telemetry[0]["status"], telemetry[0]["actor"]["verified_principal"]), ("UNVERIFIABLE", None))
        # Two movements sharing one trace_id are never merged.
        second = copy.deepcopy(self.wires[0]["receipt"])
        second.update(receipt_id="rcpt-second", nonce="d" * 32, seq=2, prev_receipt_digest=self.wires[0]["body_digest"])
        second["movement"]["movement_id"] = "mov-valid-2"
        report, _ = self.verdicts([self.wires[0], self.fx.seal("agent-a", second)], name="shared-trace")
        self.assertEqual(sorted(report["movements"]), ["mov-valid-1", "mov-valid-2"])

    def test_bundle_supplied_trust_anchor_is_a_documented_limit(self):
        attacker = self.fx.Ed25519Signer("synthetic-attacker-key", b"\x02" * 32)
        body = copy.deepcopy(self.wires[1]["receipt"])
        body["issuer"]["key_id"] = attacker.key_id
        bundle = write_bundle(self.root / "evil", [attacker.seal(body)])
        doc = json.loads(TRUST.read_text())
        doc["keys"].append({**doc["keys"][1], "key_id": attacker.key_id, "public_key": attacker.public_key})
        (bundle / "trust.json").write_text(json.dumps(doc))
        self.assertEqual(verify_bundle(bundle, None, NOW)["receipt_verdicts"]["VALID"], 1)  # anchors from evidence!
        self.assertEqual(verify_bundle(bundle, TRUST, NOW)["receipt_verdicts"]["UNTRUSTED"], 1)

    def test_signer_refuses_credential_like_values(self):
        body = copy.deepcopy(self.wires[2]["receipt"])
        body["execution"]["agent_instance_id"] = "sk-" + "Q" * 20
        with self.assertRaises(ReceiptError):
            self.fx.signer("agent-b").seal(body)

    def test_pr6_receipt_wrapped_and_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "r.sqlite")
            core_receipt = HandoffReceiver("agent-b", store, [
                Approval("approval-1", "task-1", "agent-a", "agent-b", "word_count")]).receive(fixture())
        salt = "5" * 32
        body = receipts.body_from_handoff(core_receipt, key_id=self.fx.key_id("agent-b"),
                                          issued_at="2026-10-15T09:00:00Z", nonce="e" * 32, salt=salt,
                                          envelope=fixture(), destination_principal=self.fx.principal("agent-b"))
        published = json.dumps(body)
        for unsalted in (core_receipt["envelope_digest"], core_receipt["artifact_digest"]):
            self.assertNotIn(unsalted, published)  # PR #6 digests include guessable task content
        bundle = write_bundle(self.root / "pr6", [self.fx.seal("agent-b", body)])
        (bundle / "subjects").mkdir()
        (bundle / "subjects" / "env-movement-1.json").write_bytes(
            canonicalize(receipts.commitment(fixture(), salt)))
        report = verify_bundle(bundle, TRUST, NOW)
        self.assertEqual(report["receipt_verdicts"]["VALID"], 1)
        self.assertEqual({s["ref"]: s["status"] for s in report["subjects"]},
                         {"env-movement-1": "DIGEST_MATCH", "art-movement-1": "UNKNOWN"})
        self.assertEqual(report["movements"]["movement-1"]["source_agent_label"]["status"], "SIGNED_CLAIM")
        self.assertEqual(report["movements"]["movement-1"]["source_principal"]["status"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
