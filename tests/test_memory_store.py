from __future__ import annotations

from pathlib import Path

import pytest

from memory.store import SensitiveMemoryError, SQLiteMemoryStore


def test_memory_store_create_list_forget_and_reset(tmp_path: Path) -> None:
    store = SQLiteMemoryStore(tmp_path / "memory.db")

    entry = store.remember("the office code is blue", source="test")
    assert entry.text == "the office code is blue"

    memories = store.list_memories()
    assert len(memories) == 1
    assert memories[0].text == "the office code is blue"

    assert store.forget("the office code is blue") == 1
    assert store.list_memories() == []

    store.remember("the office code is blue")
    store.remember("the launch time is 7 am")
    assert store.reset() == 2
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
