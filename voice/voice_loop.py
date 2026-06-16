from __future__ import annotations

import importlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from math import ceil
from pathlib import Path
from typing import Any

from loguru import logger

from assistant.core import AssistantCore, AssistantResponse
from config.settings import AppSettings
from services.logging_service import add_managed_file_sink
from voice.command_capture import (
    AudioCaptureMetrics,
    calculate_audio_capture_metrics,
    calculate_command_confidence,
    calculate_rms,
)
from voice.command_validation import CommandValidationResult, validate_cleaned_command
from voice.speech_repair import (
    OpenAIRepairer,
    REPAIR_OPENAI_PROMPT,
    SpeechRepairResult,
    SpeechRepairer,
    is_confirmation_no,
    is_confirmation_yes,
)
from voice.stt import create_speech_to_text_provider
from voice.tts import TextToSpeechResult, speak_text
from voice.voice_command_test import COMMAND_PROMPT, LISTENING_FOR_COMMAND_PROMPT, NO_COMMAND_DETECTED_MESSAGE
from voice.wake import WakeDetectionResult, WakeDetector, remove_wake_phrase_prefix
from voice.wake_provider import OpenWakeWordWakeProvider, WakeProviderResolution, create_openwakeword_provider, resolve_wake_provider


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
WAKE_DIAGNOSTICS_PREFIX = "Wake diagnostics:"
CAPTURE_DIAGNOSTICS_PREFIX = "Capture diagnostics:"
SPEECH_REPAIR_PREFIX = "Speech repair:"


@dataclass(frozen=True)
class CommandCaptureResult:
    raw_transcription: str
    cleaned_command: str
    validation: CommandValidationResult
    speech_repair: SpeechRepairResult | None = None
    audio_metrics: AudioCaptureMetrics | None = None
    command_transcribe_ms: float = 0.0
    transcript_confidence: float | None = None
    command_score: float = 0.0
    no_follow_up: bool = False
    stop_requested: bool = False


@dataclass
class VoiceLoopTiming:
    wake_capture_ms: float = 0.0
    wake_transcribe_ms: float = 0.0
    command_capture_ms: float = 0.0
    command_transcribe_ms: float = 0.0
    openai_ms: float = 0.0
    tts_ms: float = 0.0
    total_turn_ms: float = 0.0

    def format_summary(self) -> str:
        parts = [
            f"wake_capture_ms={self.wake_capture_ms:.1f}",
            f"wake_transcribe_ms={self.wake_transcribe_ms:.1f}",
            f"command_capture_ms={self.command_capture_ms:.1f}",
            f"command_transcribe_ms={self.command_transcribe_ms:.1f}",
            f"openai_ms={self.openai_ms:.1f}",
            f"tts_ms={self.tts_ms:.1f}",
            f"total_turn_ms={self.total_turn_ms:.1f}",
        ]
        slow_stages = self.slow_stages()
        if slow_stages:
            parts.append(f"slow_stages={','.join(slow_stages)}")
        return "Timing summary: " + " ".join(parts)

    def slow_stages(self) -> list[str]:
        return [
            name
            for name, value in (
                ("wake_capture_ms", self.wake_capture_ms),
                ("wake_transcribe_ms", self.wake_transcribe_ms),
                ("command_capture_ms", self.command_capture_ms),
                ("command_transcribe_ms", self.command_transcribe_ms),
                ("openai_ms", self.openai_ms),
                ("tts_ms", self.tts_ms),
                ("total_turn_ms", self.total_turn_ms),
            )
            if value >= 1200.0
        ]


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
    speech_repair: SpeechRepairResult | None
    command_audio_metrics: AudioCaptureMetrics | None
    timing: VoiceLoopTiming | None
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
        openai_repairer: OpenAIRepairer | None = None,
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
        self.speech_repairer = SpeechRepairer(
            settings,
            openai_repairer=openai_repairer or self._repair_with_openai,
        )
        self.wake_provider_resolution = wake_provider_resolution or resolve_wake_provider(settings)
        self.wake_provider = wake_provider or self._create_wake_provider()
        self._stop_requested = False
        self.summary = VoiceLoopSummary()
        self._consecutive_empty_commands = 0
        self._recent_voice_commands: list[str] = []
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
        turn_started = time.perf_counter()
        timing = VoiceLoopTiming()
        statuses: list[str] = []
        errors: list[str] = []
        wake_transcription = ""
        raw_command_transcription = ""
        cleaned_command = ""
        speech_repair: SpeechRepairResult | None = None
        command_audio_metrics: AudioCaptureMetrics | None = None
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
            self._finish_timing(timing, turn_started)
            return self._report(
                wake_transcription,
                empty_detection,
                raw_command_transcription,
                cleaned_command,
                assistant_response,
                tts_result,
                statuses,
                errors,
                timing=timing,
                stop_requested=True,
            )

        self.summary.wake_attempts += 1
        self._status("Sleeping", statuses)
        wake_samples: list[float] = []
        wake_capture_started = time.perf_counter()

        try:
            if not self.wake_provider_resolution.manual_mode_required:
                self._status("Listening for wake phrase", statuses)
            if self.wake_provider_resolution.manual_mode_required:
                warning = self.wake_provider_resolution.fallback_reason or (
                    "OpenWakeWord is unavailable; switching to manual command mode."
                )
                self.voice_loop_logger.warning(warning)
                self._emit(warning)
                self._status("Wake unavailable; manual command mode", statuses)
                wake_detection = self._manual_wake_detection()
                self.summary.successful_wakes += 1
                self._status("Wake detected", statuses)
                self._status(COMMAND_PROMPT, statuses)
                if self.settings.voice_loop_speak_wake_ack:
                    self._speak_text(COMMAND_PROMPT, errors, sleep_after=False)
                if self.settings.voice_command_start_delay_seconds > 0:
                    self.sleeper(self.settings.voice_command_start_delay_seconds)
                self.beeper()
                wake_capture_started = time.perf_counter()
                timing.wake_capture_ms = 0.0
                timing.wake_transcribe_ms = 0.0
                self._log_wake_diagnostics([], wake_detection)
            elif self.wake_provider_resolution.effective_provider == "openwakeword" and self.wake_provider is not None:
                wake_samples, wake_detection = self._detect_wake_with_openwakeword()
                timing.wake_capture_ms = (time.perf_counter() - wake_capture_started) * 1000.0
                self.voice_loop_logger.info(
                    "OpenWakeWord wake detection={} score={}",
                    wake_detection.detected,
                    f"{wake_detection.score:.3f}",
                )
                if not wake_detection.detected and self.wake_provider_resolution.fallback_enabled:
                    wake_transcribe_started = time.perf_counter()
                    wake_transcription = self.provider.transcribe(wake_samples, self.settings.voice_sample_rate).text.strip()
                    timing.wake_transcribe_ms = (time.perf_counter() - wake_transcribe_started) * 1000.0
                    wake_detection = detector.detect(wake_transcription)
                    self.voice_loop_logger.info(
                        "Wake fallback transcription={} detected={} score={}",
                        wake_transcription or "<empty>",
                        wake_detection.detected,
                        f"{wake_detection.score:.3f}",
                    )
                self._log_wake_diagnostics(wake_samples, wake_detection)
            else:
                wake_capture_started = time.perf_counter()
                wake_samples = self.recorder(self.settings.wake_listen_seconds)
                timing.wake_capture_ms = (time.perf_counter() - wake_capture_started) * 1000.0
                wake_transcribe_started = time.perf_counter()
                wake_transcription = self.provider.transcribe(wake_samples, self.settings.voice_sample_rate).text.strip()
                timing.wake_transcribe_ms = (time.perf_counter() - wake_transcribe_started) * 1000.0
                wake_detection = detector.detect(wake_transcription)
                self.voice_loop_logger.info(
                    "Wake transcription={} detected={} score={}",
                    wake_transcription or "<empty>",
                    wake_detection.detected,
                    f"{wake_detection.score:.3f}",
                )
                self._log_wake_diagnostics(wake_samples, wake_detection)
        except Exception as exc:
            message = f"Wake phrase stage failed: {type(exc).__name__}: {exc}"
            self.voice_loop_logger.exception(message)
            self.summary.errors += 1
            errors.append(message)
            self._status("Sleeping", statuses)
            self._finish_timing(timing, turn_started)
            return self._report(
                wake_transcription,
                empty_detection,
                raw_command_transcription,
                cleaned_command,
                assistant_response,
                tts_result,
                statuses,
                errors,
                timing=timing,
            )

        if not wake_detection.detected:
            self._status("Sleeping", statuses)
            self._finish_timing(timing, turn_started)
            return self._report(
                wake_transcription,
                wake_detection,
                raw_command_transcription,
                cleaned_command,
                assistant_response,
                tts_result,
                statuses,
                errors,
                timing=timing,
            )

        self.summary.successful_wakes += 1
        self._status("Wake detected", statuses)
        self._status(COMMAND_PROMPT, statuses)
        if self.settings.voice_loop_speak_wake_ack:
            self._speak_text(COMMAND_PROMPT, errors, sleep_after=False)

        if self.settings.voice_command_start_delay_seconds > 0:
            self.sleeper(self.settings.voice_command_start_delay_seconds)
        self.beeper()

        try:
            command_capture_started = time.perf_counter()
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
            timing.command_capture_ms = (time.perf_counter() - command_capture_started) * 1000.0
            timing.command_transcribe_ms = command_capture.command_transcribe_ms
        except Exception as exc:
            message = f"Command stage failed: {type(exc).__name__}: {exc}"
            self.voice_loop_logger.exception(message)
            self.summary.errors += 1
            errors.append(message)
            self._finish_timing(timing, turn_started)
            return self._return_to_sleep_report(
                wake_transcription,
                wake_detection,
                raw_command_transcription,
                cleaned_command,
                assistant_response,
                tts_result,
                statuses,
                errors,
                timing=timing,
            )

        raw_command_transcription = command_capture.raw_transcription
        cleaned_command = command_capture.cleaned_command
        speech_repair = command_capture.speech_repair
        command_audio_metrics = command_capture.audio_metrics
        if not command_capture.validation.accepted:
            self._finish_timing(timing, turn_started)
            return self._return_to_sleep_report(
                wake_transcription,
                wake_detection,
                raw_command_transcription,
                cleaned_command,
                assistant_response,
                tts_result,
                statuses,
                errors,
                timing=timing,
                speech_repair=speech_repair,
                command_audio_metrics=command_audio_metrics,
                stop_requested=command_capture.stop_requested,
            )

        follow_up_used = False
        while True:
            self.summary.commands_handled += 1
            self._consecutive_empty_commands = 0

            if is_stop_command(cleaned_command):
                self.voice_loop_logger.info("Stop command detected: {}", cleaned_command)
                self._status(STOP_COMMAND_DETECTED_MESSAGE, statuses)
                self._finish_timing(timing, turn_started)
                return self._report(
                    wake_transcription,
                    wake_detection,
                    raw_command_transcription,
                    cleaned_command,
                    assistant_response,
                    tts_result,
                    statuses,
                    errors,
                    timing=timing,
                    speech_repair=speech_repair,
                    command_audio_metrics=command_audio_metrics,
                    stop_requested=True,
                )

            self._status("Thinking", statuses)
            try:
                openai_started = time.perf_counter()
                assistant_response = self._handle_voice_command(cleaned_command)
                timing.openai_ms = (time.perf_counter() - openai_started) * 1000.0
            except Exception as exc:
                message = f"Assistant command failed: {type(exc).__name__}: {exc}"
                self.voice_loop_logger.exception(message)
                self.summary.errors += 1
                errors.append(message)
                self._finish_timing(timing, turn_started)
                return self._return_to_sleep_report(
                    wake_transcription,
                    wake_detection,
                    raw_command_transcription,
                    cleaned_command,
                    assistant_response,
                    tts_result,
                    statuses,
                    errors,
                    timing=timing,
                    speech_repair=speech_repair,
                    command_audio_metrics=command_audio_metrics,
                )

            self._emit(f"Last Jarvis response: {assistant_response.text}")
            self.voice_loop_logger.info("Assistant response={}", assistant_response.text)

            if assistant_response.accepted:
                if self.settings.voice_loop_speak_responses:
                    self._status("Speaking", statuses)
                    tts_started = time.perf_counter()
                    tts_result = self._speak_text(assistant_response.text, errors, sleep_after=False)
                    timing.tts_ms = (time.perf_counter() - tts_started) * 1000.0
                self._remember_voice_command(cleaned_command)
            else:
                break

            if follow_up_used:
                break

            try:
                follow_up_capture_started = time.perf_counter()
                follow_up_capture = self._capture_valid_command(
                    statuses,
                    errors,
                    listen_prompt=LISTENING_FOR_FOLLOW_UP_PROMPT,
                    record_seconds=self.settings.voice_follow_up_timeout_seconds,
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
            speech_repair = follow_up_capture.speech_repair
            command_audio_metrics = follow_up_capture.audio_metrics
            timing.command_capture_ms = (time.perf_counter() - follow_up_capture_started) * 1000.0
            timing.command_transcribe_ms = follow_up_capture.command_transcribe_ms
            follow_up_used = True

        report = self._return_to_sleep_report(
            wake_transcription,
            wake_detection,
            raw_command_transcription,
            cleaned_command,
            assistant_response,
            tts_result,
            statuses,
            errors,
            timing=timing,
            speech_repair=speech_repair,
            command_audio_metrics=command_audio_metrics,
            stop_requested=stop_requested,
        )
        timing.total_turn_ms = (time.perf_counter() - turn_started) * 1000.0
        self._emit(timing.format_summary())
        return report

    def _capture_command(
        self,
        statuses: list[str],
        *,
        listen_prompt: str = LISTENING_FOR_COMMAND_PROMPT,
        record_seconds: float | None = None,
    ) -> CommandCaptureResult:
        self._status(listen_prompt, statuses)
        command_samples = self.recorder(record_seconds or self.settings.voice_command_record_seconds)
        audio_metrics = calculate_audio_capture_metrics(
            command_samples,
            self.settings.voice_sample_rate,
            self.settings.voice_vad_threshold,
            vad_window_ms=self.settings.voice_vad_window_ms,
            noise_multiplier=self.settings.voice_vad_noise_multiplier,
        )
        transcribe_started = time.perf_counter()
        transcription = self.provider.transcribe(command_samples, self.settings.voice_sample_rate)
        raw_command_transcription = transcription.text.strip()
        transcript_confidence = getattr(transcription, "confidence", None)
        command_transcribe_ms = (time.perf_counter() - transcribe_started) * 1000.0
        cleaned_transcription = remove_wake_phrase_prefix(
            raw_command_transcription,
            wake_phrase=self.settings.wake_phrase,
            aliases=self.settings.wake_alias_list,
        )
        speech_repair = self.speech_repairer.repair(
            cleaned_transcription,
            raw_transcript=raw_command_transcription,
            recent_commands=self._recent_voice_commands,
        )
        cleaned_command = speech_repair.repaired_transcript
        command_validation = validate_cleaned_command(
            cleaned_command,
            min_words=self.settings.voice_command_min_words,
            reject_phrases=self.settings.voice_command_reject_phrase_list,
                incomplete_phrases=self.settings.voice_command_incomplete_phrase_list,
        )
        command_score = calculate_command_confidence(
            cleaned_command,
            command_validation,
            speech_repair=speech_repair,
            transcript_confidence=transcript_confidence,
        )
        self._log_capture_audio_diagnostics(
            audio_metrics,
            record_seconds or self.settings.voice_command_record_seconds,
            transcript_confidence=transcript_confidence,
            command_score=command_score,
        )
        self._log_speech_repair_diagnostics(speech_repair)
        self.voice_loop_logger.info(
            "Command transcription={} transcript_confidence={} cleaned={} repaired={} confidence={} strategy={} "
            "command_score={} accepted={} reason={}",
            raw_command_transcription or "<empty>",
            _format_optional_float(transcript_confidence),
            speech_repair.cleaned_transcript or "<empty>",
            speech_repair.repaired_transcript or "<empty>",
            f"{speech_repair.confidence:.2f}",
            speech_repair.strategy,
            f"{command_score:.2f}",
            command_validation.accepted,
            command_validation.rejection_reason or "<none>",
        )
        return CommandCaptureResult(
            raw_transcription=raw_command_transcription,
            cleaned_command=cleaned_command,
            validation=command_validation,
            speech_repair=speech_repair,
            audio_metrics=audio_metrics,
            command_transcribe_ms=command_transcribe_ms,
            transcript_confidence=transcript_confidence,
            command_score=command_score,
        )

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
        base_max_retries = self.settings.voice_command_max_retries if self.settings.voice_command_retry_on_reject else 0
        attempt = 0
        while True:
            capture = self._capture_command(
                statuses,
                listen_prompt=listen_prompt,
                record_seconds=record_seconds,
            )
            raw_transcription = capture.raw_transcription
            cleaned_command = capture.cleaned_command
            validation = capture.validation
            audio_metrics = capture.audio_metrics
            speech_repair = capture.speech_repair
            command_transcribe_ms = capture.command_transcribe_ms
            transcript_confidence = capture.transcript_confidence
            command_score = capture.command_score

            if empty_transcript_is_no_follow_up and not raw_transcription and not cleaned_command:
                self.voice_loop_logger.info("No follow-up command heard.")
                return CommandCaptureResult(
                    raw_transcription=raw_transcription,
                    cleaned_command=cleaned_command,
                    validation=validation,
                    speech_repair=speech_repair,
                    audio_metrics=audio_metrics,
                    command_transcribe_ms=command_transcribe_ms,
                    transcript_confidence=transcript_confidence,
                    command_score=command_score,
                    no_follow_up=True,
                )

            if validation.accepted and cleaned_command.casefold() in (ignored_cleaned_commands or set()):
                self.voice_loop_logger.info("Ignoring duplicate follow-up command={}", cleaned_command)
                return CommandCaptureResult(
                    raw_transcription=raw_transcription,
                    cleaned_command=cleaned_command,
                    validation=validation,
                    speech_repair=speech_repair,
                    audio_metrics=audio_metrics,
                    command_transcribe_ms=command_transcribe_ms,
                    transcript_confidence=transcript_confidence,
                    command_score=command_score,
                    no_follow_up=True,
                )

            if validation.accepted and speech_repair.needs_confirmation(self.settings.voice_repair_confirmation_threshold):
                confirmed, confirmation_reason = self._confirm_repair(speech_repair, statuses, errors)
                if not confirmed:
                    validation = CommandValidationResult(False, cleaned_command, confirmation_reason)

            self._emit(f"Last recognized command: {cleaned_command or '<empty>'}")
            if validation.accepted:
                self._emit(f"{accepted_prefix} {cleaned_command}")
                return CommandCaptureResult(
                    raw_transcription=raw_transcription,
                    cleaned_command=cleaned_command,
                    validation=validation,
                    speech_repair=speech_repair,
                    audio_metrics=audio_metrics,
                    command_transcribe_ms=command_transcribe_ms,
                    transcript_confidence=transcript_confidence,
                    command_score=command_score,
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
            max_retries_for_rejection = max(base_max_retries, 1 if _is_incomplete_transcript(validation) else 0)
            if attempt < max_retries_for_rejection:
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
                speech_repair=speech_repair,
                audio_metrics=audio_metrics,
                command_transcribe_ms=command_transcribe_ms,
                transcript_confidence=transcript_confidence,
                command_score=command_score,
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
        timing: VoiceLoopTiming | None = None,
        speech_repair: SpeechRepairResult | None = None,
        command_audio_metrics: AudioCaptureMetrics | None = None,
        stop_requested: bool = False,
    ) -> VoiceLoopCycleReport:
        self._status(RETURNING_TO_SLEEP_MESSAGE, statuses)
        if self.settings.voice_loop_speak_status and self.settings.voice_loop_speak_standby:
            self._speak_text(self.settings.voice_loop_standby_message, errors, sleep_after=True)
        return self._report(
            wake_transcription,
            wake_detection,
            raw_command_transcription,
            cleaned_command,
            assistant_response,
            tts_result,
            statuses,
            errors,
            timing=timing,
            speech_repair=speech_repair,
            command_audio_metrics=command_audio_metrics,
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

    def _finish_timing(self, timing: VoiceLoopTiming, turn_started: float) -> None:
        timing.total_turn_ms = (time.perf_counter() - turn_started) * 1000.0
        self._emit(timing.format_summary())

    def _handle_voice_command(self, command: str) -> AssistantResponse:
        handle_voice_command = getattr(self.assistant, "handle_voice_command", None)
        if callable(handle_voice_command):
            return handle_voice_command(command)
        return self.assistant.handle_command(command)

    def _speak_message(self, message: str, errors: list[str]) -> TextToSpeechResult:
        return self._speak_text(message, errors, sleep_after=True)

    def _speak_text(self, message: str, errors: list[str], *, sleep_after: bool) -> TextToSpeechResult:
        tts_result = speak_text(
            message,
            self.settings,
            speak_requested=True,
            provider=self.tts_provider,
        )
        if tts_result.error:
            errors.append(tts_result.error)
            self.summary.errors += 1
        elif tts_result.spoken and sleep_after:
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
        timing: VoiceLoopTiming | None = None,
        speech_repair: SpeechRepairResult | None = None,
        command_audio_metrics: AudioCaptureMetrics | None = None,
        stop_requested: bool = False,
    ) -> VoiceLoopCycleReport:
        wake_provider_name = self.wake_provider_resolution.effective_provider
        wake_provider_available = self.wake_provider_resolution.openwakeword_available
        if self.wake_provider_resolution.manual_mode_required:
            wake_provider_name = "manual"
            wake_provider_available = False
        elif wake_provider_name != "openwakeword":
            wake_provider_available = True
        command_validation = validate_cleaned_command(
            cleaned_command,
            min_words=self.settings.voice_command_min_words,
            reject_phrases=self.settings.voice_command_reject_phrase_list,
            incomplete_phrases=self.settings.voice_command_incomplete_phrase_list,
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
            speech_repair=speech_repair,
            command_audio_metrics=command_audio_metrics,
            timing=timing,
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

    def _manual_wake_detection(self) -> WakeDetectionResult:
        return WakeDetectionResult(
            detected=True,
            transcript="",
            matched_phrase=None,
            score=0.0,
            threshold=self.settings.wake_match_threshold,
            match_type="manual",
        )

    def _record_microphone(self, duration_seconds: float) -> list[float]:
        sd = self._require_sounddevice()
        if self.settings.voice_vad_enabled and duration_seconds >= 1.0:
            try:
                return self._record_microphone_until_silence(sd, duration_seconds)
            except Exception as exc:
                self.voice_loop_logger.debug(
                    "Adaptive microphone capture failed; falling back to fixed recording: {}: {}",
                    type(exc).__name__,
                    exc,
                )

        return self._record_microphone_fixed(sd, duration_seconds)

    def _record_microphone_fixed(self, sd: Any, duration_seconds: float) -> list[float]:
        sample_rate = self.settings.voice_sample_rate
        channels = self.settings.voice_channels
        frames = int(sample_rate * duration_seconds)

        sd.check_input_settings(samplerate=sample_rate, channels=channels)
        recording = sd.rec(frames, samplerate=sample_rate, channels=channels, dtype="float32")
        sd.wait()
        return self._flatten_samples(recording)

    def _record_microphone_until_silence(self, sd: Any, duration_seconds: float) -> list[float]:
        sample_rate = self.settings.voice_sample_rate
        channels = self.settings.voice_channels
        window_ms = self.settings.voice_vad_window_ms
        chunk_frames = max(1, int(sample_rate * window_ms / 1000.0))
        max_frames = max(1, int(sample_rate * duration_seconds))
        silence_chunks_needed = max(1, ceil(self.settings.voice_vad_silence_ms / window_ms))
        min_chunks_after_trigger = max(1, ceil(450 / window_ms))
        samples: list[float] = []
        triggered = False
        chunks_after_trigger = 0
        trailing_silence_chunks = 0

        sd.check_input_settings(samplerate=sample_rate, channels=channels)
        with sd.InputStream(samplerate=sample_rate, channels=channels, dtype="float32") as stream:
            while len(samples) < max_frames and not self._stop_requested:
                frames_to_read = min(chunk_frames, max_frames - len(samples))
                recording, _overflowed = stream.read(frames_to_read)
                chunk = self._flatten_samples(recording)
                if not chunk:
                    break

                samples.extend(chunk)
                metrics = calculate_audio_capture_metrics(
                    samples,
                    sample_rate,
                    self.settings.voice_vad_threshold,
                    vad_window_ms=window_ms,
                    noise_multiplier=self.settings.voice_vad_noise_multiplier,
                )
                chunk_rms = calculate_rms(chunk)
                if chunk_rms >= metrics.effective_vad_threshold:
                    triggered = True
                    trailing_silence_chunks = 0
                elif triggered:
                    trailing_silence_chunks += 1

                if triggered:
                    chunks_after_trigger += 1
                    if (
                        chunks_after_trigger >= min_chunks_after_trigger
                        and trailing_silence_chunks >= silence_chunks_needed
                    ):
                        break

        return samples

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
        add_managed_file_sink(
            self.log_file,
            level="DEBUG",
            filter=lambda record: bool(record["extra"].get("voice_loop")),
        )

    def _repair_with_openai(self, cleaned: str) -> str | None:
        openai_service = getattr(self.assistant, "openai_service", None)
        if openai_service is None:
            return None
        result = openai_service.chat(cleaned, system_prompt=REPAIR_OPENAI_PROMPT)
        if not result.success or not result.text:
            return None
        return result.text

    def _remember_voice_command(self, command: str) -> None:
        cleaned = " ".join(command.strip().split())
        if not cleaned:
            return
        self._recent_voice_commands.append(cleaned)
        if len(self._recent_voice_commands) > 8:
            del self._recent_voice_commands[: len(self._recent_voice_commands) - 8]

    def _confirm_repair(
        self,
        speech_repair: SpeechRepairResult,
        statuses: list[str],
        errors: list[str],
    ) -> tuple[bool, str]:
        repaired = speech_repair.repaired_transcript.rstrip(" ?")
        prompt = f"Did you mean: {repaired}?"
        self._status(prompt, statuses)
        if self.settings.voice_loop_speak_status or self.settings.tts_enabled:
            self._speak_text(prompt, errors, sleep_after=False)
        samples = self.recorder(self.settings.voice_repair_confirmation_seconds)
        confirmation = self.provider.transcribe(samples, self.settings.voice_sample_rate).text.strip()
        self.voice_loop_logger.info(
            "Repair confirmation transcript={} repaired={}",
            confirmation or "<empty>",
            speech_repair.repaired_transcript,
        )
        if is_confirmation_yes(confirmation):
            self._emit("Repair confirmation: yes")
            return True, "repair confirmed"
        if is_confirmation_no(confirmation):
            self._emit("Repair confirmation: no")
            return False, "repair not confirmed"
        self._emit(f"Repair confirmation: invalid ({confirmation or '<empty>'})")
        return False, "repair confirmation invalid"

    def _log_speech_repair_diagnostics(self, speech_repair: SpeechRepairResult) -> None:
        self.voice_loop_logger.info(
            "Speech repair raw={} cleaned={} repaired={} confidence={} strategy={} reason={}",
            speech_repair.raw_transcript or "<empty>",
            speech_repair.cleaned_transcript or "<empty>",
            speech_repair.repaired_transcript or "<empty>",
            f"{speech_repair.confidence:.2f}",
            speech_repair.strategy,
            speech_repair.repair_reason,
        )
        self._emit(
            f"{SPEECH_REPAIR_PREFIX} raw={speech_repair.raw_transcript or '<empty>'} | "
            f"cleaned={speech_repair.cleaned_transcript or '<empty>'} | "
            f"repaired={speech_repair.repaired_transcript or '<empty>'} | "
            f"confidence={speech_repair.confidence:.2f} | "
            f"strategy={speech_repair.strategy} | "
            f"reason={speech_repair.repair_reason}"
        )

    def _log_wake_diagnostics(self, samples: list[float], wake_detection: WakeDetectionResult) -> None:
        metrics = calculate_audio_capture_metrics(
            samples,
            self.settings.voice_sample_rate,
            self.settings.voice_vad_threshold,
            vad_window_ms=self.settings.voice_vad_window_ms,
            noise_multiplier=self.settings.voice_vad_noise_multiplier,
        )
        self.voice_loop_logger.info(
            "Wake diagnostics provider={} score={} threshold={} average_rms={} max_rms={} noise_floor={} "
            "effective_vad_threshold={} vad_trigger_seconds={} vad_crossed={}",
            self.wake_provider_resolution.effective_provider,
            f"{wake_detection.score:.3f}",
            f"{wake_detection.threshold:.3f}",
            f"{metrics.average_rms:.6f}",
            f"{metrics.max_rms:.6f}",
            f"{metrics.noise_floor:.6f}",
            f"{metrics.effective_vad_threshold:.6f}",
            _format_optional_seconds(metrics.vad_trigger_seconds),
            metrics.vad_threshold_crossed,
        )
        self._emit(
            f"{WAKE_DIAGNOSTICS_PREFIX} provider={self.wake_provider_resolution.effective_provider} "
            f"score={wake_detection.score:.3f} threshold={wake_detection.threshold:.3f} "
            f"average_rms={metrics.average_rms:.6f} max_rms={metrics.max_rms:.6f} "
            f"noise_floor={metrics.noise_floor:.6f} effective_vad_threshold={metrics.effective_vad_threshold:.6f} "
            f"vad_trigger_seconds={_format_optional_seconds(metrics.vad_trigger_seconds)} "
            f"vad_crossed={_yes_no(metrics.vad_threshold_crossed)}"
        )

    def _log_capture_audio_diagnostics(
        self,
        metrics: AudioCaptureMetrics,
        record_seconds: float,
        *,
        transcript_confidence: float | None = None,
        command_score: float | None = None,
    ) -> None:
        self.voice_loop_logger.info(
            "Command audio diagnostics provider={} sample_rate={} record_seconds={} average_rms={} max_rms={} "
            "noise_floor={} vad_threshold={} effective_vad_threshold={} vad_trigger_seconds={} "
            "speech_window_ratio={} transcript_confidence={} command_score={} vad_crossed={}",
            self.provider.name,
            self.settings.voice_sample_rate,
            f"{record_seconds:.2f}",
            f"{metrics.average_rms:.6f}",
            f"{metrics.max_rms:.6f}",
            f"{metrics.noise_floor:.6f}",
            f"{metrics.vad_threshold:.6f}",
            f"{metrics.effective_vad_threshold:.6f}",
            _format_optional_seconds(metrics.vad_trigger_seconds),
            f"{metrics.speech_window_ratio:.2f}",
            _format_optional_float(transcript_confidence),
            _format_optional_float(command_score),
            metrics.vad_threshold_crossed,
        )
        self._emit(
            f"{CAPTURE_DIAGNOSTICS_PREFIX} provider={self.provider.name} "
            f"sample_rate={self.settings.voice_sample_rate} record_seconds={record_seconds:.2f} "
            f"average_rms={metrics.average_rms:.6f} max_rms={metrics.max_rms:.6f} "
            f"noise_floor={metrics.noise_floor:.6f} effective_vad_threshold={metrics.effective_vad_threshold:.6f} "
            f"vad_trigger_seconds={_format_optional_seconds(metrics.vad_trigger_seconds)} "
            f"speech_window_ratio={metrics.speech_window_ratio:.2f} "
            f"transcript_confidence={_format_optional_float(transcript_confidence)} "
            f"command_score={_format_optional_float(command_score)} "
            f"vad_crossed={_yes_no(metrics.vad_threshold_crossed)}"
        )


def is_stop_command(command_text: str) -> bool:
    normalized = " ".join(command_text.lower().strip().split())
    return normalized in STOP_COMMANDS


def _is_incomplete_transcript(validation: CommandValidationResult) -> bool:
    return bool(validation.rejection_reason and validation.rejection_reason.startswith("incomplete transcript:"))


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _format_optional_seconds(value: float | None) -> str:
    if value is None:
        return "none"
    return f"{value:.2f}"


def _format_optional_float(value: float | None) -> str:
    if value is None:
        return "unknown"
    return f"{value:.2f}"
