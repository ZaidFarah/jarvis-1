from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class AppSettings(BaseSettings):
    """Runtime settings for the Phase 1 Jarvis desktop shell."""

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


def load_settings() -> AppSettings:
    return AppSettings()
