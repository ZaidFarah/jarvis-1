from __future__ import annotations

from pathlib import Path

from voice.transcription_diagnostics import TranscriptionDiagnosticReport, format_transcription_report


def test_transcription_report_formats_errors_and_result() -> None:
    report = TranscriptionDiagnosticReport(
        provider_name="faster_whisper",
        provider_available=True,
        model_name="base.en",
        device="cpu",
        compute_type="int8",
        sample_rate=16000,
        record_seconds=5.0,
        max_rms=0.02,
        vad_threshold=0.0015,
        vad_threshold_crossed=True,
        transcription="wake up jarvis",
        log_file=Path("logs/stt_diagnostics.log"),
        errors=[],
    )

    text = format_transcription_report(report)

    assert "provider: faster_whisper" in text
    assert "model: base.en" in text
    assert "max RMS level: 0.020000" in text
    assert "wake up jarvis" in text


def test_transcription_report_handles_missing_provider() -> None:
    report = TranscriptionDiagnosticReport(
        provider_name="faster_whisper",
        provider_available=False,
        model_name="base.en",
        device="cpu",
        compute_type="int8",
        sample_rate=16000,
        record_seconds=5.0,
        max_rms=0.0,
        vad_threshold=0.0015,
        vad_threshold_crossed=False,
        transcription="",
        log_file=Path("logs/stt_diagnostics.log"),
        errors=["Faster Whisper is not available."],
    )

    text = format_transcription_report(report)

    assert "provider available: no" in text
    assert "<no text detected>" in text
    assert "Faster Whisper is not available." in text
