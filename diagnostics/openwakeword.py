from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from math import sqrt
from pathlib import Path
from statistics import mean
from typing import Any, Callable, Sequence

from loguru import logger

from config.settings import AppSettings
from voice.vad import RmsVoiceActivityDetector
from voice.wake_provider import OpenWakeWordWakeProvider, available_openwakeword_models, is_openwakeword_installed


_OPENWAKEWORD_LOG_SINK_ID: int | None = None


@dataclass(frozen=True)
class OpenWakeWordObservation:
    avg_rms: float
    max_rms: float
    vad_threshold_crossed: bool
    max_score: float
    chunks_processed: int
    detected: bool
    sample_rate: int
    duration_seconds: float
    chunk_ms: int


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
    avg_rms: float
    max_rms: float
    vad_threshold_crossed: bool
    vad_threshold: float
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


@dataclass(frozen=True)
class OpenWakeWordCalibrationRoundReport:
    round_number: int
    avg_rms: float
    max_rms: float
    vad_threshold_crossed: bool
    chunks_processed: int
    max_score: float
    detected: bool
    prompt: str


@dataclass(frozen=True)
class OpenWakeWordCalibrationReport:
    package_available: bool
    selected_model: str
    available_models: list[str]
    model_available: bool
    model_path: Path | None
    microphone_stream_opened: bool
    sample_rate: int
    chunk_ms: int
    round_seconds: float
    rounds: list[OpenWakeWordCalibrationRoundReport]
    average_max_score: float
    max_score: float
    recommended_threshold: float
    vad_threshold: float
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
    _ensure_log_sink(settings, log_file)

    package_available = is_openwakeword_installed()
    available_models = available_openwakeword_models()
    selected_model = settings.openwakeword_model.strip() or "hey_jarvis"
    model_available = _is_model_available(selected_model)
    notes: list[str] = []
    errors: list[str] = []

    if not package_available:
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
            avg_rms=0.0,
            max_rms=0.0,
            vad_threshold_crossed=False,
            vad_threshold=settings.voice_vad_threshold,
            max_score=0.0,
            threshold=settings.openwakeword_threshold,
            detected=False,
            status="WARN",
            message="OpenWakeWord package is not installed.",
            log_file=log_file,
            notes=["Install openwakeword and rerun the diagnostic."],
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
            avg_rms=0.0,
            max_rms=0.0,
            vad_threshold_crossed=False,
            vad_threshold=settings.voice_vad_threshold,
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
            avg_rms=0.0,
            max_rms=0.0,
            vad_threshold_crossed=False,
            vad_threshold=settings.voice_vad_threshold,
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
                avg_rms=0.0,
                max_rms=0.0,
                vad_threshold_crossed=False,
                max_score=0.0,
                threshold=settings.openwakeword_threshold,
                detected=False,
                status="WARN",
                message="sounddevice is not available.",
                log_file=log_file,
                errors=errors,
                notes=notes,
            )

    try:
        observation = _capture_openwakeword_observation(
            settings,
            provider=provider,
            sd=sd,
            duration_seconds=settings.openwakeword_test_seconds,
            sample_rate=settings.voice_sample_rate,
            chunk_ms=settings.openwakeword_listen_chunk_ms,
        )
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
            sample_rate=settings.voice_sample_rate,
            chunk_ms=settings.openwakeword_listen_chunk_ms,
            duration_seconds=settings.openwakeword_test_seconds,
            chunks_processed=0,
            avg_rms=0.0,
            max_rms=0.0,
            vad_threshold_crossed=False,
            vad_threshold=settings.voice_vad_threshold,
            max_score=0.0,
            threshold=settings.openwakeword_threshold,
            detected=False,
            status="WARN",
            message="The microphone stream could not be opened.",
            log_file=log_file,
            errors=errors,
            notes=notes,
        )

    status = "PASS" if observation.detected else "WARN"
    message = (
        "OpenWakeWord detected the wake phrase."
        if observation.detected
        else "OpenWakeWord did not detect the wake phrase during the test window."
    )
    notes.extend(_build_interpretation_notes(settings, observation, selected_model))

    return OpenWakeWordTestReport(
        package_available=True,
        selected_model=selected_model,
        available_models=available_models,
        model_available=True,
        model_path=model_path,
        microphone_stream_opened=True,
        sample_rate=observation.sample_rate,
        chunk_ms=observation.chunk_ms,
        duration_seconds=observation.duration_seconds,
        chunks_processed=observation.chunks_processed,
        avg_rms=observation.avg_rms,
        max_rms=observation.max_rms,
        vad_threshold_crossed=observation.vad_threshold_crossed,
        vad_threshold=settings.voice_vad_threshold,
        max_score=observation.max_score,
        threshold=settings.openwakeword_threshold,
        detected=observation.detected,
        status=status,
        message=message,
        log_file=log_file,
        errors=errors,
        notes=notes,
    )


def run_openwakeword_calibration(
    settings: AppSettings | None = None,
    *,
    sounddevice_module: Any | None = None,
    provider_factory: Callable[[AppSettings], OpenWakeWordWakeProvider] | None = None,
) -> OpenWakeWordCalibrationReport:
    settings = settings or AppSettings(_env_file=None)
    provider_factory = provider_factory or OpenWakeWordWakeProvider
    log_file = settings.log_dir / "openwakeword.log"
    _ensure_log_sink(settings, log_file)

    package_available = is_openwakeword_installed()
    available_models = available_openwakeword_models()
    selected_model = settings.openwakeword_model.strip() or "hey_jarvis"
    model_available = _is_model_available(selected_model)
    notes: list[str] = []
    errors: list[str] = []

    if not package_available:
        return OpenWakeWordCalibrationReport(
            package_available=False,
            selected_model=selected_model,
            available_models=available_models,
            model_available=False,
            model_path=None,
            microphone_stream_opened=False,
            sample_rate=settings.voice_sample_rate,
            chunk_ms=settings.openwakeword_listen_chunk_ms,
            round_seconds=settings.openwakeword_calibration_seconds,
            rounds=[],
            average_max_score=0.0,
            max_score=0.0,
            recommended_threshold=settings.openwakeword_threshold,
            vad_threshold=settings.voice_vad_threshold,
            detected=False,
            status="WARN",
            message="OpenWakeWord package is not installed.",
            log_file=log_file,
            notes=["Install openwakeword and rerun the calibration."],
        )

    if not model_available:
        message = f"OpenWakeWord model '{selected_model}' is not available."
        if available_models:
            notes.append(f"Available built-in models: {', '.join(available_models)}")
            notes.append("Set OPENWAKEWORD_MODEL to one of the built-in models or point it at a local custom model path.")
        else:
            notes.append("No built-in OpenWakeWord models were found.")
        return OpenWakeWordCalibrationReport(
            package_available=True,
            selected_model=selected_model,
            available_models=available_models,
            model_available=False,
            model_path=None,
            microphone_stream_opened=False,
            sample_rate=settings.voice_sample_rate,
            chunk_ms=settings.openwakeword_listen_chunk_ms,
            round_seconds=settings.openwakeword_calibration_seconds,
            rounds=[],
            average_max_score=0.0,
            max_score=0.0,
            recommended_threshold=settings.openwakeword_threshold,
            vad_threshold=settings.voice_vad_threshold,
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
        return OpenWakeWordCalibrationReport(
            package_available=True,
            selected_model=selected_model,
            available_models=available_models,
            model_available=False,
            model_path=None,
            microphone_stream_opened=False,
            sample_rate=settings.voice_sample_rate,
            chunk_ms=settings.openwakeword_listen_chunk_ms,
            round_seconds=settings.openwakeword_calibration_seconds,
            rounds=[],
            average_max_score=0.0,
            max_score=0.0,
            recommended_threshold=settings.openwakeword_threshold,
            vad_threshold=settings.voice_vad_threshold,
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
            notes.append("Install or repair sounddevice before rerunning the calibration.")
            return OpenWakeWordCalibrationReport(
                package_available=True,
                selected_model=selected_model,
                available_models=available_models,
                model_available=True,
                model_path=model_path,
                microphone_stream_opened=False,
                sample_rate=settings.voice_sample_rate,
                chunk_ms=settings.openwakeword_listen_chunk_ms,
                round_seconds=settings.openwakeword_calibration_seconds,
                rounds=[],
                average_max_score=0.0,
                max_score=0.0,
                recommended_threshold=settings.openwakeword_threshold,
                detected=False,
                status="WARN",
                message="sounddevice is not available.",
                log_file=log_file,
                errors=errors,
                notes=notes,
            )

    rounds: list[OpenWakeWordCalibrationRoundReport] = []
    scores: list[float] = []
    any_detected = False

    try:
        for round_number in range(1, settings.openwakeword_calibration_rounds + 1):
            prompt = f"Round {round_number}/{settings.openwakeword_calibration_rounds}: say 'Hey Jarvis' now."
            round_observation = _capture_openwakeword_observation(
                settings,
                provider=provider,
                sd=sd,
                duration_seconds=settings.openwakeword_calibration_seconds,
                sample_rate=settings.voice_sample_rate,
                chunk_ms=settings.openwakeword_listen_chunk_ms,
                prompt=prompt,
            )
            rounds.append(
                OpenWakeWordCalibrationRoundReport(
                    round_number=round_number,
                    avg_rms=round_observation.avg_rms,
                    max_rms=round_observation.max_rms,
                    vad_threshold_crossed=round_observation.vad_threshold_crossed,
                    chunks_processed=round_observation.chunks_processed,
                    max_score=round_observation.max_score,
                    detected=round_observation.detected,
                    prompt=prompt,
                )
            )
            scores.append(round_observation.max_score)
            any_detected = any_detected or round_observation.detected
    except Exception as exc:
        errors.append(_format_error(exc))
        return OpenWakeWordCalibrationReport(
            package_available=True,
            selected_model=selected_model,
            available_models=available_models,
            model_available=True,
            model_path=model_path,
            microphone_stream_opened=bool(rounds),
            sample_rate=settings.voice_sample_rate,
            chunk_ms=settings.openwakeword_listen_chunk_ms,
            round_seconds=settings.openwakeword_calibration_seconds,
            rounds=rounds,
            average_max_score=mean(scores) if scores else 0.0,
            max_score=max(scores) if scores else 0.0,
            recommended_threshold=recommend_openwakeword_threshold(scores, settings.openwakeword_threshold),
            vad_threshold=settings.voice_vad_threshold,
            detected=any_detected,
            status="FAIL",
            message="OpenWakeWord calibration failed.",
            log_file=log_file,
            errors=errors,
            notes=notes,
        )

    average_max_score = mean(scores) if scores else 0.0
    max_score = max(scores) if scores else 0.0
    recommended_threshold = recommend_openwakeword_threshold(scores, settings.openwakeword_threshold)
    notes.extend(_build_calibration_notes(settings, rounds, average_max_score, max_score))
    status = "PASS" if any_detected else "WARN"
    message = (
        "OpenWakeWord detected the wake phrase during calibration."
        if any_detected
        else "OpenWakeWord did not detect the wake phrase during calibration."
    )

    return OpenWakeWordCalibrationReport(
        package_available=True,
        selected_model=selected_model,
        available_models=available_models,
        model_available=True,
        model_path=model_path,
        microphone_stream_opened=True,
        sample_rate=settings.voice_sample_rate,
        chunk_ms=settings.openwakeword_listen_chunk_ms,
        round_seconds=settings.openwakeword_calibration_seconds,
        rounds=rounds,
        average_max_score=average_max_score,
        max_score=max_score,
        recommended_threshold=recommended_threshold,
        vad_threshold=settings.voice_vad_threshold,
        detected=any_detected,
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
        f"Average RMS: {report.avg_rms:.6f}",
        f"Max RMS: {report.max_rms:.6f}",
        f"VAD threshold crossed: {_yes_no(report.vad_threshold_crossed)}",
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
    lines.extend(_format_notes_and_errors(report.notes, report.errors))
    lines.extend(
        _build_signal_interpretation_lines(
            report.avg_rms,
            report.max_rms,
            report.max_score,
            report.threshold,
            report.vad_threshold_crossed,
            vad_threshold=report.vad_threshold,
        )
    )
    return "\n".join(lines)


def format_openwakeword_calibration_report(report: OpenWakeWordCalibrationReport) -> str:
    lines = [
        "Jarvis OpenWakeWord Calibration",
        "===============================",
        f"Package available: {_yes_no(report.package_available)}",
        f"Selected model: {report.selected_model}",
        f"Model available: {_yes_no(report.model_available)}",
        f"Available models: {', '.join(report.available_models) if report.available_models else 'none'}",
        f"Model path: {report.model_path if report.model_path else 'not resolved'}",
        f"Microphone stream opened: {_yes_no(report.microphone_stream_opened)}",
        f"Sample rate: {report.sample_rate}",
        f"Chunk size: {report.chunk_ms} ms",
        f"Rounds: {len(report.rounds)}",
        f"Round duration: {report.round_seconds:.0f} s",
        f"Average max score: {report.average_max_score:.4f}",
        f"Max score: {report.max_score:.4f}",
        f"Recommended threshold: {report.recommended_threshold:.4f}",
        f"VAD threshold: {report.vad_threshold:.4f}",
        f"Detected in any round: {_yes_no(report.detected)}",
        f"Status: {report.status}",
        f"Message: {report.message}",
        f"Log file: {report.log_file}",
    ]
    for round_report in report.rounds:
        lines.extend(
            [
                "",
                f"Round {round_report.round_number}:",
                f"  prompt: {round_report.prompt}",
                f"  average RMS: {round_report.avg_rms:.6f}",
                f"  max RMS: {round_report.max_rms:.6f}",
                f"  VAD threshold crossed: {_yes_no(round_report.vad_threshold_crossed)}",
                f"  chunks processed: {round_report.chunks_processed}",
                f"  max score: {round_report.max_score:.4f}",
                f"  detected: {_yes_no(round_report.detected)}",
            ]
        )
    lines.extend(_format_notes_and_errors(report.notes, report.errors))
    lines.extend(
        _build_signal_interpretation_lines(
            report.rounds[-1].avg_rms if report.rounds else 0.0,
            report.rounds[-1].max_rms if report.rounds else 0.0,
            report.max_score,
            report.recommended_threshold,
            report.rounds[-1].vad_threshold_crossed if report.rounds else False,
            vad_threshold=report.vad_threshold,
        )
    )
    return "\n".join(lines)


def recommend_openwakeword_threshold(scores: Sequence[float], current_threshold: float) -> float:
    valid_scores = [float(score) for score in scores if score is not None]
    if not valid_scores:
        return round(float(current_threshold), 4)
    recommended = max(valid_scores) * 0.8
    return round(max(0.01, min(recommended, 0.99)), 4)


def _capture_openwakeword_observation(
    settings: AppSettings,
    *,
    provider: OpenWakeWordWakeProvider,
    sd: Any,
    duration_seconds: float,
    sample_rate: int,
    chunk_ms: int,
    prompt: str | None = None,
) -> OpenWakeWordObservation:
    if prompt:
        print(prompt, flush=True)

    channels = settings.voice_channels
    frames = int(sample_rate * duration_seconds)
    chunk_size = max(1, int(sample_rate * (chunk_ms / 1000.0)))

    sd.check_input_settings(samplerate=sample_rate, channels=channels)
    recording = sd.rec(frames, samplerate=sample_rate, channels=channels, dtype="float32")
    sd.wait()
    samples = _flatten_samples(recording)
    avg_rms = _calculate_rms(samples)
    max_rms = _calculate_max_rms(samples, sample_rate)
    vad_result = RmsVoiceActivityDetector(settings.voice_vad_threshold).analyze([max_rms], sample_rate)

    chunk_scores: list[float] = []
    chunks_processed = 0
    detected = False
    for start in range(0, len(samples), chunk_size):
        chunk = samples[start : start + chunk_size]
        if not chunk:
            continue
        chunks_processed += 1
        result = provider.detect(chunk, sample_rate)
        chunk_scores.append(float(result.score))
        if result.detected:
            detected = True

    return OpenWakeWordObservation(
        avg_rms=avg_rms,
        max_rms=max_rms,
        vad_threshold_crossed=vad_result.is_speech,
        max_score=max(chunk_scores) if chunk_scores else 0.0,
        chunks_processed=chunks_processed,
        detected=detected,
        sample_rate=sample_rate,
        duration_seconds=duration_seconds,
        chunk_ms=chunk_ms,
    )


def _build_calibration_notes(
    settings: AppSettings,
    rounds: Sequence[OpenWakeWordCalibrationRoundReport],
    average_max_score: float,
    max_score: float,
) -> list[str]:
    notes: list[str] = []
    if not rounds:
        return notes

    last_round = rounds[-1]
    if last_round.avg_rms < settings.voice_vad_threshold:
        notes.append("Microphone input is weak. Increase input gain, move closer to the microphone, or reduce background noise.")
    elif last_round.max_rms >= settings.voice_vad_threshold and max_score < settings.openwakeword_threshold:
        notes.append(
            "Microphone input looks usable, but the OpenWakeWord scores are low. The pronunciation, room noise, or wake phrase/model may not match well."
        )

    notes.append(f"Average max score across rounds: {average_max_score:.4f}")
    notes.append(f"Peak score across rounds: {max_score:.4f}")
    notes.append(f"Recommended threshold based on observed scores: {recommend_openwakeword_threshold([round_report.max_score for round_report in rounds], settings.openwakeword_threshold):.4f}")
    return notes


def _build_interpretation_notes(
    settings: AppSettings,
    observation: OpenWakeWordObservation,
    selected_model: str,
) -> list[str]:
    notes: list[str] = []
    if observation.avg_rms < settings.voice_vad_threshold:
        notes.append("Microphone input is weak. Increase input gain or move closer to the microphone.")
    elif observation.max_rms >= settings.voice_vad_threshold and observation.max_score < settings.openwakeword_threshold:
        notes.append(
            f"Microphone input looks usable, but the '{selected_model}' model scores are low. The pronunciation or wake phrase may not match this model well."
        )
    notes.append(f"Average RMS level: {observation.avg_rms:.6f}")
    notes.append(f"Max RMS level: {observation.max_rms:.6f}")
    notes.append(f"VAD threshold crossed: {_yes_no(observation.vad_threshold_crossed)}")
    return notes


def _build_signal_interpretation_lines(
    avg_rms: float,
    max_rms: float,
    max_score: float,
    threshold: float,
    vad_threshold_crossed: bool,
    *,
    vad_threshold: float,
) -> list[str]:
    lines = [
        "",
        "Interpretation:",
        f"  average RMS: {avg_rms:.6f}",
        f"  max RMS: {max_rms:.6f}",
        f"  VAD threshold crossed: {_yes_no(vad_threshold_crossed)}",
        f"  peak score vs threshold: {max_score:.4f} / {threshold:.4f}",
    ]
    if avg_rms < vad_threshold:
        lines.append("  - Microphone input is weak.")
    elif max_rms >= vad_threshold and max_score < threshold:
        lines.append("  - Microphone input looks usable, but the model scores are low.")
    return lines


def _format_notes_and_errors(notes: Sequence[str], errors: Sequence[str]) -> list[str]:
    lines: list[str] = []
    if notes:
        lines.extend(["", "Notes:"])
        lines.extend(f"  - {note}" for note in notes)
    if errors:
        lines.extend(["", "Errors:"])
        lines.extend(f"  - {error}" for error in errors)
    return lines


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


def _calculate_rms(samples: Sequence[float]) -> float:
    if not samples:
        return 0.0
    return sqrt(sum(sample * sample for sample in samples) / len(samples))


def _calculate_max_rms(samples: Sequence[float], sample_rate: int) -> float:
    if not samples:
        return 0.0
    window_size = max(1, int(sample_rate * 0.1))
    max_rms = 0.0
    for start in range(0, len(samples), window_size):
        window = samples[start : start + window_size]
        max_rms = max(max_rms, _calculate_rms(window))
    return max_rms


def _is_model_available(model_name: str) -> bool:
    cleaned = model_name.strip()
    if not cleaned:
        return False
    if Path(cleaned).exists():
        return True
    return cleaned in available_openwakeword_models()


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
