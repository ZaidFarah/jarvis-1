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
        default="pyttsx3",
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

    @field_validator("speech_to_text_provider", "tts_provider", "whisper_device", "whisper_compute_type")
    @classmethod
    def normalize_provider_name(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not cleaned:
            raise ValueError("Provider name cannot be empty.")
        return cleaned

    @field_validator("tts_voice_name")
    @classmethod
    def normalize_tts_voice_name(cls, value: str) -> str:
        return value.strip()

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


def load_settings() -> AppSettings:
    return AppSettings()
