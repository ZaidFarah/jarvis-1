from __future__ import annotations

from assistant.core import AssistantCore
from config.settings import AppSettings
from services.openai_service import OpenAIChatResult


class FakeOpenAIService:
    def __init__(self, result: OpenAIChatResult | None = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.messages: list[str] = []
        self.prompts: list[str | None] = []

    def chat(self, user_text: str, system_prompt: str | None = None) -> OpenAIChatResult:
        self.messages.append(user_text)
        self.prompts.append(system_prompt)
        if self.error:
            raise self.error
        assert self.result is not None
        return self.result


def test_assistant_core_returns_placeholder_response() -> None:
    assistant = AssistantCore(settings=AppSettings(_env_file=None))

    response = assistant.handle_command("status report")

    assert response.accepted is True
    assert "Jarvis foundation is running" in response.text
    assert "status report" in response.text
    assert response.source == "fallback"


def test_assistant_core_rejects_empty_command() -> None:
    assistant = AssistantCore(settings=AppSettings(_env_file=None))

    response = assistant.handle_command("   ")

    assert response.accepted is False
    assert response.text == "Please enter a command first."


def test_assistant_core_routes_to_openai_when_enabled() -> None:
    service = FakeOpenAIService(OpenAIChatResult(success=True, text="OpenAI answer", used_openai=True))
    assistant = AssistantCore(openai_service=service)

    response = assistant.handle_command("status report")

    assert response.text == "OpenAI answer"
    assert response.source == "openai"
    assert service.messages == ["status report"]


def test_assistant_core_uses_fallback_when_openai_disabled() -> None:
    service = FakeOpenAIService(
        OpenAIChatResult(success=False, text="", used_openai=False, safe_error="OpenAI is disabled.")
    )
    assistant = AssistantCore(openai_service=service)

    response = assistant.handle_command("status report")

    assert response.source == "fallback"
    assert "Jarvis foundation is running" in response.text
    assert response.error == "OpenAI is disabled."


def test_assistant_core_uses_fallback_on_openai_error() -> None:
    service = FakeOpenAIService(error=RuntimeError("network failed"))
    assistant = AssistantCore(openai_service=service)

    response = assistant.handle_command("status report")

    assert response.source == "fallback"
    assert "status report" in response.text
    assert response.error == "RuntimeError: network failed"
