"""Operator reconciliation of parked effects with an unknown outcome (issue #30)."""

import contextlib
import importlib.util
import io
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from agent_movement.core import Conflict, ContractError, PolicyDenied

HAVE_RUNTIME = importlib.util.find_spec("langgraph") is not None and hasattr(os, "fork")
SKIP_REASON = "needs the optional 'relocation' extra (pip install -e '.[relocation]') and os.fork"
TASK, EFFECT, RETRY = "task-1", "effect-1", "effect-1.retry-1"
REASON = "checked the synthetic external system"


class _ReconcileExperiment:
    """Runs the out-of-process reconciliation rows once per store mode, then checks them."""

    TWO_STORE = False

    @classmethod
    def setUpClass(cls):
        from agent_movement import relocation_demo_reconcile as rec
        cls.tmp = tempfile.TemporaryDirectory()
        cls.rows = {row["id"]: row for row in rec.run_matrix(cls.tmp.name, cls.TWO_STORE)}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_every_reconciliation_row_matches_expectation(self):
        self.assertEqual(sorted(self.rows), ["C13a", "C13d", "C14a", "C14d", "R1", "R2", "R3", "R4", "R5"])
        for row in self.rows.values():
            with self.subTest(row=row["id"]):
                self.assertEqual(row["observed"], row["expected"], row["steps"])

    def test_true_decisions_end_with_exactly_one_effect(self):
        absent, done = self.rows["C13a"]["evidence"], self.rows["C14d"]["evidence"]
        self.assertEqual(absent["opaque_calls_by_effect"], {"publish-report.retry-1": 1})
        self.assertEqual(absent["effect_ledger"], "confirmed_absent")
        self.assertEqual(done["opaque_calls_by_effect"], {"publish-report": 1})
        self.assertEqual(done["effect_ledger"], "confirmed_done")
        for evidence in (absent, done):
            self.assertEqual(evidence["final_status"], "done")
            self.assertEqual(evidence["reconciliations"][0]["applied_by"], "worker-b.2")

    def test_false_decisions_lose_or_duplicate_the_effect(self):
        self.assertEqual(self.rows["C13d"]["evidence"]["opaque_invocations"], 0)
        self.assertEqual(self.rows["C14a"]["evidence"]["opaque_calls_by_effect"],
                         {"publish-report": 1, "publish-report.retry-1": 1})

    def test_stale_and_double_decisions(self):
        self.assertIn("PolicyDenied", self.rows["R1"]["recovery"])
        self.assertIn("-> ok", self.rows["R2"]["recovery"])
        self.assertIn("Conflict", self.rows["R3"]["recovery"])
        self.assertIn("PolicyDenied", self.rows["R5"]["recovery"])
        self.assertEqual(self.rows["R5"]["evidence"]["opaque_calls_by_effect"], {"publish-report.retry-1": 1})


@unittest.skipUnless(HAVE_RUNTIME, SKIP_REASON)
class SingleStoreReconcileExperimentTests(_ReconcileExperiment, unittest.TestCase):
    TWO_STORE = False


@unittest.skipUnless(HAVE_RUNTIME, SKIP_REASON)
class TwoStoreReconcileExperimentTests(_ReconcileExperiment, unittest.TestCase):
    TWO_STORE = True


@unittest.skipUnless(HAVE_RUNTIME, SKIP_REASON)
class ReconcileUnitTests(unittest.TestCase):
    """In-process (soft crash) checks of the operator API and the resume semantics."""

    def setUp(self):
        from agent_movement import relocation
        self.r = relocation
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "relocation.sqlite")
        relocation.init_store(self.path)
        self.coordinator = relocation.Coordinator(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def park(self, point="effect_commit.after"):
        """Crash worker-a.1 at ``point``; worker-a.2 (epoch 2) parks the opaque effect."""
        constraints = {"classification": "synthetic", "effect_tool": "opaque", "effect_id": EFFECT,
                       "max_gated_effects": 1}
        with self.assertRaises(self.r.SimulatedCrash):
            self.r.Worker(self.path, "worker-a", faults=self.r.Faults(point, hard=False)).start(
                TASK, ["one two", "three"], constraints)
        self.r.EffectGateway(self.r.SQLiteStore(self.path)).transfer(TASK, "worker-a.1", 1, "worker-a.2")
        worker = self.r.Worker(self.path, "worker-a", 2).attach(TASK, 2)
        self.assertEqual(worker.run()["status"], "reconcile_required")
        return worker

    def decide(self, decision, epoch=2, effect=EFFECT, operator="ops-alice", reason=REASON):
        return self.coordinator.reconcile(TASK, effect, decision, operator=operator, reason=reason, epoch=epoch)

    def opaque_calls(self):
        return self.r.observe(self.path, TASK, EFFECT)["opaque_calls_by_effect"]

    def events(self):
        return [(e["event_type"], e["actor"], e["epoch"]) for e in self.coordinator.reconciliation_events(TASK)]

    def test_parking_registers_the_effect_with_the_coordinator(self):
        self.park()
        (record,) = self.coordinator.parked_effects(TASK)
        self.assertEqual((record["effect_id"], record["status"], record["parked_by"], record["parked_epoch"]),
                         (EFFECT, "parked", "worker-a.2", 2))
        self.assertEqual(self.r.EffectLedger(self.path).get(TASK, EFFECT)["status"], "unknown")
        self.assertEqual(self.events(), [("parked", "worker-a.2", 2)])

    def test_confirmed_done_continues_without_re_execution(self):
        worker = self.park("effect_commit.after")
        self.assertEqual(self.opaque_calls(), {EFFECT: 1})
        result = self.decide("confirmed_done")
        self.assertEqual((result["replayed"], result["retry_effect_id"]), (False, None))
        self.assertEqual(worker.resume_reconciled()["status"], "done")
        obs = self.r.observe(self.path, TASK, EFFECT)
        self.assertEqual(obs["opaque_calls_by_effect"], {EFFECT: 1})
        self.assertEqual(obs["effect_intent"]["status"], "confirmed_done")
        self.assertEqual(obs["values"]["effect"]["reconciled"], "operator_confirmed_done")
        self.assertIn({"node": "operator_reconcile", "index": None, "execution_id": "worker-a.2", "epoch": 2,
                       "effect_id": EFFECT, "decision": "confirmed_done"}, obs["values"]["step_log"])
        self.assertEqual(self.events(), [("parked", "worker-a.2", 2), ("confirmed_done", "ops-alice", 2),
                                         ("applied", "worker-a.2", 2)])

    def test_confirmed_absent_retries_once_with_a_new_effect_id(self):
        worker = self.park("effect_commit.before")
        self.assertEqual(self.opaque_calls(), {})
        self.assertEqual(self.decide("confirmed_absent")["retry_effect_id"], RETRY)
        self.assertEqual(worker.resume_reconciled()["status"], "done")
        obs = self.r.observe(self.path, TASK, EFFECT)
        self.assertEqual(obs["opaque_calls_by_effect"], {RETRY: 1})
        self.assertEqual(obs["effect_intent"]["status"], "confirmed_absent")
        self.assertEqual(self.r.EffectLedger(self.path).get(TASK, RETRY)["status"], "committed")
        self.assertEqual({k: obs["values"]["effect"][k] for k in ("effect_id", "retry_of", "reconciled")},
                         {"effect_id": RETRY, "retry_of": EFFECT, "reconciled": "operator_confirmed_absent_retried"})

    def test_stale_epoch_decision_is_denied_audited_and_changes_nothing(self):
        self.park()
        before = self.coordinator.parked_effects(TASK)
        with self.assertRaises(PolicyDenied):
            self.decide("confirmed_done", epoch=1)
        self.assertEqual(self.coordinator.parked_effects(TASK), before)
        denied = self.coordinator.reconciliation_events(TASK)[-1]
        self.assertEqual((denied["event_type"], denied["actor"], denied["epoch"]), ("denied", "ops-alice", 1))
        self.assertEqual(denied["detail"]["error"], "PolicyDenied")
        # The ownership moves on after a valid decision: a replay at the old epoch is denied too.
        self.decide("confirmed_done")
        self.r.EffectGateway(self.r.SQLiteStore(self.path)).transfer(TASK, "worker-a.2", 2, "worker-c.1")
        with self.assertRaises(PolicyDenied):
            self.decide("confirmed_done", epoch=2)

    def test_double_resolution_is_idempotent_or_denied(self):
        self.park()
        first = self.decide("confirmed_done")
        replay = self.decide("confirmed_done")
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["decision_digest"], first["decision_digest"])
        for decision, operator, reason in (("confirmed_absent", "ops-alice", REASON),
                                           ("confirmed_done", "ops-bob", REASON),
                                           ("confirmed_done", "ops-alice", "another reason")):
            with self.subTest(decision=decision, operator=operator, reason=reason):
                with self.assertRaises(Conflict):
                    self.decide(decision, operator=operator, reason=reason)
        (record,) = self.coordinator.parked_effects(TASK)
        self.assertEqual((record["status"], record["decision"]["operator"]), ("confirmed_done", "ops-alice"))

    def test_effect_that_is_not_parked_is_denied(self):
        self.park()
        with self.assertRaises(Conflict):
            self.decide("confirmed_done", effect="other-effect")
        with self.assertRaises(Conflict):
            self.coordinator.reconcile("no-such-task", EFFECT, "confirmed_done", operator="ops-alice",
                                       reason=REASON, epoch=1)

    def test_retry_is_allowed_only_once(self):
        self.park("effect_commit.before")
        self.decide("confirmed_absent")
        crashing = self.r.Worker(self.path, "worker-a", 2, faults=self.r.Faults("effect_commit.after", hard=False))
        with self.assertRaises(self.r.SimulatedCrash):
            crashing.attach(TASK, 2).resume_reconciled()
        self.r.EffectGateway(self.r.SQLiteStore(self.path)).transfer(TASK, "worker-a.2", 2, "worker-a.3")
        worker = self.r.Worker(self.path, "worker-a", 3).attach(TASK, 3)
        self.assertEqual(worker.run()["status"], "reconcile_required")
        retry = [r for r in self.coordinator.parked_effects(TASK) if r["effect_id"] == RETRY][0]
        self.assertEqual((retry["status"], retry["retry_of"]), ("parked", EFFECT))
        with self.assertRaises(PolicyDenied):
            self.decide("confirmed_absent", epoch=3, effect=RETRY)
        self.decide("confirmed_done", epoch=3, effect=RETRY)
        self.assertEqual(worker.resume_reconciled()["status"], "done")
        self.assertEqual(self.opaque_calls(), {RETRY: 1})

    def test_resume_needs_a_decision_and_ownership(self):
        worker = self.park()
        with self.assertRaises(Conflict):
            worker.resume_reconciled()
        self.decide("confirmed_done")
        self.r.EffectGateway(self.r.SQLiteStore(self.path)).transfer(TASK, "worker-a.2", 2, "worker-c.1")
        with self.assertRaises(PolicyDenied):
            worker.resume_reconciled()
        with self.assertRaises(PolicyDenied):  # a fenced execution cannot apply the decision either
            self.r.EffectLedger(self.path).apply_decision(TASK, EFFECT, "worker-a.2", 2)
        self.assertEqual(self.r.EffectLedger(self.path).get(TASK, EFFECT)["status"], "unknown")
        resumed = self.r.Worker(self.path, "worker-c").attach(TASK, 3).resume_reconciled()
        self.assertEqual(resumed["status"], "done")
        with self.assertRaises(Conflict):
            self.r.Worker(self.path, "worker-c").attach(TASK, 3).resume_reconciled()

    def test_malformed_decisions_are_refused_before_any_write(self):
        self.park()
        for kwargs in ({"decision": "maybe"}, {"operator": "has space"}, {"reason": ""},
                       {"reason": "   "}, {"reason": "line\nbreak"}, {"reason": "x" * 513},
                       {"epoch": True}, {"epoch": 0}):
            with self.subTest(**{k: repr(v)[:20] for k, v in kwargs.items()}):
                args = {"decision": "confirmed_done", "operator": "ops-alice", "reason": REASON, "epoch": 2,
                        **kwargs}
                with self.assertRaises(ContractError):
                    self.coordinator.reconcile(TASK, EFFECT, args.pop("decision"), **args)
        self.assertEqual([e[0] for e in self.events()], ["parked"])


@unittest.skipUnless(HAVE_RUNTIME, SKIP_REASON)
class ReconcileCliTests(unittest.TestCase):
    """main(argv) of the operator CLI, also reachable as 'relocation_demo reconcile'."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.example = cls.cli(["example", "--dir", str(Path(cls.tmp.name) / "ex"), "--two-store"])[1]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @staticmethod
    def cli(argv, demo=False):
        from agent_movement import relocation_demo, relocation_reconcile
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = relocation_demo.main(["reconcile", *argv]) if demo else relocation_reconcile.main(argv)
        return code, json.loads(out.getvalue()) if out.getvalue() else None, err.getvalue()

    def test_end_to_end_operator_flow(self):
        ex = self.example
        self.assertEqual((ex["status"], ex["owner"]), ("reconcile_required", {"execution_id": "worker-b.2", "epoch": 3}))
        self.assertEqual(ex["simulated_out_of_band_check"], {"opaque_calls": 1, "true_decision": "confirmed_done"})
        authority = ["--authority", ex["authority"]]
        code, parked, _ = self.cli(["list", *authority, "--task", ex["task"]])
        self.assertEqual((code, [p["status"] for p in parked]), (0, ["parked"]))
        from agent_movement import cli  # the unified CLI forwards `relocate reconcile ...` unchanged
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(cli.main(["relocate", "reconcile", "list", *authority]), 0)
        self.assertEqual(json.loads(out.getvalue()), parked)
        decide = ["decide", *authority, "--task", ex["task"], "--effect", ex["effect"], "--decision",
                  "confirmed_done", "--operator", "ops-alice", "--reason", REASON]
        code, _, err = self.cli([*decide, "--epoch", "2"])
        self.assertEqual(code, 1)
        self.assertIn("denied (PolicyDenied)", err)
        code, result, _ = self.cli([*decide, "--epoch", "3"])
        self.assertEqual((code, result["replayed"]), (0, False))
        code, result, _ = self.cli([*decide, "--epoch", "3"], demo=True)
        self.assertEqual((code, result["replayed"]), (0, True))
        resume = ["resume", *authority, "--task", ex["task"], "--worker", "worker-b", "--incarnation", "2",
                  "--epoch", "3", "--store", ex["stores"]["worker-b"]]
        code, result, _ = self.cli(resume, demo=True)
        self.assertEqual((code, result["status"]), (0, "done"))
        self.assertEqual(self.cli(resume)[0], 1)
        code, events, _ = self.cli(["log", *authority])
        self.assertEqual([e["event_type"] for e in events],
                         ["parked", "denied", "confirmed_done", "replayed", "applied"])
        # Decisions and audit live in the coordinator file only, never in a worker store.
        with closing(sqlite3.connect(ex["stores"]["worker-b"])) as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertFalse({"effect_reconciliations", "reconciliation_events"} & tables)

    def test_usage_errors_exit_2(self):
        code, _, err = self.cli(["list", "--authority", str(Path(self.tmp.name) / "missing.sqlite")])
        self.assertEqual(code, 2)
        self.assertIn("no coordinator file", err)
        code, _, _ = self.cli(["example", "--dir", str(Path(self.tmp.name) / "ex")])  # not empty
        self.assertEqual(code, 2)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exit_:
            self.cli(["decide", "--authority", "x", "--task", "t", "--effect", "e", "--decision", "maybe",
                      "--operator", "o", "--reason", "r", "--epoch", "1"])
        self.assertEqual(exit_.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
