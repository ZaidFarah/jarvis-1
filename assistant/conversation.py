from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConversationTurn:
    role: str
    content: str


class ConversationHistory:
    """In-memory short-term conversation history for the current session."""

    def __init__(self, enabled: bool = True, max_messages: int = 10) -> None:
        self.enabled = enabled
        self.max_messages = max(0, max_messages)
        self._messages: list[ConversationTurn] = []

    @property
    def messages(self) -> list[ConversationTurn]:
        return list(self._messages)

    def add_user(self, content: str) -> None:
        self._append("user", content)

    def add_assistant(self, content: str) -> None:
        self._append("assistant", content)

    def reset(self) -> None:
        self._messages.clear()

    def format_recent_history(self) -> str:
        if not self.enabled or not self._messages:
            return ""

        lines = ["Recent conversation context:"]
        lines.extend(f"{turn.role.title()}: {turn.content}" for turn in self._messages)
        return "\n".join(lines)

    def _append(self, role: str, content: str) -> None:
        cleaned = content.strip()
        if not self.enabled or not cleaned:
            return

        self._messages.append(ConversationTurn(role=role, content=cleaned))
        if self.max_messages == 0:
            self._messages.clear()
            return

        overflow = len(self._messages) - self.max_messages
        if overflow > 0:
            del self._messages[:overflow]
