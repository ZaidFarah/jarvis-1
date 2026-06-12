from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Iterator

from memory.models import MemoryEntry


class SensitiveMemoryError(ValueError):
    pass


@dataclass(frozen=True)
class MemoryStoreResult:
    success: bool
    message: str


class SQLiteMemoryStore:
    """SQLite-backed short-term persistent memory store."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path.expanduser().resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def remember(self, text: str, source: str = "explicit") -> MemoryEntry:
        cleaned = self._clean_text(text)
        self._reject_sensitive_text(cleaned)
        now = self._now()
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT id, created_at FROM memories WHERE LOWER(text) = LOWER(?) LIMIT 1",
                (cleaned,),
            ).fetchone()
            if existing is None:
                cursor = connection.execute(
                    """
                    INSERT INTO memories (text, created_at, updated_at, source)
                    VALUES (?, ?, ?, ?)
                    """,
                    (cleaned, now, now, source),
                )
                memory_id = int(cursor.lastrowid)
                created_at = now
            else:
                memory_id = int(existing["id"])
                created_at = str(existing["created_at"])
                connection.execute(
                    "UPDATE memories SET updated_at = ?, source = ?, text = ? WHERE id = ?",
                    (now, source, cleaned, memory_id),
                )
        return MemoryEntry(id=memory_id, text=cleaned, created_at=created_at, updated_at=now, source=source)

    def list_memories(self) -> list[MemoryEntry]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, text, created_at, updated_at, source FROM memories ORDER BY id ASC"
            ).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def forget(self, text: str) -> int:
        cleaned = self._clean_text(text)
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM memories WHERE LOWER(text) = LOWER(?) OR LOWER(text) LIKE LOWER(?)",
                (cleaned, f"%{cleaned}%"),
            )
            return int(cursor.rowcount or 0)

    def reset(self) -> int:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM memories")
            return int(cursor.rowcount or 0)

    def exists(self, text: str) -> bool:
        cleaned = self._clean_text(text)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM memories WHERE LOWER(text) = LOWER(?) OR LOWER(text) LIKE LOWER(?) LIMIT 1",
                (cleaned, f"%{cleaned}%"),
            ).fetchone()
        return row is not None

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    source TEXT NOT NULL
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at)")

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
    def _row_to_entry(row: sqlite3.Row) -> MemoryEntry:
        return MemoryEntry(
            id=int(row["id"]),
            text=str(row["text"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            source=str(row["source"]),
        )

    @staticmethod
    def _clean_text(text: str) -> str:
        cleaned = " ".join(text.strip().split())
        if not cleaned:
            raise ValueError("Memory text cannot be empty.")
        return cleaned

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _reject_sensitive_text(text: str) -> None:
        lowered = text.lower()
        sensitive_markers = [
            "password",
            "passcode",
            "api key",
            "apikey",
            "openai_api_key",
            "secret key",
            "private key",
            "access token",
            "refresh token",
            "oauth token",
        ]
        if any(marker in lowered for marker in sensitive_markers):
            raise SensitiveMemoryError("Sensitive secrets cannot be stored in memory.")

        if re.search(r"\bsk-[A-Za-z0-9_\-]{10,}\b", text):
            raise SensitiveMemoryError("Sensitive secrets cannot be stored in memory.")

        if _looks_like_payment_card(text):
            raise SensitiveMemoryError("Payment card details cannot be stored in memory.")


def _looks_like_payment_card(text: str) -> bool:
    digits = re.sub(r"\D", "", text)
    if len(digits) < 13 or len(digits) > 19:
        return False
    if not digits.isdigit():
        return False
    return _luhn_check(digits)


def _luhn_check(digits: str) -> bool:
    total = 0
    reverse_digits = digits[::-1]
    for index, character in enumerate(reverse_digits):
        value = int(character)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0
