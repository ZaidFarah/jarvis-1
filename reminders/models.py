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

