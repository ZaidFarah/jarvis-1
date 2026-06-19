from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from assistant.core import AssistantResponse
from config.settings import AppSettings
from main import main
from voice.fast_voice import FastVoiceRunner, format_fast_voice_report, resolve_fast_input_device
from voice.interfaces import TranscriptionResult
from voice.tts import TextToSpeechResult


class FakeProvider:
    name = "fake_stt"
    available = True

    def __init__(self, transcript: str) -> None:
        self.transcript = transcript
        self.calls = 0

    def transcribe(self, samples, sample_rate: int) -> TranscriptionResult:
        assert samples
        assert sample_rate == 16000
        self.calls += 1
        return TranscriptionResult(text=self.transcript, confidence=0.95)


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
    for field in ("capture_ms=", "transcribe_ms=", "openai_ms=", "tts_ms=", "total_ms="):
        assert field in text


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

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback

    def read(self, frames: int):
        self.read_count += 1
        value = self.levels.pop(0) if self.levels else 0.0
        return [value] * frames, False


class FakeSoundDevice:
    default = SimpleNamespace(device=(2, 4))

    def __init__(self, levels: list[float]) -> None:
        self.stream = FakeInputStream(levels)

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
        return self.stream


def test_fast_capture_stops_shortly_after_silence(tmp_path: Path) -> None:
    settings = AppSettings(
        _env_file=None,
        log_dir=tmp_path / "logs",
        voice_input_device="Microphone Array",
        voice_vad_threshold=0.02,
        fast_voice_record_seconds=2.0,
        fast_voice_silence_ms=160,
    )
    sd = FakeSoundDevice([0.01, 0.01, 0.01, 0.2, 0.2, 0.2, 0.01, 0.01, 0.01])
    runner = FastVoiceRunner(
        settings,
        provider=FakeProvider("status report"),
        assistant=SpyAssistant(),  # type: ignore[arg-type]
        sounddevice_module=sd,
        output_func=lambda _message: None,
    )

    samples, device_name = runner._capture_until_silence()

    assert device_name == "Microphone Array (Realtek)"
    assert samples
    assert sd.stream.read_count == 8
    assert len(samples) < int(settings.voice_sample_rate * settings.fast_voice_record_seconds)


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
