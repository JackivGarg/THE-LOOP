"""
Retry utility for Groq API calls.
Handles 429 rate-limit errors with proper retry-after header reading.
Does NOT retry 413 (request too large) — those need prompt/token reduction, not waiting.
"""

import time

from utils.groq_provider import (
    MalformedStructuredResponseError,
    RetryConfig,
    RetryableLLMError,
    get_retry_config,
)


class RetryExhaustedError(RuntimeError):
    """Raised after all retryable attempts fail while preserving debug metadata."""

    def __init__(self, attempts: int, last_exception: RetryableLLMError):
        super().__init__(
            f"Max attempts ({attempts}) exceeded on a retryable Groq request. "
            f"Last error: {last_exception}"
        )
        self.metadata = last_exception.metadata
        self.retry_after_seconds = last_exception.retry_after_seconds


def call_with_retry(fn, *args, retry_config: RetryConfig | None = None, **kwargs):
    """
    Call a function with automatic retry on Groq 429 rate-limit errors.
    
    - Reads the 'retry-after' header from the Groq error response when available
    - Falls back to exponential backoff (2^attempt seconds) if header is missing
    - 413 errors (request too large) are raised immediately — retrying won't help
    - Groq JSON-validation failures are retried quickly because a fresh generation
      can satisfy a best-effort structured-output constraint.
    - Non-rate-limit errors are raised immediately without retry
    
    Args:
        fn: The callable to invoke (typically a Groq API call)
        *args: Positional arguments passed to fn
        retry_config: Shared retry policy. Defaults to the configured Groq policy.
        **kwargs: Keyword arguments passed to fn
    
    Returns:
        The return value of fn on success
    
    Raises:
        RetryExhaustedError: If all retryable attempts are exhausted.
        PermanentLLMError: For non-retryable provider/configuration errors.
    """
    policy = retry_config or get_retry_config()
    last_exception = None

    for attempt in range(policy.max_attempts):
        try:
            return fn(*args, **kwargs)
        except RetryableLLMError as e:
            last_exception = e

            # Do not wait after the final failed attempt.
            if attempt == policy.max_attempts - 1:
                break

            if isinstance(e, MalformedStructuredResponseError):
                wait_time = min(0.25 * (2 ** attempt), 1.0)
            else:
                backoff_seconds = policy.base_delay_seconds * (2 ** attempt)
                provider_delay = e.retry_after_seconds or 0.0
                # Groq's own wait estimate is more precise than generic backoff.
                # Add a small cushion so a fractional retry-after does not fail again.
                wait_time = max(backoff_seconds, provider_delay + 0.25)
                wait_time = min(wait_time, policy.max_delay_seconds)
            time.sleep(wait_time)

    raise RetryExhaustedError(policy.max_attempts, last_exception)
