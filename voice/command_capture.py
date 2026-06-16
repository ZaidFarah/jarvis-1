from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from math import sqrt
from pathlib import Path
from typing import Any

from loguru import logger

from config.settings import AppSettings
from services.logging_service import add_managed_file_sink
from voice.command_validation import CommandValidationResult, validate_cleaned_command
from voice.speech_repair import SpeechRepairResult, SpeechRepairer
from voice.stt import create_speech_to_text_provider
from voice.vad import RmsVoiceActivityDetector
from voice.wake import clean_command_text


@dataclass(frozen=True)
class AudioCaptureMetrics:
    average_rms: float
    max_rms: float
    vad_threshold: float
    vad_threshold_crossed: bool


@dataclass(frozen=True)
class CommandCaptureReport:
    provider_name: str
    provider_available: bool
    sample_rate: int
    record_seconds: float
    average_rms: float
    max_rms: float
    vad_threshold: float
    vad_threshold_crossed: bool
    raw_transcript: str
    cleaned_command: str
    validation: CommandValidationResult
    log_file: Path
    speech_repair: SpeechRepairResult | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def accepted(self) -> bool:
        return self.validation.accepted

    @property
    def rejection_reason(self) -> str | None:
        return self.validation.rejection_reason

    @property
    def is_successful(self) -> bool:
        return self.provider_available and not self.errors


class CommandCaptureDiagnosticRunner:
    """Record and transcribe one command clip without requiring wake detection."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        provider: Any | None = None,
        sounddevice_module: Any | None = None,
    ) -> None:
        self.settings = settings
        self.provider = provider or create_speech_to_text_provider(settings)
        self.sounddevice_module = sounddevice_module
        self.log_file = self.settings.log_dir / "command_capture.log"
        self.capture_logger = logger.bind(command_capture=True)
        self.speech_repairer = SpeechRepairer(settings)
        self._ensure_log_sink()

    def run(self) -> CommandCaptureReport:
        errors: list[str] = []
        samples: list[float] = []
        average_rms = 0.0
        max_rms = 0.0
        vad_crossed = False
        raw_transcript = ""
        cleaned_command = ""
        speech_repair: SpeechRepairResult | None = None
        validation = validate_cleaned_command(
            cleaned_command,
            min_words=self.settings.voice_command_min_words,
            reject_phrases=self.settings.voice_command_reject_phrase_list,
            incomplete_phrases=self.settings.voice_command_incomplete_phrase_list,
        )

        self.capture_logger.info(
            "Running command capture diagnostic provider={} sample_rate={} record_seconds={}",
            self.provider.name,
            self.settings.voice_sample_rate,
            self.settings.voice_command_record_seconds,
        )

        if not self.provider.available:
            message = "Speech-to-text provider is not available. Command capture test cannot run."
            self.capture_logger.error(message)
            errors.append(message)
            return self._report(
                average_rms,
                max_rms,
                vad_crossed,
                raw_transcript,
                cleaned_command,
                speech_repair,
                validation,
                errors,
            )

        try:
            samples = self._record_microphone()
            metrics = calculate_audio_capture_metrics(
                samples,
                self.settings.voice_sample_rate,
                self.settings.voice_vad_threshold,
            )
            average_rms = metrics.average_rms
            max_rms = metrics.max_rms
            vad_crossed = metrics.vad_threshold_crossed
            self.capture_logger.info(
                "Recorded command sample samples={} average_rms={} max_rms={} threshold={} crossed={}",
                len(samples),
                f"{average_rms:.6f}",
                f"{max_rms:.6f}",
                metrics.vad_threshold,
                vad_crossed,
            )
        except Exception as exc:
            message = f"Microphone recording failed: {type(exc).__name__}: {exc}"
            self.capture_logger.exception(message)
            errors.append(message)
            return self._report(
                average_rms,
                max_rms,
                vad_crossed,
                raw_transcript,
                cleaned_command,
                speech_repair,
                validation,
                errors,
            )

        try:
            raw_transcript = self.provider.transcribe(samples, self.settings.voice_sample_rate).text.strip()
            cleaned_transcript = clean_command_text(raw_transcript)
            speech_repair = self.speech_repairer.repair(cleaned_transcript, raw_transcript=raw_transcript)
            cleaned_command = speech_repair.repaired_transcript
            validation = validate_cleaned_command(
                cleaned_command,
                min_words=self.settings.voice_command_min_words,
                reject_phrases=self.settings.voice_command_reject_phrase_list,
                incomplete_phrases=self.settings.voice_command_incomplete_phrase_list,
            )
            self.capture_logger.info(
                "Command capture transcription={} cleaned={} repaired={} confidence={} strategy={} accepted={} reason={}",
                raw_transcript or "<empty>",
                speech_repair.cleaned_transcript or "<empty>",
                cleaned_command or "<empty>",
                f"{speech_repair.confidence:.2f}",
                speech_repair.strategy,
                validation.accepted,
                validation.rejection_reason or "<none>",
            )
        except Exception as exc:
            message = f"Transcription failed: {type(exc).__name__}: {exc}"
            self.capture_logger.exception(message)
            errors.append(message)

        return self._report(
            average_rms,
            max_rms,
            vad_crossed,
            raw_transcript,
            cleaned_command,
            speech_repair,
            validation,
            errors,
        )

    def _report(
        self,
        average_rms: float,
        max_rms: float,
        vad_crossed: bool,
        raw_transcript: str,
        cleaned_command: str,
        speech_repair: SpeechRepairResult | None,
        validation: CommandValidationResult,
        errors: list[str],
    ) -> CommandCaptureReport:
        return CommandCaptureReport(
            provider_name=self.provider.name,
            provider_available=bool(self.provider.available),
            sample_rate=self.settings.voice_sample_rate,
            record_seconds=self.settings.voice_command_record_seconds,
            average_rms=average_rms,
            max_rms=max_rms,
            vad_threshold=self.settings.voice_vad_threshold,
            vad_threshold_crossed=vad_crossed,
            raw_transcript=raw_transcript,
            cleaned_command=cleaned_command,
            speech_repair=speech_repair,
            validation=validation,
            log_file=self.log_file,
            errors=errors,
        )

    def _record_microphone(self) -> list[float]:
        sd = self.sounddevice_module or self._require_sounddevice()
        sample_rate = self.settings.voice_sample_rate
        channels = self.settings.voice_channels
        frames = int(sample_rate * self.settings.voice_command_record_seconds)

        sd.check_input_settings(samplerate=sample_rate, channels=channels)
        recording = sd.rec(frames, samplerate=sample_rate, channels=channels, dtype="float32")
        sd.wait()
        return self._flatten_samples(recording)

    @staticmethod
    def _require_sounddevice() -> Any:
        try:
            return importlib.import_module("sounddevice")
        except Exception as exc:
            raise RuntimeError(f"sounddevice is required for command-capture-test: {exc}") from exc

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

    @staticmethod
    def _calculate_rms(samples: list[float]) -> float:
        return calculate_rms(samples)

    @classmethod
    def _calculate_max_rms(cls, samples: list[float], sample_rate: int) -> float:
        del cls
        return calculate_max_rms(samples, sample_rate)

    def _ensure_log_sink(self) -> None:
        add_managed_file_sink(
            self.log_file,
            level="DEBUG",
            filter=lambda record: bool(record["extra"].get("command_capture")),
        )


def calculate_audio_capture_metrics(samples: list[float], sample_rate: int, vad_threshold: float) -> AudioCaptureMetrics:
    average_rms = calculate_rms(samples)
    max_rms = calculate_max_rms(samples, sample_rate)
    vad_result = RmsVoiceActivityDetector(vad_threshold).analyze([max_rms], sample_rate)
    return AudioCaptureMetrics(
        average_rms=average_rms,
        max_rms=max_rms,
        vad_threshold=vad_threshold,
        vad_threshold_crossed=vad_result.is_speech,
    )


def calculate_rms(samples: list[float]) -> float:
    if not samples:
        return 0.0
    return sqrt(sum(sample * sample for sample in samples) / len(samples))


def calculate_max_rms(samples: list[float], sample_rate: int) -> float:
    if not samples:
        return 0.0

    window_size = max(1, int(sample_rate * 0.1))
    max_rms = 0.0
    for start in range(0, len(samples), window_size):
        window = samples[start : start + window_size]
        max_rms = max(max_rms, calculate_rms(window))
    return max_rms


def run_command_capture_test(settings: AppSettings | None = None) -> CommandCaptureReport:
    settings = settings or AppSettings(_env_file=None)
    return CommandCaptureDiagnosticRunner(settings).run()


def format_command_capture_report(report: CommandCaptureReport) -> str:
    lines = [
        "Jarvis Command Capture Test",
        "===========================",
        f"provider: {report.provider_name}",
        f"provider available: {_yes_no(report.provider_available)}",
        f"sample rate: {report.sample_rate}",
        f"record seconds: {report.record_seconds:.2f}",
        f"average RMS: {report.average_rms:.6f}",
        f"max RMS: {report.max_rms:.6f}",
        f"VAD threshold: {report.vad_threshold:.6f}",
        f"VAD threshold crossed: {_yes_no(report.vad_threshold_crossed)}",
        f"raw transcript: {report.raw_transcript if report.raw_transcript else '<no text detected>'}",
        f"cleaned command: {report.cleaned_command if report.cleaned_command else '<empty>'}",
        f"accepted: {_yes_no(report.accepted)}",
    ]
    if report.speech_repair is not None:
        lines.extend(
            [
                f"repaired transcript: {report.speech_repair.repaired_transcript if report.speech_repair.repaired_transcript else '<empty>'}",
                f"repair confidence: {report.speech_repair.confidence:.2f}",
                f"repair strategy: {report.speech_repair.strategy}",
                f"repair reason: {report.speech_repair.repair_reason}",
            ]
        )
    if report.rejection_reason:
        lines.append(f"rejection reason: {report.rejection_reason}")
    lines.append(f"diagnostic log: {report.log_file}")

    if report.errors:
        lines.append("")
        lines.append("Errors:")
        lines.extend(f"  - {error}" for error in report.errors)

    return "\n".join(lines)


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
