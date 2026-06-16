from __future__ import annotations

from pathlib import Path

from config.settings import AppSettings
from main import main
from voice.wake import WakeDetectionResult
from voice.wake_diagnostics import WakeDiagnosticReport, WakeJarvisTestReport, format_wake_jarvis_test_report, format_wake_report


def test_wake_report_formats_detection_result() -> None:
    detection = WakeDetectionResult(
        detected=True,
        transcript="hey jarvis",
        matched_phrase="hey jarvis",
        score=1.0,
        threshold=0.72,
        match_type="exact",
    )
    report = WakeDiagnosticReport(
        provider_name="faster_whisper",
        provider_available=True,
        wake_provider="openwakeword",
        model_name="base.en",
        sample_rate=16000,
        listen_seconds=5.0,
        max_rms=0.05,
        noise_floor=0.01,
        effective_vad_threshold=0.03,
        vad_trigger_seconds=0.4,
        vad_threshold=0.0015,
        vad_threshold_crossed=True,
        transcription="hey jarvis",
        matched_alias="hey jarvis",
        decision="detected",
        score=1.0,
        wake_phrase="hey jarvis",
        aliases=["hey jarvis", "hi jarvis"],
        detection=detection,
        log_file=Path("logs/wake_diagnostics.log"),
    )

    text = format_wake_report(report)

    assert "Jarvis Wake Test" in text
    assert "detected: yes" in text
    assert "wake provider: openwakeword" in text
    assert "matched alias: hey jarvis" in text
    assert "score: 1.000" in text
    assert "decision: detected" in text


def test_wake_jarvis_report_formats_attempts() -> None:
    detection = WakeDetectionResult(
        detected=True,
        transcript="jarvis",
        matched_phrase="jarvis",
        score=1.0,
        threshold=0.72,
        match_type="exact",
    )
    report = WakeJarvisTestReport(
        attempts=2,
        detections=2,
        reports=[
            WakeDiagnosticReport(
                provider_name="faster_whisper",
                provider_available=True,
                wake_provider="openwakeword",
                model_name="base.en",
                sample_rate=16000,
                listen_seconds=1.5,
                max_rms=0.04,
                vad_threshold=0.0015,
                transcription="jarvis",
                matched_alias="jarvis",
                decision="detected",
                score=1.0,
                wake_phrase="jarvis",
                aliases=["jarvis"],
                detection=detection,
                log_file=Path("logs/wake_diagnostics.log"),
            )
        ],
        log_file=Path("logs/wake_diagnostics.log"),
    )

    text = format_wake_jarvis_test_report(report)

    assert "Jarvis Wake Jarvis Test" in text
    assert "attempts: 2" in text
    assert "detections: 2" in text
    assert "matched alias: jarvis" in text


def test_wake_debug_cli_commands(monkeypatch, tmp_path: Path, capsys) -> None:
    settings = AppSettings(_env_file=None, log_dir=tmp_path / "logs")
    monkeypatch.setattr("main.load_settings", lambda: settings)
    monkeypatch.setattr("voice.wake_diagnostics.WakeDiagnostics.run_wake_test", lambda self: _fake_wake_report(settings))
    monkeypatch.setattr("voice.wake_diagnostics.WakeDiagnostics.run_wake_jarvis_test", lambda self, repeat_count=3: _fake_jarvis_report(settings, repeat_count))

    exit_code = main(["--wake-debug"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Jarvis Wake Test" in output
    assert "decision:" in output

    exit_code = main(["--wake-jarvis-test", "--repeat", "2"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Jarvis Wake Jarvis Test" in output
    assert "attempts: 2" in output


def _fake_wake_report(settings: AppSettings) -> WakeDiagnosticReport:
    detection = WakeDetectionResult(
        detected=True,
        transcript="jarvis",
        matched_phrase="jarvis",
        score=1.0,
        threshold=settings.wake_match_threshold,
        match_type="exact",
    )
    return WakeDiagnosticReport(
        provider_name="faster_whisper",
        provider_available=True,
        wake_provider="openwakeword",
        model_name="base.en",
        sample_rate=settings.voice_sample_rate,
        listen_seconds=settings.wake_listen_seconds,
        max_rms=0.05,
        vad_threshold=settings.voice_vad_threshold,
        transcription="jarvis",
        matched_alias="jarvis",
        decision="detected",
        score=1.0,
        wake_phrase="jarvis",
        aliases=["jarvis"],
        detection=detection,
        log_file=settings.log_dir / "wake_diagnostics.log",
    )


def _fake_jarvis_report(settings: AppSettings, repeat_count: int) -> WakeJarvisTestReport:
    report = _fake_wake_report(settings)
    return WakeJarvisTestReport(
        attempts=repeat_count,
        detections=repeat_count,
        reports=[report for _ in range(repeat_count)],
        log_file=settings.log_dir / "wake_diagnostics.log",
    )
