from __future__ import annotations

from pathlib import Path

import main as main_module
from assistant.core import AssistantResponse
from config.settings import AppSettings
from voice.tts import TextToSpeechResult


class DummyAssistant:
    def __init__(self, text: str = "Handled locally.") -> None:
        self.commands: list[str] = []
        self.text = text

    def handle_command(self, command: str) -> AssistantResponse:
        self.commands.append(command)
        return AssistantResponse(text=self.text, accepted=True, source="local")


def _settings(tmp_path: Path, **overrides) -> AppSettings:
    return AppSettings(_env_file=None, log_dir=tmp_path / "logs", **overrides)


def test_chat_test_does_not_speak_by_default_when_tts_is_enabled(monkeypatch, capsys, tmp_path: Path) -> None:
    assistant = DummyAssistant()
    settings = _settings(tmp_path, tts_enabled=True)
    speak_calls: list[str] = []

    def forbidden_speak(*args, **kwargs):
        speak_calls.append("called")
        raise AssertionError("chat-test should not speak without --speak")

    monkeypatch.setattr(main_module, "load_settings", lambda: settings)
    monkeypatch.setattr(main_module, "configure_logging", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_module, "_build_cli_assistant", lambda settings: assistant)
    monkeypatch.setattr(main_module, "speak_text", forbidden_speak)

    exit_code = main_module.main(["--chat-test", "start coding session"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert assistant.commands == ["start coding session"]
    assert speak_calls == []
    assert "Text-to-speech:" not in output


def test_chat_test_with_speak_uses_tts(monkeypatch, capsys, tmp_path: Path) -> None:
    assistant = DummyAssistant(text="Spoken response.")
    settings = _settings(tmp_path, tts_enabled=False)
    speak_calls: list[tuple[str, bool]] = []

    def fake_speak(text: str, settings: AppSettings, *, speak_requested: bool = False, **kwargs) -> TextToSpeechResult:
        del settings, kwargs
        speak_calls.append((text, speak_requested))
        return TextToSpeechResult(
            provider_name="fake_tts",
            provider_available=True,
            requested=True,
            spoken=True,
            log_file=tmp_path / "logs" / "tts.log",
        )

    monkeypatch.setattr(main_module, "load_settings", lambda: settings)
    monkeypatch.setattr(main_module, "configure_logging", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_module, "_build_cli_assistant", lambda settings: assistant)
    monkeypatch.setattr(main_module, "speak_text", fake_speak)

    exit_code = main_module.main(["--chat-test", "status report", "--speak"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert assistant.commands == ["status report"]
    assert speak_calls == [("Spoken response.", True)]
    assert "Text-to-speech:" in output
    assert "spoken: yes" in output


def test_agent_chat_test_does_not_speak_by_default_when_tts_is_enabled(monkeypatch, capsys, tmp_path: Path) -> None:
    assistant = DummyAssistant(text="Agent chat response.")
    settings = _settings(tmp_path, agent_enabled=True, tts_enabled=True)
    speak_calls: list[str] = []

    def forbidden_speak(*args, **kwargs):
        speak_calls.append("called")
        raise AssertionError("agent-chat-test should not speak without --speak")

    monkeypatch.setattr(main_module, "load_settings", lambda: settings)
    monkeypatch.setattr(main_module, "configure_logging", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_module, "_build_cli_assistant", lambda settings: assistant)
    monkeypatch.setattr(main_module, "speak_text", forbidden_speak)

    exit_code = main_module.main(["--agent-chat-test", "review today's work"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert assistant.commands == ["review today's work"]
    assert speak_calls == []
    assert "Jarvis Agent Chat Test" in output
    assert "Text-to-speech:" not in output
