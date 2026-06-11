from __future__ import annotations

import importlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from assistant.core import AssistantCore, AssistantResponse
from config.settings import AppSettings
from voice.interfaces import TranscriptionResult
from voice.stt import create_speech_to_text_provider
from voice.tts import TextToSpeechResult, speak_text
from voice.wake import WakeDetectionResult, WakeDetector, remove_wake_phrase_prefix


_VOICE_COMMAND_LOG_SINK_ID: int | None = None


StatusCallback = Callable[[str], None]
Recorder = Callable[[float], list[float]]


@dataclass(frozen=True)
class VoiceCommandTestReport:
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

    @property
    def wake_detected(self) -> bool:
        return self.wake_detection.detected

    @property
    def is_successful(self) -> bool:
        return self.provider_available and not self.errors


class VoiceCommandTestRunner:
    """Controlled one-shot wake phrase plus command test.

    This runner does not start a background listener. It records exactly one wake
    clip and, only if wake detection succeeds, one command clip.
    """

    def __init__(
        self,
        settings: AppSettings,
        assistant: AssistantCore | None = None,
        provider: Any | None = None,
        tts_provider: Any | None = None,
        speak_requested: bool = False,
        recorder: Recorder | None = None,
        status_callback: StatusCallback | None = None,
    ) -> None:
        self.settings = settings
        self.assistant = assistant or AssistantCore()
        self.provider = provider or create_speech_to_text_provider(settings)
        self.tts_provider = tts_provider
        self.speak_requested = speak_requested
        self.recorder = recorder or self._record_microphone
        self.status_callback = status_callback
        self.log_file = self.settings.log_dir / "voice_command_test.log"
        self.voice_logger = logger.bind(voice_command_test=True)
        self._ensure_voice_command_log_sink()

    def run(self) -> VoiceCommandTestReport:
        statuses: list[str] = []
        errors: list[str] = []
        wake_transcription = ""
        raw_command_transcription = ""
        cleaned_command = ""
        assistant_response: AssistantResponse | None = None
        tts_result: TextToSpeechResult | None = None
        detector = WakeDetector(
            wake_phrase=self.settings.wake_phrase,
            aliases=self.settings.wake_alias_list,
            threshold=self.settings.wake_match_threshold,
        )
        empty_detection = detector.detect("")

        self.voice_logger.info("Starting controlled voice command test")

        if not self.provider.available:
            message = "Speech-to-text provider is not available. Voice command test cannot run."
            self.voice_logger.error(message)
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

        try:
            self._status("Listening for wake phrase", statuses)
            wake_samples = self.recorder(self.settings.wake_listen_seconds)
            wake_transcription = self.provider.transcribe(wake_samples, self.settings.voice_sample_rate).text.strip()
            wake_detection = detector.detect(wake_transcription)
            self.voice_logger.info(
                "Wake transcription={} detected={} score={}",
                wake_transcription or "<empty>",
                wake_detection.detected,
                f"{wake_detection.score:.3f}",
            )
        except Exception as exc:
            message = f"Wake phrase stage failed: {type(exc).__name__}: {exc}"
            self.voice_logger.exception(message)
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

        try:
            self._status("Listening for command", statuses)
            command_samples = self.recorder(self.settings.voice_record_seconds)
            raw_command_transcription = self.provider.transcribe(command_samples, self.settings.voice_sample_rate).text.strip()
            cleaned_command = remove_wake_phrase_prefix(
                raw_command_transcription,
                wake_phrase=self.settings.wake_phrase,
                aliases=self.settings.wake_alias_list,
            )
            self.voice_logger.info(
                "Command transcription={} cleaned={}",
                raw_command_transcription or "<empty>",
                cleaned_command or "<empty>",
            )
        except Exception as exc:
            message = f"Command stage failed: {type(exc).__name__}: {exc}"
            self.voice_logger.exception(message)
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

        self._status("Thinking", statuses)
        assistant_response = self.assistant.handle_command(cleaned_command)
        self.voice_logger.info("Assistant response={}", assistant_response.text)
        if assistant_response.accepted and (self.speak_requested or self.settings.tts_enabled):
            self._status("Speaking", statuses)
            tts_result = speak_text(
                assistant_response.text,
                self.settings,
                speak_requested=self.speak_requested,
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
        )

    def _status(self, status: str, statuses: list[str]) -> None:
        statuses.append(status)
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
    ) -> VoiceCommandTestReport:
        return VoiceCommandTestReport(
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
            raise RuntimeError(f"sounddevice is required for voice-command-test: {exc}") from exc

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

    def _ensure_voice_command_log_sink(self) -> None:
        global _VOICE_COMMAND_LOG_SINK_ID
        if _VOICE_COMMAND_LOG_SINK_ID is not None:
            return

        self.settings.log_dir.mkdir(parents=True, exist_ok=True)
        _VOICE_COMMAND_LOG_SINK_ID = logger.add(
            self.log_file,
            level="DEBUG",
            rotation="1 MB",
            retention="7 days",
            encoding="utf-8",
            backtrace=False,
            diagnose=False,
            filter=lambda record: bool(record["extra"].get("voice_command_test")),
        )


def format_voice_command_report(report: VoiceCommandTestReport) -> str:
    lines = [
        "Jarvis Voice Command Test",
        "=========================",
        f"provider: {report.provider_name}",
        f"provider available: {_yes_no(report.provider_available)}",
        f"diagnostic log: {report.log_file}",
        "",
        "Status flow:",
        f"  {' -> '.join(report.statuses) if report.statuses else '<none>'}",
        "",
        "Wake phrase:",
        f"  transcription: {report.wake_transcription if report.wake_transcription else '<no text detected>'}",
        f"  detected: {_yes_no(report.wake_detection.detected)}",
        f"  match type: {report.wake_detection.match_type}",
        f"  matched phrase: {report.wake_detection.matched_phrase if report.wake_detection.detected else '<none>'}",
        f"  score: {report.wake_detection.score:.3f}",
        "",
        "Command:",
        f"  raw command transcription: {report.raw_command_transcription if report.raw_command_transcription else '<not recorded>'}",
        f"  cleaned command: {report.cleaned_command if report.cleaned_command else '<empty>'}",
    ]

    if report.assistant_response is not None:
        lines.extend(["", "Jarvis response:", f"  {report.assistant_response.text}"])

    if report.tts_result is not None:
        lines.extend(
            [
                "",
                "Text-to-speech:",
                f"  provider: {report.tts_result.provider_name}",
                f"  requested provider: {report.tts_result.requested_provider_name or report.tts_result.provider_name}",
                f"  provider available: {_yes_no(report.tts_result.provider_available)}",
                f"  fallback used: {_yes_no(report.tts_result.fallback_used)}",
                f"  spoken: {_yes_no(report.tts_result.spoken)}",
                f"  diagnostic log: {report.tts_result.log_file}",
            ]
        )
        if report.tts_result.audio_file:
            lines.append(f"  audio file: {report.tts_result.audio_file}")
        if report.tts_result.fallback_reason:
            lines.extend(["", "TTS fallback reason:", f"  {report.tts_result.fallback_reason}"])

    if report.errors:
        lines.append("")
        lines.append("Errors:")
        lines.extend(f"  - {error}" for error in report.errors)

    return "\n".join(lines)


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
