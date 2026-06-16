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
from voice.wake import WakeDetector, remove_wake_phrase_prefix


@dataclass(frozen=True)
class AudioCaptureMetrics:
    average_rms: float
    max_rms: float
    vad_threshold: float
    vad_threshold_crossed: bool
    noise_floor: float = 0.0
    effective_vad_threshold: float = 0.0
    vad_trigger_index: int | None = None
    vad_trigger_seconds: float | None = None
    speech_window_ratio: float = 0.0
    window_ms: int = 80


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
    noise_floor: float = 0.0
    effective_vad_threshold: float = 0.0
    vad_trigger_seconds: float | None = None
    transcript_confidence: float | None = None
    cleaned_transcript: str = ""
    wake_score: float = 0.0
    command_score: float = 0.0

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
        noise_floor = 0.0
        effective_vad_threshold = 0.0
        vad_trigger_seconds: float | None = None
        transcript_confidence: float | None = None
        raw_transcript = ""
        cleaned_transcript = ""
        cleaned_command = ""
        wake_score = 0.0
        command_score = 0.0
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
                cleaned_transcript,
                speech_repair,
                validation,
                transcript_confidence,
                noise_floor,
                effective_vad_threshold,
                vad_trigger_seconds,
                wake_score,
                command_score,
                errors,
            )

        try:
            samples = self._record_microphone()
            metrics = calculate_audio_capture_metrics(
                samples,
                self.settings.voice_sample_rate,
                self.settings.voice_vad_threshold,
                vad_window_ms=self.settings.voice_vad_window_ms,
                noise_multiplier=self.settings.voice_vad_noise_multiplier,
            )
            average_rms = metrics.average_rms
            max_rms = metrics.max_rms
            vad_crossed = metrics.vad_threshold_crossed
            noise_floor = metrics.noise_floor
            effective_vad_threshold = metrics.effective_vad_threshold
            vad_trigger_seconds = metrics.vad_trigger_seconds
            self.capture_logger.info(
                "Recorded command sample samples={} average_rms={} max_rms={} noise_floor={} threshold={} "
                "effective_threshold={} trigger_seconds={} crossed={}",
                len(samples),
                f"{average_rms:.6f}",
                f"{max_rms:.6f}",
                f"{noise_floor:.6f}",
                metrics.vad_threshold,
                f"{effective_vad_threshold:.6f}",
                _format_seconds(vad_trigger_seconds),
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
                cleaned_transcript,
                speech_repair,
                validation,
                transcript_confidence,
                noise_floor,
                effective_vad_threshold,
                vad_trigger_seconds,
                wake_score,
                command_score,
                errors,
            )

        try:
            transcription = self.provider.transcribe(samples, self.settings.voice_sample_rate)
            raw_transcript = transcription.text.strip()
            transcript_confidence = getattr(transcription, "confidence", None)
            cleaned_transcript = remove_wake_phrase_prefix(
                raw_transcript,
                wake_phrase=self.settings.wake_phrase,
                aliases=self.settings.wake_alias_list,
            )
            wake_detection = WakeDetector(
                wake_phrase=self.settings.wake_phrase,
                aliases=self.settings.wake_alias_list,
                threshold=self.settings.wake_match_threshold,
            ).detect(raw_transcript)
            wake_score = wake_detection.score
            speech_repair = self.speech_repairer.repair(cleaned_transcript, raw_transcript=raw_transcript)
            cleaned_command = speech_repair.repaired_transcript
            validation = validate_cleaned_command(
                cleaned_command,
                min_words=self.settings.voice_command_min_words,
                reject_phrases=self.settings.voice_command_reject_phrase_list,
                incomplete_phrases=self.settings.voice_command_incomplete_phrase_list,
            )
            command_score = calculate_command_confidence(
                cleaned_command,
                validation,
                speech_repair=speech_repair,
                transcript_confidence=transcript_confidence,
            )
            self.capture_logger.info(
                "Command capture transcription={} transcript_confidence={} cleaned={} repaired={} confidence={} "
                "strategy={} wake_score={} command_score={} accepted={} reason={}",
                raw_transcript or "<empty>",
                _format_optional_float(transcript_confidence),
                speech_repair.cleaned_transcript or "<empty>",
                cleaned_command or "<empty>",
                f"{speech_repair.confidence:.2f}",
                speech_repair.strategy,
                f"{wake_score:.3f}",
                f"{command_score:.2f}",
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
            cleaned_transcript,
            speech_repair,
            validation,
            transcript_confidence,
            noise_floor,
            effective_vad_threshold,
            vad_trigger_seconds,
            wake_score,
            command_score,
            errors,
        )

    def _report(
        self,
        average_rms: float,
        max_rms: float,
        vad_crossed: bool,
        raw_transcript: str,
        cleaned_command: str,
        cleaned_transcript: str,
        speech_repair: SpeechRepairResult | None,
        validation: CommandValidationResult,
        transcript_confidence: float | None,
        noise_floor: float,
        effective_vad_threshold: float,
        vad_trigger_seconds: float | None,
        wake_score: float,
        command_score: float,
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
            noise_floor=noise_floor,
            effective_vad_threshold=effective_vad_threshold,
            vad_trigger_seconds=vad_trigger_seconds,
            transcript_confidence=transcript_confidence,
            cleaned_transcript=cleaned_transcript,
            wake_score=wake_score,
            command_score=command_score,
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


def calculate_audio_capture_metrics(
    samples: list[float],
    sample_rate: int,
    vad_threshold: float,
    *,
    vad_window_ms: int = 80,
    noise_multiplier: float = 3.0,
) -> AudioCaptureMetrics:
    average_rms = calculate_rms(samples)
    window_rms = calculate_window_rms(samples, sample_rate, vad_window_ms=vad_window_ms)
    max_rms = max(window_rms) if window_rms else 0.0
    noise_floor = estimate_noise_floor(window_rms)
    effective_threshold = calculate_effective_vad_threshold(
        vad_threshold,
        noise_floor,
        noise_multiplier=noise_multiplier,
    )
    vad_result = RmsVoiceActivityDetector(effective_threshold).analyze([max_rms], sample_rate)
    trigger_index = _first_trigger_index(window_rms, effective_threshold)
    trigger_seconds = None
    if trigger_index is not None:
        trigger_seconds = (trigger_index * max(1, int(sample_rate * vad_window_ms / 1000.0))) / sample_rate
    speech_windows = sum(1 for rms in window_rms if rms >= effective_threshold)
    speech_window_ratio = speech_windows / len(window_rms) if window_rms else 0.0
    return AudioCaptureMetrics(
        average_rms=average_rms,
        max_rms=max_rms,
        vad_threshold=vad_threshold,
        vad_threshold_crossed=vad_result.is_speech,
        noise_floor=noise_floor,
        effective_vad_threshold=effective_threshold,
        vad_trigger_index=trigger_index,
        vad_trigger_seconds=trigger_seconds,
        speech_window_ratio=speech_window_ratio,
        window_ms=vad_window_ms,
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


def calculate_window_rms(samples: list[float], sample_rate: int, *, vad_window_ms: int = 80) -> list[float]:
    if not samples:
        return []

    window_size = max(1, int(sample_rate * max(vad_window_ms, 1) / 1000.0))
    return [calculate_rms(samples[start : start + window_size]) for start in range(0, len(samples), window_size)]


def estimate_noise_floor(window_rms: list[float]) -> float:
    if len(window_rms) < 3:
        return 0.0

    sorted_rms = sorted(max(0.0, value) for value in window_rms)
    percentile_index = int((len(sorted_rms) - 1) * 0.2)
    return sorted_rms[percentile_index]


def calculate_effective_vad_threshold(
    vad_threshold: float,
    noise_floor: float,
    *,
    noise_multiplier: float = 3.0,
) -> float:
    base_threshold = max(0.0, vad_threshold)
    floor = max(0.0, noise_floor)
    multiplier = max(1.0, noise_multiplier)
    minimum_threshold = 0.0002

    if base_threshold <= 0.0:
        return max(minimum_threshold, floor * multiplier)

    if floor >= base_threshold * 0.6:
        return min(1.0, max(base_threshold, floor * max(2.0, multiplier * 0.85)))

    quiet_room_threshold = max(minimum_threshold, base_threshold * 0.55, floor * multiplier)
    return min(base_threshold, quiet_room_threshold)


def calculate_command_confidence(
    cleaned_command: str,
    validation: CommandValidationResult,
    *,
    speech_repair: SpeechRepairResult | None = None,
    transcript_confidence: float | None = None,
) -> float:
    normalized = " ".join(cleaned_command.strip().split())
    if not normalized:
        return 0.0

    repair_confidence = speech_repair.confidence if speech_repair is not None else 1.0
    score = max(0.0, min(1.0, repair_confidence))
    if transcript_confidence is not None:
        score *= max(0.35, min(1.0, transcript_confidence))

    word_count = len(normalized.split())
    if validation.accepted:
        length_factor = min(1.0, 0.65 + (word_count * 0.12))
        return round(max(0.50, min(1.0, score * length_factor)), 2)

    short_penalty = 0.30 if word_count <= 1 else 0.45
    return round(min(0.49, score * short_penalty), 2)


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
        f"noise floor: {report.noise_floor:.6f}",
        f"VAD threshold: {report.vad_threshold:.6f}",
        f"effective VAD threshold: {report.effective_vad_threshold:.6f}",
        f"VAD threshold crossed: {_yes_no(report.vad_threshold_crossed)}",
        f"VAD trigger point: {_format_seconds(report.vad_trigger_seconds)}",
        f"raw transcript: {report.raw_transcript if report.raw_transcript else '<no text detected>'}",
        f"transcript confidence: {_format_optional_float(report.transcript_confidence)}",
        f"clean transcript: {report.cleaned_transcript if report.cleaned_transcript else '<empty>'}",
        f"cleaned command: {report.cleaned_command if report.cleaned_command else '<empty>'}",
        f"wake score: {report.wake_score:.3f}",
        f"command score: {report.command_score:.2f}",
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


def _first_trigger_index(window_rms: list[float], threshold: float) -> int | None:
    for index, rms in enumerate(window_rms):
        if rms >= threshold:
            return index
    return None


def _format_seconds(value: float | None) -> str:
    if value is None:
        return "<none>"
    return f"{value:.2f}s"


def _format_optional_float(value: float | None) -> str:
    if value is None:
        return "<unknown>"
    return f"{value:.2f}"
