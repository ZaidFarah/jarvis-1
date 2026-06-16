from __future__ import annotations

from pathlib import Path

from config.settings import AppSettings
from main import main
from voice.command_capture import (
    CommandCaptureDiagnosticRunner,
    CommandCaptureReport,
    calculate_audio_capture_metrics,
    format_command_capture_report,
)
from voice.command_validation import validate_cleaned_command
from voice.interfaces import TranscriptionResult


class FakeProvider:
    name = "fake_stt"
    available = True

    def __init__(self, transcript: str) -> None:
        self.transcript = transcript

    def transcribe(self, samples, sample_rate: int) -> TranscriptionResult:
        del samples, sample_rate
        return TranscriptionResult(text=self.transcript)


class FakeSoundDevice:
    def check_input_settings(self, samplerate: int, channels: int) -> None:
        assert samplerate == 16000
        assert channels == 1

    def rec(self, frames: int, samplerate: int, channels: int, dtype: str):
        assert samplerate == 16000
        assert channels == 1
        assert dtype == "float32"
        return [0.05 for _ in range(frames)]

    def wait(self) -> None:
        return None


def test_command_capture_runner_reports_validation_and_audio_levels(tmp_path: Path) -> None:
    settings = AppSettings(
        _env_file=None,
        log_dir=tmp_path / "logs",
        voice_command_record_seconds=0.25,
    )

    report = CommandCaptureDiagnosticRunner(
        settings,
        provider=FakeProvider("you"),
        sounddevice_module=FakeSoundDevice(),
    ).run()
    text = format_command_capture_report(report)

    assert report.provider_name == "fake_stt"
    assert report.sample_rate == 16000
    assert report.record_seconds == 0.25
    assert report.average_rms > 0
    assert report.max_rms > 0
    assert report.vad_threshold_crossed is True
    assert report.raw_transcript == "you"
    assert report.cleaned_command == "you"
    assert report.speech_repair is not None
    assert report.speech_repair.strategy == "skipped"
    assert report.accepted is False
    assert report.rejection_reason == "rejected phrase: you"
    assert report.log_file == tmp_path / "logs" / "command_capture.log"
    assert "Jarvis Command Capture Test" in text
    assert "provider: fake_stt" in text
    assert "sample rate: 16000" in text
    assert "record seconds: 0.25" in text
    assert "average RMS:" in text
    assert "max RMS:" in text
    assert "VAD threshold crossed: yes" in text
    assert "raw transcript: you" in text
    assert "cleaned command: you" in text
    assert "repair strategy: skipped" in text
    assert "accepted: no" in text
    assert "rejection reason: rejected phrase: you" in text
    assert "diagnostic log:" in text


def test_audio_capture_metrics_helper_reports_rms_and_vad() -> None:
    metrics = calculate_audio_capture_metrics([0.0, 0.2, -0.2, 0.0], sample_rate=16000, vad_threshold=0.05)

    assert metrics.average_rms > 0
    assert metrics.max_rms > 0
    assert metrics.vad_threshold == 0.05
    assert metrics.vad_threshold_crossed is True


def test_command_capture_runner_reports_speech_repair(tmp_path: Path) -> None:
    settings = AppSettings(
        _env_file=None,
        log_dir=tmp_path / "logs",
        weather_default_city="Nottingham",
        voice_command_record_seconds=0.25,
    )

    report = CommandCaptureDiagnosticRunner(
        settings,
        provider=FakeProvider("Did it noting him today? What's the"),
        sounddevice_module=FakeSoundDevice(),
    ).run()
    text = format_command_capture_report(report)

    assert report.raw_transcript == "Did it noting him today? What's the"
    assert report.cleaned_command == "what's the weather in Nottingham today"
    assert report.speech_repair is not None
    assert report.speech_repair.confidence == 0.92
    assert report.speech_repair.strategy == "rule"
    assert report.accepted is True
    assert "repaired transcript: what's the weather in Nottingham today" in text
    assert "repair confidence: 0.92" in text
    assert "repair strategy: rule" in text


def test_command_capture_cli_command_formats_report(tmp_path: Path, monkeypatch, capsys) -> None:
    settings = AppSettings(_env_file=None, log_dir=tmp_path / "logs")
    report = CommandCaptureReport(
        provider_name="fake_stt",
        provider_available=True,
        sample_rate=16000,
        record_seconds=7.0,
        average_rms=0.01,
        max_rms=0.03,
        vad_threshold=0.0015,
        vad_threshold_crossed=True,
        raw_transcript="status report",
        cleaned_command="status report",
        validation=validate_cleaned_command("status report", reject_phrases=settings.voice_command_reject_phrase_list),
        log_file=tmp_path / "logs" / "command_capture.log",
    )
    monkeypatch.setattr("main.load_settings", lambda: settings)
    monkeypatch.setattr("main.run_command_capture_test", lambda settings: report)

    exit_code = main(["--command-capture-test"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Jarvis Command Capture Test" in output
    assert "raw transcript: status report" in output
    assert "accepted: yes" in output
