from __future__ import annotations

from pathlib import Path
from datetime import datetime

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


def test_reminder_service_detects_due_reminders_and_marks_notified(tmp_path: Path) -> None:
    fixed_now = lambda: datetime(2026, 6, 12, 18, 30)
    settings = AppSettings(_env_file=None, reminders_database_path=tmp_path / "reminders.db")
    service = ReminderService(settings, store=ReminderStore(settings.reminders_database_path), now_provider=fixed_now)

    store = service.store
    due_entry = store.create("stretch", "2026-06-12 18:00")
    future_entry = store.create("drink water", "2026-06-12 19:00")
    store.cancel(future_entry.id)

    result = service.check_due_reminders()
    second_result = service.check_due_reminders()

    assert result.success is True
    assert [entry.id for entry in result.due_reminders] == [due_entry.id]
    assert "Due reminders:" in result.text
    assert store.list_reminders()[0].status == "notified"
    assert second_result.due_reminders == []
    assert "No reminders are due right now." in second_result.text


def test_reminder_service_ignores_future_reminders(tmp_path: Path) -> None:
    fixed_now = lambda: datetime(2026, 6, 12, 18, 30)
    settings = AppSettings(_env_file=None, reminders_database_path=tmp_path / "reminders.db")
    service = ReminderService(settings, store=ReminderStore(settings.reminders_database_path), now_provider=fixed_now)

    store = service.store
    store.create("stretch", "2026-06-12 19:00")

    result = service.check_due_reminders()

    assert result.due_reminders == []
    assert "No reminders are due right now." in result.text


def test_reminder_service_ignores_cancelled_and_completed_reminders(tmp_path: Path) -> None:
    fixed_now = lambda: datetime(2026, 6, 12, 18, 30)
    settings = AppSettings(_env_file=None, reminders_database_path=tmp_path / "reminders.db")
    service = ReminderService(settings, store=ReminderStore(settings.reminders_database_path), now_provider=fixed_now)

    store = service.store
    cancelled_entry = store.create("cancelled", "2026-06-12 18:00")
    completed_entry = store.create("completed", "2026-06-12 18:00")
    store.cancel(cancelled_entry.id)
    store.complete(completed_entry.id)

    result = service.check_due_reminders()

    assert result.due_reminders == []
    assert "No reminders are due right now." in result.text


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


def test_reminder_cli_check_uses_isolated_database(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    reminders_db = tmp_path / "cli_reminders.db"
    monkeypatch.setenv("REMINDERS_DATABASE_PATH", str(reminders_db))
    monkeypatch.setenv("REMINDERS_ENABLED", "true")
    monkeypatch.setenv("REMINDERS_CHECK_ENABLED", "true")
    monkeypatch.setenv("REMINDERS_SPEAK_DUE", "false")

    service = ReminderService(AppSettings(_env_file=None, reminders_database_path=reminders_db), store=ReminderStore(reminders_db))
    service.store.create("stretch", "2026-06-11 18:00")

    from main import main

    exit_code = main(["--reminders-check"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Jarvis Reminders Check" in output
    assert "Due reminders:" in output


def test_reminder_cli_watch_disabled_fallback(capsys) -> None:
    from main import main

    exit_code = main(["--reminders-watch"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Reminder watcher is disabled." in output
