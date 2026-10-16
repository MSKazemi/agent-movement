import importlib.util
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from agent_movement.core import Conflict, ContractError, PolicyDenied, canonical

HAVE_RUNTIME = importlib.util.find_spec("langgraph") is not None and hasattr(os, "fork")
SKIP_REASON = "needs the optional 'relocation' extra (pip install -e '.[relocation]') and os.fork"
COPY_FAULTS = {"truncated": "B4", "digest_mismatch": "B5", "partial_import": "B7", "duplicate_import": "B9"}


@unittest.skipUnless(HAVE_RUNTIME, SKIP_REASON)
class TwoStoreExperimentTests(unittest.TestCase):
    """Runs the out-of-process two-store experiment once, then checks its evidence."""

    @classmethod
    def setUpClass(cls):
        from agent_movement import relocation_demo
        cls.tmp = tempfile.TemporaryDirectory()
        cls.results = relocation_demo.experiment(cls.tmp.name, two_store=True)
        cls.rows = {row["id"]: row for row in cls.results["matrix"]}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_headline_checks_hold_with_two_stores(self):
        h = self.results["headline"]
        self.assertEqual(self.results["mode"], "two-store")
        self.assertTrue(self.results["headline_ok"])
        self.assertEqual(h["items_by_execution"], {"worker-a.1": [0, 1, 2], "worker-b.1": [3, 4, 5]})
        self.assertEqual(h["process_item_runs"],
                         {"origin worker-a.1": 3, "receiver worker-b.1": 3, "restart baseline": 6})
        self.assertEqual((h["fenced_a_step"], h["fenced_a_commit"]), ("PolicyDenied", "PolicyDenied"))
        self.assertEqual(h["gateway_commits"], [{"effect_id": "publish-report", "epoch": 2}])
        self.assertTrue(h["b_first_checkpoint_parent_is_exported"])

    def test_state_is_copied_not_shared(self):
        h = self.results["headline"]
        self.assertTrue(h["stores_distinct"])
        self.assertNotIn("checkpoints", h["coordinator_tables"])
        self.assertNotIn("effect_intents", h["coordinator_tables"])
        self.assertEqual(h["receiver_rows_before_import"], 0)
        self.assertEqual(h["imported"]["checkpoints"], 1)
        self.assertEqual(h["receiver_checkpoints_from_origin"], 1)
        self.assertTrue(h["bundle_verified"])
        self.assertTrue(h["origin_head_unchanged_after_transfer"])

    def test_manifest_is_self_describing(self):
        m = self.results["headline"]["manifest"]
        self.assertEqual(m["transport"], "bundle")
        self.assertEqual(m["graph_version"], "1")
        self.assertEqual(m["runtime"], self.results["pinned"])
        self.assertEqual(set(m["bundle"]["sections"]), {"checkpoint", "writes", "effect_ledger"})
        self.assertTrue(set(m["channels"]) <= set(m["bundle"]["channel_digests"]))
        for value in [*m["bundle"]["sections"].values(), *m["bundle"]["channel_digests"].values()]:
            self.assertRegex(value, r"^[0-9a-f]{64}$")

    def test_every_copy_fault_row_matches_expectation(self):
        self.assertEqual(len(self.results["matrix"]), 11)
        for row in self.results["matrix"]:
            with self.subTest(row=row["id"], fault=row["fault"]):
                self.assertEqual(row["observed"], row["expected"], row["steps"])
                self.assertEqual(row["evidence"]["gateway_commits"] + row["evidence"]["opaque_invocations"], 1)
        for name, row_id in COPY_FAULTS.items():
            with self.subTest(issue_fault=name):
                self.assertIn(row_id, self.rows)

    def test_corrupt_bundles_fail_closed_with_reason(self):
        for row_id, reason in (("B4", "bundle_unreadable"), ("B5", "digest_mismatch"),
                               ("B6", "manifest_not_granted")):
            with self.subTest(row=row_id):
                report = self.rows[row_id]["report"]
                self.assertEqual(report["decision"], "refuse_fail_closed")
                self.assertEqual(report["reason"], reason)
                self.assertIn("effect_ledger", report["unavailable_state"])
                self.assertIn("checkpoint_history", report["always_unsupported"])
        self.assertEqual(self.rows["B5"]["report"]["corrupt_sections"], ["checkpoint"])

    def test_partial_import_leaves_no_rows(self):
        self.assertIn("B store: 0 checkpoint rows", self.rows["B7"]["recovery"])
        self.assertIn("B store: 1 checkpoint row", self.rows["B8"]["recovery"])

    def test_matrix_markdown_is_byte_identical_across_runs(self):
        from agent_movement import relocation_demo, relocation_demo_two_store
        with tempfile.TemporaryDirectory() as root:
            rows = relocation_demo.run_matrix(root, relocation_demo_two_store.MATRIX,
                                              relocation_demo_two_store.TwoStoreRun)
        self.assertEqual(relocation_demo.markdown(rows), relocation_demo.markdown(self.results["matrix"]))


@unittest.skipUnless(HAVE_RUNTIME, SKIP_REASON)
class TwoStoreUnitTests(unittest.TestCase):
    def setUp(self):
        from agent_movement import relocation
        self.r = relocation
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.base = base
        self.auth = str(base / "coordinator.sqlite")
        self.a, self.b = str(base / "a.sqlite"), str(base / "b.sqlite")
        relocation.init_authority(self.auth)
        relocation.init_worker_store(self.a)
        relocation.init_worker_store(self.b)

    def tearDown(self):
        self.tmp.cleanup()

    def constraints(self):
        return {"classification": "synthetic", "effect_tool": "gateway", "effect_id": "effect-1",
                "max_gated_effects": 1}

    def worker(self, name, store, incarnation=1):
        return self.r.Worker(self.auth, name, incarnation, store=store, faults=self.r.Faults(hard=False))

    def started_export(self, movement="move-1"):
        origin = self.worker("worker-a", self.a)
        origin.start("task-1", ["one two", "three", "four"], self.constraints(), max_supersteps=2)
        exported = origin.export_bundle(movement, "worker-b.1", self.base / "outbox")
        return origin, exported

    def relocated(self):
        origin, exported = self.started_export()
        self.r.Coordinator(self.auth).transfer("move-1", self.r.local_profile())
        copy = self.r.bundles.copy(exported["bundle"], self.base / "inbox" / "move-1.bundle.json")
        receiver = self.worker("worker-b", self.b)
        return origin, receiver, receiver.accept("move-1", copy), copy

    def test_round_trip_into_separate_store_completes(self):
        _origin, receiver, accepted, _copy = self.relocated()
        self.assertEqual(accepted["imported"]["checkpoints"], 1)
        result = receiver.attach("task-1", 2).run()
        self.assertEqual(result["status"], "done")
        obs = self.r.observe(self.auth, "task-1", "effect-1", stores={"worker-a": self.a, "worker-b": self.b})
        self.assertEqual(obs["gateway_commits"], [{"effect_id": "effect-1", "epoch": 2}])
        self.assertEqual(obs["values"]["word_total"], 4)
        with closing(sqlite3.connect(self.auth)) as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertFalse({"checkpoints", "writes", "effect_intents"} & tables)

    def test_export_freezes_origin_until_refused(self):
        origin, _exported = self.started_export()
        with self.assertRaises(PolicyDenied):
            origin.run(1, check_ownership=False)
        profile = {**self.r.local_profile(), "graph_version": "2"}
        self.assertEqual(self.r.Coordinator(self.auth).transfer("move-1", profile)["status"], "refused")
        self.assertEqual(origin.run()["status"], "done")  # fail closed, not lost: A finishes

    def test_attached_fence_holds_the_coordinator_write_lock(self):
        with self.r._state_connection(self.a, self.auth) as (db, schema):
            self.assertEqual(schema, "authority")
            db.execute("BEGIN IMMEDIATE")
            with closing(sqlite3.connect(self.auth, timeout=0)) as other:
                with self.assertRaises(sqlite3.OperationalError):
                    other.execute("BEGIN IMMEDIATE")
            db.rollback()

    def test_parse_rejects_non_canonical_and_duplicate_keys(self):
        _origin, exported = self.started_export()
        bundle = json.loads(Path(exported["bundle"]).read_bytes())
        pretty = self.base / "pretty.json"
        pretty.write_text(json.dumps(bundle, indent=1), encoding="utf-8")
        with self.assertRaises(self.r.bundles.BundleRejected) as caught:
            self.r.bundles.parse(pretty)
        self.assertEqual(caught.exception.reason, "bundle_not_canonical")
        dup = self.base / "dup.json"
        dup.write_text('{"format":"x","format":"y"}', encoding="utf-8")
        with self.assertRaises(self.r.bundles.BundleRejected) as caught:
            self.r.bundles.parse(dup)
        self.assertEqual(caught.exception.reason, "bundle_unreadable")
        self.assertEqual(self.r.bundles.parse(exported["bundle"])[1], exported["bundle_sha256"])

    def test_refused_serializer_type_is_never_decoded(self):
        _origin, exported = self.started_export()
        payload = json.loads(Path(exported["bundle"]).read_bytes())["payload"]
        payload["checkpoint"]["type"] = "pickle"
        with self.assertRaises(self.r.bundles.BundleRejected) as caught:
            self.r.bundles.decode_checkpoint(payload, None)
        self.assertEqual(caught.exception.reason, "unsupported_serialization")

    def test_import_never_rewinds_a_newer_receiver_store(self):
        _origin, receiver, _accepted, _copy = self.relocated()
        receiver.attach("task-1", 2).run(1)
        coordinator = self.r.Coordinator(self.auth)
        # Operator error: fail over from the ORIGIN's stale store into B's newer store.
        grant = coordinator.failover("move-2", "task-1", "worker-b.2", self.r.local_profile(),
                                     source_store=self.a, outbox=self.base / "outbox-c")
        before = self.r.observe(self.auth, "task-1", stores={"worker-b": self.b})["stores"]
        with self.assertRaises(Conflict):
            self.worker("worker-b", self.b, 2).accept("move-2", grant["bundle"])
        after = self.r.observe(self.auth, "task-1", stores={"worker-b": self.b})["stores"]
        self.assertEqual(before, after)

    def test_divergent_existing_rows_are_refused(self):
        _origin, exported = self.started_export()
        payload = json.loads(Path(exported["bundle"]).read_bytes())["payload"]
        with closing(sqlite3.connect(self.b)) as db:
            self.r.bundles.insert_payload(db, "task-1", payload)
            self.assertEqual(self.r.bundles.insert_payload(db, "task-1", payload)["checkpoints"], 0)
            payload["checkpoint"]["metadata_b64"] = None
            with self.assertRaises(Conflict):
                self.r.bundles.insert_payload(db, "task-1", payload)

    def test_import_record_replays_after_a_lost_ack(self):
        _origin, exported = self.started_export()
        self.r.Coordinator(self.auth).transfer("move-1", self.r.local_profile())
        receiver = self.r.Worker(self.auth, "worker-b", store=self.b,
                                 faults=self.r.Faults("receiver.after_accept", hard=False))
        with self.assertRaises(self.r.SimulatedCrash):
            receiver.accept("move-1", exported["bundle"])
        again = self.worker("worker-b", self.b).accept("move-1", exported["bundle"])
        self.assertEqual(again["imported"], {"replayed": True})
        self.assertEqual(again["ack"]["status"], "acknowledged")

    def test_shared_and_bundle_apis_do_not_mix(self):
        origin, exported = self.started_export()
        with self.assertRaises(ContractError):
            origin.export("move-9", "worker-b.1")
        with self.assertRaises(ContractError):
            self.r.Coordinator(self.auth).request(exported["manifest"])
        with self.assertRaises(ContractError):
            self.r.Worker(self.auth, "worker-a", store=os.path.join(self.tmp.name, ".", "coordinator.sqlite"))
        self.assertEqual(canonical(exported["manifest"]["unsupported_state"]),
                         canonical(sorted(self.r.BUNDLE_UNSUPPORTED_STATE)))


if __name__ == "__main__":
    unittest.main()
