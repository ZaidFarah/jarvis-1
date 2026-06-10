from __future__ import annotations

import pytest

from config.settings import AppSettings


def test_settings_defaults_are_safe() -> None:
    settings = AppSettings(_env_file=None)

    assert settings.app_name == "Jarvis"
    assert settings.environment == "development"
    assert settings.log_level == "INFO"
    assert settings.always_on_top is True
    assert settings.minimize_to_tray is True


def test_settings_read_jarvis_prefixed_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JARVIS_APP_NAME", "Jarvis Test")
    monkeypatch.setenv("JARVIS_LOG_LEVEL", "debug")

    settings = AppSettings(_env_file=None)

    assert settings.app_name == "Jarvis Test"
    assert settings.log_level == "DEBUG"


def test_invalid_log_level_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JARVIS_LOG_LEVEL", "nope")

    with pytest.raises(ValueError):
        AppSettings(_env_file=None)
