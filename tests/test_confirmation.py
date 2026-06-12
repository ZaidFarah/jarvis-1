from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtWidgets import QApplication

from config.settings import AppSettings
from security.confirmation import ConfirmationDialog, ConfirmationResult, confirm_action_cli


def test_confirmation_cli_approved(monkeypatch, capsys, tmp_path: Path) -> None:
    from main import main

    result = ConfirmationResult(approved=True, denied=False, timed_out=False, reason="Approved.", log_file=tmp_path / "confirmations.log")
    monkeypatch.setattr("main.confirm_action_cli", lambda *args, **kwargs: result)

    exit_code = main(["--confirm-test", "read file contents"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Jarvis Confirmation Result" in output
    assert "Approved: yes" in output


def test_confirmation_cli_denied(monkeypatch, capsys, tmp_path: Path) -> None:
    from main import main

    result = ConfirmationResult(approved=False, denied=True, timed_out=False, reason="Denied.", log_file=tmp_path / "confirmations.log")
    monkeypatch.setattr("main.confirm_action_cli", lambda *args, **kwargs: result)

    exit_code = main(["--confirm-test", "read file contents"])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Denied: yes" in output


def test_confirmation_timeout_defaults_to_deny(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, log_dir=tmp_path)

    def slow_input(prompt: str) -> str:
        del prompt
        time.sleep(0.1)
        return "yes"

    result = confirm_action_cli(settings, "read file contents", timeout_seconds=0.01, input_func=slow_input, output_func=lambda *_: None)

    assert result.approved is False
    assert result.denied is True
    assert result.timed_out is True


def test_blocked_actions_do_not_ask_confirmation(monkeypatch, capsys) -> None:
    from main import main

    def forbidden(*args, **kwargs):  # pragma: no cover - defensive helper
        raise AssertionError("confirmation should not be requested for blocked actions")

    monkeypatch.setattr("main.confirm_action_cli", forbidden)

    exit_code = main(["--confirm-test", "delete files"])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Jarvis Permission Decision" in output
    assert "Blocked by policy." in output


def test_low_risk_actions_do_not_require_confirmation(tmp_path: Path) -> None:
    from security.permissions import PermissionBroker

    decision = PermissionBroker(AppSettings(_env_file=None, log_dir=tmp_path)).check("weather query")

    assert decision.allowed is True
    assert decision.requires_confirmation is False


def test_confirmation_dialog_construction() -> None:
    app = QApplication.instance() or QApplication([])
    dialog = ConfirmationDialog("read file contents", "medium", "Read file contents from a local file.")

    assert dialog.action_label.text() == "Action: read file contents"
    assert dialog.risk_label.text() == "Risk level: medium"
    assert "Read file contents" in dialog.description_label.text()
    assert len(dialog.button_box.buttons()) == 2
    del app
