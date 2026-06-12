from __future__ import annotations

from datetime import datetime
from pathlib import Path
import time

from config.settings import AppSettings
from reminders.scheduler import ReminderWatcher
from reminders.service import ReminderService
from reminders.store import ReminderStore


def test_reminder_watcher_starts_and_stops(tmp_path: Path) -> None:
    fixed_now = lambda: datetime(2026, 6, 12, 18, 30)
    settings = AppSettings(
        _env_file=None,
        reminders_enabled=True,
        reminders_check_enabled=True,
        reminders_watch_enabled=True,
        reminders_database_path=tmp_path / "watch.db",
    )
    service = ReminderService(settings, store=ReminderStore(settings.reminders_database_path), now_provider=fixed_now)
    watcher = ReminderWatcher(settings, reminder_service=service, sleeper=lambda _: None)

    assert watcher.start() is True
    time.sleep(0.05)
    assert watcher.running is True

    watcher.stop()

    assert watcher.running is False


def test_reminder_watcher_detects_due_reminders(tmp_path: Path) -> None:
    fixed_now = lambda: datetime(2026, 6, 12, 18, 30)
    settings = AppSettings(
        _env_file=None,
        reminders_enabled=True,
        reminders_check_enabled=True,
        reminders_watch_enabled=True,
        reminders_database_path=tmp_path / "watch.db",
    )
    store = ReminderStore(settings.reminders_database_path)
    service = ReminderService(settings, store=store, now_provider=fixed_now)
    store.create("stretch", "2026-06-12 18:00")
    watcher = ReminderWatcher(settings, reminder_service=service)

    result = watcher.run_once()

    assert result.started is True
    assert result.summary.due_notifications == 1
    assert result.last_response is not None
    assert "Due reminders:" in result.last_response.text


def test_reminder_watcher_notifies_only_once(tmp_path: Path) -> None:
    fixed_now = lambda: datetime(2026, 6, 12, 18, 30)
    settings = AppSettings(
        _env_file=None,
        reminders_enabled=True,
        reminders_check_enabled=True,
        reminders_watch_enabled=True,
        reminders_database_path=tmp_path / "watch.db",
    )
    store = ReminderStore(settings.reminders_database_path)
    service = ReminderService(settings, store=store, now_provider=fixed_now)
    store.create("stretch", "2026-06-12 18:00")
    watcher = ReminderWatcher(settings, reminder_service=service)

    first = watcher.run_once()
    second = watcher.run_once()

    assert first.summary.due_notifications == 1
    assert second.summary.due_notifications == 1
    assert second.last_response is not None
    assert "No reminders are due right now." in second.last_response.text


def test_reminder_watcher_disabled_fallback(tmp_path: Path) -> None:
    settings = AppSettings(
        _env_file=None,
        reminders_enabled=True,
        reminders_check_enabled=True,
        reminders_watch_enabled=False,
        reminders_database_path=tmp_path / "watch.db",
    )
    watcher = ReminderWatcher(settings)

    assert watcher.start() is False
    assert watcher.running is False
