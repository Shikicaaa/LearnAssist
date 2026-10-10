import httpx
import pytest
from google.genai import errors, types

from app.main import app
from app.modules.llm import (
    FakeLLM,
    LLMEmptyResponseError,
    LLMMessage,
    LLMNotConfiguredError,
    LLMRateLimitError,
    LLMUnavailableError,
    get_llm_provider,
)
from app.modules.llm.gemini import GeminiProvider
from app.shared.config import get_settings
from tests.helpers import signup

URL = "/api/v1/llm/test"


@pytest.fixture
def alice(client):
    return signup(client, "alice@example.com")


@pytest.fixture
def fake():
    llm = FakeLLM()
    app.dependency_overrides[get_llm_provider] = lambda: llm
    yield llm
    app.dependency_overrides.pop(get_llm_provider, None)


def ask(client, headers, message="cao", **extra):
    return client.post(URL, json={"message": message, **extra}, headers=headers)


class TestTestEndpoint:
    def test_answers_a_simple_greeting(self, client, alice, fake):
        r = ask(client, alice, "cao")
        assert r.status_code == 200
        body = r.json()
        assert body["answer"] == "Zdravo! Kako mogu da pomognem?"
        assert (body["provider"], body["model"]) == ("fake", "fake-model")
        assert (body["tokens_in"], body["tokens_out"]) == (7, 11)
        assert body["latency_ms"] >= 0

    def test_message_and_system_prompt_reach_the_provider(self, client, alice, fake):
        ask(client, alice, "  cao  ", system="Odgovaraj kratko.")
        [call] = fake.calls
        assert call["messages"] == [LLMMessage("user", "cao")]
        assert call["system"] == "Odgovaraj kratko."
        assert call["max_output_tokens"] == 2048

    def test_requires_authentication(self, client, fake):
        assert ask(client, {}).status_code == 401
        assert fake.calls == []

    @pytest.mark.parametrize(
        "payload", [{"message": ""}, {"message": "   "}, {"message": "x" * 4001}, {}]
    )
    def test_invalid_input_is_422_and_costs_nothing(self, client, alice, fake, payload):
        assert client.post(URL, json=payload, headers=alice).status_code == 422
        assert fake.calls == []

    def test_is_hidden_outside_development(self, client, alice, fake, monkeypatch):
        monkeypatch.setattr(get_settings(), "environment", "production")
        assert ask(client, alice).status_code == 404
        assert fake.calls == []

    def test_is_rate_limited_per_user(self, client, alice, fake, monkeypatch):
        monkeypatch.setattr(get_settings(), "llm_test_requests_per_minute", 2)
        bob = signup(client, "bob@example.com")
        statuses = [ask(client, alice).status_code for _ in range(3)]
        assert statuses == [200, 200, 429]
        assert ask(client, bob).status_code == 200

    @pytest.mark.parametrize(
        "error,status,code",
        [
            (LLMRateLimitError("quota"), 429, "llm_rate_limited"),
            (LLMUnavailableError("down"), 502, "llm_unavailable"),
            (LLMEmptyResponseError("empty"), 502, "llm_empty_response"),
            (LLMNotConfiguredError("no key"), 503, "llm_not_configured"),
        ],
    )
    def test_provider_failures_become_clear_http_errors(
        self, client, alice, fake, error, status, code
    ):
        fake.error = error
        r = ask(client, alice)
        assert r.status_code == status
        assert r.json()["error"]["code"] == code


class FakeModels:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def generate_content(self, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        if self.error:
            raise self.error
        return self.response


class FakeClient:
    def __init__(self, response=None, error=None):
        self.models = FakeModels(response, error)


def reply(text="Zdravo!", prompt=5, out=3, thoughts=0, finish=types.FinishReason.STOP):
    candidate = types.Candidate(
        content=types.Content(role="model", parts=[types.Part(text=text)]) if text else None,
        finish_reason=finish,
    )
    return types.GenerateContentResponse(
        candidates=[candidate],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=prompt, candidates_token_count=out, thoughts_token_count=thoughts
        ),
    )


def provider(response=None, error=None):
    client = FakeClient(response, error)
    return GeminiProvider(client, "gemini-test"), client.models


def api_error(cls, code, message="boom", status="STATUS"):
    return cls(code, {"error": {"code": code, "message": message, "status": status}})


class TestGeminiProvider:
    def test_builds_the_request_and_parses_the_answer(self):
        p, models = provider(reply("Zdravo!", prompt=5, out=3, thoughts=4))
        result = p.generate(
            [
                LLMMessage("user", "cao"),
                LLMMessage("assistant", "Zdravo!"),
                LLMMessage("user", "kako si?"),
            ],
            system="Budi kratak.",
            max_output_tokens=100,
        )
        assert (result.text, result.provider, result.model) == ("Zdravo!", "gemini", "gemini-test")
        assert (result.tokens_in, result.tokens_out) == (5, 7)  # thinking tokens count as output

        [call] = models.calls
        assert call["model"] == "gemini-test"
        assert [(c.role, c.parts[0].text) for c in call["contents"]] == [
            ("user", "cao"),
            ("model", "Zdravo!"),
            ("user", "kako si?"),
        ]
        assert call["config"].system_instruction == "Budi kratak."
        assert call["config"].max_output_tokens == 100

    def test_works_without_usage_information(self):
        response = reply()
        response.usage_metadata = None
        p, _ = provider(response)
        result = p.generate([LLMMessage("user", "cao")])
        assert (result.tokens_in, result.tokens_out) == (0, 0)

    def test_empty_answer_explains_why(self):
        p, _ = provider(reply(text="", finish=types.FinishReason.MAX_TOKENS))
        with pytest.raises(LLMEmptyResponseError, match="MAX_TOKENS"):
            p.generate([LLMMessage("user", "cao")])

    def test_blocked_prompt_is_reported(self):
        blocked = types.GenerateContentResponse(
            prompt_feedback=types.GenerateContentResponsePromptFeedback(
                block_reason=types.BlockedReason.SAFETY
            )
        )
        p, _ = provider(blocked)
        with pytest.raises(LLMEmptyResponseError, match="blocked: SAFETY"):
            p.generate([LLMMessage("user", "cao")])

    @pytest.mark.parametrize(
        "error,expected",
        [
            (api_error(errors.ClientError, 429, "Quota exceeded"), LLMRateLimitError),
            (api_error(errors.ClientError, 403, "denied"), LLMNotConfiguredError),
            (api_error(errors.ClientError, 401, "no auth"), LLMNotConfiguredError),
            (
                api_error(errors.ClientError, 400, "API key not valid. Please pass a valid one."),
                LLMNotConfiguredError,
            ),
            (api_error(errors.ClientError, 404, "model not found"), LLMNotConfiguredError),
            (api_error(errors.ClientError, 400, "invalid argument"), LLMUnavailableError),
            (api_error(errors.ServerError, 503, "overloaded"), LLMUnavailableError),
            (httpx.ReadTimeout("slow"), LLMUnavailableError),
            (httpx.ConnectError("no network"), LLMUnavailableError),
            (TimeoutError(), LLMUnavailableError),
        ],
    )
    def test_provider_errors_are_translated(self, error, expected):
        p, _ = provider(error=error)
        with pytest.raises(expected):
            p.generate([LLMMessage("user", "cao")])

    def test_upstream_error_text_is_not_leaked_to_clients(self):
        p, _ = provider(error=api_error(errors.ClientError, 400, "API key AIzaSECRET is invalid"))
        with pytest.raises(LLMNotConfiguredError) as raised:
            p.generate([LLMMessage("user", "cao")])
        assert "AIzaSECRET" not in raised.value.message

    def test_missing_model_error_names_the_setting_to_fix(self):
        p, _ = provider(error=api_error(errors.ClientError, 404, "not found"))
        with pytest.raises(LLMNotConfiguredError, match="GEMINI_MODEL"):
            p.generate([LLMMessage("user", "cao")])


class TestFactory:
    def test_missing_api_key_is_a_clear_503_not_a_crash(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "gemini_api_key", "")
        with pytest.raises(LLMNotConfiguredError, match="GEMINI_API_KEY"):
            get_llm_provider()

    def test_unknown_provider_is_rejected(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "llm_provider", "skynet")
        with pytest.raises(LLMNotConfiguredError, match="skynet"):
            get_llm_provider()

    def test_builds_gemini_from_settings(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "llm_provider", "gemini")
        monkeypatch.setattr(get_settings(), "gemini_api_key", "test-key-not-real")
        monkeypatch.setattr(get_settings(), "gemini_model", "gemini-test")
        built = get_llm_provider()
        assert isinstance(built, GeminiProvider) and built.model == "gemini-test"

    def test_missing_key_surfaces_as_503_over_http(self, client, monkeypatch):
        monkeypatch.setattr(get_settings(), "gemini_api_key", "")
        headers = signup(client, "alice@example.com")
        r = ask(client, headers)
        assert r.status_code == 503 and r.json()["error"]["code"] == "llm_not_configured"


@pytest.mark.live
def test_real_gemini_answers_a_greeting():
    result = get_llm_provider().generate(
        [LLMMessage("user", "cao")],
        system="Odgovaraj kratko, jednom rečenicom, na srpskom.",
        max_output_tokens=2048,
    )
    print(f"\n[{result.model}] {result.text!r} (in={result.tokens_in}, out={result.tokens_out})")
    assert result.text.strip()
