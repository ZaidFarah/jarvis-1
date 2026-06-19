from __future__ import annotations

import importlib
import math
import re
import threading
import time
from collections import deque
from collections.abc import Callable, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
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
SHORT_COMMAND_SPEECH_MS = 1000.0

@dataclass(frozen=True)
class FastCaptureResult:
    samples: list[float]
    input_device: str
    vad_wait_ms: float = 0.0
    speech_ms: float = 0.0
    trailing_silence_ms: float = 0.0
    vad_crossed: bool = False
    audio_record_ms: float | None = None
    audio_prepare_ms: float = 0.0


AudioRecorder = Callable[[], FastCaptureResult | tuple[list[float], str]]
TtsFunction = Callable[..., TextToSpeechResult]


@dataclass(frozen=True)
class FastVoiceTiming:
    capture_ms: float = 0.0
    audio_record_ms: float = 0.0
    audio_prepare_ms: float = 0.0
    stt_warmup_ms: float = 0.0
    vad_wait_ms: float = 0.0
    speech_ms: float = 0.0
    trailing_silence_ms: float = 0.0
    transcribe_ms: float = 0.0
    openai_ms: float = 0.0
    tts_ms: float = 0.0
    total_ms: float = 0.0

    def format(self) -> str:
        return " ".join(
            (
                f"capture_ms={self.capture_ms:.1f}",
                f"audio_record_ms={self.audio_record_ms:.1f}",
                f"audio_prepare_ms={self.audio_prepare_ms:.1f}",
                f"stt_warmup_ms={self.stt_warmup_ms:.1f}",
                f"vad_wait_ms={self.vad_wait_ms:.1f}",
                f"speech_ms={self.speech_ms:.1f}",
                f"trailing_silence_ms={self.trailing_silence_ms:.1f}",
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
    vad_crossed: bool = False
    wake_only: bool = False
    unintelligible_audio: bool = False
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
            and self.command_accepted
            and self.assistant_response is not None
            and self.assistant_response.accepted
            and not self.errors
        )

    @property
    def command_accepted(self) -> bool:
        return self.wake_only or self.validation.accepted


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
        status_callback: Callable[[str], None] | None = None,
        report_callback: Callable[[FastVoiceReport], None] | None = None,
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
        self.status_callback = status_callback
        self.report_callback = report_callback
        self.log_file = self.settings.log_dir / "fast_voice.log"
        self.fast_logger = logger.bind(fast_voice=True)
        self._stt_warm_attempted = False
        self._audio_stream: Any | None = None
        self._audio_device_index: int | None = None
        self._audio_device_name = ""
        self._stop_requested = threading.Event()
        add_managed_file_sink(
            self.log_file,
            level="DEBUG",
            filter=lambda record: bool(record["extra"].get("fast_voice")),
        )

    def run(self, *, max_turns: int | None = None) -> int:
        if not self.settings.fast_voice_enabled:
            self.output_func("Fast voice is disabled. Set FAST_VOICE_ENABLED=true to enable it.")
            return 1

        self._stop_requested.clear()
        stt_warmup_ms = 0.0
        if self.settings.fast_voice_warm_stt_on_start:
            stt_warmup_ms = self._warm_stt()

        audio_session_ms = 0.0
        if self.recorder is None:
            try:
                audio_session_ms = self._open_audio_session()
            except Exception as exc:
                self._close_audio_session()
                self.output_func(
                    f"Fast voice audio session failed: {type(exc).__name__}: {exc}"
                )
                return 1

        activation = self.settings.fast_voice_activation
        self.output_func(
            f"Jarvis fast voice ready | activation={activation} | "
            f"TTS={'on' if self.settings.fast_voice_tts_enabled else 'off'} | "
            f"startup_stt_warmup_ms={stt_warmup_ms:.1f} | "
            f"audio_session_prepare_ms={audio_session_ms:.1f}"
        )
        try:
            completed = 0
            while (
                not self._stop_requested.is_set()
                and (max_turns is None or completed < max_turns)
            ):
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
        finally:
            self._close_audio_session()

    def run_continuous(self, *, max_turns: int | None = None) -> int:
        """Run callback-driven fast voice for GUI and other non-terminal clients."""
        if not self.settings.fast_voice_enabled:
            self._notify_status("Error")
            return 1

        self._stop_requested.clear()
        if self.settings.fast_voice_warm_stt_on_start:
            self._warm_stt()
        failed = False
        try:
            if self.recorder is None:
                self._open_audio_session()
            completed = 0
            while (
                not self._stop_requested.is_set()
                and (max_turns is None or completed < max_turns)
            ):
                report = self.run_once()
                if self.report_callback is not None:
                    self.report_callback(report)
                completed += 1
                if report.errors or not report.provider_available:
                    failed = True
                    self._notify_status("Error")
                    return 1
            return 0
        except Exception:
            failed = True
            self._notify_status("Error")
            raise
        finally:
            self._close_audio_session()
            if not failed:
                self._notify_status("Stopped")

    def request_stop(self) -> None:
        self._stop_requested.set()

    def run_once(self) -> FastVoiceReport:
        if self.settings.fast_voice_warm_stt_on_start:
            self._warm_stt()
        stt_warmup_ms = 0.0
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
        capture_result = FastCaptureResult([], input_device)
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
                stt_warmup_ms=stt_warmup_ms,
                capture_result=capture_result,
            )

        self._notify_status("Listening")
        self.output_func("Listening...")
        capture_started = self.clock()
        try:
            if self.recorder is not None:
                recorded = self.recorder()
                if isinstance(recorded, FastCaptureResult):
                    capture_result = recorded
                else:
                    samples, input_device = recorded
                    capture_result = FastCaptureResult(samples, input_device)
            else:
                capture_result = self._capture_until_silence()
            samples = capture_result.samples
            input_device = capture_result.input_device
        except Exception as exc:
            self._notify_status("Error")
            errors.append(f"Fast voice capture failed: {type(exc).__name__}: {exc}")
            samples = []
        capture_wall_ms = (self.clock() - capture_started) * 1000.0
        if capture_result.audio_record_ms is None:
            capture_result = replace(
                capture_result,
                audio_record_ms=capture_wall_ms if samples else 0.0,
                audio_prepare_ms=0.0 if samples else capture_wall_ms,
            )
        capture_ms = float(capture_result.audio_record_ms or 0.0)

        if samples:
            self._notify_status("Transcribing")
            transcribe_started = self.clock()
            try:
                transcription: TranscriptionResult = self.provider.transcribe(
                    samples,
                    self.settings.voice_sample_rate,
                )
                raw_transcript = transcription.text.strip()
            except Exception as exc:
                self._notify_status("Error")
                errors.append(f"Fast voice transcription failed: {type(exc).__name__}: {exc}")
            transcribe_ms = (self.clock() - transcribe_started) * 1000.0

        cleaned_transcript = remove_wake_phrase_prefix(
            raw_transcript,
            wake_phrase=self.settings.wake_phrase,
            aliases=self.settings.wake_alias_list,
        )
        if capture_result.vad_crossed and not raw_transcript:
            assistant_response = AssistantResponse(
                text=self.settings.fast_voice_empty_audio_response,
                accepted=True,
                source="fast_voice_empty_audio",
            )
            self._notify_status("Responding")
            self.output_func(f"Jarvis: {assistant_response.text}")
            if self.settings.fast_voice_tts_enabled:
                tts_started = self.clock()
                tts_result = self.tts_function(
                    assistant_response.text,
                    self.settings,
                    speak_requested=True,
                )
                tts_ms = (self.clock() - tts_started) * 1000.0
                if tts_result.error:
                    errors.append(tts_result.error)
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
                stt_warmup_ms=stt_warmup_ms,
                unintelligible_audio=True,
                capture_result=capture_result,
            )

        repair = SpeechRepairer(self.settings).repair(
            cleaned_transcript,
            raw_transcript=raw_transcript,
        )
        wake_only = is_wake_only_transcript(raw_transcript, self.settings) or is_wake_only_transcript(
            repair.repaired_transcript,
            self.settings,
        )
        if wake_only:
            assistant_response = AssistantResponse(
                text=self.settings.fast_voice_wake_only_response,
                accepted=True,
                source="fast_voice_wake_only",
            )
            self._notify_status("Responding")
            self.output_func(f"Jarvis: {assistant_response.text}")
            if self.settings.fast_voice_tts_enabled:
                tts_started = self.clock()
                tts_result = self.tts_function(
                    assistant_response.text,
                    self.settings,
                    speak_requested=True,
                )
                tts_ms = (self.clock() - tts_started) * 1000.0
                if tts_result.error:
                    errors.append(tts_result.error)
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
                stt_warmup_ms=stt_warmup_ms,
                wake_only=True,
                capture_result=capture_result,
            )

        validation = self._validate(repair.repaired_transcript)

        if validation.accepted:
            self._notify_status("Thinking")
            assistant_started = self.clock()
            try:
                fast_handler = getattr(self.assistant, "handle_fast_voice_command", None)
                if callable(fast_handler):
                    assistant_response = fast_handler(repair.repaired_transcript)
                else:
                    assistant_response = self.assistant.handle_voice_command(
                        repair.repaired_transcript
                    )
            except Exception as exc:
                self._notify_status("Error")
                errors.append(f"Assistant handling failed: {type(exc).__name__}: {exc}")
            openai_ms = (self.clock() - assistant_started) * 1000.0

            if assistant_response is not None:
                self._notify_status("Responding")
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
            stt_warmup_ms=stt_warmup_ms,
            capture_result=capture_result,
        )

    def _capture_until_silence(self) -> FastCaptureResult:
        capture_work_started = self.clock()
        audio_record_ms = 0.0
        sd = self.sounddevice_module or _require_sounddevice()
        if self._audio_stream is not None:
            device_index = self._audio_device_index
            device_name = self._audio_device_name
            if device_index is None:
                raise RuntimeError("Persistent audio session has no input device.")
        else:
            device_index, device_name = resolve_fast_input_device(
                sd,
                self.settings.voice_input_device,
            )
        sample_rate = self.settings.voice_sample_rate
        channels = self.settings.voice_channels
        window_ms = min(self.settings.voice_vad_window_ms, 80)
        chunk_frames = max(1, int(sample_rate * window_ms / 1000.0))
        max_seconds = min(
            self.settings.fast_voice_record_seconds,
            self.settings.fast_voice_max_seconds,
        )
        max_frames = max(1, int(sample_rate * max_seconds))
        selected_silence_ms = self.settings.fast_voice_silence_ms
        minimum_speech_frames = max(
            1,
            int(sample_rate * self.settings.fast_voice_min_speech_ms / 1000.0),
        )
        preroll_sample_limit = int(
            sample_rate
            * channels
            * self.settings.fast_voice_preroll_ms
            / 1000.0
        )
        preroll_samples: deque[float] = deque(maxlen=preroll_sample_limit)
        samples: list[float] = []
        levels: list[float] = []
        frames_read = 0
        triggered = False
        trigger_start_frame: int | None = None
        last_speech_frame: int | None = None
        trailing_silence_frames = 0

        if self._audio_stream is None:
            sd.check_input_settings(device=device_index, samplerate=sample_rate, channels=channels)
        with self._active_input_stream(sd, device_index, sample_rate, channels) as stream:
            while frames_read < max_frames and not self._stop_requested.is_set():
                frames_to_read = min(chunk_frames, max_frames - frames_read)
                read_started = self.clock()
                recording, _overflowed = stream.read(frames_to_read)
                audio_record_ms += (self.clock() - read_started) * 1000.0
                chunk = _flatten_samples(recording)
                if not chunk:
                    break
                frames_read += frames_to_read
                chunk_rms = calculate_rms(chunk)
                noise_floor = estimate_noise_floor(levels)
                if noise_floor <= 0.0 and levels:
                    noise_floor = min(levels)
                threshold = calculate_effective_vad_threshold(
                    self.settings.voice_vad_threshold,
                    noise_floor,
                    noise_multiplier=self.settings.voice_vad_noise_multiplier,
                )
                if chunk_rms >= threshold:
                    if not triggered:
                        samples.extend(preroll_samples)
                        triggered = True
                        trigger_start_frame = frames_read - frames_to_read
                    samples.extend(chunk)
                    last_speech_frame = frames_read
                    trailing_silence_frames = 0
                elif triggered:
                    samples.extend(chunk)
                    trailing_silence_frames += frames_to_read
                else:
                    levels.append(chunk_rms)
                    preroll_samples.extend(chunk)

                if triggered and trigger_start_frame is not None:
                    elapsed_since_trigger = frames_read - trigger_start_frame
                    speech_span_ms = (
                        ((last_speech_frame - trigger_start_frame) / sample_rate) * 1000.0
                        if last_speech_frame is not None
                        else 0.0
                    )
                    selected_silence_ms = select_fast_voice_silence_ms(
                        self.settings,
                        speech_span_ms,
                    )
                    silence_frames_needed = max(
                        1,
                        int(sample_rate * selected_silence_ms / 1000.0),
                    )
                    if (
                        elapsed_since_trigger >= minimum_speech_frames
                        and trailing_silence_frames >= silence_frames_needed
                    ):
                        break

        capture_work_ms = (self.clock() - capture_work_started) * 1000.0
        audio_prepare_ms = max(0.0, capture_work_ms - audio_record_ms)

        vad_wait_ms = (
            (trigger_start_frame / sample_rate) * 1000.0
            if trigger_start_frame is not None
            else (frames_read / sample_rate) * 1000.0
        )
        speech_ms = (
            ((last_speech_frame - trigger_start_frame) / sample_rate) * 1000.0
            if trigger_start_frame is not None and last_speech_frame is not None
            else 0.0
        )
        trailing_silence_ms = (trailing_silence_frames / sample_rate) * 1000.0

        self.fast_logger.info(
            "Fast capture device={} samples={} triggered={} max_seconds={} silence_ms={} "
            "audio_record_ms={:.1f} audio_prepare_ms={:.1f}",
            device_name,
            len(samples),
            triggered,
            max_seconds,
            selected_silence_ms,
            audio_record_ms,
            audio_prepare_ms,
        )
        return FastCaptureResult(
            samples=samples,
            input_device=device_name,
            vad_wait_ms=vad_wait_ms,
            speech_ms=speech_ms,
            trailing_silence_ms=trailing_silence_ms,
            vad_crossed=triggered,
            audio_record_ms=audio_record_ms,
            audio_prepare_ms=audio_prepare_ms,
        )

    def _warm_stt(self) -> float:
        if self._stt_warm_attempted or not self.provider.available:
            return 0.0
        self._stt_warm_attempted = True
        warm_up = getattr(self.provider, "warm_up", None)
        if not callable(warm_up):
            return 0.0
        started = self.clock()
        warmed = False
        try:
            warmed = bool(warm_up())
        except Exception as exc:
            self.fast_logger.warning(
                "Fast voice STT warm-up failed provider={}: {}: {}",
                self.provider.name,
                type(exc).__name__,
                exc,
            )
        elapsed_ms = (self.clock() - started) * 1000.0
        self.fast_logger.info(
            "Fast voice STT warm-up provider={} warmed={} elapsed_ms={:.1f}",
            self.provider.name,
            warmed,
            elapsed_ms,
        )
        return elapsed_ms

    def _open_audio_session(self) -> float:
        if self._audio_stream is not None or self.recorder is not None:
            return 0.0
        started = self.clock()
        sd = self.sounddevice_module or _require_sounddevice()
        device_index, device_name = resolve_fast_input_device(
            sd,
            self.settings.voice_input_device,
        )
        sd.check_input_settings(
            device=device_index,
            samplerate=self.settings.voice_sample_rate,
            channels=self.settings.voice_channels,
        )
        self._audio_stream = sd.InputStream(
            device=device_index,
            samplerate=self.settings.voice_sample_rate,
            channels=self.settings.voice_channels,
            dtype="float32",
        )
        self._audio_device_index = device_index
        self._audio_device_name = device_name
        elapsed_ms = (self.clock() - started) * 1000.0
        self.fast_logger.info(
            "Persistent fast voice audio session opened device={} elapsed_ms={:.1f}",
            device_name,
            elapsed_ms,
        )
        return elapsed_ms

    def _close_audio_session(self) -> None:
        stream = self._audio_stream
        self._audio_stream = None
        self._audio_device_index = None
        self._audio_device_name = ""
        if stream is None:
            return
        if bool(getattr(stream, "active", False)):
            self._safe_stop_audio_stream(stream)
        try:
            stream.close()
        except Exception as exc:
            self.fast_logger.warning(
                "Persistent fast voice audio session close failed: {}: {}",
                type(exc).__name__,
                exc,
            )

    @contextmanager
    def _active_input_stream(
        self,
        sd: Any,
        device_index: int,
        sample_rate: int,
        channels: int,
    ):
        if self._audio_stream is None:
            with sd.InputStream(
                device=device_index,
                samplerate=sample_rate,
                channels=channels,
                dtype="float32",
            ) as stream:
                yield stream
            return

        stream = self._audio_stream
        stream.start()
        try:
            yield stream
        finally:
            self._safe_stop_audio_stream(stream)

    def _safe_stop_audio_stream(self, stream: Any) -> None:
        try:
            stream.stop()
        except Exception as exc:
            self.fast_logger.warning(
                "Persistent fast voice audio session stop failed: {}: {}",
                type(exc).__name__,
                exc,
            )

    def _notify_status(self, status: str) -> None:
        if self.status_callback is not None:
            self.status_callback(status)

    def _wait_for_clap(self) -> bool:
        sd = self.sounddevice_module or _require_sounddevice()
        if self._audio_stream is not None:
            device_index = self._audio_device_index
            if device_index is None:
                raise RuntimeError("Persistent audio session has no input device.")
        else:
            device_index, _device_name = resolve_fast_input_device(
                sd,
                self.settings.voice_input_device,
            )
        sample_rate = self.settings.voice_sample_rate
        channels = self.settings.voice_channels
        chunk_ms = 50
        chunk_frames = max(1, int(sample_rate * chunk_ms / 1000.0))
        max_chunks = max(1, math.ceil(CLAP_WAIT_SECONDS * 1000 / chunk_ms))
        rms_threshold = max(CLAP_MIN_RMS, self.settings.voice_vad_threshold * 10.0)

        if self._audio_stream is None:
            sd.check_input_settings(device=device_index, samplerate=sample_rate, channels=channels)
        with self._active_input_stream(sd, device_index, sample_rate, channels) as stream:
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
        *,
        stt_warmup_ms: float = 0.0,
        wake_only: bool = False,
        unintelligible_audio: bool = False,
        capture_result: FastCaptureResult | None = None,
    ) -> FastVoiceReport:
        capture_result = capture_result or FastCaptureResult([], input_device)
        timing = FastVoiceTiming(
            capture_ms=capture_ms,
            audio_record_ms=float(capture_result.audio_record_ms or 0.0),
            audio_prepare_ms=capture_result.audio_prepare_ms,
            stt_warmup_ms=stt_warmup_ms,
            vad_wait_ms=capture_result.vad_wait_ms,
            speech_ms=capture_result.speech_ms,
            trailing_silence_ms=capture_result.trailing_silence_ms,
            transcribe_ms=transcribe_ms,
            openai_ms=openai_ms,
            tts_ms=tts_ms,
            total_ms=(self.clock() - total_started) * 1000.0,
        )
        self.fast_logger.info(
            "Fast voice command={} accepted={} response_source={} {}",
            repair.repaired_transcript if repair else "<empty>",
            wake_only or validation.accepted,
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
            vad_crossed=capture_result.vad_crossed,
            wake_only=wake_only,
            unintelligible_audio=unintelligible_audio,
            errors=errors,
        )


def run_fast_command_test(
    settings: AppSettings,
    *,
    assistant: AssistantCore | None = None,
) -> FastVoiceReport:
    return FastVoiceRunner(settings, assistant=assistant).run_once()


def select_fast_voice_silence_ms(settings: AppSettings, speech_ms: float) -> int:
    if not settings.fast_voice_fast_stop_enabled:
        return settings.fast_voice_silence_ms
    if speech_ms <= SHORT_COMMAND_SPEECH_MS:
        return settings.fast_voice_short_command_silence_ms
    return settings.fast_voice_long_command_silence_ms


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


def is_wake_only_transcript(transcript: str, settings: AppSettings) -> bool:
    normalized = _normalize_phrase(transcript)
    if not normalized:
        return False
    configured = [settings.wake_phrase, *settings.wake_alias_list]
    phrases = {"wake up jarvis", "hey jarvis", "jarvis"}
    phrases.update(_normalize_phrase(phrase) for phrase in configured)
    return normalized in phrases


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
        f"VAD crossed: {_yes_no(report.vad_crossed)}",
        f"wake only: {_yes_no(report.wake_only)}",
        f"unintelligible audio: {_yes_no(report.unintelligible_audio)}",
        f"command accepted: {_yes_no(report.command_accepted)}",
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


def _normalize_phrase(value: str) -> str:
    without_punctuation = re.sub(r"[^a-z0-9\s]", " ", value.casefold())
    return re.sub(r"\s+", " ", without_punctuation).strip()
