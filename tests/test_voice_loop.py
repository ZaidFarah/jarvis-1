from __future__ import annotations

from assistant.core import AssistantCore, AssistantResponse
from config.settings import AppSettings
from voice.interfaces import TranscriptionResult
from voice.voice_command_test import COMMAND_PROMPT, LISTENING_FOR_COMMAND_PROMPT, NO_COMMAND_DETECTED_MESSAGE
from voice.voice_loop import RETURNING_TO_SLEEP_MESSAGE, STOP_COMMAND_DETECTED_MESSAGE, VoiceLoopRunner, is_stop_command


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
        return AssistantResponse(text=f"handled {command}", accepted=True, source="test")


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


def test_voice_loop_one_cycle_state_transitions_calls_assistant_and_tts() -> None:
    settings = AppSettings(_env_file=None)
    settings.voice_loop_speak_status = False
    assistant = SpyAssistant()
    tts_provider = FakeTtsProvider()
    provider = FakeProvider(["hey jarvis", "status report"])

    report = VoiceLoopRunner(
        settings=settings,
        assistant=assistant,
        provider=provider,
        tts_provider=tts_provider,
        recorder=fake_recorder,
        sleeper=no_sleep,
        beeper=no_beep,
    ).run_once()

    assert report.wake_detected is True
    assert report.cleaned_command == "status report"
    assert assistant.commands == ["status report"]
    assert tts_provider.spoken == ["handled status report"]
    assert report.statuses == [
        "Sleeping",
        "Listening for wake phrase",
        "Wake detected",
        COMMAND_PROMPT,
        LISTENING_FOR_COMMAND_PROMPT,
        "Thinking",
        "Speaking",
        RETURNING_TO_SLEEP_MESSAGE,
    ]


def test_voice_loop_stop_command_detection() -> None:
    assert is_stop_command("stop listening") is True
    assert is_stop_command("Jarvis Sleep") is True
    assert is_stop_command("shutdown jarvis") is True
    assert is_stop_command("that is all") is True
    assert is_stop_command("thank you jarvis") is True
    assert is_stop_command("status report") is False


def test_voice_loop_stop_command_does_not_call_assistant() -> None:
    settings = AppSettings(_env_file=None)
    settings.voice_loop_speak_status = False
    assistant = SpyAssistant()
    provider = FakeProvider(["hey jarvis", "exit jarvis"])

    report = VoiceLoopRunner(
        settings=settings,
        assistant=assistant,
        provider=provider,
        recorder=fake_recorder,
        sleeper=no_sleep,
        beeper=no_beep,
    ).run_once()

    assert report.stop_requested is True
    assert report.cleaned_command == "exit jarvis"
    assert assistant.commands == []
    assert STOP_COMMAND_DETECTED_MESSAGE in report.statuses
    assert report.statuses[-1] == STOP_COMMAND_DETECTED_MESSAGE


def test_voice_loop_empty_command_returns_to_sleep_without_assistant_call() -> None:
    settings = AppSettings(_env_file=None)
    settings.voice_loop_speak_status = False
    assistant = SpyAssistant()
    provider = FakeProvider(["hey jarvis", ". . . . ."])

    report = VoiceLoopRunner(
        settings=settings,
        assistant=assistant,
        provider=provider,
        recorder=fake_recorder,
        sleeper=no_sleep,
        beeper=no_beep,
    ).run_once()

    assert report.stop_requested is False
    assert report.cleaned_command == ""
    assert assistant.commands == []
    assert NO_COMMAND_DETECTED_MESSAGE in report.statuses
    assert RETURNING_TO_SLEEP_MESSAGE in report.statuses
    assert report.statuses[-1] == RETURNING_TO_SLEEP_MESSAGE


def test_voice_loop_cooldown_exists_after_speaking() -> None:
    settings = AppSettings(_env_file=None)
    settings.voice_loop_wake_cooldown_seconds = 1.5
    settings.voice_loop_speak_status = True
    assistant = SpyAssistant()
    tts_provider = FakeTtsProvider()
    provider = FakeProvider(["hey jarvis", "status report"])
    sleep_calls: list[float] = []

    def recording_sleep(duration: float) -> None:
        sleep_calls.append(duration)

    report = VoiceLoopRunner(
        settings=settings,
        assistant=assistant,
        provider=provider,
        tts_provider=tts_provider,
        recorder=fake_recorder,
        sleeper=recording_sleep,
        beeper=no_beep,
    ).run_once()

    assert report.cleaned_command == "status report"
    assert 1.5 in sleep_calls
    assert len(tts_provider.spoken) >= 2


def test_voice_loop_summary_counters_track_wakes_commands_empty_and_errors() -> None:
    settings = AppSettings(_env_file=None)
    settings.voice_loop_speak_status = False
    assistant = SpyAssistant()
    provider = FakeProvider(["hey jarvis", "status report", "hey jarvis", "sleep jarvis"])

    runner = VoiceLoopRunner(
        settings=settings,
        assistant=assistant,
        provider=provider,
        recorder=fake_recorder,
        sleeper=no_sleep,
        beeper=no_beep,
    )

    reports = runner.run(max_cycles=2)

    assert len(reports) == 2
    assert runner.summary.wake_attempts == 2
    assert runner.summary.successful_wakes == 2
    assert runner.summary.commands_handled == 2
    assert runner.summary.empty_commands == 0
    assert runner.summary.errors == 0


def test_voice_loop_stops_after_max_empty_commands() -> None:
    settings = AppSettings(_env_file=None)
    settings.voice_loop_speak_status = False
    settings.voice_loop_max_empty_commands = 2
    assistant = SpyAssistant()
    provider = FakeProvider(["hey jarvis", ". . . . .", "hey jarvis", ". . . . ."])

    runner = VoiceLoopRunner(
        settings=settings,
        assistant=assistant,
        provider=provider,
        recorder=fake_recorder,
        sleeper=no_sleep,
        beeper=no_beep,
    )

    reports = runner.run(max_cycles=5)

    assert len(reports) == 2
    assert reports[-1].stop_requested is True
    assert runner.summary.empty_commands == 2
    assert assistant.commands == []


def test_voice_loop_run_stops_after_stop_command() -> None:
    settings = AppSettings(_env_file=None)
    settings.voice_loop_speak_status = False
    provider = FakeProvider(["hey jarvis", "sleep jarvis"])

    reports = VoiceLoopRunner(
        settings=settings,
        assistant=SpyAssistant(),
        provider=provider,
        recorder=fake_recorder,
        sleeper=no_sleep,
        beeper=no_beep,
    ).run(max_cycles=3)

    assert len(reports) == 1
    assert reports[0].stop_requested is True
