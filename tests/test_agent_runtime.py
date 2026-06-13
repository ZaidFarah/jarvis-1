from __future__ import annotations

from pathlib import Path

import pytest

from agent.router import AgentRouter
from agent.runtime import AgentRuntime
from assistant.core import AssistantCore, AssistantResponse
from config.settings import AppSettings
from security.confirmation import ConfirmationResult
from tools.file_access import FileAccess


class StubAssistant:
    def __init__(self) -> None:
        self.commands: list[str] = []

        class _History:
            @staticmethod
            def format_recent_history() -> str:
                return ""

        self.conversation_history = _History()

    def handle_command(self, command: str) -> AssistantResponse:
        self.commands.append(command)
        normalized = command.lower().strip()
        if "weather" in normalized:
            return AssistantResponse(text="Weather route handled.", accepted=True, source="weather")
        if "reminder" in normalized:
            return AssistantResponse(text="Reminder route handled.", accepted=True, source="reminders")
        if "google" in normalized:
            return AssistantResponse(text="Website route handled.", accepted=True, source="website")
        return AssistantResponse(text="Chat fallback handled.", accepted=True, source="openai")


def _approve(action_name: str, risk_level: str, description: str, log_file: Path) -> ConfirmationResult:
    del action_name, risk_level, description
    return ConfirmationResult(approved=True, denied=False, timed_out=False, reason="Approved.", log_file=log_file)


def _deny(action_name: str, risk_level: str, description: str, log_file: Path) -> ConfirmationResult:
    del action_name, risk_level, description
    return ConfirmationResult(approved=False, denied=True, timed_out=False, reason="Denied.", log_file=log_file)


def test_agent_routes_weather() -> None:
    settings = AppSettings(_env_file=None)
    runtime = AgentRuntime(settings=settings, assistant=StubAssistant())

    result = runtime.run("what is the weather")

    assert result.selected_tool == "weather"
    assert "Weather route handled" in result.final_response


def test_agent_routes_reminders() -> None:
    settings = AppSettings(_env_file=None)
    runtime = AgentRuntime(settings=settings, assistant=StubAssistant())

    result = runtime.run("list reminders")

    assert result.selected_tool == "reminders"
    assert "Reminder route handled" in result.final_response


def test_agent_routes_website() -> None:
    settings = AppSettings(_env_file=None)
    runtime = AgentRuntime(settings=settings, assistant=StubAssistant())

    result = runtime.run("open google")

    assert result.selected_tool == "website_launcher"
    assert "Website route handled" in result.final_response


def test_agent_fallback_chat_route() -> None:
    settings = AppSettings(_env_file=None)
    runtime = AgentRuntime(settings=settings, assistant=StubAssistant())

    result = runtime.run("tell me a joke")

    assert result.selected_tool == "chat"
    assert "Chat fallback handled" in result.final_response


def test_agent_permission_and_confirmation_enforced_for_file_read(tmp_path: Path) -> None:
    documents_dir = tmp_path / "documents"
    documents_dir.mkdir()
    sample_file = documents_dir / "note.txt"
    sample_file.write_text("hello jarvis", encoding="utf-8")

    settings = AppSettings(
        _env_file=None,
        file_access_enabled=True,
        file_read_enabled=True,
        file_access_allowed_folders=f"documents={documents_dir}",
    )
    confirmations: list[str] = []

    def deny(action_name: str, risk_level: str, description: str) -> ConfirmationResult:
        confirmations.append(action_name)
        return _deny(action_name, risk_level, description, log_file=tmp_path / "confirmations.log")

    assistant = AssistantCore(settings=settings, confirmation_handler=deny)
    runtime = AgentRuntime(settings=settings, assistant=assistant)

    result = runtime.run("read file note.txt in documents")

    assert result.selected_tool == "file_access"
    assert result.response.accepted is False
    assert result.final_response == "Denied."
    assert confirmations


def test_agent_confirmation_approved_file_read(tmp_path: Path) -> None:
    documents_dir = tmp_path / "documents"
    documents_dir.mkdir()
    sample_file = documents_dir / "note.txt"
    sample_file.write_text("hello jarvis", encoding="utf-8")

    settings = AppSettings(
        _env_file=None,
        file_access_enabled=True,
        file_read_enabled=True,
        file_access_allowed_folders=f"documents={documents_dir}",
    )

    def approve(action_name: str, risk_level: str, description: str) -> ConfirmationResult:
        return _approve(action_name, risk_level, description, log_file=tmp_path / "confirmations.log")

    assistant = AssistantCore(settings=settings, confirmation_handler=approve)
    runtime = AgentRuntime(settings=settings, assistant=assistant)

    result = runtime.run("read file note.txt in documents")

    assert result.selected_tool == "file_access"
    assert result.response.accepted is True
    assert "hello jarvis" in result.final_response.lower()

