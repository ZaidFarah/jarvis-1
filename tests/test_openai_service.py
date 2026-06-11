from __future__ import annotations

from config.settings import AppSettings
from services.openai_service import OpenAIService, format_openai_check_report, format_openai_error


class FakeResponse:
    output_text = "Jarvis OpenAI check OK."


class FakeResponses:
    def create(self, **kwargs):
        assert kwargs["model"] == "gpt-test"
        assert "api_key" not in kwargs
        return FakeResponse()


class FakeClient:
    responses = FakeResponses()


def test_openai_check_disabled_does_not_attempt_request() -> None:
    called = False

    def factory(api_key: str):
        nonlocal called
        called = True
        return FakeClient()

    settings = AppSettings(_env_file=None, openai_enabled=False, openai_api_key="", openai_model="gpt-test")
    report = OpenAIService(settings, client_factory=factory).run_check()

    assert report.enabled is False
    assert report.api_key_detected is False
    assert report.request_attempted is False
    assert report.is_successful is True
    assert called is False


def test_openai_check_enabled_missing_api_key_does_not_attempt_request() -> None:
    called = False

    def factory(api_key: str):
        nonlocal called
        called = True
        return FakeClient()

    settings = AppSettings(_env_file=None, openai_enabled=True, openai_api_key="", openai_model="gpt-test")
    report = OpenAIService(settings, client_factory=factory).run_check()

    assert report.enabled is True
    assert report.api_key_detected is False
    assert report.request_attempted is False
    assert "OPENAI_API_KEY is not set" in (report.safe_error or "")
    assert called is False


def test_openai_provider_configuration_and_success() -> None:
    captured_key = ""

    def factory(api_key: str):
        nonlocal captured_key
        captured_key = api_key
        return FakeClient()

    settings = AppSettings(_env_file=None, openai_enabled=True, openai_api_key="sk-secret", openai_model="gpt-test")
    report = OpenAIService(settings, client_factory=factory).run_check()
    text = format_openai_check_report(report)

    assert captured_key == "sk-secret"
    assert report.model == "gpt-test"
    assert report.request_attempted is True
    assert report.success is True
    assert "API key detected: yes" in text
    assert "sk-secret" not in text


def test_openai_safe_error_formatting_redacts_key_like_text() -> None:
    error = RuntimeError("request failed with key sk-test-secret and OPENAI_API_KEY")

    text = format_openai_error(error)

    assert "RuntimeError:" in text
    assert "sk-test-secret" not in text
    assert "OPENAI_API_KEY" not in text
    assert "[redacted]" in text


def test_openai_chat_disabled_returns_safe_fallback_result() -> None:
    settings = AppSettings(_env_file=None, openai_enabled=False, openai_api_key="", openai_model="gpt-test")
    result = OpenAIService(settings).chat("hello")

    assert result.success is False
    assert result.used_openai is False
    assert result.safe_error == "OpenAI is disabled."


def test_openai_chat_success_uses_configured_model_and_prompt() -> None:
    captured: dict[str, str] = {}

    class ChatResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return FakeResponse()

    class ChatClient:
        responses = ChatResponses()

    settings = AppSettings(
        _env_file=None,
        openai_enabled=True,
        openai_api_key="sk-secret",
        openai_model="gpt-test",
        system_prompt="You are Jarvis.",
    )
    service = OpenAIService(settings, client_factory=lambda api_key: ChatClient())

    result = service.chat("hello")

    assert result.success is True
    assert result.text == "Jarvis OpenAI check OK."
    assert captured["model"] == "gpt-test"
    assert captured["instructions"] == "You are Jarvis."
    assert captured["input"] == "hello"


def test_openai_chat_error_is_safe() -> None:
    class FailingResponses:
        def create(self, **kwargs):
            del kwargs
            raise RuntimeError("bad key sk-secret")

    class FailingClient:
        responses = FailingResponses()

    settings = AppSettings(_env_file=None, openai_enabled=True, openai_api_key="sk-secret", openai_model="gpt-test")
    result = OpenAIService(settings, client_factory=lambda api_key: FailingClient()).chat("hello")

    assert result.success is False
    assert result.safe_error is not None
    assert "sk-secret" not in result.safe_error
