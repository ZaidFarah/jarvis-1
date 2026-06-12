from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from loguru import logger

from config.settings import AppSettings


_NOTIFICATION_LOG_SINK_ID: int | None = None


class NotificationSender(Protocol):
    def send(self, title: str, message: str) -> None:
        pass


@dataclass(frozen=True)
class NotificationResult:
    enabled: bool
    provider: str
    provider_available: bool
    request_attempted: bool
    delivered: bool
    title: str
    message: str
    log_file: Path
    safe_error: str | None = None
    fallback_reason: str | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        if not self.enabled:
            return True
        if not self.provider_available:
            return True
        return self.delivered


class NotificationService:
    """Optional Windows toast notifications with safe fallback behavior."""

    def __init__(
        self,
        settings: AppSettings,
        sender_factory: Callable[[], NotificationSender] | None = None,
    ) -> None:
        self.settings = settings
        self.sender_factory = sender_factory or self._default_sender_factory
        self.log_file = self.settings.log_dir / "notifications.log"
        self.notifications_logger = logger.bind(notifications=True)
        self._sender: NotificationSender | None = None
        self._sender_error: str | None = None
        self._ensure_log_sink()

    @property
    def enabled(self) -> bool:
        return self.settings.notifications_enabled

    @property
    def provider_name(self) -> str:
        return self.settings.notification_provider

    @property
    def provider_available(self) -> bool:
        if not self.enabled:
            return False
        if self.provider_name != "windows_toast":
            return False
        return self._get_sender() is not None

    def run_check(self) -> NotificationResult:
        self.notifications_logger.info(
            "Running notification diagnostic enabled={} provider={}",
            self.enabled,
            self.provider_name,
        )
        if not self.enabled:
            message = "Notifications are disabled."
            self.notifications_logger.info(message)
            return self._result(
                request_attempted=False,
                delivered=False,
                title="",
                message=message,
                safe_error=None,
                fallback_reason=message,
                errors=[],
            )

        if not self.provider_available:
            fallback_reason = self._sender_error or self._unavailable_message()
            self.notifications_logger.warning(fallback_reason)
            return self._result(
                request_attempted=False,
                delivered=False,
                title="",
                message=fallback_reason,
                safe_error=fallback_reason,
                fallback_reason=fallback_reason,
                errors=[fallback_reason],
            )

        return self.send_notification(
            "Jarvis notification check",
            "Jarvis notification diagnostics are working.",
        )

    def send_notification(self, title: str, message: str) -> NotificationResult:
        clean_title = self._clean_text(title)
        clean_message = self._clean_text(message)
        self.notifications_logger.info(
            "Sending notification provider={} enabled={} title_chars={} message_chars={}",
            self.provider_name,
            self.enabled,
            len(clean_title),
            len(clean_message),
        )

        if not self.enabled:
            fallback_reason = "Notifications are disabled."
            self.notifications_logger.info(fallback_reason)
            return self._result(
                request_attempted=False,
                delivered=False,
                title=clean_title,
                message=clean_message,
                safe_error=None,
                fallback_reason=fallback_reason,
                errors=[],
            )

        sender = self._get_sender()
        if sender is None:
            fallback_reason = self._sender_error or self._unavailable_message()
            self.notifications_logger.warning(fallback_reason)
            return self._result(
                request_attempted=False,
                delivered=False,
                title=clean_title,
                message=clean_message,
                safe_error=fallback_reason,
                fallback_reason=fallback_reason,
                errors=[fallback_reason],
            )

        try:
            sender.send(clean_title, clean_message)
            self.notifications_logger.info("Notification delivered")
            return self._result(
                request_attempted=True,
                delivered=True,
                title=clean_title,
                message=clean_message,
                safe_error=None,
                fallback_reason=None,
                errors=[],
            )
        except Exception as exc:  # pragma: no cover - defensive boundary
            safe_error = format_notification_error(exc)
            self.notifications_logger.error("Notification delivery failed: {}", safe_error)
            return self._result(
                request_attempted=True,
                delivered=False,
                title=clean_title,
                message=clean_message,
                safe_error=safe_error,
                fallback_reason=safe_error,
                errors=[safe_error],
            )

    def send_reminder_notification(self, reminders: list[object]) -> NotificationResult:
        if not reminders:
            return self._result(
                request_attempted=False,
                delivered=False,
                title="",
                message="",
                safe_error=None,
                fallback_reason="No reminders to notify.",
                errors=[],
            )

        title = "Jarvis reminder"
        if len(reminders) == 1:
            reminder = reminders[0]
            reminder_title = getattr(reminder, "title", "Reminder")
            remind_at = getattr(reminder, "remind_at", "")
            message = f"{reminder_title} at {remind_at}".strip()
        else:
            first = getattr(reminders[0], "title", "Reminder")
            message = f"{len(reminders)} reminders are due. First: {first}"
        return self.send_notification(title, message)

    def _get_sender(self) -> NotificationSender | None:
        if self._sender is not None:
            return self._sender
        if self._sender_error is not None:
            return None

        if self.provider_name != "windows_toast":
            self._sender_error = f"Unsupported notification provider: {self.provider_name}"
            return None

        if os.name != "nt":
            self._sender_error = "Windows toast notifications are only available on Windows."
            return None

        try:
            self._sender = self.sender_factory()
        except ImportError as exc:
            self._sender_error = "winotify is not installed."
            self.notifications_logger.warning("winotify import failed: {}", format_notification_error(exc))
            return None
        except Exception as exc:  # pragma: no cover - defensive boundary
            self._sender_error = format_notification_error(exc)
            self.notifications_logger.warning("Notification sender creation failed: {}", self._sender_error)
            return None
        return self._sender

    def _result(
        self,
        request_attempted: bool,
        delivered: bool,
        title: str,
        message: str,
        safe_error: str | None,
        fallback_reason: str | None,
        errors: list[str],
    ) -> NotificationResult:
        return NotificationResult(
            enabled=self.enabled,
            provider=self.provider_name,
            provider_available=self.provider_available,
            request_attempted=request_attempted,
            delivered=delivered,
            title=title,
            message=message,
            log_file=self.log_file,
            safe_error=safe_error,
            fallback_reason=fallback_reason,
            errors=errors,
        )

    def _ensure_log_sink(self) -> None:
        global _NOTIFICATION_LOG_SINK_ID
        if _NOTIFICATION_LOG_SINK_ID is not None:
            return

        self.settings.log_dir.mkdir(parents=True, exist_ok=True)
        _NOTIFICATION_LOG_SINK_ID = logger.add(
            self.log_file,
            level="DEBUG",
            rotation="1 MB",
            retention="7 days",
            encoding="utf-8",
            backtrace=False,
            diagnose=False,
            filter=lambda record: bool(record["extra"].get("notifications")),
        )

    def _default_sender_factory(self) -> NotificationSender:
        from winotify import Notification

        class WinotifySender:
            def __init__(self, app_id: str) -> None:
                self.app_id = app_id

            def send(self, title: str, message: str) -> None:
                toast = Notification(app_id=self.app_id, title=title, msg=message, duration="short")
                toast.show()

        return WinotifySender(self.settings.app_name)

    @staticmethod
    def _clean_text(value: str) -> str:
        cleaned = " ".join(value.strip().split())
        return cleaned

    @staticmethod
    def _unavailable_message() -> str:
        return "Windows toast notifications are unavailable on this platform."


def format_notification_error(error: Exception) -> str:
    error_type = type(error).__name__
    message = str(error).strip() or "No error details provided."
    return f"{error_type}: {_redact_secret_like_text(message)}"


def format_notification_check_report(result: NotificationResult) -> str:
    lines = [
        "Jarvis Notification Check",
        "=========================",
        f"Notifications enabled: {_yes_no(result.enabled)}",
        f"Provider: {result.provider}",
        f"Provider available: {_yes_no(result.provider_available)}",
        f"Request attempted: {_yes_no(result.request_attempted)}",
        f"Delivered: {_yes_no(result.delivered)}",
        f"Diagnostic log: {result.log_file}",
    ]

    if result.title:
        lines.extend(["", f"Title: {result.title}"])
    if result.message:
        lines.extend(["", f"Message: {result.message}"])
    if result.fallback_reason:
        lines.extend(["", "Fallback reason:", f"  {result.fallback_reason}"])
    if result.safe_error:
        lines.extend(["", "Error:", f"  {result.safe_error}"])
    return "\n".join(lines)


def _redact_secret_like_text(text: str) -> str:
    redacted_words: list[str] = []
    for word in text.split():
        if word.startswith("sk-") or "API_KEY" in word or "TOKEN" in word or "PASSWORD" in word:
            redacted_words.append("[redacted]")
        else:
            redacted_words.append(word)
    return " ".join(redacted_words)


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
