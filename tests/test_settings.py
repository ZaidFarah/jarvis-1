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


def test_openai_settings_defaults_are_safe() -> None:
    settings = AppSettings(_env_file=None)

    assert settings.openai_enabled is False
    assert settings.has_openai_api_key is False
    assert settings.openai_model == "gpt-4o-mini"
    assert settings.system_prompt == "You are Jarvis, a helpful personal desktop AI assistant."
    assert settings.conversation_history_enabled is True
    assert settings.conversation_history_max_messages == 10
    assert settings.memory_enabled is True
    assert settings.memory_database_path.name == "jarvis_memory.db"


def test_conversation_history_settings_read_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONVERSATION_HISTORY_ENABLED", "false")
    monkeypatch.setenv("CONVERSATION_HISTORY_MAX_MESSAGES", "4")

    settings = AppSettings(_env_file=None)

    assert settings.conversation_history_enabled is False
    assert settings.conversation_history_max_messages == 4


def test_memory_settings_read_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEMORY_ENABLED", "false")
    monkeypatch.setenv("MEMORY_DATABASE_PATH", "data/custom_memory.db")

    settings = AppSettings(_env_file=None)

    assert settings.memory_enabled is False
    assert settings.memory_database_path.name == "custom_memory.db"


def test_weather_settings_defaults_are_safe() -> None:
    settings = AppSettings(_env_file=None)

    assert settings.weather_enabled is False
    assert settings.weather_provider == "openweathermap"
    assert settings.has_weather_api_key is False
    assert settings.weather_default_city == "Nottingham"
    assert settings.weather_units == "metric"


def test_weather_settings_read_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEATHER_ENABLED", "true")
    monkeypatch.setenv("WEATHER_PROVIDER", "openweathermap")
    monkeypatch.setenv("WEATHER_API_KEY", "  key-123  ")
    monkeypatch.setenv("WEATHER_DEFAULT_CITY", "  London  ")
    monkeypatch.setenv("WEATHER_UNITS", "imperial")

    settings = AppSettings(_env_file=None)

    assert settings.weather_enabled is True
    assert settings.weather_provider == "openweathermap"
    assert settings.weather_api_key == "key-123"
    assert settings.has_weather_api_key is True
    assert settings.weather_default_city == "London"
    assert settings.weather_units == "imperial"


def test_reminder_settings_defaults_are_safe() -> None:
    settings = AppSettings(_env_file=None)

    assert settings.reminders_enabled is True
    assert settings.reminders_check_enabled is True
    assert settings.reminders_check_interval_seconds == 60
    assert settings.reminders_speak_due is False
    assert settings.reminders_watch_enabled is False
    assert settings.reminders_watch_speak is False
    assert settings.reminders_database_path.name == "jarvis_reminders.db"


def test_notification_settings_defaults_are_safe() -> None:
    settings = AppSettings(_env_file=None)

    assert settings.notifications_enabled is False
    assert settings.notification_provider == "windows_toast"
    assert settings.reminders_toast_enabled is False


def test_notification_settings_read_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTIFICATIONS_ENABLED", "true")
    monkeypatch.setenv("NOTIFICATION_PROVIDER", "windows_toast")
    monkeypatch.setenv("REMINDERS_TOAST_ENABLED", "true")

    settings = AppSettings(_env_file=None)

    assert settings.notifications_enabled is True
    assert settings.notification_provider == "windows_toast"
    assert settings.reminders_toast_enabled is True


def test_reminder_settings_read_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REMINDERS_ENABLED", "false")
    monkeypatch.setenv("REMINDERS_CHECK_ENABLED", "false")
    monkeypatch.setenv("REMINDERS_CHECK_INTERVAL_SECONDS", "120")
    monkeypatch.setenv("REMINDERS_SPEAK_DUE", "true")
    monkeypatch.setenv("REMINDERS_WATCH_ENABLED", "true")
    monkeypatch.setenv("REMINDERS_WATCH_SPEAK", "true")
    monkeypatch.setenv("REMINDERS_DATABASE_PATH", "data/custom_reminders.db")

    settings = AppSettings(_env_file=None)

    assert settings.reminders_enabled is False
    assert settings.reminders_check_enabled is False
    assert settings.reminders_check_interval_seconds == 120
    assert settings.reminders_speak_due is True
    assert settings.reminders_watch_enabled is True
    assert settings.reminders_watch_speak is True
    assert settings.reminders_database_path.name == "custom_reminders.db"


def test_openai_settings_read_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "  sk-test  ")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    monkeypatch.setenv("SYSTEM_PROMPT", "  You are test Jarvis.  ")

    settings = AppSettings(_env_file=None)

    assert settings.openai_enabled is True
    assert settings.openai_api_key == "sk-test"
    assert settings.has_openai_api_key is True
    assert settings.openai_model == "gpt-test"
    assert settings.system_prompt == "You are test Jarvis."
