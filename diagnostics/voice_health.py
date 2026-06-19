from __future__ import annotations

import importlib
import math
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from config.settings import AppSettings
from voice.audio_diagnostics import AudioDeviceInfo
from voice.command_capture import (
    calculate_effective_vad_threshold,
    calculate_rms,
    calculate_window_rms,
)
from voice.command_validation import validate_cleaned_command
from voice.interfaces import TranscriptionResult
from voice.speech_repair import SpeechRepairResult, SpeechRepairer
from voice.stt import create_speech_to_text_provider
from voice.wake import WakeDetectionResult, WakeDetector, remove_wake_phrase_prefix
from voice.wake_provider import create_openwakeword_provider, resolve_wake_provider


MIC_PROBLEM = "MIC_PROBLEM"
VAD_PROBLEM = "VAD_PROBLEM"
WAKE_PROBLEM = "WAKE_PROBLEM"
STT_PROBLEM = "STT_PROBLEM"
COMMAND_REPAIR_PROBLEM = "COMMAND_REPAIR_PROBLEM"
TIMING_PROBLEM = "TIMING_PROBLEM"
HEALTHY = "HEALTHY"
HEALTHY_WITH_WARNINGS = "HEALTHY_WITH_WARNINGS"

CALIBRATION_SECONDS = 2.0
MIN_AVERAGE_RMS = 0.006
MIN_MAX_RMS = 0.025
MIN_SIGNAL_TO_NOISE_DB = 10.0
LATE_VAD_TRIGGER_FRACTION = 0.70
CALIBRATION_CONTAMINATION_RATIO = 0.75
NOISE_PERCENTILE = 0.20
MIN_TRANSCRIPT_CONFIDENCE = 0.35


@dataclass(frozen=True)
class VoiceHealthSignals:
    microphone_detected: bool = False
    stream_opened: bool = False
    average_rms: float = 0.0
    max_rms: float = 0.0
    noise_floor: float = 0.0
    signal_to_noise_db: float = 0.0
    calibration_rms: float = 0.0
    calibration_contaminated: bool = False
    clipping: bool = False
    vad_crossed: bool = False
    vad_trigger_seconds: float | None = None
    speech_seconds: float = 0.0
    selected_device_problem: bool = False
    wake_provider_available: bool = False
    wake_detected: bool = False
    wake_requires_stt: bool = False
    stt_provider_available: bool = False
    stt_error: bool = False
    raw_transcript: str = ""
    transcript_confidence: float | None = None
    repaired_transcript: str = ""
    repair_confidence: float = 0.0
    command_accepted: bool = False


@dataclass(frozen=True)
class VoiceHealthAudioMetrics:
    average_rms: float
    max_rms: float
    noise_floor: float
    signal_to_noise_db: float
    calibration_rms: float
    calibration_contaminated: bool
    clipping: bool
    vad_threshold: float
    effective_vad_threshold: float
    vad_crossed: bool
    vad_trigger_seconds: float | None


@dataclass(frozen=True)
class VoiceHealthReport:
    input_devices: list[AudioDeviceInfo]
    selected_input_device: AudioDeviceInfo | None
    calibration_seconds: float
    speech_seconds: float
    audio: VoiceHealthAudioMetrics
    wake_provider: str
    wake_model_name: str
    wake_model_available: bool
    wake_score: float
    wake_matched_phrase: str | None
    wake_decision: str
    stt_provider: str
    stt_model_name: str
    stt_provider_available: bool
    raw_transcript: str
    transcript_confidence: float | None
    transcription_seconds: float
    clean_transcript: str
    repaired_transcript: str
    repair_confidence: float
    repair_strategy: str
    command_accepted: bool
    diagnosis: str
    recommended_action: str
    stream_opened: bool
    selected_device_warning: str | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def is_healthy(self) -> bool:
        return self.diagnosis in {HEALTHY, HEALTHY_WITH_WARNINGS}


def diagnose_voice_health(signals: VoiceHealthSignals) -> str:
    pipeline_succeeded = bool(
        signals.wake_detected
        and signals.raw_transcript.strip()
        and signals.command_accepted
    )
    if (
        not signals.microphone_detected
        or not signals.stream_opened
        or signals.average_rms < MIN_AVERAGE_RMS
        or signals.max_rms < MIN_MAX_RMS
        or signals.clipping
        or signals.selected_device_problem
    ):
        return MIC_PROBLEM
    if not signals.raw_transcript.strip() and signals.signal_to_noise_db < MIN_SIGNAL_TO_NOISE_DB:
        return MIC_PROBLEM
    if not signals.vad_crossed:
        return VAD_PROBLEM
    if signals.wake_requires_stt and _stt_failed(signals):
        return STT_PROBLEM
    if not signals.wake_provider_available or not signals.wake_detected:
        return WAKE_PROBLEM
    if _stt_failed(signals):
        return STT_PROBLEM
    if pipeline_succeeded:
        if _has_nonfatal_input_warning(signals):
            return HEALTHY_WITH_WARNINGS
        return HEALTHY
    if signals.wake_detected and not signals.repaired_transcript.strip():
        return TIMING_PROBLEM
    if (
        not signals.command_accepted
        or signals.repair_confidence <= 0.0
    ):
        return COMMAND_REPAIR_PROBLEM
    return HEALTHY


def recommended_voice_action(diagnosis: str) -> str:
    return {
        MIC_PROBLEM: (
            "Select the real microphone instead of Microsoft Sound Mapper, Stereo Mix, PC Speaker, or another "
            "output device; increase Windows microphone input volume; disable noise suppression/enhancements if "
            "they damage speech; speak closer to the laptop microphone; or try a wired/headset microphone."
        ),
        VAD_PROBLEM: (
            "The microphone captured speech but VAD did not trigger. Compare the printed noise floor and "
            "effective threshold, then lower VOICE_VAD_THRESHOLD or reduce background noise."
        ),
        WAKE_PROBLEM: (
            "The audio and VAD stages passed but wake detection failed. Verify the wake provider/model and "
            "rerun while clearly saying 'Hey Jarvis' near the start of the sample."
        ),
        STT_PROBLEM: (
            "Wake/audio passed but transcription failed or was unreliable. Verify faster-whisper and its "
            "configured model, then run python main.py --transcribe-test."
        ),
        COMMAND_REPAIR_PROBLEM: (
            "Transcription succeeded but command cleaning/repair did not produce an accepted command. Review "
            "the raw, clean, and repaired transcript plus repair rules."
        ),
        TIMING_PROBLEM: (
            "Wake detection succeeded, but no command was captured. Speak immediately when the prompt appears, "
            "or extend VOICE_HEALTH_SPEECH_SECONDS and rerun the check."
        ),
        HEALTHY_WITH_WARNINGS: (
            "Wake, transcription, and command handling succeeded. Review the warnings, repeat calibration in "
            "silence, and rerun the check if recognition remains unreliable."
        ),
        HEALTHY: "The measured voice pipeline is healthy. Run python main.py --voice-loop to verify normal operation.",
    }.get(diagnosis, "Review the voice health report and rerun the check.")


class VoiceHealthCheck:
    """Run one evidence-producing check through the complete voice input pipeline."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        sounddevice_module: Any | None = None,
        stt_provider: Any | None = None,
        wake_provider: Any | None = None,
        output: Callable[[str], None] = print,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.settings = settings
        self.sounddevice_module = sounddevice_module
        self.stt_provider = stt_provider or create_speech_to_text_provider(settings)
        self.wake_provider = wake_provider
        self.output = output
        self.clock = clock

    def run(self) -> VoiceHealthReport:
        errors: list[str] = []
        devices: list[AudioDeviceInfo] = []
        selected_device: AudioDeviceInfo | None = None
        selected_device_warning: str | None = None
        selected_device_problem = False
        stream_opened = False
        silence_samples: list[float] = []
        speech_samples: list[float] = []

        try:
            sd = self.sounddevice_module or importlib.import_module("sounddevice")
            devices = _list_input_devices(sd)
            selected_device, selection_warning = _select_input_device(
                sd,
                devices,
                self.settings.voice_input_device,
            )
            device_name_warning = _selected_device_name_warning(selected_device)
            selected_device_problem = device_name_warning is not None
            selected_device_warning = _join_warnings(
                selection_warning,
                device_name_warning,
            )
            if selected_device is None:
                errors.append("No microphone input device was detected.")
            else:
                self.output(f"Calibration: remain silent for {CALIBRATION_SECONDS:.1f} seconds...")
                silence_samples = self._record(sd, CALIBRATION_SECONDS, selected_device.index)
                self.output(
                    f"Speech sample: say '{self.settings.wake_phrase.title()}, status report' now "
                    f"({self.settings.voice_health_speech_seconds:.1f} seconds)..."
                )
                speech_samples = self._record(
                    sd,
                    self.settings.voice_health_speech_seconds,
                    selected_device.index,
                )
                stream_opened = True
        except Exception as exc:
            errors.append(f"Microphone capture failed: {type(exc).__name__}: {exc}")

        audio = calculate_voice_health_audio_metrics(
            silence_samples,
            speech_samples,
            sample_rate=self.settings.voice_sample_rate,
            vad_threshold=self.settings.voice_vad_threshold,
            vad_window_ms=self.settings.voice_vad_window_ms,
            noise_multiplier=self.settings.voice_vad_noise_multiplier,
        )

        transcription = TranscriptionResult(text="")
        transcription_seconds = 0.0
        stt_error = False
        if stream_opened and self.stt_provider.available:
            started = self.clock()
            try:
                transcription = self.stt_provider.transcribe(speech_samples, self.settings.voice_sample_rate)
            except Exception as exc:
                stt_error = True
                errors.append(f"Transcription failed: {type(exc).__name__}: {exc}")
            finally:
                transcription_seconds = max(0.0, self.clock() - started)
        elif not self.stt_provider.available:
            stt_error = True
            errors.append("Speech-to-text provider is not available.")

        raw_transcript = transcription.text.strip()
        clean_transcript = remove_wake_phrase_prefix(
            raw_transcript,
            wake_phrase=self.settings.wake_phrase,
            aliases=self.settings.wake_alias_list,
        )
        repair = SpeechRepairer(self.settings).repair(
            clean_transcript,
            raw_transcript=raw_transcript,
        )
        validation = validate_cleaned_command(
            repair.repaired_transcript,
            min_words=self.settings.voice_command_min_words,
            reject_phrases=self.settings.voice_command_reject_phrase_list,
            incomplete_phrases=self.settings.voice_command_incomplete_phrase_list,
        )

        wake_resolution = resolve_wake_provider(self.settings)
        wake_detection, wake_available, wake_model_name, wake_requires_stt = self._run_wake_test(
            speech_samples,
            raw_transcript,
            wake_resolution.effective_provider,
            bool(stream_opened),
            errors,
        )
        wake_decision = "detected" if wake_detection.detected else "rejected"
        if not wake_available:
            wake_decision = "unavailable"
        if wake_resolution.effective_provider == "manual":
            wake_decision = "manual mode required"

        signals = VoiceHealthSignals(
            microphone_detected=bool(devices),
            stream_opened=stream_opened,
            average_rms=audio.average_rms,
            max_rms=audio.max_rms,
            noise_floor=audio.noise_floor,
            signal_to_noise_db=audio.signal_to_noise_db,
            calibration_rms=audio.calibration_rms,
            calibration_contaminated=audio.calibration_contaminated,
            clipping=audio.clipping,
            vad_crossed=audio.vad_crossed,
            vad_trigger_seconds=audio.vad_trigger_seconds,
            speech_seconds=self.settings.voice_health_speech_seconds,
            selected_device_problem=selected_device_problem,
            wake_provider_available=wake_available,
            wake_detected=wake_detection.detected,
            wake_requires_stt=wake_requires_stt,
            stt_provider_available=bool(self.stt_provider.available),
            stt_error=stt_error,
            raw_transcript=raw_transcript,
            transcript_confidence=transcription.confidence,
            repaired_transcript=repair.repaired_transcript,
            repair_confidence=repair.confidence,
            command_accepted=validation.accepted,
        )
        diagnosis = diagnose_voice_health(signals)
        warnings = _input_quality_warnings(signals)
        return VoiceHealthReport(
            input_devices=devices,
            selected_input_device=selected_device,
            calibration_seconds=CALIBRATION_SECONDS,
            speech_seconds=self.settings.voice_health_speech_seconds,
            audio=audio,
            wake_provider=wake_resolution.effective_provider,
            wake_model_name=wake_model_name,
            wake_model_available=wake_available,
            wake_score=wake_detection.score,
            wake_matched_phrase=wake_detection.matched_phrase,
            wake_decision=wake_decision,
            stt_provider=self.stt_provider.name,
            stt_model_name=self.settings.whisper_model,
            stt_provider_available=bool(self.stt_provider.available),
            raw_transcript=raw_transcript,
            transcript_confidence=transcription.confidence,
            transcription_seconds=transcription_seconds,
            clean_transcript=repair.cleaned_transcript,
            repaired_transcript=repair.repaired_transcript,
            repair_confidence=repair.confidence,
            repair_strategy=repair.strategy,
            command_accepted=validation.accepted,
            diagnosis=diagnosis,
            recommended_action=recommended_voice_action(diagnosis),
            stream_opened=stream_opened,
            selected_device_warning=selected_device_warning,
            warnings=warnings,
            errors=errors,
        )

    def _record(self, sd: Any, seconds: float, device_index: int) -> list[float]:
        sample_rate = self.settings.voice_sample_rate
        channels = self.settings.voice_channels
        sd.check_input_settings(device=device_index, samplerate=sample_rate, channels=channels)
        recording = sd.rec(
            int(sample_rate * seconds),
            samplerate=sample_rate,
            channels=channels,
            dtype="float32",
            device=device_index,
        )
        sd.wait()
        return _flatten_samples(recording)

    def _run_wake_test(
        self,
        speech_samples: list[float],
        transcript: str,
        effective_provider: str,
        stream_opened: bool,
        errors: list[str],
    ) -> tuple[WakeDetectionResult, bool, str, bool]:
        empty = _empty_wake_detection(self.settings)
        if not stream_opened:
            return empty, False, self.settings.openwakeword_model, effective_provider == "whisper_fuzzy"

        if effective_provider == "openwakeword":
            provider = self.wake_provider or create_openwakeword_provider(self.settings)
            if not provider.available:
                return empty, False, self.settings.openwakeword_model, False
            try:
                detection = _detect_openwakeword_sample(provider, speech_samples, self.settings)
                return detection, True, self.settings.openwakeword_model, False
            except Exception as exc:
                errors.append(f"Wake detection failed: {type(exc).__name__}: {exc}")
                return empty, False, self.settings.openwakeword_model, False

        if effective_provider == "whisper_fuzzy":
            detector = WakeDetector(
                wake_phrase=self.settings.wake_phrase,
                aliases=self.settings.wake_alias_list,
                threshold=self.settings.wake_match_threshold,
            )
            return detector.detect(transcript), bool(self.stt_provider.available), "fuzzy phrase matcher", True

        return empty, False, "manual", False


def calculate_voice_health_audio_metrics(
    silence_samples: Sequence[float],
    speech_samples: Sequence[float],
    *,
    sample_rate: int,
    vad_threshold: float,
    vad_window_ms: int,
    noise_multiplier: float,
) -> VoiceHealthAudioMetrics:
    silence = list(silence_samples)
    speech = list(speech_samples)
    calibration_rms = calculate_rms(silence)
    average_rms = calculate_rms(speech)
    calibration_windows = calculate_window_rms(silence, sample_rate, vad_window_ms=vad_window_ms)
    windows = calculate_window_rms(speech, sample_rate, vad_window_ms=vad_window_ms)
    calibration_noise = _percentile(calibration_windows, NOISE_PERCENTILE)
    speech_noise = _percentile(windows, NOISE_PERCENTILE)
    noise_candidates: list[float] = []
    if calibration_windows:
        noise_candidates.append(calibration_noise)
    if windows:
        noise_candidates.append(speech_noise)
    noise_floor = min(noise_candidates) if noise_candidates else 0.0
    max_rms = max(windows) if windows else 0.0
    calibration_contaminated = bool(
        average_rms >= MIN_AVERAGE_RMS
        and calibration_rms >= average_rms * CALIBRATION_CONTAMINATION_RATIO
    )
    effective_threshold = calculate_effective_vad_threshold(
        vad_threshold,
        noise_floor,
        noise_multiplier=noise_multiplier,
    )
    trigger_index = next((index for index, value in enumerate(windows) if value >= effective_threshold), None)
    trigger_seconds = None
    if trigger_index is not None:
        trigger_seconds = trigger_index * max(vad_window_ms, 1) / 1000.0
    return VoiceHealthAudioMetrics(
        average_rms=average_rms,
        max_rms=max_rms,
        noise_floor=noise_floor,
        signal_to_noise_db=_signal_to_noise_db(average_rms, noise_floor),
        calibration_rms=calibration_rms,
        calibration_contaminated=calibration_contaminated,
        clipping=any(abs(sample) >= 0.98 for sample in speech),
        vad_threshold=vad_threshold,
        effective_vad_threshold=effective_threshold,
        vad_crossed=max_rms >= effective_threshold,
        vad_trigger_seconds=trigger_seconds,
    )


def format_voice_health_report(report: VoiceHealthReport) -> str:
    selected = report.selected_input_device
    lines = [
        "Jarvis Voice Pipeline Health Check",
        "==================================",
        "",
        "Input devices:",
    ]
    if report.input_devices:
        for device in report.input_devices:
            marker = " (selected/default)" if selected and device.index == selected.index else ""
            lines.append(
                f"  [{device.index}] {device.name}{marker} | channels={device.input_channels} | "
                f"default_sample_rate={device.default_sample_rate:.0f}"
            )
    else:
        lines.append("  none detected")

    lines.extend(
        [
            f"selected/default microphone: {selected.name if selected else 'none'}",
            f"selected device warning: {report.selected_device_warning or 'none'}",
            f"stream opened: {_yes_no(report.stream_opened)}",
            "",
            "Audio capture and VAD:",
            f"  calibration silence: {report.calibration_seconds:.1f}s",
            f"  speech sample: {report.speech_seconds:.1f}s",
            f"  calibration RMS: {report.audio.calibration_rms:.6f}",
            f"  average RMS: {report.audio.average_rms:.6f}",
            f"  max RMS: {report.audio.max_rms:.6f}",
            f"  noise floor: {report.audio.noise_floor:.6f}",
            f"  signal-to-noise ratio: {_format_snr(report.audio.signal_to_noise_db)}",
            f"  clipping check: {'CLIPPING' if report.audio.clipping else 'ok'}",
            f"  VAD threshold: {report.audio.vad_threshold:.6f}",
            f"  effective VAD threshold: {report.audio.effective_vad_threshold:.6f}",
            f"  VAD crossed: {_yes_no(report.audio.vad_crossed)}",
            f"  VAD trigger time: {_format_seconds(report.audio.vad_trigger_seconds)}",
            "",
            "Wake detection test:",
            f"  provider: {report.wake_provider}",
            f"  model: {report.wake_model_name}",
            f"  model available: {_yes_no(report.wake_model_available)}",
            f"  wake score: {report.wake_score:.3f}",
            f"  matched phrase: {report.wake_matched_phrase or '<none>'}",
            f"  decision: {report.wake_decision}",
            "",
            "STT test:",
            f"  provider: {report.stt_provider}",
            f"  provider available: {_yes_no(report.stt_provider_available)}",
            f"  model name: {report.stt_model_name}",
            f"  raw transcript: {report.raw_transcript or '<empty>'}",
            f"  transcript confidence: {_format_optional_confidence(report.transcript_confidence)}",
            f"  transcription time: {report.transcription_seconds:.3f}s",
            "",
            "Command cleaning/repair test:",
            f"  clean transcript: {report.clean_transcript or '<empty>'}",
            f"  repaired transcript: {report.repaired_transcript or '<empty>'}",
            f"  repair confidence: {report.repair_confidence:.2f}",
            f"  repair strategy: {report.repair_strategy}",
            f"  command accepted: {_yes_no(report.command_accepted)}",
        ]
    )
    if report.errors:
        lines.extend(["", "Errors:"])
        lines.extend(f"  - {error}" for error in report.errors)
    if report.warnings:
        lines.extend(["", "Warnings:"])
        lines.extend(f"  - {warning}" for warning in report.warnings)
    lines.extend(
        [
            "",
            f"DIAGNOSIS: {report.diagnosis}",
            f"RECOMMENDED NEXT ACTION: {report.recommended_action}",
        ]
    )
    return "\n".join(lines)


def _stt_failed(signals: VoiceHealthSignals) -> bool:
    return bool(
        not signals.stt_provider_available
        or signals.stt_error
        or not signals.raw_transcript.strip()
        or (
            signals.transcript_confidence is not None
            and signals.transcript_confidence < MIN_TRANSCRIPT_CONFIDENCE
        )
    )


def _list_input_devices(sd: Any) -> list[AudioDeviceInfo]:
    devices: list[AudioDeviceInfo] = []
    for index, device in enumerate(sd.query_devices()):
        channels = int(device.get("max_input_channels", 0))
        if channels > 0:
            devices.append(
                AudioDeviceInfo(
                    index=index,
                    name=str(device.get("name", "Unknown input device")),
                    input_channels=channels,
                    default_sample_rate=float(device.get("default_samplerate", 0.0)),
                )
            )
    return devices


def _select_input_device(
    sd: Any,
    devices: list[AudioDeviceInfo],
    preferred: str = "",
) -> tuple[AudioDeviceInfo | None, str | None]:
    if not devices:
        return None, None

    preferred_value = preferred.strip()
    if preferred_value:
        preferred_device = _find_preferred_input_device(devices, preferred_value)
        if preferred_device is not None:
            return preferred_device, None
        selection_warning = (
            f"Configured VOICE_INPUT_DEVICE '{preferred_value}' was not found; using the Windows default input."
        )
    else:
        selection_warning = None

    default = getattr(getattr(sd, "default", None), "device", None)
    default_input = default[0] if isinstance(default, (list, tuple)) and default else default
    try:
        default_index = int(default_input)
    except (TypeError, ValueError):
        default_index = -1
    selected = next((device for device in devices if device.index == default_index), devices[0])
    return selected, selection_warning


def _find_preferred_input_device(
    devices: list[AudioDeviceInfo],
    preferred: str,
) -> AudioDeviceInfo | None:
    try:
        preferred_index = int(preferred)
    except ValueError:
        preferred_index = None
    if preferred_index is not None:
        return next((device for device in devices if device.index == preferred_index), None)

    normalized = preferred.casefold()
    exact = next((device for device in devices if device.name.casefold() == normalized), None)
    if exact is not None:
        return exact
    return next((device for device in devices if normalized in device.name.casefold()), None)


def _selected_device_name_warning(device: AudioDeviceInfo | None) -> str | None:
    if device is None:
        return None
    name = device.name.casefold()
    suspicious_names = (
        "microsoft sound mapper",
        "stereo mix",
        "pc speaker",
        "speakers",
        "speaker output",
        "audio output",
        "hdmi output",
        "display audio",
    )
    if any(value in name for value in suspicious_names):
        return (
            f"'{device.name}' may be a mapper, loopback, speaker, or output device rather than the real microphone. "
            "Set VOICE_INPUT_DEVICE to the microphone name or input-device index."
        )
    return None


def _input_quality_warnings(signals: VoiceHealthSignals) -> list[str]:
    warnings: list[str] = []
    if signals.average_rms < MIN_AVERAGE_RMS:
        warnings.append(
            f"Average RMS {signals.average_rms:.6f} is below the weak-input threshold {MIN_AVERAGE_RMS:.3f}."
        )
    if signals.max_rms < MIN_MAX_RMS:
        warnings.append(f"Max RMS {signals.max_rms:.6f} is below the weak-input threshold {MIN_MAX_RMS:.3f}.")
    if signals.signal_to_noise_db < MIN_SIGNAL_TO_NOISE_DB:
        warnings.append(
            f"Signal-to-noise ratio {signals.signal_to_noise_db:.2f} dB is below the required "
            f"{MIN_SIGNAL_TO_NOISE_DB:.0f} dB."
        )
    if signals.calibration_contaminated:
        warnings.append(
            "Calibration may have captured noise or speech because silence RMS is close to speech RMS; "
            "repeat the check and remain silent during calibration."
        )
    if _vad_trigger_is_late(signals.vad_trigger_seconds, signals.speech_seconds):
        fraction = signals.vad_trigger_seconds / signals.speech_seconds
        warnings.append(
            f"VAD triggered at {signals.vad_trigger_seconds:.2f}s ({fraction:.0%} of the speech sample); "
            "speech was detected very late."
        )
    return warnings


def _has_nonfatal_input_warning(signals: VoiceHealthSignals) -> bool:
    return bool(
        signals.signal_to_noise_db < MIN_SIGNAL_TO_NOISE_DB
        or signals.calibration_contaminated
        or _vad_trigger_is_late(signals.vad_trigger_seconds, signals.speech_seconds)
    )


def _vad_trigger_is_late(trigger_seconds: float | None, speech_seconds: float) -> bool:
    return bool(
        trigger_seconds is not None
        and speech_seconds > 0.0
        and trigger_seconds > speech_seconds * LATE_VAD_TRIGGER_FRACTION
    )


def _join_warnings(*warnings: str | None) -> str | None:
    present = [warning for warning in warnings if warning]
    return " ".join(present) if present else None


def _flatten_samples(recording: Any) -> list[float]:
    if hasattr(recording, "reshape"):
        return [float(value) for value in recording.reshape(-1)]
    samples: list[float] = []
    for value in recording:
        if isinstance(value, (list, tuple)):
            samples.extend(float(item) for item in value)
        else:
            samples.append(float(value))
    return samples


def _detect_openwakeword_sample(provider: Any, samples: list[float], settings: AppSettings) -> WakeDetectionResult:
    chunk_size = max(1, int(settings.voice_sample_rate * settings.openwakeword_listen_chunk_ms / 1000.0))
    best = _empty_wake_detection(settings)
    for start in range(0, len(samples), chunk_size):
        chunk = samples[start : start + chunk_size]
        if len(chunk) < chunk_size:
            chunk.extend([0.0] * (chunk_size - len(chunk)))
        result = provider.detect(chunk, settings.voice_sample_rate)
        if result.score > best.score:
            best = result
        if result.detected:
            return result
    return best


def _empty_wake_detection(settings: AppSettings) -> WakeDetectionResult:
    threshold = (
        settings.openwakeword_threshold
        if settings.wake_provider == "openwakeword"
        else settings.wake_match_threshold
    )
    return WakeDetectionResult(
        detected=False,
        transcript="",
        matched_phrase=None,
        score=0.0,
        threshold=threshold,
        match_type="none",
    )


def _signal_to_noise_db(signal_rms: float, noise_floor: float) -> float:
    if signal_rms <= 0.0:
        return 0.0
    if noise_floor <= 0.0:
        return math.inf
    return 20.0 * math.log10(signal_rms / noise_floor)


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(max(0.0, float(value)) for value in values)
    index = int((len(ordered) - 1) * max(0.0, min(1.0, percentile)))
    return ordered[index]


def _format_snr(value: float) -> str:
    return "infinite (zero measured noise)" if math.isinf(value) else f"{value:.2f} dB"


def _format_seconds(value: float | None) -> str:
    return "<none>" if value is None else f"{value:.2f}s"


def _format_optional_confidence(value: float | None) -> str:
    return "<unknown>" if value is None else f"{value:.2f}"


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
