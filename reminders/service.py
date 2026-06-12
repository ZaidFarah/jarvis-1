from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from config.settings import AppSettings
from reminders.models import ReminderEntry
from reminders.store import ReminderStore


_REMINDERS_LOG_SINK_ID: int | None = None
_REMINDERS_LOG_FILE: Path | None = None


@dataclass(frozen=True)
class ReminderQueryResult:
    success: bool
    text: str
    reminder: ReminderEntry | None = None
    reminders: list[ReminderEntry] = field(default_factory=list)
    safe_error: str | None = None


class ReminderTimeError(ValueError):
    pass


class ReminderService:
    """Local reminder service backed by SQLite only."""

    def __init__(self, settings: AppSettings, store: ReminderStore | None = None) -> None:
        self.settings = settings
        self.store = store or ReminderStore(settings.reminders_database_path)
        self.log_file = self.settings.log_dir / "reminders.log"
        self.reminders_logger = logger.bind(reminders=True)
        self._ensure_reminders_log_sink()

    def create_reminder(self, title: str, remind_at_text: str | None = None) -> ReminderQueryResult:
        cleaned_title = self._clean_text(title)
        if not remind_at_text:
            return ReminderQueryResult(
                success=False,
                text="Please provide a reminder time in format YYYY-MM-DD HH:MM.",
                safe_error="Missing reminder time.",
            )

        try:
            remind_at = self.parse_reminder_time(remind_at_text)
        except ReminderTimeError as exc:
            message = str(exc)
            return ReminderQueryResult(success=False, text=message, safe_error=message)

        reminder = self.store.create(cleaned_title, remind_at.isoformat(sep=" ", timespec="minutes"))
        self.reminders_logger.info("Created reminder id={} title={}", reminder.id, reminder.title)
        return ReminderQueryResult(
            success=True,
            text=f"Reminder created: {reminder.title} at {reminder.remind_at} (id {reminder.id}).",
            reminder=reminder,
        )

    def list_reminders(self) -> ReminderQueryResult:
        reminders = self.store.list_reminders()
        if not reminders:
            return ReminderQueryResult(success=True, text="You have no reminders yet.", reminders=[])

        lines = ["Here are your reminders:"]
        lines.extend(
            f"{entry.id}. {entry.title} at {entry.remind_at} [{entry.status}]"
            for entry in reminders
        )
        return ReminderQueryResult(success=True, text="\n".join(lines), reminders=reminders)

    def cancel_reminder(self, reminder_id: int) -> ReminderQueryResult:
        if self.store.cancel(reminder_id):
            self.reminders_logger.info("Cancelled reminder id={}", reminder_id)
            return ReminderQueryResult(success=True, text=f"Reminder {reminder_id} cancelled.")
        return ReminderQueryResult(success=False, text=f"Reminder {reminder_id} was not found.", safe_error="Not found.")

    def complete_reminder(self, reminder_id: int) -> ReminderQueryResult:
        if self.store.complete(reminder_id):
            self.reminders_logger.info("Completed reminder id={}", reminder_id)
            return ReminderQueryResult(success=True, text=f"Reminder {reminder_id} completed.")
        return ReminderQueryResult(success=False, text=f"Reminder {reminder_id} was not found.", safe_error="Not found.")

    @staticmethod
    def parse_reminder_time(remind_at_text: str) -> datetime:
        cleaned = " ".join(remind_at_text.strip().split())
        if not cleaned:
            raise ReminderTimeError("Please provide a reminder time in format YYYY-MM-DD HH:MM.")

        formats = ["%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M"]
        for time_format in formats:
            try:
                return datetime.strptime(cleaned, time_format)
            except ValueError:
                continue
        raise ReminderTimeError("Please provide a reminder time in format YYYY-MM-DD HH:MM.")

    @staticmethod
    def parse_reminder_command(command: str) -> tuple[str, str | None]:
        cleaned = " ".join(command.strip().split())
        match = re.match(r"(?i)^remind me to\s+(.+)$", cleaned)
        if not match:
            raise ValueError("Not a reminder command.")

        remainder = match.group(1).strip()
        task, separator, remind_at = remainder.rpartition(" at ")
        if separator:
            task = task.strip()
            remind_at = remind_at.strip()
            return task, remind_at or None
        return remainder, None

    @staticmethod
    def _clean_text(text: str) -> str:
        cleaned = " ".join(text.strip().split())
        if not cleaned:
            raise ValueError("Reminder title cannot be empty.")
        return cleaned

    def _ensure_reminders_log_sink(self) -> None:
        global _REMINDERS_LOG_FILE, _REMINDERS_LOG_SINK_ID
        if _REMINDERS_LOG_SINK_ID is not None and _REMINDERS_LOG_FILE == self.log_file:
            return

        if _REMINDERS_LOG_SINK_ID is not None:
            try:
                logger.remove(_REMINDERS_LOG_SINK_ID)
            except ValueError:
                pass

        self.settings.log_dir.mkdir(parents=True, exist_ok=True)
        _REMINDERS_LOG_SINK_ID = logger.add(
            self.log_file,
            level="DEBUG",
            rotation="1 MB",
            retention="7 days",
            encoding="utf-8",
            backtrace=False,
            diagnose=False,
            filter=lambda record: bool(record["extra"].get("reminders")),
        )
        _REMINDERS_LOG_FILE = self.log_file
