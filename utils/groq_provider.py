"""Central configuration and provider utilities for Groq-backed pipeline nodes."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from dotenv import load_dotenv
from groq import Groq


# Load local developer configuration once, while keeping every value out of git.
load_dotenv()


TaskName = Literal["planner", "code_writer", "code_updater", "rater", "criteria_updater"]


@dataclass(frozen=True)
class ModelConfig:
    """Model assignment for every LLM task in the website-generation pipeline."""

    planner: str
    code_writer: str
    code_updater: str
    rater: str
    criteria_updater: str


@dataclass(frozen=True)
class CompletionSettings:
    """Generation parameters shared by a task type."""

    temperature: float
    max_completion_tokens: int
    top_p: float | None = None
    requires_json_mode: bool = False


@dataclass(frozen=True)
class RetryConfig:
    """Retry policy used for rate-limited Groq requests."""

    max_attempts: int
    base_delay_seconds: float
    max_delay_seconds: float


@dataclass(frozen=True)
class ProviderConfig:
    """Connection-level configuration for the Groq SDK client."""

    api_key: str
    timeout_seconds: float


@dataclass(frozen=True)
class ModelCapabilities:
    """Capabilities used to validate a model before a task is dispatched."""

    supports_json_mode: bool


# These are the production defaults recommended by Groq after the Llama 3.x
# retirement. Environment variables always take precedence over these values.
DEFAULT_MODELS = ModelConfig(
    planner="openai/gpt-oss-120b",
    code_writer="openai/gpt-oss-120b",
    code_updater="openai/gpt-oss-120b",
    rater="openai/gpt-oss-120b",
    criteria_updater="openai/gpt-oss-20b",
)

MODEL_CAPABILITIES: dict[str, ModelCapabilities] = {
    "openai/gpt-oss-20b": ModelCapabilities(supports_json_mode=True),
    "openai/gpt-oss-120b": ModelCapabilities(supports_json_mode=True),
    "qwen/qwen3.6-27b": ModelCapabilities(supports_json_mode=True),
    "groq/compound": ModelCapabilities(supports_json_mode=True),
    "groq/compound-mini": ModelCapabilities(supports_json_mode=True),
}


def _positive_int(name: str, default: int) -> int:
    value = os.getenv(name, str(default))
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer; received {value!r}") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be greater than zero; received {parsed}")
    return parsed


def _positive_float(name: str, default: float) -> float:
    value = os.getenv(name, str(default))
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number; received {value!r}") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be greater than zero; received {parsed}")
    return parsed


def _temperature(name: str, default: float) -> float:
    value = os.getenv(name, str(default))
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number; received {value!r}") from exc
    if not 0 <= parsed <= 2:
        raise ValueError(f"{name} must be between 0 and 2; received {parsed}")
    return parsed


def load_model_config() -> ModelConfig:
    """Load task-to-model assignments from environment variables."""
    return ModelConfig(
        planner=os.getenv("PLANNER_MODEL", DEFAULT_MODELS.planner),
        code_writer=os.getenv("CODE_WRITER_MODEL", DEFAULT_MODELS.code_writer),
        code_updater=os.getenv("CODE_UPDATER_MODEL", DEFAULT_MODELS.code_updater),
        rater=os.getenv("RATER_MODEL", DEFAULT_MODELS.rater),
        criteria_updater=os.getenv("CRITERIA_UPDATER_MODEL", DEFAULT_MODELS.criteria_updater),
    )


def get_completion_settings(task: TaskName) -> CompletionSettings:
    """Return validated generation limits and sampling parameters for a task."""
    defaults: dict[TaskName, CompletionSettings] = {
        "planner": CompletionSettings(temperature=0.5, max_completion_tokens=2048, requires_json_mode=True),
        "code_writer": CompletionSettings(temperature=0.7, max_completion_tokens=5000, top_p=0.8),
        "code_updater": CompletionSettings(temperature=0.7, max_completion_tokens=5000, top_p=0.8),
        "rater": CompletionSettings(temperature=0.3, max_completion_tokens=512, requires_json_mode=True),
        "criteria_updater": CompletionSettings(temperature=0.3, max_completion_tokens=1024, requires_json_mode=True),
    }
    default = defaults[task]
    prefix = task.upper()
    return CompletionSettings(
        temperature=_temperature(f"{prefix}_TEMPERATURE", default.temperature),
        max_completion_tokens=_positive_int(f"{prefix}_MAX_COMPLETION_TOKENS", default.max_completion_tokens),
        top_p=default.top_p,
        requires_json_mode=default.requires_json_mode,
    )


def get_retry_config() -> RetryConfig:
    """Load a single retry policy used by every pipeline node."""
    return RetryConfig(
        max_attempts=_positive_int("GROQ_MAX_RETRY_ATTEMPTS", 3),
        base_delay_seconds=_positive_float("GROQ_RETRY_BASE_DELAY_SECONDS", 2),
        max_delay_seconds=_positive_float("GROQ_RETRY_MAX_DELAY_SECONDS", 30),
    )


def get_provider_config() -> ProviderConfig:
    """Load and validate credentials and connection settings without exposing secrets."""
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key or api_key == "your_groq_api_key_here":
        raise RuntimeError(
            "GROQ_API_KEY is not configured. Add it to a local .env file; do not commit the key."
        )
    return ProviderConfig(
        api_key=api_key,
        timeout_seconds=_positive_float("GROQ_REQUEST_TIMEOUT_SECONDS", 60),
    )


@lru_cache(maxsize=4)
def _build_client(api_key: str, timeout_seconds: float) -> Groq:
    # Retries are deliberately disabled in the SDK because retry.py owns the
    # application's retry policy and keeps behavior consistent across nodes.
    return Groq(api_key=api_key, timeout=timeout_seconds, max_retries=0)


def get_groq_client() -> Groq:
    """Return a cached Groq client configured with the centralized timeout."""
    config = get_provider_config()
    return _build_client(config.api_key, config.timeout_seconds)


def validate_model_capabilities(model: str, *, requires_json_mode: bool) -> None:
    """Fail early when a known configured model cannot satisfy a task contract.

    Unknown models remain permitted to support future Groq catalog additions and
    private deployments. Their capabilities should be verified before production use.
    """
    if not model or not model.strip():
        raise ValueError("Configured Groq model name cannot be empty.")
    capabilities = MODEL_CAPABILITIES.get(model)
    if requires_json_mode and capabilities and not capabilities.supports_json_mode:
        raise ValueError(f"Model {model!r} does not support the JSON mode required by this task.")


def get_task_config(task: TaskName) -> tuple[str, CompletionSettings]:
    """Resolve and validate the model and generation settings for one task."""
    model = getattr(load_model_config(), task)
    settings = get_completion_settings(task)
    validate_model_capabilities(model, requires_json_mode=settings.requires_json_mode)
    return model, settings
