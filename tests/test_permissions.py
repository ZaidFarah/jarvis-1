from __future__ import annotations

from pathlib import Path

from config.settings import AppSettings
from security.permissions import (
    PermissionBroker,
    format_permission_check_report,
    format_permission_decision,
)


def test_permission_low_risk_allowed(tmp_path: Path) -> None:
    broker = PermissionBroker(AppSettings(_env_file=None, log_dir=tmp_path))

    decision = broker.check("weather query", description="Weather lookup for London.")

    assert decision.allowed is True
    assert decision.requires_confirmation is False
    assert decision.risk_level == "low"


def test_permission_medium_risk_requires_confirmation(tmp_path: Path) -> None:
    broker = PermissionBroker(AppSettings(_env_file=None, log_dir=tmp_path))

    decision = broker.check("create reminder", description="Create a reminder.")

    assert decision.allowed is True
    assert decision.requires_confirmation is True
    assert decision.risk_level == "medium"


def test_permission_medium_risk_openai_requires_confirmation(tmp_path: Path) -> None:
    broker = PermissionBroker(AppSettings(_env_file=None, log_dir=tmp_path))

    decision = broker.check("send text to openai", description="Send text to OpenAI.")

    assert decision.allowed is True
    assert decision.requires_confirmation is True
    assert decision.risk_level == "medium"


def test_permission_high_risk_requires_confirmation(tmp_path: Path) -> None:
    broker = PermissionBroker(AppSettings(_env_file=None, log_dir=tmp_path))

    decision = broker.check("send email", description="Send email.")

    assert decision.allowed is True
    assert decision.requires_confirmation is True
    assert decision.risk_level == "high"


def test_permission_blocked_denied(tmp_path: Path) -> None:
    broker = PermissionBroker(AppSettings(_env_file=None, log_dir=tmp_path))

    decision = broker.check("delete files", description="Delete files.")

    assert decision.allowed is False
    assert decision.requires_confirmation is False
    assert decision.risk_level == "blocked"


def test_permission_unknown_action_defaults_safe(tmp_path: Path) -> None:
    broker = PermissionBroker(AppSettings(_env_file=None, log_dir=tmp_path))

    decision = broker.check("mystery action", description="Unknown action.")

    assert decision.allowed is False
    assert decision.requires_confirmation is True
    assert decision.risk_level == "medium"


def test_permission_reports_include_details(tmp_path: Path) -> None:
    broker = PermissionBroker(AppSettings(_env_file=None, log_dir=tmp_path))
    report = broker.run_check()
    text = format_permission_check_report(report)
    decision_text = format_permission_decision(broker.check("delete files"))

    assert "Jarvis Permission Check" in text
    assert "weather query" in text
    assert "Jarvis Permission Decision" in decision_text
    assert "delete files" in decision_text


def test_permission_cli_commands(capsys) -> None:
    from main import main

    check_exit = main(["--permission-check"])
    check_output = capsys.readouterr().out
    blocked_exit = main(["--permission-check-action", "delete files"])
    blocked_output = capsys.readouterr().out

    assert check_exit == 0
    assert "Jarvis Permission Check" in check_output
    assert blocked_exit == 1
    assert "Jarvis Permission Decision" in blocked_output
    assert "delete files" in blocked_output
