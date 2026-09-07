"""Tests for classifying retryable and permanent provider failures."""

import unittest

from utils.groq_provider import PermanentLLMError, RetryableLLMError, _classify_provider_error


class ProviderError(Exception):
    def __init__(self, status_code: int, message: str, headers=None):
        super().__init__(message)
        self.status_code = status_code
        self.response = type("Response", (), {"headers": headers or {}})()


class LLMErrorClassificationTests(unittest.TestCase):
    def test_rate_limit_error_is_retryable(self):
        result = _classify_provider_error(ProviderError(429, "rate limit exceeded"))

        self.assertIsInstance(result, RetryableLLMError)

    def test_rate_limit_delay_is_read_from_provider_message(self):
        result = _classify_provider_error(ProviderError(429, "Please try again in 2.12s."))

        self.assertEqual(result.retry_after_seconds, 2.12)

    def test_rate_limit_header_takes_precedence(self):
        result = _classify_provider_error(ProviderError(429, "Please try again in 2.12s.", {"retry-after": "5"}))

        self.assertEqual(result.retry_after_seconds, 5.0)

    def test_invalid_request_is_permanent(self):
        result = _classify_provider_error(ProviderError(400, "invalid model parameter"))

        self.assertIsInstance(result, PermanentLLMError)


if __name__ == "__main__":
    unittest.main()
