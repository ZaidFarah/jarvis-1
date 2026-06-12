from __future__ import annotations

from pathlib import Path

from config.settings import AppSettings
from integrations.calendar_service import CalendarService, format_calendar_check_report, format_calendar_error


class FakeCalendarClient:
    def __init__(self, events: list[dict]) -> None:
        self.events = events
        self.calls: list[tuple[object, object]] = []

    def list_events(self, start, end):
        self.calls.append((start, end))
        return self.events


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


def test_calendar_safe_error_formatting_redacts_secret_like_text() -> None:
    error = RuntimeError("request failed with token=secret123 and secret=mysecret")

    text = format_calendar_error(error)

    assert "RuntimeError:" in text
    assert "secret123" not in text
    assert "mysecret" not in text
    assert "[redacted]" in text
