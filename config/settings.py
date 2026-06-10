from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class AppSettings(BaseSettings):
    """Runtime settings for the Jarvis desktop shell."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_prefix="JARVIS_",
        extra="ignore",
    )

    app_name: str = "Jarvis"
    environment: str = "development"
    log_level: str = "INFO"
    log_dir: Path = Field(default=PROJECT_ROOT / "logs")
    window_width: int = Field(default=460, ge=360, le=1200)
    window_height: int = Field(default=620, ge=420, le=1400)
    always_on_top: bool = True
    minimize_to_tray: bool = True
    voice_sample_rate: int = Field(default=16000, ge=8000, le=48000)
    voice_channels: int = Field(default=1, ge=1, le=2)
    voice_microphone_test_seconds: float = Field(default=2.0, ge=0.25, le=10.0)
    voice_vad_enabled: bool = True
    voice_vad_threshold: float = Field(default=0.01, ge=0.0, le=1.0)
    speech_to_text_provider: str = "interface-only"
    text_to_speech_provider: str = "pyttsx3"

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

    @field_validator("speech_to_text_provider", "text_to_speech_provider")
    @classmethod
    def normalize_provider_name(cls, value: str) -> str:
        return value.strip().lower()


def load_settings() -> AppSettings:
    return AppSettings()
