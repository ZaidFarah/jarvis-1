from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


APP_CONFIG_DIR_NAME = "Jarvis"
PACKAGED_ENV_FILE_NAME = "Jarvis.env"
SOURCE_ENV_FILE_NAME = ".env"
ENV_TEMPLATE_FILE_NAME = ".env.example"


@dataclass(frozen=True)
class RuntimeConfigPaths:
    config_root: Path
    env_path: Path
    logs_path: Path
    data_path: Path
    credentials_path: Path


@dataclass(frozen=True)
class ConfigInitResult:
    paths: RuntimeConfigPaths
    template_path: Path
    env_created: bool
    env_already_exists: bool
    created_directories: tuple[Path, ...]


def detect_runtime_mode() -> str:
    return "packaged" if getattr(sys, "frozen", False) else "source"


def resolve_appdata_base(appdata_base: Path | None = None) -> Path:
    if appdata_base is not None:
        return appdata_base.expanduser().resolve()

    raw_appdata = os.environ.get("APPDATA")
    if raw_appdata:
        return Path(raw_appdata).expanduser().resolve()

    return (Path.home() / "AppData" / "Roaming").resolve()


def get_runtime_config_paths(
    runtime_mode: str,
    project_root: Path,
    *,
    appdata_base: Path | None = None,
) -> RuntimeConfigPaths:
    cleaned_mode = runtime_mode.strip().lower()
    if cleaned_mode == "packaged":
        appdata = resolve_appdata_base(appdata_base)
        config_root = appdata / APP_CONFIG_DIR_NAME
        env_path = appdata / PACKAGED_ENV_FILE_NAME
    else:
        config_root = project_root.expanduser().resolve()
        env_path = config_root / SOURCE_ENV_FILE_NAME

    return RuntimeConfigPaths(
        config_root=config_root,
        env_path=env_path,
        logs_path=config_root / "logs",
        data_path=config_root / "data",
        credentials_path=config_root / "credentials",
    )


def initialize_config(
    *,
    appdata_base: Path | None = None,
    template_path: Path | None = None,
) -> ConfigInitResult:
    paths = get_runtime_config_paths("packaged", _resolve_project_root(), appdata_base=appdata_base)
    template = template_path.expanduser().resolve() if template_path is not None else resolve_env_template_path()
    if not template.exists():
        raise FileNotFoundError(template)

    created_directories: list[Path] = []
    for folder in (paths.config_root, paths.logs_path, paths.data_path, paths.credentials_path):
        existed = folder.exists()
        folder.mkdir(parents=True, exist_ok=True)
        if not existed:
            created_directories.append(folder)

    env_already_exists = paths.env_path.exists()
    env_created = False
    if not env_already_exists:
        paths.env_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(template, paths.env_path)
        env_created = True

    return ConfigInitResult(
        paths=paths,
        template_path=template,
        env_created=env_created,
        env_already_exists=env_already_exists,
        created_directories=tuple(created_directories),
    )


def resolve_env_template_path() -> Path:
    bundle_root = Path(getattr(sys, "_MEIPASS", _resolve_project_root())).resolve()
    bundled_template = bundle_root / ENV_TEMPLATE_FILE_NAME
    if bundled_template.exists():
        return bundled_template
    return _resolve_project_root() / ENV_TEMPLATE_FILE_NAME


def format_config_init_report(result: ConfigInitResult) -> str:
    env_status = "created" if result.env_created else "already existed; left unchanged"
    lines = [
        "Jarvis Config Init",
        "==================",
        f"Config root: {result.paths.config_root}",
        f"Env path: {result.paths.env_path}",
        f"logs path: {result.paths.logs_path}",
        f"data path: {result.paths.data_path}",
        f"credentials path: {result.paths.credentials_path}",
        f"Template: {result.template_path}",
        f"Env file: {env_status}",
        "Secrets created: no",
    ]
    return "\n".join(lines)


def format_config_init_error(error: FileNotFoundError) -> str:
    return "\n".join(
        [
            "Jarvis Config Init",
            "==================",
            f"Template not found: {error.filename or error}",
            "Config was not initialized.",
        ]
    )


def _resolve_project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]
