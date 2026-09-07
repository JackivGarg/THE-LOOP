"""Tests for the iterative quality gate and early-stop behavior."""

import unittest

from state import init_state, is_quality_ready, should_stop


def _quality_report(score=9.5, issues=None):
    return {"score": score, "issues": issues or []}


def _strong_rating(score=8):
    return {
        "scores": {
            "layout": score,
            "typography": score,
            "responsiveness": score,
            "visual_design": score,
            "description_match": score,
        }
    }


class GenerationFlowTests(unittest.TestCase):
    def test_high_first_round_never_stops_before_minimum_rounds(self):
        state = init_state()
        state["iteration"] = 1
        state["reward_history"] = [0.99]
        state["last_rating_json"] = _strong_rating(10)
        state["last_deterministic_evaluation"] = _quality_report(10)

        self.assertFalse(should_stop(state))

    def test_average_score_cannot_bypass_quality_gate(self):
        state = init_state()
        state["iteration"] = state["min_iterations"]
        state["reward_history"] = [0.85, 0.9, 0.97]
        state["last_rating_json"] = _strong_rating(8)
        state["last_deterministic_evaluation"] = _quality_report(8.5, ["Missing <footer>"])

        self.assertFalse(is_quality_ready(state))
        self.assertFalse(should_stop(state))

    def test_clean_high_quality_result_can_stop_after_minimum_rounds(self):
        state = init_state()
        state["iteration"] = state["min_iterations"]
        state["reward_history"] = [0.84, 0.9, 0.95]
        state["last_rating_json"] = _strong_rating(8)
        state["last_deterministic_evaluation"] = _quality_report()

        self.assertTrue(is_quality_ready(state))
        self.assertTrue(should_stop(state))


if __name__ == "__main__":
    unittest.main()
