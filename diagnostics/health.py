from __future__ import annotations

import platform
import sys
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

from config.settings import AppSettings, PROJECT_ROOT


_HEALTH_LOG_SINK_ID: int | None = None
_HEALTH_LOG_FILE: Path | None = None


@dataclass(frozen=True)
class HealthCheckReport:
    python_version: str
    os_platform: str
    project_path: Path
    openai_enabled: bool
    openai_key_detected: bool
    openai_model: str
    tts_enabled: bool
    tts_provider: str
    stt_provider: str
    stt_model: str
    stt_device: str
    wake_phrase: str
    wake_alias_count: int
    wake_match_threshold: float
    voice_loop_enabled: bool
    memory_enabled: bool
    memory_database_path: Path
    reminders_enabled: bool
    reminders_database_path: Path
    reminders_check_enabled: bool
    reminders_check_interval_seconds: int
    reminders_watch_enabled: bool
    reminders_watch_speak: bool
    weather_enabled: bool
    weather_default_city: str
    weather_key_detected: bool
    notifications_enabled: bool
    notification_provider: str
    app_launcher_enabled: bool
    website_launcher_enabled: bool
    file_access_enabled: bool
    file_read_enabled: bool
    calendar_enabled: bool
    calendar_client_secret_detected: bool
    calendar_token_detected: bool
    gmail_enabled: bool
    gmail_client_secret_detected: bool
    gmail_token_detected: bool
    vision_enabled: bool
    screenshot_enabled: bool
    ocr_enabled: bool
    openai_vision_enabled: bool
    agent_enabled: bool
    agent_experimental: bool
    log_file: Path
    sections: list[tuple[str, list[tuple[str, str]]]] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        return True


class HealthService:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.log_file = self.settings.log_dir / "health.log"
        self.health_logger = logger.bind(health=True)
        self._ensure_log_sink()

    def run_check(self) -> HealthCheckReport:
        report = HealthCheckReport(
            python_version=platform.python_version(),
            os_platform=platform.platform(),
            project_path=PROJECT_ROOT,
            openai_enabled=self.settings.openai_enabled,
            openai_key_detected=self.settings.has_openai_api_key,
            openai_model=self.settings.openai_model,
            tts_enabled=self.settings.tts_enabled,
            tts_provider=self.settings.tts_provider,
            stt_provider=self.settings.speech_to_text_provider,
            stt_model=self.settings.whisper_model,
            stt_device=self.settings.whisper_device,
            wake_phrase=self.settings.wake_phrase,
            wake_alias_count=len(self.settings.wake_alias_list),
            wake_match_threshold=self.settings.wake_match_threshold,
            voice_loop_enabled=self.settings.voice_loop_enabled,
            memory_enabled=self.settings.memory_enabled,
            memory_database_path=self.settings.memory_database_path,
            reminders_enabled=self.settings.reminders_enabled,
            reminders_database_path=self.settings.reminders_database_path,
            reminders_check_enabled=self.settings.reminders_check_enabled,
            reminders_check_interval_seconds=self.settings.reminders_check_interval_seconds,
            reminders_watch_enabled=self.settings.reminders_watch_enabled,
            reminders_watch_speak=self.settings.reminders_watch_speak,
            weather_enabled=self.settings.weather_enabled,
            weather_default_city=self.settings.weather_default_city,
            weather_key_detected=self.settings.has_weather_api_key,
            notifications_enabled=self.settings.notifications_enabled,
            notification_provider=self.settings.notification_provider,
            app_launcher_enabled=self.settings.app_launcher_enabled,
            website_launcher_enabled=self.settings.website_launcher_enabled,
            file_access_enabled=self.settings.file_access_enabled,
            file_read_enabled=self.settings.file_read_enabled,
            calendar_enabled=self.settings.calendar_enabled,
            calendar_client_secret_detected=self.settings.has_calendar_client_secret,
            calendar_token_detected=self.settings.has_calendar_token,
            gmail_enabled=self.settings.gmail_enabled,
            gmail_client_secret_detected=self.settings.has_gmail_client_secret,
            gmail_token_detected=self.settings.has_gmail_token,
            vision_enabled=self.settings.vision_enabled,
            screenshot_enabled=self.settings.screenshot_enabled,
            ocr_enabled=self.settings.ocr_enabled,
            openai_vision_enabled=self.settings.openai_vision_enabled,
            agent_enabled=self.settings.agent_enabled,
            agent_experimental=self.settings.agent_experimental,
            log_file=self.log_file,
            sections=self._build_sections(),
        )
        self.health_logger.info(
            "Health check completed openai={} tts={} stt={} weather={} calendar={} gmail={} vision={} agent={}",
            report.openai_enabled,
            report.tts_provider,
            report.stt_provider,
            report.weather_enabled,
            report.calendar_enabled,
            report.gmail_enabled,
            report.vision_enabled,
            report.agent_enabled,
        )
        return report

    def _build_sections(self) -> list[tuple[str, list[tuple[str, str]]]]:
        settings = self.settings
        return [
            (
                "System",
                [
                    ("Python version", platform.python_version()),
                    ("OS/platform", platform.platform()),
                    ("Project path", str(PROJECT_ROOT)),
                ],
            ),
            (
                "OpenAI",
                [
                    ("Enabled", _yes_no(settings.openai_enabled)),
                    ("API key detected", _yes_no(settings.has_openai_api_key)),
                    ("Model", settings.openai_model),
                ],
            ),
            (
                "Voice",
                [
                    ("TTS enabled", _yes_no(settings.tts_enabled)),
                    ("TTS provider", settings.tts_provider),
                    ("STT provider", settings.speech_to_text_provider),
                    ("STT model", settings.whisper_model),
                    ("STT device", settings.whisper_device),
                    ("Wake phrase", settings.wake_phrase),
                    ("Wake aliases", str(len(settings.wake_alias_list))),
                    ("Wake threshold", f"{settings.wake_match_threshold:.2f}"),
                    ("Voice loop enabled", _yes_no(settings.voice_loop_enabled)),
                ],
            ),
            (
                "Memory",
                [
                    ("Enabled", _yes_no(settings.memory_enabled)),
                    ("Database path", str(settings.memory_database_path)),
                ],
            ),
            (
                "Reminders",
                [
                    ("Enabled", _yes_no(settings.reminders_enabled)),
                    ("Database path", str(settings.reminders_database_path)),
                    ("Check enabled", _yes_no(settings.reminders_check_enabled)),
                    ("Check interval", f"{settings.reminders_check_interval_seconds}s"),
                    ("Watcher enabled", _yes_no(settings.reminders_watch_enabled)),
                    ("Watcher speak", _yes_no(settings.reminders_watch_speak)),
                ],
            ),
            (
                "Weather",
                [
                    ("Enabled", _yes_no(settings.weather_enabled)),
                    ("Default city", settings.weather_default_city),
                    ("API key detected", _yes_no(settings.has_weather_api_key)),
                ],
            ),
            (
                "Notifications",
                [
                    ("Enabled", _yes_no(settings.notifications_enabled)),
                    ("Provider", settings.notification_provider),
                ],
            ),
            (
                "Launchers",
                [
                    ("App launcher enabled", _yes_no(settings.app_launcher_enabled)),
                    ("Website launcher enabled", _yes_no(settings.website_launcher_enabled)),
                ],
            ),
            (
                "Files",
                [
                    ("File access enabled", _yes_no(settings.file_access_enabled)),
                    ("File read enabled", _yes_no(settings.file_read_enabled)),
                ],
            ),
            (
                "Calendar",
                [
                    ("Enabled", _yes_no(settings.calendar_enabled)),
                    ("Client secret detected", _yes_no(settings.has_calendar_client_secret)),
                    ("Token detected", _yes_no(settings.has_calendar_token)),
                ],
            ),
            (
                "Gmail",
                [
                    ("Enabled", _yes_no(settings.gmail_enabled)),
                    ("Client secret detected", _yes_no(settings.has_gmail_client_secret)),
                    ("Token detected", _yes_no(settings.has_gmail_token)),
                ],
            ),
            (
                "Vision",
                [
                    ("Enabled", _yes_no(settings.vision_enabled)),
                    ("Screenshot enabled", _yes_no(settings.screenshot_enabled)),
                    ("OCR enabled", _yes_no(settings.ocr_enabled)),
                    ("OpenAI vision enabled", _yes_no(settings.openai_vision_enabled)),
                ],
            ),
            (
                "Agent",
                [
                    ("Enabled", _yes_no(settings.agent_enabled)),
                    ("Experimental", _yes_no(settings.agent_experimental)),
                ],
            ),
        ]

    def _ensure_log_sink(self) -> None:
        global _HEALTH_LOG_FILE, _HEALTH_LOG_SINK_ID
        if _HEALTH_LOG_SINK_ID is not None and _HEALTH_LOG_FILE == self.log_file:
            return

        if _HEALTH_LOG_SINK_ID is not None:
            try:
                logger.remove(_HEALTH_LOG_SINK_ID)
            except ValueError:
                pass

        self.settings.log_dir.mkdir(parents=True, exist_ok=True)
        _HEALTH_LOG_SINK_ID = logger.add(
            self.log_file,
            level="DEBUG",
            rotation="1 MB",
            retention="7 days",
            encoding="utf-8",
            backtrace=False,
            diagnose=False,
            filter=lambda record: bool(record["extra"].get("health")),
        )
        _HEALTH_LOG_FILE = self.log_file


def format_health_check_report(report: HealthCheckReport) -> str:
    lines = [
        "Jarvis Health Check",
        "===================",
    ]
    for section_name, entries in report.sections:
        lines.extend(["", section_name])
        lines.extend(f"  {label}: {value}" for label, value in entries)
    lines.extend(["", f"Log file: {report.log_file}"])
    return "\n".join(lines)


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
