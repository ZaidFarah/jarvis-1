from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from memory.store import SensitiveMemoryError, SQLiteMemoryStore


def test_memory_store_create_list_forget_and_reset(tmp_path: Path) -> None:
    store = SQLiteMemoryStore(tmp_path / "memory.db")

    entry = store.remember("the office code is blue", source="test")
    assert entry.text == "the office code is blue"
    assert entry.key == "fact_the_office_code_is_blue"
    assert entry.category == "fact"
    assert entry.value == "the office code is blue"
    assert entry.source == "test"

    memories = store.list_memories()
    assert len(memories) == 1
    assert memories[0].text == "the office code is blue"

    assert store.forget("the office code is blue") == 1
    assert store.list_memories() == []

    store.remember("the office code is blue")
    store.remember("the launch time is 7 am")
    assert store.reset() == 2
    assert store.list_memories() == []


def test_memory_store_upserts_structured_memory_and_searches_relevant_entries(
    tmp_path: Path,
) -> None:
    store = SQLiteMemoryStore(tmp_path / "memory.db")

    first = store.remember(
        "my name is Zaid",
        key="name",
        category="identity",
        value="Zaid",
        source="test",
    )
    updated = store.remember(
        "my name is Zaid Khan",
        key="name",
        category="identity",
        value="Zaid Khan",
        source="test_update",
    )
    store.remember(
        "I prefer dark red UI",
        key="preference_dark_red_ui",
        category="preference",
        value="dark red UI",
        source="test",
    )

    assert updated.id == first.id
    assert updated.value == "Zaid Khan"
    assert updated.source == "test_update"
    assert store.find_by_key("name") == updated
    matches = store.search("dark red UI")
    assert [entry.value for entry in matches] == ["dark red UI"]
    assert store.relevant_memories("suggest a UI style")[0].category == "preference"


def test_memory_store_migrates_existing_text_only_database(tmp_path: Path) -> None:
    database_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        CREATE TABLE memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            source TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        INSERT INTO memories (text, created_at, updated_at, source)
        VALUES ('the office code is blue', '2026-01-01', '2026-01-01', 'legacy')
        """
    )
    connection.commit()
    connection.close()

    store = SQLiteMemoryStore(database_path)
    memories = store.list_memories()

    assert len(memories) == 1
    assert memories[0].category == "fact"
    assert memories[0].value == "the office code is blue"
    assert memories[0].source == "legacy"
    updated = store.remember("the office code is blue")
    assert updated.id == memories[0].id
    assert store.find_by_key("fact_the_office_code_is_blue") == updated


def test_memory_store_removes_existing_malformed_name_memory(tmp_path: Path) -> None:
    database_path = tmp_path / "malformed.db"
    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        CREATE TABLE memories (
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
    connection.execute(
        """
        INSERT INTO memories
            (memory_key, category, value, text, source, created_at, updated_at)
        VALUES
            ('fact_my_name_is', 'fact', 'my name is', 'my name is',
             'explicit_command', '2026-01-01', '2026-01-01')
        """
    )
    connection.commit()
    connection.close()

    store = SQLiteMemoryStore(database_path)

    assert store.list_memories() == []


@pytest.mark.parametrize(
    "text",
    [
        "remember that my password is hunter2",
        "remember that my api key is sk-secret",
        "remember that card 4111 1111 1111 1111",
    ],
)
def test_memory_store_rejects_sensitive_data(tmp_path: Path, text: str) -> None:
    store = SQLiteMemoryStore(tmp_path / "memory.db")

    with pytest.raises(SensitiveMemoryError):
        store.remember(text)
