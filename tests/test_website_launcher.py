from __future__ import annotations

from pathlib import Path

import pytest

from assistant.core import AssistantCore
from config.settings import AppSettings
from tools.website_launcher import (
    WebsiteLauncher,
    WebsiteLauncherCheckReport,
    WebsiteOpenResult,
    WebsiteResolutionResult,
    format_website_launcher_check_report,
    format_website_open_report,
    format_website_resolution_report,
    format_website_launcher_error,
)


class FakeOpenAIService:
    def chat(self, *args, **kwargs):  # pragma: no cover - defensive helper
        del args, kwargs
        raise AssertionError("OpenAI should not be called")


def test_website_launcher_allowed_site_lookup(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, log_dir=tmp_path)
    launcher = WebsiteLauncher(settings, browser_open=lambda *args, **kwargs: True)

    assert launcher.allowed_sites["google"] == "https://www.google.com"
    assert launcher.allowed_sites["outlook"] == "https://outlook.office.com"


def test_website_launcher_unconfigured_site_rejected(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, log_dir=tmp_path)
    launcher = WebsiteLauncher(settings, browser_open=lambda *args, **kwargs: True)

    result = launcher.resolve_site("blackboard")

    assert result.allowed is True
    assert result.configured is False
    assert result.resolved_url is None
    assert "not configured" in (result.safe_error or "")


def test_website_launcher_unknown_site_rejected(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, log_dir=tmp_path)
    launcher = WebsiteLauncher(settings, browser_open=lambda *args, **kwargs: True)

    result = launcher.resolve_site("weather")

    assert result.allowed is False
    assert result.resolved_url is None
    assert "not allowed" in (result.safe_error or "")


def test_website_launcher_arbitrary_url_rejected(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, log_dir=tmp_path)
    launcher = WebsiteLauncher(settings, browser_open=lambda *args, **kwargs: True)

    result = launcher.open_site("https://evil.example")

    assert result.opened is False
    assert result.request_attempted is False
    assert "whitelisted site name" in (result.safe_error or "")


def test_website_launcher_disabled_fallback(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, website_launcher_enabled=False, log_dir=tmp_path)
    launcher = WebsiteLauncher(settings, browser_open=lambda *args, **kwargs: True)

    result = launcher.open_site("google")

    assert result.opened is False
    assert result.enabled is False
    assert result.fallback_reason == "Website launcher is disabled."


def test_website_launcher_open_site_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_open(*args, **kwargs):
        captured.append((args, kwargs))
        return True

    settings = AppSettings(_env_file=None, log_dir=tmp_path)
    launcher = WebsiteLauncher(settings, browser_open=fake_open)

    result = launcher.open_site("google")

    assert result.opened is True
    assert captured
    assert captured[0][0][0] == "https://www.google.com"
    assert captured[0][1]["new"] == 0
    assert captured[0][1]["autoraise"] is True


def test_website_launcher_check_formats_safe_error() -> None:
    error = format_website_launcher_error(RuntimeError("failed with OPENAI_API_KEY=sk-test-secret"))

    assert "sk-test-secret" not in error
    assert "OPENAI_API_KEY" not in error


def test_website_launcher_resolution_report_includes_details(tmp_path: Path) -> None:
    result = WebsiteResolutionResult(
        enabled=True,
        site_name="google",
        configured_url="https://www.google.com",
        resolved_url="https://www.google.com",
        allowed=True,
        configured=True,
        log_file=tmp_path / "website_launcher.log",
    )

    text = format_website_resolution_report(result)

    assert "Jarvis Website Resolution" in text
    assert "Configured URL" in text
    assert "Resolved URL" in text


def test_website_launcher_open_report_includes_resolved_url(tmp_path: Path) -> None:
    result = WebsiteOpenResult(
        enabled=True,
        site_name="google",
        allowed=True,
        configured=True,
        request_attempted=True,
        opened=True,
        configured_url="https://www.google.com",
        resolved_url="https://www.google.com",
        log_file=tmp_path / "website_launcher.log",
    )

    text = format_website_open_report(result)

    assert "Jarvis Website Open" in text
    assert "Resolved URL" in text


def test_assistant_core_routes_website_commands(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, log_dir=tmp_path)
    assistant = AssistantCore(settings=settings, openai_service=FakeOpenAIService())
    assistant.website_launcher = WebsiteLauncher(settings, browser_open=lambda *args, **kwargs: True)

    response = assistant.handle_command("open google")

    assert response.source == "website"
    assert response.accepted is True
    assert "Opened google" in response.text


def test_assistant_core_rejects_raw_website_urls(tmp_path: Path) -> None:
    assistant = AssistantCore(settings=AppSettings(_env_file=None, log_dir=tmp_path), openai_service=FakeOpenAIService())

    response = assistant.handle_command("open https://evil.example")

    assert response.source == "local"
    assert response.accepted is False
    assert "whitelisted site name" in response.text


def test_assistant_core_disabled_website_fallback(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, website_launcher_enabled=False, log_dir=tmp_path)
    assistant = AssistantCore(settings=settings, openai_service=FakeOpenAIService())

    response = assistant.handle_command("open google")

    assert response.source == "local"
    assert response.text == "Website launcher is disabled."


def test_website_launcher_cli_commands(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    from main import main

    class DummyLauncher:
        def __init__(self, settings: AppSettings) -> None:
            del settings

        def run_check(self) -> WebsiteLauncherCheckReport:
            return WebsiteLauncherCheckReport(
                enabled=True,
                allowed_sites={"google": "https://www.google.com"},
                log_file=Path("logs/website_launcher.log"),
            )

        def open_site(self, site_name: str) -> WebsiteOpenResult:
            return WebsiteOpenResult(
                enabled=True,
                site_name=site_name,
                allowed=True,
                configured=True,
                request_attempted=True,
                opened=True,
                configured_url="https://www.google.com",
                resolved_url="https://www.google.com",
                log_file=Path("logs/website_launcher.log"),
            )

    monkeypatch.setattr("main.WebsiteLauncher", DummyLauncher)

    check_exit = main(["--website-check"])
    check_output = capsys.readouterr().out
    open_exit = main(["--open-site", "google"])
    open_output = capsys.readouterr().out

    assert check_exit == 0
    assert "Jarvis Website Check" in check_output
    assert open_exit == 0
    assert "Jarvis Website Open" in open_output
