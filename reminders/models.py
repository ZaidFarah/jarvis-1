from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReminderEntry:
    id: int
    title: str
    remind_at: str
    status: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ReminderCheckResult:
    success: bool
    text: str
    due_reminders: list[ReminderEntry]
    safe_error: str | None = None
