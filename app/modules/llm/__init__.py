"""Public interface of the llm module: other modules may import only this."""

from app.modules.llm.api import router
from app.modules.llm.service import (
    FakeLLM,
    LLMEmptyResponseError,
    LLMError,
    LLMMessage,
    LLMNotConfiguredError,
    LLMProvider,
    LLMRateLimitError,
    LLMResult,
    LLMUnavailableError,
    get_llm_provider,
)

__all__ = [
    "FakeLLM",
    "LLMEmptyResponseError",
    "LLMError",
    "LLMMessage",
    "LLMNotConfiguredError",
    "LLMProvider",
    "LLMRateLimitError",
    "LLMResult",
    "LLMUnavailableError",
    "get_llm_provider",
    "router",
]
