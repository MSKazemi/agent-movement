"""MobilityBench v0.1 optional-extra baselines: B2 over A2A v1 and B3 checkpoint relocation (issue #31).

The mode-table tests run everywhere. The B2/B3 tests skip unless their extra is installed:
python -m pip install -e '.[a2a,relocation]'
"""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent_movement import mobilitybench_v01 as mb

HAVE_A2A = mb.extra_available("a2a")
HAVE_RELOCATION = mb.extra_available("relocation")


class _Attempts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx = mb.load_fixtures("v0.1")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.n = 0

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def task(self, task_id):
        return next(t for t in self.fx.tasks if t["task_id"] == task_id)

    def attempt(self, task_id, mode, fault="none", task=None):
        """`task` overrides the frozen task (e.g. a negative fixture, which has no ground truth)."""
        type(self).n += 1
        workdir = Path(self.tmp.name) / f"a{self.n}"
        task = task or self.task(task_id)
        return mb.run_attempt(task, self.fx.truth.get(task["task_id"]), mode, fault, workdir), workdir


class ModeTableTests(_Attempts):
    def test_missing_extras_make_explicit_unavailable_modes(self):
        table = mb.mode_table(lambda extra: False)
        self.assertEqual(table["a2a_delegate"]["unavailable_reason"], "extra_not_installed:a2a")
        self.assertEqual(table["checkpoint_relocate"]["unavailable_reason"], "extra_not_installed:relocation")
        self.assertEqual(table["cross_framework_reconstruct"]["unavailable_reason"], "baseline_not_implemented")
        self.assertEqual({m for m, i in table.items() if i["status"] == "implemented"},
                         {"keep_on_origin", "restart_on_destination", "local_delegate"})

    def test_installed_extras_make_modes_scored_but_never_b4(self):
        table = mb.mode_table(lambda extra: True)
        self.assertEqual([m for m, i in table.items() if i["status"] != "implemented"],
                         ["cross_framework_reconstruct"])
        self.assertEqual((table["a2a_delegate"]["extra"], table["checkpoint_relocate"]["extra"]),
                         ("a2a", "relocation"))

    def test_unavailable_record_without_extra_is_not_scored(self):
        with mock.patch.dict(mb.MODES, mb.mode_table(lambda extra: False)):
            for mode, extra in (("a2a_delegate", "a2a"), ("checkpoint_relocate", "relocation")):
                record, workdir = self.attempt("doc-release-notes", mode)
                self.assertEqual((record["outcome"], record["mode_status"], record["reason"]),
                                 ("unavailable", "unavailable", f"extra_not_installed:{extra}"))
                self.assertTrue(all(record[k] is None for k in mb.METRIC_KEYS))
                self.assertFalse(workdir.exists())  # nothing ran

    def test_report_uses_the_run_mode_table_and_records_extras(self):
        with mock.patch.dict(mb.MODES, mb.mode_table(lambda extra: False)):
            records = mb.run_suite("v0.1", subset="smoke", timing=False)
        self.assertEqual(set(records[0]["run_version"]["extras"]), set(mb.EXTRAS))
        summary = mb.summarize(records)
        self.assertEqual(summary["modes"]["a2a_delegate"]["unavailable"], 6)
        report = mb.build_report(records)  # rendered in an environment that may have the extras
        self.assertIn("**UNAVAILABLE** (issue #31", report)
        self.assertIn("`extra_not_installed:relocation`", report)
        self.assertIn("`baseline_not_implemented`", report)


@unittest.skipUnless(HAVE_A2A, "optional A2A extra not installed (pip install -e '.[a2a]')")
class A2ADelegateModeTests(_Attempts):
    def test_delegable_tail_is_correct_and_crosses_the_a2a_sdk(self):
        record, workdir = self.attempt("code-version-bump", "a2a_delegate")
        self.assertEqual((record["outcome"], record["task_correct"]), ("completed", True))
        from agent_movement.a2a_profile import A2ACorrelationLog
        rows = A2ACorrelationLog(workdir / "receiver.sqlite").rows()
        self.assertEqual([r["outcome"] for r in rows], ["completed", "completed"])
        self.assertTrue(all(r["a2a_task_id"] for r in rows))  # real A2A tasks were created
        local, _ = self.attempt("code-version-bump", "local_delegate")
        self.assertEqual(record["transfer_messages"], local["transfer_messages"])
        self.assertGreater(record["transfer_bytes"], local["transfer_bytes"])  # A2A metadata projection

    def test_duplicate_delivery_is_a_replayed_receipt(self):
        record, workdir = self.attempt("code-version-bump", "a2a_delegate", "duplicate_delivery")
        self.assertTrue(record["task_correct"])
        self.assertEqual((record["duplicate_deliveries_suppressed"], record["transfer_messages"]), (2, 8))
        from agent_movement.a2a_profile import A2ACorrelationLog
        self.assertEqual(sorted(r["outcome"] for r in A2ACorrelationLog(workdir / "receiver.sqlite").rows()),
                         ["completed", "completed", "replayed", "replayed"])

    def test_refusals_happen_before_anything_is_sent(self):
        record, workdir = self.attempt("code-rename-helper", "a2a_delegate")
        self.assertEqual(record["outcome"], "refused")
        self.assertTrue(record["reason"].startswith("incompatible_state:"))
        self.assertEqual(record["transfer_bytes"], 0)
        self.assertFalse((workdir / "receiver.sqlite").exists())

    def test_private_task_is_refused_client_side_before_disclosure(self):
        case = next(c for c in self.fx.negatives if c["case_id"] == "neg-private-delegate")
        record, workdir = self.attempt(None, "a2a_delegate", task=case["task"])
        self.assertEqual((record["outcome"], record["reason"], record["transfer_bytes"]),
                         ("refused", "contract_rejected", 0))

    def test_origin_preemption_is_incomplete(self):
        record, _ = self.attempt("doc-release-notes", "a2a_delegate", "origin_preempted")
        self.assertEqual((record["outcome"], record["reason"]),
                         ("incomplete", "origin_preempted_owner_not_transferred"))


@unittest.skipUnless(HAVE_RELOCATION, "optional relocation extra not installed (pip install -e '.[relocation]')")
class CheckpointRelocateModeTests(_Attempts):
    def relocation_rows(self, workdir):
        with sqlite3.connect(workdir / "effects.sqlite") as db:
            return db.execute("SELECT mode, from_execution, from_epoch, to_execution, to_epoch, status "
                              "FROM relocations").fetchall()

    def test_every_frozen_task_is_correct_without_faults(self):
        for task in self.fx.tasks:
            with self.subTest(task=task["task_id"]):
                record, workdir = self.attempt(task["task_id"], "checkpoint_relocate")
                self.assertEqual((record["outcome"], record["task_correct"]), ("completed", True))
                self.assertEqual((record["steps_executed"], record["steps_reexecuted"]), (len(task["plan"]), 0))
                self.assertEqual(self.relocation_rows(workdir),
                                 [("cooperative", "agent-a", 1, "agent-b", 2, "acknowledged")])

    def test_preserves_session_context_that_restart_loses(self):
        restart, _ = self.attempt("doc-release-notes", "restart_on_destination")
        relocate, _ = self.attempt("doc-release-notes", "checkpoint_relocate")
        self.assertEqual((restart["constraints_preserved"], restart["duplicate_effects"]), (0, 1))
        self.assertEqual((relocate["constraints_preserved"], relocate["duplicate_effects"]), (1, 0))
        self.assertGreater(relocate["sensitive_transfers"], 0)  # the checkpoint carries the raw input

    def test_origin_preemption_fails_over_from_the_durable_head(self):
        record, workdir = self.attempt("tools-refund-sim", "checkpoint_relocate", "origin_preempted")
        self.assertEqual((record["outcome"], record["task_correct"], record["fault_applied"]),
                         ("completed", True, True))
        self.assertEqual(self.relocation_rows(workdir)[0][0], "failover")
        with sqlite3.connect(workdir / "effects.sqlite") as db:
            epochs = dict(db.execute("SELECT effect_id, epoch FROM effects").fetchall())
        self.assertEqual(epochs, {"tools-refund-sim.e1": 1, "tools-refund-sim.e3": 2})  # e2 is skipped by policy

    def test_stale_origin_is_fenced(self):
        record, _ = self.attempt("tools-restock-order", "checkpoint_relocate", "stale_origin_returns")
        self.assertEqual((record["stale_commits_fenced"], record["stale_commits_accepted"]), (1, 0))
        self.assertTrue(record["task_correct"])

    def test_duplicate_movement_and_grant_are_replays(self):
        record, workdir = self.attempt("tools-calendar-hold", "checkpoint_relocate", "duplicate_delivery")
        self.assertTrue(record["task_correct"])
        self.assertEqual((record["duplicate_deliveries_suppressed"], record["transfer_messages"]), (2, 4))
        self.assertEqual(len(self.relocation_rows(workdir)), 1)

    def test_effect_ack_loss_is_reconciled(self):
        record, _ = self.attempt("tools-travel-booking", "checkpoint_relocate", "effect_ack_lost")
        self.assertEqual((record["unknown_events"], record["reconciled_events"], record["duplicate_effects"]),
                         (1, 1, 0))

    def test_incompatible_receiver_refuses_fail_closed(self):
        from agent_movement import mobilitybench_optional as opt
        wrong = {**opt.receiver_profile(), "graph_version": "999"}
        with mock.patch.object(opt, "receiver_profile", return_value=wrong):
            record, workdir = self.attempt("doc-release-notes", "checkpoint_relocate")
        self.assertEqual((record["outcome"], record["reason"]), ("refused", "incompatible_checkpoint"))
        self.assertEqual(self.relocation_rows(workdir)[0][5], "refused")
        pre_move = [e for e in self.fx.truth["doc-release-notes"]["expected_effects"]
                    if e["step"] < self.task("doc-release-notes")["movement_at"]]
        self.assertEqual(record["effects_committed"], len(pre_move))  # only the origin's pre-move effects


@unittest.skipUnless(HAVE_A2A and HAVE_RELOCATION, "needs both optional extras")
class OptionalSuiteTests(unittest.TestCase):
    def test_smoke_subset_scores_five_modes_deterministically(self):
        first = mb.run_suite("v0.1", subset="smoke", timing=False)
        second = mb.run_suite("v0.1", subset="smoke", timing=False)
        self.assertEqual(mb.outcome_digest(first), mb.outcome_digest(second))
        summary = mb.summarize(first)
        self.assertEqual(summary["harness_errors"], 0)
        scored = [m for m, s in summary["modes"].items() if s["unavailable"] == 0]
        self.assertEqual(len(scored), 5)
        self.assertEqual(summary["modes"]["checkpoint_relocate"]["task_correct"], 6)


if __name__ == "__main__":
    unittest.main()
