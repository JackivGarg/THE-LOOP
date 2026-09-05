"""Tests for classifying retryable and permanent provider failures."""

import unittest

from utils.groq_provider import PermanentLLMError, RetryableLLMError, _classify_provider_error


class ProviderError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


class LLMErrorClassificationTests(unittest.TestCase):
    def test_rate_limit_error_is_retryable(self):
        result = _classify_provider_error(ProviderError(429, "rate limit exceeded"))

        self.assertIsInstance(result, RetryableLLMError)

    def test_invalid_request_is_permanent(self):
        result = _classify_provider_error(ProviderError(400, "invalid model parameter"))

        self.assertIsInstance(result, PermanentLLMError)


if __name__ == "__main__":
    unittest.main()
