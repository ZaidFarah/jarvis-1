from __future__ import annotations

from assistant.core import AssistantCore, AssistantResponse
from config.settings import AppSettings
from services.openai_service import OpenAIChatResult
from voice.interfaces import TranscriptionResult
from voice.voice_command_test import COMMAND_PROMPT, LISTENING_FOR_COMMAND_PROMPT, NO_COMMAND_DETECTED_MESSAGE
from voice.voice_loop import (
    ACCEPTED_COMMAND_PREFIX,
    ACCEPTED_FOLLOW_UP_PREFIX,
    FOLLOW_UP_RECORD_SECONDS,
    LISTENING_FOR_FOLLOW_UP_PROMPT,
    REJECTED_COMMAND_PREFIX,
    REJECTED_FOLLOW_UP_PREFIX,
    RETURNING_TO_SLEEP_MESSAGE,
    RETRYING_COMMAND_CAPTURE_MESSAGE,
    RETRYING_FOLLOW_UP_CAPTURE_MESSAGE,
    STOP_COMMAND_DETECTED_MESSAGE,
    VoiceLoopRunner,
    is_stop_command,
)
from voice.wake import WakeDetectionResult
from voice.wake_provider import WakeProviderResolution


class FakeProvider:
    name = "fake_stt"
    available = True

    def __init__(self, transcripts: list[str]) -> None:
        self.transcripts = transcripts
        self.calls = 0

    def transcribe(self, samples, sample_rate: int) -> TranscriptionResult:
        del samples, sample_rate
        text = self.transcripts[self.calls] if self.calls < len(self.transcripts) else ""
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


class FakeWakeProvider:
    name = "openwakeword"
    available = True

    def __init__(self, detections: list[WakeDetectionResult]) -> None:
        self.detections = detections
        self.calls = 0

    def detect(self, samples, sample_rate: int) -> WakeDetectionResult:
        del samples, sample_rate
        result = self.detections[min(self.calls, len(self.detections) - 1)]
        self.calls += 1
        return result


class SpyOpenAIService:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.histories: list[str | None] = []

    def chat(self, user_text: str, system_prompt: str | None = None, conversation_history: str | None = None) -> OpenAIChatResult:
        del system_prompt
        self.messages.append(user_text)
        self.histories.append(conversation_history)
        return OpenAIChatResult(success=True, text=f"handled {user_text}", used_openai=True)


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
        LISTENING_FOR_FOLLOW_UP_PROMPT,
        RETURNING_TO_SLEEP_MESSAGE,
    ]


def test_voice_loop_openwakeword_path_does_not_transcribe_wake_clip_first() -> None:
    settings = AppSettings(
        _env_file=None,
        wake_provider="openwakeword",
        openwakeword_enabled=True,
        openwakeword_model="hey.jarvis",
    )
    settings.voice_loop_speak_status = False
    assistant = SpyAssistant()
    tts_provider = FakeTtsProvider()
    provider = FakeProvider(["status report"])
    wake_provider = FakeWakeProvider(
        [
            WakeDetectionResult(
                detected=True,
                transcript="",
                matched_phrase="hey.jarvis",
                score=0.91,
                threshold=0.5,
                match_type="openwakeword",
            )
        ]
    )
    wake_resolution = WakeProviderResolution(
        selected_provider="openwakeword",
        openwakeword_enabled=True,
        openwakeword_installed=True,
        model_configured=True,
        fallback_enabled=True,
        effective_provider="openwakeword",
        openwakeword_available=True,
    )
    durations: list[float] = []

    def recording_recorder(duration: float) -> list[float]:
        durations.append(duration)
        return [0.1, -0.1, 0.0]

    report = VoiceLoopRunner(
        settings=settings,
        assistant=assistant,
        provider=provider,
        tts_provider=tts_provider,
        wake_provider=wake_provider,
        wake_provider_resolution=wake_resolution,
        recorder=recording_recorder,
        sleeper=no_sleep,
        beeper=no_beep,
    ).run_once()

    assert report.wake_provider_name == "openwakeword"
    assert report.wake_provider_available is True
    assert report.wake_transcription == ""
    assert report.wake_detected is True
    assert wake_provider.calls == 1
    assert provider.calls == 2
    assert assistant.commands == ["status report"]
    assert report.cleaned_command == "status report"
    assert durations[0] == settings.openwakeword_listen_chunk_ms / 1000.0
    assert settings.voice_command_record_seconds in durations
    assert durations[-1] == FOLLOW_UP_RECORD_SECONDS


def test_voice_loop_stop_command_detection() -> None:
    assert is_stop_command("stop listening") is True
    assert is_stop_command("Jarvis Sleep") is True
    assert is_stop_command("shutdown jarvis") is True
    assert is_stop_command("that is all") is True
    assert is_stop_command("thank you jarvis") is True
    assert is_stop_command("status report") is False


def test_voice_loop_falls_back_to_whisper_when_openwakeword_is_unavailable() -> None:
    settings = AppSettings(
        _env_file=None,
        wake_provider="openwakeword",
        openwakeword_enabled=True,
        openwakeword_model="hey.jarvis",
    )
    settings.voice_loop_speak_status = False
    assistant = SpyAssistant()
    provider = FakeProvider(["hey jarvis", "status report"])

    report = VoiceLoopRunner(
        settings=settings,
        assistant=assistant,
        provider=provider,
        recorder=fake_recorder,
        sleeper=no_sleep,
        beeper=no_beep,
    ).run_once()

    assert report.wake_provider_name == "whisper_fuzzy"
    assert report.wake_provider_available is True
    assert report.wake_transcription == "hey jarvis"
    assert report.wake_detected is True
    assert provider.calls == 3


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
    provider = FakeProvider(["hey jarvis", ". . . . .", ". . . . ."])

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
    assert report.command_validation.accepted is False
    assert assistant.commands == []
    assert NO_COMMAND_DETECTED_MESSAGE in report.statuses
    assert RETURNING_TO_SLEEP_MESSAGE in report.statuses
    assert report.statuses[-1] == RETURNING_TO_SLEEP_MESSAGE


def test_voice_loop_retries_rejected_command_and_handles_valid_retry() -> None:
    settings = AppSettings(_env_file=None)
    settings.voice_loop_speak_status = False
    assistant = SpyAssistant()
    provider = FakeProvider(["hey jarvis", "you", "status report"])
    events: list[str] = []

    report = VoiceLoopRunner(
        settings=settings,
        assistant=assistant,
        provider=provider,
        recorder=fake_recorder,
        sleeper=no_sleep,
        beeper=no_beep,
        status_callback=events.append,
    ).run_once()

    assert report.cleaned_command == "status report"
    assert report.command_validation.accepted is True
    assert assistant.commands == ["status report"]
    assert provider.calls == 4
    assert NO_COMMAND_DETECTED_MESSAGE in report.statuses
    assert RETRYING_COMMAND_CAPTURE_MESSAGE in report.statuses
    assert LISTENING_FOR_FOLLOW_UP_PROMPT in report.statuses
    assert report.statuses.count(LISTENING_FOR_COMMAND_PROMPT) == 2
    assert "Last recognized command: you" in events
    assert f"{REJECTED_COMMAND_PREFIX} you (rejected phrase: you)" in events
    assert NO_COMMAND_DETECTED_MESSAGE in events
    assert RETRYING_COMMAND_CAPTURE_MESSAGE in events
    assert "Last recognized command: status report" in events
    assert f"{ACCEPTED_COMMAND_PREFIX} status report" in events
    assert "Last Jarvis response: handled status report" in events


def test_voice_loop_rejects_bad_command_before_openai_then_valid_retry_is_sent() -> None:
    settings = AppSettings(_env_file=None, openai_enabled=True, openai_api_key="sk-test")
    settings.voice_loop_speak_status = False
    openai_service = SpyOpenAIService()
    assistant = AssistantCore(settings=settings, openai_service=openai_service)
    provider = FakeProvider(["hey jarvis", "okay", "second question"])

    report = VoiceLoopRunner(
        settings=settings,
        assistant=assistant,
        provider=provider,
        tts_provider=FakeTtsProvider(),
        recorder=fake_recorder,
        sleeper=no_sleep,
        beeper=no_beep,
    ).run_once()

    assert report.cleaned_command == "second question"
    assert report.command_validation.accepted is True
    assert openai_service.messages == ["second question"]


def test_voice_loop_valid_follow_up_does_not_require_wake_phrase() -> None:
    settings = AppSettings(_env_file=None)
    settings.voice_loop_speak_status = False
    assistant = SpyAssistant()
    provider = FakeProvider(["hey jarvis", "status report", "weather report", ""])
    events: list[str] = []

    report = VoiceLoopRunner(
        settings=settings,
        assistant=assistant,
        provider=provider,
        recorder=fake_recorder,
        sleeper=no_sleep,
        beeper=no_beep,
        status_callback=events.append,
    ).run_once()

    assert report.cleaned_command == "weather report"
    assert assistant.commands == ["status report", "weather report"]
    assert report.statuses.count("Listening for wake phrase") == 1
    assert report.statuses.count(LISTENING_FOR_FOLLOW_UP_PROMPT) == 1
    assert f"{ACCEPTED_COMMAND_PREFIX} status report" in events
    assert f"{ACCEPTED_FOLLOW_UP_PREFIX} weather report" in events
    assert "Last Jarvis response: handled weather report" in events


def test_voice_loop_rejects_invalid_follow_up_before_openai_then_valid_retry_is_sent() -> None:
    settings = AppSettings(_env_file=None, openai_enabled=True, openai_api_key="sk-test")
    settings.voice_loop_speak_status = False
    openai_service = SpyOpenAIService()
    assistant = AssistantCore(settings=settings, openai_service=openai_service)
    provider = FakeProvider(["hey jarvis", "first question", "you", "second question", ""])
    events: list[str] = []

    report = VoiceLoopRunner(
        settings=settings,
        assistant=assistant,
        provider=provider,
        tts_provider=FakeTtsProvider(),
        recorder=fake_recorder,
        sleeper=no_sleep,
        beeper=no_beep,
        status_callback=events.append,
    ).run_once()

    assert report.cleaned_command == "second question"
    assert openai_service.messages == ["first question", "second question"]
    assert f"{REJECTED_FOLLOW_UP_PREFIX} you (rejected phrase: you)" in events
    assert RETRYING_FOLLOW_UP_CAPTURE_MESSAGE in events
    assert f"{ACCEPTED_FOLLOW_UP_PREFIX} second question" in events


def test_voice_loop_returns_to_sleep_when_follow_up_retry_is_invalid() -> None:
    settings = AppSettings(_env_file=None)
    settings.voice_loop_speak_status = False
    assistant = SpyAssistant()
    provider = FakeProvider(["hey jarvis", "status report", "you", "uh"])
    events: list[str] = []

    report = VoiceLoopRunner(
        settings=settings,
        assistant=assistant,
        provider=provider,
        recorder=fake_recorder,
        sleeper=no_sleep,
        beeper=no_beep,
        status_callback=events.append,
    ).run_once()

    assert report.cleaned_command == "status report"
    assert assistant.commands == ["status report"]
    assert report.statuses.count(NO_COMMAND_DETECTED_MESSAGE) == 2
    assert report.statuses.count(RETRYING_FOLLOW_UP_CAPTURE_MESSAGE) == 1
    assert report.statuses[-1] == RETURNING_TO_SLEEP_MESSAGE
    assert f"{REJECTED_FOLLOW_UP_PREFIX} you (rejected phrase: you)" in events
    assert f"{REJECTED_FOLLOW_UP_PREFIX} uh (rejected phrase: uh)" in events


def test_voice_loop_follow_up_timeout_returns_to_sleep_without_wake_retry() -> None:
    settings = AppSettings(_env_file=None)
    settings.voice_loop_speak_status = False
    assistant = SpyAssistant()
    provider = FakeProvider(["hey jarvis", "status report", ""])
    durations: list[float] = []

    def recording_recorder(duration: float) -> list[float]:
        durations.append(duration)
        return fake_recorder(duration)

    report = VoiceLoopRunner(
        settings=settings,
        assistant=assistant,
        provider=provider,
        recorder=recording_recorder,
        sleeper=no_sleep,
        beeper=no_beep,
    ).run_once()

    assert report.cleaned_command == "status report"
    assert assistant.commands == ["status report"]
    assert report.statuses.count("Listening for wake phrase") == 1
    assert report.statuses.count(LISTENING_FOR_FOLLOW_UP_PROMPT) == 1
    assert NO_COMMAND_DETECTED_MESSAGE not in report.statuses
    assert report.statuses[-1] == RETURNING_TO_SLEEP_MESSAGE
    assert durations[-1] == FOLLOW_UP_RECORD_SECONDS


def test_voice_loop_returns_to_sleep_after_retry_is_also_invalid() -> None:
    settings = AppSettings(_env_file=None)
    settings.voice_loop_speak_status = False
    assistant = SpyAssistant()
    provider = FakeProvider(["hey jarvis", "you", "uh"])
    events: list[str] = []

    report = VoiceLoopRunner(
        settings=settings,
        assistant=assistant,
        provider=provider,
        recorder=fake_recorder,
        sleeper=no_sleep,
        beeper=no_beep,
        status_callback=events.append,
    ).run_once()

    assert report.cleaned_command == "uh"
    assert report.command_validation.accepted is False
    assert report.command_validation.rejection_reason == "rejected phrase: uh"
    assert assistant.commands == []
    assert report.statuses.count(NO_COMMAND_DETECTED_MESSAGE) == 2
    assert report.statuses.count(RETRYING_COMMAND_CAPTURE_MESSAGE) == 1
    assert report.statuses[-1] == RETURNING_TO_SLEEP_MESSAGE
    assert f"{REJECTED_COMMAND_PREFIX} you (rejected phrase: you)" in events
    assert f"{REJECTED_COMMAND_PREFIX} uh (rejected phrase: uh)" in events
    assert RETURNING_TO_SLEEP_MESSAGE in events


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
    provider = FakeProvider(["hey jarvis", "status report", "", "hey jarvis", "sleep jarvis"])

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
    provider = FakeProvider(["hey jarvis", ". . . . .", ". . . . ."])

    runner = VoiceLoopRunner(
        settings=settings,
        assistant=assistant,
        provider=provider,
        recorder=fake_recorder,
        sleeper=no_sleep,
        beeper=no_beep,
    )

    reports = runner.run(max_cycles=5)

    assert len(reports) == 1
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


def test_voice_loop_uses_conversation_history_between_turns() -> None:
    settings = AppSettings(_env_file=None, openai_enabled=True, openai_api_key="sk-test")
    settings.voice_loop_speak_status = False
    openai_service = SpyOpenAIService()
    assistant = AssistantCore(settings=settings, openai_service=openai_service)
    provider = FakeProvider(["hey jarvis", "first question", "second question", ""])

    runner = VoiceLoopRunner(
        settings=settings,
        assistant=assistant,
        provider=provider,
        tts_provider=FakeTtsProvider(),
        recorder=fake_recorder,
        sleeper=no_sleep,
        beeper=no_beep,
    )

    reports = runner.run(max_cycles=1)

    assert len(reports) == 1
    assert openai_service.messages == ["first question", "second question"]
    assert openai_service.histories[0] is None
    assert openai_service.histories[1] is not None
    assert "User: first question" in (openai_service.histories[1] or "")
    assert "Assistant: handled first question" in (openai_service.histories[1] or "")
