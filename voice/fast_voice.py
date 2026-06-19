from __future__ import annotations

import importlib
import math
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from assistant.core import AssistantCore, AssistantResponse
from config.settings import AppSettings
from services.logging_service import add_managed_file_sink
from voice.command_capture import (
    calculate_effective_vad_threshold,
    calculate_rms,
    estimate_noise_floor,
)
from voice.command_validation import CommandValidationResult, validate_cleaned_command
from voice.interfaces import TranscriptionResult
from voice.speech_repair import SpeechRepairResult, SpeechRepairer
from voice.stt import create_speech_to_text_provider
from voice.tts import TextToSpeechResult, speak_text
from voice.wake import remove_wake_phrase_prefix


FAST_VOICE_EXIT_WORDS = {"exit fast voice", "quit fast voice", "stop fast voice"}
CLAP_WAIT_SECONDS = 15.0
CLAP_MIN_RMS = 0.04
CLAP_MIN_PEAK = 0.15

AudioRecorder = Callable[[], tuple[list[float], str]]
TtsFunction = Callable[..., TextToSpeechResult]


@dataclass(frozen=True)
class FastVoiceTiming:
    capture_ms: float = 0.0
    transcribe_ms: float = 0.0
    openai_ms: float = 0.0
    tts_ms: float = 0.0
    total_ms: float = 0.0

    def format(self) -> str:
        return " ".join(
            (
                f"capture_ms={self.capture_ms:.1f}",
                f"transcribe_ms={self.transcribe_ms:.1f}",
                f"openai_ms={self.openai_ms:.1f}",
                f"tts_ms={self.tts_ms:.1f}",
                f"total_ms={self.total_ms:.1f}",
            )
        )


@dataclass(frozen=True)
class FastVoiceReport:
    activation: str
    input_device: str
    provider_name: str
    provider_available: bool
    raw_transcript: str
    cleaned_transcript: str
    speech_repair: SpeechRepairResult | None
    validation: CommandValidationResult
    assistant_response: AssistantResponse | None
    tts_result: TextToSpeechResult | None
    timing: FastVoiceTiming
    log_file: Path
    errors: list[str] = field(default_factory=list)

    @property
    def command(self) -> str:
        if self.speech_repair is not None:
            return self.speech_repair.repaired_transcript
        return self.cleaned_transcript

    @property
    def is_successful(self) -> bool:
        return bool(
            self.provider_available
            and self.validation.accepted
            and self.assistant_response is not None
            and self.assistant_response.accepted
            and not self.errors
        )


class FastVoiceRunner:
    """Low-latency one-command capture beside the full wake-based voice loop."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        assistant: AssistantCore | None = None,
        provider: Any | None = None,
        sounddevice_module: Any | None = None,
        recorder: AudioRecorder | None = None,
        tts_function: TtsFunction = speak_text,
        input_func: Callable[[str], str] = input,
        output_func: Callable[[str], None] = print,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.settings = settings
        self.assistant = assistant or AssistantCore(settings=settings)
        self.provider = provider or create_speech_to_text_provider(settings)
        self.sounddevice_module = sounddevice_module
        self.recorder = recorder
        self.tts_function = tts_function
        self.input_func = input_func
        self.output_func = output_func
        self.clock = clock
        self.log_file = self.settings.log_dir / "fast_voice.log"
        self.fast_logger = logger.bind(fast_voice=True)
        add_managed_file_sink(
            self.log_file,
            level="DEBUG",
            filter=lambda record: bool(record["extra"].get("fast_voice")),
        )

    def run(self, *, max_turns: int | None = None) -> int:
        if not self.settings.fast_voice_enabled:
            self.output_func("Fast voice is disabled. Set FAST_VOICE_ENABLED=true to enable it.")
            return 1

        activation = self.settings.fast_voice_activation
        self.output_func(
            f"Jarvis fast voice ready | activation={activation} | "
            f"TTS={'on' if self.settings.fast_voice_tts_enabled else 'off'}"
        )
        completed = 0
        while max_turns is None or completed < max_turns:
            if activation == "enter":
                action = self.input_func("Press Enter to speak, or type q to quit: ").strip().lower()
                if action in {"q", "quit", "exit"}:
                    return 0
            elif activation == "clap":
                self.output_func("Waiting for a clap...")
                if not self._wait_for_clap():
                    self.output_func("No clap detected before timeout.")
                    return 1

            report = self.run_once()
            self.output_func(format_fast_voice_report(report))
            completed += 1
            if report.command.strip().lower() in FAST_VOICE_EXIT_WORDS:
                return 0
            if activation == "direct":
                return 0 if report.is_successful else 1

        return 0

    def run_once(self) -> FastVoiceReport:
        total_started = self.clock()
        errors: list[str] = []
        input_device = "unavailable"
        raw_transcript = ""
        cleaned_transcript = ""
        repair: SpeechRepairResult | None = None
        assistant_response: AssistantResponse | None = None
        tts_result: TextToSpeechResult | None = None
        capture_ms = 0.0
        transcribe_ms = 0.0
        openai_ms = 0.0
        tts_ms = 0.0
        validation = self._validate("")

        if not self.provider.available:
            errors.append("Speech-to-text provider is not available.")
            return self._report(
                input_device,
                raw_transcript,
                cleaned_transcript,
                repair,
                validation,
                assistant_response,
                tts_result,
                capture_ms,
                transcribe_ms,
                openai_ms,
                tts_ms,
                total_started,
                errors,
            )

        self.output_func("Listening...")
        capture_started = self.clock()
        try:
            if self.recorder is not None:
                samples, input_device = self.recorder()
            else:
                samples, input_device = self._capture_until_silence()
        except Exception as exc:
            errors.append(f"Fast voice capture failed: {type(exc).__name__}: {exc}")
            samples = []
        capture_ms = (self.clock() - capture_started) * 1000.0

        if samples:
            transcribe_started = self.clock()
            try:
                transcription: TranscriptionResult = self.provider.transcribe(
                    samples,
                    self.settings.voice_sample_rate,
                )
                raw_transcript = transcription.text.strip()
            except Exception as exc:
                errors.append(f"Fast voice transcription failed: {type(exc).__name__}: {exc}")
            transcribe_ms = (self.clock() - transcribe_started) * 1000.0

        cleaned_transcript = remove_wake_phrase_prefix(
            raw_transcript,
            wake_phrase=self.settings.wake_phrase,
            aliases=self.settings.wake_alias_list,
        )
        repair = SpeechRepairer(self.settings).repair(
            cleaned_transcript,
            raw_transcript=raw_transcript,
        )
        validation = self._validate(repair.repaired_transcript)

        if validation.accepted:
            assistant_started = self.clock()
            try:
                assistant_response = self.assistant.handle_voice_command(repair.repaired_transcript)
            except Exception as exc:
                errors.append(f"Assistant handling failed: {type(exc).__name__}: {exc}")
            openai_ms = (self.clock() - assistant_started) * 1000.0

            if assistant_response is not None:
                self.output_func(f"Jarvis: {assistant_response.text}")
                if assistant_response.accepted and self.settings.fast_voice_tts_enabled:
                    tts_started = self.clock()
                    tts_result = self.tts_function(
                        assistant_response.text,
                        self.settings,
                        speak_requested=True,
                    )
                    tts_ms = (self.clock() - tts_started) * 1000.0
                    if tts_result.error:
                        errors.append(tts_result.error)
        else:
            self.output_func(
                f"Command rejected: {validation.rejection_reason or 'no usable speech detected'}"
            )

        return self._report(
            input_device,
            raw_transcript,
            cleaned_transcript,
            repair,
            validation,
            assistant_response,
            tts_result,
            capture_ms,
            transcribe_ms,
            openai_ms,
            tts_ms,
            total_started,
            errors,
        )

    def _capture_until_silence(self) -> tuple[list[float], str]:
        sd = self.sounddevice_module or _require_sounddevice()
        device_index, device_name = resolve_fast_input_device(sd, self.settings.voice_input_device)
        sample_rate = self.settings.voice_sample_rate
        channels = self.settings.voice_channels
        window_ms = min(self.settings.voice_vad_window_ms, 80)
        chunk_frames = max(1, int(sample_rate * window_ms / 1000.0))
        max_frames = max(1, int(sample_rate * self.settings.fast_voice_record_seconds))
        silence_chunks_needed = max(1, math.ceil(self.settings.fast_voice_silence_ms / window_ms))
        minimum_speech_chunks = max(1, math.ceil(240 / window_ms))
        samples: list[float] = []
        levels: list[float] = []
        frames_read = 0
        triggered = False
        chunks_after_trigger = 0
        trailing_silence_chunks = 0

        sd.check_input_settings(device=device_index, samplerate=sample_rate, channels=channels)
        with sd.InputStream(
            device=device_index,
            samplerate=sample_rate,
            channels=channels,
            dtype="float32",
        ) as stream:
            while frames_read < max_frames:
                frames_to_read = min(chunk_frames, max_frames - frames_read)
                recording, _overflowed = stream.read(frames_to_read)
                chunk = _flatten_samples(recording)
                if not chunk:
                    break
                frames_read += frames_to_read
                samples.extend(chunk)
                chunk_rms = calculate_rms(chunk)
                levels.append(chunk_rms)
                noise_floor = estimate_noise_floor(levels)
                if noise_floor <= 0.0 and levels:
                    noise_floor = min(levels)
                threshold = calculate_effective_vad_threshold(
                    self.settings.voice_vad_threshold,
                    noise_floor,
                    noise_multiplier=self.settings.voice_vad_noise_multiplier,
                )
                if chunk_rms >= threshold:
                    triggered = True
                    trailing_silence_chunks = 0
                elif triggered:
                    trailing_silence_chunks += 1

                if triggered:
                    chunks_after_trigger += 1
                    if (
                        chunks_after_trigger >= minimum_speech_chunks
                        and trailing_silence_chunks >= silence_chunks_needed
                    ):
                        break

        self.fast_logger.info(
            "Fast capture device={} samples={} triggered={} max_seconds={} silence_ms={}",
            device_name,
            len(samples),
            triggered,
            self.settings.fast_voice_record_seconds,
            self.settings.fast_voice_silence_ms,
        )
        return samples, device_name

    def _wait_for_clap(self) -> bool:
        sd = self.sounddevice_module or _require_sounddevice()
        device_index, _device_name = resolve_fast_input_device(sd, self.settings.voice_input_device)
        sample_rate = self.settings.voice_sample_rate
        channels = self.settings.voice_channels
        chunk_ms = 50
        chunk_frames = max(1, int(sample_rate * chunk_ms / 1000.0))
        max_chunks = max(1, math.ceil(CLAP_WAIT_SECONDS * 1000 / chunk_ms))
        rms_threshold = max(CLAP_MIN_RMS, self.settings.voice_vad_threshold * 10.0)

        sd.check_input_settings(device=device_index, samplerate=sample_rate, channels=channels)
        with sd.InputStream(
            device=device_index,
            samplerate=sample_rate,
            channels=channels,
            dtype="float32",
        ) as stream:
            for _ in range(max_chunks):
                recording, _overflowed = stream.read(chunk_frames)
                chunk = _flatten_samples(recording)
                if not chunk:
                    continue
                peak = max(abs(value) for value in chunk)
                if calculate_rms(chunk) >= rms_threshold and peak >= CLAP_MIN_PEAK:
                    self.output_func("Clap detected. Speak now.")
                    return True
        return False

    def _validate(self, command: str) -> CommandValidationResult:
        return validate_cleaned_command(
            command,
            min_words=self.settings.voice_command_min_words,
            reject_phrases=self.settings.voice_command_reject_phrase_list,
            incomplete_phrases=self.settings.voice_command_incomplete_phrase_list,
        )

    def _report(
        self,
        input_device: str,
        raw_transcript: str,
        cleaned_transcript: str,
        repair: SpeechRepairResult | None,
        validation: CommandValidationResult,
        assistant_response: AssistantResponse | None,
        tts_result: TextToSpeechResult | None,
        capture_ms: float,
        transcribe_ms: float,
        openai_ms: float,
        tts_ms: float,
        total_started: float,
        errors: list[str],
    ) -> FastVoiceReport:
        timing = FastVoiceTiming(
            capture_ms=capture_ms,
            transcribe_ms=transcribe_ms,
            openai_ms=openai_ms,
            tts_ms=tts_ms,
            total_ms=(self.clock() - total_started) * 1000.0,
        )
        self.fast_logger.info(
            "Fast voice command={} accepted={} response_source={} {}",
            repair.repaired_transcript if repair else "<empty>",
            validation.accepted,
            assistant_response.source if assistant_response else "none",
            timing.format(),
        )
        return FastVoiceReport(
            activation=self.settings.fast_voice_activation,
            input_device=input_device,
            provider_name=self.provider.name,
            provider_available=bool(self.provider.available),
            raw_transcript=raw_transcript,
            cleaned_transcript=cleaned_transcript,
            speech_repair=repair,
            validation=validation,
            assistant_response=assistant_response,
            tts_result=tts_result,
            timing=timing,
            log_file=self.log_file,
            errors=errors,
        )


def run_fast_command_test(
    settings: AppSettings,
    *,
    assistant: AssistantCore | None = None,
) -> FastVoiceReport:
    return FastVoiceRunner(settings, assistant=assistant).run_once()


def resolve_fast_input_device(sd: Any, preferred: str) -> tuple[int, str]:
    devices = sd.query_devices()
    inputs: list[tuple[int, str]] = []
    for index, device in enumerate(devices):
        if int(device.get("max_input_channels", 0)) > 0:
            inputs.append((index, str(device.get("name", f"Input device {index}"))))
    if not inputs:
        raise RuntimeError("No microphone input device was detected.")

    selector = preferred.strip()
    if selector:
        try:
            preferred_index = int(selector)
        except ValueError:
            preferred_index = None
        if preferred_index is not None:
            match = next((item for item in inputs if item[0] == preferred_index), None)
        else:
            normalized = selector.casefold()
            match = next((item for item in inputs if item[1].casefold() == normalized), None)
            if match is None:
                match = next((item for item in inputs if normalized in item[1].casefold()), None)
        if match is None:
            raise RuntimeError(f"Configured VOICE_INPUT_DEVICE '{selector}' was not found.")
        return match

    default = getattr(getattr(sd, "default", None), "device", None)
    default_input = default[0] if isinstance(default, (list, tuple)) and default else default
    try:
        default_index = int(default_input)
    except (TypeError, ValueError):
        default_index = -1
    return next((item for item in inputs if item[0] == default_index), inputs[0])


def format_fast_voice_report(report: FastVoiceReport) -> str:
    repair = report.speech_repair
    lines = [
        "Jarvis Fast Voice Command",
        "=========================",
        f"activation: {report.activation}",
        f"input device: {report.input_device}",
        f"STT provider: {report.provider_name}",
        f"provider available: {_yes_no(report.provider_available)}",
        f"raw transcript: {report.raw_transcript or '<empty>'}",
        f"cleaned transcript: {report.cleaned_transcript or '<empty>'}",
        f"repaired command: {report.command or '<empty>'}",
        f"repair strategy: {repair.strategy if repair else '<none>'}",
        f"command accepted: {_yes_no(report.validation.accepted)}",
    ]
    if report.validation.rejection_reason:
        lines.append(f"rejection reason: {report.validation.rejection_reason}")
    if report.assistant_response is not None:
        lines.extend(
            [
                f"response source: {report.assistant_response.source}",
                f"response: {report.assistant_response.text}",
            ]
        )
    lines.extend(
        [
            f"TTS enabled: {_yes_no(report.tts_result is not None)}",
            f"timing: {report.timing.format()}",
            f"diagnostic log: {report.log_file}",
        ]
    )
    if report.errors:
        lines.extend(["", "Errors:"])
        lines.extend(f"  - {error}" for error in report.errors)
    return "\n".join(lines)


def _require_sounddevice() -> Any:
    try:
        return importlib.import_module("sounddevice")
    except Exception as exc:
        raise RuntimeError(f"sounddevice is required for fast voice mode: {exc}") from exc


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


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
