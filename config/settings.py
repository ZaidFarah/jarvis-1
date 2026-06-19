from __future__ import annotations

import sys
import os
from pathlib import Path
from typing import Any

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from jarvis_runtime.config_bootstrap import detect_runtime_mode, get_runtime_config_paths
from jarvis_runtime.version import APP_VERSION, normalize_version


def _resolve_project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


PROJECT_ROOT = _resolve_project_root()
DEFAULT_CONFIG_PATHS = get_runtime_config_paths(detect_runtime_mode(), PROJECT_ROOT)


class AppSettings(BaseSettings):
    """Runtime settings for the Jarvis desktop shell."""

    model_config = SettingsConfigDict(
        env_file=DEFAULT_CONFIG_PATHS.env_path,
        env_prefix="JARVIS_",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = Field(
        default="Jarvis",
        validation_alias=AliasChoices("APP_NAME", "JARVIS_APP_NAME"),
    )
    app_version: str = Field(
        default=APP_VERSION,
        validation_alias=AliasChoices("APP_VERSION", "JARVIS_APP_VERSION"),
    )
    startup_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("STARTUP_ENABLED", "JARVIS_STARTUP_ENABLED"),
    )
    backup_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("BACKUP_ENABLED", "JARVIS_BACKUP_ENABLED"),
    )
    backup_include_env: bool = Field(
        default=False,
        validation_alias=AliasChoices("BACKUP_INCLUDE_ENV", "JARVIS_BACKUP_INCLUDE_ENV"),
    )
    backup_include_tokens: bool = Field(
        default=False,
        validation_alias=AliasChoices("BACKUP_INCLUDE_TOKENS", "JARVIS_BACKUP_INCLUDE_TOKENS"),
    )
    backup_include_client_secret: bool = Field(
        default=False,
        validation_alias=AliasChoices("BACKUP_INCLUDE_CLIENT_SECRET", "JARVIS_BACKUP_INCLUDE_CLIENT_SECRET"),
    )
    signing_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("SIGNING_ENABLED", "JARVIS_SIGNING_ENABLED"),
    )
    signing_cert_path: str = Field(
        default="",
        validation_alias=AliasChoices("SIGNING_CERT_PATH", "JARVIS_SIGNING_CERT_PATH"),
    )
    signing_timestamp_url: str = Field(
        default="http://timestamp.digicert.com",
        validation_alias=AliasChoices("SIGNING_TIMESTAMP_URL", "JARVIS_SIGNING_TIMESTAMP_URL"),
    )
    signing_description: str = Field(
        default="Jarvis Desktop AI Assistant",
        validation_alias=AliasChoices("SIGNING_DESCRIPTION", "JARVIS_SIGNING_DESCRIPTION"),
    )
    startup_app_name: str = Field(
        default="Jarvis",
        validation_alias=AliasChoices("STARTUP_APP_NAME", "JARVIS_STARTUP_APP_NAME"),
    )
    runtime_mode: str = Field(
        default="source",
        validation_alias=AliasChoices("RUNTIME_MODE", "JARVIS_RUNTIME_MODE"),
    )
    environment: str = "development"
    log_level: str = "INFO"
    log_dir: Path = Field(default=DEFAULT_CONFIG_PATHS.logs_path)
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
    voice_input_device: str = Field(
        default="",
        validation_alias=AliasChoices("VOICE_INPUT_DEVICE", "JARVIS_VOICE_INPUT_DEVICE"),
    )
    voice_health_speech_seconds: float = Field(
        default=6.0,
        ge=1.0,
        le=30.0,
        validation_alias=AliasChoices(
            "VOICE_HEALTH_SPEECH_SECONDS",
            "JARVIS_VOICE_HEALTH_SPEECH_SECONDS",
        ),
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
    voice_vad_window_ms: int = Field(
        default=80,
        ge=20,
        le=250,
        validation_alias=AliasChoices("VOICE_VAD_WINDOW_MS", "JARVIS_VOICE_VAD_WINDOW_MS"),
    )
    voice_vad_noise_multiplier: float = Field(
        default=3.0,
        ge=1.0,
        le=10.0,
        validation_alias=AliasChoices("VOICE_VAD_NOISE_MULTIPLIER", "JARVIS_VOICE_VAD_NOISE_MULTIPLIER"),
    )
    voice_vad_silence_ms: int = Field(
        default=650,
        ge=120,
        le=2500,
        validation_alias=AliasChoices("VOICE_VAD_SILENCE_MS", "JARVIS_VOICE_VAD_SILENCE_MS"),
    )
    fast_voice_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("FAST_VOICE_ENABLED", "JARVIS_FAST_VOICE_ENABLED"),
    )
    fast_voice_activation: str = Field(
        default="enter",
        validation_alias=AliasChoices("FAST_VOICE_ACTIVATION", "JARVIS_FAST_VOICE_ACTIVATION"),
    )
    fast_voice_record_seconds: float = Field(
        default=4.0,
        ge=1.0,
        le=30.0,
        validation_alias=AliasChoices("FAST_VOICE_RECORD_SECONDS", "JARVIS_FAST_VOICE_RECORD_SECONDS"),
    )
    fast_voice_max_seconds: float = Field(
        default=2.2,
        ge=1.0,
        le=30.0,
        validation_alias=AliasChoices("FAST_VOICE_MAX_SECONDS", "JARVIS_FAST_VOICE_MAX_SECONDS"),
    )
    fast_voice_min_speech_ms: int = Field(
        default=300,
        ge=80,
        le=5000,
        validation_alias=AliasChoices("FAST_VOICE_MIN_SPEECH_MS", "JARVIS_FAST_VOICE_MIN_SPEECH_MS"),
    )
    fast_voice_silence_ms: int = Field(
        default=400,
        ge=120,
        le=2500,
        validation_alias=AliasChoices("FAST_VOICE_SILENCE_MS", "JARVIS_FAST_VOICE_SILENCE_MS"),
    )
    fast_voice_preroll_ms: int = Field(
        default=250,
        ge=0,
        le=1000,
        validation_alias=AliasChoices("FAST_VOICE_PREROLL_MS", "JARVIS_FAST_VOICE_PREROLL_MS"),
    )
    fast_voice_tts_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("FAST_VOICE_TTS_ENABLED", "JARVIS_FAST_VOICE_TTS_ENABLED"),
    )
    fast_voice_wake_only_response: str = Field(
        default="I'm listening.",
        validation_alias=AliasChoices(
            "FAST_VOICE_WAKE_ONLY_RESPONSE",
            "JARVIS_FAST_VOICE_WAKE_ONLY_RESPONSE",
        ),
    )
    fast_voice_empty_audio_response: str = Field(
        default="I heard sound but could not understand it.",
        validation_alias=AliasChoices(
            "FAST_VOICE_EMPTY_AUDIO_RESPONSE",
            "JARVIS_FAST_VOICE_EMPTY_AUDIO_RESPONSE",
        ),
    )
    fast_voice_warm_stt_on_start: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "FAST_VOICE_WARM_STT_ON_START",
            "JARVIS_FAST_VOICE_WARM_STT_ON_START",
        ),
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
        default=(
            "jarvis,hey jarvis,hi jarvis,okay jarvis,wake up jarvis,yo jarvis,"
            "jarvis please,service,jervis,travis,charities,office,jar of this,out of this,turn this"
        ),
        validation_alias=AliasChoices("WAKE_ALIASES", "JARVIS_WAKE_ALIASES"),
    )
    wake_match_threshold: float = Field(
        default=0.72,
        ge=0.0,
        le=1.0,
        validation_alias=AliasChoices(
            "WAKE_MATCH_THRESHOLD",
            "WAKE_THRESHOLD",
            "JARVIS_WAKE_MATCH_THRESHOLD",
            "JARVIS_WAKE_THRESHOLD",
        ),
    )
    wake_listen_seconds: float = Field(
        default=2.0,
        ge=0.25,
        le=10.0,
        validation_alias=AliasChoices("WAKE_LISTEN_SECONDS", "JARVIS_WAKE_LISTEN_SECONDS"),
    )
    wake_provider: str = Field(
        default="openwakeword",
        validation_alias=AliasChoices("WAKE_PROVIDER", "JARVIS_WAKE_PROVIDER"),
    )
    wake_fallback_provider: str = Field(
        default="whisper_fuzzy",
        validation_alias=AliasChoices("WAKE_FALLBACK_PROVIDER", "JARVIS_WAKE_FALLBACK_PROVIDER"),
    )
    openwakeword_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("OPENWAKEWORD_ENABLED", "JARVIS_OPENWAKEWORD_ENABLED"),
    )
    openwakeword_model: str = Field(
        default="hey_jarvis",
        validation_alias=AliasChoices("OPENWAKEWORD_MODEL", "JARVIS_OPENWAKEWORD_MODEL"),
    )
    openwakeword_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        validation_alias=AliasChoices("OPENWAKEWORD_THRESHOLD", "JARVIS_OPENWAKEWORD_THRESHOLD"),
    )
    openwakeword_listen_chunk_ms: int = Field(
        default=80,
        ge=20,
        le=1000,
        validation_alias=AliasChoices(
            "OPENWAKEWORD_LISTEN_CHUNK_MS",
            "JARVIS_OPENWAKEWORD_LISTEN_CHUNK_MS",
        ),
    )
    openwakeword_test_seconds: float = Field(
        default=10.0,
        ge=1.0,
        le=60.0,
        validation_alias=AliasChoices("OPENWAKEWORD_TEST_SECONDS", "JARVIS_OPENWAKEWORD_TEST_SECONDS"),
    )
    openwakeword_calibration_rounds: int = Field(
        default=5,
        ge=1,
        le=20,
        validation_alias=AliasChoices(
            "OPENWAKEWORD_CALIBRATION_ROUNDS",
            "JARVIS_OPENWAKEWORD_CALIBRATION_ROUNDS",
        ),
    )
    openwakeword_calibration_seconds: float = Field(
        default=4.0,
        ge=1.0,
        le=30.0,
        validation_alias=AliasChoices(
            "OPENWAKEWORD_CALIBRATION_SECONDS",
            "JARVIS_OPENWAKEWORD_CALIBRATION_SECONDS",
        ),
    )
    openwakeword_fallback_to_whisper: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "OPENWAKEWORD_FALLBACK_TO_WHISPER",
            "JARVIS_OPENWAKEWORD_FALLBACK_TO_WHISPER",
        ),
    )
    voice_command_start_delay_seconds: float = Field(
        default=0.0,
        ge=0.0,
        le=5.0,
        validation_alias=AliasChoices(
            "VOICE_COMMAND_START_DELAY_SECONDS",
            "JARVIS_VOICE_COMMAND_START_DELAY_SECONDS",
        ),
    )
    voice_command_record_seconds: float = Field(
        default=5.0,
        ge=0.25,
        le=30.0,
        validation_alias=AliasChoices("VOICE_COMMAND_RECORD_SECONDS", "JARVIS_VOICE_COMMAND_RECORD_SECONDS"),
    )
    voice_command_min_words: int = Field(
        default=2,
        ge=1,
        le=20,
        validation_alias=AliasChoices("VOICE_COMMAND_MIN_WORDS", "JARVIS_VOICE_COMMAND_MIN_WORDS"),
    )
    voice_command_reject_phrases: str = Field(
        default="you,uh,um,hmm,yeah,okay",
        validation_alias=AliasChoices("VOICE_COMMAND_REJECT_PHRASES", "JARVIS_VOICE_COMMAND_REJECT_PHRASES"),
    )
    voice_command_incomplete_phrases: str = Field(
        default="what's the,what is the,tell me about,can you,could you,weather in,remind me,please",
        validation_alias=AliasChoices(
            "VOICE_COMMAND_INCOMPLETE_PHRASES",
            "JARVIS_VOICE_COMMAND_INCOMPLETE_PHRASES",
        ),
    )
    voice_speech_repair_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("VOICE_SPEECH_REPAIR_ENABLED", "JARVIS_VOICE_SPEECH_REPAIR_ENABLED"),
    )
    voice_use_openai_repair: bool = Field(
        default=False,
        validation_alias=AliasChoices("VOICE_USE_OPENAI_REPAIR", "JARVIS_VOICE_USE_OPENAI_REPAIR"),
    )
    voice_repair_rules: str = Field(
        default=(
            "did it noting him today whats the=>what's the weather in {weather_default_city} today;"
            "did it nottingham today whats the=>what's the weather in {weather_default_city} today"
        ),
        validation_alias=AliasChoices("VOICE_REPAIR_RULES", "JARVIS_VOICE_REPAIR_RULES"),
    )
    voice_repair_incomplete_phrases: str = Field(
        default="what's the,what is the,tell me about,can you,could you,weather in,remind me,please",
        validation_alias=AliasChoices(
            "VOICE_REPAIR_INCOMPLETE_PHRASES",
            "JARVIS_VOICE_REPAIR_INCOMPLETE_PHRASES",
        ),
    )
    voice_repair_confirmation_threshold: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        validation_alias=AliasChoices(
            "VOICE_REPAIR_CONFIRMATION_THRESHOLD",
            "JARVIS_VOICE_REPAIR_CONFIRMATION_THRESHOLD",
        ),
    )
    voice_repair_confirmation_seconds: float = Field(
        default=3.0,
        ge=0.25,
        le=10.0,
        validation_alias=AliasChoices(
            "VOICE_REPAIR_CONFIRMATION_SECONDS",
            "JARVIS_VOICE_REPAIR_CONFIRMATION_SECONDS",
        ),
    )
    voice_command_retry_on_reject: bool = Field(
        default=True,
        validation_alias=AliasChoices("VOICE_COMMAND_RETRY_ON_REJECT", "JARVIS_VOICE_COMMAND_RETRY_ON_REJECT"),
    )
    voice_command_max_retries: int = Field(
        default=1,
        ge=0,
        le=5,
        validation_alias=AliasChoices("VOICE_COMMAND_MAX_RETRIES", "JARVIS_VOICE_COMMAND_MAX_RETRIES"),
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
    voice_loop_speak_wake_ack: bool = Field(
        default=False,
        validation_alias=AliasChoices("VOICE_LOOP_SPEAK_WAKE_ACK", "JARVIS_VOICE_LOOP_SPEAK_WAKE_ACK"),
    )
    voice_loop_speak_responses: bool = Field(
        default=True,
        validation_alias=AliasChoices("VOICE_LOOP_SPEAK_RESPONSES", "JARVIS_VOICE_LOOP_SPEAK_RESPONSES"),
    )
    voice_follow_up_timeout_seconds: float = Field(
        default=10.0,
        ge=1.0,
        le=30.0,
        validation_alias=AliasChoices(
            "VOICE_FOLLOW_UP_TIMEOUT_SECONDS",
            "JARVIS_VOICE_FOLLOW_UP_TIMEOUT_SECONDS",
        ),
    )
    voice_response_mode: str = Field(
        default="concise",
        validation_alias=AliasChoices("VOICE_RESPONSE_MODE", "JARVIS_VOICE_RESPONSE_MODE"),
    )
    voice_concise_instruction: str = Field(
        default="Answer voice commands in one or two short sentences unless the user asks for detail.",
        validation_alias=AliasChoices("VOICE_CONCISE_INSTRUCTION", "JARVIS_VOICE_CONCISE_INSTRUCTION"),
    )
    voice_loop_speak_standby: bool = Field(
        default=False,
        validation_alias=AliasChoices("VOICE_LOOP_SPEAK_STANDBY", "JARVIS_VOICE_LOOP_SPEAK_STANDBY"),
    )
    voice_loop_standby_message: str = Field(
        default="Standing by.",
        validation_alias=AliasChoices("VOICE_LOOP_STANDBY_MESSAGE", "JARVIS_VOICE_LOOP_STANDBY_MESSAGE"),
    )
    agent_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("AGENT_ENABLED", "JARVIS_AGENT_ENABLED"),
    )
    agent_experimental: bool = Field(
        default=True,
        validation_alias=AliasChoices("AGENT_EXPERIMENTAL", "JARVIS_AGENT_EXPERIMENTAL"),
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
        default=DEFAULT_CONFIG_PATHS.data_path / "jarvis_memory.db",
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
    file_summary_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("FILE_SUMMARY_ENABLED", "JARVIS_FILE_SUMMARY_ENABLED"),
    )
    file_summary_max_chars: int = Field(
        default=6000,
        ge=512,
        le=100_000,
        validation_alias=AliasChoices("FILE_SUMMARY_MAX_CHARS", "JARVIS_FILE_SUMMARY_MAX_CHARS"),
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
    gmail_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("GMAIL_ENABLED", "JARVIS_GMAIL_ENABLED"),
    )
    gmail_client_secret_path: Path = Field(
        default=DEFAULT_CONFIG_PATHS.credentials_path / "google_client_secret.json",
        validation_alias=AliasChoices("GMAIL_CLIENT_SECRET_PATH", "JARVIS_GMAIL_CLIENT_SECRET_PATH"),
    )
    gmail_token_path: Path = Field(
        default=DEFAULT_CONFIG_PATHS.credentials_path / "token_gmail.json",
        validation_alias=AliasChoices("GMAIL_TOKEN_PATH", "JARVIS_GMAIL_TOKEN_PATH"),
    )
    gmail_scopes: str = Field(
        default="https://www.googleapis.com/auth/gmail.readonly",
        validation_alias=AliasChoices("GMAIL_SCOPES", "JARVIS_GMAIL_SCOPES"),
    )
    gmail_draft_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("GMAIL_DRAFT_ENABLED", "JARVIS_GMAIL_DRAFT_ENABLED"),
    )
    gmail_draft_scopes: str = Field(
        default="https://www.googleapis.com/auth/gmail.compose",
        validation_alias=AliasChoices("GMAIL_DRAFT_SCOPES", "JARVIS_GMAIL_DRAFT_SCOPES"),
    )
    gmail_send_draft_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("GMAIL_SEND_DRAFT_ENABLED", "JARVIS_GMAIL_SEND_DRAFT_ENABLED"),
    )
    gmail_send_scopes: str = Field(
        default="https://www.googleapis.com/auth/gmail.modify",
        validation_alias=AliasChoices("GMAIL_SEND_SCOPES", "JARVIS_GMAIL_SEND_SCOPES"),
    )
    gmail_max_results: int = Field(
        default=5,
        ge=1,
        le=50,
        validation_alias=AliasChoices("GMAIL_MAX_RESULTS", "JARVIS_GMAIL_MAX_RESULTS"),
    )
    reminders_database_path: Path = Field(
        default=DEFAULT_CONFIG_PATHS.data_path / "jarvis_reminders.db",
        validation_alias=AliasChoices("REMINDERS_DATABASE_PATH", "JARVIS_REMINDERS_DATABASE_PATH"),
    )
    calendar_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("CALENDAR_ENABLED", "JARVIS_CALENDAR_ENABLED"),
    )
    calendar_client_secret_path: Path = Field(
        default=DEFAULT_CONFIG_PATHS.credentials_path / "google_client_secret.json",
        validation_alias=AliasChoices("CALENDAR_CLIENT_SECRET_PATH", "JARVIS_CALENDAR_CLIENT_SECRET_PATH"),
    )
    calendar_token_path: Path = Field(
        default=DEFAULT_CONFIG_PATHS.credentials_path / "token_calendar.json",
        validation_alias=AliasChoices("CALENDAR_TOKEN_PATH", "JARVIS_CALENDAR_TOKEN_PATH"),
    )
    calendar_scopes: str = Field(
        default="https://www.googleapis.com/auth/calendar.readonly",
        validation_alias=AliasChoices("CALENDAR_SCOPES", "JARVIS_CALENDAR_SCOPES"),
    )
    calendar_create_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("CALENDAR_CREATE_ENABLED", "JARVIS_CALENDAR_CREATE_ENABLED"),
    )
    calendar_write_scopes: str = Field(
        default="https://www.googleapis.com/auth/calendar.events",
        validation_alias=AliasChoices("CALENDAR_WRITE_SCOPES", "JARVIS_CALENDAR_WRITE_SCOPES"),
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
    vision_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("VISION_ENABLED", "JARVIS_VISION_ENABLED"),
    )
    screenshot_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("SCREENSHOT_ENABLED", "JARVIS_SCREENSHOT_ENABLED"),
    )
    ocr_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("OCR_ENABLED", "JARVIS_OCR_ENABLED"),
    )
    screenshot_save_dir: Path = Field(
        default=DEFAULT_CONFIG_PATHS.logs_path / "screenshots",
        validation_alias=AliasChoices("SCREENSHOT_SAVE_DIR", "JARVIS_SCREENSHOT_SAVE_DIR"),
    )
    ocr_provider: str = Field(
        default="tesseract",
        validation_alias=AliasChoices("OCR_PROVIDER", "JARVIS_OCR_PROVIDER"),
    )
    ocr_max_output_chars: int = Field(
        default=4000,
        ge=1,
        le=100_000,
        validation_alias=AliasChoices("OCR_MAX_OUTPUT_CHARS", "JARVIS_OCR_MAX_OUTPUT_CHARS"),
    )
    openai_vision_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("OPENAI_VISION_ENABLED", "JARVIS_OPENAI_VISION_ENABLED"),
    )
    openai_vision_model: str = Field(
        default="gpt-4o-mini",
        validation_alias=AliasChoices("OPENAI_VISION_MODEL", "JARVIS_OPENAI_VISION_MODEL"),
    )
    openai_vision_max_image_bytes: int = Field(
        default=5_000_000,
        ge=1024,
        le=50_000_000,
        validation_alias=AliasChoices(
            "OPENAI_VISION_MAX_IMAGE_BYTES",
            "JARVIS_OPENAI_VISION_MAX_IMAGE_BYTES",
        ),
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

    @field_validator("startup_app_name")
    @classmethod
    def normalize_startup_app_name(cls, value: str) -> str:
        cleaned = " ".join(value.strip().split())
        if not cleaned:
            raise ValueError("Startup app name cannot be empty.")
        return cleaned

    @field_validator("signing_cert_path", "signing_timestamp_url", "signing_description")
    @classmethod
    def normalize_signing_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("app_version")
    @classmethod
    def normalize_app_version(cls, value: str) -> str:
        return normalize_version(value)

    @field_validator("runtime_mode")
    @classmethod
    def normalize_runtime_mode(cls, value: str) -> str:
        cleaned = value.strip().lower()
        allowed = {"source", "packaged"}
        if cleaned not in allowed:
            raise ValueError(f"Unsupported runtime mode: {value}")
        return cleaned

    @field_validator("wake_provider")
    @classmethod
    def normalize_wake_provider(cls, value: str) -> str:
        cleaned = value.strip().lower().replace("-", "_")
        allowed = {"openwakeword", "whisper_fuzzy"}
        if cleaned not in allowed:
            raise ValueError(f"Unsupported wake provider: {value}")
        return cleaned

    @field_validator("wake_fallback_provider")
    @classmethod
    def normalize_wake_fallback_provider(cls, value: str) -> str:
        cleaned = value.strip().lower().replace("-", "_")
        allowed = {"manual", "whisper_fuzzy"}
        if cleaned not in allowed:
            raise ValueError(f"Unsupported wake fallback provider: {value}")
        return cleaned

    @field_validator("log_dir")
    @classmethod
    def expand_log_dir(cls, value: Path) -> Path:
        return _resolve_config_path(value)

    @field_validator("memory_database_path")
    @classmethod
    def expand_memory_database_path(cls, value: Path) -> Path:
        return _resolve_config_path(value)

    @field_validator("reminders_database_path")
    @classmethod
    def expand_reminders_database_path(cls, value: Path) -> Path:
        return _resolve_config_path(value)

    @field_validator("calendar_client_secret_path", "calendar_token_path", "gmail_client_secret_path", "gmail_token_path")
    @classmethod
    def expand_calendar_paths(cls, value: Path) -> Path:
        return _resolve_config_path(value)

    @field_validator("speech_to_text_provider", "tts_provider", "whisper_device", "whisper_compute_type")
    @classmethod
    def normalize_provider_name(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not cleaned:
            raise ValueError("Provider name cannot be empty.")
        return cleaned

    @field_validator("voice_input_device")
    @classmethod
    def normalize_voice_input_device(cls, value: str) -> str:
        return value.strip()

    @field_validator("fast_voice_activation")
    @classmethod
    def normalize_fast_voice_activation(cls, value: str) -> str:
        cleaned = value.strip().lower().replace("-", "_")
        aliases = {"push_to_talk": "enter", "ptt": "enter", "immediate": "direct"}
        cleaned = aliases.get(cleaned, cleaned)
        if cleaned not in {"enter", "clap", "direct"}:
            raise ValueError(f"Unsupported fast voice activation: {value}")
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

    @field_validator("openwakeword_model")
    @classmethod
    def normalize_openwakeword_model(cls, value: str) -> str:
        return value.strip()

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

    @field_validator("openai_vision_model")
    @classmethod
    def normalize_openai_vision_model(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("OpenAI vision model cannot be empty.")
        return cleaned

    @field_validator("voice_response_mode")
    @classmethod
    def normalize_voice_response_mode(cls, value: str) -> str:
        cleaned = value.strip().lower().replace("-", "_")
        allowed = {"concise", "normal"}
        if cleaned not in allowed:
            raise ValueError(f"Unsupported voice response mode: {value}")
        return cleaned

    @field_validator(
        "voice_concise_instruction",
        "voice_loop_standby_message",
        "fast_voice_wake_only_response",
        "fast_voice_empty_audio_response",
    )
    @classmethod
    def normalize_voice_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Voice text setting cannot be empty.")
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
    def voice_command_reject_phrase_list(self) -> list[str]:
        phrases = [item.strip().lower() for item in self.voice_command_reject_phrases.replace("\n", ",").split(",")]
        return [phrase for phrase in phrases if phrase]

    @property
    def voice_command_incomplete_phrase_list(self) -> list[str]:
        phrases = [
            item.strip().lower()
            for item in self.voice_command_incomplete_phrases.replace("\n", ",").split(",")
        ]
        return [phrase for phrase in phrases if phrase]

    @property
    def voice_repair_incomplete_phrase_list(self) -> list[str]:
        phrases = [
            item.strip().lower()
            for item in self.voice_repair_incomplete_phrases.replace("\n", ",").split(",")
        ]
        return [phrase for phrase in phrases if phrase]

    @property
    def voice_repair_rule_pairs(self) -> list[tuple[str, str]]:
        rules: list[tuple[str, str]] = []
        for raw_rule in self.voice_repair_rules.replace("\n", ";").split(";"):
            if "=>" not in raw_rule:
                continue
            source, target = raw_rule.split("=>", 1)
            source = " ".join(source.strip().split())
            target = " ".join(target.strip().split())
            if source and target:
                try:
                    target = target.format(weather_default_city=self.weather_default_city)
                except (KeyError, ValueError):
                    pass
                rules.append((source, target))
        return rules

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
    def has_gmail_client_secret(self) -> bool:
        return self.gmail_client_secret_path.exists()

    @property
    def has_gmail_token(self) -> bool:
        return self.gmail_token_path.exists()

    @property
    def has_calendar_client_secret(self) -> bool:
        return self.calendar_client_secret_path.exists()

    @property
    def has_calendar_token(self) -> bool:
        return self.calendar_token_path.exists()

    @property
    def calendar_scopes_list(self) -> list[str]:
        raw = self.calendar_scopes.strip()
        if not raw:
            return []

        scopes: list[str] = []
        for item in raw.replace("\n", ",").split(","):
            cleaned = item.strip()
            if cleaned and cleaned not in scopes:
                scopes.append(cleaned)
        return scopes

    @property
    def gmail_scopes_list(self) -> list[str]:
        raw = self.gmail_scopes.strip()
        if not raw:
            return []

        scopes: list[str] = []
        for item in raw.replace("\n", ",").split(","):
            cleaned = item.strip()
            if cleaned and cleaned not in scopes:
                scopes.append(cleaned)
        return scopes

    @property
    def gmail_auth_scopes_list(self) -> list[str]:
        scopes = self.gmail_scopes_list[:]
        if self.gmail_draft_enabled:
            for scope in self.gmail_draft_scopes_list:
                if scope not in scopes:
                    scopes.append(scope)
        if self.gmail_send_draft_enabled:
            for scope in self.gmail_send_scopes_list:
                if scope not in scopes:
                    scopes.append(scope)
        return scopes

    @property
    def gmail_draft_scopes_list(self) -> list[str]:
        raw = self.gmail_draft_scopes.strip()
        if not raw:
            return []

        scopes: list[str] = []
        for item in raw.replace("\n", ",").split(","):
            cleaned = item.strip()
            if cleaned and cleaned not in scopes:
                scopes.append(cleaned)
        return scopes

    @property
    def gmail_send_scopes_list(self) -> list[str]:
        raw = self.gmail_send_scopes.strip()
        if not raw:
            return []

        scopes: list[str] = []
        for item in raw.replace("\n", ",").split(","):
            cleaned = item.strip()
            if cleaned and cleaned not in scopes:
                scopes.append(cleaned)
        return scopes

    @property
    def calendar_write_scopes_list(self) -> list[str]:
        raw = self.calendar_write_scopes.strip()
        if not raw:
            return []

        scopes: list[str] = []
        for item in raw.replace("\n", ",").split(","):
            cleaned = item.strip()
            if cleaned and cleaned not in scopes:
                scopes.append(cleaned)
        return scopes

    @property
    def calendar_auth_scopes_list(self) -> list[str]:
        scopes = self.calendar_scopes_list[:]
        if self.calendar_create_enabled:
            for scope in self.calendar_write_scopes_list:
                if scope not in scopes:
                    scopes.append(scope)
        return scopes

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


def _resolve_config_path(value: Path) -> Path:
    expanded = Path(os.path.expandvars(str(value))).expanduser()
    if not expanded.is_absolute():
        expanded = DEFAULT_CONFIG_PATHS.config_root / expanded
    return expanded.resolve()
