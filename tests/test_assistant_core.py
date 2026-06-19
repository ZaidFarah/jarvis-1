from __future__ import annotations

from pathlib import Path

from assistant.core import AssistantCore
from config.settings import AppSettings
from security.confirmation import ConfirmationResult
from integrations.calendar_service import CalendarCreateResult, CalendarQueryResult
from integrations.gmail_service import GmailUnreadResult
from integrations.weather_service import WeatherQueryResult
from reminders.models import ReminderCheckResult
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

    def check_due_reminders(self) -> ReminderCheckResult:
        self.calls.append(("check",))
        return ReminderCheckResult(success=True, text="Due reminders:\n1. stretch at 2026-06-12 18:00", due_reminders=[])


class FakeCalendarService:
    def __init__(self, result: CalendarQueryResult | None = None) -> None:
        self.result = result or CalendarQueryResult(
            success=True,
            text="Calendar for today:\n- 09:00 Standup",
            provider="google_calendar",
            day_label="today",
            request_attempted=True,
            authenticated=True,
            client_secret_detected=True,
            token_detected=True,
        )
        self.calls: list[str] = []
        self.create_calls: list[tuple[str, str, int, str | None, str | None]] = []

    def current_events(self, day_label: str = "today") -> CalendarQueryResult:
        self.calls.append(day_label)
        return self.result

    def create_event(
        self,
        title: str,
        start_text: str,
        duration_minutes: int,
        location: str | None = None,
        description: str | None = None,
    ) -> CalendarCreateResult:
        self.create_calls.append((title, start_text, duration_minutes, location, description))
        return CalendarCreateResult(
            success=True,
            text=f"Created calendar event: {title}",
            provider="google_calendar",
            title=title,
            start_text=start_text,
            duration_minutes=duration_minutes,
            request_attempted=True,
            authenticated=True,
            client_secret_detected=True,
            token_detected=True,
            create_enabled=True,
            write_scope_detected=True,
            event_id="abc123",
        )


class FakeGmailService:
    def __init__(self, result: GmailUnreadResult | None = None) -> None:
        self.result = result or GmailUnreadResult(
            enabled=True,
            success=True,
            text="Unread Gmail messages (1):\n1. From: Alice\n   Subject: Hello\n   Date: 2026-06-12\n   Snippet: Quick note",
            provider="google_gmail",
            request_attempted=True,
            authenticated=True,
            client_secret_detected=True,
            token_detected=True,
            unread_count=1,
            emails=[],
        )
        self.calls = 0
        self.draft_calls: list[tuple[str, str, str]] = []
        self.draft_list_calls = 0
        self.send_draft_calls: list[str] = []

    def unread_emails(self) -> GmailUnreadResult:
        self.calls += 1
        return self.result

    def create_draft(self, recipient: str, subject: str, body: str):
        self.draft_calls.append((recipient, subject, body))
        return type(
            "DraftResult",
            (),
            {
                "success": True,
                "text": f"Created Gmail draft for {recipient}.",
                "safe_error": None,
            },
        )()

    def list_drafts(self):
        self.draft_list_calls += 1
        return type(
            "DraftListResult",
            (),
            {
                "success": True,
                "text": "Gmail drafts: draft-1 -> recipient@example.com / Hello.",
                "safe_error": None,
                "drafts": [
                    type(
                        "DraftItem",
                        (),
                        {
                            "draft_id": "draft-1",
                            "recipient": "recipient@example.com",
                            "subject": "Hello",
                            "snippet": "Draft preview",
                        },
                    )()
                ],
            },
        )()

    def send_draft(self, draft_id: str):
        self.send_draft_calls.append(draft_id)
        return type(
            "SendDraftResult",
            (),
            {
                "success": True,
                "text": f"Sent Gmail draft {draft_id}.",
                "safe_error": None,
            },
        )()


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


def test_assistant_core_text_chat_keeps_normal_prompt_when_voice_is_concise() -> None:
    service = FakeOpenAIService(OpenAIChatResult(success=True, text="OpenAI answer", used_openai=True))
    settings = AppSettings(_env_file=None, openai_enabled=True, openai_api_key="sk-test")
    assistant = AssistantCore(settings=settings, openai_service=service)

    response = assistant.handle_command("status report")

    assert response.source == "openai"
    assert service.prompts == [settings.system_prompt]
    assert settings.voice_concise_instruction not in (service.prompts[0] or "")


def test_assistant_core_voice_command_uses_concise_prompt_when_configured() -> None:
    service = FakeOpenAIService(OpenAIChatResult(success=True, text="Short answer.", used_openai=True))
    settings = AppSettings(
        _env_file=None,
        openai_enabled=True,
        openai_api_key="sk-test",
        voice_response_mode="concise",
        voice_concise_instruction="Keep it short for speech.",
    )
    assistant = AssistantCore(settings=settings, openai_service=service)

    response = assistant.handle_voice_command("status report")

    assert response.source == "openai"
    assert service.messages == ["status report"]
    assert service.prompts == [f"{settings.system_prompt}\n\nKeep it short for speech."]


def test_assistant_core_voice_command_can_use_normal_prompt() -> None:
    service = FakeOpenAIService(OpenAIChatResult(success=True, text="Normal answer.", used_openai=True))
    settings = AppSettings(
        _env_file=None,
        openai_enabled=True,
        openai_api_key="sk-test",
        voice_response_mode="normal",
    )
    assistant = AssistantCore(settings=settings, openai_service=service)

    response = assistant.handle_voice_command("status report")

    assert response.source == "openai"
    assert service.prompts == [settings.system_prompt]


def test_assistant_core_fast_voice_uses_fast_concise_prompt() -> None:
    service = FakeOpenAIService(OpenAIChatResult(success=True, text="Brief answer.", used_openai=True))
    settings = AppSettings(
        _env_file=None,
        openai_enabled=True,
        openai_api_key="sk-test",
        voice_response_mode="normal",
        fast_voice_concise_responses=True,
        fast_voice_concise_instruction="Answer in one brief sentence.",
    )
    assistant = AssistantCore(settings=settings, openai_service=service)

    response = assistant.handle_fast_voice_command("explain the status")

    assert response.source == "openai"
    assert service.prompts == [f"{settings.system_prompt}\n\nAnswer in one brief sentence."]


def test_assistant_core_fast_voice_can_disable_concise_prompt() -> None:
    service = FakeOpenAIService(OpenAIChatResult(success=True, text="Normal answer.", used_openai=True))
    settings = AppSettings(
        _env_file=None,
        openai_enabled=True,
        openai_api_key="sk-test",
        fast_voice_concise_responses=False,
    )
    assistant = AssistantCore(settings=settings, openai_service=service)

    response = assistant.handle_fast_voice_command("explain the status")

    assert response.source == "openai"
    assert service.prompts == [settings.system_prompt]


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
        settings=AppSettings(_env_file=None, openai_enabled=False, calendar_enabled=True),
        openai_service=openai_service,
        weather_service=weather_service,
    )

    response = assistant.handle_command("what is the weather in London")

    assert response.source == "weather"
    assert response.text == "Current weather in London: clear sky."
    assert weather_service.calls == ["London"]
    assert openai_service.messages == []


def test_assistant_core_routes_calendar_commands() -> None:
    calendar_service = FakeCalendarService()
    openai_service = FakeOpenAIService(error=AssertionError("OpenAI should not be called for calendar"))
    assistant = AssistantCore(
        settings=AppSettings(_env_file=None, openai_enabled=False, calendar_enabled=True),
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
        calendar_service=calendar_service,
        confirmation_handler=lambda *args: ConfirmationResult(
            approved=True,
            denied=False,
            timed_out=False,
            reason="Approved.",
            log_file=Path("confirmations.log"),
        ),
    )

    response = assistant.handle_command("what is on my calendar today")

    assert response.source == "calendar"
    assert "Standup" in response.text
    assert calendar_service.calls == ["today"]
    assert openai_service.messages == []


def test_assistant_core_routes_calendar_tomorrow_commands() -> None:
    calendar_service = FakeCalendarService(
        CalendarQueryResult(
            success=True,
            text="Calendar for tomorrow:\n- 10:00 Planning",
            provider="google_calendar",
            day_label="tomorrow",
            request_attempted=True,
            authenticated=True,
            client_secret_detected=True,
            token_detected=True,
        )
    )
    assistant = AssistantCore(
        settings=AppSettings(_env_file=None, openai_enabled=False, calendar_enabled=True),
        openai_service=FakeOpenAIService(error=AssertionError("OpenAI should not be called for calendar")),
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
        calendar_service=calendar_service,
        confirmation_handler=lambda *args: ConfirmationResult(
            approved=True,
            denied=False,
            timed_out=False,
            reason="Approved.",
            log_file=Path("confirmations.log"),
        ),
    )

    response = assistant.handle_command("what is on my calendar tomorrow")

    assert response.source == "calendar"
    assert "Planning" in response.text
    assert calendar_service.calls == ["tomorrow"]


def test_assistant_core_calendar_confirmation_denied_blocks_read() -> None:
    calendar_service = FakeCalendarService()
    assistant = AssistantCore(
        settings=AppSettings(_env_file=None, openai_enabled=False, calendar_enabled=True),
        openai_service=FakeOpenAIService(error=AssertionError("OpenAI should not be called for calendar")),
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
        calendar_service=calendar_service,
        confirmation_handler=lambda *args: ConfirmationResult(
            approved=False,
            denied=True,
            timed_out=False,
            reason="Denied.",
            log_file=Path("confirmations.log"),
        ),
    )

    response = assistant.handle_command("what is on my calendar today")

    assert response.source == "local"
    assert response.accepted is False
    assert response.text == "Denied."
    assert calendar_service.calls == []


def test_assistant_core_routes_calendar_create_commands() -> None:
    calendar_service = FakeCalendarService()
    assistant = AssistantCore(
        settings=AppSettings(_env_file=None, openai_enabled=False, calendar_enabled=True, calendar_create_enabled=True),
        openai_service=FakeOpenAIService(error=AssertionError("OpenAI should not be called for calendar")),
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
        calendar_service=calendar_service,
        confirmation_handler=lambda *args: ConfirmationResult(
            approved=True,
            denied=False,
            timed_out=False,
            reason="Approved.",
            log_file=Path("confirmations.log"),
        ),
    )

    response = assistant.handle_command("create calendar event Team Sync at 2026-06-12 18:30 for 30")

    assert response.source == "calendar"
    assert "Created calendar event: Team Sync" in response.text
    assert calendar_service.create_calls == [("Team Sync", "2026-06-12 18:30", 30, None, None)]


def test_assistant_core_routes_gmail_unread_commands() -> None:
    gmail_service = FakeGmailService()
    assistant = AssistantCore(
        settings=AppSettings(_env_file=None, openai_enabled=False, gmail_enabled=True),
        openai_service=FakeOpenAIService(error=AssertionError("OpenAI should not be called for Gmail")),
        gmail_service=gmail_service,
        confirmation_handler=lambda *args: ConfirmationResult(
            approved=True,
            denied=False,
            timed_out=False,
            reason="Approved.",
            log_file=Path("confirmations.log"),
        ),
    )

    response = assistant.handle_command("read my unread emails")

    assert response.source == "gmail"
    assert "Unread Gmail messages" in response.text
    assert gmail_service.calls == 1


def test_assistant_core_gmail_confirmation_denied_blocks_read() -> None:
    gmail_service = FakeGmailService()
    assistant = AssistantCore(
        settings=AppSettings(_env_file=None, openai_enabled=False, gmail_enabled=True),
        openai_service=FakeOpenAIService(error=AssertionError("OpenAI should not be called for Gmail")),
        gmail_service=gmail_service,
        confirmation_handler=lambda *args: ConfirmationResult(
            approved=False,
            denied=True,
            timed_out=False,
            reason="Denied.",
            log_file=Path("confirmations.log"),
        ),
    )

    response = assistant.handle_command("show unread emails")

    assert response.source == "local"
    assert response.accepted is False
    assert response.text == "Denied."
    assert gmail_service.calls == 0


def test_assistant_core_routes_gmail_draft_list_commands() -> None:
    gmail_service = FakeGmailService()
    assistant = AssistantCore(
        settings=AppSettings(_env_file=None, openai_enabled=False, gmail_enabled=True, gmail_send_draft_enabled=True),
        openai_service=FakeOpenAIService(error=AssertionError("OpenAI should not be called for Gmail")),
        gmail_service=gmail_service,
        confirmation_handler=lambda *args: ConfirmationResult(
            approved=True,
            denied=False,
            timed_out=False,
            reason="Approved.",
            log_file=Path("confirmations.log"),
        ),
    )

    response = assistant.handle_command("list email drafts")

    assert response.source == "gmail"
    assert "Gmail drafts" in response.text
    assert gmail_service.draft_list_calls == 1


def test_assistant_core_routes_gmail_send_draft_commands() -> None:
    gmail_service = FakeGmailService()
    assistant = AssistantCore(
        settings=AppSettings(_env_file=None, openai_enabled=False, gmail_enabled=True, gmail_send_draft_enabled=True),
        openai_service=FakeOpenAIService(error=AssertionError("OpenAI should not be called for Gmail")),
        gmail_service=gmail_service,
        confirmation_handler=lambda *args: ConfirmationResult(
            approved=True,
            denied=False,
            timed_out=False,
            reason="Approved.",
            log_file=Path("confirmations.log"),
        ),
    )

    response = assistant.handle_command("send email draft draft-1")

    assert response.source == "gmail"
    assert "Sent Gmail draft draft-1" in response.text
    assert gmail_service.send_draft_calls == ["draft-1"]


def test_assistant_core_gmail_send_draft_confirmation_denied_blocks_send() -> None:
    gmail_service = FakeGmailService()
    assistant = AssistantCore(
        settings=AppSettings(_env_file=None, openai_enabled=False, gmail_enabled=True, gmail_send_draft_enabled=True),
        openai_service=FakeOpenAIService(error=AssertionError("OpenAI should not be called for Gmail")),
        gmail_service=gmail_service,
        confirmation_handler=lambda *args: ConfirmationResult(
            approved=False,
            denied=True,
            timed_out=False,
            reason="Denied.",
            log_file=Path("confirmations.log"),
        ),
    )

    response = assistant.handle_command("send email draft draft-1")

    assert response.source == "local"
    assert response.accepted is False
    assert response.text == "Denied."
    assert gmail_service.send_draft_calls == []


def test_assistant_core_routes_gmail_draft_commands() -> None:
    gmail_service = FakeGmailService()
    assistant = AssistantCore(
        settings=AppSettings(_env_file=None, openai_enabled=False, gmail_enabled=True, gmail_draft_enabled=True),
        openai_service=FakeOpenAIService(error=AssertionError("OpenAI should not be called for Gmail")),
        gmail_service=gmail_service,
        confirmation_handler=lambda *args: ConfirmationResult(
            approved=True,
            denied=False,
            timed_out=False,
            reason="Approved.",
            log_file=Path("confirmations.log"),
        ),
    )

    response = assistant.handle_command("draft email to recipient@example.com subject Hello body Quick note")

    assert response.source == "gmail"
    assert "Created Gmail draft" in response.text
    assert gmail_service.draft_calls == [("recipient@example.com", "Hello", "Quick note")]


def test_assistant_core_gmail_draft_confirmation_denied_blocks_create() -> None:
    gmail_service = FakeGmailService()
    assistant = AssistantCore(
        settings=AppSettings(_env_file=None, openai_enabled=False, gmail_enabled=True, gmail_draft_enabled=True),
        openai_service=FakeOpenAIService(error=AssertionError("OpenAI should not be called for Gmail")),
        gmail_service=gmail_service,
        confirmation_handler=lambda *args: ConfirmationResult(
            approved=False,
            denied=True,
            timed_out=False,
            reason="Denied.",
            log_file=Path("confirmations.log"),
        ),
    )

    response = assistant.handle_command("create email draft to recipient@example.com subject Hello body Quick note")

    assert response.source == "local"
    assert response.accepted is False
    assert response.text == "Denied."
    assert gmail_service.draft_calls == []


def test_assistant_core_calendar_create_confirmation_denied_blocks_create() -> None:
    calendar_service = FakeCalendarService()
    assistant = AssistantCore(
        settings=AppSettings(_env_file=None, openai_enabled=False, calendar_enabled=True, calendar_create_enabled=True),
        openai_service=FakeOpenAIService(error=AssertionError("OpenAI should not be called for calendar")),
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
        calendar_service=calendar_service,
        confirmation_handler=lambda *args: ConfirmationResult(
            approved=False,
            denied=True,
            timed_out=False,
            reason="Denied.",
            log_file=Path("confirmations.log"),
        ),
    )

    response = assistant.handle_command("schedule Team Sync at 2026-06-12 18:30 for 30")

    assert response.source == "local"
    assert response.accepted is False
    assert response.text == "Denied."
    assert calendar_service.create_calls == []


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


def test_assistant_core_disabled_due_reminders_fallback() -> None:
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

    response = assistant.handle_command("check reminders")

    assert response.source == "local"
    assert response.text == "Reminders are disabled."


def test_assistant_core_routes_due_reminder_commands() -> None:
    reminder_service = FakeReminderService()
    assistant = AssistantCore(
        settings=AppSettings(_env_file=None, openai_enabled=False),
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
        reminder_service=reminder_service,
    )

    response = assistant.handle_command("check reminders")

    assert response.source == "reminders"
    assert "Due reminders:" in response.text
    assert reminder_service.calls == [("check",)]


def test_assistant_core_routes_read_file_command_with_confirmation(tmp_path: Path) -> None:
    folder = tmp_path / "documents"
    folder.mkdir()
    (folder / "notes.md").write_text("hello world", encoding="utf-8")
    settings = AppSettings(
        _env_file=None,
        openai_enabled=False,
        file_access_enabled=True,
        file_read_enabled=True,
        confirmation_required=True,
        file_access_allowed_folders=f"documents={folder}",
    )
    confirmations: list[tuple[str, str, str]] = []

    def approve(action_name: str, risk_level: str, description: str) -> ConfirmationResult:
        confirmations.append((action_name, risk_level, description))
        return ConfirmationResult(
            approved=True,
            denied=False,
            timed_out=False,
            reason="Approved.",
            log_file=tmp_path / "confirmations.log",
        )

    assistant = AssistantCore(settings=settings, openai_service=FakeOpenAIService(), confirmation_handler=approve)

    response = assistant.handle_command("read file notes.md in documents")

    assert response.source == "file_access"
    assert response.accepted is True
    assert response.text == "hello world"
    assert confirmations and confirmations[0][0] == "read file contents"


def test_assistant_core_read_file_confirmation_denied_blocks_read(tmp_path: Path) -> None:
    folder = tmp_path / "documents"
    folder.mkdir()
    (folder / "notes.md").write_text("hello world", encoding="utf-8")
    settings = AppSettings(
        _env_file=None,
        openai_enabled=False,
        file_access_enabled=True,
        file_read_enabled=True,
        confirmation_required=True,
        file_access_allowed_folders=f"documents={folder}",
    )

    def deny(action_name: str, risk_level: str, description: str) -> ConfirmationResult:
        del action_name, risk_level, description
        return ConfirmationResult(
            approved=False,
            denied=True,
            timed_out=False,
            reason="Denied.",
            log_file=tmp_path / "confirmations.log",
        )

    assistant = AssistantCore(settings=settings, openai_service=FakeOpenAIService(), confirmation_handler=deny)

    response = assistant.handle_command("read file notes.md in documents")

    assert response.source == "local"
    assert response.accepted is False
    assert response.text == "Denied."


def test_assistant_core_summarize_file_disabled_fallback(tmp_path: Path) -> None:
    folder = tmp_path / "documents"
    folder.mkdir()
    (folder / "notes.md").write_text("hello world", encoding="utf-8")
    assistant = AssistantCore(
        settings=AppSettings(
            _env_file=None,
            openai_enabled=True,
            file_access_enabled=True,
            file_read_enabled=True,
            file_summary_enabled=False,
            confirmation_required=True,
            file_access_allowed_folders=f"documents={folder}",
        ),
        openai_service=FakeOpenAIService(OpenAIChatResult(success=True, text="summary", used_openai=True)),
        confirmation_handler=lambda *args: ConfirmationResult(
            approved=True,
            denied=False,
            timed_out=False,
            reason="Approved.",
            log_file=tmp_path / "confirmations.log",
        ),
    )

    response = assistant.handle_command("summarize file notes.md in documents")

    assert response.source == "local"
    assert response.text == "File summarization is disabled."


def test_assistant_core_summarize_file_confirmation_denied_before_read(tmp_path: Path) -> None:
    folder = tmp_path / "documents"
    folder.mkdir()
    (folder / "notes.md").write_text("hello world", encoding="utf-8")
    settings = AppSettings(
        _env_file=None,
        openai_enabled=True,
        file_access_enabled=True,
        file_read_enabled=True,
        file_summary_enabled=True,
        confirmation_required=True,
        file_access_allowed_folders=f"documents={folder}",
    )

    def deny_read(action_name: str, risk_level: str, description: str) -> ConfirmationResult:
        del action_name, risk_level, description
        return ConfirmationResult(
            approved=False,
            denied=True,
            timed_out=False,
            reason="Denied before read.",
            log_file=tmp_path / "confirmations.log",
        )

    assistant = AssistantCore(settings=settings, openai_service=FakeOpenAIService(), confirmation_handler=deny_read)

    response = assistant.handle_command("summarize file notes.md in documents")

    assert response.source == "local"
    assert response.accepted is False
    assert response.text == "Denied before read."


def test_assistant_core_summarize_file_confirmation_denied_before_openai(tmp_path: Path) -> None:
    folder = tmp_path / "documents"
    folder.mkdir()
    (folder / "notes.md").write_text("hello world", encoding="utf-8")
    settings = AppSettings(
        _env_file=None,
        openai_enabled=True,
        file_access_enabled=True,
        file_read_enabled=True,
        file_summary_enabled=True,
        confirmation_required=True,
        file_access_allowed_folders=f"documents={folder}",
    )
    confirmations: list[str] = []

    def gate(action_name: str, risk_level: str, description: str) -> ConfirmationResult:
        confirmations.append(action_name)
        if len(confirmations) == 1:
            return ConfirmationResult(
                approved=True,
                denied=False,
                timed_out=False,
                reason="Approved.",
                log_file=tmp_path / "confirmations.log",
            )
        return ConfirmationResult(
            approved=False,
            denied=True,
            timed_out=False,
            reason="Denied before OpenAI.",
            log_file=tmp_path / "confirmations.log",
        )

    openai_service = FakeOpenAIService(OpenAIChatResult(success=True, text="summary", used_openai=True))
    assistant = AssistantCore(settings=settings, openai_service=openai_service, confirmation_handler=gate)

    response = assistant.handle_command("summarize file notes.md in documents")

    assert response.source == "local"
    assert response.accepted is False
    assert response.text == "Denied before OpenAI."
    assert openai_service.messages == []


def test_assistant_core_summarize_file_success_with_mocked_openai(tmp_path: Path) -> None:
    folder = tmp_path / "documents"
    folder.mkdir()
    (folder / "notes.md").write_text("hello world", encoding="utf-8")
    settings = AppSettings(
        _env_file=None,
        openai_enabled=True,
        file_access_enabled=True,
        file_read_enabled=True,
        file_summary_enabled=True,
        confirmation_required=True,
        file_access_allowed_folders=f"documents={folder}",
    )
    confirmations: list[str] = []

    def approve_all(action_name: str, risk_level: str, description: str) -> ConfirmationResult:
        confirmations.append(action_name)
        return ConfirmationResult(
            approved=True,
            denied=False,
            timed_out=False,
            reason="Approved.",
            log_file=tmp_path / "confirmations.log",
        )

    openai_service = FakeOpenAIService(OpenAIChatResult(success=True, text="A concise summary.", used_openai=True))
    assistant = AssistantCore(settings=settings, openai_service=openai_service, confirmation_handler=approve_all)

    response = assistant.handle_command("summarize file notes.md in documents")

    assert response.source == "openai"
    assert response.accepted is True
    assert response.text == "A concise summary."
    assert confirmations.count("read file contents") == 1
    assert confirmations.count("send text to openai") == 1
    assert assistant.conversation_history.messages == []


def test_assistant_core_summarize_file_rejects_absolute_path(tmp_path: Path) -> None:
    assistant = AssistantCore(
        settings=AppSettings(
            _env_file=None,
            openai_enabled=True,
            file_access_enabled=True,
            file_read_enabled=True,
            file_summary_enabled=True,
        ),
        openai_service=FakeOpenAIService(OpenAIChatResult(success=True, text="summary", used_openai=True)),
    )

    response = assistant.handle_command("summarize file C:\\Windows\\win.ini in documents")

    assert response.accepted is False
    assert "plain filename" in response.text.lower()


def test_assistant_core_summarize_file_rejects_traversal(tmp_path: Path) -> None:
    assistant = AssistantCore(
        settings=AppSettings(
            _env_file=None,
            openai_enabled=True,
            file_access_enabled=True,
            file_read_enabled=True,
            file_summary_enabled=True,
        ),
        openai_service=FakeOpenAIService(OpenAIChatResult(success=True, text="summary", used_openai=True)),
    )

    response = assistant.handle_command("summarize file ..\\secret.md in documents")

    assert response.accepted is False
    assert "plain filename" in response.text.lower()


def test_assistant_core_summarize_file_rejects_disallowed_extension(tmp_path: Path) -> None:
    folder = tmp_path / "documents"
    folder.mkdir()
    (folder / "notes.log").write_text("hello world", encoding="utf-8")
    assistant = AssistantCore(
        settings=AppSettings(
            _env_file=None,
            openai_enabled=True,
            file_access_enabled=True,
            file_read_enabled=True,
            file_summary_enabled=True,
            confirmation_required=True,
            file_access_allowed_folders=f"documents={folder}",
        ),
        openai_service=FakeOpenAIService(OpenAIChatResult(success=True, text="summary", used_openai=True)),
        confirmation_handler=lambda *args: ConfirmationResult(
            approved=True,
            denied=False,
            timed_out=False,
            reason="Approved.",
            log_file=tmp_path / "confirmations.log",
        ),
    )

    response = assistant.handle_command("summarize file notes.log in documents")

    assert response.accepted is False
    assert "not allowed" in response.text.lower()
