import importlib.util
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from agent_movement.core import PolicyDenied

HAVE_RUNTIME = importlib.util.find_spec("langgraph") is not None and hasattr(os, "fork")
SKIP_REASON = "needs the optional 'relocation' extra (pip install -e '.[relocation]') and os.fork"
TRANSITIONS = ("origin", "receiver", "coordinator", "checkpoint", "effect-intent", "effect-commit",
               "acknowledgement")


@unittest.skipUnless(HAVE_RUNTIME, SKIP_REASON)
class RelocationExperimentTests(unittest.TestCase):
    """Runs the full out-of-process experiment once, then checks its evidence."""

    @classmethod
    def setUpClass(cls):
        from agent_movement import relocation_demo
        cls.tmp = tempfile.TemporaryDirectory()
        cls.results = relocation_demo.experiment(cls.tmp.name)
        cls.rows = {row["id"]: row for row in cls.results["matrix"]}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_pinned_runtime_is_installed(self):
        self.assertEqual(self.results["runtime"], self.results["pinned"])

    def test_worker_b_continues_from_checkpoint_not_restart(self):
        h = self.results["headline"]
        self.assertTrue(self.results["headline_ok"])
        self.assertEqual(h["items_by_execution"], {"worker-a.1": [0, 1, 2], "worker-b.1": [3, 4, 5]})
        self.assertEqual(h["process_item_runs"],
                         {"origin worker-a.1": 3, "receiver worker-b.1": 3, "restart baseline": 6})
        self.assertTrue(h["b_first_checkpoint_parent_is_exported"])
        self.assertTrue(h["constraints_preserved"])
        self.assertTrue(h["artifacts_from_origin_preserved"])

    def test_worker_a_is_fenced_after_transfer(self):
        h = self.results["headline"]
        self.assertEqual(h["fenced_a_step"], "PolicyDenied")
        self.assertEqual(h["fenced_a_commit"], "PolicyDenied")
        self.assertEqual(h["gateway_commits"], [{"effect_id": "publish-report", "epoch": 2}])
        self.assertEqual(h["final_owner"], {"execution_id": "worker-b.1", "epoch": 2})

    def test_task_identity_vs_execution_identity(self):
        h = self.results["headline"]
        self.assertEqual(h["manifest"]["logical_task_id"], h["task_identity"])
        self.assertEqual(h["grant"]["logical_task_id"], h["task_identity"])
        self.assertEqual(h["execution_identities"], ["worker-a.1", "worker-b.1"])
        self.assertEqual((h["manifest"]["from_epoch"], h["grant"]["to_epoch"]), (1, 2))

    def test_every_fault_row_matches_expectation(self):
        for row in self.results["matrix"]:
            with self.subTest(row=row["id"], fault=row["fault"]):
                self.assertEqual(row["observed"], row["expected"], row["steps"])

    def test_crash_and_duplicate_for_every_transition(self):
        for transition in TRANSITIONS:
            with self.subTest(transition=transition):
                kinds = {r["id"][0] for r in self.results["matrix"] if r["transition"] == transition}
                self.assertIn("C", kinds)
                self.assertIn("D", kinds)

    def test_never_more_than_one_gated_effect(self):
        for row in self.results["matrix"]:
            with self.subTest(row=row["id"]):
                e = row["evidence"]
                self.assertLessEqual(e["gateway_commits"] + e["opaque_invocations"], 1)

    def test_uncertain_opaque_effect_is_parked_not_retried(self):
        for row_id, truth in (("C13", 0), ("C14", 1)):
            with self.subTest(row=row_id):
                e = self.rows[row_id]["evidence"]
                self.assertEqual(e["final_status"], "reconcile_required")
                self.assertEqual(e["effect_ledger"], "unknown")
                self.assertEqual(e["opaque_invocations"], truth)

    def test_version_mismatch_fails_closed_and_reports_state(self):
        for row_id in ("V1", "V2", "V3"):
            with self.subTest(row=row_id):
                report = self.rows[row_id]["report"]
                self.assertFalse(report["compatible"])
                self.assertEqual(report["decision"], "refuse_fail_closed")
                self.assertTrue(report["unavailable_state"])
                self.assertIn("in_flight_node_execution", report["always_unsupported"])
                self.assertEqual(self.rows[row_id]["evidence"]["final_owner"], "worker-a.1@1")
        self.assertEqual(self.rows["V3"]["report"]["lost_state"], ["step_log"])
        self.assertEqual(self.rows["V4"]["report"]["decision"], "refuse_fail_closed")


@unittest.skipUnless(HAVE_RUNTIME, SKIP_REASON)
class RelocationUnitTests(unittest.TestCase):
    def setUp(self):
        from agent_movement import relocation
        self.r = relocation
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "relocation.sqlite")
        relocation.init_store(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def constraints(self):
        return {"classification": "synthetic", "effect_tool": "gateway", "effect_id": "effect-1",
                "max_gated_effects": 1}

    def test_manifest_declares_exported_and_unsupported_state(self):
        worker = self.r.Worker(self.path, "worker-a", faults=self.r.Faults(hard=False))
        worker.start("task-1", ["one two", "three"], self.constraints(), max_supersteps=1)
        manifest = worker.export("move-1", "worker-b.1")["manifest"]
        self.assertEqual(manifest["checkpoint"]["format"], self.r.CHECKPOINT_FORMAT)
        self.assertEqual(manifest["checkpoint"]["next"], ["process_item"])
        self.assertEqual(manifest["checkpoint"]["pending_writes"], [])
        self.assertTrue(set(self.r.STATE_CHANNELS) <= set(manifest["checkpoint"]["exported_channels"]))
        self.assertIn("credentials_and_grants", manifest["unsupported_state"])
        self.assertEqual(manifest["uncertain_effects"], [])

    def test_fenced_saver_rejects_stale_and_read_only_writes(self):
        worker = self.r.Worker(self.path, "worker-a", faults=self.r.Faults(hard=False))
        worker.start("task-1", ["one", "two"], self.constraints(), max_supersteps=1)
        self.r.EffectGateway(self.r.SQLiteStore(self.path)).transfer("task-1", "worker-a.1", 1, "worker-b.1")
        with closing(sqlite3.connect(self.path)) as db:
            before = db.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0]
        with self.assertRaises(PolicyDenied):
            worker.run(1, check_ownership=False)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0], before)
        with closing(sqlite3.connect(self.path, check_same_thread=False)) as conn:
            with self.assertRaises(PolicyDenied):
                self.r.FencedSqliteSaver(conn, "task-1").delete_thread("task-1")

    def test_soft_crash_mode_and_unknown_points(self):
        with self.assertRaises(self.r.SimulatedCrash):
            self.r.Faults("origin.before_export", hard=False).hit("origin.before_export")
        with self.assertRaises(self.r.ContractError):
            self.r.Faults("nowhere")

    def test_compatibility_accepts_identical_profile(self):
        worker = self.r.Worker(self.path, "worker-a", faults=self.r.Faults(hard=False))
        worker.start("task-1", ["one", "two"], self.constraints(), max_supersteps=1)
        manifest = worker.export("move-1", "worker-b.1")["manifest"]
        report = self.r.compatibility(manifest, self.r.local_profile())
        self.assertTrue(report["compatible"])
        self.assertEqual(report["unavailable_state"], [])

    def test_invalid_constraints_rejected(self):
        bad = {**self.constraints(), "classification": "private"}
        with self.assertRaises(self.r.ContractError):
            self.r.Worker(self.path, "worker-a").start("task-1", ["x"], bad)


if __name__ == "__main__":
    unittest.main()
