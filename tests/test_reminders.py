from __future__ import annotations

from pathlib import Path

import pytest

from config.settings import AppSettings
from integrations.weather_service import WeatherQueryResult
from reminders.service import ReminderService, ReminderTimeError
from reminders.store import ReminderStore


class FakeOpenAIService:
    def chat(self, *args, **kwargs):
        del args, kwargs
        raise AssertionError("OpenAI should not be called")


class FakeWeatherService:
    def __init__(self) -> None:
        self.result = WeatherQueryResult(
            success=True,
            text="Current weather in Nottingham: clear sky.",
            provider="openweathermap",
            city="Nottingham",
            request_attempted=False,
            api_key_detected=False,
        )

    def current_weather(self, city: str | None = None) -> WeatherQueryResult:
        del city
        return self.result


def test_reminder_store_create_list_cancel_and_complete(tmp_path: Path) -> None:
    store = ReminderStore(tmp_path / "reminders.db")

    entry = store.create("stretch", "2026-06-12 18:30")
    reminders = store.list_reminders()

    assert entry.title == "stretch"
    assert len(reminders) == 1
    assert reminders[0].title == "stretch"
    assert reminders[0].status == "pending"

    assert store.complete(entry.id) is True
    assert store.list_reminders()[0].status == "completed"

    assert store.cancel(entry.id) is True
    assert store.list_reminders()[0].status == "cancelled"


def test_reminder_service_rejects_invalid_time_format() -> None:
    with pytest.raises(ReminderTimeError):
        ReminderService.parse_reminder_time("tomorrow evening")


def test_reminder_service_parses_iso_like_time() -> None:
    parsed = ReminderService.parse_reminder_time("2026-06-12 18:30")

    assert parsed.year == 2026
    assert parsed.month == 6
    assert parsed.day == 12
    assert parsed.hour == 18
    assert parsed.minute == 30


def test_reminder_service_create_list_cancel_complete(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, reminders_database_path=tmp_path / "reminders.db")
    service = ReminderService(settings, store=ReminderStore(settings.reminders_database_path))

    create_result = service.create_reminder("stretch", "2026-06-12 18:30")
    list_result = service.list_reminders()
    complete_result = service.complete_reminder(create_result.reminder.id)
    cancel_result = service.cancel_reminder(create_result.reminder.id)

    assert create_result.success is True
    assert list_result.success is True
    assert len(list_result.reminders) == 1
    assert complete_result.success is True
    assert cancel_result.success is True


def test_reminder_disabled_fallback_uses_local_response() -> None:
    from assistant.core import AssistantCore

    assistant = AssistantCore(
        settings=AppSettings(_env_file=None, reminders_enabled=False, openai_enabled=False),
        openai_service=FakeOpenAIService(),
        weather_service=FakeWeatherService(),
    )

    response = assistant.handle_command("list reminders")

    assert response.source == "local"
    assert response.text == "Reminders are disabled."
