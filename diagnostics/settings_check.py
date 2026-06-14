from __future__ import annotations

from dataclasses import dataclass, field

from config.settings import AppSettings
from jarvis_runtime.runtime_paths import resolve_runtime_paths
from jarvis_runtime.settings_editor import (
    build_redacted_settings_snapshot,
    build_safe_settings_snapshot,
)


@dataclass(frozen=True)
class SettingsCheckReport:
    runtime_mode: str
    config_root: str
    env_path: str
    safe_settings: list[tuple[str, str]] = field(default_factory=list)
    redacted_settings: list[tuple[str, str]] = field(default_factory=list)


def run_settings_check(settings: AppSettings) -> SettingsCheckReport:
    runtime_paths = resolve_runtime_paths(settings)
    safe_items = [(spec.label, value) for spec, value in build_safe_settings_snapshot(settings)]
    redacted_items = build_redacted_settings_snapshot(settings)
    return SettingsCheckReport(
        runtime_mode=runtime_paths.runtime_mode,
        config_root=str(runtime_paths.config_root),
        env_path=str(runtime_paths.env_path),
        safe_settings=safe_items,
        redacted_settings=redacted_items,
    )


def format_settings_check_report(report: SettingsCheckReport) -> str:
    lines = [
        "Jarvis Settings Check",
        "=====================",
        f"Runtime mode: {report.runtime_mode}",
        f"Config root: {report.config_root}",
        f".env path: {report.env_path}",
        "",
        "Safe editable settings:",
    ]
    lines.extend(f"- {label}: {value}" for label, value in report.safe_settings)
    lines.extend(["", "Redacted settings:"])
    lines.extend(f"- {label}: {value}" for label, value in report.redacted_settings)
    return "\n".join(lines)
