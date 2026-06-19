from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from config.settings import AppSettings
from diagnostics.voice_health import (
    COMMAND_REPAIR_PROBLEM,
    HEALTHY,
    HEALTHY_WITH_WARNINGS,
    MIC_PROBLEM,
    STT_PROBLEM,
    TIMING_PROBLEM,
    VAD_PROBLEM,
    WAKE_PROBLEM,
    VoiceHealthAudioMetrics,
    VoiceHealthReport,
    VoiceHealthSignals,
    _input_quality_warnings,
    _select_input_device,
    _selected_device_name_warning,
    calculate_voice_health_audio_metrics,
    diagnose_voice_health,
    format_voice_health_report,
)
from main import main
from voice.audio_diagnostics import AudioDeviceInfo


def _healthy_signals() -> VoiceHealthSignals:
    return VoiceHealthSignals(
        microphone_detected=True,
        stream_opened=True,
        average_rms=0.03,
        max_rms=0.08,
        noise_floor=0.002,
        signal_to_noise_db=24.0,
        clipping=False,
        vad_crossed=True,
        vad_trigger_seconds=0.32,
        speech_seconds=5.0,
        wake_provider_available=True,
        wake_detected=True,
        stt_provider_available=True,
        raw_transcript="hey jarvis status report",
        transcript_confidence=0.91,
        repaired_transcript="status report",
        repair_confidence=1.0,
        command_accepted=True,
    )


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"stream_opened": False}, MIC_PROBLEM),
        ({"average_rms": 0.0059}, MIC_PROBLEM),
        ({"max_rms": 0.0249}, MIC_PROBLEM),
        ({"signal_to_noise_db": 9.9}, HEALTHY_WITH_WARNINGS),
        ({"vad_trigger_seconds": 3.51}, HEALTHY_WITH_WARNINGS),
        ({"clipping": True}, MIC_PROBLEM),
        ({"vad_crossed": False}, VAD_PROBLEM),
        ({"wake_detected": False}, WAKE_PROBLEM),
        ({"raw_transcript": ""}, STT_PROBLEM),
        ({"transcript_confidence": 0.2}, STT_PROBLEM),
        ({"command_accepted": False}, COMMAND_REPAIR_PROBLEM),
        ({}, HEALTHY),
    ],
)
def test_voice_health_diagnosis_precedence(overrides: dict[str, object], expected: str) -> None:
    assert diagnose_voice_health(replace(_healthy_signals(), **overrides)) == expected


def test_voice_health_diagnoses_stt_before_fuzzy_wake() -> None:
    signals = replace(
        _healthy_signals(),
        wake_requires_stt=True,
        wake_detected=False,
        raw_transcript="",
    )

    assert diagnose_voice_health(signals) == STT_PROBLEM


def test_weak_microphone_has_priority_over_failed_wake() -> None:
    signals = replace(
        _healthy_signals(),
        average_rms=0.001948,
        max_rms=0.004164,
        noise_floor=0.001359,
        signal_to_noise_db=3.13,
        vad_trigger_seconds=4.64,
        wake_detected=False,
    )

    assert diagnose_voice_health(signals) == MIC_PROBLEM


def test_good_audio_with_failed_wake_is_wake_problem() -> None:
    assert diagnose_voice_health(replace(_healthy_signals(), wake_detected=False)) == WAKE_PROBLEM


def test_healthy_audio_late_wake_only_transcript_is_timing_problem() -> None:
    signals = replace(
        _healthy_signals(),
        average_rms=0.063054,
        max_rms=0.278146,
        signal_to_noise_db=32.89,
        vad_trigger_seconds=4.0,
        wake_detected=True,
        raw_transcript="Hey Jarvis.",
        repaired_transcript="",
        repair_confidence=1.0,
        command_accepted=False,
    )

    assert diagnose_voice_health(signals) == TIMING_PROBLEM


def test_healthy_audio_with_late_vad_and_complete_command_is_healthy() -> None:
    signals = replace(_healthy_signals(), vad_trigger_seconds=4.0)

    assert diagnose_voice_health(signals) == HEALTHY_WITH_WARNINGS


def test_successful_pipeline_with_low_snr_is_healthy_with_warnings() -> None:
    signals = replace(
        _healthy_signals(),
        signal_to_noise_db=0.19,
        calibration_rms=0.065784,
        calibration_contaminated=True,
    )

    assert diagnose_voice_health(signals) == HEALTHY_WITH_WARNINGS


def test_contaminated_calibration_produces_warning() -> None:
    signals = replace(
        _healthy_signals(),
        signal_to_noise_db=0.19,
        calibration_rms=0.065784,
        calibration_contaminated=True,
    )

    warnings = _input_quality_warnings(signals)

    assert any("Calibration may have captured noise or speech" in warning for warning in warnings)


def test_contaminated_calibration_uses_robust_speech_percentile() -> None:
    metrics = calculate_voice_health_audio_metrics(
        [0.07] * 1000,
        [0.01] * 800 + [0.2] * 200,
        sample_rate=1000,
        vad_threshold=0.02,
        vad_window_ms=100,
        noise_multiplier=3.0,
    )

    assert metrics.calibration_rms == pytest.approx(0.07)
    assert metrics.noise_floor == pytest.approx(0.01)
    assert metrics.calibration_contaminated is True


class _DefaultAudioDevice:
    device = (0, 4)


class _FakeSoundDevice:
    default = _DefaultAudioDevice()


def test_preferred_input_device_can_be_selected_by_index_or_name() -> None:
    devices = [
        AudioDeviceInfo(0, "Microsoft Sound Mapper - Input", 2, 44100.0),
        AudioDeviceInfo(3, "Realtek Microphone Array", 2, 48000.0),
    ]

    selected_by_index, index_warning = _select_input_device(_FakeSoundDevice(), devices, "3")
    selected_by_name, name_warning = _select_input_device(_FakeSoundDevice(), devices, "realtek microphone")

    assert selected_by_index == devices[1]
    assert selected_by_name == devices[1]
    assert index_warning is None
    assert name_warning is None


@pytest.mark.parametrize(
    "name",
    ["Microsoft Sound Mapper - Input", "Stereo Mix", "PC Speaker", "HDMI Output"],
)
def test_output_like_selected_devices_produce_warning(name: str) -> None:
    warning = _selected_device_name_warning(AudioDeviceInfo(0, name, 1, 48000.0))

    assert warning is not None
    assert "VOICE_INPUT_DEVICE" in warning


def _report(tmp_path: Path) -> VoiceHealthReport:
    device = AudioDeviceInfo(2, "USB Microphone", 1, 48000.0)
    return VoiceHealthReport(
        input_devices=[device],
        selected_input_device=device,
        calibration_seconds=2.0,
        speech_seconds=5.0,
        audio=VoiceHealthAudioMetrics(
            average_rms=0.03,
            max_rms=0.08,
            noise_floor=0.002,
            signal_to_noise_db=23.5,
            calibration_rms=0.002,
            calibration_contaminated=False,
            clipping=False,
            vad_threshold=0.0015,
            effective_vad_threshold=0.006,
            vad_crossed=True,
            vad_trigger_seconds=0.32,
        ),
        wake_provider="openwakeword",
        wake_model_name="hey_jarvis",
        wake_model_available=True,
        wake_score=0.82,
        wake_matched_phrase="hey_jarvis",
        wake_decision="detected",
        stt_provider="faster_whisper",
        stt_model_name="base.en",
        stt_provider_available=True,
        raw_transcript="Hey Jarvis, status report",
        transcript_confidence=0.91,
        transcription_seconds=0.45,
        clean_transcript="status report",
        repaired_transcript="status report",
        repair_confidence=1.0,
        repair_strategy="unchanged",
        command_accepted=True,
        diagnosis=HEALTHY,
        recommended_action="Run the voice loop.",
        stream_opened=True,
    )


def test_voice_health_report_contains_complete_pipeline(tmp_path: Path) -> None:
    text = format_voice_health_report(_report(tmp_path))

    for expected in (
        "Input devices:",
        "selected/default microphone: USB Microphone",
        "selected device warning: none",
        "calibration silence: 2.0s",
        "speech sample: 5.0s",
        "calibration RMS: 0.002000",
        "average RMS: 0.030000",
        "max RMS: 0.080000",
        "noise floor: 0.002000",
        "signal-to-noise ratio: 23.50 dB",
        "clipping check: ok",
        "VAD threshold: 0.001500",
        "effective VAD threshold: 0.006000",
        "VAD crossed: yes",
        "VAD trigger time: 0.32s",
        "Wake detection test:",
        "model available: yes",
        "wake score: 0.820",
        "matched phrase: hey_jarvis",
        "decision: detected",
        "STT test:",
        "model name: base.en",
        "raw transcript: Hey Jarvis, status report",
        "transcript confidence: 0.91",
        "transcription time: 0.450s",
        "Command cleaning/repair test:",
        "clean transcript: status report",
        "repaired transcript: status report",
        "repair confidence: 1.00",
        "repair strategy: unchanged",
        "DIAGNOSIS: HEALTHY",
        "RECOMMENDED NEXT ACTION: Run the voice loop.",
    ):
        assert expected in text


def test_voice_health_cli_command(tmp_path: Path, monkeypatch, capsys) -> None:
    settings = AppSettings(_env_file=None, log_dir=tmp_path / "logs")
    report = _report(tmp_path)
    monkeypatch.setattr("main.load_settings", lambda: settings)
    monkeypatch.setattr("main.VoiceHealthCheck.run", lambda self: report)

    exit_code = main(["--voice-health-check"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Jarvis Voice Pipeline Health Check" in output
    assert "DIAGNOSIS: HEALTHY" in output
