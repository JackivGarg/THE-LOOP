"""Tests for retry behavior without real network calls or waits."""

import unittest
from unittest.mock import patch

from utils.groq_provider import RetryConfig
from utils.retry import call_with_retry


class JsonValidationError(Exception):
    status_code = 400

    def __str__(self) -> str:
        return "Error code: 400 - {'code': 'json_validate_failed'}"


class RetryTests(unittest.TestCase):
    def test_retries_json_validation_failure(self):
        calls = 0

        def occasionally_invalid_json():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise JsonValidationError()
            return "success"

        with patch("utils.retry.time.sleep") as sleep:
            result = call_with_retry(
                occasionally_invalid_json,
                retry_config=RetryConfig(max_attempts=3, base_delay_seconds=2, max_delay_seconds=30),
            )

        self.assertEqual(result, "success")
        self.assertEqual(calls, 2)
        sleep.assert_called_once_with(0.25)


if __name__ == "__main__":
    unittest.main()
