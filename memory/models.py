from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryEntry:
    id: int
    key: str
    category: str
    value: str
    text: str
    source: str
    created_at: str
    updated_at: str
