from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from config.settings import AppSettings
from diagnostics.settings_check import format_settings_check_report, run_settings_check
from gui.settings_window import SettingsWindow
from jarvis_runtime.settings_editor import SAFE_SETTING_SPECS, save_safe_settings


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_settings_window_constructs_with_safe_fields_only() -> None:
    app = _app()
    window = SettingsWindow(AppSettings(_env_file=None))

    assert window.windowTitle() == "Jarvis Settings"
    assert set(window.field_widgets) == {spec.field_name for spec in SAFE_SETTING_SPECS}
    assert "openai_api_key" not in window.field_widgets
    assert "gmail_token_path" not in window.field_widgets
    assert "calendar_client_secret_path" not in window.field_widgets

    window.close()
    app.processEvents()


def test_safe_setting_update_preserves_unrelated_keys(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "# header comment",
                "UNRELATED_KEY=keep-me",
                "WAKE_PHRASE=old phrase",
                "OPENAI_API_KEY=sk-secret",
                "",
            ]
        ),
        encoding="utf-8",
    )

    settings = AppSettings(_env_file=None, runtime_mode="source")
    result = save_safe_settings(
        settings,
        {
            "wake_phrase": "hello jarvis",
            "notifications_enabled": True,
        },
        env_path=env_path,
    )

    text = env_path.read_text(encoding="utf-8")
    assert "# header comment" in text
    assert "UNRELATED_KEY=keep-me" in text
    assert "WAKE_PHRASE=" in text
    assert "hello jarvis" in text
    assert "NOTIFICATIONS_ENABLED=true" in text
    assert "OPENAI_API_KEY=sk-secret" in text
    assert result.created_file is False
    assert result.preserved_unrelated_keys is True


def test_settings_check_redacts_secrets(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    monkeypatch.setenv("GMAIL_TOKEN_PATH", "credentials/token_gmail.json")
    monkeypatch.setenv("CALENDAR_CLIENT_SECRET_PATH", "credentials/calendar_secret.json")

    report = run_settings_check(AppSettings(_env_file=None))
    text = format_settings_check_report(report)

    assert "sk-secret" not in text
    assert "token_gmail.json" not in text
    assert "calendar_secret.json" not in text
    assert "[redacted]" in text
    assert "Wake phrase" in text
    assert "TTS provider" in text
