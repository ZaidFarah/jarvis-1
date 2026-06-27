from __future__ import annotations

import pytest

from config.settings import AppSettings


def test_settings_defaults_are_safe() -> None:
    settings = AppSettings(_env_file=None)

    assert settings.app_name == "Jarvis"
    assert settings.app_version == "0.1.0"
    assert settings.startup_enabled is False
    assert settings.startup_app_name == "Jarvis"
    assert settings.signing_enabled is False
    assert settings.signing_cert_path == ""
    assert settings.signing_timestamp_url == "http://timestamp.digicert.com"
    assert settings.signing_description == "Jarvis Desktop AI Assistant"
    assert settings.backup_enabled is True
    assert settings.backup_include_env is False
    assert settings.backup_include_tokens is False
    assert settings.backup_include_client_secret is False
    assert settings.runtime_mode == "source"
    assert settings.environment == "development"
    assert settings.log_level == "INFO"
    assert settings.always_on_top is True
    assert settings.minimize_to_tray is True


def test_settings_read_jarvis_prefixed_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JARVIS_APP_NAME", "Jarvis Test")
    monkeypatch.setenv("JARVIS_LOG_LEVEL", "debug")
    monkeypatch.setenv("RUNTIME_MODE", "packaged")

    settings = AppSettings(_env_file=None)

    assert settings.app_name == "Jarvis Test"
    assert settings.log_level == "DEBUG"
    assert settings.runtime_mode == "packaged"


def test_runtime_mode_read_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUNTIME_MODE", "packaged")

    settings = AppSettings(_env_file=None)

    assert settings.runtime_mode == "packaged"


def test_app_version_read_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_VERSION", "1.2.3")

    settings = AppSettings(_env_file=None)

    assert settings.app_version == "1.2.3"


def test_invalid_app_version_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_VERSION", "v1")

    with pytest.raises(ValueError):
        AppSettings(_env_file=None)


def test_startup_settings_read_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STARTUP_ENABLED", "true")
    monkeypatch.setenv("STARTUP_APP_NAME", "Jarvis Dev")

    settings = AppSettings(_env_file=None)

    assert settings.startup_enabled is True
    assert settings.startup_app_name == "Jarvis Dev"


def test_signing_settings_read_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIGNING_ENABLED", "true")
    monkeypatch.setenv("SIGNING_CERT_PATH", "  C:\\certs\\jarvis.pfx  ")
    monkeypatch.setenv("SIGNING_TIMESTAMP_URL", "  http://timestamp.example.com  ")
    monkeypatch.setenv("SIGNING_DESCRIPTION", "  Jarvis Signed Build  ")

    settings = AppSettings(_env_file=None)

    assert settings.signing_enabled is True
    assert settings.signing_cert_path == "C:\\certs\\jarvis.pfx"
    assert settings.signing_timestamp_url == "http://timestamp.example.com"
    assert settings.signing_description == "Jarvis Signed Build"


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
    assert settings.memory_confirm_names is True
    assert settings.memory_database_path.name == "jarvis_memory.db"
    assert settings.developer_mode_enabled is True
    assert settings.developer_command_timeout_seconds == 120


def test_conversation_history_settings_read_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONVERSATION_HISTORY_ENABLED", "false")
    monkeypatch.setenv("CONVERSATION_HISTORY_MAX_MESSAGES", "4")

    settings = AppSettings(_env_file=None)

    assert settings.conversation_history_enabled is False
    assert settings.conversation_history_max_messages == 4


def test_agent_settings_defaults_are_safe() -> None:
    settings = AppSettings(_env_file=None)

    assert settings.agent_enabled is False
    assert settings.agent_experimental is True


def test_agent_settings_read_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_ENABLED", "true")
    monkeypatch.setenv("AGENT_EXPERIMENTAL", "false")

    settings = AppSettings(_env_file=None)

    assert settings.agent_enabled is True
    assert settings.agent_experimental is False


def test_memory_settings_read_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEMORY_ENABLED", "false")
    monkeypatch.setenv("MEMORY_CONFIRM_NAMES", "false")
    monkeypatch.setenv("MEMORY_DB_PATH", "data/custom_memory.db")

    settings = AppSettings(_env_file=None)

    assert settings.memory_enabled is False
    assert settings.memory_confirm_names is False
    assert settings.memory_database_path.name == "custom_memory.db"


def test_developer_settings_read_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVELOPER_MODE_ENABLED", "false")
    monkeypatch.setenv("DEVELOPER_COMMAND_TIMEOUT_SECONDS", "45")

    settings = AppSettings(_env_file=None)

    assert settings.developer_mode_enabled is False
    assert settings.developer_command_timeout_seconds == 45


def test_memory_settings_keep_legacy_database_path_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEMORY_DATABASE_PATH", "data/legacy_memory.db")

    settings = AppSettings(_env_file=None)

    assert settings.memory_database_path.name == "legacy_memory.db"


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


def test_vision_settings_defaults_are_safe() -> None:
    settings = AppSettings(_env_file=None)

    assert settings.vision_enabled is False
    assert settings.screen_vision_enabled is False
    assert settings.screenshot_enabled is False
    assert settings.ocr_enabled is False
    assert settings.screen_vision_analyze_default is True
    assert settings.screen_capture_monitor == "primary"
    assert settings.screen_capture_all_monitors is False
    assert settings.openai_vision_enabled is False
    assert settings.openai_vision_model == "gpt-4o-mini"
    assert settings.openai_vision_max_image_bytes == 5000000
    assert settings.screenshot_save_dir.name == "screenshots"
    assert settings.screenshot_save_dir.as_posix().endswith("data/screenshots")
    assert settings.ocr_provider == "tesseract"
    assert settings.ocr_max_output_chars == 4000


def test_vision_settings_read_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VISION_ENABLED", "true")
    monkeypatch.setenv("SCREENSHOT_ENABLED", "true")
    monkeypatch.setenv("SCREEN_VISION_ENABLED", "true")
    monkeypatch.setenv("SCREEN_VISION_ANALYZE_DEFAULT", "true")
    monkeypatch.setenv("SCREEN_CAPTURE_MONITOR", "2")
    monkeypatch.setenv("SCREEN_CAPTURE_ALL_MONITORS", "true")
    monkeypatch.setenv("OCR_ENABLED", "true")
    monkeypatch.setenv("OPENAI_VISION_ENABLED", "true")
    monkeypatch.setenv("OPENAI_VISION_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("OPENAI_VISION_MAX_IMAGE_BYTES", "123456")
    monkeypatch.setenv("SCREENSHOT_DIR", "data/custom-screenshots")
    monkeypatch.setenv("OCR_PROVIDER", "tesseract")
    monkeypatch.setenv("OCR_MAX_OUTPUT_CHARS", "1234")

    settings = AppSettings(_env_file=None)

    assert settings.vision_enabled is True
    assert settings.screen_vision_enabled is True
    assert settings.screenshot_enabled is True
    assert settings.ocr_enabled is True
    assert settings.screen_vision_analyze_default is True
    assert settings.screen_capture_monitor == "2"
    assert settings.screen_capture_all_monitors is True
    assert settings.openai_vision_enabled is True
    assert settings.openai_vision_model == "gpt-4o-mini"
    assert settings.openai_vision_max_image_bytes == 123456
    assert settings.screenshot_save_dir.as_posix().endswith("data/custom-screenshots")
    assert settings.ocr_provider == "tesseract"
    assert settings.ocr_max_output_chars == 1234


def test_reminder_settings_defaults_are_safe() -> None:
    settings = AppSettings(_env_file=None)

    assert settings.reminders_enabled is True
    assert settings.reminders_check_enabled is True
    assert settings.reminders_check_interval_seconds == 60
    assert settings.reminders_speak_due is False
    assert settings.reminders_watch_enabled is False
    assert settings.reminders_watch_speak is False
    assert settings.reminders_database_path.name == "jarvis_reminders.db"


def test_gmail_settings_defaults_are_safe() -> None:
    settings = AppSettings(_env_file=None)

    assert settings.gmail_enabled is False
    assert settings.gmail_draft_enabled is False
    assert settings.gmail_send_draft_enabled is False
    assert settings.gmail_client_secret_path.name == "google_client_secret.json"
    assert settings.gmail_token_path.name == "token_gmail.json"
    assert settings.gmail_scopes_list == ["https://www.googleapis.com/auth/gmail.readonly"]
    assert settings.gmail_draft_scopes_list == ["https://www.googleapis.com/auth/gmail.compose"]
    assert settings.gmail_send_scopes_list == ["https://www.googleapis.com/auth/gmail.modify"]
    assert settings.gmail_max_results == 5


def test_gmail_settings_read_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GMAIL_ENABLED", "true")
    monkeypatch.setenv("GMAIL_DRAFT_ENABLED", "true")
    monkeypatch.setenv("GMAIL_SEND_DRAFT_ENABLED", "true")
    monkeypatch.setenv("GMAIL_CLIENT_SECRET_PATH", "credentials/custom_secret.json")
    monkeypatch.setenv("GMAIL_TOKEN_PATH", "credentials/custom_token.json")
    monkeypatch.setenv("GMAIL_SCOPES", "https://www.googleapis.com/auth/gmail.readonly")
    monkeypatch.setenv("GMAIL_DRAFT_SCOPES", "https://www.googleapis.com/auth/gmail.compose")
    monkeypatch.setenv("GMAIL_SEND_SCOPES", "https://www.googleapis.com/auth/gmail.modify")
    monkeypatch.setenv("GMAIL_MAX_RESULTS", "7")

    settings = AppSettings(_env_file=None)

    assert settings.gmail_enabled is True
    assert settings.gmail_draft_enabled is True
    assert settings.gmail_send_draft_enabled is True
    assert settings.gmail_client_secret_path.name == "custom_secret.json"
    assert settings.gmail_token_path.name == "custom_token.json"
    assert settings.gmail_scopes_list == ["https://www.googleapis.com/auth/gmail.readonly"]
    assert settings.gmail_draft_scopes_list == ["https://www.googleapis.com/auth/gmail.compose"]
    assert settings.gmail_send_scopes_list == ["https://www.googleapis.com/auth/gmail.modify"]
    assert settings.gmail_max_results == 7


def test_calendar_settings_defaults_are_safe() -> None:
    settings = AppSettings(_env_file=None)

    assert settings.calendar_enabled is False
    assert settings.calendar_create_enabled is False
    assert settings.calendar_client_secret_path.name == "google_client_secret.json"
    assert settings.calendar_token_path.name == "token_calendar.json"
    assert settings.calendar_scopes_list == ["https://www.googleapis.com/auth/calendar.readonly"]
    assert settings.calendar_write_scopes_list == ["https://www.googleapis.com/auth/calendar.events"]


def test_calendar_settings_read_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CALENDAR_ENABLED", "true")
    monkeypatch.setenv("CALENDAR_CREATE_ENABLED", "true")
    monkeypatch.setenv("CALENDAR_CLIENT_SECRET_PATH", "credentials/custom_secret.json")
    monkeypatch.setenv("CALENDAR_TOKEN_PATH", "credentials/custom_token.json")
    monkeypatch.setenv("CALENDAR_SCOPES", "https://www.googleapis.com/auth/calendar.readonly")
    monkeypatch.setenv("CALENDAR_WRITE_SCOPES", "https://www.googleapis.com/auth/calendar.events")

    settings = AppSettings(_env_file=None)

    assert settings.calendar_enabled is True
    assert settings.calendar_create_enabled is True
    assert settings.calendar_client_secret_path.name == "custom_secret.json"
    assert settings.calendar_token_path.name == "custom_token.json"
    assert settings.calendar_scopes_list == ["https://www.googleapis.com/auth/calendar.readonly"]
    assert settings.calendar_write_scopes_list == ["https://www.googleapis.com/auth/calendar.events"]
    assert settings.calendar_auth_scopes_list == [
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/calendar.events",
    ]


def test_app_launcher_settings_defaults_are_safe() -> None:
    settings = AppSettings(_env_file=None)

    assert settings.app_launcher_enabled is True
    assert settings.app_launcher_allowed_apps_map["notepad"] == "notepad.exe"
    assert settings.app_launcher_allowed_apps_map["calculator"] == "calc.exe"
    assert settings.app_launcher_allowed_apps_map["file explorer"] == "explorer.exe"
    assert settings.app_launcher_allowed_apps_map["edge"] == ""
    assert settings.app_launcher_allowed_apps_map["vscode"] == ""
    assert settings.app_launcher_allowed_apps_map["spotify"] == ""


def test_app_launcher_settings_read_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_LAUNCHER_ENABLED", "false")
    monkeypatch.setenv("APP_LAUNCHER_ALLOWED_APPS", "notepad=notepad.exe,paint=paint.exe")

    settings = AppSettings(_env_file=None)

    assert settings.app_launcher_enabled is False
    assert settings.app_launcher_allowed_apps_map == {"notepad": "notepad.exe", "paint": "paint.exe"}


def test_website_launcher_settings_defaults_are_safe() -> None:
    settings = AppSettings(_env_file=None)

    assert settings.website_launcher_enabled is True
    assert settings.website_allowed_sites_map["google"] == "https://www.google.com"
    assert settings.website_allowed_sites_map["chatgpt"] == "https://chatgpt.com"
    assert settings.website_allowed_sites_map["calendar"] == "https://calendar.google.com"
    assert settings.website_allowed_sites_map["blackboard"] == ""


def test_website_launcher_settings_read_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBSITE_LAUNCHER_ENABLED", "false")
    monkeypatch.setenv("WEBSITE_ALLOWED_SITES", "docs=https://docs.example.com,blackboard=")

    settings = AppSettings(_env_file=None)

    assert settings.website_launcher_enabled is False
    assert settings.website_allowed_sites_map == {"docs": "https://docs.example.com", "blackboard": ""}


def test_file_access_settings_defaults_are_safe() -> None:
    settings = AppSettings(_env_file=None)

    assert settings.file_access_enabled is False
    assert settings.file_read_enabled is False
    assert settings.file_summary_enabled is False
    assert settings.file_summary_max_chars == 6000
    assert settings.file_read_max_bytes == 20000
    assert settings.file_read_max_output_chars == 4000
    assert ".txt" in settings.file_read_allowed_extensions_list
    assert settings.file_access_allowed_folders_map["documents"].endswith("\\Documents")
    assert settings.file_access_allowed_folders_map["desktop"].endswith("\\Desktop")
    assert settings.file_access_allowed_folders_map["downloads"].endswith("\\Downloads")
    assert settings.file_access_allowed_folders_map["pictures"].endswith("\\Pictures")
    assert settings.file_access_allowed_folders_map["videos"].endswith("\\Videos")
    assert settings.file_access_allowed_folders_map["music"].endswith("\\Music")


def test_file_access_settings_read_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FILE_ACCESS_ENABLED", "true")
    monkeypatch.setenv("FILE_READ_ENABLED", "true")
    monkeypatch.setenv("FILE_SUMMARY_ENABLED", "true")
    monkeypatch.setenv("FILE_SUMMARY_MAX_CHARS", "2048")
    monkeypatch.setenv("FILE_READ_MAX_BYTES", "4096")
    monkeypatch.setenv("FILE_READ_MAX_OUTPUT_CHARS", "1024")
    monkeypatch.setenv("FILE_READ_ALLOWED_EXTENSIONS", "txt, md")
    monkeypatch.setenv("FILE_ACCESS_ALLOWED_FOLDERS", "docs=%USERPROFILE%\\Docs")

    settings = AppSettings(_env_file=None)

    assert settings.file_access_enabled is True
    assert settings.file_read_enabled is True
    assert settings.file_summary_enabled is True
    assert settings.file_summary_max_chars == 2048
    assert settings.file_read_max_bytes == 4096
    assert settings.file_read_max_output_chars == 1024
    assert settings.file_read_allowed_extensions_list == [".txt", ".md"]
    assert settings.file_access_allowed_folders_map == {"docs": "%USERPROFILE%\\Docs"}


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
