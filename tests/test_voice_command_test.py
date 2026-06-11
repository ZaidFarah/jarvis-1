from __future__ import annotations

from assistant.core import AssistantCore
from config.settings import AppSettings
from voice.interfaces import TranscriptionResult
from voice.voice_command_test import (
    COMMAND_PROMPT,
    LISTENING_FOR_COMMAND_PROMPT,
    NO_COMMAND_DETECTED_MESSAGE,
    VoiceCommandTestRunner,
    format_voice_command_report,
)


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


class FakeTtsProvider:
    name = "fake_tts"
    available = True

    def __init__(self) -> None:
        self.spoken: list[str] = []

    def speak(self, text: str) -> None:
        self.spoken.append(text)


def fake_recorder(duration: float) -> list[float]:
    assert duration > 0
    return [0.1, -0.1, 0.0]


def no_sleep(duration: float) -> None:
    assert duration >= 0


def no_beep() -> None:
    return None


def test_voice_command_wake_detected_path_passes_command_to_assistant() -> None:
    settings = AppSettings(_env_file=None)
    assistant = SpyAssistant()
    provider = FakeProvider(["wake up jarvis", "Hey Jarvis, status report"])

    report = VoiceCommandTestRunner(
        settings=settings,
        assistant=assistant,
        provider=provider,
        recorder=fake_recorder,
        sleeper=no_sleep,
        beeper=no_beep,
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
        COMMAND_PROMPT,
        LISTENING_FOR_COMMAND_PROMPT,
        "Thinking",
        "Sleeping",
    ]
    assert report.tts_result is None


def test_voice_command_speak_flag_speaks_response() -> None:
    settings = AppSettings(_env_file=None)
    provider = FakeProvider(["hey jarvis", "say hello"])
    tts_provider = FakeTtsProvider()

    report = VoiceCommandTestRunner(
        settings=settings,
        assistant=AssistantCore(settings=settings),
        provider=provider,
        tts_provider=tts_provider,
        speak_requested=True,
        recorder=fake_recorder,
        sleeper=no_sleep,
        beeper=no_beep,
    ).run()

    assert report.tts_result is not None
    assert report.tts_result.spoken is True
    assert tts_provider.spoken
    assert report.statuses == [
        "Listening for wake phrase",
        "Wake detected",
        COMMAND_PROMPT,
        LISTENING_FOR_COMMAND_PROMPT,
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
        sleeper=no_sleep,
        beeper=no_beep,
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
        sleeper=no_sleep,
        beeper=no_beep,
    ).run()
    text = format_voice_command_report(report)

    assert "Jarvis Voice Command Test" in text
    assert "detected: yes" in text
    assert "raw command transcription: open settings" in text
    assert "cleaned command: open settings" in text
    assert "Jarvis foundation is running" in text


def test_voice_command_punctuation_only_transcription_is_empty() -> None:
    settings = AppSettings(_env_file=None)
    assistant = SpyAssistant()
    provider = FakeProvider(["hey jarvis", ". . . . ."])

    report = VoiceCommandTestRunner(
        settings=settings,
        assistant=assistant,
        provider=provider,
        recorder=fake_recorder,
        sleeper=no_sleep,
        beeper=no_beep,
    ).run()

    text = format_voice_command_report(report)

    assert report.raw_command_transcription == ". . . . ."
    assert report.cleaned_command == ""
    assert assistant.commands == []
    assert NO_COMMAND_DETECTED_MESSAGE in report.errors
    assert NO_COMMAND_DETECTED_MESSAGE in text


def test_voice_command_uses_separate_wake_and_command_durations() -> None:
    durations: list[float] = []

    def recorder(duration: float) -> list[float]:
        durations.append(duration)
        return [0.1, -0.1]

    settings = AppSettings(
        _env_file=None,
        wake_listen_seconds=2.0,
        voice_command_record_seconds=7.0,
    )
    provider = FakeProvider(["hey jarvis", "status report"])

    report = VoiceCommandTestRunner(
        settings=settings,
        assistant=AssistantCore(settings=settings),
        provider=provider,
        recorder=recorder,
        sleeper=no_sleep,
        beeper=no_beep,
    ).run()

    assert report.cleaned_command == "status report"
    assert durations == [2.0, 7.0]
