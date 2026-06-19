from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from assistant.core import AssistantResponse
from config.settings import AppSettings
from main import main
from voice.fast_voice import (
    FAST_GUI_REJECTED_RESPONSE,
    FastCaptureResult,
    FastVoiceRunner,
    format_fast_voice_report,
    resolve_fast_input_device,
    select_fast_voice_silence_ms,
)
from voice.interfaces import TranscriptionResult
from voice.tts import TextToSpeechResult


class FakeProvider:
    name = "fake_stt"
    available = True

    def __init__(self, transcript: str, confidence: float | None = 0.95) -> None:
        self.transcript = transcript
        self.confidence = confidence
        self.calls = 0
        self.warm_up_calls = 0

    def warm_up(self) -> bool:
        self.warm_up_calls += 1
        return True

    def transcribe(self, samples, sample_rate: int) -> TranscriptionResult:
        assert samples
        assert sample_rate == 16000
        self.calls += 1
        return TranscriptionResult(text=self.transcript, confidence=self.confidence)


class SpyAssistant:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def handle_voice_command(self, command: str) -> AssistantResponse:
        self.commands.append(command)
        return AssistantResponse(text="Systems nominal.", source="fake")


def test_fast_voice_runs_one_repaired_command_through_assistant(tmp_path: Path) -> None:
    settings = AppSettings(
        _env_file=None,
        log_dir=tmp_path / "logs",
        fast_voice_activation="direct",
        fast_voice_tts_enabled=False,
    )
    provider = FakeProvider("Hey Jarvis, that's report")
    assistant = SpyAssistant()
    output: list[str] = []
    runner = FastVoiceRunner(
        settings,
        provider=provider,
        assistant=assistant,  # type: ignore[arg-type]
        recorder=lambda: ([0.2] * 1600, "Microphone Array"),
        output_func=output.append,
    )

    report = runner.run_once()
    text = format_fast_voice_report(report)

    assert provider.calls == 1
    assert report.raw_transcript == "Hey Jarvis, that's report"
    assert report.cleaned_transcript == "that's report"
    assert report.command == "status report"
    assert report.validation.accepted is True
    assert assistant.commands == ["status report"]
    assert report.assistant_response is not None
    assert report.assistant_response.text == "Systems nominal."
    assert report.tts_result is None
    assert report.is_successful is True
    assert any(item == "Jarvis: Systems nominal." for item in output)
    for field in (
        "capture_ms=",
        "audio_record_ms=",
        "audio_prepare_ms=",
        "stt_warmup_ms=",
        "vad_wait_ms=",
        "speech_ms=",
        "trailing_silence_ms=",
        "transcribe_ms=",
        "openai_ms=",
        "tts_ms=",
        "total_ms=",
    ):
        assert field in text


@pytest.mark.parametrize("transcript", ["Wake up, Jarvis.", "Hey Jarvis", "Jarvis"])
def test_fast_voice_wake_only_returns_ready_without_assistant(
    transcript: str,
    tmp_path: Path,
) -> None:
    settings = AppSettings(_env_file=None, log_dir=tmp_path / "logs")
    provider = FakeProvider(transcript)
    assistant = SpyAssistant()
    output: list[str] = []
    report = FastVoiceRunner(
        settings,
        provider=provider,
        assistant=assistant,  # type: ignore[arg-type]
        recorder=lambda: ([0.2] * 1600, "Microphone Array"),
        output_func=output.append,
    ).run_once()

    assert report.wake_only is True
    assert report.command == ""
    assert report.command_accepted is True
    assert report.is_successful is True
    assert report.assistant_response is not None
    assert report.assistant_response.text == "I'm listening."
    assert report.timing.openai_ms == 0.0
    assert assistant.commands == []
    assert "Jarvis: I'm listening." in output


def test_fast_voice_vad_with_empty_transcript_returns_clear_local_response(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, log_dir=tmp_path / "logs")
    assistant = SpyAssistant()
    output: list[str] = []
    report = FastVoiceRunner(
        settings,
        provider=FakeProvider(""),
        assistant=assistant,  # type: ignore[arg-type]
        recorder=lambda: FastCaptureResult(
            [0.2] * 1600,
            "Microphone Array",
            speech_ms=400.0,
            vad_crossed=True,
        ),
        output_func=output.append,
    ).run_once()

    assert report.unintelligible_audio is True
    assert report.vad_crossed is True
    assert report.command_accepted is False
    assert report.assistant_response is not None
    assert report.assistant_response.text == "I heard sound but could not understand it."
    assert report.timing.openai_ms == 0.0
    assert assistant.commands == []
    assert "Jarvis: I heard sound but could not understand it." in output


@pytest.mark.parametrize(
    "transcript",
    ["You", "Okay", "For me", "3 8 8 8 8 9", ""],
)
def test_gui_fast_voice_rejects_accidental_or_weak_transcripts(
    transcript: str,
    tmp_path: Path,
) -> None:
    settings = AppSettings(_env_file=None, log_dir=tmp_path / "logs")
    assistant = SpyAssistant()
    report = FastVoiceRunner(
        settings,
        provider=FakeProvider(transcript),
        assistant=assistant,  # type: ignore[arg-type]
        recorder=lambda: FastCaptureResult(
            [0.2] * 1600,
            "Microphone Array",
            speech_ms=400.0,
            vad_crossed=True,
        ),
        strict_command_validation=True,
        output_func=lambda _message: None,
    ).run_once()

    assert report.command_accepted is False
    assert report.assistant_response is not None
    assert report.assistant_response.text == FAST_GUI_REJECTED_RESPONSE
    assert report.assistant_response.source == "fast_voice_rejected"
    assert report.timing.openai_ms == 0.0
    assert assistant.commands == []


def test_gui_fast_voice_rejects_low_confidence_transcript(tmp_path: Path) -> None:
    assistant = SpyAssistant()
    report = FastVoiceRunner(
        AppSettings(_env_file=None, log_dir=tmp_path / "logs"),
        provider=FakeProvider("status report", confidence=0.2),
        assistant=assistant,  # type: ignore[arg-type]
        recorder=lambda: ([0.2] * 1600, "Microphone Array"),
        strict_command_validation=True,
        output_func=lambda _message: None,
    ).run_once()

    assert report.command_accepted is False
    assert report.transcript_confidence == 0.2
    assert report.assistant_response is not None
    assert report.assistant_response.text == FAST_GUI_REJECTED_RESPONSE
    assert assistant.commands == []


def test_gui_fast_voice_accepts_intentional_command_and_wake_only(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, log_dir=tmp_path / "logs")
    assistant = SpyAssistant()
    command_report = FastVoiceRunner(
        settings,
        provider=FakeProvider("status report"),
        assistant=assistant,  # type: ignore[arg-type]
        recorder=lambda: ([0.2] * 1600, "Microphone Array"),
        strict_command_validation=True,
        output_func=lambda _message: None,
    ).run_once()
    wake_report = FastVoiceRunner(
        settings,
        provider=FakeProvider("Jarvis"),
        assistant=assistant,  # type: ignore[arg-type]
        recorder=lambda: ([0.2] * 1600, "Microphone Array"),
        strict_command_validation=True,
        output_func=lambda _message: None,
    ).run_once()

    assert command_report.command_accepted is True
    assert assistant.commands == ["status report"]
    assert wake_report.wake_only is True
    assert wake_report.command_accepted is True
    assert wake_report.assistant_response is not None
    assert wake_report.assistant_response.text == "I'm listening."


def test_terminal_fast_voice_keeps_existing_validation_behavior(tmp_path: Path) -> None:
    assistant = SpyAssistant()
    report = FastVoiceRunner(
        AppSettings(_env_file=None, log_dir=tmp_path / "logs"),
        provider=FakeProvider("for me"),
        assistant=assistant,  # type: ignore[arg-type]
        recorder=lambda: ([0.2] * 1600, "Microphone Array"),
        output_func=lambda _message: None,
    ).run_once()

    assert report.command_accepted is True
    assert assistant.commands == ["for me"]


def test_fast_voice_tts_is_controlled_by_fast_setting(tmp_path: Path) -> None:
    settings = AppSettings(
        _env_file=None,
        log_dir=tmp_path / "logs",
        fast_voice_tts_enabled=True,
    )
    calls: list[str] = []

    def fake_tts(text: str, settings: AppSettings, speak_requested: bool) -> TextToSpeechResult:
        assert speak_requested is True
        calls.append(text)
        return TextToSpeechResult(
            provider_name="fake_tts",
            provider_available=True,
            requested=True,
            spoken=True,
            log_file=settings.log_dir / "tts.log",
        )

    report = FastVoiceRunner(
        settings,
        provider=FakeProvider("status report"),
        assistant=SpyAssistant(),  # type: ignore[arg-type]
        recorder=lambda: ([0.2] * 1600, "Microphone Array"),
        tts_function=fake_tts,
        output_func=lambda _message: None,
    ).run_once()

    assert calls == ["Systems nominal."]
    assert report.tts_result is not None
    assert report.tts_result.spoken is True


class FakeInputStream:
    def __init__(self, levels: list[float]) -> None:
        self.levels = list(levels)
        self.read_count = 0
        self.start_count = 0
        self.stop_count = 0
        self.close_count = 0
        self.enter_count = 0
        self.active = False

    def __enter__(self):
        self.enter_count += 1
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback

    def read(self, frames: int):
        self.read_count += 1
        value = self.levels.pop(0) if self.levels else 0.0
        return [value] * frames, False

    def start(self) -> None:
        self.start_count += 1
        self.active = True

    def stop(self) -> None:
        self.stop_count += 1
        self.active = False

    def close(self) -> None:
        self.close_count += 1
        self.active = False


class FakeSoundDevice:
    default = SimpleNamespace(device=(2, 4))

    def __init__(self, levels: list[float]) -> None:
        self.stream = FakeInputStream(levels)
        self.input_stream_calls = 0
        self.input_stream_kwargs: list[dict[str, object]] = []

    def query_devices(self):
        return [
            {"name": "Microsoft Sound Mapper", "max_input_channels": 1},
            {"name": "Speakers", "max_input_channels": 0},
            {"name": "Microphone Array (Realtek)", "max_input_channels": 2},
        ]

    def check_input_settings(self, *, device: int, samplerate: int, channels: int) -> None:
        assert device == 2
        assert samplerate == 16000
        assert channels == 1

    def InputStream(self, **kwargs):
        assert kwargs["device"] == 2
        assert "start" not in kwargs
        self.input_stream_calls += 1
        self.input_stream_kwargs.append(dict(kwargs))
        return self.stream


def test_fast_capture_stops_shortly_after_silence(tmp_path: Path) -> None:
    settings = AppSettings(
        _env_file=None,
        log_dir=tmp_path / "logs",
        voice_input_device="Microphone Array",
        voice_vad_threshold=0.02,
        fast_voice_record_seconds=2.0,
        fast_voice_silence_ms=160,
        fast_voice_fast_stop_enabled=False,
    )
    sd = FakeSoundDevice([0.01, 0.01, 0.01, 0.2, 0.2, 0.2, 0.01, 0.01, 0.01])
    runner = FastVoiceRunner(
        settings,
        provider=FakeProvider("status report"),
        assistant=SpyAssistant(),  # type: ignore[arg-type]
        sounddevice_module=sd,
        output_func=lambda _message: None,
    )

    capture = runner._capture_until_silence()

    assert capture.input_device == "Microphone Array (Realtek)"
    assert capture.samples
    assert capture.vad_crossed is True
    assert sd.stream.read_count == 8
    assert len(capture.samples) < int(settings.voice_sample_rate * settings.fast_voice_record_seconds)
    assert capture.vad_wait_ms == pytest.approx(240.0)
    assert capture.speech_ms == pytest.approx(240.0)
    assert capture.trailing_silence_ms == pytest.approx(160.0)


def test_fast_capture_separates_blocking_reads_from_preparation(tmp_path: Path) -> None:
    settings = AppSettings(
        _env_file=None,
        log_dir=tmp_path / "logs",
        voice_input_device="Microphone Array",
        voice_vad_threshold=0.02,
        fast_voice_record_seconds=2.0,
        fast_voice_silence_ms=160,
        fast_voice_fast_stop_enabled=False,
    )
    sd = FakeSoundDevice([0.01, 0.01, 0.01, 0.2, 0.2, 0.2, 0.01, 0.01])
    clock_values = [0.0]
    read_started = 0.5
    for _ in range(8):
        clock_values.extend((read_started, read_started + 0.08))
        read_started += 0.10
    clock_values.append(2.6)
    values = iter(clock_values)
    runner = FastVoiceRunner(
        settings,
        provider=FakeProvider("status report"),
        assistant=SpyAssistant(),  # type: ignore[arg-type]
        sounddevice_module=sd,
        output_func=lambda _message: None,
        clock=lambda: next(values),
    )

    capture = runner._capture_until_silence()

    assert capture.audio_record_ms == pytest.approx(640.0)
    assert capture.audio_prepare_ms == pytest.approx(1960.0)


def test_fast_voice_capture_metric_uses_audio_record_time(tmp_path: Path) -> None:
    settings = AppSettings(
        _env_file=None,
        log_dir=tmp_path / "logs",
        fast_voice_warm_stt_on_start=False,
    )
    report = FastVoiceRunner(
        settings,
        provider=FakeProvider("status report"),
        assistant=SpyAssistant(),  # type: ignore[arg-type]
        recorder=lambda: FastCaptureResult(
            [0.2] * 1600,
            "Microphone Array",
            vad_wait_ms=240.0,
            speech_ms=960.0,
            trailing_silence_ms=400.0,
            vad_crossed=True,
            audio_record_ms=1600.0,
            audio_prepare_ms=1676.0,
        ),
        output_func=lambda _message: None,
    ).run_once()

    assert report.timing.capture_ms == 1600.0
    assert report.timing.audio_record_ms == 1600.0
    assert report.timing.audio_prepare_ms == 1676.0
    assert report.timing.stt_warmup_ms == 0.0


def test_fast_capture_keeps_only_configured_preroll_before_speech(tmp_path: Path) -> None:
    settings = AppSettings(
        _env_file=None,
        log_dir=tmp_path / "logs",
        voice_input_device="Microphone Array",
        voice_vad_threshold=0.02,
        fast_voice_record_seconds=2.0,
        fast_voice_max_seconds=2.0,
        fast_voice_min_speech_ms=300,
        fast_voice_silence_ms=160,
        fast_voice_fast_stop_enabled=False,
        fast_voice_preroll_ms=250,
    )
    sd = FakeSoundDevice(
        [0.01, 0.01, 0.01, 0.01, 0.01, 0.2, 0.2, 0.2, 0.01, 0.01]
    )
    runner = FastVoiceRunner(
        settings,
        provider=FakeProvider("status report"),
        assistant=SpyAssistant(),  # type: ignore[arg-type]
        sounddevice_module=sd,
        output_func=lambda _message: None,
    )

    capture = runner._capture_until_silence()

    expected_preroll_samples = int(settings.voice_sample_rate * 0.250)
    captured_after_trigger = 5 * int(settings.voice_sample_rate * 0.080)
    assert sd.stream.read_count == 10
    assert len(capture.samples) == expected_preroll_samples + captured_after_trigger
    assert len(capture.samples) < sd.stream.read_count * int(settings.voice_sample_rate * 0.080)


@pytest.mark.parametrize(
    ("speech_chunks", "expected_silence_ms", "expected_silence_chunks"),
    [(5, 250, 4), (14, 450, 6)],
)
def test_fast_capture_adapts_silence_to_command_length(
    speech_chunks: int,
    expected_silence_ms: int,
    expected_silence_chunks: int,
    tmp_path: Path,
) -> None:
    settings = AppSettings(
        _env_file=None,
        log_dir=tmp_path / "logs",
        voice_input_device="Microphone Array",
        voice_vad_threshold=0.02,
        fast_voice_record_seconds=3.0,
        fast_voice_max_seconds=3.0,
        fast_voice_fast_stop_enabled=True,
        fast_voice_short_command_silence_ms=250,
        fast_voice_long_command_silence_ms=450,
    )
    pre_speech_chunks = 3
    sd = FakeSoundDevice(
        [0.01] * pre_speech_chunks
        + [0.2] * speech_chunks
        + [0.01] * (expected_silence_chunks + 2)
    )
    runner = FastVoiceRunner(
        settings,
        provider=FakeProvider("status report"),
        assistant=SpyAssistant(),  # type: ignore[arg-type]
        sounddevice_module=sd,
        output_func=lambda _message: None,
    )

    capture = runner._capture_until_silence()

    speech_ms = speech_chunks * 80.0
    assert select_fast_voice_silence_ms(settings, speech_ms) == expected_silence_ms
    assert sd.stream.read_count == pre_speech_chunks + speech_chunks + expected_silence_chunks
    assert capture.trailing_silence_ms == pytest.approx(expected_silence_chunks * 80.0)


def test_fast_voice_uses_fast_specific_assistant_handler(tmp_path: Path) -> None:
    class FastAwareAssistant:
        def __init__(self) -> None:
            self.fast_commands: list[str] = []

        def handle_fast_voice_command(self, command: str) -> AssistantResponse:
            self.fast_commands.append(command)
            return AssistantResponse(text="Brief response.", source="fake")

        def handle_voice_command(self, command: str) -> AssistantResponse:
            pytest.fail(f"normal voice handler called for fast command: {command}")

    assistant = FastAwareAssistant()
    report = FastVoiceRunner(
        AppSettings(_env_file=None, log_dir=tmp_path / "logs"),
        provider=FakeProvider("status report"),
        assistant=assistant,  # type: ignore[arg-type]
        recorder=lambda: ([0.2] * 1600, "Microphone Array"),
        output_func=lambda _message: None,
    ).run_once()

    assert assistant.fast_commands == ["status report"]
    assert report.assistant_response is not None
    assert report.assistant_response.text == "Brief response."


def test_fast_voice_reuses_and_warms_stt_provider_once(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, log_dir=tmp_path / "logs")
    provider = FakeProvider("status report")
    runner = FastVoiceRunner(
        settings,
        provider=provider,
        assistant=SpyAssistant(),  # type: ignore[arg-type]
        recorder=lambda: FastCaptureResult(
            [0.2] * 1600,
            "Microphone Array",
            vad_wait_ms=80.0,
            speech_ms=500.0,
            trailing_silence_ms=600.0,
        ),
        output_func=lambda _message: None,
    )

    first = runner.run_once()
    second = runner.run_once()

    assert first.timing.vad_wait_ms == 80.0
    assert first.timing.speech_ms == 500.0
    assert first.timing.trailing_silence_ms == 600.0
    assert second.is_successful is True
    assert provider.warm_up_calls == 1
    assert provider.calls == 2
    assert first.timing.stt_warmup_ms == 0.0
    assert second.timing.stt_warmup_ms == 0.0


def test_fast_voice_loop_reuses_one_persistent_audio_stream(tmp_path: Path) -> None:
    settings = AppSettings(
        _env_file=None,
        log_dir=tmp_path / "logs",
        voice_input_device="Microphone Array",
        voice_vad_threshold=0.02,
        fast_voice_activation="enter",
        fast_voice_silence_ms=160,
        fast_voice_fast_stop_enabled=False,
    )
    levels = [0.01, 0.01, 0.01, 0.2, 0.2, 0.2, 0.01, 0.01] * 2
    sd = FakeSoundDevice(levels)
    provider = FakeProvider("status report")
    output: list[str] = []
    runner = FastVoiceRunner(
        settings,
        provider=provider,
        assistant=SpyAssistant(),  # type: ignore[arg-type]
        sounddevice_module=sd,
        input_func=lambda _prompt: "",
        output_func=output.append,
    )

    result = runner.run(max_turns=2)

    assert result == 0
    assert sd.input_stream_calls == 1
    assert "start" not in sd.input_stream_kwargs[0]
    assert sd.stream.start_count == 2
    assert sd.stream.stop_count == 2
    assert sd.stream.close_count == 1
    assert provider.warm_up_calls == 1
    assert provider.calls == 2
    assert any("startup_stt_warmup_ms=" in line for line in output)
    assert sum(
        line.startswith("Jarvis Fast Voice Command") and "stt_warmup_ms=0.0" in line
        for line in output
    ) == 2


def test_fast_voice_continuous_session_emits_gui_stages_and_report(tmp_path: Path) -> None:
    settings = AppSettings(
        _env_file=None,
        log_dir=tmp_path / "logs",
        voice_input_device="Microphone Array",
        voice_vad_threshold=0.02,
        fast_voice_silence_ms=160,
        fast_voice_fast_stop_enabled=False,
    )
    sd = FakeSoundDevice([0.01, 0.01, 0.01, 0.2, 0.2, 0.2, 0.01, 0.01])
    statuses: list[str] = []
    reports = []
    runner = FastVoiceRunner(
        settings,
        provider=FakeProvider("status report"),
        assistant=SpyAssistant(),  # type: ignore[arg-type]
        sounddevice_module=sd,
        output_func=lambda _message: None,
        status_callback=statuses.append,
        report_callback=reports.append,
    )

    result = runner.run_continuous(max_turns=1)

    assert result == 0
    assert statuses == ["Listening", "Transcribing", "Thinking", "Responding", "Stopped"]
    assert len(reports) == 1
    assert reports[0].command == "status report"
    assert sd.stream.close_count == 1


def test_fast_command_capture_keeps_one_shot_stream_fallback(tmp_path: Path) -> None:
    settings = AppSettings(
        _env_file=None,
        log_dir=tmp_path / "logs",
        voice_input_device="Microphone Array",
        voice_vad_threshold=0.02,
        fast_voice_silence_ms=160,
        fast_voice_fast_stop_enabled=False,
    )
    sd = FakeSoundDevice([0.01, 0.01, 0.01, 0.2, 0.2, 0.2, 0.01, 0.01])
    runner = FastVoiceRunner(
        settings,
        provider=FakeProvider("status report"),
        assistant=SpyAssistant(),  # type: ignore[arg-type]
        sounddevice_module=sd,
        output_func=lambda _message: None,
    )

    report = runner.run_once()

    assert report.is_successful is True
    assert runner._audio_stream is None
    assert sd.input_stream_calls == 1
    assert sd.stream.enter_count == 1
    assert sd.stream.start_count == 0
    assert sd.stream.close_count == 0


@pytest.mark.parametrize(
    "transcript",
    [
        "We cup out of his.",
        "Wake up out of his.",
        "Wake up jar of this.",
        "We got Jarvis.",
    ],
)
def test_fast_voice_repaired_wake_phrase_stays_local(
    transcript: str,
    tmp_path: Path,
) -> None:
    settings = AppSettings(_env_file=None, log_dir=tmp_path / "logs")
    assistant = SpyAssistant()
    report = FastVoiceRunner(
        settings,
        provider=FakeProvider(transcript),
        assistant=assistant,  # type: ignore[arg-type]
        recorder=lambda: ([0.2] * 1600, "Microphone Array"),
        output_func=lambda _message: None,
    ).run_once()

    assert report.wake_only is True
    assert report.speech_repair is not None
    assert report.speech_repair.repaired_transcript == "wake up jarvis"
    assert report.assistant_response is not None
    assert report.assistant_response.text == "I'm listening."
    assert report.timing.openai_ms == 0.0
    assert assistant.commands == []


def test_fast_input_device_supports_name_and_index() -> None:
    sd = FakeSoundDevice([])

    assert resolve_fast_input_device(sd, "Microphone Array") == (2, "Microphone Array (Realtek)")
    assert resolve_fast_input_device(sd, "2") == (2, "Microphone Array (Realtek)")
    with pytest.raises(RuntimeError, match="was not found"):
        resolve_fast_input_device(sd, "missing mic")


def test_clap_activation_is_local_amplitude_detection(tmp_path: Path) -> None:
    settings = AppSettings(
        _env_file=None,
        log_dir=tmp_path / "logs",
        voice_input_device="Microphone Array",
        fast_voice_activation="clap",
    )
    sd = FakeSoundDevice([0.01, 0.2])
    output: list[str] = []
    runner = FastVoiceRunner(
        settings,
        provider=FakeProvider("status report"),
        assistant=SpyAssistant(),  # type: ignore[arg-type]
        sounddevice_module=sd,
        output_func=output.append,
    )

    assert runner._wait_for_clap() is True
    assert output == ["Clap detected. Speak now."]


def test_fast_voice_cli_commands(monkeypatch, tmp_path: Path, capsys) -> None:
    settings = AppSettings(_env_file=None, log_dir=tmp_path / "logs")
    monkeypatch.setattr("main.load_settings", lambda: settings)
    monkeypatch.setattr("main.FastVoiceRunner.run", lambda self: 0)

    assert main(["--fast-voice"]) == 0

    fake_report = SimpleNamespace(is_successful=True)
    monkeypatch.setattr("main.run_fast_command_test", lambda settings, assistant: fake_report)
    monkeypatch.setattr("main.format_fast_voice_report", lambda report: "fast command report")

    assert main(["--fast-command-test"]) == 0
    assert "fast command report" in capsys.readouterr().out
