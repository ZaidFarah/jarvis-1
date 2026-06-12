from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class AppSettings(BaseSettings):
    """Runtime settings for the Jarvis desktop shell."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_prefix="JARVIS_",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "Jarvis"
    environment: str = "development"
    log_level: str = "INFO"
    log_dir: Path = Field(default=PROJECT_ROOT / "logs")
    window_width: int = Field(default=460, ge=360, le=1200)
    window_height: int = Field(default=620, ge=420, le=1400)
    always_on_top: bool = True
    minimize_to_tray: bool = True
    voice_sample_rate: int = Field(
        default=16000,
        ge=8000,
        le=48000,
        validation_alias=AliasChoices("VOICE_SAMPLE_RATE", "JARVIS_VOICE_SAMPLE_RATE"),
    )
    voice_channels: int = Field(
        default=1,
        ge=1,
        le=2,
        validation_alias=AliasChoices("VOICE_CHANNELS", "JARVIS_VOICE_CHANNELS"),
    )
    voice_record_seconds: float = Field(
        default=5.0,
        ge=0.25,
        le=10.0,
        validation_alias=AliasChoices(
            "VOICE_RECORD_SECONDS",
            "JARVIS_VOICE_RECORD_SECONDS",
            "JARVIS_VOICE_MICROPHONE_TEST_SECONDS",
        ),
    )
    voice_vad_enabled: bool = True
    voice_vad_threshold: float = Field(
        default=0.0015,
        ge=0.0,
        le=1.0,
        validation_alias=AliasChoices("VOICE_VAD_THRESHOLD", "JARVIS_VOICE_VAD_THRESHOLD"),
    )
    speech_to_text_provider: str = Field(
        default="faster_whisper",
        validation_alias=AliasChoices("STT_PROVIDER", "JARVIS_STT_PROVIDER", "JARVIS_SPEECH_TO_TEXT_PROVIDER"),
    )
    whisper_model: str = Field(
        default="base.en",
        validation_alias=AliasChoices("WHISPER_MODEL", "JARVIS_WHISPER_MODEL"),
    )
    whisper_device: str = Field(
        default="cpu",
        validation_alias=AliasChoices("WHISPER_DEVICE", "JARVIS_WHISPER_DEVICE"),
    )
    whisper_compute_type: str = Field(
        default="int8",
        validation_alias=AliasChoices("WHISPER_COMPUTE_TYPE", "JARVIS_WHISPER_COMPUTE_TYPE"),
    )
    wake_phrase: str = Field(
        default="hey jarvis",
        validation_alias=AliasChoices("WAKE_PHRASE", "JARVIS_WAKE_PHRASE"),
    )
    wake_aliases: str = Field(
        default="hey jarvis,hi jarvis,wake up jarvis,jarvis wake up,okay jarvis,yo jarvis",
        validation_alias=AliasChoices("WAKE_ALIASES", "JARVIS_WAKE_ALIASES"),
    )
    wake_match_threshold: float = Field(
        default=0.72,
        ge=0.0,
        le=1.0,
        validation_alias=AliasChoices("WAKE_MATCH_THRESHOLD", "JARVIS_WAKE_MATCH_THRESHOLD"),
    )
    wake_listen_seconds: float = Field(
        default=5.0,
        ge=0.25,
        le=10.0,
        validation_alias=AliasChoices("WAKE_LISTEN_SECONDS", "JARVIS_WAKE_LISTEN_SECONDS"),
    )
    voice_command_start_delay_seconds: float = Field(
        default=1.0,
        ge=0.0,
        le=5.0,
        validation_alias=AliasChoices(
            "VOICE_COMMAND_START_DELAY_SECONDS",
            "JARVIS_VOICE_COMMAND_START_DELAY_SECONDS",
        ),
    )
    voice_command_record_seconds: float = Field(
        default=7.0,
        ge=0.25,
        le=30.0,
        validation_alias=AliasChoices("VOICE_COMMAND_RECORD_SECONDS", "JARVIS_VOICE_COMMAND_RECORD_SECONDS"),
    )
    voice_loop_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("VOICE_LOOP_ENABLED", "JARVIS_VOICE_LOOP_ENABLED"),
    )
    voice_loop_max_empty_commands: int = Field(
        default=3,
        ge=0,
        le=20,
        validation_alias=AliasChoices("VOICE_LOOP_MAX_EMPTY_COMMANDS", "JARVIS_VOICE_LOOP_MAX_EMPTY_COMMANDS"),
    )
    voice_loop_wake_cooldown_seconds: float = Field(
        default=1.5,
        ge=0.0,
        le=10.0,
        validation_alias=AliasChoices(
            "VOICE_LOOP_WAKE_COOLDOWN_SECONDS",
            "JARVIS_VOICE_LOOP_WAKE_COOLDOWN_SECONDS",
        ),
    )
    voice_loop_speak_status: bool = Field(
        default=True,
        validation_alias=AliasChoices("VOICE_LOOP_SPEAK_STATUS", "JARVIS_VOICE_LOOP_SPEAK_STATUS"),
    )
    conversation_history_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "CONVERSATION_HISTORY_ENABLED",
            "JARVIS_CONVERSATION_HISTORY_ENABLED",
        ),
    )
    conversation_history_max_messages: int = Field(
        default=10,
        ge=0,
        le=50,
        validation_alias=AliasChoices(
            "CONVERSATION_HISTORY_MAX_MESSAGES",
            "JARVIS_CONVERSATION_HISTORY_MAX_MESSAGES",
        ),
    )
    memory_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("MEMORY_ENABLED", "JARVIS_MEMORY_ENABLED"),
    )
    memory_database_path: Path = Field(
        default=PROJECT_ROOT / "data" / "jarvis_memory.db",
        validation_alias=AliasChoices("MEMORY_DATABASE_PATH", "JARVIS_MEMORY_DATABASE_PATH"),
    )
    reminders_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("REMINDERS_ENABLED", "JARVIS_REMINDERS_ENABLED"),
    )
    reminders_check_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("REMINDERS_CHECK_ENABLED", "JARVIS_REMINDERS_CHECK_ENABLED"),
    )
    reminders_check_interval_seconds: int = Field(
        default=60,
        ge=5,
        le=3600,
        validation_alias=AliasChoices(
            "REMINDERS_CHECK_INTERVAL_SECONDS",
            "JARVIS_REMINDERS_CHECK_INTERVAL_SECONDS",
        ),
    )
    reminders_speak_due: bool = Field(
        default=False,
        validation_alias=AliasChoices("REMINDERS_SPEAK_DUE", "JARVIS_REMINDERS_SPEAK_DUE"),
    )
    reminders_watch_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("REMINDERS_WATCH_ENABLED", "JARVIS_REMINDERS_WATCH_ENABLED"),
    )
    reminders_watch_speak: bool = Field(
        default=False,
        validation_alias=AliasChoices("REMINDERS_WATCH_SPEAK", "JARVIS_REMINDERS_WATCH_SPEAK"),
    )
    app_launcher_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("APP_LAUNCHER_ENABLED", "JARVIS_APP_LAUNCHER_ENABLED"),
    )
    app_launcher_allowed_apps: str = Field(
        default="notepad=notepad.exe,calculator=calc.exe,chrome=,edge=,vscode=,docker=",
        validation_alias=AliasChoices("APP_LAUNCHER_ALLOWED_APPS", "JARVIS_APP_LAUNCHER_ALLOWED_APPS"),
    )
    website_launcher_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("WEBSITE_LAUNCHER_ENABLED", "JARVIS_WEBSITE_LAUNCHER_ENABLED"),
    )
    website_allowed_sites: str = Field(
        default=(
            "google=https://www.google.com,"
            "youtube=https://www.youtube.com,"
            "github=https://github.com,"
            "gmail=https://mail.google.com,"
            "blackboard=,"
            "outlook=https://outlook.office.com"
        ),
        validation_alias=AliasChoices("WEBSITE_ALLOWED_SITES", "JARVIS_WEBSITE_ALLOWED_SITES"),
    )
    file_access_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("FILE_ACCESS_ENABLED", "JARVIS_FILE_ACCESS_ENABLED"),
    )
    file_read_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("FILE_READ_ENABLED", "JARVIS_FILE_READ_ENABLED"),
    )
    file_read_max_bytes: int = Field(
        default=20000,
        ge=1024,
        le=10_000_000,
        validation_alias=AliasChoices("FILE_READ_MAX_BYTES", "JARVIS_FILE_READ_MAX_BYTES"),
    )
    file_read_max_output_chars: int = Field(
        default=4000,
        ge=256,
        le=100_000,
        validation_alias=AliasChoices("FILE_READ_MAX_OUTPUT_CHARS", "JARVIS_FILE_READ_MAX_OUTPUT_CHARS"),
    )
    file_read_allowed_extensions: str = Field(
        default=".txt,.md,.csv,.json,.py,.java,.cpp,.h,.html,.css,.js",
        validation_alias=AliasChoices("FILE_READ_ALLOWED_EXTENSIONS", "JARVIS_FILE_READ_ALLOWED_EXTENSIONS"),
    )
    file_access_allowed_folders: str = Field(
        default=(
            "documents=%USERPROFILE%\\Documents,"
            "desktop=%USERPROFILE%\\Desktop,"
            "downloads=%USERPROFILE%\\Downloads"
        ),
        validation_alias=AliasChoices("FILE_ACCESS_ALLOWED_FOLDERS", "JARVIS_FILE_ACCESS_ALLOWED_FOLDERS"),
    )
    confirmation_required: bool = Field(
        default=True,
        validation_alias=AliasChoices("CONFIRMATION_REQUIRED", "JARVIS_CONFIRMATION_REQUIRED"),
    )
    confirmation_timeout_seconds: int = Field(
        default=30,
        ge=1,
        le=300,
        validation_alias=AliasChoices("CONFIRMATION_TIMEOUT_SECONDS", "JARVIS_CONFIRMATION_TIMEOUT_SECONDS"),
    )
    notifications_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("NOTIFICATIONS_ENABLED", "JARVIS_NOTIFICATIONS_ENABLED"),
    )
    notification_provider: str = Field(
        default="windows_toast",
        validation_alias=AliasChoices("NOTIFICATION_PROVIDER", "JARVIS_NOTIFICATION_PROVIDER"),
    )
    reminders_toast_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("REMINDERS_TOAST_ENABLED", "JARVIS_REMINDERS_TOAST_ENABLED"),
    )
    reminders_database_path: Path = Field(
        default=PROJECT_ROOT / "data" / "jarvis_reminders.db",
        validation_alias=AliasChoices("REMINDERS_DATABASE_PATH", "JARVIS_REMINDERS_DATABASE_PATH"),
    )
    weather_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("WEATHER_ENABLED", "JARVIS_WEATHER_ENABLED"),
    )
    weather_provider: str = Field(
        default="openweathermap",
        validation_alias=AliasChoices("WEATHER_PROVIDER", "JARVIS_WEATHER_PROVIDER"),
    )
    weather_api_key: str = Field(
        default="",
        repr=False,
        validation_alias=AliasChoices("WEATHER_API_KEY", "JARVIS_WEATHER_API_KEY"),
    )
    weather_default_city: str = Field(
        default="Nottingham",
        validation_alias=AliasChoices("WEATHER_DEFAULT_CITY", "JARVIS_WEATHER_DEFAULT_CITY"),
    )
    weather_units: str = Field(
        default="metric",
        validation_alias=AliasChoices("WEATHER_UNITS", "JARVIS_WEATHER_UNITS"),
    )
    openai_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("OPENAI_ENABLED", "JARVIS_OPENAI_ENABLED"),
    )
    openai_api_key: str = Field(
        default="",
        repr=False,
        validation_alias=AliasChoices("OPENAI_API_KEY", "JARVIS_OPENAI_API_KEY"),
    )
    openai_model: str = Field(
        default="gpt-4o-mini",
        validation_alias=AliasChoices("OPENAI_MODEL", "JARVIS_OPENAI_MODEL"),
    )
    system_prompt: str = Field(
        default="You are Jarvis, a helpful personal desktop AI assistant.",
        validation_alias=AliasChoices("SYSTEM_PROMPT", "JARVIS_SYSTEM_PROMPT"),
    )
    tts_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("TTS_ENABLED", "JARVIS_TTS_ENABLED"),
    )
    tts_provider: str = Field(
        default="openai",
        validation_alias=AliasChoices(
            "TTS_PROVIDER",
            "JARVIS_TTS_PROVIDER",
            "JARVIS_TEXT_TO_SPEECH_PROVIDER",
            "text_to_speech_provider",
        ),
    )
    tts_voice_name: str = Field(
        default="",
        validation_alias=AliasChoices("TTS_VOICE_NAME", "JARVIS_TTS_VOICE_NAME"),
    )
    tts_rate: int = Field(
        default=175,
        ge=80,
        le=400,
        validation_alias=AliasChoices("TTS_RATE", "JARVIS_TTS_RATE"),
    )
    tts_volume: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        validation_alias=AliasChoices("TTS_VOLUME", "JARVIS_TTS_VOLUME"),
    )
    openai_tts_model: str = Field(
        default="gpt-4o-mini-tts",
        validation_alias=AliasChoices("OPENAI_TTS_MODEL", "JARVIS_OPENAI_TTS_MODEL"),
    )
    openai_tts_voice: str = Field(
        default="cedar",
        validation_alias=AliasChoices("OPENAI_TTS_VOICE", "JARVIS_OPENAI_TTS_VOICE"),
    )
    openai_tts_format: str = Field(
        default="mp3",
        validation_alias=AliasChoices("OPENAI_TTS_FORMAT", "JARVIS_OPENAI_TTS_FORMAT"),
    )
    openai_tts_instructions: str = Field(
        default=(
            "Speak as a calm, mature, professional British-inspired desktop AI assistant. "
            "Use a confident, clear, cinematic tone. Do not sound childish. "
            "Keep the pace natural and efficient."
        ),
        validation_alias=AliasChoices("OPENAI_TTS_INSTRUCTIONS", "JARVIS_OPENAI_TTS_INSTRUCTIONS"),
    )

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized = value.upper().strip()
        allowed = {"TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"}
        if normalized not in allowed:
            raise ValueError(f"Unsupported log level: {value}")
        return normalized

    @field_validator("log_dir")
    @classmethod
    def expand_log_dir(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    @field_validator("memory_database_path")
    @classmethod
    def expand_memory_database_path(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    @field_validator("reminders_database_path")
    @classmethod
    def expand_reminders_database_path(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    @field_validator("speech_to_text_provider", "tts_provider", "whisper_device", "whisper_compute_type")
    @classmethod
    def normalize_provider_name(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not cleaned:
            raise ValueError("Provider name cannot be empty.")
        return cleaned

    @field_validator("weather_provider")
    @classmethod
    def normalize_weather_provider(cls, value: str) -> str:
        cleaned = value.strip().lower()
        allowed = {"openweathermap"}
        if cleaned not in allowed:
            raise ValueError(f"Unsupported weather provider: {value}")
        return cleaned

    @field_validator("notification_provider")
    @classmethod
    def normalize_notification_provider(cls, value: str) -> str:
        cleaned = value.strip().lower()
        allowed = {"windows_toast"}
        if cleaned not in allowed:
            raise ValueError(f"Unsupported notification provider: {value}")
        return cleaned

    @field_validator("app_launcher_allowed_apps")
    @classmethod
    def normalize_app_launcher_allowed_apps(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            return ""
        return cleaned

    @field_validator("website_allowed_sites")
    @classmethod
    def normalize_website_allowed_sites(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            return ""
        return cleaned

    @field_validator("file_access_allowed_folders")
    @classmethod
    def normalize_file_access_allowed_folders(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            return ""
        return cleaned

    @field_validator("file_read_allowed_extensions")
    @classmethod
    def normalize_file_read_allowed_extensions(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            return ""
        return cleaned

    @field_validator("weather_default_city")
    @classmethod
    def normalize_weather_default_city(cls, value: str) -> str:
        cleaned = " ".join(value.strip().split())
        if not cleaned:
            raise ValueError("Weather default city cannot be empty.")
        return cleaned

    @field_validator("weather_units")
    @classmethod
    def normalize_weather_units(cls, value: str) -> str:
        cleaned = value.strip().lower()
        allowed = {"metric", "imperial", "standard"}
        if cleaned not in allowed:
            raise ValueError(f"Unsupported weather units: {value}")
        return cleaned

    @field_validator("weather_api_key")
    @classmethod
    def strip_weather_api_key(cls, value: str) -> str:
        return value.strip()

    @field_validator("tts_voice_name")
    @classmethod
    def normalize_tts_voice_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("openai_tts_model", "openai_tts_voice", "openai_tts_instructions")
    @classmethod
    def normalize_openai_tts_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("OpenAI TTS setting cannot be empty.")
        return cleaned

    @field_validator("openai_tts_format")
    @classmethod
    def normalize_openai_tts_format(cls, value: str) -> str:
        cleaned = value.strip().lower()
        allowed = {"mp3", "opus", "aac", "flac", "wav", "pcm"}
        if cleaned not in allowed:
            raise ValueError(f"Unsupported OpenAI TTS format: {value}")
        return cleaned

    @field_validator("wake_phrase")
    @classmethod
    def normalize_wake_phrase(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not cleaned:
            raise ValueError("Wake phrase cannot be empty.")
        return cleaned

    @field_validator("wake_aliases", mode="before")
    @classmethod
    def normalize_wake_aliases(cls, value: Any) -> str:
        if isinstance(value, (list, tuple)):
            return ",".join(str(item) for item in value)
        return str(value)

    @field_validator("openai_api_key")
    @classmethod
    def strip_openai_api_key(cls, value: str) -> str:
        return value.strip()

    @field_validator("openai_model")
    @classmethod
    def normalize_openai_model(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("OpenAI model cannot be empty.")
        return cleaned

    @field_validator("system_prompt")
    @classmethod
    def normalize_system_prompt(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("System prompt cannot be empty.")
        return cleaned

    @property
    def voice_microphone_test_seconds(self) -> float:
        return self.voice_record_seconds

    @property
    def text_to_speech_provider(self) -> str:
        return self.tts_provider

    @property
    def wake_alias_list(self) -> list[str]:
        aliases = [item.strip().lower() for item in self.wake_aliases.split(",")]
        return [alias for alias in aliases if alias]

    @property
    def has_openai_api_key(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def has_weather_api_key(self) -> bool:
        return bool(self.weather_api_key)

    @property
    def has_reminders_database(self) -> bool:
        return bool(self.reminders_database_path)

    @property
    def app_launcher_allowed_apps_map(self) -> dict[str, str]:
        raw = self.app_launcher_allowed_apps.strip()
        if not raw:
            return {}

        entries = raw.replace("\n", ",").split(",")
        parsed: dict[str, str] = {}
        for entry in entries:
            item = entry.strip()
            if not item:
                continue
            if "=" not in item:
                continue
            name, command = item.split("=", 1)
            cleaned_name = name.strip().lower()
            if not cleaned_name:
                continue
            parsed[cleaned_name] = command.strip()
        return parsed

    @property
    def website_allowed_sites_map(self) -> dict[str, str]:
        raw = self.website_allowed_sites.strip()
        if not raw:
            return {}

        entries = raw.replace("\n", ",").split(",")
        parsed: dict[str, str] = {}
        for entry in entries:
            item = entry.strip()
            if not item:
                continue
            if "=" not in item:
                continue
            name, url = item.split("=", 1)
            cleaned_name = name.strip().lower()
            if not cleaned_name:
                continue
            parsed[cleaned_name] = url.strip()
        return parsed

    @property
    def file_access_allowed_folders_map(self) -> dict[str, str]:
        raw = self.file_access_allowed_folders.strip()
        if not raw:
            return {}

        entries = raw.replace("\n", ",").split(",")
        parsed: dict[str, str] = {}
        for entry in entries:
            item = entry.strip()
            if not item:
                continue
            if "=" not in item:
                continue
            name, folder_path = item.split("=", 1)
            cleaned_name = name.strip().lower()
            if not cleaned_name:
                continue
            parsed[cleaned_name] = folder_path.strip()
        return parsed

    @property
    def file_read_allowed_extensions_list(self) -> list[str]:
        raw = self.file_read_allowed_extensions.strip()
        if not raw:
            return []

        extensions: list[str] = []
        for item in raw.replace("\n", ",").split(","):
            cleaned = item.strip().lower()
            if not cleaned:
                continue
            if not cleaned.startswith("."):
                cleaned = f".{cleaned}"
            if cleaned not in extensions:
                extensions.append(cleaned)
        return extensions


def load_settings() -> AppSettings:
    return AppSettings()
