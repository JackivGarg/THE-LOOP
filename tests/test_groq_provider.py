"""Tests for centralized Groq configuration without making network requests."""

import os
import unittest
from unittest.mock import patch

from utils.groq_provider import (
    MODEL_CAPABILITIES,
    ModelCapabilities,
    get_completion_settings,
    get_provider_config,
    get_retry_config,
    get_structured_response_format,
    get_task_config,
    load_model_config,
    validate_model_capabilities,
)


class GroqProviderTests(unittest.TestCase):
    def test_defaults_use_supported_replacement_models(self):
        with patch.dict(os.environ, {}, clear=True):
            config = load_model_config()

        self.assertEqual(config.planner, "openai/gpt-oss-20b")
        self.assertEqual(config.code_writer, "openai/gpt-oss-20b")
        self.assertEqual(config.criteria_updater, "openai/gpt-oss-20b")

    def test_environment_overrides_task_model_and_limits(self):
        overrides = {
            "CODE_WRITER_MODEL": "qwen/qwen3.6-27b",
            "CODE_WRITER_TEMPERATURE": "0.2",
            "CODE_WRITER_MAX_COMPLETION_TOKENS": "1024",
        }
        with patch.dict(os.environ, overrides, clear=False):
            model, settings = get_task_config("code_writer")

        self.assertEqual(model, "qwen/qwen3.6-27b")
        self.assertEqual(settings.temperature, 0.2)
        self.assertEqual(settings.max_completion_tokens, 1024)
        self.assertEqual(settings.reasoning_effort, "low")

    def test_invalid_generation_limit_is_rejected(self):
        with patch.dict(os.environ, {"RATER_MAX_COMPLETION_TOKENS": "0"}, clear=False):
            with self.assertRaises(ValueError):
                get_completion_settings("rater")

    def test_known_model_without_strict_json_schema_is_rejected(self):
        model_name = "example/no-strict-json-schema"
        MODEL_CAPABILITIES[model_name] = ModelCapabilities(
            supports_json_mode=True, supports_strict_json_schema=False
        )
        try:
            with self.assertRaises(ValueError):
                validate_model_capabilities(model_name, requires_strict_json_schema=True)
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

    def test_structured_task_uses_strict_schema(self):
        response_format = get_structured_response_format("rater")

        self.assertEqual(response_format["type"], "json_schema")
        self.assertTrue(response_format["json_schema"]["strict"])
        self.assertEqual(response_format["json_schema"]["schema"]["required"], ["scores", "deductions"])

    def test_missing_api_key_has_a_clear_startup_error(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "GROQ_API_KEY is not configured"):
                get_provider_config()


if __name__ == "__main__":
    unittest.main()
