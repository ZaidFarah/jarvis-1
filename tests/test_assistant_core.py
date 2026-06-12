from __future__ import annotations

from assistant.core import AssistantCore
from config.settings import AppSettings
from integrations.weather_service import WeatherQueryResult
from reminders.service import ReminderQueryResult
from services.openai_service import OpenAIChatResult
from memory.store import SQLiteMemoryStore


class FakeOpenAIService:
    def __init__(self, result: OpenAIChatResult | None = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.messages: list[str] = []
        self.prompts: list[str | None] = []
        self.histories: list[str | None] = []

    def chat(
        self,
        user_text: str,
        system_prompt: str | None = None,
        conversation_history: str | None = None,
    ) -> OpenAIChatResult:
        self.messages.append(user_text)
        self.prompts.append(system_prompt)
        self.histories.append(conversation_history)
        if self.error:
            raise self.error
        assert self.result is not None
        return self.result


class FakeWeatherService:
    def __init__(self, result: WeatherQueryResult) -> None:
        self.result = result
        self.calls: list[str | None] = []

    def current_weather(self, city: str | None = None) -> WeatherQueryResult:
        self.calls.append(city)
        return self.result


class FakeReminderService:
    def __init__(self, list_result: ReminderQueryResult | None = None) -> None:
        self.list_result = list_result or ReminderQueryResult(success=True, text="Here are your reminders:")
        self.calls: list[tuple[object, ...]] = []

    def parse_reminder_command(self, command: str) -> tuple[str, str | None]:
        self.calls.append(("parse", command))
        if command.lower().startswith("remind me to "):
            return command.removeprefix("remind me to ").strip(), None
        raise ValueError("Not a reminder command.")

    def create_reminder(self, title: str, remind_at_text: str | None = None) -> ReminderQueryResult:
        self.calls.append(("create", title, remind_at_text))
        return ReminderQueryResult(success=True, text=f"Reminder created: {title}")

    def list_reminders(self) -> ReminderQueryResult:
        self.calls.append(("list",))
        return self.list_result

    def cancel_reminder(self, reminder_id: int) -> ReminderQueryResult:
        self.calls.append(("cancel", reminder_id))
        return ReminderQueryResult(success=True, text=f"Reminder {reminder_id} cancelled.")

    def complete_reminder(self, reminder_id: int) -> ReminderQueryResult:
        self.calls.append(("complete", reminder_id))
        return ReminderQueryResult(success=True, text=f"Reminder {reminder_id} completed.")


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


def test_assistant_core_stores_history_turns() -> None:
    service = FakeOpenAIService(OpenAIChatResult(success=True, text="OpenAI answer", used_openai=True))
    assistant = AssistantCore(
        settings=AppSettings(_env_file=None, openai_enabled=True, openai_api_key="sk-test"),
        openai_service=service,
    )

    first = assistant.handle_command("first question")
    second = assistant.handle_command("second question")

    assert first.source == "openai"
    assert second.source == "openai"
    assert [turn.role for turn in assistant.conversation_history.messages] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert assistant.conversation_history.messages[0].content == "first question"
    assert assistant.conversation_history.messages[1].content == "OpenAI answer"


def test_assistant_core_reset_conversation_clears_history() -> None:
    service = FakeOpenAIService(OpenAIChatResult(success=True, text="OpenAI answer", used_openai=True))
    assistant = AssistantCore(
        settings=AppSettings(_env_file=None, openai_enabled=True, openai_api_key="sk-test"),
        openai_service=service,
    )

    assistant.handle_command("first question")
    response = assistant.handle_command("reset conversation")

    assert response.text == "Conversation history cleared."
    assert response.source == "local"
    assert assistant.conversation_history.messages == []


def test_assistant_core_history_disabled_still_uses_fallback() -> None:
    service = FakeOpenAIService(error=RuntimeError("network failed"))
    assistant = AssistantCore(
        settings=AppSettings(_env_file=None, conversation_history_enabled=False),
        openai_service=service,
    )

    response = assistant.handle_command("status report")

    assert response.source == "fallback"
    assert assistant.conversation_history.messages == []


def test_assistant_core_can_remember_list_forget_and_reset_memory(tmp_path) -> None:
    settings = AppSettings(_env_file=None, openai_enabled=False, memory_enabled=True, memory_database_path=tmp_path / "memory.db")
    assistant = AssistantCore(settings=settings, openai_service=FakeOpenAIService(), memory_store=SQLiteMemoryStore(settings.memory_database_path))

    remember_response = assistant.handle_command("remember that the office code is blue")
    list_response = assistant.handle_command("what do you remember")
    forget_response = assistant.handle_command("forget that the office code is blue")
    reset_response = assistant.handle_command("reset memory")

    assert remember_response.source == "local"
    assert "I'll remember that" in remember_response.text
    assert "the office code is blue" in list_response.text
    assert "I forgot that" in forget_response.text
    assert "Memory cleared." in reset_response.text


def test_assistant_core_rejects_sensitive_memory() -> None:
    settings = AppSettings(_env_file=None, memory_enabled=True)
    assistant = AssistantCore(settings=settings, openai_service=FakeOpenAIService())

    response = assistant.handle_command("remember that my password is hunter2")

    assert response.accepted is False
    assert "cannot be stored" in response.text.lower() or "sensitive" in response.text.lower()


def test_assistant_core_memory_disabled_fallback() -> None:
    settings = AppSettings(_env_file=None, memory_enabled=False)
    assistant = AssistantCore(settings=settings, openai_service=FakeOpenAIService())

    response = assistant.handle_command("remember that the office code is blue")

    assert response.source == "local"
    assert response.text == "Memory is disabled."


def test_assistant_core_routes_weather_commands_without_openai() -> None:
    weather_service = FakeWeatherService(
        WeatherQueryResult(
            success=True,
            text="Current weather in London: clear sky.",
            provider="openweathermap",
            city="London",
            request_attempted=True,
            api_key_detected=True,
        )
    )
    openai_service = FakeOpenAIService(error=AssertionError("OpenAI should not be called for weather"))
    assistant = AssistantCore(
        settings=AppSettings(_env_file=None, openai_enabled=False),
        openai_service=openai_service,
        weather_service=weather_service,
    )

    response = assistant.handle_command("what is the weather in London")

    assert response.source == "weather"
    assert response.text == "Current weather in London: clear sky."
    assert weather_service.calls == ["London"]
    assert openai_service.messages == []


def test_assistant_core_routes_reminder_commands() -> None:
    reminder_service = FakeReminderService()
    openai_service = FakeOpenAIService(error=AssertionError("OpenAI should not be called for reminders"))
    assistant = AssistantCore(
        settings=AppSettings(_env_file=None, openai_enabled=False),
        openai_service=openai_service,
        weather_service=FakeWeatherService(
            WeatherQueryResult(
                success=True,
                text="Current weather in Nottingham: clear sky.",
                provider="openweathermap",
                city="Nottingham",
                request_attempted=False,
                api_key_detected=False,
            )
        ),
        reminder_service=reminder_service,
    )

    create_response = assistant.handle_command("remind me to stretch")
    list_response = assistant.handle_command("show reminders")
    cancel_response = assistant.handle_command("cancel reminder 7")
    complete_response = assistant.handle_command("complete reminder 8")

    assert create_response.source == "reminders"
    assert "Reminder created" in create_response.text
    assert list_response.text == "Here are your reminders:"
    assert cancel_response.text == "Reminder 7 cancelled."
    assert complete_response.text == "Reminder 8 completed."
    assert [call[0] for call in reminder_service.calls] == ["parse", "create", "list", "cancel", "complete"]
    assert openai_service.messages == []


def test_assistant_core_disabled_reminders_fallback() -> None:
    assistant = AssistantCore(
        settings=AppSettings(_env_file=None, reminders_enabled=False, openai_enabled=False),
        openai_service=FakeOpenAIService(),
        weather_service=FakeWeatherService(
            WeatherQueryResult(
                success=True,
                text="Current weather in Nottingham: clear sky.",
                provider="openweathermap",
                city="Nottingham",
                request_attempted=False,
                api_key_detected=False,
            )
        ),
    )

    response = assistant.handle_command("remind me to stretch at 2026-06-12 18:30")

    assert response.source == "local"
    assert response.text == "Reminders are disabled."
