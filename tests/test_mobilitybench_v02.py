"""MobilityBench v0.2 (issue #40): mid-step crashes, partitions and the restart_stable_ids baseline.

The core-mode tests run everywhere; the B2 (A2A) and B3 (relocation) fault tests skip unless
their optional extra is installed: python -m pip install -e '.[a2a,relocation]'
"""
import contextlib
import dataclasses
import io
import json
import shutil
import sqlite3
import sys
import tempfile
import unittest
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar
from unittest import mock

from agent_movement import mobilitybench
from agent_movement import mobilitybench_v01 as mb
from agent_movement.core import SQLiteStore, canonical

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import mobilitybench_freeze  # noqa: E402

HAVE_A2A = mb.extra_available("a2a")
HAVE_RELOCATION = mb.extra_available("relocation")
# v0.1 release digest pinned in docs/mobilitybench-v0.1.md; v0.2 must never change it.
V01_RELEASE_DIGEST = "920e9a2f4a7117729cba9f028c4c1ab394c9edbef4dd8fb10e49dda0ecc9a001"
# Timing-free outcome digests of the v0.1 smoke subset under harness 0.2.0 (before issue #40),
# without extras (B2/B3 unavailable) and with both extras installed.
V01_SMOKE_DIGEST_CORE = "db658036834efe6b74b4ec0c8322880ff86b7cc2439787d58d923114b0aea9aa"
V01_SMOKE_DIGEST_EXTRAS = "d9f809cc6f94689a705f51000b9f88f3e634a123521c4b504b3df2bd413ff5cb"


def _cli(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = mobilitybench.main(argv)
    return code, out.getvalue(), err.getvalue()


def _quiet(func: Callable[..., Any], *args: Any) -> Any:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return func(*args)


class V02FixtureTests(unittest.TestCase):
    fx: ClassVar[mb.Fixtures]

    @classmethod
    def setUpClass(cls) -> None:
        cls.fx = mb.load_fixtures("v0.2")

    def test_v02_release_verifies_and_v01_release_is_unchanged(self) -> None:
        manifest = mb.verify_fixtures(mb.fixture_dir("v0.2"), "v0.2")
        self.assertEqual(manifest["suite_version"], "mobilitybench-v0.2")
        self.assertEqual(set(manifest["files"]), set(mb.FIXTURE_FILES) | {"schedule.jsonl"})
        self.assertEqual(mb.verify_fixtures(mb.fixture_dir("v0.1"))["release_digest"], V01_RELEASE_DIGEST)
        with self.assertRaises(mb.FixtureError):  # a release only verifies as its own suite
            mb.verify_fixtures(mb.fixture_dir("v0.2"), "v0.1")
        for suite in ("v0.1", "v0.2"):
            self.assertEqual(_quiet(mobilitybench_freeze.main, ["--suite", suite, "--check"]), 0, suite)

    def test_tasks_and_ground_truth_are_paired_with_v01(self) -> None:
        v01, v02 = mb.fixture_dir("v0.1"), mb.fixture_dir("v0.2")
        for name in ("tasks.jsonl", "ground_truth.jsonl"):
            self.assertEqual((v01 / name).read_bytes(), (v02 / name).read_bytes(), name)

    def test_frozen_schedule_matches_the_seeded_generator(self) -> None:
        rows = mb.schedule_rows(self.fx.tasks, self.fx.seeds["seeds"], "v0.2")
        self.assertEqual(len(rows), len(self.fx.tasks) * len(self.fx.seeds["seeds"]))
        self.assertEqual(self.fx.schedule, {(r["seed"], r["task_id"]): r for r in rows})
        tasks = {t["task_id"]: t for t in self.fx.tasks}
        for row in rows:
            if row["fault"] in mb.CRASH_KINDS:
                self.assertIn(row["crash_step"], mb.effect_steps(tasks[row["task_id"]]))
            else:
                self.assertIsNone(row["crash_step"])

    def test_schedule_is_balanced_and_covers_every_fault_per_seed(self) -> None:
        schedule = self.fx.schedule
        assert schedule is not None  # v0.2 fixtures always carry schedule.jsonl
        for seed in self.fx.seeds["seeds"]:
            counts = Counter(r["fault"] for k, r in schedule.items() if k[0] == seed)
            self.assertEqual(set(counts), set(mb.FAULT_KINDS_V02), seed)
            self.assertLessEqual(max(counts.values()) - min(counts.values()), 1)
        smoke = self.fx.seeds["smoke"]
        covered = {schedule[(smoke["seeds"][0], t)]["fault"] for t in smoke["tasks"]}
        self.assertEqual(covered, set(mb.FAULT_KINDS_V02))

    def test_schedule_edited_under_a_consistent_manifest_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            copy = Path(d) / "fx"
            shutil.copytree(self.fx.directory, copy)
            path = copy / "schedule.jsonl"
            path.write_text(path.read_text(encoding="utf-8").replace(
                '"fault": "none"', '"fault": "origin_preempted"', 1), encoding="utf-8")
            with self.assertRaises(mb.FixtureError):  # digest mismatch
                mb.load_fixtures("v0.2", copy)
            files = mb.file_digests(copy, mb.SUITE_SPECS["v0.2"].files)
            manifest = json.loads((copy / mb.MANIFEST_NAME).read_text(encoding="utf-8"))
            manifest.update(files=files, release_digest=mb.release_digest(files))
            (copy / mb.MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")
            mb.verify_fixtures(copy, "v0.2")  # the digests now agree ...
            with self.assertRaisesRegex(mb.FixtureError, "schedule differs"):  # ... the generator does not
                mb.load_fixtures("v0.2", copy)


class _Attempts(unittest.TestCase):
    fx: ClassVar[mb.Fixtures]
    tmp: ClassVar[tempfile.TemporaryDirectory[str]]
    n: ClassVar[int]

    @classmethod
    def setUpClass(cls) -> None:
        cls.fx = mb.load_fixtures("v0.2")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.n = 0

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def attempt(self, task_id: str, mode: str, fault: str = "none",
                crash_step: int | None = None) -> tuple[dict[str, Any], Path]:
        type(self).n += 1
        workdir = Path(self.tmp.name) / f"a{self.n}"
        task = next(t for t in self.fx.tasks if t["task_id"] == task_id)
        return mb.run_attempt(task, self.fx.truth[task_id], mode, fault, workdir, "v0.2", crash_step), workdir


class MidStepCrashTests(_Attempts):
    def test_crash_after_commit_duplicates_only_with_fresh_ids(self) -> None:
        # code-test-fixture commits at step 1 before its move at step 2; the origin dies after the
        # commit is durable but before the ack, so the task moves at once.
        fresh, _ = self.attempt("code-test-fixture", "restart_on_destination", "crash_after_effect_commit", 1)
        stable, _ = self.attempt("code-test-fixture", "restart_stable_ids", "crash_after_effect_commit", 1)
        for rec in (fresh, stable):
            self.assertEqual((rec["outcome"], rec["fault_applied"], rec["crash_step"]), ("completed", True, 1))
            self.assertEqual(rec["steps_reexecuted"], 2)  # steps 0 and 1 ran on the crashed origin
        self.assertEqual((fresh["duplicate_effects"], fresh["task_correct"]), (1, False))
        self.assertEqual((stable["duplicate_effects"], stable["effect_id_conflicts"], stable["task_correct"]),
                         (0, 0, True))

    def test_keep_cannot_recover_and_the_phase_decides_what_is_committed(self) -> None:
        before, _ = self.attempt("code-test-fixture", "keep_on_origin", "crash_before_effect_commit", 1)
        after, _ = self.attempt("code-test-fixture", "keep_on_origin", "crash_after_effect_commit", 1)
        for rec in (before, after):
            self.assertEqual((rec["outcome"], rec["reason"], rec["task_correct"]),
                             ("incomplete", "origin_crashed_no_recovery", None))
        self.assertEqual((before["effects_committed"], after["effects_committed"]), (0, 1))

    def test_delegate_origin_crash_is_incomplete(self) -> None:
        rec, _ = self.attempt("code-test-fixture", "local_delegate", "crash_after_effect_commit", 1)
        self.assertEqual((rec["outcome"], rec["reason"]), ("incomplete", "origin_crashed_owner_not_transferred"))
        self.assertEqual(rec["transfer_bytes"], 0)

    def test_destination_crash_restarts_from_zero_and_loses_heard_events(self) -> None:
        # code-guard-config moves at 1, hears forbid_path@2 on the destination and commits at 4.
        # The destination dies after that commit; its restart no longer hears forbid_path@2.
        fresh, _ = self.attempt("code-guard-config", "restart_on_destination", "crash_after_effect_commit", 4)
        stable, _ = self.attempt("code-guard-config", "restart_stable_ids", "crash_after_effect_commit", 4)
        clean, _ = self.attempt("code-guard-config", "restart_on_destination")
        self.assertTrue(clean["task_correct"])
        for rec in (fresh, stable):
            self.assertEqual((rec["outcome"], rec["constraints_preserved"], rec["task_correct"]),
                             ("completed", 0, False))
            self.assertEqual(rec["steps_reexecuted"], 6)  # origin step 0 + the first 5-step destination run
        self.assertEqual((fresh["duplicate_effects"], fresh["unexpected_effects"]), (1, 1))
        # Stable IDs: the re-issued payload differs, the gateway refuses it and the ledger keeps the first.
        self.assertEqual((stable["duplicate_effects"], stable["unexpected_effects"], stable["effect_id_conflicts"]),
                         (0, 0, 1))

    def test_crash_fires_at_the_first_effect_intent_even_on_the_destination(self) -> None:
        # tools-restock-order: the origin skips its step-2 reserve (forbid_tool@2), so it forms no
        # intent there; restart lost that policy, forms the intent and is the one that crashes.
        keep, _ = self.attempt("tools-restock-order", "keep_on_origin", "crash_before_effect_commit", 2)
        self.assertEqual((keep["fault_applied"], keep["fault_not_applied_reason"], keep["task_correct"]),
                         (False, "no_effect_intent_at_crash_step", True))
        restart, _ = self.attempt("tools-restock-order", "restart_on_destination", "crash_before_effect_commit", 2)
        self.assertTrue(restart["fault_applied"])
        self.assertGreaterEqual(restart["policy_violations"], 1)


class StableIdBaselineTests(_Attempts):
    def test_stable_ids_remove_the_restart_duplicate(self) -> None:
        fresh, _ = self.attempt("tools-travel-booking", "restart_on_destination")
        stable, _ = self.attempt("tools-travel-booking", "restart_stable_ids")
        self.assertEqual((fresh["duplicate_effects"], fresh["task_correct"]), (1, False))
        self.assertEqual((stable["duplicate_effects"], stable["task_correct"]), (0, True))
        self.assertEqual(stable["baseline"], "B1-stable")

    def test_divergent_payload_is_a_conflict_and_the_ledger_keeps_the_first(self) -> None:
        rec, workdir = self.attempt("doc-release-notes", "restart_stable_ids")
        self.assertEqual((rec["effect_id_conflicts"], rec["duplicate_effects"], rec["unexpected_effects"]), (1, 0, 0))
        self.assertFalse(rec["task_correct"])  # the restart still lost the mid-session redaction
        with sqlite3.connect(workdir / "effects.sqlite") as db:
            rows = db.execute("SELECT effect_id, payload_digest, epoch FROM effects").fetchall()
        expected = self.fx.truth["doc-release-notes"]["expected_effects"]
        # The ledger stores a keyed commitment to the payload's SHA-256 (store layout v2, issue #39).
        commitment = SQLiteStore(workdir / "effects.sqlite").keyed_digest(expected[0]["payload_digest"])
        self.assertEqual(rows, [("doc-release-notes.e2", commitment, 1)])

    def test_stable_variant_is_a_v02_mode_only(self) -> None:
        self.assertNotIn("restart_stable_ids", mb.modes_for("v0.1"))
        self.assertEqual(list(mb.modes_for("v0.2"))[:3],
                         ["keep_on_origin", "restart_on_destination", "restart_stable_ids"])


class PartitionTests(_Attempts):
    def test_dropped_request_is_retried_once(self) -> None:
        clean, _ = self.attempt("code-version-bump", "local_delegate")
        rec, _ = self.attempt("code-version-bump", "local_delegate", "partition_drop_request")
        self.assertTrue(rec["task_correct"])
        self.assertEqual((rec["messages_dropped"], rec["retries"]), (1, 1))
        self.assertEqual(rec["transfer_messages"], clean["transfer_messages"] + 1)
        self.assertEqual(rec["duplicate_deliveries_suppressed"], 0)  # the lost copy was never received

    def test_lost_receipt_is_answered_by_a_replay(self) -> None:
        rec, workdir = self.attempt("code-version-bump", "local_delegate", "partition_drop_reply")
        self.assertTrue(rec["task_correct"])
        self.assertEqual((rec["messages_dropped"], rec["retries"], rec["duplicate_deliveries_suppressed"]), (1, 1, 1))
        events = Counter(e["event_type"] for e in SQLiteStore(workdir / "receiver.sqlite").audit())
        self.assertEqual(events["handoff.completed"], 2)  # two delegated steps, each executed exactly once

    def test_delayed_original_arrives_late_and_is_deduplicated(self) -> None:
        for task_id, mode in (("doc-policy-digest", "restart_on_destination"),
                              ("code-version-bump", "local_delegate")):
            with self.subTest(mode=mode):
                rec, _ = self.attempt(task_id, mode, "partition_delay")
                self.assertTrue(rec["task_correct"])
                self.assertEqual((rec["messages_delayed"], rec["retries"], rec["duplicate_deliveries_suppressed"]),
                                 (1, 1, 1))

    def test_modes_that_cannot_be_faulted_say_why(self) -> None:
        cases = (("doc-release-notes", "keep_on_origin", "partition_delay", "no_transfer_channel"),
                 ("doc-release-notes", "keep_on_origin", "stale_origin_returns", "no_ownership_transfer"),
                 ("doc-policy-digest", "restart_on_destination", "partition_drop_reply", "no_reply_message"),
                 ("doc-release-notes", "local_delegate", "stale_origin_returns", "origin_remains_owner"),
                 ("code-rename-helper", "local_delegate", "partition_drop_request",
                  "attempt_ended_before_fault_point"),
                 ("doc-release-notes", "cross_framework_reconstruct", "partition_delay", "mode_unavailable"))
        for task_id, mode, fault, reason in cases:
            with self.subTest(mode=mode, fault=fault):
                rec, _ = self.attempt(task_id, mode, fault)
                self.assertEqual((rec["fault_applied"], rec["fault_not_applied_reason"]), (False, reason))

    def test_v01_records_keep_exactly_their_v01_fields(self) -> None:
        task = self.fx.tasks[0]
        with tempfile.TemporaryDirectory() as d:
            v01 = mb.run_attempt(task, self.fx.truth[task["task_id"]], "local_delegate", "none", Path(d) / "a")
            v02 = mb.run_attempt(task, self.fx.truth[task["task_id"]], "local_delegate", "none", Path(d) / "b",
                                 "v0.2")
        self.assertFalse(set(mb.V02_RECORD_FIELDS) & set(v01))
        self.assertEqual(set(v02) - set(v01), set(mb.V02_RECORD_FIELDS))
        with tempfile.TemporaryDirectory() as d, self.assertRaises(mb.FixtureError):  # v0.2 faults stay in v0.2
            mb.run_attempt(task, self.fx.truth[task["task_id"]], "local_delegate", "partition_delay", Path(d) / "c")


@unittest.skipUnless(HAVE_RELOCATION, "optional relocation extra not installed (pip install -e '.[relocation]')")
class CheckpointRelocateFaultTests(_Attempts):
    def relocation_modes(self, workdir: Path) -> list[str]:
        with sqlite3.connect(workdir / "effects.sqlite") as db:
            return [row[0] for row in db.execute("SELECT mode FROM relocations")]

    def test_origin_crash_fails_over_and_reexecutes_the_step_once(self) -> None:
        for fault in mb.CRASH_KINDS:
            with self.subTest(fault=fault):
                rec, workdir = self.attempt("code-test-fixture", "checkpoint_relocate", fault, 1)
                self.assertEqual((rec["outcome"], rec["task_correct"], rec["fault_applied"]), ("completed", True, True))
                self.assertEqual((rec["steps_reexecuted"], rec["duplicate_effects"]), (1, 0))
                self.assertEqual(self.relocation_modes(workdir), ["failover"])

    def test_destination_crash_resumes_from_its_own_head(self) -> None:
        rec, workdir = self.attempt("code-guard-config", "checkpoint_relocate", "crash_after_effect_commit", 4)
        self.assertEqual((rec["task_correct"], rec["steps_reexecuted"], rec["duplicate_effects"]), (True, 1, 0))
        self.assertEqual(rec["constraints_preserved"], rec["constraints_total"])
        self.assertEqual(self.relocation_modes(workdir), ["cooperative"])

    def test_partitions_on_the_relocation_request(self) -> None:
        expected = {"partition_drop_request": (1, 0, 0), "partition_drop_reply": (1, 0, 1),
                    "partition_delay": (0, 1, 1)}
        for fault, (dropped, delayed, suppressed) in expected.items():
            with self.subTest(fault=fault):
                rec, workdir = self.attempt("code-version-bump", "checkpoint_relocate", fault)
                self.assertTrue(rec["task_correct"])
                self.assertEqual((rec["messages_dropped"], rec["messages_delayed"],
                                  rec["duplicate_deliveries_suppressed"]), (dropped, delayed, suppressed))
                self.assertEqual(len(self.relocation_modes(workdir)), 1)  # one movement, however many copies


@unittest.skipUnless(HAVE_A2A, "optional A2A extra not installed (pip install -e '.[a2a]')")
class A2ADelegateFaultTests(_Attempts):
    def test_lost_receipt_over_a2a_is_a_replayed_task(self) -> None:
        rec, workdir = self.attempt("code-version-bump", "a2a_delegate", "partition_drop_reply")
        self.assertTrue(rec["task_correct"])
        self.assertEqual((rec["messages_dropped"], rec["duplicate_deliveries_suppressed"]), (1, 1))
        from agent_movement.a2a_profile import A2ACorrelationLog
        self.assertEqual(sorted(r["outcome"] for r in A2ACorrelationLog(workdir / "receiver.sqlite").rows()),
                         ["completed", "completed", "replayed"])


class V02NegativeFixtureTests(unittest.TestCase):
    NEW: ClassVar[dict[str, str]] = {"neg-stable-id-divergent-payload": "ledger_kept_first_payload",
           "neg-lost-receipt-replay": "replayed_not_reexecuted",
           "neg-runtime-revocation-at-effect": "rejected",
           "neg-crash-zombie-commit": "fenced"}

    def test_new_cases_pass_in_isolation_and_v01_cases_keep_their_expectations(self) -> None:
        fx = mb.load_fixtures("v0.2")
        v01 = {c["case_id"]: c for c in mb.load_fixtures("v0.1").negatives}
        self.assertEqual({c["case_id"] for c in fx.negatives}, set(v01) | set(self.NEW))
        for case in fx.negatives:
            if case["case_id"] in v01:
                same = {k: v for k, v in case.items() if k != "question_ids"}
                self.assertEqual(same, {k: v for k, v in v01[case["case_id"]].items() if k != "question_ids"})
                continue
            with self.subTest(case=case["case_id"]), tempfile.TemporaryDirectory() as d:
                [record] = mb.run_security_cases(dataclasses.replace(fx, negatives=[case]), Path(d), timing=False)
                self.assertEqual((record["observed"], record["verdict"]), (self.NEW[case["case_id"]], "pass"))

    def test_static_revocation_stays_a_known_gap(self) -> None:
        fx = mb.load_fixtures("v0.2")
        case = next(c for c in fx.negatives if c["case_id"] == "neg-revocation-not-at-effect")
        with tempfile.TemporaryDirectory() as d:
            [record] = mb.run_security_cases(dataclasses.replace(fx, negatives=[case]), Path(d), timing=False)
        self.assertEqual(record["verdict"], "known_gap")


class V02SuiteRunTests(unittest.TestCase):
    records: ClassVar[list[dict[str, Any]]]

    @classmethod
    def setUpClass(cls) -> None:
        cls.records = mb.run_suite("v0.2", timing=False)  # full suite, manifest seeds and repeats

    def attempts(self, repeat: int = 0) -> list[dict[str, Any]]:
        return [r for r in self.records if r["record_type"] == "attempt" and r["repeat"] == repeat]

    def test_denominators_cover_every_task_seed_and_mode(self) -> None:
        manifest = self.records[0]
        self.assertEqual(manifest["run_version"]["suite_version"], "mobilitybench-v0.2")
        self.assertEqual(manifest["fault_kinds"], list(mb.FAULT_KINDS_V02))
        self.assertIn("crash_step_assignment", manifest)
        expected = len(manifest["tasks"]) * len(manifest["seeds"]) * len(mb.modes_for("v0.2"))
        self.assertEqual((len(self.attempts(0)), len(self.attempts(1))), (expected, expected))
        schedule = mb.load_fixtures("v0.2").schedule
        assert schedule is not None
        for record in self.attempts():
            planned = schedule[(record["seed"], record["task_id"])]
            self.assertEqual((record["fault"], record["crash_step"]), (planned["fault"], planned["crash_step"]))
            if record["fault"] != "none" and not record["fault_applied"]:
                self.assertIsInstance(record["fault_not_applied_reason"], str)
            else:
                self.assertIsNone(record["fault_not_applied_reason"])

    def test_no_harness_errors_repeats_reproduce_and_security_matches(self) -> None:
        summary = mb.summarize(self.records)
        negatives = mb.load_fixtures("v0.2").negatives
        self.assertEqual(summary["harness_errors"], 0)
        self.assertEqual(summary["reproducibility"]["mismatched"], 0)
        self.assertEqual((summary["security_total"], summary["security"]["fail"]), (len(negatives), 0))
        self.assertEqual(summary["security"]["pass"], sum(not c["known_gap"] for c in negatives))
        self.assertEqual(mb.run_exit_code(self.records), 0)

    def test_every_new_fault_acts_on_the_core_restart_baseline(self) -> None:
        for fault in (*mb.CRASH_KINDS, "partition_drop_request", "partition_delay"):
            rows = [r for r in self.attempts() if r["mode"] == "restart_on_destination" and r["fault"] == fault]
            self.assertTrue(rows and any(r["fault_applied"] for r in rows), fault)

    def test_stable_ids_remove_every_restart_duplicate(self) -> None:
        modes = mb.summarize(self.records)["modes"]
        restart, stable = modes["restart_on_destination"], modes["restart_stable_ids"]
        self.assertGreater(restart["duplicate_effects"], 0)
        self.assertEqual(stable["duplicate_effects"], 0)
        self.assertGreater(stable["effect_id_conflicts"], 0)
        self.assertGreater(stable["task_correct"], restart["task_correct"])
        self.assertLess(stable["task_correct"], stable["attempts"])  # lost session context remains

    def test_records_are_sanitized(self) -> None:
        blob = canonical(self.records)
        for secret in mb.sensitive_strings(mb.load_fixtures("v0.2")):
            self.assertNotIn(secret, blob)

    def test_report_has_v02_sections_denominators_and_raw_rows(self) -> None:
        report = mb.build_report(self.records)
        for needle in ("# MobilityBench v0.2 report", "docs/mobilitybench-v0.2.md", "## Denominators",
                       "## Fault-path evidence", "## Fault applicability", "`no_transfer_channel`",
                       "| restart_stable_ids | B1-stable | implemented |", "no confidence intervals"):
            self.assertIn(needle, report)
        raw = [line for line in report.splitlines() if line.startswith("| 1103 | ")]
        self.assertEqual(len(raw), len(self.records[0]["tasks"]) * len(mb.modes_for("v0.2")))


class DeterminismAndCliTests(unittest.TestCase):
    def test_timing_free_v02_output_is_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            outputs = []
            for name in ("one.jsonl", "two.jsonl"):
                code, _, err = _cli(["run", "--suite", "v0.2", "--subset", "smoke", "--no-timing",
                                     "--out", str(Path(d) / name)])
                self.assertEqual(code, 0, err)
                outputs.append((Path(d) / name).read_bytes())
            self.assertEqual(outputs[0], outputs[1])
            rows = [json.loads(line) for line in outputs[0].decode("utf-8").splitlines()]
            self.assertTrue(all(r.get("elapsed_ms") is None for r in rows if r["record_type"] != "run_manifest"))
            self.assertEqual(mb.outcome_digest(rows), json.loads(err)["outcome_digest"])
            self.assertEqual({r["fault"] for r in rows if r["record_type"] == "attempt"}, set(mb.FAULT_KINDS_V02))

    def test_verify_schedule_and_report_cli(self) -> None:
        code, stdout, _ = _cli(["verify", "--suite", "v0.2"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout)["suite_version"], "mobilitybench-v0.2")
        code, stdout, _ = _cli(["schedule", "--suite", "v0.2", "--subset", "smoke"])
        rows = [json.loads(line) for line in stdout.splitlines()]
        self.assertEqual((code, len(rows)), (0, 10))
        self.assertTrue(all(set(r) == {"seed", "task_id", "fault", "crash_step"} for r in rows))
        code, stdout, _ = _cli(["schedule", "--suite", "v0.1", "--subset", "smoke"])
        self.assertTrue(all("crash_step" not in json.loads(line) for line in stdout.splitlines()))

    def test_unified_cli_forwards_suite_v02(self) -> None:
        from agent_movement import cli
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = cli.main(["bench", "verify", "--suite", "v0.2"])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out.getvalue())["verified"])

    def test_v01_smoke_outcomes_are_unchanged_by_harness_0_3_0(self) -> None:
        with mock.patch.dict(mb.MODES, mb.mode_table(lambda extra: False)):
            core = mb.run_suite("v0.1", subset="smoke", timing=False)
        self.assertEqual(mb.outcome_digest(core), V01_SMOKE_DIGEST_CORE)
        if HAVE_A2A and HAVE_RELOCATION:
            self.assertEqual(mb.outcome_digest(mb.run_suite("v0.1", subset="smoke", timing=False)),
                             V01_SMOKE_DIGEST_EXTRAS)


if __name__ == "__main__":
    unittest.main()
