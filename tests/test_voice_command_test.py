from __future__ import annotations

from assistant.core import AssistantCore
from config.settings import AppSettings
from voice.interfaces import TranscriptionResult
from voice.voice_command_test import VoiceCommandTestRunner, format_voice_command_report


class FakeProvider:
    name = "fake_stt"
    available = True

    def __init__(self, transcripts: list[str]) -> None:
        self.transcripts = transcripts
        self.calls = 0

    def transcribe(self, samples, sample_rate: int) -> TranscriptionResult:
        del samples, sample_rate
        text = self.transcripts[self.calls]
        self.calls += 1
        return TranscriptionResult(text=text)


class SpyAssistant(AssistantCore):
    def __init__(self) -> None:
        super().__init__(settings=AppSettings(_env_file=None))
        self.commands: list[str] = []

    def handle_command(self, command: str):
        self.commands.append(command)
        return super().handle_command(command)


def fake_recorder(duration: float) -> list[float]:
    assert duration > 0
    return [0.1, -0.1, 0.0]


def test_voice_command_wake_detected_path_passes_command_to_assistant() -> None:
    settings = AppSettings(_env_file=None)
    assistant = SpyAssistant()
    provider = FakeProvider(["wake up jarvis", "Hey Jarvis, status report"])

    report = VoiceCommandTestRunner(
        settings=settings,
        assistant=assistant,
        provider=provider,
        recorder=fake_recorder,
    ).run()

    assert report.wake_detected is True
    assert report.raw_command_transcription == "Hey Jarvis, status report"
    assert report.cleaned_command == "status report"
    assert assistant.commands == ["status report"]
    assert report.assistant_response is not None
    assert "Jarvis foundation is running" in report.assistant_response.text
    assert report.assistant_response.source == "fallback"
    assert report.statuses == [
        "Listening for wake phrase",
        "Wake detected",
        "Listening for command",
        "Thinking",
        "Speaking",
        "Sleeping",
    ]


def test_voice_command_wake_not_detected_path_does_not_record_command() -> None:
    settings = AppSettings(_env_file=None)
    assistant = SpyAssistant()
    provider = FakeProvider(["not the phrase", "status report"])

    report = VoiceCommandTestRunner(
        settings=settings,
        assistant=assistant,
        provider=provider,
        recorder=fake_recorder,
    ).run()

    assert report.wake_detected is False
    assert report.raw_command_transcription == ""
    assert report.cleaned_command == ""
    assert assistant.commands == []
    assert provider.calls == 1
    assert report.statuses == ["Listening for wake phrase", "Sleeping"]


def test_voice_command_report_includes_safe_placeholder_response() -> None:
    settings = AppSettings(_env_file=None)
    provider = FakeProvider(["hey jarvis", "open settings"])

    report = VoiceCommandTestRunner(
        settings=settings,
        assistant=AssistantCore(settings=settings),
        provider=provider,
        recorder=fake_recorder,
    ).run()
    text = format_voice_command_report(report)

    assert "Jarvis Voice Command Test" in text
    assert "detected: yes" in text
    assert "raw command transcription: open settings" in text
    assert "cleaned command: open settings" in text
    assert "Jarvis foundation is running" in text
