from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryEntry:
    id: int
    text: str
    created_at: str
    updated_at: str
    source: str
