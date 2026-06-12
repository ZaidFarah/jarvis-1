from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from loguru import logger

from assistant.core import AssistantResponse
from config.settings import AppSettings
from reminders.service import ReminderService
from voice.tts import TextToSpeechResult, speak_text


_REMINDER_WATCH_LOG_SINK_ID: int | None = None
_REMINDER_WATCH_LOG_FILE: Path | None = None


StatusCallback = Callable[[str], None]


@dataclass
class ReminderWatcherSummary:
    checks: int = 0
    due_notifications: int = 0
    errors: int = 0

    def format(self) -> str:
        return (
            "Reminder watcher summary: "
            f"checks={self.checks}, "
            f"due notifications={self.due_notifications}, "
            f"errors={self.errors}"
        )


@dataclass(frozen=True)
class ReminderWatcherResult:
    running: bool
    started: bool
    stopped: bool
    summary: ReminderWatcherSummary
    last_response: AssistantResponse | None = None
    tts_result: TextToSpeechResult | None = None
    log_file: Path | None = None
    errors: list[str] = field(default_factory=list)


class ReminderWatcher:
    """Background reminder watcher that lives only while Jarvis is running."""

    def __init__(
        self,
        settings: AppSettings,
        reminder_service: ReminderService | None = None,
        speak_requested: bool = False,
        status_callback: StatusCallback | None = None,
        sleeper: Callable[[float], None] | None = None,
        tts_provider: object | None = None,
    ) -> None:
        self.settings = settings
        if reminder_service is not None:
            self.reminder_service = reminder_service
        elif settings.reminders_enabled and settings.reminders_check_enabled and settings.reminders_watch_enabled:
            self.reminder_service = ReminderService(settings)
        else:
            self.reminder_service = None
        self.speak_requested = speak_requested
        self.status_callback = status_callback
        self.sleeper = sleeper or time.sleep
        self.tts_provider = tts_provider
        self.log_file = self.reminder_service.log_file if self.reminder_service is not None else self.settings.log_dir / "reminders.log"
        self.watch_logger = logger.bind(reminder_watch=True)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.summary = ReminderWatcherSummary()
        self.last_response: AssistantResponse | None = None
        self.last_tts_result: TextToSpeechResult | None = None
        self.errors: list[str] = []
        self._ensure_log_sink()

    @property
    def available(self) -> bool:
        return bool(
            self.settings.reminders_enabled
            and self.settings.reminders_check_enabled
            and self.settings.reminders_watch_enabled
            and self.reminder_service is not None
        )

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        if self.running:
            return True
        if not self.available:
            self._emit("Reminder watcher is disabled.")
            return False

        self._stop_event.clear()
        self.summary = ReminderWatcherSummary()
        self.errors = []
        self.last_response = None
        self.last_tts_result = None
        self._emit("Reminder watcher started.")
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=max(1.0, float(self.settings.reminders_check_interval_seconds) + 1.0))
        self._thread = None
        self._emit(self.summary.format())
        self._emit("Reminder watcher stopped.")

    def run_forever(self) -> ReminderWatcherResult:
        started = self.start()
        if not started:
            return self._result(started=False, stopped=True)

        while self.running and not self._stop_event.is_set():
            self.sleeper(0.1)
        return self._result(started=True, stopped=True)

    def run_once(self) -> ReminderWatcherResult:
        if not self.available:
            self._emit("Reminder watcher is disabled.")
            return self._result(started=False, stopped=True)

        try:
            self._check_once()
        except Exception as exc:  # pragma: no cover - defensive boundary
            self.summary.errors += 1
            message = f"Reminder watcher failed: {type(exc).__name__}: {exc}"
            self.errors.append(message)
            self._emit(message)
        return self._result(started=True, stopped=True)

    def _run(self) -> None:
        interval = float(self.settings.reminders_check_interval_seconds)
        self.watch_logger.info("Reminder watcher loop started interval={}", interval)
        try:
            while not self._stop_event.is_set():
                self._check_once()
                if self._stop_event.is_set():
                    break
                self._wait(interval)
        except Exception as exc:  # pragma: no cover - defensive boundary
            self.summary.errors += 1
            message = f"Reminder watcher failed: {type(exc).__name__}: {exc}"
            self.errors.append(message)
            self._emit(message)
        finally:
            self.watch_logger.info("Reminder watcher loop stopped")

    def _check_once(self) -> None:
        self.summary.checks += 1
        self._emit("Checking reminders...")
        response = self.reminder_service.check_due_reminders()
        self.last_response = AssistantResponse(
            text=response.text,
            accepted=response.success,
            source="reminders",
            error=response.safe_error,
        )
        self.watch_logger.info("Reminder watcher result={}", response.text)
        self._emit(response.text)

        if response.due_reminders:
            self.summary.due_notifications += len(response.due_reminders)
            if self.speak_requested or self.settings.reminders_watch_speak or self.settings.tts_enabled:
                self.last_tts_result = speak_text(
                    response.text,
                    self.settings,
                    speak_requested=True,
                    provider=self.tts_provider,
                )
                if self.last_tts_result.error:
                    self.summary.errors += 1
                    self.errors.append(self.last_tts_result.error)

    def _wait(self, interval: float) -> None:
        if interval <= 0:
            return
        self._stop_event.wait(interval)

    def _emit(self, message: str) -> None:
        self.watch_logger.info(message)
        if self.status_callback is not None:
            self.status_callback(message)

    def _result(self, started: bool, stopped: bool) -> ReminderWatcherResult:
        return ReminderWatcherResult(
            running=self.running,
            started=started,
            stopped=stopped,
            summary=self.summary,
            last_response=self.last_response,
            tts_result=self.last_tts_result,
            log_file=self.log_file,
            errors=list(self.errors),
        )

    def _ensure_log_sink(self) -> None:
        global _REMINDER_WATCH_LOG_FILE, _REMINDER_WATCH_LOG_SINK_ID
        if _REMINDER_WATCH_LOG_SINK_ID is not None and _REMINDER_WATCH_LOG_FILE == self.log_file:
            return

        if _REMINDER_WATCH_LOG_SINK_ID is not None:
            try:
                logger.remove(_REMINDER_WATCH_LOG_SINK_ID)
            except ValueError:
                pass

        self.settings.log_dir.mkdir(parents=True, exist_ok=True)
        _REMINDER_WATCH_LOG_SINK_ID = logger.add(
            self.log_file,
            level="DEBUG",
            rotation="1 MB",
            retention="7 days",
            encoding="utf-8",
            backtrace=False,
            diagnose=False,
            filter=lambda record: bool(record["extra"].get("reminder_watch")),
        )
        _REMINDER_WATCH_LOG_FILE = self.log_file
