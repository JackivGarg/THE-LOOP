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
    reasoning_effort: str | None = None
    requires_strict_json_schema: bool = False


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
    supports_strict_json_schema: bool


# These are the production defaults recommended by Groq after the Llama 3.x
# retirement. Environment variables always take precedence over these values.
DEFAULT_MODELS = ModelConfig(
    planner="openai/gpt-oss-20b",
    code_writer="openai/gpt-oss-20b",
    code_updater="openai/gpt-oss-20b",
    rater="openai/gpt-oss-20b",
    criteria_updater="openai/gpt-oss-20b",
)

MODEL_CAPABILITIES: dict[str, ModelCapabilities] = {
    "openai/gpt-oss-20b": ModelCapabilities(supports_json_mode=True, supports_strict_json_schema=True),
    "openai/gpt-oss-120b": ModelCapabilities(supports_json_mode=True, supports_strict_json_schema=True),
    "qwen/qwen3.6-27b": ModelCapabilities(supports_json_mode=True, supports_strict_json_schema=False),
    "groq/compound": ModelCapabilities(supports_json_mode=True, supports_strict_json_schema=False),
    "groq/compound-mini": ModelCapabilities(supports_json_mode=True, supports_strict_json_schema=False),
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
        "planner": CompletionSettings(
            temperature=0.2, max_completion_tokens=1024, reasoning_effort="low", requires_strict_json_schema=True
        ),
        "code_writer": CompletionSettings(
            temperature=0.6, max_completion_tokens=5000, top_p=0.8, reasoning_effort="low"
        ),
        "code_updater": CompletionSettings(
            temperature=0.5, max_completion_tokens=5000, top_p=0.8, reasoning_effort="low"
        ),
        "rater": CompletionSettings(
            temperature=0.1, max_completion_tokens=512, reasoning_effort="low", requires_strict_json_schema=True
        ),
        "criteria_updater": CompletionSettings(
            temperature=0.1, max_completion_tokens=512, reasoning_effort="low", requires_strict_json_schema=True
        ),
    }
    default = defaults[task]
    prefix = task.upper()
    return CompletionSettings(
        temperature=_temperature(f"{prefix}_TEMPERATURE", default.temperature),
        max_completion_tokens=_positive_int(f"{prefix}_MAX_COMPLETION_TOKENS", default.max_completion_tokens),
        top_p=default.top_p,
        reasoning_effort=default.reasoning_effort,
        requires_strict_json_schema=default.requires_strict_json_schema,
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


def validate_model_capabilities(model: str, *, requires_strict_json_schema: bool) -> None:
    """Fail early when a known configured model cannot satisfy a task contract.

    Unknown models remain permitted to support future Groq catalog additions and
    private deployments. Their capabilities should be verified before production use.
    """
    if not model or not model.strip():
        raise ValueError("Configured Groq model name cannot be empty.")
    capabilities = MODEL_CAPABILITIES.get(model)
    if requires_strict_json_schema and capabilities and not capabilities.supports_strict_json_schema:
        raise ValueError(f"Model {model!r} does not support strict JSON Schema required by this task.")


def get_task_config(task: TaskName) -> tuple[str, CompletionSettings]:
    """Resolve and validate the model and generation settings for one task."""
    model = getattr(load_model_config(), task)
    settings = get_completion_settings(task)
    validate_model_capabilities(model, requires_strict_json_schema=settings.requires_strict_json_schema)
    return model, settings


def get_structured_response_format(task: TaskName) -> dict:
    """Return the strict Groq JSON Schema contract for a structured-output task."""
    schemas: dict[TaskName, dict] = {
        "planner": {
            "name": "website_plan",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["write", "update"]},
                    "instruction": {"type": "string"},
                },
                "required": ["action", "instruction"],
                "additionalProperties": False,
            },
        },
        "rater": {
            "name": "website_rating",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "scores": {
                        "type": "object",
                        "properties": {
                            "layout": {"type": "integer", "minimum": 0, "maximum": 10},
                            "typography": {"type": "integer", "minimum": 0, "maximum": 10},
                            "responsiveness": {"type": "integer", "minimum": 0, "maximum": 10},
                            "visual_design": {"type": "integer", "minimum": 0, "maximum": 10},
                            "description_match": {"type": "integer", "minimum": 0, "maximum": 10},
                        },
                        "required": ["layout", "typography", "responsiveness", "visual_design", "description_match"],
                        "additionalProperties": False,
                    },
                    "deductions": {"type": "string"},
                },
                "required": ["scores", "deductions"],
                "additionalProperties": False,
            },
        },
        "criteria_updater": {
            "name": "updated_rating_criteria",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "updated_criteria": {"type": "string"},
                    "changelog": {"type": "string"},
                },
                "required": ["updated_criteria", "changelog"],
                "additionalProperties": False,
            },
        },
        "code_writer": {},
        "code_updater": {},
    }
    if not schemas[task]:
        raise ValueError(f"Task {task!r} does not use structured output.")
    return {"type": "json_schema", "json_schema": schemas[task]}
