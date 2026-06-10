from __future__ import annotations

from assistant.core import AssistantCore


def test_assistant_core_returns_placeholder_response() -> None:
    assistant = AssistantCore()

    response = assistant.handle_command("status report")

    assert response.accepted is True
    assert "Jarvis foundation is running" in response.text
    assert "status report" in response.text


def test_assistant_core_rejects_empty_command() -> None:
    assistant = AssistantCore()

    response = assistant.handle_command("   ")

    assert response.accepted is False
    assert response.text == "Please enter a command first."
