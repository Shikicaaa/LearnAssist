from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal, Protocol

from app.shared.config import get_settings
from app.shared.errors import AppError


class LLMError(AppError):
    """Base class for failures of the AI provider, mapped to HTTP errors."""


class LLMNotConfiguredError(LLMError):
    status_code = 503
    code = "llm_not_configured"


class LLMRateLimitError(LLMError):
    status_code = 429
    code = "llm_rate_limited"


class LLMUnavailableError(LLMError):
    status_code = 502
    code = "llm_unavailable"


class LLMEmptyResponseError(LLMError):
    status_code = 502
    code = "llm_empty_response"


@dataclass(frozen=True)
class LLMMessage:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class LLMResult:
    text: str
    provider: str
    model: str
    tokens_in: int
    tokens_out: int


class LLMProvider(Protocol):
    name: str
    model: str

    def generate(
        self,
        messages: list[LLMMessage],
        system: str | None = None,
        max_output_tokens: int | None = None,
    ) -> LLMResult: ...


@dataclass
class FakeLLM:
    """Scripted provider for tests: records every call, replies with a fixed text or raises."""

    reply: str = "Zdravo! Kako mogu da pomognem?"
    error: Exception | None = None
    name: str = "fake"
    model: str = "fake-model"
    calls: list[dict] = field(default_factory=list)

    def generate(
        self,
        messages: list[LLMMessage],
        system: str | None = None,
        max_output_tokens: int | None = None,
    ) -> LLMResult:
        self.calls.append(
            {"messages": messages, "system": system, "max_output_tokens": max_output_tokens}
        )
        if self.error:
            raise self.error
        return LLMResult(self.reply, self.name, self.model, tokens_in=7, tokens_out=11)


@lru_cache
def _build_provider(provider: str, api_key: str, model: str, timeout: float) -> LLMProvider:
    if provider == "gemini":
        if not api_key:
            raise LLMNotConfiguredError("GEMINI_API_KEY is not set")
        # Imported here so processes that never talk to an LLM (the worker) skip the SDK.
        from app.modules.llm.gemini import GeminiProvider

        return GeminiProvider.create(api_key, model, timeout)
    raise LLMNotConfiguredError(f"Unknown LLM_PROVIDER '{provider}'. Supported: gemini")


def get_llm_provider() -> LLMProvider:
    s = get_settings()
    return _build_provider(s.llm_provider, s.gemini_api_key, s.gemini_model, s.llm_timeout_seconds)
