from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from loguru import logger

from config.settings import AppSettings
from voice.wake_provider import OpenWakeWordWakeProvider, available_openwakeword_models, is_openwakeword_installed


_OPENWAKEWORD_LOG_SINK_ID: int | None = None


@dataclass(frozen=True)
class OpenWakeWordTestReport:
    package_available: bool
    selected_model: str
    available_models: list[str]
    model_available: bool
    model_path: Path | None
    microphone_stream_opened: bool
    sample_rate: int
    chunk_ms: int
    duration_seconds: float
    chunks_processed: int
    max_score: float
    threshold: float
    detected: bool
    status: str
    message: str
    log_file: Path
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        return self.status != "FAIL"


def run_openwakeword_test(
    settings: AppSettings | None = None,
    *,
    sounddevice_module: Any | None = None,
    provider_factory: Callable[[AppSettings], OpenWakeWordWakeProvider] | None = None,
) -> OpenWakeWordTestReport:
    settings = settings or AppSettings(_env_file=None)
    provider_factory = provider_factory or OpenWakeWordWakeProvider
    log_file = settings.log_dir / "openwakeword.log"
    logger.bind(openwakeword_test=True)
    _ensure_log_sink(settings, log_file)

    package_available = is_openwakeword_installed()
    available_models = available_openwakeword_models()
    selected_model = settings.openwakeword_model.strip() or "hey_jarvis"
    model_available = selected_model in available_models or Path(selected_model).exists()
    notes: list[str] = []
    errors: list[str] = []

    if not package_available:
        message = "OpenWakeWord package is not installed."
        notes.append("Install openwakeword and rerun the diagnostic.")
        return OpenWakeWordTestReport(
            package_available=False,
            selected_model=selected_model,
            available_models=available_models,
            model_available=False,
            model_path=None,
            microphone_stream_opened=False,
            sample_rate=settings.voice_sample_rate,
            chunk_ms=settings.openwakeword_listen_chunk_ms,
            duration_seconds=settings.openwakeword_test_seconds,
            chunks_processed=0,
            max_score=0.0,
            threshold=settings.openwakeword_threshold,
            detected=False,
            status="WARN",
            message=message,
            log_file=log_file,
            notes=notes,
        )

    if not model_available:
        message = f"OpenWakeWord model '{selected_model}' is not available."
        if available_models:
            notes.append(f"Available built-in models: {', '.join(available_models)}")
            notes.append("Set OPENWAKEWORD_MODEL to one of the built-in models or point it at a local custom model path.")
        else:
            notes.append("No built-in OpenWakeWord models were found.")
        return OpenWakeWordTestReport(
            package_available=True,
            selected_model=selected_model,
            available_models=available_models,
            model_available=False,
            model_path=None,
            microphone_stream_opened=False,
            sample_rate=settings.voice_sample_rate,
            chunk_ms=settings.openwakeword_listen_chunk_ms,
            duration_seconds=settings.openwakeword_test_seconds,
            chunks_processed=0,
            max_score=0.0,
            threshold=settings.openwakeword_threshold,
            detected=False,
            status="WARN",
            message=message,
            log_file=log_file,
            notes=notes,
        )

    diagnostic_settings = settings.model_copy(update={"openwakeword_enabled": True, "openwakeword_model": selected_model})
    provider = provider_factory(diagnostic_settings)
    model_path: Path | None = None

    try:
        model_path = provider.resolve_model_path()
    except Exception as exc:
        errors.append(_format_error(exc))
        notes.append("Use OPENWAKEWORD_MODEL with a built-in model name or a custom local ONNX/TFLite path.")
        return OpenWakeWordTestReport(
            package_available=True,
            selected_model=selected_model,
            available_models=available_models,
            model_available=False,
            model_path=None,
            microphone_stream_opened=False,
            sample_rate=settings.voice_sample_rate,
            chunk_ms=settings.openwakeword_listen_chunk_ms,
            duration_seconds=settings.openwakeword_test_seconds,
            chunks_processed=0,
            max_score=0.0,
            threshold=settings.openwakeword_threshold,
            detected=False,
            status="WARN",
            message=f"OpenWakeWord model '{selected_model}' could not be prepared.",
            log_file=log_file,
            errors=errors,
            notes=notes,
        )

    sd = sounddevice_module
    if sd is None:
        try:
            sd = importlib.import_module("sounddevice")
        except Exception as exc:
            errors.append(_format_error(exc))
            notes.append("Install or repair sounddevice before rerunning the diagnostic.")
            return OpenWakeWordTestReport(
                package_available=True,
                selected_model=selected_model,
                available_models=available_models,
                model_available=True,
                model_path=model_path,
                microphone_stream_opened=False,
                sample_rate=settings.voice_sample_rate,
                chunk_ms=settings.openwakeword_listen_chunk_ms,
                duration_seconds=settings.openwakeword_test_seconds,
                chunks_processed=0,
                max_score=0.0,
                threshold=settings.openwakeword_threshold,
                detected=False,
                status="WARN",
                message="sounddevice is not available.",
                log_file=log_file,
                errors=errors,
                notes=notes,
            )

    sample_rate = settings.voice_sample_rate
    chunk_ms = settings.openwakeword_listen_chunk_ms
    duration_seconds = settings.openwakeword_test_seconds
    chunk_size = max(1, int(sample_rate * (chunk_ms / 1000.0)))
    frames = int(sample_rate * duration_seconds)

    try:
        sd.check_input_settings(samplerate=sample_rate, channels=settings.voice_channels)
        recording = sd.rec(frames, samplerate=sample_rate, channels=settings.voice_channels, dtype="float32")
        sd.wait()
        microphone_stream_opened = True
    except Exception as exc:
        errors.append(_format_error(exc))
        notes.append("Check Windows microphone permissions and input device selection.")
        return OpenWakeWordTestReport(
            package_available=True,
            selected_model=selected_model,
            available_models=available_models,
            model_available=True,
            model_path=model_path,
            microphone_stream_opened=False,
            sample_rate=sample_rate,
            chunk_ms=chunk_ms,
            duration_seconds=duration_seconds,
            chunks_processed=0,
            max_score=0.0,
            threshold=settings.openwakeword_threshold,
            detected=False,
            status="WARN",
            message="The microphone stream could not be opened.",
            log_file=log_file,
            errors=errors,
            notes=notes,
        )

    samples = _flatten_samples(recording)
    scores: list[float] = []
    chunks_processed = 0
    detected = False
    max_score = 0.0

    try:
        for start in range(0, len(samples), chunk_size):
            chunk = samples[start : start + chunk_size]
            if not chunk:
                continue
            chunks_processed += 1
            result = provider.detect(chunk, sample_rate)
            max_score = max(max_score, float(result.score))
            scores.append(float(result.score))
            if result.detected:
                detected = True
    except Exception as exc:
        errors.append(_format_error(exc))
        return OpenWakeWordTestReport(
            package_available=True,
            selected_model=selected_model,
            available_models=available_models,
            model_available=True,
            model_path=model_path,
            microphone_stream_opened=microphone_stream_opened,
            sample_rate=sample_rate,
            chunk_ms=chunk_ms,
            duration_seconds=duration_seconds,
            chunks_processed=chunks_processed,
            max_score=max_score,
            threshold=settings.openwakeword_threshold,
            detected=detected,
            status="FAIL",
            message="OpenWakeWord prediction failed.",
            log_file=log_file,
            errors=errors,
            notes=notes,
        )

    status = "PASS" if detected else "WARN"
    message = (
        "OpenWakeWord detected the wake phrase."
        if detected
        else "OpenWakeWord did not detect the wake phrase during the test window."
    )
    if not detected:
        notes.append("If you want a custom wake phrase, train or supply a custom model.")

    return OpenWakeWordTestReport(
        package_available=True,
        selected_model=selected_model,
        available_models=available_models,
        model_available=True,
        model_path=model_path,
        microphone_stream_opened=microphone_stream_opened,
        sample_rate=sample_rate,
        chunk_ms=chunk_ms,
        duration_seconds=duration_seconds,
        chunks_processed=chunks_processed,
        max_score=max_score,
        threshold=settings.openwakeword_threshold,
        detected=detected,
        status=status,
        message=message,
        log_file=log_file,
        errors=errors,
        notes=notes,
    )


def format_openwakeword_test_report(report: OpenWakeWordTestReport) -> str:
    lines = [
        "Jarvis OpenWakeWord Test",
        "========================",
        f"Package available: {_yes_no(report.package_available)}",
        f"Selected model: {report.selected_model}",
        f"Model available: {_yes_no(report.model_available)}",
        f"Available models: {', '.join(report.available_models) if report.available_models else 'none'}",
        f"Model path: {report.model_path if report.model_path else 'not resolved'}",
        f"Microphone stream opened: {_yes_no(report.microphone_stream_opened)}",
        f"Sample rate: {report.sample_rate}",
        f"Chunk size: {report.chunk_ms} ms",
        f"Test duration: {report.duration_seconds:.0f} s",
        f"Chunks processed: {report.chunks_processed}",
        f"Max score: {report.max_score:.4f}",
        f"Threshold: {report.threshold:.4f}",
        f"Detected: {_yes_no(report.detected)}",
        f"Status: {report.status}",
        f"Message: {report.message}",
        f"Log file: {report.log_file}",
    ]
    if report.notes:
        lines.extend(["", "Notes:"])
        lines.extend(f"  - {note}" for note in report.notes)
    if report.errors:
        lines.extend(["", "Errors:"])
        lines.extend(f"  - {error}" for error in report.errors)
    return "\n".join(lines)


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


def _format_error(error: Exception) -> str:
    error_type = type(error).__name__
    message = str(error).strip() or "No error details provided."
    return f"{error_type}: {message}"


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _ensure_log_sink(settings: AppSettings, log_file: Path) -> None:
    global _OPENWAKEWORD_LOG_SINK_ID
    if _OPENWAKEWORD_LOG_SINK_ID is not None:
        return

    settings.log_dir.mkdir(parents=True, exist_ok=True)
    _OPENWAKEWORD_LOG_SINK_ID = logger.add(
        log_file,
        level="DEBUG",
        rotation="1 MB",
        retention="7 days",
        encoding="utf-8",
        backtrace=False,
        diagnose=False,
        filter=lambda record: bool(record["extra"].get("openwakeword_test")),
    )
