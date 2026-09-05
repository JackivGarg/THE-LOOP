"""Central configuration and provider utilities for Groq-backed pipeline nodes."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal, TypeVar

from dotenv import load_dotenv
from groq import Groq
from pydantic import BaseModel, ValidationError

from utils.llm_schemas import CriteriaUpdaterResponse, PlannerResponse, RaterResponse


# Load local developer configuration once, while keeping every value out of git.
load_dotenv()


TaskName = Literal["planner", "code_writer", "code_updater", "rater", "criteria_updater"]
StructuredTaskName = Literal["planner", "rater", "criteria_updater"]
SchemaModel = TypeVar("SchemaModel", bound=BaseModel)


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


@dataclass(frozen=True)
class LLMResponseMetadata:
    """Debug metadata for one successful Groq completion."""

    task: TaskName
    model: str
    request_id: str | None
    latency_ms: int
    finish_reason: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    raw_content: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "model": self.model,
            "request_id": self.request_id,
            "latency_ms": self.latency_ms,
            "finish_reason": self.finish_reason,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "raw_content": self.raw_content,
        }


@dataclass(frozen=True)
class LLMCompletion:
    """Normalized completion content plus observable request metadata."""

    content: str
    metadata: LLMResponseMetadata


class LLMRequestError(RuntimeError):
    """Base class for errors raised by the centralized Groq request layer."""

    def __init__(self, message: str, *, metadata: LLMResponseMetadata | None = None):
        super().__init__(message)
        self.metadata = metadata


class RetryableLLMError(LLMRequestError):
    """A transient provider or structured-output failure that can be retried."""


class MalformedStructuredResponseError(RetryableLLMError):
    """A model response that did not satisfy the declared structured contract."""


class PermanentLLMError(LLMRequestError):
    """A request/configuration error that should be surfaced without retrying."""


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


def _classify_provider_error(error: Exception) -> LLMRequestError:
    """Classify provider failures so retries never mask permanent errors."""
    status_code = getattr(error, "status_code", None)
    if status_code is None and hasattr(error, "response"):
        status_code = getattr(error.response, "status_code", None)
    message = str(error)

    if status_code in {408, 409, 429, 500, 502, 503, 504}:
        return RetryableLLMError(message)
    if status_code == 400 and "json_validate_failed" in message:
        return MalformedStructuredResponseError(message)
    return PermanentLLMError(message)


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


def _structured_model(task: StructuredTaskName) -> type[BaseModel]:
    return {
        "planner": PlannerResponse,
        "rater": RaterResponse,
        "criteria_updater": CriteriaUpdaterResponse,
    }[task]


def get_structured_response_format(task: StructuredTaskName) -> dict:
    """Return the strict Groq JSON Schema contract for a structured-output task."""
    schema_names: dict[StructuredTaskName, str] = {
        "planner": "website_plan",
        "rater": "website_rating",
        "criteria_updater": "updated_rating_criteria",
    }
    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema_names[task],
            "strict": True,
            "schema": _structured_model(task).model_json_schema(),
        },
    }


def request_completion(task: TaskName, messages: list[dict[str, str]]) -> LLMCompletion:
    """Execute one Groq completion with centralized timeout and observability."""
    model, settings = get_task_config(task)
    request_kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": settings.temperature,
        "max_completion_tokens": settings.max_completion_tokens,
        "reasoning_effort": settings.reasoning_effort,
    }
    if settings.top_p is not None:
        request_kwargs["top_p"] = settings.top_p
    if settings.requires_strict_json_schema:
        request_kwargs["response_format"] = get_structured_response_format(task)  # type: ignore[arg-type]

    started_at = time.perf_counter()
    try:
        raw_response = get_groq_client().chat.completions.with_raw_response.create(**request_kwargs)
        response = raw_response.parse()
    except Exception as error:
        raise _classify_provider_error(error) from error

    latency_ms = round((time.perf_counter() - started_at) * 1000)
    choice = response.choices[0]
    raw_content = choice.message.content or ""
    usage = response.usage
    metadata = LLMResponseMetadata(
        task=task,
        model=model,
        request_id=(
            raw_response.headers.get("x-request-id")
            or raw_response.headers.get("request-id")
            or getattr(response, "_request_id", None)
        ),
        latency_ms=latency_ms,
        finish_reason=choice.finish_reason,
        prompt_tokens=getattr(usage, "prompt_tokens", None),
        completion_tokens=getattr(usage, "completion_tokens", None),
        total_tokens=getattr(usage, "total_tokens", None),
        raw_content=raw_content,
    )
    return LLMCompletion(content=raw_content, metadata=metadata)


def request_structured_completion(task: StructuredTaskName, messages: list[dict[str, str]]) -> tuple[BaseModel, LLMCompletion]:
    """Execute and strictly validate a structured completion against its Pydantic contract."""
    completion = request_completion(task, messages)
    try:
        parsed = _structured_model(task).model_validate_json(completion.content)
    except ValidationError as error:
        raise MalformedStructuredResponseError(
            f"{task} returned a response that failed local schema validation: {error}",
            metadata=completion.metadata,
        ) from error
    return parsed, completion


def record_completion_metadata(state: dict, completion: LLMCompletion) -> None:
    """Append a bounded request trace to Streamlit session state for debugging."""
    trace = state.setdefault("llm_request_trace", [])
    trace.append(completion.metadata.as_dict())
    del trace[:-20]
