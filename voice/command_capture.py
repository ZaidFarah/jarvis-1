from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from math import sqrt
from pathlib import Path
from typing import Any

from loguru import logger

from config.settings import AppSettings
from voice.command_validation import CommandValidationResult, validate_cleaned_command
from voice.stt import create_speech_to_text_provider
from voice.vad import RmsVoiceActivityDetector
from voice.wake import clean_command_text


_COMMAND_CAPTURE_LOG_SINK_ID: int | None = None
_COMMAND_CAPTURE_LOG_FILE: Path | None = None


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
        self._ensure_log_sink()

    def run(self) -> CommandCaptureReport:
        errors: list[str] = []
        samples: list[float] = []
        average_rms = 0.0
        max_rms = 0.0
        vad_crossed = False
        raw_transcript = ""
        cleaned_command = ""
        validation = validate_cleaned_command(
            cleaned_command,
            min_words=self.settings.voice_command_min_words,
            reject_phrases=self.settings.voice_command_reject_phrase_list,
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
            return self._report(average_rms, max_rms, vad_crossed, raw_transcript, cleaned_command, validation, errors)

        try:
            samples = self._record_microphone()
            average_rms = self._calculate_rms(samples)
            max_rms = self._calculate_max_rms(samples, self.settings.voice_sample_rate)
            vad_result = RmsVoiceActivityDetector(self.settings.voice_vad_threshold).analyze(
                [max_rms],
                self.settings.voice_sample_rate,
            )
            vad_crossed = vad_result.is_speech
            self.capture_logger.info(
                "Recorded command sample samples={} average_rms={} max_rms={} threshold={} crossed={}",
                len(samples),
                f"{average_rms:.6f}",
                f"{max_rms:.6f}",
                self.settings.voice_vad_threshold,
                vad_crossed,
            )
        except Exception as exc:
            message = f"Microphone recording failed: {type(exc).__name__}: {exc}"
            self.capture_logger.exception(message)
            errors.append(message)
            return self._report(average_rms, max_rms, vad_crossed, raw_transcript, cleaned_command, validation, errors)

        try:
            raw_transcript = self.provider.transcribe(samples, self.settings.voice_sample_rate).text.strip()
            cleaned_command = clean_command_text(raw_transcript)
            validation = validate_cleaned_command(
                cleaned_command,
                min_words=self.settings.voice_command_min_words,
                reject_phrases=self.settings.voice_command_reject_phrase_list,
            )
            self.capture_logger.info(
                "Command capture transcription={} cleaned={} accepted={} reason={}",
                raw_transcript or "<empty>",
                cleaned_command or "<empty>",
                validation.accepted,
                validation.rejection_reason or "<none>",
            )
        except Exception as exc:
            message = f"Transcription failed: {type(exc).__name__}: {exc}"
            self.capture_logger.exception(message)
            errors.append(message)

        return self._report(average_rms, max_rms, vad_crossed, raw_transcript, cleaned_command, validation, errors)

    def _report(
        self,
        average_rms: float,
        max_rms: float,
        vad_crossed: bool,
        raw_transcript: str,
        cleaned_command: str,
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
        if not samples:
            return 0.0
        return sqrt(sum(sample * sample for sample in samples) / len(samples))

    @classmethod
    def _calculate_max_rms(cls, samples: list[float], sample_rate: int) -> float:
        if not samples:
            return 0.0

        window_size = max(1, int(sample_rate * 0.1))
        max_rms = 0.0
        for start in range(0, len(samples), window_size):
            window = samples[start : start + window_size]
            max_rms = max(max_rms, cls._calculate_rms(window))
        return max_rms

    def _ensure_log_sink(self) -> None:
        global _COMMAND_CAPTURE_LOG_FILE, _COMMAND_CAPTURE_LOG_SINK_ID
        if _COMMAND_CAPTURE_LOG_SINK_ID is not None and _COMMAND_CAPTURE_LOG_FILE == self.log_file:
            return

        if _COMMAND_CAPTURE_LOG_SINK_ID is not None:
            try:
                logger.remove(_COMMAND_CAPTURE_LOG_SINK_ID)
            except ValueError:
                pass

        self.settings.log_dir.mkdir(parents=True, exist_ok=True)
        _COMMAND_CAPTURE_LOG_SINK_ID = logger.add(
            self.log_file,
            level="DEBUG",
            rotation="1 MB",
            retention="7 days",
            encoding="utf-8",
            backtrace=False,
            diagnose=False,
            filter=lambda record: bool(record["extra"].get("command_capture")),
        )
        _COMMAND_CAPTURE_LOG_FILE = self.log_file


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
