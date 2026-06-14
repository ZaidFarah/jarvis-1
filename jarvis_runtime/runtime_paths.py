from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from config.settings import AppSettings, PROJECT_ROOT
from jarvis_runtime.config_bootstrap import get_runtime_config_paths


@dataclass(frozen=True)
class RuntimePaths:
    runtime_mode: str
    project_root: Path
    runtime_root: Path
    config_root: Path
    executable_path: Path
    env_path: Path
    logs_path: Path
    data_path: Path
    credentials_path: Path
    assets_path: Path


def resolve_runtime_paths(
    settings: AppSettings | None = None,
    *,
    runtime_mode: str | None = None,
    base_dir: Path | None = None,
    executable_path: Path | None = None,
    appdata_base: Path | None = None,
) -> RuntimePaths:
    settings = settings or AppSettings(_env_file=None)
    detected_mode = _detect_runtime_mode(settings, runtime_mode)
    project_root = PROJECT_ROOT
    if base_dir is not None:
        runtime_root = base_dir.expanduser().resolve()
    elif executable_path is not None:
        runtime_root = executable_path.expanduser().resolve().parent
    elif detected_mode == "packaged" or getattr(sys, "frozen", False):
        runtime_root = Path(sys.executable).resolve().parent
    else:
        runtime_root = project_root

    executable = executable_path.expanduser().resolve() if executable_path is not None else Path(sys.executable).resolve()
    config_paths = get_runtime_config_paths(detected_mode, project_root, appdata_base=appdata_base)
    return RuntimePaths(
        runtime_mode=detected_mode,
        project_root=project_root,
        runtime_root=runtime_root,
        config_root=config_paths.config_root,
        executable_path=executable,
        env_path=config_paths.env_path,
        logs_path=config_paths.logs_path,
        data_path=config_paths.data_path,
        credentials_path=config_paths.credentials_path,
        assets_path=_resolve_assets_path(runtime_root),
    )


def format_runtime_check_report(paths: RuntimePaths) -> str:
    lines = [
        "Jarvis Runtime Check",
        "====================",
        f"Runtime mode: {paths.runtime_mode}",
        f"Project root: {paths.project_root}",
        f"Runtime root: {paths.runtime_root}",
        f"Config root: {paths.config_root}",
        f"Executable: {paths.executable_path}",
        f".env path: {paths.env_path}",
        f"logs path: {paths.logs_path}",
        f"data path: {paths.data_path}",
        f"credentials path: {paths.credentials_path}",
        f"assets path: {paths.assets_path}",
    ]
    return "\n".join(lines)


def _detect_runtime_mode(settings: AppSettings, override_mode: str | None = None) -> str:
    if override_mode:
        cleaned_override = override_mode.strip().lower()
        if cleaned_override in {"source", "packaged"}:
            return cleaned_override
    if getattr(sys, "frozen", False):
        return "packaged"
    cleaned = settings.runtime_mode.strip().lower()
    if cleaned in {"source", "packaged"}:
        return cleaned
    return "source"


def _resolve_assets_path(runtime_root: Path) -> Path:
    if getattr(sys, "frozen", False):
        bundle_root = Path(getattr(sys, "_MEIPASS", runtime_root)).resolve()
        bundled_assets = bundle_root / "assets"
        if bundled_assets.exists():
            return bundled_assets
    return runtime_root / "assets"
