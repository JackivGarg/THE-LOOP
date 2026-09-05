"""Tests for strict structured response contracts."""

import unittest

from pydantic import ValidationError

from utils.llm_schemas import PlannerResponse, RaterResponse


class StructuredResponseSchemaTests(unittest.TestCase):
    def test_planner_requires_a_nonblank_instruction(self):
        with self.assertRaises(ValidationError):
            PlannerResponse.model_validate({"action": "write", "instruction": "   "})

    def test_rater_rejects_missing_scores(self):
        with self.assertRaises(ValidationError):
            RaterResponse.model_validate(
                {
                    "scores": {"layout": 8},
                    "deductions": "Missing required score dimensions.",
                }
            )

    def test_rater_rejects_scores_outside_the_rubric_range(self):
        with self.assertRaises(ValidationError):
            RaterResponse.model_validate(
                {
                    "scores": {
                        "layout": 11,
                        "typography": 8,
                        "responsiveness": 8,
                        "visual_design": 8,
                        "description_match": 8,
                    },
                    "deductions": "Invalid score range.",
                }
            )

    def test_rater_accepts_a_complete_valid_response(self):
        response = RaterResponse.model_validate(
            {
                "scores": {
                    "layout": 8,
                    "typography": 8,
                    "responsiveness": 8,
                    "visual_design": 8,
                    "description_match": 8,
                },
                "deductions": "Minor spacing improvements remain.",
            }
        )

        self.assertEqual(response.scores.layout, 8)


if __name__ == "__main__":
    unittest.main()
