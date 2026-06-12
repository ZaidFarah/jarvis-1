from __future__ import annotations

import re
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from loguru import logger

from config.settings import AppSettings


_CALENDAR_LOG_SINK_ID: int | None = None
_CALENDAR_LOG_FILE: Path | None = None


class CalendarClient(Protocol):
    def list_events(self, start: datetime, end: datetime) -> list[dict[str, Any]]: ...


CalendarClientFactory = Callable[[AppSettings], CalendarClient]


@dataclass(frozen=True)
class CalendarEvent:
    summary: str
    start: str
    end: str


@dataclass(frozen=True)
class CalendarQueryResult:
    success: bool
    text: str
    provider: str
    day_label: str
    request_attempted: bool
    authenticated: bool
    client_secret_detected: bool
    token_detected: bool
    safe_error: str | None = None


@dataclass(frozen=True)
class CalendarCheckReport:
    enabled: bool
    provider: str
    client_secret_detected: bool
    token_detected: bool
    authenticated: bool
    authentication_status: str
    setup_guide: str | None
    day_label: str
    request_attempted: bool
    success: bool
    text: str
    safe_error: str | None
    log_file: Path
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        if not self.enabled:
            return True
        if not self.client_secret_detected or not self.token_detected:
            return True
        return self.success


@dataclass(frozen=True)
class CalendarAuthReport:
    enabled: bool
    client_secret_detected: bool
    token_detected: bool
    token_path: Path
    credentials_dir_created: bool
    authenticated: bool
    setup_status: str
    text: str
    safe_error: str | None
    log_file: Path
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        if not self.enabled:
            return True
        if not self.client_secret_detected:
            return True
        return self.authenticated


class CalendarService:
    """Safe read-only Google Calendar foundation with explicit configuration."""

    def __init__(
        self,
        settings: AppSettings,
        client_factory: CalendarClientFactory | None = None,
    ) -> None:
        self.settings = settings
        self.client_factory = client_factory or self._default_client_factory
        self.log_file = self.settings.log_dir / "calendar.log"
        self.calendar_logger = logger.bind(calendar=True)
        self._ensure_calendar_log_sink()

    def current_events(self, day_label: str = "today") -> CalendarQueryResult:
        target_date = self._resolve_day_label(day_label)
        provider = "google_calendar"
        client_secret_detected = self.settings.has_calendar_client_secret
        token_detected = self.settings.has_calendar_token

        self.calendar_logger.info(
            "Calendar query enabled={} day={} client_secret_detected={} token_detected={}",
            self.settings.calendar_enabled,
            day_label,
            client_secret_detected,
            token_detected,
        )

        if not self.settings.calendar_enabled:
            message = self._disabled_message(day_label)
            return self._result(
                success=False,
                text=message,
                provider=provider,
                day_label=day_label,
                request_attempted=False,
                authenticated=False,
                client_secret_detected=client_secret_detected,
                token_detected=token_detected,
                safe_error=message,
            )

        if not client_secret_detected:
            message = "Calendar is enabled, but the Google client secret file is missing."
            self.calendar_logger.warning(message)
            return self._result(
                success=False,
                text=self._credentials_missing_message(day_label),
                provider=provider,
                day_label=day_label,
                request_attempted=False,
                authenticated=False,
                client_secret_detected=False,
                token_detected=token_detected,
                safe_error=message,
            )

        if not token_detected:
            message = "Calendar is enabled, but the calendar token file is missing."
            self.calendar_logger.warning(message)
            return self._result(
                success=False,
                text=self._credentials_missing_message(day_label),
                provider=provider,
                day_label=day_label,
                request_attempted=False,
                authenticated=False,
                client_secret_detected=True,
                token_detected=False,
                safe_error=message,
            )

        try:
            client = self.client_factory(self.settings)
            events = client.list_events(*self._day_window(target_date))
            text = self._format_events(day_label, target_date, events)
            self.calendar_logger.info("Calendar request succeeded day={} events={}", day_label, len(events))
            return self._result(
                success=True,
                text=text,
                provider=provider,
                day_label=day_label,
                request_attempted=True,
                authenticated=True,
                client_secret_detected=True,
                token_detected=True,
            )
        except Exception as exc:
            safe_error = format_calendar_error(exc)
            self.calendar_logger.error("Calendar request failed: {}", safe_error)
            return self._result(
                success=False,
                text=self._service_unavailable_message(day_label),
                provider=provider,
                day_label=day_label,
                request_attempted=True,
                authenticated=False,
                client_secret_detected=True,
                token_detected=True,
                safe_error=safe_error,
            )

    def auth_calendar(self) -> CalendarAuthReport:
        credentials_dir_created = self.settings.calendar_token_path.parent.exists()
        self.settings.calendar_token_path.parent.mkdir(parents=True, exist_ok=True)
        credentials_dir_created = credentials_dir_created or self.settings.calendar_token_path.parent.exists()

        client_secret_detected = self.settings.has_calendar_client_secret
        token_detected = self.settings.has_calendar_token
        self.calendar_logger.info(
            "Calendar auth enabled={} client_secret_detected={} token_detected={}",
            self.settings.calendar_enabled,
            client_secret_detected,
            token_detected,
        )

        if not client_secret_detected:
            message = self._auth_guide_message(missing_client_secret=True, missing_token=not token_detected)
            return self._auth_report(
                client_secret_detected=False,
                token_detected=token_detected,
                credentials_dir_created=credentials_dir_created,
                authenticated=False,
                setup_status="missing client secret",
                text=message,
                safe_error="Google client secret file is missing.",
            )

        try:
            credentials = self._load_credentials()
            if credentials is not None and credentials.valid:
                self._save_credentials(credentials)
                return self._auth_report(
                    client_secret_detected=True,
                    token_detected=True,
                    credentials_dir_created=credentials_dir_created,
                    authenticated=True,
                    setup_status="authenticated",
                    text="Google Calendar is already authenticated.",
                    safe_error=None,
                )

            if credentials is not None and getattr(credentials, "expired", False) and getattr(credentials, "refresh_token", None):
                credentials.refresh(self._request_adapter())
                self._save_credentials(credentials)
                return self._auth_report(
                    client_secret_detected=True,
                    token_detected=True,
                    credentials_dir_created=credentials_dir_created,
                    authenticated=True,
                    setup_status="authenticated",
                    text="Google Calendar authentication refreshed successfully.",
                    safe_error=None,
                )

            flow = self._build_flow()
            try:
                credentials = flow.run_local_server(port=0)
            except Exception:
                credentials = flow.run_console()
            self._save_credentials(credentials)
            return self._auth_report(
                client_secret_detected=True,
                token_detected=True,
                credentials_dir_created=credentials_dir_created,
                authenticated=True,
                setup_status="authenticated",
                text="Google Calendar authentication completed successfully.",
                safe_error=None,
            )
        except Exception as exc:
            safe_error = format_calendar_error(exc)
            self.calendar_logger.error("Calendar auth failed: {}", safe_error)
            return self._auth_report(
                client_secret_detected=True,
                token_detected=self.settings.has_calendar_token,
                credentials_dir_created=credentials_dir_created,
                authenticated=False,
                setup_status="authentication failed",
                text=self._auth_guide_message(missing_client_secret=False, missing_token=not self.settings.has_calendar_token),
                safe_error=safe_error,
            )

    def run_check(self) -> CalendarCheckReport:
        day_label = "today"
        result = self.current_events(day_label)
        authentication_status = self._authentication_status(result)
        errors = [result.safe_error] if result.safe_error else []
        return CalendarCheckReport(
            enabled=self.settings.calendar_enabled,
            provider=result.provider,
            client_secret_detected=result.client_secret_detected,
            token_detected=result.token_detected,
            authenticated=result.authenticated,
            authentication_status=authentication_status,
            setup_guide=self._setup_guide(result),
            day_label=day_label,
            request_attempted=result.request_attempted,
            success=result.success,
            text=result.text,
            safe_error=result.safe_error,
            log_file=self.log_file,
            errors=errors,
        )

    def _result(
        self,
        success: bool,
        text: str,
        provider: str,
        day_label: str,
        request_attempted: bool,
        authenticated: bool,
        client_secret_detected: bool,
        token_detected: bool,
        safe_error: str | None = None,
    ) -> CalendarQueryResult:
        return CalendarQueryResult(
            success=success,
            text=text,
            provider=provider,
            day_label=day_label,
            request_attempted=request_attempted,
            authenticated=authenticated,
            client_secret_detected=client_secret_detected,
            token_detected=token_detected,
            safe_error=safe_error,
        )

    def _authentication_status(self, result: CalendarQueryResult) -> str:
        if not self.settings.calendar_enabled:
            return "disabled"
        if not result.client_secret_detected:
            return "missing client secret"
        if not result.token_detected:
            return "missing token"
        if result.authenticated:
            return "authenticated"
        return "unavailable"

    def _setup_guide(self, result: CalendarQueryResult) -> str | None:
        if not self.settings.calendar_enabled:
            return (
                "Enable CALENDAR_ENABLED, place the Google OAuth client secret JSON at "
                f"{self.settings.calendar_client_secret_path}, then run `python main.py --calendar-auth`."
            )
        if not result.client_secret_detected:
            return (
                "Place your Google OAuth client secret JSON at "
                f"{self.settings.calendar_client_secret_path} and run `python main.py --calendar-auth`."
            )
        if not result.token_detected:
            return f"Run `python main.py --calendar-auth` to create the token file at {self.settings.calendar_token_path}."
        if not result.authenticated:
            return "Run `python main.py --calendar-auth` to complete Google Calendar sign-in."
        return None

    def _day_window(self, target_date: date) -> tuple[datetime, datetime]:
        start = datetime(target_date.year, target_date.month, target_date.day)
        end = start + timedelta(days=1)
        return start, end

    @staticmethod
    def _resolve_day_label(day_label: str) -> date:
        normalized = " ".join(day_label.lower().strip().split())
        today = date.today()
        if normalized == "today":
            return today
        if normalized == "tomorrow":
            return today + timedelta(days=1)
        return today

    def _format_events(self, day_label: str, target_date: date, events: list[dict[str, Any]]) -> str:
        readable_date = target_date.strftime("%Y-%m-%d")
        if not events:
            return f"No events found for {day_label} ({readable_date})."

        lines = [f"Calendar for {day_label} ({readable_date}):"]
        for event in events:
            summary = str(event.get("summary") or "Untitled event").strip()
            start = self._event_time_text(event.get("start"))
            end = self._event_time_text(event.get("end"))
            location = str(event.get("location") or "").strip()
            label = summary if not location else f"{summary} ({location})"
            if start and end:
                lines.append(f"- {start} to {end}: {label}")
            elif start:
                lines.append(f"- {start}: {label}")
            else:
                lines.append(f"- {label}")
        return "\n".join(lines)

    @staticmethod
    def _event_time_text(value: Any) -> str:
        if isinstance(value, dict):
            return str(value.get("dateTime") or value.get("date") or "").strip()
        return str(value or "").strip()

    def _disabled_message(self, day_label: str) -> str:
        return (
            f"Calendar is disabled. Enable CALENDAR_ENABLED and provide Google Calendar credentials "
            f"to check {day_label}."
        )

    def _credentials_missing_message(self, day_label: str) -> str:
        return (
            f"Calendar credentials are incomplete, so I cannot check {day_label} yet. "
            f"Set CALENDAR_CLIENT_SECRET_PATH and CALENDAR_TOKEN_PATH."
        )

    def _service_unavailable_message(self, day_label: str) -> str:
        return f"I couldn't fetch your calendar for {day_label} right now. Please try again later."

    def _default_client_factory(self, settings: AppSettings) -> CalendarClient:
        client = self._build_calendar_client(settings)
        return client

    def _auth_report(
        self,
        client_secret_detected: bool,
        token_detected: bool,
        credentials_dir_created: bool,
        authenticated: bool,
        setup_status: str,
        text: str,
        safe_error: str | None,
    ) -> CalendarAuthReport:
        errors = [safe_error] if safe_error else []
        return CalendarAuthReport(
            enabled=self.settings.calendar_enabled,
            client_secret_detected=client_secret_detected,
            token_detected=token_detected,
            token_path=self.settings.calendar_token_path,
            credentials_dir_created=credentials_dir_created,
            authenticated=authenticated,
            setup_status=setup_status,
            text=text,
            safe_error=safe_error,
            log_file=self.log_file,
            errors=errors,
        )

    def _auth_guide_message(self, missing_client_secret: bool, missing_token: bool) -> str:
        lines = [
            "Google Calendar setup is incomplete.",
            f"Client secret path: {self.settings.calendar_client_secret_path}",
            f"Token path: {self.settings.calendar_token_path}",
            "",
            "Next steps:",
        ]
        if missing_client_secret:
            lines.append("1. Place your Google OAuth client secret JSON at the client secret path.")
        if missing_token:
            lines.append("2. Run `python main.py --calendar-auth` to create or refresh the token file.")
        else:
            lines.append("1. Run `python main.py --calendar-auth` to sign in and save the token.")
        return "\n".join(lines)

    def _load_credentials(self) -> Any | None:
        if not self.settings.has_calendar_token:
            return None

        try:
            from google.oauth2.credentials import Credentials
        except Exception as exc:
            raise RuntimeError(
                "Google authentication libraries are missing. Install google-auth and google-auth-oauthlib."
            ) from exc

        return Credentials.from_authorized_user_file(str(self.settings.calendar_token_path), scopes=self.settings.calendar_scopes_list)

    def _save_credentials(self, credentials: Any) -> None:
        token_path = self.settings.calendar_token_path
        token_path.parent.mkdir(parents=True, exist_ok=True)
        serialized = getattr(credentials, "to_json", None)
        if callable(serialized):
            token_path.write_text(serialized(), encoding="utf-8")
            return
        raise RuntimeError("Unable to serialize Google Calendar credentials.")

    def _build_flow(self) -> Any:
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
        except Exception as exc:
            raise RuntimeError(
                "Google authentication libraries are missing. Install google-auth and google-auth-oauthlib."
            ) from exc

        return InstalledAppFlow.from_client_secrets_file(
            str(self.settings.calendar_client_secret_path),
            scopes=self.settings.calendar_scopes_list,
        )

    def _build_calendar_client(self, settings: AppSettings) -> CalendarClient:
        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build
        except Exception as exc:
            raise RuntimeError(
                "Google Calendar libraries are missing. Install google-api-python-client, google-auth, and google-auth-oauthlib."
            ) from exc

        if not settings.has_calendar_client_secret:
            raise RuntimeError("Google client secret file is missing.")

        credentials = None
        if settings.has_calendar_token:
            credentials = Credentials.from_authorized_user_file(str(settings.calendar_token_path), scopes=settings.calendar_scopes_list)
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
                settings.calendar_token_path.parent.mkdir(parents=True, exist_ok=True)
                settings.calendar_token_path.write_text(credentials.to_json(), encoding="utf-8")

        if credentials is None or not credentials.valid:
            raise RuntimeError(
                "Google Calendar is not authenticated. Run `python main.py --calendar-auth` to sign in."
            )

        service = build("calendar", "v3", credentials=credentials, cache_discovery=False)

        class _GoogleCalendarClient:
            def __init__(self, calendar_service: Any) -> None:
                self.calendar_service = calendar_service

            def list_events(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
                iso_start = start.isoformat() + "Z"
                iso_end = end.isoformat() + "Z"
                response = (
                    self.calendar_service.events()
                    .list(
                        calendarId="primary",
                        timeMin=iso_start,
                        timeMax=iso_end,
                        singleEvents=True,
                        orderBy="startTime",
                        maxResults=20,
                    )
                    .execute()
                )
                return list(response.get("items", []))

        return _GoogleCalendarClient(service)

    def _request_adapter(self) -> Any:
        try:
            from google.auth.transport.requests import Request
        except Exception as exc:
            raise RuntimeError(
                "Google authentication libraries are missing. Install google-auth and google-auth-oauthlib."
            ) from exc

        return Request()

    def _ensure_calendar_log_sink(self) -> None:
        global _CALENDAR_LOG_FILE, _CALENDAR_LOG_SINK_ID
        if _CALENDAR_LOG_SINK_ID is not None and _CALENDAR_LOG_FILE == self.log_file:
            return

        if _CALENDAR_LOG_SINK_ID is not None:
            try:
                logger.remove(_CALENDAR_LOG_SINK_ID)
            except ValueError:
                pass

        self.settings.log_dir.mkdir(parents=True, exist_ok=True)
        _CALENDAR_LOG_SINK_ID = logger.add(
            self.log_file,
            level="DEBUG",
            rotation="1 MB",
            retention="7 days",
            encoding="utf-8",
            backtrace=False,
            diagnose=False,
            filter=lambda record: bool(record["extra"].get("calendar")),
        )
        _CALENDAR_LOG_FILE = self.log_file


def format_calendar_error(error: Exception) -> str:
    error_type = type(error).__name__
    message = str(error).strip() or "No error details provided."
    return f"{error_type}: {_redact_secret_like_text(message)}"


def format_calendar_check_report(report: CalendarCheckReport) -> str:
    lines = [
        "Jarvis Calendar Check",
        "=====================",
        f"Calendar enabled: {_yes_no(report.enabled)}",
        f"Provider: {report.provider}",
        f"Client secret detected: {_yes_no(report.client_secret_detected)}",
        f"Token detected: {_yes_no(report.token_detected)}",
        f"Authenticated: {_yes_no(report.authenticated)}",
        f"Authentication status: {report.authentication_status}",
        f"Diagnostic log: {report.log_file}",
        f"Request attempted: {_yes_no(report.request_attempted)}",
        f"Request success: {_yes_no(report.success)}",
    ]
    if report.setup_guide:
        lines.extend(["", "Setup:", f"  {report.setup_guide}"])

    if report.text:
        lines.extend(["", "Result:", f"  {report.text}"])

    if report.safe_error:
        lines.extend(["", "Error:", f"  {report.safe_error}"])

    return "\n".join(lines)


def format_calendar_auth_report(report: CalendarAuthReport) -> str:
    lines = [
        "Jarvis Calendar Auth",
        "====================",
        f"Calendar enabled: {_yes_no(report.enabled)}",
        f"Client secret detected: {_yes_no(report.client_secret_detected)}",
        f"Token detected: {_yes_no(report.token_detected)}",
        f"Credentials directory created: {_yes_no(report.credentials_dir_created)}",
        f"Authenticated: {_yes_no(report.authenticated)}",
        f"Setup status: {report.setup_status}",
        f"Token path: {report.token_path}",
        f"Diagnostic log: {report.log_file}",
    ]

    if report.text:
        lines.extend(["", "Result:", f"  {report.text}"])

    if report.safe_error:
        lines.extend(["", "Error:", f"  {report.safe_error}"])

    return "\n".join(lines)


def _redact_secret_like_text(text: str) -> str:
    redacted = text
    redacted = redacted.replace("token_calendar.json", "[redacted]")
    redacted = redacted.replace("google_client_secret.json", "[redacted]")
    redacted = re.sub(r"(token=)[^\s&]+", r"\1[redacted]", redacted, flags=re.IGNORECASE)
    redacted = re.sub(r"(secret=)[^\s&]+", r"\1[redacted]", redacted, flags=re.IGNORECASE)
    return redacted


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
