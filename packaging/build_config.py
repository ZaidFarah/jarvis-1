from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from config.settings import PROJECT_ROOT


@dataclass(frozen=True)
class BuildConfig:
    app_name: str
    entry_point: Path
    icon_path: Path
    build_script_name: str
    runtime_mode: str


def default_build_config() -> BuildConfig:
    return BuildConfig(
        app_name="Jarvis",
        entry_point=PROJECT_ROOT / "main.py",
        icon_path=PROJECT_ROOT / "assets" / "jarvis.ico",
        build_script_name="build_exe.bat",
        runtime_mode="source",
    )
