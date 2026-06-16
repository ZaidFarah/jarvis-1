from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from config.settings import AppSettings
from voice.command_capture import calculate_audio_capture_metrics
from voice.stt import create_speech_to_text_provider
from voice.vad import RmsVoiceActivityDetector
from voice.wake import WakeDetectionResult, WakeDetector
from voice.wake_provider import resolve_wake_provider


_WAKE_LOG_SINK_ID: int | None = None


@dataclass(frozen=True)
class WakeDiagnosticReport:
    provider_name: str
    provider_available: bool
    wake_provider: str
    model_name: str
    sample_rate: int
    listen_seconds: float
    max_rms: float
    noise_floor: float = 0.0
    effective_vad_threshold: float = 0.0
    vad_trigger_seconds: float | None = None
    vad_threshold: float = 0.0
    vad_threshold_crossed: bool = False
    transcription: str = ""
    matched_alias: str | None = None
    decision: str = "rejected"
    score: float = 0.0
    wake_phrase: str = ""
    aliases: list[str] = field(default_factory=list)
    detection: WakeDetectionResult = field(
        default_factory=lambda: WakeDetectionResult(
            detected=False,
            transcript="",
            matched_phrase=None,
            score=0.0,
            threshold=0.0,
            match_type="none",
        )
    )
    log_file: Path = Path(".")
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        return self.provider_available and not self.errors


class WakeDiagnostics:
    """One-shot wake phrase test. This is not a continuous listener."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.log_file = self.settings.log_dir / "wake_diagnostics.log"
        self.wake_logger = logger.bind(wake_diagnostics=True)
        self._ensure_wake_log_sink()

    def run_wake_test(self) -> WakeDiagnosticReport:
        return self._run_once(
            wake_phrase=self.settings.wake_phrase,
            aliases=self.settings.wake_alias_list,
            listen_seconds=self.settings.wake_listen_seconds,
        )

    def run_wake_jarvis_test(self, repeat_count: int = 3) -> "WakeJarvisTestReport":
        reports: list[WakeDiagnosticReport] = []
        errors: list[str] = []
        for _ in range(max(1, repeat_count)):
            report = self._run_once(
                wake_phrase="jarvis",
                aliases=["jarvis"],
                listen_seconds=max(1.0, min(self.settings.wake_listen_seconds, 1.5)),
            )
            reports.append(report)
            errors.extend(report.errors)

        return WakeJarvisTestReport(
            attempts=len(reports),
            detections=sum(1 for report in reports if report.detection.detected),
            reports=reports,
            log_file=self.log_file,
            errors=errors,
        )

    def _run_once(self, wake_phrase: str, aliases: list[str], listen_seconds: float) -> WakeDiagnosticReport:
        provider = create_speech_to_text_provider(self.settings)
        detector = WakeDetector(
            wake_phrase=wake_phrase,
            aliases=aliases,
            threshold=self.settings.wake_match_threshold,
        )
        errors: list[str] = []
        max_rms = 0.0
        noise_floor = 0.0
        effective_vad_threshold = 0.0
        vad_trigger_seconds: float | None = None
        vad_crossed = False
        transcription = ""
        wake_provider = resolve_wake_provider(self.settings).effective_provider

        self.wake_logger.info(
            "Running wake diagnostic phrase={} aliases={} threshold={}",
            wake_phrase,
            aliases,
            self.settings.wake_match_threshold,
        )

        if not provider.available:
            message = "Faster Whisper is not available. Wake test requires transcription first."
            self.wake_logger.error(message)
            errors.append(message)
            detection = detector.detect("")
            return self._report(
                provider.name,
                provider.available,
                wake_provider,
                listen_seconds,
                max_rms,
                noise_floor,
                effective_vad_threshold,
                vad_trigger_seconds,
                vad_crossed,
                transcription,
                detection,
                errors,
            )

        try:
            samples = self._record_microphone(listen_seconds)
            metrics = calculate_audio_capture_metrics(
                samples,
                self.settings.voice_sample_rate,
                self.settings.voice_vad_threshold,
                vad_window_ms=self.settings.voice_vad_window_ms,
                noise_multiplier=self.settings.voice_vad_noise_multiplier,
            )
            max_rms = metrics.max_rms
            noise_floor = metrics.noise_floor
            effective_vad_threshold = metrics.effective_vad_threshold
            vad_trigger_seconds = metrics.vad_trigger_seconds
            vad_crossed = metrics.vad_threshold_crossed
            self.wake_logger.info(
                "Recorded wake test audio samples={} max_rms={} noise_floor={} threshold={} effective_threshold={} "
                "trigger_seconds={} crossed={}",
                len(samples),
                f"{max_rms:.6f}",
                f"{noise_floor:.6f}",
                self.settings.voice_vad_threshold,
                f"{effective_vad_threshold:.6f}",
                _format_seconds(vad_trigger_seconds),
                vad_crossed,
            )
        except Exception as exc:
            message = f"Microphone recording failed: {type(exc).__name__}: {exc}"
            self.wake_logger.exception(message)
            errors.append(message)
            detection = detector.detect("")
            return self._report(
                provider.name,
                provider.available,
                wake_provider,
                listen_seconds,
                max_rms,
                noise_floor,
                effective_vad_threshold,
                vad_trigger_seconds,
                vad_crossed,
                transcription,
                detection,
                errors,
            )

        try:
            result = provider.transcribe(samples, self.settings.voice_sample_rate)
            transcription = result.text.strip()
            detection = detector.detect(transcription)
            self.wake_logger.info(
                "Wake test transcription={} detected={} matched={} score={}",
                transcription or "<empty>",
                detection.detected,
                detection.matched_phrase,
                f"{detection.score:.3f}",
            )
            return self._report(
                provider.name,
                provider.available,
                wake_provider,
                listen_seconds,
                max_rms,
                noise_floor,
                effective_vad_threshold,
                vad_trigger_seconds,
                vad_crossed,
                transcription,
                detection,
                errors,
            )
        except Exception as exc:
            message = f"Wake transcription failed: {type(exc).__name__}: {exc}"
            self.wake_logger.exception(message)
            errors.append(message)
            detection = detector.detect(transcription)
            return self._report(
                provider.name,
                provider.available,
                wake_provider,
                listen_seconds,
                max_rms,
                noise_floor,
                effective_vad_threshold,
                vad_trigger_seconds,
                vad_crossed,
                transcription,
                detection,
                errors,
            )

    def _report(
        self,
        provider_name: str,
        provider_available: bool,
        wake_provider: str,
        listen_seconds: float,
        max_rms: float,
        noise_floor: float,
        effective_vad_threshold: float,
        vad_trigger_seconds: float | None,
        vad_crossed: bool,
        transcription: str,
        detection: WakeDetectionResult,
        errors: list[str],
    ) -> WakeDiagnosticReport:
        return WakeDiagnosticReport(
            provider_name=provider_name,
            provider_available=provider_available,
            wake_provider=wake_provider,
            model_name=self.settings.whisper_model,
            sample_rate=self.settings.voice_sample_rate,
            listen_seconds=listen_seconds,
            max_rms=max_rms,
            noise_floor=noise_floor,
            effective_vad_threshold=effective_vad_threshold,
            vad_trigger_seconds=vad_trigger_seconds,
            vad_threshold=self.settings.voice_vad_threshold,
            vad_threshold_crossed=vad_crossed,
            transcription=transcription,
            matched_alias=detection.matched_phrase,
            decision="detected" if detection.detected else "rejected",
            score=detection.score,
            wake_phrase=self.settings.wake_phrase,
            aliases=self.settings.wake_alias_list,
            detection=detection,
            log_file=self.log_file,
            errors=errors,
        )

    def _record_microphone(self, listen_seconds: float) -> list[float]:
        sd = self._require_sounddevice()
        sample_rate = self.settings.voice_sample_rate
        channels = self.settings.voice_channels
        frames = int(sample_rate * listen_seconds)

        sd.check_input_settings(samplerate=sample_rate, channels=channels)
        recording = sd.rec(frames, samplerate=sample_rate, channels=channels, dtype="float32")
        sd.wait()
        return self._flatten_samples(recording)

    @staticmethod
    def _require_sounddevice() -> Any:
        try:
            return importlib.import_module("sounddevice")
        except Exception as exc:
            raise RuntimeError(f"sounddevice is required for wake-test: {exc}") from exc

    @staticmethod
    def _flatten_samples(recording: Any) -> list[float]:
        if hasattr(recording, "reshape"):
            return [float(value) for value in recording.reshape(-1)]

        flattened: list[float] = []
        for sample in recording:
            if isinstance(sample, (list, tuple)):
                flattened.extend(float(value) for value in sample)
            else:
                flattened.append(float(sample))
        return flattened

    def _ensure_wake_log_sink(self) -> None:
        global _WAKE_LOG_SINK_ID
        if _WAKE_LOG_SINK_ID is not None:
            return

        self.settings.log_dir.mkdir(parents=True, exist_ok=True)
        _WAKE_LOG_SINK_ID = logger.add(
            self.log_file,
            level="DEBUG",
            rotation="1 MB",
            retention="7 days",
            encoding="utf-8",
            backtrace=False,
            diagnose=False,
            filter=lambda record: bool(record["extra"].get("wake_diagnostics")),
        )


@dataclass(frozen=True)
class WakeJarvisTestReport:
    attempts: int
    detections: int
    reports: list[WakeDiagnosticReport]
    log_file: Path
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        return not self.errors and self.attempts > 0


def format_wake_report(report: WakeDiagnosticReport) -> str:
    detection = report.detection
    lines = [
        "Jarvis Wake Test",
        "================",
        f"provider: {report.provider_name}",
        f"provider available: {_yes_no(report.provider_available)}",
        f"wake provider: {report.wake_provider}",
        f"model: {report.model_name}",
        f"diagnostic log: {report.log_file}",
        "",
        "Wake settings:",
        f"  phrase: {report.wake_phrase}",
        f"  aliases: {', '.join(report.aliases)}",
        f"  threshold: {detection.threshold:.2f}",
        "",
        "Recording:",
        f"  sample rate: {report.sample_rate}",
        f"  listen seconds: {report.listen_seconds:.2f}s",
        f"  max RMS level: {report.max_rms:.6f}",
        f"  noise floor: {report.noise_floor:.6f}",
        f"  effective VAD threshold: {report.effective_vad_threshold:.6f}",
        f"  VAD trigger seconds: {_format_seconds(report.vad_trigger_seconds)}",
        f"  VAD threshold: {report.vad_threshold:.6f}",
        f"  VAD threshold crossed: {_yes_no(report.vad_threshold_crossed)}",
        "",
        "Transcription:",
        f"  {report.transcription if report.transcription else '<no text detected>'}",
        "",
        "Wake detection:",
        f"  detected: {_yes_no(detection.detected)}",
        f"  match type: {detection.match_type}",
        f"  matched alias: {report.matched_alias if report.matched_alias else '<none>'}",
        f"  score: {report.score:.3f}",
        f"  decision: {report.decision}",
    ]

    if report.errors:
        lines.append("")
        lines.append("Errors:")
        lines.extend(f"  - {error}" for error in report.errors)

    return "\n".join(lines)


def format_wake_jarvis_test_report(report: WakeJarvisTestReport) -> str:
    lines = [
        "Jarvis Wake Jarvis Test",
        "=======================",
        f"attempts: {report.attempts}",
        f"detections: {report.detections}",
        f"diagnostic log: {report.log_file}",
    ]
    for index, item in enumerate(report.reports, start=1):
        lines.extend(
            [
                "",
                f"Attempt {index}:",
                f"  provider: {item.provider_name}",
                f"  wake provider: {item.wake_provider}",
                f"  transcript: {item.transcription or '<empty>'}",
                f"  matched alias: {item.matched_alias or '<none>'}",
                f"  score: {item.score:.3f}",
                f"  decision: {item.decision}",
            ]
        )
    if report.errors:
        lines.append("")
        lines.append("Errors:")
        lines.extend(f"  - {error}" for error in report.errors)
    return "\n".join(lines)


def _format_seconds(value: float | None) -> str:
    if value is None:
        return "none"
    return f"{value:.2f}"


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
