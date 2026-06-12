from __future__ import annotations

from pathlib import Path

import pytest

from config.settings import AppSettings
from integrations.gmail_service import (
    GmailAuthReport,
    GmailCheckReport,
    GmailService,
    GmailUnreadEmail,
    GmailUnreadResult,
    format_gmail_auth_report,
    format_gmail_check_report,
    format_gmail_error,
    format_gmail_unread_report,
)


class FakeGmailClient:
    def __init__(self, messages: list[dict[str, object]]) -> None:
        self.messages = messages
        self.calls: list[int] = []

    def list_unread_messages(self, max_results: int) -> list[dict[str, object]]:
        self.calls.append(max_results)
        return self.messages


def test_gmail_disabled_fallback(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, gmail_enabled=False, log_dir=tmp_path)
    service = GmailService(settings)

    result = service.unread_emails()

    assert result.success is False
    assert "Gmail is disabled" in result.text


def test_gmail_missing_credentials_guide(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, gmail_enabled=True, gmail_client_secret_path=tmp_path / "missing.json", gmail_token_path=tmp_path / "token.json", log_dir=tmp_path)
    report = GmailService(settings).run_check()
    text = format_gmail_check_report(report)

    assert report.authenticated is False
    assert report.client_secret_detected is False
    assert "Place your Google OAuth client secret JSON" in text


def test_gmail_missing_token_guide(tmp_path: Path) -> None:
    secret = tmp_path / "google_client_secret.json"
    secret.write_text("{}", encoding="utf-8")
    settings = AppSettings(_env_file=None, gmail_enabled=True, gmail_client_secret_path=secret, gmail_token_path=tmp_path / "missing.json", log_dir=tmp_path)
    report = GmailService(settings).run_check()

    assert report.token_detected is False
    assert "token file is missing" in (report.safe_error or "").lower()


def test_gmail_unread_metadata_formatting(tmp_path: Path) -> None:
    secret = tmp_path / "google_client_secret.json"
    token = tmp_path / "token_gmail.json"
    secret.write_text("{}", encoding="utf-8")
    token.write_text("{}", encoding="utf-8")
    client = FakeGmailClient(
        [
            {
                "id": "msg-1",
                "snippet": "Quick note",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "Alice <alice@example.com>"},
                        {"name": "Subject", "value": "Hello"},
                        {"name": "Date", "value": "Fri, 12 Jun 2026 10:30:00 +0100"},
                    ]
                },
            }
        ]
    )
    settings = AppSettings(_env_file=None, gmail_enabled=True, gmail_client_secret_path=secret, gmail_token_path=token, log_dir=tmp_path)
    service = GmailService(settings, client_factory=lambda _: client)

    result = service.unread_emails()
    text = format_gmail_unread_report(result)

    assert result.success is True
    assert client.calls == [5]
    assert "Alice <alice@example.com>" in text
    assert "Hello" in text
    assert "Quick note" in text
    assert "Fri, 12 Jun 2026" in text


def test_gmail_safe_error_formatting_redacts_secret_like_text() -> None:
    error = RuntimeError("request failed with token=secret123 and secret=mysecret")

    text = format_gmail_error(error)

    assert "secret123" not in text
    assert "mysecret" not in text
    assert "[redacted]" in text


def test_gmail_auth_report_and_check_report_formatting(tmp_path: Path) -> None:
    auth_report = GmailAuthReport(
        enabled=True,
        client_secret_detected=True,
        token_detected=True,
        token_path=tmp_path / "credentials" / "token_gmail.json",
        credentials_dir_created=True,
        authenticated=True,
        setup_status="authenticated",
        text="Google Gmail authentication completed successfully.",
        safe_error=None,
        log_file=tmp_path / "gmail.log",
    )
    check_report = GmailCheckReport(
        enabled=True,
        provider="google_gmail",
        client_secret_detected=True,
        token_detected=True,
        authenticated=True,
        authentication_status="authenticated",
        setup_guide=None,
        request_attempted=False,
        success=True,
        text="Gmail is ready.",
        safe_error=None,
        log_file=tmp_path / "gmail.log",
    )

    assert "Jarvis Gmail Auth" in format_gmail_auth_report(auth_report)
    assert "Jarvis Gmail Check" in format_gmail_check_report(check_report)


def test_gmail_cli_commands(monkeypatch: pytest.MonkeyPatch, capsys, tmp_path: Path) -> None:
    from main import main

    class DummyGmailService:
        def __init__(self, settings: AppSettings, client_factory=None) -> None:
            del settings, client_factory

        def run_check(self) -> GmailCheckReport:
            return GmailCheckReport(
                enabled=True,
                provider="google_gmail",
                client_secret_detected=True,
                token_detected=True,
                authenticated=True,
                authentication_status="authenticated",
                setup_guide=None,
                request_attempted=False,
                success=True,
                text="Gmail is ready.",
                safe_error=None,
                log_file=tmp_path / "gmail.log",
            )

        def auth_gmail(self) -> GmailAuthReport:
            return GmailAuthReport(
                enabled=True,
                client_secret_detected=True,
                token_detected=True,
                token_path=tmp_path / "credentials" / "token_gmail.json",
                credentials_dir_created=True,
                authenticated=True,
                setup_status="authenticated",
                text="Google Gmail authentication completed successfully.",
                safe_error=None,
                log_file=tmp_path / "gmail.log",
            )

    class DummyAssistant:
        def handle_command(self, command: str):
            return type("Response", (), {"accepted": True, "text": f"Handled: {command}", "source": "gmail", "error": None})()

    monkeypatch.setattr("main.GmailService", DummyGmailService)
    monkeypatch.setattr("main._build_cli_assistant", lambda settings: DummyAssistant())

    check_exit = main(["--gmail-check"])
    check_output = capsys.readouterr().out
    auth_exit = main(["--gmail-auth"])
    auth_output = capsys.readouterr().out
    unread_exit = main(["--gmail-unread"])
    unread_output = capsys.readouterr().out

    assert check_exit == 0
    assert "Jarvis Gmail Check" in check_output
    assert auth_exit == 0
    assert "Jarvis Gmail Auth" in auth_output
    assert unread_exit == 0
    assert "Handled: read my unread emails" in unread_output
