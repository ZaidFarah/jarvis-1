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
    """SQLite-backed long-term memory store with in-place schema migration."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path.expanduser().resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def remember(
        self,
        text: str,
        source: str = "explicit",
        *,
        key: str | None = None,
        category: str = "fact",
        value: str | None = None,
    ) -> MemoryEntry:
        cleaned = self._clean_text(text)
        self._reject_sensitive_text(cleaned)
        cleaned_value = self._clean_text(value if value is not None else cleaned)
        cleaned_category = self._clean_identifier(category, fallback="fact")
        cleaned_key = self._clean_identifier(
            key or f"{cleaned_category}_{self._slug(cleaned)}",
            fallback=f"memory_{self._slug(cleaned)}",
        )
        now = self._now()
        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT id, created_at
                FROM memories
                WHERE LOWER(memory_key) = LOWER(?)
                   OR LOWER(text) = LOWER(?)
                LIMIT 1
                """,
                (cleaned_key, cleaned),
            ).fetchone()
            if existing is None:
                cursor = connection.execute(
                    """
                    INSERT INTO memories
                        (memory_key, category, value, text, source, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        cleaned_key,
                        cleaned_category,
                        cleaned_value,
                        cleaned,
                        source,
                        now,
                        now,
                    ),
                )
                memory_id = int(cursor.lastrowid)
                created_at = now
            else:
                memory_id = int(existing["id"])
                created_at = str(existing["created_at"])
                connection.execute(
                    """
                    UPDATE memories
                    SET memory_key = ?, category = ?, value = ?, text = ?,
                        source = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        cleaned_key,
                        cleaned_category,
                        cleaned_value,
                        cleaned,
                        source,
                        now,
                        memory_id,
                    ),
                )
        return MemoryEntry(
            id=memory_id,
            key=cleaned_key,
            category=cleaned_category,
            value=cleaned_value,
            text=cleaned,
            source=source,
            created_at=created_at,
            updated_at=now,
        )

    def list_memories(self) -> list[MemoryEntry]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, memory_key, category, value, text, source, created_at, updated_at
                FROM memories
                ORDER BY updated_at DESC, id DESC
                """
            ).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def find_by_key(self, key: str) -> MemoryEntry | None:
        cleaned_key = self._clean_identifier(key, fallback="")
        if not cleaned_key:
            return None
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, memory_key, category, value, text, source, created_at, updated_at
                FROM memories
                WHERE LOWER(memory_key) = LOWER(?)
                LIMIT 1
                """,
                (cleaned_key,),
            ).fetchone()
        return self._row_to_entry(row) if row is not None else None

    def search(self, query: str, *, limit: int = 5) -> list[MemoryEntry]:
        cleaned = self._clean_text(query)
        query_tokens = self._search_tokens(cleaned)
        memories = self.list_memories()
        ranked: list[tuple[int, MemoryEntry]] = []
        normalized_query = cleaned.casefold()
        for entry in memories:
            searchable = " ".join(
                (entry.key.replace("_", " "), entry.category, entry.value, entry.text)
            ).casefold()
            entry_tokens = self._search_tokens(searchable)
            score = len(query_tokens.intersection(entry_tokens)) * 3
            if normalized_query in searchable:
                score += 8
            if entry.value.casefold() in normalized_query:
                score += 4
            if score > 0:
                ranked.append((score, entry))
        ranked.sort(key=lambda item: (item[0], item[1].updated_at), reverse=True)
        return [entry for _score, entry in ranked[: max(1, limit)]]

    def relevant_memories(self, query: str, *, limit: int = 5) -> list[MemoryEntry]:
        matches = self.search(query, limit=limit)
        if matches:
            return matches
        normalized = query.casefold()
        if any(word in normalized.split() for word in {"i", "me", "my", "mine"}):
            profile = [
                entry
                for entry in self.list_memories()
                if entry.category in {"identity", "profile", "preference"}
            ]
            return profile[: max(1, limit)]
        return []

    def forget(self, text: str) -> int:
        cleaned = self._clean_text(text)
        cleaned_key = self._clean_identifier(cleaned, fallback="")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM memories
                WHERE LOWER(memory_key) = LOWER(?)
                   OR LOWER(text) = LOWER(?)
                   OR LOWER(text) LIKE LOWER(?)
                   OR LOWER(value) = LOWER(?)
                   OR LOWER(value) LIKE LOWER(?)
                """,
                (
                    cleaned_key,
                    cleaned,
                    f"%{cleaned}%",
                    cleaned,
                    f"%{cleaned}%",
                ),
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
                """
                SELECT 1
                FROM memories
                WHERE LOWER(text) = LOWER(?)
                   OR LOWER(text) LIKE LOWER(?)
                   OR LOWER(value) = LOWER(?)
                   OR LOWER(memory_key) = LOWER(?)
                LIMIT 1
                """,
                (
                    cleaned,
                    f"%{cleaned}%",
                    cleaned,
                    self._clean_identifier(cleaned, fallback=""),
                ),
            ).fetchone()
        return row is not None

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    memory_key TEXT,
                    category TEXT,
                    value TEXT,
                    text TEXT NOT NULL UNIQUE,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(memories)").fetchall()
            }
            for name, declaration in (
                ("memory_key", "TEXT"),
                ("category", "TEXT"),
                ("value", "TEXT"),
            ):
                if name not in columns:
                    connection.execute(f"ALTER TABLE memories ADD COLUMN {name} {declaration}")
            legacy_rows = connection.execute(
                """
                SELECT id, text
                FROM memories
                WHERE memory_key IS NULL OR category IS NULL OR value IS NULL
                """
            ).fetchall()
            for row in legacy_rows:
                text = str(row["text"])
                connection.execute(
                    """
                    UPDATE memories
                    SET memory_key = ?, category = ?, value = ?
                    WHERE id = ?
                    """,
                    (
                        f"fact_{self._slug(text)}_{int(row['id'])}",
                        "fact",
                        text,
                        int(row["id"]),
                    ),
                )
            connection.execute(
                """
                DELETE FROM memories
                WHERE TRIM(COALESCE(value, '')) = ''
                   OR LOWER(TRIM(COALESCE(text, ''))) IN (
                       'my name is',
                       'remember that my name is',
                       'remember my name is'
                   )
                   OR LOWER(TRIM(COALESCE(value, ''))) IN (
                       'my name is',
                       'remember that my name is',
                       'remember my name is'
                   )
                   OR LOWER(REPLACE(TRIM(COALESCE(memory_key, '')), '_', ' ')) IN (
                       'my name is',
                       'fact my name is',
                       'remember that my name is',
                       'remember my name is'
                   )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at)")
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_key ON memories(memory_key)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category)"
            )

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
            key=str(row["memory_key"]),
            category=str(row["category"]),
            value=str(row["value"]),
            text=str(row["text"]),
            source=str(row["source"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
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

    @classmethod
    def _clean_identifier(cls, value: str, *, fallback: str) -> str:
        cleaned = cls._slug(value)
        return cleaned or fallback

    @staticmethod
    def _slug(value: str) -> str:
        cleaned = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
        return cleaned[:120]

    @staticmethod
    def _search_tokens(value: str) -> set[str]:
        ignored = {
            "a",
            "about",
            "an",
            "and",
            "do",
            "i",
            "is",
            "me",
            "my",
            "of",
            "remember",
            "that",
            "the",
            "what",
            "you",
        }
        return {
            token
            for token in re.findall(r"[a-z0-9]+", value.casefold())
            if len(token) > 1 and token not in ignored
        }

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
