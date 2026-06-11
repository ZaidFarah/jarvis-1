from __future__ import annotations

from pathlib import Path

from voice.wake import WakeDetectionResult
from voice.wake_diagnostics import WakeDiagnosticReport, format_wake_report


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
        model_name="base.en",
        sample_rate=16000,
        listen_seconds=5.0,
        max_rms=0.05,
        vad_threshold=0.0015,
        vad_threshold_crossed=True,
        transcription="hey jarvis",
        wake_phrase="hey jarvis",
        aliases=["hey jarvis", "hi jarvis"],
        detection=detection,
        log_file=Path("logs/wake_diagnostics.log"),
    )

    text = format_wake_report(report)

    assert "Jarvis Wake Test" in text
    assert "detected: yes" in text
    assert "matched phrase: hey jarvis" in text
    assert "score: 1.000" in text
