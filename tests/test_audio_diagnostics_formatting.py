from __future__ import annotations

from pathlib import Path

from voice.audio_diagnostics import (
    AudioDeviceInfo,
    AudioDiagnosticsReport,
    MicrophoneTestResult,
    build_audio_suggestions,
    format_audio_check_report,
    format_microphone_test_summary,
)


def test_audio_report_includes_default_mic_sample_rate_and_max_rms() -> None:
    device = AudioDeviceInfo(index=1, name="Built-in Mic", input_channels=2, default_sample_rate=48000)
    test = MicrophoneTestResult(
        microphone_detected=True,
        stream_opened=True,
        rms=0.002,
        max_rms=0.004,
        vad_threshold_crossed=True,
        sample_rate=16000,
        channels=1,
        duration_seconds=5.0,
    )
    report = AudioDiagnosticsReport(
        sounddevice_available=True,
        input_devices=[device],
        default_input_device=device,
        microphone_test=test,
        tts_provider_available=True,
        log_file=Path("logs/audio_diagnostics.log"),
    )

    text = format_audio_check_report(report)

    assert "default microphone: Built-in Mic" in text
    assert "sample rate: 16000" in text
    assert "max RMS level: 0.004000" in text
    assert "VAD threshold crossed: yes" in text
    assert "diagnostic log: logs\\audio_diagnostics.log" in text or "diagnostic log: logs/audio_diagnostics.log" in text


def test_audio_report_suggests_help_when_no_microphone_detected() -> None:
    report = AudioDiagnosticsReport(
        sounddevice_available=True,
        input_devices=[],
        default_input_device=None,
        microphone_test=None,
        tts_provider_available=False,
    )
    suggestions = build_audio_suggestions(report)
    report = AudioDiagnosticsReport(
        sounddevice_available=report.sounddevice_available,
        input_devices=report.input_devices,
        default_input_device=report.default_input_device,
        microphone_test=report.microphone_test,
        tts_provider_available=report.tts_provider_available,
        suggestions=suggestions,
    )

    text = format_audio_check_report(report)

    assert "none detected" in text
    assert "No microphone input device was detected" in text


def test_audio_report_suggests_lower_threshold_when_vad_does_not_cross() -> None:
    device = AudioDeviceInfo(index=0, name="Quiet Mic", input_channels=1, default_sample_rate=44100)
    test = MicrophoneTestResult(
        microphone_detected=True,
        stream_opened=True,
        rms=0.0004,
        max_rms=0.001,
        vad_threshold_crossed=False,
        sample_rate=16000,
        channels=1,
        duration_seconds=5.0,
    )
    report = AudioDiagnosticsReport(
        sounddevice_available=True,
        input_devices=[device],
        default_input_device=device,
        microphone_test=test,
        tts_provider_available=True,
    )
    suggestions = build_audio_suggestions(report)
    report = AudioDiagnosticsReport(
        sounddevice_available=report.sounddevice_available,
        input_devices=report.input_devices,
        default_input_device=report.default_input_device,
        microphone_test=report.microphone_test,
        tts_provider_available=report.tts_provider_available,
        suggestions=suggestions,
    )

    text = format_audio_check_report(report)
    summary = format_microphone_test_summary(report)

    assert "VOICE_VAD_THRESHOLD=0.0006" in text
    assert "Max RMS: 0.001000" in summary
    assert "Suggestion:" in summary
