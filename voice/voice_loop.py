from __future__ import annotations

import importlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from assistant.core import AssistantCore, AssistantResponse
from config.settings import AppSettings
from voice.command_validation import CommandValidationResult, validate_cleaned_command
from voice.stt import create_speech_to_text_provider
from voice.tts import TextToSpeechResult, speak_text
from voice.voice_command_test import COMMAND_PROMPT, LISTENING_FOR_COMMAND_PROMPT, NO_COMMAND_DETECTED_MESSAGE
from voice.wake import WakeDetectionResult, WakeDetector, remove_wake_phrase_prefix
from voice.wake_provider import OpenWakeWordWakeProvider, WakeProviderResolution, create_openwakeword_provider, resolve_wake_provider


_VOICE_LOOP_LOG_SINK_ID: int | None = None
_VOICE_LOOP_LOG_FILE: Path | None = None


StatusCallback = Callable[[str], None]
Recorder = Callable[[float], list[float]]
Sleeper = Callable[[float], None]
Beeper = Callable[[], None]


STOP_COMMANDS = {
    "stop listening",
    "go to sleep",
    "sleep jarvis",
    "jarvis sleep",
    "exit jarvis",
    "shutdown jarvis",
    "that is all",
    "thank you jarvis",
}
VOICE_LOOP_STARTED_MESSAGE = "Jarvis voice loop started. Press Ctrl+C to stop."
VOICE_LOOP_STOPPED_MESSAGE = "Jarvis voice loop stopped."
STOP_COMMAND_DETECTED_MESSAGE = "Stop command detected. Exiting voice loop."
RETURNING_TO_SLEEP_MESSAGE = "Standing by."
REJECTED_COMMAND_PREFIX = "Rejected command:"
ACCEPTED_COMMAND_PREFIX = "Accepted command:"
RETRYING_COMMAND_CAPTURE_MESSAGE = "Retrying command capture..."
LISTENING_FOR_FOLLOW_UP_PROMPT = "Listening for follow-up..."
REJECTED_FOLLOW_UP_PREFIX = "Rejected follow-up:"
ACCEPTED_FOLLOW_UP_PREFIX = "Accepted follow-up:"
RETRYING_FOLLOW_UP_CAPTURE_MESSAGE = "Retrying follow-up capture..."
FOLLOW_UP_RECORD_SECONDS = 10.0


@dataclass(frozen=True)
class CommandCaptureResult:
    raw_transcription: str
    cleaned_command: str
    validation: CommandValidationResult
    no_follow_up: bool = False
    stop_requested: bool = False


@dataclass
class VoiceLoopSummary:
    wake_attempts: int = 0
    successful_wakes: int = 0
    commands_handled: int = 0
    empty_commands: int = 0
    errors: int = 0

    def format(self) -> str:
        return (
            "Voice loop summary: "
            f"wake attempts={self.wake_attempts}, "
            f"successful wakes={self.successful_wakes}, "
            f"commands handled={self.commands_handled}, "
            f"empty commands={self.empty_commands}, "
            f"errors={self.errors}"
        )


@dataclass(frozen=True)
class VoiceLoopCycleReport:
    provider_name: str
    provider_available: bool
    wake_provider_name: str
    wake_provider_available: bool
    wake_provider_resolution: WakeProviderResolution
    wake_transcription: str
    wake_detection: WakeDetectionResult
    raw_command_transcription: str
    cleaned_command: str
    command_validation: CommandValidationResult
    assistant_response: AssistantResponse | None
    tts_result: TextToSpeechResult | None
    statuses: list[str]
    log_file: Path
    errors: list[str] = field(default_factory=list)
    stop_requested: bool = False

    @property
    def wake_detected(self) -> bool:
        return self.wake_detection.detected


class VoiceLoopRunner:
    """Continuous one-command-at-a-time Jarvis voice loop."""

    def __init__(
        self,
        settings: AppSettings,
        assistant: AssistantCore | None = None,
        provider: Any | None = None,
        tts_provider: Any | None = None,
        recorder: Recorder | None = None,
        sleeper: Sleeper | None = None,
        beeper: Beeper | None = None,
        status_callback: StatusCallback | None = None,
        wake_provider: OpenWakeWordWakeProvider | None = None,
        wake_provider_resolution: WakeProviderResolution | None = None,
    ) -> None:
        self.settings = settings
        self.assistant = assistant or AssistantCore(settings=settings)
        self.provider = provider or create_speech_to_text_provider(settings)
        self.tts_provider = tts_provider
        self.recorder = recorder or self._record_microphone
        self.sleeper = sleeper or time.sleep
        self.beeper = beeper or self._safe_beep
        self.status_callback = status_callback
        self.log_file = self.settings.log_dir / "voice_loop.log"
        self.voice_loop_logger = logger.bind(voice_loop=True)
        self.wake_provider_resolution = wake_provider_resolution or resolve_wake_provider(settings)
        self.wake_provider = wake_provider or self._create_wake_provider()
        self._stop_requested = False
        self.summary = VoiceLoopSummary()
        self._consecutive_empty_commands = 0
        self._ensure_voice_loop_log_sink()

    def request_stop(self) -> None:
        self._stop_requested = True

    def _create_wake_provider(self) -> OpenWakeWordWakeProvider | None:
        if self.wake_provider_resolution.effective_provider != "openwakeword":
            return None
        return create_openwakeword_provider(self.settings)

    def run(self, max_cycles: int | None = None) -> list[VoiceLoopCycleReport]:
        self.summary = VoiceLoopSummary()
        self._consecutive_empty_commands = 0
        self.voice_loop_logger.info("Starting Jarvis voice loop")
        self._status(VOICE_LOOP_STARTED_MESSAGE, [])
        reports: list[VoiceLoopCycleReport] = []
        cycles = 0

        while not self._stop_requested:
            report = self.run_once()
            if max_cycles is not None:
                reports.append(report)

            cycles += 1
            if report.stop_requested:
                self.request_stop()
            if max_cycles is not None and cycles >= max_cycles:
                break

        self._emit(self.summary.format())
        self.voice_loop_logger.info("Jarvis voice loop stopped")
        self._status(VOICE_LOOP_STOPPED_MESSAGE, [])
        return reports

    def run_once(self) -> VoiceLoopCycleReport:
        statuses: list[str] = []
        errors: list[str] = []
        wake_transcription = ""
        raw_command_transcription = ""
        cleaned_command = ""
        assistant_response: AssistantResponse | None = None
        tts_result: TextToSpeechResult | None = None
        stop_requested = False
        detector = WakeDetector(
            wake_phrase=self.settings.wake_phrase,
            aliases=self.settings.wake_alias_list,
            threshold=self.settings.wake_match_threshold,
        )
        empty_detection = detector.detect("")

        if not self.provider.available:
            message = "Speech-to-text provider is not available. Voice loop cannot run."
            self.voice_loop_logger.error(message)
            self.summary.errors += 1
            errors.append(message)
            self._status("Sleeping", statuses)
            return self._report(
                wake_transcription,
                empty_detection,
                raw_command_transcription,
                cleaned_command,
                assistant_response,
                tts_result,
                statuses,
                errors,
                stop_requested=True,
            )

        self.summary.wake_attempts += 1
        self._status("Sleeping", statuses)
        wake_samples: list[float] = []

        try:
            self._status("Listening for wake phrase", statuses)
            if self.wake_provider_resolution.effective_provider == "openwakeword" and self.wake_provider is not None:
                wake_samples, wake_detection = self._detect_wake_with_openwakeword()
                self.voice_loop_logger.info(
                    "OpenWakeWord wake detection={} score={}",
                    wake_detection.detected,
                    f"{wake_detection.score:.3f}",
                )
                if not wake_detection.detected and self.wake_provider_resolution.fallback_enabled:
                    wake_transcription = self.provider.transcribe(wake_samples, self.settings.voice_sample_rate).text.strip()
                    wake_detection = detector.detect(wake_transcription)
                    self.voice_loop_logger.info(
                        "Wake fallback transcription={} detected={} score={}",
                        wake_transcription or "<empty>",
                        wake_detection.detected,
                        f"{wake_detection.score:.3f}",
                    )
            else:
                wake_samples = self.recorder(self.settings.wake_listen_seconds)
                wake_transcription = self.provider.transcribe(wake_samples, self.settings.voice_sample_rate).text.strip()
                wake_detection = detector.detect(wake_transcription)
                self.voice_loop_logger.info(
                    "Wake transcription={} detected={} score={}",
                    wake_transcription or "<empty>",
                    wake_detection.detected,
                    f"{wake_detection.score:.3f}",
                )
        except Exception as exc:
            message = f"Wake phrase stage failed: {type(exc).__name__}: {exc}"
            self.voice_loop_logger.exception(message)
            self.summary.errors += 1
            errors.append(message)
            self._status("Sleeping", statuses)
            return self._report(
                wake_transcription,
                empty_detection,
                raw_command_transcription,
                cleaned_command,
                assistant_response,
                tts_result,
                statuses,
                errors,
            )

        if not wake_detection.detected:
            self._status("Sleeping", statuses)
            return self._report(
                wake_transcription,
                wake_detection,
                raw_command_transcription,
                cleaned_command,
                assistant_response,
                tts_result,
                statuses,
                errors,
            )

        self.summary.successful_wakes += 1
        self._status("Wake detected", statuses)
        self._status(COMMAND_PROMPT, statuses)
        if self.settings.voice_loop_speak_status:
            self._speak_message(COMMAND_PROMPT, errors)

        if self.settings.voice_command_start_delay_seconds > 0:
            self.sleeper(self.settings.voice_command_start_delay_seconds)
        self.beeper()

        try:
            command_capture = self._capture_valid_command(
                statuses,
                errors,
                listen_prompt=LISTENING_FOR_COMMAND_PROMPT,
                record_seconds=self.settings.voice_command_record_seconds,
                accepted_prefix=ACCEPTED_COMMAND_PREFIX,
                rejected_prefix=REJECTED_COMMAND_PREFIX,
                retry_message=RETRYING_COMMAND_CAPTURE_MESSAGE,
                retry_start_delay_seconds=self.settings.voice_command_start_delay_seconds,
                retry_beep=True,
            )
        except Exception as exc:
            message = f"Command stage failed: {type(exc).__name__}: {exc}"
            self.voice_loop_logger.exception(message)
            self.summary.errors += 1
            errors.append(message)
            return self._return_to_sleep_report(
                wake_transcription,
                wake_detection,
                raw_command_transcription,
                cleaned_command,
                assistant_response,
                tts_result,
                statuses,
                errors,
            )

        raw_command_transcription = command_capture.raw_transcription
        cleaned_command = command_capture.cleaned_command
        if not command_capture.validation.accepted:
            return self._return_to_sleep_report(
                wake_transcription,
                wake_detection,
                raw_command_transcription,
                cleaned_command,
                assistant_response,
                tts_result,
                statuses,
                errors,
                stop_requested=command_capture.stop_requested,
            )

        follow_up_used = False
        while True:
            self.summary.commands_handled += 1
            self._consecutive_empty_commands = 0

            if is_stop_command(cleaned_command):
                self.voice_loop_logger.info("Stop command detected: {}", cleaned_command)
                self._status(STOP_COMMAND_DETECTED_MESSAGE, statuses)
                return self._report(
                    wake_transcription,
                    wake_detection,
                    raw_command_transcription,
                    cleaned_command,
                    assistant_response,
                    tts_result,
                    statuses,
                    errors,
                    stop_requested=True,
                )

            self._status("Thinking", statuses)
            try:
                assistant_response = self.assistant.handle_command(cleaned_command)
            except Exception as exc:
                message = f"Assistant command failed: {type(exc).__name__}: {exc}"
                self.voice_loop_logger.exception(message)
                self.summary.errors += 1
                errors.append(message)
                return self._return_to_sleep_report(
                    wake_transcription,
                    wake_detection,
                    raw_command_transcription,
                    cleaned_command,
                    assistant_response,
                    tts_result,
                    statuses,
                    errors,
                )

            self._emit(f"Last Jarvis response: {assistant_response.text}")
            self.voice_loop_logger.info("Assistant response={}", assistant_response.text)

            if assistant_response.accepted:
                self._status("Speaking", statuses)
                tts_result = speak_text(
                    assistant_response.text,
                    self.settings,
                    speak_requested=True,
                    provider=self.tts_provider,
                )
                if tts_result.error:
                    errors.append(tts_result.error)
                    self.summary.errors += 1
                elif tts_result.spoken:
                    self.sleeper(self.settings.voice_loop_wake_cooldown_seconds)
            else:
                break

            if follow_up_used:
                break

            try:
                follow_up_capture = self._capture_valid_command(
                    statuses,
                    errors,
                    listen_prompt=LISTENING_FOR_FOLLOW_UP_PROMPT,
                    record_seconds=FOLLOW_UP_RECORD_SECONDS,
                    accepted_prefix=ACCEPTED_FOLLOW_UP_PREFIX,
                    rejected_prefix=REJECTED_FOLLOW_UP_PREFIX,
                    retry_message=RETRYING_FOLLOW_UP_CAPTURE_MESSAGE,
                    empty_transcript_is_no_follow_up=True,
                    ignored_cleaned_commands={cleaned_command.casefold()},
                )
            except Exception as exc:
                message = f"Follow-up command stage failed: {type(exc).__name__}: {exc}"
                self.voice_loop_logger.exception(message)
                self.summary.errors += 1
                errors.append(message)
                break

            if follow_up_capture.no_follow_up or not follow_up_capture.validation.accepted:
                if follow_up_capture.stop_requested:
                    stop_requested = True
                break

            raw_command_transcription = follow_up_capture.raw_transcription
            cleaned_command = follow_up_capture.cleaned_command
            follow_up_used = True

        return self._return_to_sleep_report(
            wake_transcription,
            wake_detection,
            raw_command_transcription,
            cleaned_command,
            assistant_response,
            tts_result,
            statuses,
            errors,
            stop_requested=stop_requested,
        )

    def _capture_command(
        self,
        statuses: list[str],
        *,
        listen_prompt: str = LISTENING_FOR_COMMAND_PROMPT,
        record_seconds: float | None = None,
    ) -> tuple[str, str, CommandValidationResult]:
        self._status(listen_prompt, statuses)
        command_samples = self.recorder(record_seconds or self.settings.voice_command_record_seconds)
        raw_command_transcription = self.provider.transcribe(command_samples, self.settings.voice_sample_rate).text.strip()
        cleaned_command = remove_wake_phrase_prefix(
            raw_command_transcription,
            wake_phrase=self.settings.wake_phrase,
            aliases=self.settings.wake_alias_list,
        )
        command_validation = validate_cleaned_command(
            cleaned_command,
            min_words=self.settings.voice_command_min_words,
            reject_phrases=self.settings.voice_command_reject_phrase_list,
        )
        self.voice_loop_logger.info(
            "Command transcription={} cleaned={} accepted={} reason={}",
            raw_command_transcription or "<empty>",
            cleaned_command or "<empty>",
            command_validation.accepted,
            command_validation.rejection_reason or "<none>",
        )
        return raw_command_transcription, cleaned_command, command_validation

    def _capture_valid_command(
        self,
        statuses: list[str],
        errors: list[str],
        *,
        listen_prompt: str,
        record_seconds: float,
        accepted_prefix: str,
        rejected_prefix: str,
        retry_message: str,
        retry_start_delay_seconds: float = 0.0,
        retry_beep: bool = False,
        empty_transcript_is_no_follow_up: bool = False,
        ignored_cleaned_commands: set[str] | None = None,
    ) -> CommandCaptureResult:
        max_retries = self.settings.voice_command_max_retries if self.settings.voice_command_retry_on_reject else 0
        attempt = 0
        while True:
            raw_transcription, cleaned_command, validation = self._capture_command(
                statuses,
                listen_prompt=listen_prompt,
                record_seconds=record_seconds,
            )

            if empty_transcript_is_no_follow_up and not raw_transcription and not cleaned_command:
                self.voice_loop_logger.info("No follow-up command heard.")
                return CommandCaptureResult(
                    raw_transcription=raw_transcription,
                    cleaned_command=cleaned_command,
                    validation=validation,
                    no_follow_up=True,
                )

            if validation.accepted and cleaned_command.casefold() in (ignored_cleaned_commands or set()):
                self.voice_loop_logger.info("Ignoring duplicate follow-up command={}", cleaned_command)
                return CommandCaptureResult(
                    raw_transcription=raw_transcription,
                    cleaned_command=cleaned_command,
                    validation=validation,
                    no_follow_up=True,
                )

            self._emit(f"Last recognized command: {cleaned_command or '<empty>'}")
            if validation.accepted:
                self._emit(f"{accepted_prefix} {cleaned_command}")
                return CommandCaptureResult(
                    raw_transcription=raw_transcription,
                    cleaned_command=cleaned_command,
                    validation=validation,
                )

            rejection_reason = validation.rejection_reason or "invalid command"
            self._emit(f"{rejected_prefix} {cleaned_command or '<empty>'} ({rejection_reason})")
            self.voice_loop_logger.info(
                "{} reason={}",
                NO_COMMAND_DETECTED_MESSAGE,
                rejection_reason,
            )
            self.summary.empty_commands += 1
            self._consecutive_empty_commands += 1
            self._status(NO_COMMAND_DETECTED_MESSAGE, statuses)
            if self.settings.voice_loop_speak_status:
                self._speak_message(NO_COMMAND_DETECTED_MESSAGE, errors)
            if attempt < max_retries:
                attempt += 1
                self._status(retry_message, statuses)
                if retry_start_delay_seconds > 0:
                    self.sleeper(retry_start_delay_seconds)
                if retry_beep:
                    self.beeper()
                continue

            stop_requested = False
            if self.settings.voice_loop_max_empty_commands >= 0 and self._consecutive_empty_commands >= self.settings.voice_loop_max_empty_commands:
                stop_requested = True
                self.voice_loop_logger.info(
                    "Empty command limit reached after {} attempts",
                    self._consecutive_empty_commands,
                )
            return CommandCaptureResult(
                raw_transcription=raw_transcription,
                cleaned_command=cleaned_command,
                validation=validation,
                stop_requested=stop_requested,
            )

    def _return_to_sleep_report(
        self,
        wake_transcription: str,
        wake_detection: WakeDetectionResult,
        raw_command_transcription: str,
        cleaned_command: str,
        assistant_response: AssistantResponse | None,
        tts_result: TextToSpeechResult | None,
        statuses: list[str],
        errors: list[str],
        stop_requested: bool = False,
    ) -> VoiceLoopCycleReport:
        self._status(RETURNING_TO_SLEEP_MESSAGE, statuses)
        if self.settings.voice_loop_speak_status:
            self._speak_message(RETURNING_TO_SLEEP_MESSAGE, errors)
        return self._report(
            wake_transcription,
            wake_detection,
            raw_command_transcription,
            cleaned_command,
            assistant_response,
            tts_result,
            statuses,
            errors,
            stop_requested=stop_requested,
        )

    def _status(self, status: str, statuses: list[str]) -> None:
        statuses.append(status)
        self.voice_loop_logger.info("Status={}", status)
        if self.status_callback is not None:
            self.status_callback(status)

    def _emit(self, message: str) -> None:
        self.voice_loop_logger.info(message)
        if self.status_callback is not None:
            self.status_callback(message)

    def _speak_message(self, message: str, errors: list[str]) -> TextToSpeechResult:
        tts_result = speak_text(
            message,
            self.settings,
            speak_requested=True,
            provider=self.tts_provider,
        )
        if tts_result.error:
            errors.append(tts_result.error)
            self.summary.errors += 1
        elif tts_result.spoken:
            self.sleeper(self.settings.voice_loop_wake_cooldown_seconds)
        return tts_result

    def _report(
        self,
        wake_transcription: str,
        wake_detection: WakeDetectionResult,
        raw_command_transcription: str,
        cleaned_command: str,
        assistant_response: AssistantResponse | None,
        tts_result: TextToSpeechResult | None,
        statuses: list[str],
        errors: list[str],
        stop_requested: bool = False,
    ) -> VoiceLoopCycleReport:
        wake_provider_name = self.wake_provider_resolution.effective_provider
        wake_provider_available = self.wake_provider_resolution.openwakeword_available
        if wake_provider_name != "openwakeword":
            wake_provider_available = True
        command_validation = validate_cleaned_command(
            cleaned_command,
            min_words=self.settings.voice_command_min_words,
            reject_phrases=self.settings.voice_command_reject_phrase_list,
        )
        return VoiceLoopCycleReport(
            provider_name=self.provider.name,
            provider_available=bool(self.provider.available),
            wake_provider_name=wake_provider_name,
            wake_provider_available=wake_provider_available,
            wake_provider_resolution=self.wake_provider_resolution,
            wake_transcription=wake_transcription,
            wake_detection=wake_detection,
            raw_command_transcription=raw_command_transcription,
            cleaned_command=cleaned_command,
            command_validation=command_validation,
            assistant_response=assistant_response,
            tts_result=tts_result,
            statuses=statuses,
            log_file=self.log_file,
            errors=errors,
            stop_requested=stop_requested,
        )

    def _detect_wake_with_openwakeword(self) -> tuple[list[float], WakeDetectionResult]:
        if self.wake_provider is None:
            raise RuntimeError("OpenWakeWord wake provider is not available.")

        listen_chunk_seconds = max(self.settings.openwakeword_listen_chunk_ms / 1000.0, 0.02)
        deadline = time.monotonic() + self.settings.wake_listen_seconds
        buffered_samples: list[float] = []
        wake_detection = WakeDetectionResult(
            detected=False,
            transcript="",
            matched_phrase=None,
            score=0.0,
            threshold=self.settings.openwakeword_threshold,
            match_type="none",
        )

        while time.monotonic() < deadline and not self._stop_requested:
            chunk = self.recorder(listen_chunk_seconds)
            if chunk:
                buffered_samples.extend(chunk)
                wake_detection = self.wake_provider.detect(chunk, self.settings.voice_sample_rate)
            if wake_detection.detected:
                break

        return buffered_samples, wake_detection

    def _record_microphone(self, duration_seconds: float) -> list[float]:
        sd = self._require_sounddevice()
        sample_rate = self.settings.voice_sample_rate
        channels = self.settings.voice_channels
        frames = int(sample_rate * duration_seconds)

        sd.check_input_settings(samplerate=sample_rate, channels=channels)
        recording = sd.rec(frames, samplerate=sample_rate, channels=channels, dtype="float32")
        sd.wait()
        return self._flatten_samples(recording)

    @staticmethod
    def _require_sounddevice() -> Any:
        try:
            return importlib.import_module("sounddevice")
        except Exception as exc:
            raise RuntimeError(f"sounddevice is required for voice-loop: {exc}") from exc

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
    def _safe_beep() -> None:
        try:
            winsound = importlib.import_module("winsound")
            winsound.Beep(880, 180)
        except Exception:
            return

    def _ensure_voice_loop_log_sink(self) -> None:
        global _VOICE_LOOP_LOG_FILE, _VOICE_LOOP_LOG_SINK_ID
        if _VOICE_LOOP_LOG_SINK_ID is not None and _VOICE_LOOP_LOG_FILE == self.log_file:
            return

        if _VOICE_LOOP_LOG_SINK_ID is not None:
            try:
                logger.remove(_VOICE_LOOP_LOG_SINK_ID)
            except ValueError:
                pass

        self.settings.log_dir.mkdir(parents=True, exist_ok=True)
        _VOICE_LOOP_LOG_SINK_ID = logger.add(
            self.log_file,
            level="DEBUG",
            rotation="1 MB",
            retention="7 days",
            encoding="utf-8",
            backtrace=False,
            diagnose=False,
            filter=lambda record: bool(record["extra"].get("voice_loop")),
        )
        _VOICE_LOOP_LOG_FILE = self.log_file


def is_stop_command(command_text: str) -> bool:
    normalized = " ".join(command_text.lower().strip().split())
    return normalized in STOP_COMMANDS
