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
