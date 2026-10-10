import logging

import httpx
from google import genai
from google.genai import errors, types

from app.modules.llm.service import (
    LLMEmptyResponseError,
    LLMMessage,
    LLMNotConfiguredError,
    LLMRateLimitError,
    LLMResult,
    LLMUnavailableError,
)

logger = logging.getLogger(__name__)
_ROLES = {"user": "user", "assistant": "model"}


class GeminiProvider:
    name = "gemini"

    def __init__(self, client: genai.Client, model: str):
        self._client = client
        self.model = model

    @classmethod
    def create(cls, api_key: str, model: str, timeout_seconds: float) -> GeminiProvider:
        options = types.HttpOptions(
            timeout=int(timeout_seconds * 1000),
            # Retry only server-side hiccups. A 429 (quota) will not clear in a second or two.
            retry_options=types.HttpRetryOptions(
                attempts=3, initial_delay=1.0, http_status_codes=[500, 502, 503, 504]
            ),
        )
        return cls(genai.Client(api_key=api_key, http_options=options), model)

    def generate(
        self,
        messages: list[LLMMessage],
        system: str | None = None,
        max_output_tokens: int | None = None,
    ) -> LLMResult:
        contents = [
            types.Content(role=_ROLES[m.role], parts=[types.Part(text=m.content)])
            for m in messages
        ]
        config = types.GenerateContentConfig(
            system_instruction=system, max_output_tokens=max_output_tokens
        )
        try:
            response = self._client.models.generate_content(
                model=self.model, contents=contents, config=config
            )
        except errors.APIError as exc:
            raise self._translate(exc) from exc
        except (httpx.TransportError, TimeoutError, ConnectionError) as exc:
            logger.warning("Gemini request failed: %s", type(exc).__name__)
            raise LLMUnavailableError(
                "The AI provider could not be reached or took too long. Try again."
            ) from exc
        return self._to_result(response)

    def _to_result(self, response: types.GenerateContentResponse) -> LLMResult:
        text = response.text
        if not text:
            raise LLMEmptyResponseError(f"The model returned no text ({_why_empty(response)}).")
        usage = response.usage_metadata
        return LLMResult(
            text=text,
            provider=self.name,
            model=self.model,
            tokens_in=(usage.prompt_token_count or 0) if usage else 0,
            # Thinking tokens are billed as output, so they count here too.
            tokens_out=(
                (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)
                if usage
                else 0
            ),
        )

    def _translate(self, exc: errors.APIError):
        # Details go to the log; the message shown to API clients stays generic on purpose.
        logger.warning(
            "Gemini API error: code=%s status=%s message=%.200s", exc.code, exc.status, exc.message
        )
        message = str(exc.message or "")
        if exc.code == 429:
            return LLMRateLimitError(
                "The AI provider's rate limit or quota was reached. Try again in a minute."
            )
        if exc.code in (401, 403) or (exc.code == 400 and "API key" in message):
            return LLMNotConfiguredError(
                "The AI provider rejected the API key. Check GEMINI_API_KEY."
            )
        if exc.code == 404:
            return LLMNotConfiguredError(
                f"The AI model '{self.model}' was not found. Check GEMINI_MODEL."
            )
        return LLMUnavailableError("The AI provider could not process the request. Try again.")


def _why_empty(response: types.GenerateContentResponse) -> str:
    feedback = response.prompt_feedback
    if feedback and feedback.block_reason:
        return f"prompt blocked: {feedback.block_reason.name}"
    if response.candidates and response.candidates[0].finish_reason:
        return f"finish reason: {response.candidates[0].finish_reason.name}"
    return "no candidates"
