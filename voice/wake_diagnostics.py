from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from config.settings import AppSettings
from voice.stt import create_speech_to_text_provider
from voice.vad import RmsVoiceActivityDetector
from voice.wake import WakeDetectionResult, WakeDetector


_WAKE_LOG_SINK_ID: int | None = None


@dataclass(frozen=True)
class WakeDiagnosticReport:
    provider_name: str
    provider_available: bool
    model_name: str
    sample_rate: int
    listen_seconds: float
    max_rms: float
    vad_threshold: float
    vad_threshold_crossed: bool
    transcription: str
    wake_phrase: str
    aliases: list[str]
    detection: WakeDetectionResult
    log_file: Path
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
        provider = create_speech_to_text_provider(self.settings)
        detector = WakeDetector(
            wake_phrase=self.settings.wake_phrase,
            aliases=self.settings.wake_alias_list,
            threshold=self.settings.wake_match_threshold,
        )
        errors: list[str] = []
        max_rms = 0.0
        vad_crossed = False
        transcription = ""

        self.wake_logger.info(
            "Running wake diagnostic phrase={} aliases={} threshold={}",
            self.settings.wake_phrase,
            self.settings.wake_alias_list,
            self.settings.wake_match_threshold,
        )

        if not provider.available:
            message = "Faster Whisper is not available. Wake test requires transcription first."
            self.wake_logger.error(message)
            errors.append(message)
            detection = detector.detect("")
            return self._report(provider.name, provider.available, max_rms, vad_crossed, transcription, detection, errors)

        try:
            samples = self._record_microphone()
            max_rms = self._calculate_max_rms(samples, self.settings.voice_sample_rate)
            vad = RmsVoiceActivityDetector(self.settings.voice_vad_threshold)
            vad_crossed = vad.analyze([max_rms], self.settings.voice_sample_rate).is_speech
            self.wake_logger.info(
                "Recorded wake test audio samples={} max_rms={} threshold={} crossed={}",
                len(samples),
                f"{max_rms:.6f}",
                self.settings.voice_vad_threshold,
                vad_crossed,
            )
        except Exception as exc:
            message = f"Microphone recording failed: {type(exc).__name__}: {exc}"
            self.wake_logger.exception(message)
            errors.append(message)
            detection = detector.detect("")
            return self._report(provider.name, provider.available, max_rms, vad_crossed, transcription, detection, errors)

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
            return self._report(provider.name, provider.available, max_rms, vad_crossed, transcription, detection, errors)
        except Exception as exc:
            message = f"Wake transcription failed: {type(exc).__name__}: {exc}"
            self.wake_logger.exception(message)
            errors.append(message)
            detection = detector.detect(transcription)
            return self._report(provider.name, provider.available, max_rms, vad_crossed, transcription, detection, errors)

    def _report(
        self,
        provider_name: str,
        provider_available: bool,
        max_rms: float,
        vad_crossed: bool,
        transcription: str,
        detection: WakeDetectionResult,
        errors: list[str],
    ) -> WakeDiagnosticReport:
        return WakeDiagnosticReport(
            provider_name=provider_name,
            provider_available=provider_available,
            model_name=self.settings.whisper_model,
            sample_rate=self.settings.voice_sample_rate,
            listen_seconds=self.settings.wake_listen_seconds,
            max_rms=max_rms,
            vad_threshold=self.settings.voice_vad_threshold,
            vad_threshold_crossed=vad_crossed,
            transcription=transcription,
            wake_phrase=self.settings.wake_phrase,
            aliases=self.settings.wake_alias_list,
            detection=detection,
            log_file=self.log_file,
            errors=errors,
        )

    def _record_microphone(self) -> list[float]:
        sd = self._require_sounddevice()
        sample_rate = self.settings.voice_sample_rate
        channels = self.settings.voice_channels
        frames = int(sample_rate * self.settings.wake_listen_seconds)

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

    @classmethod
    def _calculate_max_rms(cls, samples: list[float], sample_rate: int) -> float:
        if not samples:
            return 0.0

        window_size = max(1, int(sample_rate * 0.1))
        max_rms = 0.0
        for start in range(0, len(samples), window_size):
            window = samples[start : start + window_size]
            rms = (sum(sample * sample for sample in window) / len(window)) ** 0.5
            max_rms = max(max_rms, rms)
        return max_rms

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


def format_wake_report(report: WakeDiagnosticReport) -> str:
    detection = report.detection
    lines = [
        "Jarvis Wake Test",
        "================",
        f"provider: {report.provider_name}",
        f"provider available: {_yes_no(report.provider_available)}",
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
        f"  VAD threshold: {report.vad_threshold:.6f}",
        f"  VAD threshold crossed: {_yes_no(report.vad_threshold_crossed)}",
        "",
        "Transcription:",
        f"  {report.transcription if report.transcription else '<no text detected>'}",
        "",
        "Wake detection:",
        f"  detected: {_yes_no(detection.detected)}",
        f"  match type: {detection.match_type}",
        f"  matched phrase: {detection.matched_phrase if detection.detected else '<none>'}",
        f"  score: {detection.score:.3f}",
    ]

    if report.errors:
        lines.append("")
        lines.append("Errors:")
        lines.extend(f"  - {error}" for error in report.errors)

    return "\n".join(lines)


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
