from __future__ import annotations

from pathlib import Path

import pytest

from config.settings import AppSettings
from integrations.calendar_service import CalendarService, format_calendar_auth_report, format_calendar_check_report, format_calendar_error


class FakeCalendarClient:
    def __init__(self, events: list[dict]) -> None:
        self.events = events
        self.calls: list[tuple[object, object]] = []
        self.create_calls: list[dict[str, object]] = []

    def list_events(self, start, end):
        self.calls.append((start, end))
        return self.events

    def create_event(self, title, start, end, location=None, description=None):
        self.create_calls.append(
            {
                "title": title,
                "start": start,
                "end": end,
                "location": location,
                "description": description,
            }
        )
        return {"id": "event-123", "htmlLink": "https://calendar.example/event-123", "summary": title}


def test_calendar_disabled_does_not_attempt_request(tmp_path: Path) -> None:
    called = False

    def factory(settings: AppSettings):
        nonlocal called
        del settings
        called = True
        raise AssertionError("client should not be created")

    settings = AppSettings(_env_file=None, calendar_enabled=False, log_dir=tmp_path)
    service = CalendarService(settings, client_factory=factory)

    result = service.current_events("today")

    assert called is False
    assert result.success is False
    assert result.request_attempted is False
    assert "Calendar is disabled" in result.text


def test_calendar_missing_credentials(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, calendar_enabled=True, calendar_client_secret_path=tmp_path / "missing.json", calendar_token_path=tmp_path / "token.json", log_dir=tmp_path)
    service = CalendarService(settings)

    result = service.current_events("today")

    assert result.request_attempted is False
    assert "client secret file is missing" in (result.safe_error or "").lower()


def test_calendar_missing_token(tmp_path: Path) -> None:
    secret = tmp_path / "google_client_secret.json"
    secret.write_text("{}", encoding="utf-8")
    settings = AppSettings(_env_file=None, calendar_enabled=True, calendar_client_secret_path=secret, calendar_token_path=tmp_path / "missing.json", log_dir=tmp_path)
    service = CalendarService(settings)

    result = service.current_events("today")

    assert result.request_attempted is False
    assert "token" in (result.safe_error or "").lower()


def test_calendar_provider_configuration_and_success(tmp_path: Path) -> None:
    secret = tmp_path / "google_client_secret.json"
    token = tmp_path / "token_calendar.json"
    secret.write_text("{}", encoding="utf-8")
    token.write_text("{}", encoding="utf-8")
    client = FakeCalendarClient([
        {"summary": "Standup", "start": {"dateTime": "2026-06-12T09:00:00"}, "end": {"dateTime": "2026-06-12T09:15:00"}},
    ])

    settings = AppSettings(_env_file=None, calendar_enabled=True, calendar_client_secret_path=secret, calendar_token_path=token, log_dir=tmp_path)
    report = CalendarService(settings, client_factory=lambda _: client).run_check()
    text = format_calendar_check_report(report)

    assert report.enabled is True
    assert report.client_secret_detected is True
    assert report.token_detected is True
    assert report.request_attempted is True
    assert report.success is True
    assert "Authenticated: yes" in text
    assert "google_client_secret.json" not in text
    assert "token_calendar.json" not in text


def test_calendar_auth_guides_when_client_secret_missing(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, calendar_enabled=True, calendar_client_secret_path=tmp_path / "missing.json", calendar_token_path=tmp_path / "token.json", log_dir=tmp_path)
    report = CalendarService(settings).auth_calendar()
    text = format_calendar_auth_report(report)

    assert report.authenticated is False
    assert report.client_secret_detected is False
    assert "Place your Google OAuth client secret JSON" in text
    assert "missing.json" in text


def test_calendar_auth_creates_token_path(tmp_path: Path) -> None:
    secret = tmp_path / "google_client_secret.json"
    secret.write_text("{}", encoding="utf-8")
    token = tmp_path / "credentials" / "token_calendar.json"

    class FakeFlow:
        def run_local_server(self, port: int = 0):
            del port
            return type("Creds", (), {"to_json": lambda self: "{\"token\":\"abc\"}"})()

        def run_console(self):
            raise AssertionError("run_console should not be called")

    service = CalendarService(
        AppSettings(_env_file=None, calendar_enabled=True, calendar_client_secret_path=secret, calendar_token_path=token, log_dir=tmp_path),
        client_factory=lambda _: None,
    )
    service._build_flow = lambda: FakeFlow()  # type: ignore[method-assign]
    service._load_credentials = lambda scopes=None: None  # type: ignore[method-assign]
    report = service.auth_calendar()

    assert report.credentials_dir_created is True
    assert token.parent.exists()


def test_calendar_readonly_scope_config() -> None:
    settings = AppSettings(_env_file=None)

    assert settings.calendar_scopes_list == ["https://www.googleapis.com/auth/calendar.readonly"]
    assert settings.calendar_write_scopes_list == ["https://www.googleapis.com/auth/calendar.events"]


def test_calendar_safe_error_formatting_redacts_secret_like_text() -> None:
    error = RuntimeError("request failed with token=secret123 and secret=mysecret")

    text = format_calendar_error(error)

    assert "RuntimeError:" in text
    assert "secret123" not in text
    assert "mysecret" not in text
    assert "[redacted]" in text


def test_calendar_cli_commands(monkeypatch: pytest.MonkeyPatch, capsys, tmp_path: Path) -> None:
    from main import main
    from integrations.calendar_service import CalendarAuthReport, CalendarCheckReport, CalendarQueryResult

    class DummyCalendarService:
        def __init__(self, settings: AppSettings, client_factory=None) -> None:
            del settings, client_factory

        def run_check(self) -> CalendarCheckReport:
            return CalendarCheckReport(
                enabled=True,
                provider="google_calendar",
                client_secret_detected=True,
                token_detected=True,
                authenticated=True,
                authentication_status="authenticated",
                setup_guide=None,
                day_label="today",
                request_attempted=False,
                success=True,
                text="Calendar is ready.",
                safe_error=None,
                log_file=tmp_path / "calendar.log",
            )

        def auth_calendar(self) -> CalendarAuthReport:
            return CalendarAuthReport(
                enabled=True,
                client_secret_detected=True,
                token_detected=True,
                token_path=tmp_path / "credentials" / "token_calendar.json",
                credentials_dir_created=True,
                authenticated=True,
                setup_status="authenticated",
                text="Google Calendar authentication completed successfully.",
                safe_error=None,
                log_file=tmp_path / "calendar.log",
            )

        def create_event(self, title: str, start_text: str, duration_minutes: int, location=None, description=None):
            return type(
                "CreateResult",
                (),
                {
                    "success": True,
                    "text": f"Created calendar event: {title}",
                    "safe_error": None,
                },
            )()

    class DummyAssistant:
        def handle_command(self, command: str) -> CalendarQueryResult | object:
            return type("Response", (), {"accepted": True, "text": f"Handled: {command}"})()

    monkeypatch.setattr("main.CalendarService", DummyCalendarService)
    monkeypatch.setattr("main._build_cli_assistant", lambda settings: DummyAssistant())

    auth_exit = main(["--calendar-auth"])
    auth_output = capsys.readouterr().out
    today_exit = main(["--calendar-today"])
    today_output = capsys.readouterr().out
    tomorrow_exit = main(["--calendar-tomorrow"])
    tomorrow_output = capsys.readouterr().out
    create_exit = main(["--calendar-create", "Meeting", "2026-06-12 18:30", "30"])
    create_output = capsys.readouterr().out

    assert auth_exit == 0
    assert "Jarvis Calendar Auth" in auth_output
    assert today_exit == 0
    assert "Handled: what is on my calendar today" in today_output
    assert tomorrow_exit == 0
    assert "Handled: what is on my calendar tomorrow" in tomorrow_output
    assert create_exit == 0
    assert "Handled:" in create_output


def test_calendar_create_disabled_fallback(tmp_path: Path) -> None:
    secret = tmp_path / "google_client_secret.json"
    token = tmp_path / "token_calendar.json"
    secret.write_text("{}", encoding="utf-8")
    token.write_text("{}", encoding="utf-8")
    settings = AppSettings(
        _env_file=None,
        calendar_enabled=True,
        calendar_create_enabled=False,
        calendar_client_secret_path=secret,
        calendar_token_path=token,
        log_dir=tmp_path,
    )
    service = CalendarService(settings)

    result = service.create_event("Meeting", "2026-06-12 18:30", 30)

    assert result.success is False
    assert "Calendar creation is disabled" in result.text


def test_calendar_create_invalid_datetime_rejected(tmp_path: Path) -> None:
    secret = tmp_path / "google_client_secret.json"
    token = tmp_path / "token_calendar.json"
    secret.write_text("{}", encoding="utf-8")
    token.write_text("{}", encoding="utf-8")
    settings = AppSettings(
        _env_file=None,
        calendar_enabled=True,
        calendar_create_enabled=True,
        calendar_client_secret_path=secret,
        calendar_token_path=token,
        log_dir=tmp_path,
    )
    service = CalendarService(settings, client_factory=lambda _: FakeCalendarClient([]))
    service._load_credentials = lambda scopes=None: type("Creds", (), {"has_scopes": lambda self, scopes: True})()  # type: ignore[method-assign]

    result = service.create_event("Meeting", "not-a-datetime", 30)

    assert result.success is False
    assert "YYYY-MM-DD HH:MM" in result.text


def test_calendar_create_invalid_duration_rejected(tmp_path: Path) -> None:
    secret = tmp_path / "google_client_secret.json"
    token = tmp_path / "token_calendar.json"
    secret.write_text("{}", encoding="utf-8")
    token.write_text("{}", encoding="utf-8")
    settings = AppSettings(
        _env_file=None,
        calendar_enabled=True,
        calendar_create_enabled=True,
        calendar_client_secret_path=secret,
        calendar_token_path=token,
        log_dir=tmp_path,
    )
    service = CalendarService(settings, client_factory=lambda _: FakeCalendarClient([]))
    service._load_credentials = lambda scopes=None: type("Creds", (), {"has_scopes": lambda self, scopes: True})()  # type: ignore[method-assign]

    result = service.create_event("Meeting", "2026-06-12 18:30", 0)

    assert result.success is False
    assert "positive number of minutes" in result.text


def test_calendar_create_missing_write_scope_message(tmp_path: Path) -> None:
    secret = tmp_path / "google_client_secret.json"
    token = tmp_path / "token_calendar.json"
    secret.write_text("{}", encoding="utf-8")
    token.write_text("{}", encoding="utf-8")
    settings = AppSettings(
        _env_file=None,
        calendar_enabled=True,
        calendar_create_enabled=True,
        calendar_client_secret_path=secret,
        calendar_token_path=token,
        log_dir=tmp_path,
    )
    service = CalendarService(settings, client_factory=lambda _: FakeCalendarClient([]))

    class Creds:
        def has_scopes(self, scopes):
            del scopes
            return False

    service._load_credentials = lambda scopes=None: Creds()  # type: ignore[method-assign]

    result = service.create_event("Meeting", "2026-06-12 18:30", 30)

    assert result.success is False
    assert result.text == "Calendar write scope is required. Re-run calendar auth after enabling create."


def test_calendar_create_success_with_mocked_client(tmp_path: Path) -> None:
    secret = tmp_path / "google_client_secret.json"
    token = tmp_path / "token_calendar.json"
    secret.write_text("{}", encoding="utf-8")
    token.write_text("{}", encoding="utf-8")
    client = FakeCalendarClient([])
    settings = AppSettings(
        _env_file=None,
        calendar_enabled=True,
        calendar_create_enabled=True,
        calendar_client_secret_path=secret,
        calendar_token_path=token,
        log_dir=tmp_path,
    )
    service = CalendarService(settings, client_factory=lambda _: client)

    class Creds:
        def has_scopes(self, scopes):
            del scopes
            return True

    service._load_credentials = lambda scopes=None: Creds()  # type: ignore[method-assign]

    result = service.create_event("Meeting", "2026-06-12 18:30", 30, location="Room 1")

    assert result.success is True
    assert "Created calendar event: Meeting" in result.text
    assert client.create_calls[0]["title"] == "Meeting"
    assert client.create_calls[0]["location"] == "Room 1"
