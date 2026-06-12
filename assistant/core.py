from __future__ import annotations

from dataclasses import dataclass

from config.settings import AppSettings, load_settings
from assistant.conversation import ConversationHistory
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
        self.conversation_history = ConversationHistory(
            enabled=self.settings.conversation_history_enabled,
            max_messages=self.settings.conversation_history_max_messages,
        )

    def reset_conversation(self) -> None:
        self.conversation_history.reset()

    def handle_command(self, command: str) -> AssistantResponse:
        cleaned = command.strip()
        if not cleaned:
            return AssistantResponse(text="Please enter a command first.", accepted=False)

        if cleaned.lower() == "reset conversation":
            self.reset_conversation()
            return AssistantResponse(text="Conversation history cleared.", accepted=True, source="local")

        history_context = self.conversation_history.format_recent_history()
        self.conversation_history.add_user(cleaned)

        try:
            chat_result = self.openai_service.chat(
                cleaned,
                system_prompt=self.settings.system_prompt,
                conversation_history=history_context or None,
            )
        except Exception as exc:
            response = self._fallback_response(cleaned, error=f"{type(exc).__name__}: {exc}")
            self.conversation_history.add_assistant(response.text)
            return response

        if chat_result.success and chat_result.text:
            response = AssistantResponse(text=chat_result.text, accepted=True, source="openai")
            self.conversation_history.add_assistant(response.text)
            return response

        response = self._fallback_response(cleaned, error=chat_result.safe_error)
        self.conversation_history.add_assistant(response.text)
        return response

    def _fallback_response(self, command: str, error: str | None = None) -> AssistantResponse:
        return AssistantResponse(
            text=f"{self.placeholder} You said: {command}",
            accepted=True,
            source="fallback",
            error=error,
        )
