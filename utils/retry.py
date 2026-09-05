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

            # 429 = Rate limited — retry with backoff
            if status_code == 429:
                retry_after = None
                if hasattr(e, "response") and hasattr(e.response, "headers"):
                    retry_after = e.response.headers.get("retry-after")
                wait_time = float(retry_after) if retry_after else policy.base_delay_seconds * (2 ** attempt)
                wait_time = min(wait_time, policy.max_delay_seconds)
                time.sleep(wait_time)
                continue

            # Fallback string check for 429 only (not generic "rate_limit" which 413 also contains)
            if "429" in error_str:
                wait_time = min(policy.base_delay_seconds * (2 ** attempt), policy.max_delay_seconds)
                time.sleep(wait_time)
                continue

            # Any other error → raise immediately
            raise

    raise RuntimeError(
        f"Max attempts ({policy.max_attempts}) exceeded on Groq API call. "
        f"Last error: {last_exception}"
    )
