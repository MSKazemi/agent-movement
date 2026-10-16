"""Small-state regression tests for the proposed abstract movement protocol."""

import unittest

from movement_modelcheck import State, explore, transitions, violations


def step(state: State, name: str) -> State:
    matches = [transition.state for transition in transitions(state) if transition.name == name]
    assert len(matches) == 1, (name, state)
    return matches[0]


class ProtectedMovementModelTests(unittest.TestCase):
    def test_all_schedules_through_depth_twelve_preserve_invariants(self):
        result = explore(12)
        self.assertIsNone(result.counterexample)
        self.assertTrue(result.exhausted)
        self.assertFalse(explore(2).exhausted)
        self.assertGreater(result.states, 100)
        self.assertGreater(result.transitions, result.states)

    def test_stale_writer_negative_control_has_minimal_counterexample(self):
        result = explore(8, unsafe_stale_writer=True)
        self.assertIsNotNone(result.counterexample)
        assert result.counterexample is not None
        self.assertEqual(result.counterexample.property_name, "CurrentEpochAtCommit")
        self.assertIn("unsafe_stale_A_effect", result.counterexample.trace)
        self.assertIn("atomic_fence_and_transfer", result.counterexample.trace)

    def test_destination_cannot_start_without_grant_or_fencing(self):
        state = step(State(), "prepare_destination")
        self.assertNotIn("atomic_fence_and_transfer", {t.name for t in transitions(state)})
        self.assertNotIn("resume_destination", {t.name for t in transitions(state)})
        state = step(state, "issue_separate_destination_grant")
        state = step(state, "atomic_fence_and_transfer")
        state = step(state, "resume_destination")
        self.assertEqual((state.owner, state.epoch, state.b_running), ("B", 2, True))

    def test_partition_and_revocation_fail_closed(self):
        state = step(State(), "partition_gateway")
        self.assertFalse(any(t.name.startswith("commit_") for t in transitions(state)))
        state = step(state, "heal_gateway")
        state = step(state, "revoke_authority")
        self.assertFalse(any(t.name.startswith("commit_") for t in transitions(state)))

    def test_effect_id_is_deduplicated_even_after_transfer(self):
        state = step(State(), "commit_A_effect-1")
        state = step(state, "prepare_destination")
        state = step(state, "issue_separate_destination_grant")
        state = step(state, "atomic_fence_and_transfer")
        state = step(state, "resume_destination")
        names = {t.name for t in transitions(state)}
        self.assertNotIn("commit_B_effect-1", names)
        self.assertIn("commit_B_effect-2", names)
        self.assertNotIn("commit_A_effect-2", names)
        state = step(state, "commit_B_effect-2")
        self.assertEqual(len(state.effects), 2)
        self.assertFalse(violations(state))

    def test_recovered_stale_source_never_regains_effect_authority(self):
        state = step(State(), "crash_A")
        state = step(state, "prepare_destination")
        state = step(state, "issue_separate_destination_grant")
        state = step(state, "atomic_fence_and_transfer")
        state = step(state, "restart_stale_A")
        self.assertFalse(any(t.name.startswith("commit_A_") for t in transitions(state)))


if __name__ == "__main__":
    unittest.main()
