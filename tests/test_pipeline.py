"""Integration-level pipeline tests with explicit fake nodes; no provider requests."""
import unittest
from core.pipeline import PipelineNodes, RunCancelled, run_pipeline
from state import init_state


class PipelineTests(unittest.TestCase):
    def test_each_candidate_is_evaluated_and_best_draft_is_selected(self):
        state = init_state()
        events = []
        calls = []

        def planner(s):
            calls.append("plan")
            return s

        def writer(s):
            calls.append("write")
            s["current_code"] = "draft-1"
            return s

        def updater(s):
            calls.append("update")
            s["current_code"] = f"draft-{s['iteration'] + 1}"
            return s

        def evaluator(s):
            calls.append("evaluate")
            score = [6, 8, 7, 7][s["iteration"]]
            s["last_rating_json"] = {"scores": {dim: score for dim in ["layout", "typography", "responsiveness", "visual_design", "description_match"]}}
            s["last_deterministic_evaluation"] = {"score": 8, "issues": ["Remaining defect"]}
            return s

        result = run_pipeline(state, on_event=lambda stage, s, message: events.append(stage),
                              nodes=PipelineNodes(planner, writer, updater, evaluator))
        self.assertEqual(calls.count("evaluate"), 4)
        self.assertEqual(calls.count("update"), 3)
        self.assertEqual(result["current_code"], "draft-2")
        self.assertEqual(result["best_iteration"], 2)
        self.assertFalse(result["quality_passed"])
        self.assertEqual(events[-1], "completed")

    def test_cancellation_stops_before_provider_call(self):
        with self.assertRaises(RunCancelled):
            run_pipeline(init_state(), on_event=lambda *args: None, cancelled=lambda: True)


if __name__ == "__main__":
    unittest.main()
