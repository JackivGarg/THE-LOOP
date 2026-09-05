"""Tests for centralized Groq configuration without making network requests."""

import os
import unittest
from unittest.mock import patch

from utils.groq_provider import (
    MODEL_CAPABILITIES,
    ModelCapabilities,
    get_completion_settings,
    get_retry_config,
    get_task_config,
    load_model_config,
    validate_model_capabilities,
)


class GroqProviderTests(unittest.TestCase):
    def test_defaults_use_supported_replacement_models(self):
        with patch.dict(os.environ, {}, clear=True):
            config = load_model_config()

        self.assertEqual(config.planner, "openai/gpt-oss-120b")
        self.assertEqual(config.code_writer, "openai/gpt-oss-120b")
        self.assertEqual(config.criteria_updater, "openai/gpt-oss-20b")

    def test_environment_overrides_task_model_and_limits(self):
        overrides = {
            "PLANNER_MODEL": "qwen/qwen3.6-27b",
            "PLANNER_TEMPERATURE": "0.2",
            "PLANNER_MAX_COMPLETION_TOKENS": "1024",
        }
        with patch.dict(os.environ, overrides, clear=False):
            model, settings = get_task_config("planner")

        self.assertEqual(model, "qwen/qwen3.6-27b")
        self.assertEqual(settings.temperature, 0.2)
        self.assertEqual(settings.max_completion_tokens, 1024)
        self.assertTrue(settings.requires_json_mode)

    def test_invalid_generation_limit_is_rejected(self):
        with patch.dict(os.environ, {"RATER_MAX_COMPLETION_TOKENS": "0"}, clear=False):
            with self.assertRaises(ValueError):
                get_completion_settings("rater")

    def test_known_model_without_json_mode_is_rejected(self):
        model_name = "example/no-json-mode"
        MODEL_CAPABILITIES[model_name] = ModelCapabilities(supports_json_mode=False)
        try:
            with self.assertRaises(ValueError):
                validate_model_capabilities(model_name, requires_json_mode=True)
        finally:
            del MODEL_CAPABILITIES[model_name]

    def test_retry_policy_reads_environment(self):
        overrides = {
            "GROQ_MAX_RETRY_ATTEMPTS": "5",
            "GROQ_RETRY_BASE_DELAY_SECONDS": "1.5",
            "GROQ_RETRY_MAX_DELAY_SECONDS": "12",
        }
        with patch.dict(os.environ, overrides, clear=False):
            policy = get_retry_config()

        self.assertEqual(policy.max_attempts, 5)
        self.assertEqual(policy.base_delay_seconds, 1.5)
        self.assertEqual(policy.max_delay_seconds, 12.0)


if __name__ == "__main__":
    unittest.main()
