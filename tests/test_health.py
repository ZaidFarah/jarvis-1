from __future__ import annotations

from pathlib import Path

from config.settings import AppSettings
from diagnostics.health import HealthService, format_health_check_report


def test_health_check_contains_all_required_sections() -> None:
    settings = AppSettings(_env_file=None)
    report = HealthService(settings).run_check()
    text = format_health_check_report(report)

    for section in [
        "System",
        "OpenAI",
        "Voice",
        "Memory",
        "Reminders",
        "Weather",
        "Notifications",
        "Launchers",
        "Files",
        "Calendar",
        "Gmail",
        "Vision",
        "Agent",
    ]:
        assert section in text


def test_health_check_does_not_leak_api_keys_or_tokens() -> None:
    settings = AppSettings(
        _env_file=None,
        openai_enabled=True,
        openai_api_key="sk-secret-value",
        gmail_enabled=True,
        calendar_enabled=True,
    )
    report = HealthService(settings).run_check()
    text = format_health_check_report(report)

    assert "sk-secret-value" not in text
    assert "token-secret-value" not in text
    assert "API key detected: yes" in text


def test_health_check_reports_disabled_services() -> None:
    settings = AppSettings(_env_file=None)
    report = HealthService(settings).run_check()

    assert report.openai_enabled is False
    assert report.weather_enabled is False
    assert report.calendar_enabled is False
    assert report.gmail_enabled is False
    assert report.vision_enabled is False


def test_health_check_uses_safe_paths() -> None:
    settings = AppSettings(_env_file=None)
    report = HealthService(settings).run_check()

    assert isinstance(report.project_path, Path)
    assert report.log_file.name == "health.log"
