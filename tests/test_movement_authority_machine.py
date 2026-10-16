"""Executable MASM-0.1 specification and counterexample regression tests.

Synthetic, stdlib-only, no live network/tool action. Unlike the runtime tests,
these test the *specification's* predicates and bounded transition graph.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from dataclasses import replace
from pathlib import Path

from movement_authority_machine import (
    ROOT_SCOPES, State, apply, authorize_child_grant, authorize_effect,
    authorize_transfer, explore, violations,
)


class AuthorityMachineTests(unittest.TestCase):
    def test_bounded_state_exploration_is_explicitly_not_complete(self):
        result = explore(8)
        self.assertIsNone(result.counterexample)
        self.assertFalse(result.exhausted)  # avoid advertising this as a universal proof
        self.assertGreater(result.states, 15000)
        self.assertGreater(result.transitions, 50000)
        self.assertFalse(explore(0).exhausted)

    def test_each_bypassed_invariant_has_a_short_counterexample(self):
        examples = {
            "skip_epoch": ("EffectRequiresCurrentFencingEpoch", "commit_A_publish-1"),
            "skip_principals": ("AllPrincipalsAtEffectCommit", "revoke_user"),
            "skip_dedup": ("NoDuplicateProtectedEffect", "commit_A_publish-1"),
            "skip_policy": ("PolicyEpochAtEffectCommit", "bump_policy_epoch"),
        }
        for mutation, (property_name, witness) in examples.items():
            with self.subTest(mutation=mutation):
                result = explore(6, mutation=mutation)
                self.assertIsNotNone(result.counterexample)
                assert result.counterexample is not None
                self.assertEqual(result.counterexample.invariant, property_name)
                self.assertIn(witness, result.counterexample.trace)
                self.assertLessEqual(len(result.counterexample.trace), 6)

    def test_issuance_requires_two_principals_and_attenuation(self):
        prepared = apply(State(), "prepare_destination")
        allowed = authorize_child_grant(
            prepared, task_id="task-1", audience="B", scopes=frozenset({"publish"}),
        )
        self.assertTrue(allowed.allowed)
        self.assertFalse(authorize_child_grant(
            prepared, task_id="task-1", audience="A", scopes=frozenset({"publish"}),
        ).allowed)
        self.assertFalse(authorize_child_grant(
            prepared, task_id="wrong-task", audience="B", scopes=frozenset({"publish"}),
        ).allowed)
        self.assertEqual(authorize_child_grant(
            prepared, task_id="task-1", audience="B", scopes=ROOT_SCOPES | {"admin"},
        ).reason, "scope_escalation")
        no_owner = apply(prepared, "revoke_data_owner")
        self.assertFalse(authorize_child_grant(
            no_owner, task_id="task-1", audience="B", scopes=frozenset({"publish"}),
        ).allowed)
        with self.assertRaises(ValueError):
            apply(no_owner, "issue_attenuated_grant_B")

    def test_mutated_child_scope_and_task_are_detected(self):
        s = apply(apply(State(), "prepare_destination"), "issue_attenuated_grant_B")
        self.assertIn("NoPrivilegeEscalation", violations(replace(s, child_scopes=ROOT_SCOPES | {"admin"})))
        self.assertIn("DestinationGrantBinding", violations(replace(s, child_task_id="other-task")))
        self.assertEqual(authorize_transfer(replace(s, child_audience="A")).reason,
                         "destination_grant_binding_or_scope")

    def test_grant_is_issued_before_fence_and_activation(self):
        s = apply(State(), "prepare_destination")
        self.assertFalse(authorize_transfer(s).allowed)
        s = apply(s, "issue_attenuated_grant_B")
        self.assertTrue(authorize_transfer(s).allowed)
        s = apply(s, "fence_and_transfer")
        self.assertEqual((s.owner, s.epoch, s.phase), ("B", 2, "fenced"))
        self.assertFalse(authorize_effect(s, "B", "publish-1").allowed)
        s = apply(s, "resume_destination")
        self.assertTrue(authorize_effect(s, "B", "publish-1").allowed)
        self.assertFalse(violations(s))

    def test_revoke_between_grant_and_fence_prevents_transfer(self):
        s = apply(apply(State(), "prepare_destination"), "issue_attenuated_grant_B")
        for action in ("revoke_user", "revoke_data_owner", "cancel_task"):
            with self.subTest(action=action):
                denied = apply(s, action)
                self.assertFalse(authorize_transfer(denied).allowed)
                with self.assertRaises(ValueError):
                    apply(denied, "fence_and_transfer")

    def test_revocation_is_not_retroactive_but_blocks_new_commits(self):
        s = apply(State(), "commit_A_publish-1")
        before = s.commits
        s = apply(s, "revoke_data_owner")
        self.assertEqual(s.commits, before)
        self.assertEqual(authorize_effect(s, "A", "publish-2").reason,
                         "mandatory_principal_revoked")
        self.assertFalse(violations(s))
        with self.assertRaises(ValueError):
            apply(s, "commit_A_publish-2")

    def test_stale_origin_after_recovery_cannot_commit(self):
        s = State()
        for action in (
            "crash_A", "prepare_destination", "issue_attenuated_grant_B",
            "fence_and_transfer", "restart_stale_A", "resume_destination",
        ):
            s = apply(s, action)
        self.assertEqual(authorize_effect(s, "A", "publish-1").reason, "stale_owner_or_epoch")
        self.assertTrue(authorize_effect(s, "B", "publish-1").allowed)
        s = apply(s, "commit_B_publish-1")
        self.assertEqual(s.commits[0].presented_epoch, 2)
        self.assertFalse(violations(s))

    def test_shared_effect_id_deduplication_and_budget_across_transfer(self):
        s = apply(State(), "commit_A_publish-1")
        for action in (
            "prepare_destination", "issue_attenuated_grant_B",
            "fence_and_transfer", "resume_destination",
        ):
            s = apply(s, action)
        self.assertEqual(authorize_effect(s, "B", "publish-1").reason, "already_committed")
        s = apply(s, "commit_B_publish-2")
        self.assertEqual(s.budget_left, 0)
        self.assertEqual(len(s.commits), 2)
        self.assertEqual(s.commits[0].owner_at_commit, "A")
        self.assertEqual(s.commits[1].owner_at_commit, "B")
        self.assertEqual(authorize_effect(s, "B", "publish-1").reason, "budget_exhausted")
        self.assertFalse(violations(s))

    def test_expiry_policy_change_and_partition_are_fail_closed(self):
        s = State()
        self.assertEqual(authorize_effect(apply(s, "partition_gateway"), "A", "publish-1").reason,
                         "gateway_unavailable")
        self.assertTrue(authorize_effect(apply(apply(s, "partition_gateway"), "heal_gateway"),
                                         "A", "publish-1").allowed)
        changed = apply(s, "bump_policy_epoch")
        self.assertEqual(authorize_effect(changed, "A", "publish-1").reason, "policy_epoch_mismatch")
        s = apply(apply(s, "advance_clock"), "advance_clock")
        self.assertEqual(authorize_effect(s, "A", "publish-1").reason, "expired_grant")
        with self.assertRaises(ValueError):
            apply(s, "commit_A_publish-1")

    def test_opaque_effect_waits_for_explicit_reconciliation(self):
        s = apply(State(), "dispatch_opaque_effect_unknown")
        self.assertEqual(s.opaque, "unknown")
        self.assertEqual(authorize_effect(s, "A", "publish-1").reason,
                         "unknown_effect_requires_reconciliation")
        s = apply(apply(s, "prepare_destination"), "issue_attenuated_grant_B")
        self.assertEqual(authorize_transfer(s).reason, "external_effect_unknown")
        for action in ("operator_claim_done", "operator_claim_absent"):
            with self.subTest(action=action):
                resolved = apply(s, action)
                self.assertTrue(authorize_transfer(resolved).allowed)
                self.assertEqual(len(resolved.commits), 0)
                self.assertFalse(violations(resolved))
        # An operator claim is an assertion, NOT proof of the external outcome.

    def test_cancel_does_not_undo_existing_effects(self):
        s = apply(State(), "commit_A_publish-1")
        s = apply(s, "cancel_task")
        self.assertEqual(len(s.commits), 1)
        self.assertEqual(authorize_effect(s, "A", "publish-2").reason, "cancelled")
        self.assertFalse(violations(s))

    def test_unknown_model_transition_and_invalid_bounds_fail(self):
        with self.assertRaises(ValueError):
            apply(State(), "forged_external_effect")
        with self.assertRaises(ValueError):
            explore(-1)
        with self.assertRaises(ValueError):
            explore(3, mutation="unknown")
        limited = explore(4, max_states=10)
        self.assertFalse(limited.exhausted)
        self.assertIsNone(limited.counterexample)

    def test_cli_report_is_deterministic_and_reports_negative_control(self):
        script = Path(__file__).resolve().parents[1] / "tools" / "movement_authority_machine.py"
        safe = subprocess.run(
            [sys.executable, str(script), "--depth", "4"], capture_output=True,
            text=True, check=True, timeout=30, env=os.environ.copy(),
        )
        safe2 = subprocess.run(
            [sys.executable, str(script), "--depth", "4"], capture_output=True,
            text=True, check=True, timeout=30, env=os.environ.copy(),
        )
        self.assertEqual(safe.stdout, safe2.stdout)
        self.assertEqual(json.loads(safe.stdout)["status"], "no_violation_within_bound")
        bad = subprocess.run(
            [sys.executable, str(script), "--mutation", "skip_epoch", "--depth", "5"],
            capture_output=True, text=True, check=False, timeout=30, env=os.environ.copy(),
        )
        self.assertEqual(bad.returncode, 1)
        self.assertEqual(json.loads(bad.stdout)["violated_invariant"],
                         "EffectRequiresCurrentFencingEpoch")


if __name__ == "__main__":
    unittest.main()
