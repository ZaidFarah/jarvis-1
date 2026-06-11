from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from math import sqrt
from pathlib import Path
from typing import Any

from loguru import logger

from config.settings import AppSettings
from voice.tts import Pyttsx3TextToSpeechProvider
from voice.vad import RmsVoiceActivityDetector


_AUDIO_LOG_SINK_ID: int | None = None


@dataclass(frozen=True)
class AudioDeviceInfo:
    index: int
    name: str
    input_channels: int
    default_sample_rate: float


@dataclass(frozen=True)
class MicrophoneTestResult:
    microphone_detected: bool
    stream_opened: bool
    rms: float
    max_rms: float
    vad_threshold_crossed: bool
    sample_rate: int
    channels: int
    duration_seconds: float
    error: str | None = None


@dataclass(frozen=True)
class AudioDiagnosticsReport:
    sounddevice_available: bool
    input_devices: list[AudioDeviceInfo]
    default_input_device: AudioDeviceInfo | None
    microphone_test: MicrophoneTestResult | None
    tts_provider_available: bool
    errors: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    log_file: Path | None = None

    @property
    def is_successful(self) -> bool:
        return bool(
            self.sounddevice_available
            and self.input_devices
            and self.microphone_test
            and self.microphone_test.stream_opened
        )


class AudioDiagnostics:
    """Microphone and local audio diagnostics for Phase 2.5."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.log_file = self.settings.log_dir / "audio_diagnostics.log"
        self.audio_logger = logger.bind(audio_diagnostics=True)
        self._ensure_audio_log_sink()

    def run_full_check(self) -> AudioDiagnosticsReport:
        self.audio_logger.info("Running Jarvis audio diagnostics")
        errors: list[str] = []
        sd = self._load_sounddevice()
        sounddevice_available = sd is not None

        if sd is None:
            message = "sounddevice is not available; microphone stream test cannot run."
            self.audio_logger.error(message)
            errors.append(message)
            report = AudioDiagnosticsReport(
                sounddevice_available=False,
                input_devices=[],
                default_input_device=None,
                microphone_test=None,
                tts_provider_available=Pyttsx3TextToSpeechProvider().available,
                errors=errors,
                log_file=self.log_file,
            )
            return self._with_suggestions(report)

        try:
            input_devices = self.list_input_devices(sd)
        except Exception as exc:
            message = f"Failed to query audio devices: {exc}"
            self.audio_logger.exception(message)
            errors.append(message)
            input_devices = []

        default_input = self.get_default_input_device(sd, input_devices)
        microphone_test = self.run_microphone_test(sd=sd) if input_devices else None

        report = AudioDiagnosticsReport(
            sounddevice_available=sounddevice_available,
            input_devices=input_devices,
            default_input_device=default_input,
            microphone_test=microphone_test,
            tts_provider_available=Pyttsx3TextToSpeechProvider().available,
            errors=errors,
            log_file=self.log_file,
        )
        return self._with_suggestions(report)

    def list_input_devices(self, sd: Any | None = None) -> list[AudioDeviceInfo]:
        sd = sd or self._require_sounddevice()
        devices = sd.query_devices()
        input_devices: list[AudioDeviceInfo] = []

        for index, device in enumerate(devices):
            channels = int(device.get("max_input_channels", 0))
            if channels <= 0:
                continue
            input_devices.append(
                AudioDeviceInfo(
                    index=index,
                    name=str(device.get("name", "Unknown input device")),
                    input_channels=channels,
                    default_sample_rate=float(device.get("default_samplerate", 0.0)),
                )
            )

        self.audio_logger.info("Detected {} microphone input device(s)", len(input_devices))
        return input_devices

    def get_default_input_device(
        self,
        sd: Any | None = None,
        input_devices: list[AudioDeviceInfo] | None = None,
    ) -> AudioDeviceInfo | None:
        sd = sd or self._require_sounddevice()
        input_devices = input_devices if input_devices is not None else self.list_input_devices(sd)
        if not input_devices:
            return None

        default_index = self._default_input_index(sd)
        for device in input_devices:
            if device.index == default_index:
                return device

        return input_devices[0]

    def run_microphone_test(self, sd: Any | None = None) -> MicrophoneTestResult:
        sd = sd or self._require_sounddevice()
        sample_rate = self.settings.voice_sample_rate
        channels = self.settings.voice_channels
        duration = self.settings.voice_record_seconds
        frames = int(sample_rate * duration)

        self.audio_logger.info(
            "Testing microphone stream: sample_rate={} channels={} duration={}",
            sample_rate,
            channels,
            duration,
        )

        try:
            sd.check_input_settings(samplerate=sample_rate, channels=channels)
            recording = sd.rec(frames, samplerate=sample_rate, channels=channels, dtype="float32")
            sd.wait()
            samples = self._flatten_samples(recording)
            rms = self._calculate_rms(samples)
            max_rms = self._calculate_max_rms(samples, sample_rate)
            vad = RmsVoiceActivityDetector(self.settings.voice_vad_threshold)
            vad_result = vad.analyze([max_rms], sample_rate)
            self.audio_logger.info(
                "Microphone stream opened. avg_rms={} max_rms={} threshold={} crossed={}",
                f"{rms:.6f}",
                f"{max_rms:.6f}",
                self.settings.voice_vad_threshold,
                vad_result.is_speech,
            )
            return MicrophoneTestResult(
                microphone_detected=True,
                stream_opened=True,
                rms=rms,
                max_rms=max_rms,
                vad_threshold_crossed=vad_result.is_speech,
                sample_rate=sample_rate,
                channels=channels,
                duration_seconds=duration,
            )
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            self.audio_logger.exception("Microphone stream test failed: {}", message)
            return MicrophoneTestResult(
                microphone_detected=bool(self.list_input_devices(sd)),
                stream_opened=False,
                rms=0.0,
                max_rms=0.0,
                vad_threshold_crossed=False,
                sample_rate=sample_rate,
                channels=channels,
                duration_seconds=duration,
                error=message,
            )

    @staticmethod
    def _load_sounddevice() -> Any | None:
        try:
            return importlib.import_module("sounddevice")
        except Exception:
            return None

    @classmethod
    def _require_sounddevice(cls) -> Any:
        sd = cls._load_sounddevice()
        if sd is None:
            raise RuntimeError("sounddevice is not installed.")
        return sd

    @staticmethod
    def _default_input_index(sd: Any) -> int | None:
        default_device = getattr(sd, "default", None)
        device = getattr(default_device, "device", None)
        if isinstance(device, (list, tuple)) and device:
            value = device[0]
        else:
            value = device

        try:
            index = int(value)
        except (TypeError, ValueError):
            return None

        return index if index >= 0 else None

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

    def _ensure_audio_log_sink(self) -> None:
        global _AUDIO_LOG_SINK_ID
        if _AUDIO_LOG_SINK_ID is not None:
            return

        self.settings.log_dir.mkdir(parents=True, exist_ok=True)
        _AUDIO_LOG_SINK_ID = logger.add(
            self.log_file,
            level="DEBUG",
            rotation="1 MB",
            retention="7 days",
            encoding="utf-8",
            backtrace=False,
            diagnose=False,
            filter=lambda record: bool(record["extra"].get("audio_diagnostics")),
        )

    def _with_suggestions(self, report: AudioDiagnosticsReport) -> AudioDiagnosticsReport:
        suggestions = build_audio_suggestions(report)
        return AudioDiagnosticsReport(
            sounddevice_available=report.sounddevice_available,
            input_devices=report.input_devices,
            default_input_device=report.default_input_device,
            microphone_test=report.microphone_test,
            tts_provider_available=report.tts_provider_available,
            errors=report.errors,
            suggestions=suggestions,
            log_file=report.log_file,
        )


def format_audio_check_report(report: AudioDiagnosticsReport) -> str:
    lines = [
        "Jarvis Audio Check",
        "==================",
        f"sounddevice available: {_yes_no(report.sounddevice_available)}",
        f"pyttsx3 TTS available: {_yes_no(report.tts_provider_available)}",
        f"diagnostic log: {report.log_file if report.log_file else 'not configured'}",
        f"default microphone: {report.default_input_device.name if report.default_input_device else 'none'}",
        "",
        "Input devices:",
    ]

    if report.input_devices:
        for device in report.input_devices:
            default_marker = " (default)" if report.default_input_device and device.index == report.default_input_device.index else ""
            lines.append(
                f"  [{device.index}] {device.name}{default_marker} | "
                f"channels={device.input_channels} | default_sample_rate={device.default_sample_rate:.0f}"
            )
    else:
        lines.append("  none detected")

    if report.microphone_test is not None:
        test = report.microphone_test
        lines.extend(
            [
                "",
                "Microphone test:",
                f"  microphone detected: {_yes_no(test.microphone_detected)}",
                f"  stream opened: {'ok' if test.stream_opened else 'failed'}",
                f"  sample rate: {test.sample_rate}",
                f"  channels: {test.channels}",
                f"  duration: {test.duration_seconds:.2f}s",
                f"  average RMS level: {test.rms:.6f}",
                f"  max RMS level: {test.max_rms:.6f}",
                f"  VAD threshold crossed: {_yes_no(test.vad_threshold_crossed)}",
            ]
        )
        if test.error:
            lines.append(f"  error: {test.error}")
    else:
        lines.extend(["", "Microphone test:", "  not run"])

    if report.errors:
        lines.append("")
        lines.append("Errors:")
        lines.extend(f"  - {error}" for error in report.errors)

    if report.suggestions:
        lines.append("")
        lines.append("Suggestions:")
        lines.extend(f"  - {suggestion}" for suggestion in report.suggestions)

    return "\n".join(lines)


def format_microphone_test_summary(report: AudioDiagnosticsReport) -> str:
    mic_name = report.default_input_device.name if report.default_input_device else "none"
    if report.microphone_test is None:
        base = f"Microphone test did not run. Default microphone: {mic_name}."
    else:
        test = report.microphone_test
        crossed = _yes_no(test.vad_threshold_crossed)
        state = "opened" if test.stream_opened else "failed"
        base = (
            f"Default microphone: {mic_name}. Stream {state}. "
            f"Sample rate: {test.sample_rate}. Max RMS: {test.max_rms:.6f}. "
            f"VAD threshold crossed: {crossed}."
        )
        if test.error:
            base = f"{base} Error: {test.error}."

    if report.suggestions:
        return f"{base} Suggestion: {report.suggestions[0]}"
    return base


def build_audio_suggestions(report: AudioDiagnosticsReport) -> list[str]:
    suggestions: list[str] = []

    if not report.sounddevice_available:
        suggestions.append("Install or repair the sounddevice package, then run python main.py --audio-check again.")
        return suggestions

    if not report.input_devices:
        suggestions.extend(
            [
                "No microphone input device was detected. Connect or enable a microphone in Windows Settings > System > Sound > Input.",
                "Check Windows microphone privacy permissions and confirm desktop apps can access the microphone.",
            ]
        )
        return suggestions

    test = report.microphone_test
    if test is None:
        suggestions.append("A microphone was listed, but the stream test did not run. Re-run python main.py --audio-check.")
        return suggestions

    if not test.stream_opened:
        suggestions.append(
            "The microphone was detected but the stream did not open. Try a different sample rate or check whether another app is using the microphone."
        )
        return suggestions

    if not test.vad_threshold_crossed:
        if test.max_rms > 0:
            suggested_threshold = max(test.max_rms * 0.6, 0.0001)
            suggestions.append(
                "Your microphone is working, but input volume did not cross the current VAD threshold. "
                f"Try VOICE_VAD_THRESHOLD={suggested_threshold:.4f} or increase Windows microphone input volume."
            )
        else:
            suggestions.append(
                "The microphone stream opened, but no input level was detected. Unmute the microphone and increase Windows input volume."
            )

    return suggestions


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
