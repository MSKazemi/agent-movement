"""Check benchmark verdict discipline, evidence redaction and deterministic scenarios."""
import contextlib
import io
import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from agent_movement.mobilitybench import CANARY, main, run_suite, summarize


class MobilityBenchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = run_suite()

    def test_all_expected_scenarios_present(self):
        scenarios = [c.scenario for c in self.cases]
        self.assertEqual(len(scenarios), len(set(scenarios)))
        self.assertEqual(len(scenarios), 20)
        self.assertIn("claimed_identity_is_not_authenticated", scenarios)
        self.assertIn("grant_revocation_not_bound_to_effect_gateway", scenarios)
        self.assertIn("old_worker_fenced_after_transfer", scenarios)
        self.assertIn("keep_origin_baseline", scenarios)

    def test_no_unexplained_failure_and_gaps_not_counted_as_pass(self):
        summary = summarize(self.cases)
        self.assertEqual(summary["total"], 20)
        self.assertEqual(summary["pass"], 17)
        self.assertEqual(summary["known_gap"], 3)
        self.assertEqual(summary["fail"], 0)
        for case in self.cases:
            self.assertEqual(case.expected, case.observed)
            self.assertGreaterEqual(case.duration_ms, 0)

    def test_no_canary_in_report(self):
        serialized = json.dumps([asdict(c) for c in self.cases])
        self.assertNotIn(CANARY, serialized)
        self.assertTrue(all("text" not in case.evidence for case in self.cases))

    def test_jsonl_cli_and_summary(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "observations.jsonl"
            with contextlib.redirect_stderr(io.StringIO()) as err:
                exit_code = main(["--output", str(target)])
            self.assertEqual(exit_code, 0)
            rows = [json.loads(line) for line in target.read_text().splitlines()]
            self.assertEqual(len(rows), 20)
            self.assertEqual(sum(r["verdict"] == "known_gap" for r in rows), 3)
            self.assertEqual(json.loads(err.getvalue())["fail"], 0)


if __name__ == "__main__":
    unittest.main()
