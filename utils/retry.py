"""
Retry utility for Groq API calls.
Handles 429 rate-limit errors with proper retry-after header reading.
Does NOT retry 413 (request too large) — those need prompt/token reduction, not waiting.
"""

import time

from utils.groq_provider import RetryConfig, get_retry_config


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
        RuntimeError: If all retries are exhausted
        Exception: Any non-429 error from fn
    """
    policy = retry_config or get_retry_config()
    last_exception = None

    for attempt in range(policy.max_attempts):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_exception = e
            error_str = str(e)

            # Check for Groq SDK errors with .status_code attribute
            status_code = getattr(e, "status_code", None)
            if status_code is None and hasattr(e, "response"):
                status_code = getattr(e.response, "status_code", None)

            # 413 = Request too large — NEVER retry, the request itself is the problem
            if status_code == 413 or "413" in error_str:
                raise

            is_rate_limited = status_code == 429 or "429" in error_str
            is_json_validation_failure = status_code == 400 and "json_validate_failed" in error_str

            # Do not wait after the final failed attempt.
            if attempt == policy.max_attempts - 1:
                break

            # 429 = rate limited — retry with the provider-supplied or exponential delay.
            if is_rate_limited:
                retry_after = None
                if hasattr(e, "response") and hasattr(e.response, "headers"):
                    retry_after = e.response.headers.get("retry-after")
                try:
                    wait_time = float(retry_after) if retry_after else policy.base_delay_seconds * (2 ** attempt)
                except (TypeError, ValueError):
                    wait_time = policy.base_delay_seconds * (2 ** attempt)
                wait_time = min(wait_time, policy.max_delay_seconds)
                time.sleep(wait_time)
                continue

            # A malformed best-effort JSON generation can succeed on the next sample.
            if is_json_validation_failure:
                wait_time = min(0.25 * (2 ** attempt), 1.0)
                time.sleep(wait_time)
                continue

            # Any other error → raise immediately
            raise

    raise RuntimeError(
        f"Max attempts ({policy.max_attempts}) exceeded on Groq API call. "
        f"Last error: {last_exception}"
    )
