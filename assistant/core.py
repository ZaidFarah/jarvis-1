from __future__ import annotations

from dataclasses import dataclass

from config.settings import AppSettings, load_settings
from services.openai_service import OpenAIService


@dataclass(frozen=True)
class AssistantResponse:
    text: str
    accepted: bool = True
    source: str = "fallback"
    error: str | None = None


class AssistantCore:
    """Assistant routing core.

    Phase 7 supports OpenAI chat responses with a local placeholder fallback.
    """

    placeholder = "Jarvis foundation is running. OpenAI is disabled or unavailable, so local fallback is active."

    def __init__(self, settings: AppSettings | None = None, openai_service: OpenAIService | None = None) -> None:
        self.settings = settings or load_settings()
        self.openai_service = openai_service or OpenAIService(self.settings)

    def handle_command(self, command: str) -> AssistantResponse:
        cleaned = command.strip()
        if not cleaned:
            return AssistantResponse(text="Please enter a command first.", accepted=False)

        try:
            chat_result = self.openai_service.chat(cleaned, system_prompt=self.settings.system_prompt)
        except Exception as exc:
            return self._fallback_response(cleaned, error=f"{type(exc).__name__}: {exc}")

        if chat_result.success and chat_result.text:
            return AssistantResponse(text=chat_result.text, accepted=True, source="openai")

        return self._fallback_response(cleaned, error=chat_result.safe_error)

    def _fallback_response(self, command: str, error: str | None = None) -> AssistantResponse:
        return AssistantResponse(
            text=f"{self.placeholder} You said: {command}",
            accepted=True,
            source="fallback",
            error=error,
        )
