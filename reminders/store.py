from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Iterator

from reminders.models import ReminderEntry


class ReminderStore:
    """SQLite-backed reminder store."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path.expanduser().resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def create(self, title: str, remind_at: str, status: str = "pending") -> ReminderEntry:
        cleaned_title = self._clean_text(title)
        cleaned_remind_at = self._clean_text(remind_at)
        now = self._now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO reminders (title, remind_at, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (cleaned_title, cleaned_remind_at, status, now, now),
            )
            reminder_id = int(cursor.lastrowid)
        return ReminderEntry(
            id=reminder_id,
            title=cleaned_title,
            remind_at=cleaned_remind_at,
            status=status,
            created_at=now,
            updated_at=now,
        )

    def list_reminders(self) -> list[ReminderEntry]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, title, remind_at, status, created_at, updated_at
                FROM reminders
                ORDER BY remind_at ASC, id ASC
                """
            ).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def cancel(self, reminder_id: int) -> bool:
        return self._set_status(reminder_id, "cancelled")

    def complete(self, reminder_id: int) -> bool:
        return self._set_status(reminder_id, "completed")

    def exists(self, reminder_id: int) -> bool:
        with self._connect() as connection:
            row = connection.execute("SELECT 1 FROM reminders WHERE id = ? LIMIT 1", (int(reminder_id),)).fetchone()
        return row is not None

    def _set_status(self, reminder_id: int, status: str) -> bool:
        now = self._now()
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE reminders SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, int(reminder_id)),
            )
            return bool(cursor.rowcount)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    remind_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_reminders_status ON reminders(status)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_reminders_remind_at ON reminders(remind_at)")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> ReminderEntry:
        return ReminderEntry(
            id=int(row["id"]),
            title=str(row["title"]),
            remind_at=str(row["remind_at"]),
            status=str(row["status"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _clean_text(text: str) -> str:
        cleaned = " ".join(text.strip().split())
        if not cleaned:
            raise ValueError("Reminder text cannot be empty.")
        return cleaned

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

