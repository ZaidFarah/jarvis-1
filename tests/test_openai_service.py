from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

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


def test_openai_chat_includes_recent_history_in_prompt() -> None:
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

    result = service.chat("follow up", conversation_history="Recent conversation context:\nUser: hello\nAssistant: hi")

    assert result.success is True
    assert captured["input"] == "Recent conversation context:\nUser: hello\nAssistant: hi\nUser: follow up"


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


def test_openai_chat_stream_emits_text_deltas() -> None:
    captured: dict[str, object] = {}

    class StreamingResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return iter(
                [
                    SimpleNamespace(type="response.created"),
                    SimpleNamespace(type="response.output_text.delta", delta="Systems "),
                    SimpleNamespace(type="response.output_text.delta", delta="nominal."),
                    SimpleNamespace(type="response.completed", response=FakeResponse()),
                ]
            )

    class StreamingClient:
        responses = StreamingResponses()

    settings = AppSettings(
        _env_file=None,
        openai_enabled=True,
        openai_api_key="sk-secret",
        openai_model="gpt-test",
    )
    chunks: list[str] = []
    result = OpenAIService(
        settings,
        client_factory=lambda api_key: StreamingClient(),
    ).chat_stream("status report", chunks.append)

    assert result.success is True
    assert result.text == "Systems nominal."
    assert chunks == ["Systems ", "nominal."]
    assert captured["stream"] is True
    assert captured["model"] == "gpt-test"


def test_openai_chat_stream_falls_back_when_streaming_is_unsupported() -> None:
    calls: list[bool] = []

    class FallbackResponses:
        def create(self, **kwargs):
            streaming = bool(kwargs.get("stream", False))
            calls.append(streaming)
            if streaming:
                raise TypeError("stream is unsupported")
            return FakeResponse()

    class FallbackClient:
        responses = FallbackResponses()

    settings = AppSettings(
        _env_file=None,
        openai_enabled=True,
        openai_api_key="sk-secret",
        openai_model="gpt-test",
    )
    chunks: list[str] = []
    result = OpenAIService(
        settings,
        client_factory=lambda api_key: FallbackClient(),
    ).chat_stream("status report", chunks.append)

    assert result.success is True
    assert result.text == "Jarvis OpenAI check OK."
    assert calls == [True, False]
    assert chunks == []


def test_openai_vision_uses_configured_request_timeout(tmp_path: Path) -> None:
    image_path = tmp_path / "screen.jpg"
    image_path.write_bytes(b"fake-jpeg")
    captured: dict[str, object] = {}

    class VisionResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(output_text="Vision OK.")

    class VisionClient:
        responses = VisionResponses()

    settings = AppSettings(
        _env_file=None,
        openai_vision_enabled=True,
        openai_api_key="sk-secret",
        openai_vision_model="gpt-vision-test",
        openai_vision_timeout_seconds=8.5,
    )
    result = OpenAIService(settings, client_factory=lambda api_key: VisionClient()).analyze_image(
        image_path,
        prompt="Describe it.",
    )

    assert result.success is True
    assert captured["model"] == "gpt-vision-test"
    assert captured["timeout"] == 8.5
    assert "api_key" not in captured
    content = captured["input"][0]["content"]  # type: ignore[index]
    assert content[0]["type"] == "input_text"
    assert content[1]["type"] == "input_image"
