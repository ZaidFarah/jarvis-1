from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from config.settings import AppSettings
from reminders.models import ReminderEntry
from reminders.service import ReminderService
from reminders.store import ReminderStore
from services.notification_service import NotificationService, format_notification_error


class FakeSender:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def send(self, title: str, message: str) -> None:
        self.calls.append((title, message))


def test_notification_service_disabled_fallback(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, notifications_enabled=False, log_dir=tmp_path)
    service = NotificationService(settings)

    result = service.run_check()

    assert result.enabled is False
    assert result.request_attempted is False
    assert result.delivered is False
    assert result.is_successful is True
    assert "Notifications are disabled." in result.fallback_reason


def test_notification_service_provider_unavailable_fallback(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, notifications_enabled=True, log_dir=tmp_path)
    def missing_sender() -> FakeSender:
        raise ImportError("winotify missing")

    service = NotificationService(settings, sender_factory=missing_sender)

    result = service.run_check()

    assert result.enabled is True
    assert result.provider == "windows_toast"
    assert result.delivered is False
    assert result.request_attempted is False
    assert result.safe_error is not None
    assert result.is_successful is True


def test_notification_service_safe_notification_request(tmp_path: Path) -> None:
    sender = FakeSender()
    settings = AppSettings(
        _env_file=None,
        notifications_enabled=True,
        log_dir=tmp_path,
    )
    service = NotificationService(settings, sender_factory=lambda: sender)

    result = service.send_notification("Jarvis", "Hello from Jarvis")

    assert result.enabled is True
    assert result.request_attempted is True
    assert result.delivered is True
    assert sender.calls == [("Jarvis", "Hello from Jarvis")]


def test_notification_service_no_api_key_leakage(tmp_path: Path) -> None:
    def exploding_sender() -> FakeSender:
        class BadSender:
            def send(self, title: str, message: str) -> None:
                del title, message
                raise RuntimeError("Failed with OPENAI_API_KEY=sk-test-secret")

        return BadSender()  # type: ignore[return-value]

    settings = AppSettings(_env_file=None, notifications_enabled=True, log_dir=tmp_path)
    service = NotificationService(settings, sender_factory=exploding_sender)

    result = service.send_notification("Jarvis", "Hello from Jarvis")

    assert result.delivered is False
    assert result.safe_error is not None
    assert "sk-test-secret" not in result.safe_error
    assert "OPENAI_API_KEY" not in result.safe_error


def test_notification_service_check_formats_safe_error() -> None:
    error = format_notification_error(RuntimeError("missing OPENAI_API_KEY=sk-test-secret"))

    assert "sk-test-secret" not in error
    assert "OPENAI_API_KEY" not in error


def test_reminder_service_triggers_notification_when_enabled(tmp_path: Path) -> None:
    fixed_now = lambda: datetime(2026, 6, 12, 18, 30)
    settings = AppSettings(
        _env_file=None,
        reminders_enabled=True,
        reminders_check_enabled=True,
        reminders_toast_enabled=True,
        notifications_enabled=True,
        reminders_database_path=tmp_path / "reminders.db",
        log_dir=tmp_path,
    )
    store = ReminderStore(settings.reminders_database_path)

    class FakeNotificationService:
        def __init__(self) -> None:
            self.calls: list[list[ReminderEntry]] = []

        def send_reminder_notification(self, reminders: list[ReminderEntry]):
            self.calls.append(list(reminders))

            class Result:
                delivered = False
                fallback_reason = "Notification unavailable."

            return Result()

    notification_service = FakeNotificationService()
    service = ReminderService(
        settings,
        store=store,
        notification_service=notification_service,  # type: ignore[arg-type]
        now_provider=fixed_now,
    )
    due_entry = store.create("stretch", "2026-06-12 18:00")

    result = service.check_due_reminders()

    assert result.due_reminders == [due_entry]
    assert notification_service.calls == [[due_entry]]


def test_notification_service_disabled_fallback_no_crash(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, notifications_enabled=False, log_dir=tmp_path)
    service = NotificationService(settings)

    result = service.send_notification("Jarvis", "Hello from Jarvis")

    assert result.delivered is False
    assert result.is_successful is True
