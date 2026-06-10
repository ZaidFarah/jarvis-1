from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AssistantResponse:
    text: str
    accepted: bool = True


class AssistantCore:
    """Phase 1 assistant stub.

    Real AI routing, tools, memory, and voice will be added only in later phases.
    """

    placeholder = "Jarvis foundation is running. Full AI agent will be added in Phase 3."

    def handle_command(self, command: str) -> AssistantResponse:
        cleaned = command.strip()
        if not cleaned:
            return AssistantResponse(text="Please enter a command first.", accepted=False)

        return AssistantResponse(text=f"{self.placeholder} You said: {cleaned}")
