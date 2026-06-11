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
from voice.stt import create_speech_to_text_provider
from voice.tts import TextToSpeechResult, speak_text
from voice.voice_command_test import COMMAND_PROMPT, LISTENING_FOR_COMMAND_PROMPT, NO_COMMAND_DETECTED_MESSAGE
from voice.wake import WakeDetectionResult, WakeDetector, remove_wake_phrase_prefix


_VOICE_LOOP_LOG_SINK_ID: int | None = None
_VOICE_LOOP_LOG_FILE: Path | None = None


StatusCallback = Callable[[str], None]
Recorder = Callable[[float], list[float]]
Sleeper = Callable[[float], None]
Beeper = Callable[[], None]


STOP_COMMANDS = {
    "stop listening",
    "sleep jarvis",
    "jarvis sleep",
    "exit jarvis",
    "shutdown jarvis",
}
VOICE_LOOP_STARTED_MESSAGE = "Jarvis voice loop started. Press Ctrl+C to stop."
VOICE_LOOP_STOPPED_MESSAGE = "Jarvis voice loop stopped."
STOP_COMMAND_DETECTED_MESSAGE = "Stop command detected. Exiting voice loop."


@dataclass(frozen=True)
class VoiceLoopCycleReport:
    provider_name: str
    provider_available: bool
    wake_transcription: str
    wake_detection: WakeDetectionResult
    raw_command_transcription: str
    cleaned_command: str
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
        self._stop_requested = False
        self._ensure_voice_loop_log_sink()

    def request_stop(self) -> None:
        self._stop_requested = True

    def run(self, max_cycles: int | None = None) -> list[VoiceLoopCycleReport]:
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

        self._status("Sleeping", statuses)

        try:
            self._status("Listening for wake phrase", statuses)
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

        self._status("Wake detected", statuses)
        self._status(COMMAND_PROMPT, statuses)
        if self.settings.voice_command_start_delay_seconds > 0:
            self.sleeper(self.settings.voice_command_start_delay_seconds)
        self.beeper()

        try:
            self._status(LISTENING_FOR_COMMAND_PROMPT, statuses)
            command_samples = self.recorder(self.settings.voice_command_record_seconds)
            raw_command_transcription = self.provider.transcribe(command_samples, self.settings.voice_sample_rate).text.strip()
            cleaned_command = remove_wake_phrase_prefix(
                raw_command_transcription,
                wake_phrase=self.settings.wake_phrase,
                aliases=self.settings.wake_alias_list,
            )
            self.voice_loop_logger.info(
                "Command transcription={} cleaned={}",
                raw_command_transcription or "<empty>",
                cleaned_command or "<empty>",
            )
        except Exception as exc:
            message = f"Command stage failed: {type(exc).__name__}: {exc}"
            self.voice_loop_logger.exception(message)
            errors.append(message)
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

        if not cleaned_command:
            self.voice_loop_logger.warning(NO_COMMAND_DETECTED_MESSAGE)
            errors.append(NO_COMMAND_DETECTED_MESSAGE)
            self._status(NO_COMMAND_DETECTED_MESSAGE, statuses)
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

        if is_stop_command(cleaned_command):
            self.voice_loop_logger.info("Stop command detected: {}", cleaned_command)
            self._status(STOP_COMMAND_DETECTED_MESSAGE, statuses)
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
                stop_requested=True,
            )

        self._status("Thinking", statuses)
        assistant_response = self.assistant.handle_command(cleaned_command)
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
            stop_requested=stop_requested,
        )

    def _status(self, status: str, statuses: list[str]) -> None:
        statuses.append(status)
        self.voice_loop_logger.info("Status={}", status)
        if self.status_callback is not None:
            self.status_callback(status)

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
        return VoiceLoopCycleReport(
            provider_name=self.provider.name,
            provider_available=bool(self.provider.available),
            wake_transcription=wake_transcription,
            wake_detection=wake_detection,
            raw_command_transcription=raw_command_transcription,
            cleaned_command=cleaned_command,
            assistant_response=assistant_response,
            tts_result=tts_result,
            statuses=statuses,
            log_file=self.log_file,
            errors=errors,
            stop_requested=stop_requested,
        )

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
