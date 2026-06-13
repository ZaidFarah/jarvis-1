from __future__ import annotations

from pathlib import Path

import pytest

from agent.router import AgentRouter
from agent.runtime import AgentRunResult, AgentRuntime
from assistant.core import AssistantCore, AssistantResponse
from config.settings import AppSettings
from security.confirmation import ConfirmationResult
from tools.file_access import FileAccess
from voice.voice_loop import VoiceLoopRunner


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


class FakeAgentRuntime:
    def __init__(self, response_text: str = "Agent handled.") -> None:
        self.calls: list[str] = []
        self.response_text = response_text

    def run(self, user_input: str) -> AgentRunResult:
        self.calls.append(user_input)
        response = AssistantResponse(text=self.response_text, accepted=True, source="agent")
        return AgentRunResult(
            user_input=user_input,
            selected_tool="chat",
            tool_result=self.response_text,
            final_response=self.response_text,
            conversation_history="",
            reason="Agent runtime stub.",
            response=response,
        )


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


def test_agent_disabled_keeps_old_assistant_core_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(AssistantCore, "_create_agent_runtime", lambda self: pytest.fail("agent runtime should not be created"))
    settings = AppSettings(_env_file=None, openai_enabled=False, agent_enabled=False)
    assistant = AssistantCore(settings=settings, openai_service=None)

    response = assistant.handle_command("status report")

    assert assistant.agent_runtime is None
    assert response.source == "fallback"
    assert "status report" in response.text


def test_agent_enabled_routes_through_agent_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_runtime = FakeAgentRuntime(response_text="Agent route handled.")
    monkeypatch.setattr(AssistantCore, "_create_agent_runtime", lambda self: fake_runtime)

    assistant = AssistantCore(settings=AppSettings(_env_file=None, agent_enabled=True, openai_enabled=False), openai_service=None)

    response = assistant.handle_command("what is the weather")

    assert fake_runtime.calls == ["what is the weather"]
    assert response.source == "agent"
    assert response.text == "Agent route handled."


def test_voice_loop_respects_agent_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_runtime = FakeAgentRuntime(response_text="Agent route handled in voice loop.")
    monkeypatch.setattr(AssistantCore, "_create_agent_runtime", lambda self: fake_runtime)
    settings = AppSettings(_env_file=None, agent_enabled=True)
    settings.voice_loop_speak_status = False
    assistant = AssistantCore(settings=settings, openai_service=None)

    class DummyTtsProvider:
        name = "fake_tts"
        available = True

        def speak(self, text: str) -> None:
            del text

    class VoiceProvider:
        name = "fake_stt"
        available = True

        def __init__(self) -> None:
            self.calls = 0

        def transcribe(self, samples, sample_rate: int):
            del samples, sample_rate
            self.calls += 1
            if self.calls == 1:
                return type("Transcript", (), {"text": "hey jarvis"})()
            return type("Transcript", (), {"text": "status report"})()

    report = VoiceLoopRunner(
        settings=settings,
        assistant=assistant,
        provider=VoiceProvider(),
        tts_provider=DummyTtsProvider(),
        recorder=lambda duration: [0.1, -0.1, 0.0],
        sleeper=lambda duration: None,
        beeper=lambda: None,
    ).run_once()

    assert fake_runtime.calls == ["status report"]
    assert report.assistant_response is not None
    assert report.assistant_response.text == "Agent route handled in voice loop."


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
