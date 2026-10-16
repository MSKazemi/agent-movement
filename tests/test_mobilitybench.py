"""20-case smoke: fixture-declared verdicts, per-case isolation, byte-identical output.

Counts are derived from the packaged case declarations, never from literals: when a
later change closes a known gap, its case moves from known_gap to gap_closed (and must
then be rewritten) without breaking these tests.
"""
import contextlib
import importlib.util
import io
import json
import re
import tempfile
import unittest
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from agent_movement import mobilitybench as mb
from agent_movement.core import canonical

REPO = Path(__file__).resolve().parents[1]


def _cli(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = mb.main(argv)
    return code, out.getvalue(), err.getvalue()


def _declared(scenario, **changes):
    case = next(c for c in mb.load_cases() if c["scenario"] == scenario)
    case = {k: v for k, v in case.items() if k not in ("closed_observation", "expected_fix")}
    return {**case, **changes}


class SmokeDeclarationTests(unittest.TestCase):
    def test_declarations_cover_every_evaluator_once(self):
        names = [c["scenario"] for c in mb.load_cases()]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(set(names), set(mb.EVALUATORS))
        self.assertTrue(set(Counter(c["expectation"] for c in mb.load_cases())) <= set(mb.EXPECTATIONS))

    def test_known_gaps_name_a_fix_that_exists(self):
        gaps = [c for c in mb.load_cases() if c["expectation"] != "pass"]
        self.assertTrue(gaps, "the smoke is expected to document at least one gap")
        for case in gaps:
            with self.subTest(case["scenario"]):
                self.assertRegex(case["expected_fix"], r"issue #\d+")
                modules = re.findall(r"agent_movement\.(\w+)", case["expected_fix"])
                self.assertTrue(modules)
                for module in modules:
                    self.assertIsNotNone(importlib.util.find_spec(f"agent_movement.{module}"), module)
                for doc in re.findall(r"docs/[\w.-]+\.md", case["expected_fix"]):
                    self.assertTrue((REPO / doc).is_file(), doc)
                if case["expectation"] == "known_gap":
                    self.assertNotEqual(case["closed_observation"], case["expected"])

    def test_invalid_declarations_are_rejected(self):
        good = _declared("incorrect_destination_claim")
        bad = [
            {**good, "expectation": "maybe"},
            {**good, "expected_fix": "issue #8"},  # a pass case declares no fix
            {**good, "expectation": "known_gap", "expected_fix": "issue #8"},  # no closed observation
            {**good, "expectation": "known_gap", "expected_fix": "issue #8", "closed_observation": "denied"},
            {**good, "expectation": "gap_closed"},  # no fix named
            {**good, "scenario": "no_such_scenario"},
            {**good, "extra": True},
            {k: v for k, v in good.items() if k != "baseline"},
        ]
        for case in bad:
            with self.subTest(case=case), self.assertRaises(mb.CaseFixtureError):
                mb.validate_case(case)
        with tempfile.TemporaryDirectory() as d:
            dup = Path(d) / "cases.jsonl"
            dup.write_text((json.dumps(good) + "\n") * 2, encoding="utf-8")
            with self.assertRaises(mb.CaseFixtureError):
                mb.load_cases(dup)
            dup.write_text(json.dumps(good) + "\n", encoding="utf-8")
            self.assertEqual(mb.load_cases(dup), [good])  # a custom subset is allowed


class SmokeRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.declared = mb.load_cases()
        cls.cases = mb.run_suite()

    def test_every_verdict_matches_its_declaration(self):
        self.assertEqual([c.scenario for c in self.cases], [d["scenario"] for d in self.declared])
        for case, decl in zip(self.cases, self.declared):
            with self.subTest(case.scenario):
                self.assertEqual(case.expectation, decl["expectation"])
                allowed = {decl["expectation"]} | ({"gap_closed"} if decl["expectation"] == "known_gap" else set())
                self.assertIn(case.verdict, allowed, case.observed)
                self.assertGreaterEqual(case.duration_ms, 0)

    def test_summary_counts_derive_from_declarations(self):
        summary = mb.summarize(self.cases)
        want = Counter(d["expectation"] for d in self.declared)
        self.assertEqual(summary["total"], len(self.declared))
        self.assertEqual(summary["fail"], 0)
        self.assertEqual(summary["pass"], want["pass"])
        self.assertEqual(summary["known_gap"] + summary["gap_closed"], want["known_gap"] + want["gap_closed"])
        self.assertEqual(sum(summary[v] for v in mb.VERDICTS), summary["total"])

    def test_known_gap_cases_exercise_the_attack(self):
        evidence = {c.scenario: c.evidence for c in self.cases if c.verdict == "known_gap"}
        attack_succeeded = {
            "claimed_identity_is_not_authenticated": ("forged_task_executed",
                                                      "receipt_attributes_to_claimed_origin"),
            "grant_revocation_not_bound_to_effect_gateway": ("new_handoff_denied",
                                                             "simulated_commit_after_revocation"),
            "receipt_is_not_independently_authenticated": ("forged_receipt_self_consistent",),
        }
        for scenario, keys in attack_succeeded.items():
            if scenario in evidence:  # once a gap closes, this no longer applies
                for key in keys:
                    self.assertIs(evidence[scenario][key], True, (scenario, key))

    def test_no_canary_in_report(self):
        serialized = json.dumps([asdict(c) for c in self.cases])
        self.assertNotIn(mb.CANARY, serialized)
        self.assertTrue(all("text" not in case.evidence for case in self.cases))


class SmokeVerdictLogicTests(unittest.TestCase):
    def test_closed_gap_is_reported_not_passed_or_failed(self):
        # A test-only declaration: pretend the destination check were a known gap.
        case = _declared("incorrect_destination_claim", expected="accepted", expectation="known_gap",
                         closed_observation="denied", expected_fix="test-only")
        [result] = mb.run_suite(timing=False, cases=[case])
        self.assertEqual((result.observed, result.verdict), ("denied", "gap_closed"))
        self.assertEqual(mb.summarize([result])["fail"], 0)

    def test_declared_gap_closed_case(self):
        case = _declared("incorrect_destination_claim", expectation="gap_closed", expected_fix="test-only")
        [result] = mb.run_suite(timing=False, cases=[case])
        self.assertEqual(result.verdict, "gap_closed")
        reopened = _declared("incorrect_destination_claim", expected="accepted",
                             expectation="gap_closed", expected_fix="test-only")
        [result] = mb.run_suite(timing=False, cases=[reopened])
        self.assertEqual(result.verdict, "fail")

    def test_unexpected_observation_fails(self):
        case = _declared("incorrect_destination_claim", expected="accepted")
        [result] = mb.run_suite(timing=False, cases=[case])
        self.assertEqual((result.observed, result.verdict), ("denied", "fail"))


class SmokeIsolationAndDeterminismTests(unittest.TestCase):
    def test_reversed_order_gives_byte_identical_output(self):
        declared = mb.load_cases()
        forward = mb.to_jsonl(mb.run_suite(timing=False))
        names = [c["scenario"] for c in declared]
        backward_exec = mb.to_jsonl(mb.run_suite(timing=False, order=reversed(names)))
        self.assertEqual(forward.encode("utf-8"), backward_exec.encode("utf-8"))
        backward_decl = mb.run_suite(timing=False, cases=declared[::-1])
        self.assertEqual(sorted(map(canonical, map(asdict, backward_decl))),
                         sorted(canonical(json.loads(line)) for line in forward.splitlines()))

    def test_each_case_alone_matches_the_full_run(self):
        full = {c.scenario: c for c in mb.run_suite(timing=False)}
        for decl in mb.load_cases():
            with self.subTest(decl["scenario"]):
                [alone] = mb.run_suite(timing=False, cases=[decl])
                self.assertEqual(alone, full[decl["scenario"]])

    def test_order_must_name_every_scenario(self):
        with self.assertRaises(ValueError):
            mb.run_suite(timing=False, order=["keep_origin_baseline"])

    def test_no_timing_cli_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as d:
            outputs, digests = [], []
            for name in ("one.jsonl", "two.jsonl"):
                code, _, err = _cli(["--no-timing", "--output", str(Path(d) / name)])
                self.assertEqual(code, 0, err)
                outputs.append((Path(d) / name).read_bytes())
                digests.append(json.loads(err)["outcome_digest"])
            self.assertEqual(outputs[0], outputs[1])
            rows = [json.loads(line) for line in outputs[0].decode("utf-8").splitlines()]
            self.assertTrue(all(r["duration_ms"] is None for r in rows))
            # Timing stays out of the compared digest, so a timed run has the same one.
            code, _, err = _cli(["--output", str(Path(d) / "timed.jsonl")])
            self.assertEqual(code, 0, err)
            self.assertEqual(digests, [json.loads(err)["outcome_digest"]] * 2)

    def test_jsonl_cli_and_summary(self):
        declared = Counter(c["expectation"] for c in mb.load_cases())
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "observations.jsonl"
            code, _, err = _cli(["--output", str(target)])
            self.assertEqual(code, 0)
            rows = [json.loads(line) for line in target.read_text().splitlines()]
            self.assertEqual(len(rows), sum(declared.values()))
            summary = json.loads(err)
            self.assertEqual(summary["fail"], 0)
            self.assertEqual(summary["suite_version"], mb.SUITE_VERSION)
            self.assertEqual(sum(r["verdict"] in ("known_gap", "gap_closed") for r in rows),
                             declared["known_gap"] + declared["gap_closed"])
            for row in rows:
                self.assertEqual(row["expected_fix"] is None, row["expectation"] == "pass")


if __name__ == "__main__":
    unittest.main()
