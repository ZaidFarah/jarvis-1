from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from config.settings import AppSettings
from voice.stt import create_speech_to_text_provider
from voice.vad import RmsVoiceActivityDetector


_STT_LOG_SINK_ID: int | None = None


@dataclass(frozen=True)
class TranscriptionDiagnosticReport:
    provider_name: str
    provider_available: bool
    model_name: str
    device: str
    compute_type: str
    sample_rate: int
    record_seconds: float
    max_rms: float
    vad_threshold: float
    vad_threshold_crossed: bool
    transcription: str
    log_file: Path
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        return self.provider_available and not self.errors


class TranscriptionDiagnostics:
    """One-shot microphone recording and Faster Whisper transcription test."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.log_file = self.settings.log_dir / "stt_diagnostics.log"
        self.stt_logger = logger.bind(stt_diagnostics=True)
        self._ensure_stt_log_sink()

    def run_transcribe_test(self) -> TranscriptionDiagnosticReport:
        provider = create_speech_to_text_provider(self.settings)
        errors: list[str] = []
        samples: list[float] = []
        max_rms = 0.0
        vad_crossed = False

        self.stt_logger.info(
            "Running STT diagnostic provider={} model={} device={} compute_type={}",
            provider.name,
            self.settings.stt_model_name,
            self.settings.whisper_device,
            self.settings.whisper_compute_type,
        )

        if not provider.available:
            message = f"STT provider '{provider.name}' is not available. Check provider configuration and dependencies."
            self.stt_logger.error(message)
            errors.append(message)
            return self._report(provider.name, provider.available, max_rms, vad_crossed, "", errors)

        try:
            samples = self._record_microphone()
            max_rms = self._calculate_max_rms(samples, self.settings.voice_sample_rate)
            vad = RmsVoiceActivityDetector(self.settings.voice_vad_threshold)
            vad_crossed = vad.analyze([max_rms], self.settings.voice_sample_rate).is_speech
            self.stt_logger.info(
                "Recorded audio samples={} max_rms={} threshold={} crossed={}",
                len(samples),
                f"{max_rms:.6f}",
                self.settings.voice_vad_threshold,
                vad_crossed,
            )
        except Exception as exc:
            message = f"Microphone recording failed: {type(exc).__name__}: {exc}"
            self.stt_logger.exception(message)
            errors.append(message)
            return self._report(provider.name, provider.available, max_rms, vad_crossed, "", errors)

        try:
            result = provider.transcribe(samples, self.settings.voice_sample_rate)
            text = result.text.strip()
            self.stt_logger.info("Transcription result text={}", text or "<empty>")
            return self._report(provider.name, provider.available, max_rms, vad_crossed, text, errors)
        except Exception as exc:
            message = f"Transcription failed: {type(exc).__name__}: {exc}"
            self.stt_logger.exception(message)
            errors.append(message)
            return self._report(provider.name, provider.available, max_rms, vad_crossed, "", errors)

    def _report(
        self,
        provider_name: str,
        provider_available: bool,
        max_rms: float,
        vad_crossed: bool,
        transcription: str,
        errors: list[str],
    ) -> TranscriptionDiagnosticReport:
        return TranscriptionDiagnosticReport(
            provider_name=provider_name,
            provider_available=provider_available,
            model_name=self.settings.stt_model_name,
            device=self.settings.whisper_device,
            compute_type=self.settings.whisper_compute_type,
            sample_rate=self.settings.voice_sample_rate,
            record_seconds=self.settings.voice_record_seconds,
            max_rms=max_rms,
            vad_threshold=self.settings.voice_vad_threshold,
            vad_threshold_crossed=vad_crossed,
            transcription=transcription,
            log_file=self.log_file,
            errors=errors,
        )

    def _record_microphone(self) -> list[float]:
        sd = self._require_sounddevice()
        sample_rate = self.settings.voice_sample_rate
        channels = self.settings.voice_channels
        frames = int(sample_rate * self.settings.voice_record_seconds)

        sd.check_input_settings(samplerate=sample_rate, channels=channels)
        recording = sd.rec(frames, samplerate=sample_rate, channels=channels, dtype="float32")
        sd.wait()
        return self._flatten_samples(recording)

    @staticmethod
    def _require_sounddevice() -> Any:
        try:
            return importlib.import_module("sounddevice")
        except Exception as exc:
            raise RuntimeError(f"sounddevice is required for transcribe-test: {exc}") from exc

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

    def _ensure_stt_log_sink(self) -> None:
        global _STT_LOG_SINK_ID
        if _STT_LOG_SINK_ID is not None:
            return

        self.settings.log_dir.mkdir(parents=True, exist_ok=True)
        _STT_LOG_SINK_ID = logger.add(
            self.log_file,
            level="DEBUG",
            rotation="1 MB",
            retention="7 days",
            encoding="utf-8",
            backtrace=False,
            diagnose=False,
            filter=lambda record: bool(record["extra"].get("stt_diagnostics")),
        )


def format_transcription_report(report: TranscriptionDiagnosticReport) -> str:
    lines = [
        "Jarvis Transcription Test",
        "=========================",
        f"provider: {report.provider_name}",
        f"provider available: {_yes_no(report.provider_available)}",
        f"model: {report.model_name}",
        f"device: {report.device}",
        f"compute type: {report.compute_type}",
        f"diagnostic log: {report.log_file}",
        "",
        "Recording:",
        f"  sample rate: {report.sample_rate}",
        f"  duration: {report.record_seconds:.2f}s",
        f"  max RMS level: {report.max_rms:.6f}",
        f"  VAD threshold: {report.vad_threshold:.6f}",
        f"  VAD threshold crossed: {_yes_no(report.vad_threshold_crossed)}",
        "",
        "Transcription:",
        f"  {report.transcription if report.transcription else '<no text detected>'}",
    ]

    if report.errors:
        lines.append("")
        lines.append("Errors:")
        lines.extend(f"  - {error}" for error in report.errors)

    return "\n".join(lines)


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
