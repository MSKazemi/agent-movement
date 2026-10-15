"""MobilityBench v0.1: frozen fixtures, baseline semantics, sanitization and CLI."""
import contextlib
import dataclasses
import io
import json
import shutil
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from agent_movement import mobilitybench, mobilitybench_v01 as mb
from agent_movement.core import canonical


def _cli(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = mobilitybench.main(argv)
    return code, out.getvalue(), err.getvalue()


class FixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx = mb.load_fixtures("v0.1")

    def test_release_manifest_verifies(self):
        manifest = mb.verify_fixtures(mb.fixture_dir("v0.1"))
        self.assertEqual(manifest["release_digest"], mb.release_digest(mb.file_digests(self.fx.directory)))
        self.assertEqual(set(manifest["files"]), set(mb.FIXTURE_FILES))

    def test_tampered_copy_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            copy = Path(d) / "fx"
            shutil.copytree(self.fx.directory, copy)
            seeds = copy / "seeds.json"
            seeds.write_text(seeds.read_text(encoding="utf-8").replace("1103", "1104", 1), encoding="utf-8")
            with self.assertRaises(mb.FixtureError):
                mb.verify_fixtures(copy)
            code, _, err = _cli(["verify", "--fixtures", str(copy)])
            self.assertEqual(code, 2)
            self.assertIn("fixture_verification_failed", err)
            with self.assertRaises(mb.FixtureError):
                mb.run_suite(fixtures=copy, subset="smoke")

    def test_three_workload_families_with_effects_and_ground_truth(self):
        families = Counter(t["family"] for t in self.fx.tasks)
        self.assertEqual(set(families), set(mb.FAMILIES))
        self.assertTrue(all(n >= 5 for n in families.values()), families)
        for task in self.fx.tasks:
            self.assertTrue(any(op["op"] in ("effect", "reserve") for op in task["plan"]), task["task_id"])
            self.assertIn(task["task_id"], self.fx.truth)
        delegable_tail = {t["family"] for t in self.fx.tasks
                          if all(op["op"] in mb.DELEGABLE for op in t["plan"][t["movement_at"]:])}
        self.assertEqual(delegable_tail, set(mb.FAMILIES))

    def test_ground_truth_reproduces_and_satisfies_every_rule(self):
        for task in self.fx.tasks:
            with self.subTest(task=task["task_id"]):
                fresh = mb.build_ground_truth(task)
                self.assertEqual(fresh, self.fx.truth[task["task_id"]])
                with tempfile.TemporaryDirectory() as d:
                    record = mb.run_attempt(task, fresh, "keep_on_origin", "none", Path(d) / "a")
                self.assertTrue(record["task_correct"])
                self.assertEqual(record["constraints_preserved"], record["constraints_total"])
                self.assertEqual(record["policy_violations"], 0)

    def test_fault_schedule_is_seeded_balanced_and_stable(self):
        ids = [t["task_id"] for t in self.fx.tasks]
        first = mb.fault_schedule(ids, [1103, 2207])
        self.assertEqual(first, mb.fault_schedule(list(reversed(ids)), [1103, 2207]))
        for seed in (1103, 2207):
            counts = Counter(first[(seed, t)] for t in ids)
            self.assertEqual(set(counts), set(mb.FAULT_KINDS))
            self.assertLessEqual(max(counts.values()) - min(counts.values()), 1)
        self.assertNotEqual([first[(1103, t)] for t in ids], [first[(2207, t)] for t in ids])


class BaselineSemanticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx = mb.load_fixtures("v0.1")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.n = 0

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def attempt(self, task_id, mode, fault="none"):
        type(self).n += 1
        task = next(t for t in self.fx.tasks if t["task_id"] == task_id)
        return mb.run_attempt(task, self.fx.truth[task_id], mode, fault, Path(self.tmp.name) / str(self.n))

    def test_restart_loses_mid_session_constraint_and_duplicates_effect(self):
        rec = self.attempt("doc-release-notes", "restart_on_destination")
        self.assertEqual(rec["outcome"], "completed")
        self.assertFalse(rec["task_correct"])
        self.assertEqual((rec["constraints_preserved"], rec["constraints_total"]), (0, 1))
        self.assertEqual(rec["duplicate_effects"], 1)
        self.assertGreater(rec["sensitive_transfers"], 0)

    def test_correct_output_can_hide_a_duplicate_booking(self):
        rec = self.attempt("tools-travel-booking", "restart_on_destination")
        self.assertTrue(rec["output_correct"])
        self.assertEqual(rec["duplicate_effects"], 1)
        self.assertFalse(rec["task_correct"])

    def test_restart_lost_policy_counts_violation(self):
        rec = self.attempt("tools-refund-sim", "restart_on_destination")
        self.assertGreaterEqual(rec["policy_violations"], 1)

    def test_restart_is_correct_when_nothing_precedes_movement(self):
        self.assertTrue(self.attempt("doc-policy-digest", "restart_on_destination")["task_correct"])

    def test_keep_preempted_is_incomplete_not_wrong(self):
        rec = self.attempt("doc-release-notes", "keep_on_origin", "origin_preempted")
        self.assertEqual(rec["outcome"], "incomplete")
        self.assertIsNone(rec["task_correct"])
        self.assertTrue(rec["fault_applied"])

    def test_local_delegate_uses_pr6_receiver_and_deduplicates(self):
        rec = self.attempt("code-version-bump", "local_delegate", "duplicate_delivery")
        self.assertTrue(rec["task_correct"])
        self.assertEqual(rec["duplicate_deliveries_suppressed"], 2)
        self.assertEqual(rec["transfer_messages"], 8)  # 2 envelopes + 2 receipts, each delivered twice

    def test_local_delegate_refuses_incompatible_state(self):
        rec = self.attempt("code-rename-helper", "local_delegate")
        self.assertEqual(rec["outcome"], "refused")
        self.assertTrue(rec["reason"].startswith("incompatible_state:"))
        self.assertEqual(rec["transfer_bytes"], 0)

    def test_ack_loss_is_reconciled_not_recommitted(self):
        rec = self.attempt("tools-travel-booking", "keep_on_origin", "effect_ack_lost")
        self.assertEqual((rec["unknown_events"], rec["reconciled_events"]), (1, 1))
        self.assertTrue(rec["task_correct"])

    def test_stale_origin_is_fenced(self):
        rec = self.attempt("tools-restock-order", "restart_on_destination", "stale_origin_returns")
        self.assertEqual((rec["stale_commits_fenced"], rec["stale_commits_accepted"]), (1, 0))

    def test_unavailable_modes_are_explicit(self):
        for mode in ("a2a_delegate", "checkpoint_relocate", "cross_framework_reconstruct"):
            rec = self.attempt("doc-release-notes", mode)
            self.assertEqual((rec["outcome"], rec["mode_status"]), ("unavailable", "unavailable"))
            self.assertIsNone(rec["task_correct"])
            self.assertNotEqual(rec["tracking"], "-")


class SuiteRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = mb.run_suite("v0.1")  # full suite, manifest seeds and repeats

    def attempts(self, repeat=0):
        return [r for r in self.records if r["record_type"] == "attempt" and r["repeat"] == repeat]

    def test_denominators_cover_every_task_seed_and_mode(self):
        manifest = self.records[0]
        self.assertEqual(manifest["record_type"], "run_manifest")
        self.assertEqual(manifest["repeats"], 2)
        expected = len(manifest["tasks"]) * len(manifest["seeds"]) * len(mb.MODES)
        self.assertEqual(len(self.attempts(0)), expected)
        self.assertEqual(len(self.attempts(1)), expected)
        keys = Counter((r["seed"], r["task_id"]) for r in self.attempts())
        self.assertTrue(all(n == len(mb.MODES) for n in keys.values()))

    def test_no_harness_errors_and_security_verdicts(self):
        # Counts derive from the frozen fixture expectations, not literals: a gap closed by a
        # later issue (e.g. #8) moves from known_gap to gap_closed without breaking this test.
        negatives = mb.load_fixtures("v0.1").negatives
        summary = mb.summarize(self.records)
        self.assertEqual(summary["harness_errors"], 0)
        self.assertEqual(summary["security"]["fail"], 0)
        self.assertEqual(summary["security_total"], len(negatives))
        self.assertEqual(summary["security"]["pass"], sum(not c["known_gap"] for c in negatives))
        self.assertEqual(summary["security"]["known_gap"] + summary["security"]["gap_closed"],
                         sum(c["known_gap"] for c in negatives))
        self.assertEqual(mb.run_exit_code(self.records), 0)

    def test_repeats_and_reruns_are_deterministic(self):
        self.assertEqual(mb.reproducibility(self.records)["mismatched"], [])
        again = mb.run_suite("v0.1", repeats=1)
        def fingerprints(rows):
            return [(r["seed"], r["task_id"], r["mode"], r["outcome_fingerprint"])
                    for r in rows if r["record_type"] == "attempt"]
        self.assertEqual(fingerprints(again), fingerprints(self.attempts()))

    def test_two_baselines_meaningfully_differ(self):
        modes = mb.summarize(self.records)["modes"]
        keep, restart = modes["keep_on_origin"], modes["restart_on_destination"]
        self.assertEqual(keep["task_correct"], keep["completed"])
        self.assertLess(keep["completed"], keep["attempts"])  # preemption hurts keep
        self.assertEqual(restart["completed"], restart["attempts"])  # restart survives preemption
        self.assertLess(restart["task_correct"], restart["completed"])  # ... at a correctness cost
        self.assertGreater(restart["duplicate_effects"], 0)
        self.assertEqual(modes["local_delegate"]["policy_violations"], 0)

    def test_records_are_sanitized(self):
        fx = mb.load_fixtures("v0.1")
        blob = canonical(self.records)
        for secret in mb.sensitive_strings(fx):
            self.assertNotIn(secret, blob)
        for record in self.attempts():
            self.assertNotIn("text", record)
            self.assertNotIn("payload", record)
            self.assertEqual(record["model_calls"], 0)
            for key in ("suite_version", "fixture_release_digest", "contract_version", "python"):
                self.assertIn(key, record["run_version"])

    def test_report_has_denominators_unavailable_and_raw_rows(self):
        report = mb.build_report(self.records)
        for needle in ("## Denominators", "**UNAVAILABLE** (issue #7)", "**UNAVAILABLE** (issue #9)",
                       "## Raw per-case results", "known_gap", "correct / attempts",
                       "no confidence intervals"):
            self.assertIn(needle, report)
        raw_rows = [line for line in report.splitlines() if line.startswith("| 1103 | ")]
        self.assertEqual(len(raw_rows), len(self.records[0]["tasks"]) * len(mb.MODES))


class IsolationAndDeterminismTests(unittest.TestCase):
    def test_security_cases_are_order_independent(self):
        fx = mb.load_fixtures("v0.1")
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            forward = mb.run_security_cases(fx, Path(a), timing=False)
            backward = mb.run_security_cases(dataclasses.replace(fx, negatives=fx.negatives[::-1]),
                                             Path(b), timing=False)
        self.assertEqual(sorted(map(canonical, forward)), sorted(map(canonical, backward)))

    def test_closed_gap_is_reported_not_passed_or_failed(self):
        fx = mb.load_fixtures("v0.1")
        case = {"case_id": "synthetic-closed-gap", "attack": "forged_destination", "mode": "local_delegate",
                "task": None, "expected": "accepted", "known_gap": True, "closed_observation": "denied",
                "question_ids": ["Q3"], "description": "test-only"}
        with tempfile.TemporaryDirectory() as d:
            [record] = mb.run_security_cases(dataclasses.replace(fx, negatives=[case]), Path(d))
        self.assertEqual((record["observed"], record["verdict"]), ("denied", "gap_closed"))

    def test_timing_free_output_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as d:
            outputs = []
            for name in ("one.jsonl", "two.jsonl"):
                code, _, err = _cli(["run", "--subset", "smoke", "--no-timing", "--out", str(Path(d) / name)])
                self.assertEqual(code, 0, err)
                outputs.append((Path(d) / name).read_bytes())
            self.assertEqual(outputs[0], outputs[1])
            self.assertNotIn(b'"elapsed_ms": 0.', outputs[0])
            rows = [json.loads(line) for line in outputs[0].decode("utf-8").splitlines()]
            self.assertTrue(all(r.get("elapsed_ms") is None for r in rows if r["record_type"] != "run_manifest"))
            self.assertEqual(mb.outcome_digest(rows), json.loads(err)["outcome_digest"])


class CliTests(unittest.TestCase):
    def test_run_smoke_report_verify_and_legacy_entrypoint(self):
        with tempfile.TemporaryDirectory() as d:
            out, report = Path(d) / "results.jsonl", Path(d) / "report.md"
            code, _, err = _cli(["run", "--suite", "v0.1", "--subset", "smoke", "--out", str(out)])
            self.assertEqual(code, 0, err)
            rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
            attempts = [r for r in rows if r["record_type"] == "attempt"]
            self.assertEqual(len(attempts), 6 * len(mb.MODES))
            self.assertEqual(json.loads(err)["subset"], "smoke")
            code, _, _ = _cli(["report", "--in", str(out), "--out", str(report)])
            self.assertEqual(code, 0)
            self.assertIn("MobilityBench v0.1 report", report.read_text(encoding="utf-8"))
            code, stdout, _ = _cli(["verify", "--suite", "v0.1"])
            self.assertEqual(code, 0)
            self.assertTrue(json.loads(stdout)["verified"])
            code, stdout, _ = _cli(["schedule", "--subset", "smoke"])
            self.assertEqual(code, 0)
            self.assertEqual(len(stdout.splitlines()), 6)
            legacy = Path(d) / "legacy.jsonl"
            code, _, _ = _cli(["--output", str(legacy)])
            self.assertEqual(code, 0)
            self.assertEqual(len(legacy.read_text(encoding="utf-8").splitlines()), 20)


if __name__ == "__main__":
    unittest.main()
