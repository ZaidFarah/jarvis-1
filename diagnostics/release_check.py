from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Literal

from config.settings import AppSettings, PROJECT_ROOT
from diagnostics.health import HealthService, format_health_check_report
from jarvis_runtime.runtime_paths import format_runtime_check_report, resolve_runtime_paths


ReleaseStatus = Literal["PASS", "WARN", "FAIL"]


@dataclass(frozen=True)
class ReleaseCheckItem:
    name: str
    status: ReleaseStatus
    message: str
    details: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReleaseCheckReport:
    items: list[ReleaseCheckItem]

    @property
    def overall_status(self) -> ReleaseStatus:
        statuses = {item.status for item in self.items}
        if "FAIL" in statuses:
            return "FAIL"
        if "WARN" in statuses:
            return "WARN"
        return "PASS"

    @property
    def is_successful(self) -> bool:
        return self.overall_status != "FAIL"


def run_release_check(
    settings: AppSettings | None = None,
    *,
    project_root: Path | None = None,
    tracked_files: Iterable[str] | None = None,
) -> ReleaseCheckReport:
    root = (project_root or PROJECT_ROOT).expanduser().resolve()
    settings = settings or AppSettings(_env_file=None)
    tracked, tracked_error = _resolve_tracked_files(root, tracked_files)

    items = [
        _tests_command_reminder(),
        _file_exists_check("Build script", root / "build_exe.bat", "build_exe.bat exists.", "build_exe.bat is missing."),
        _packaged_exe_check(root),
        _tracked_secret_check(".env not tracked", tracked, tracked_error, _is_env_file, ".env is not tracked."),
        _tracked_secret_check("credentials not tracked", tracked, tracked_error, _is_credentials_path, "credentials/ is not tracked."),
        _tracked_secret_check("tokens not tracked", tracked, tracked_error, _is_token_path, "Token files are not tracked."),
        _tracked_secret_check("logs not tracked", tracked, tracked_error, _is_log_path, "logs/ is not tracked."),
        _tracked_secret_check("data DB files not tracked", tracked, tracked_error, _is_data_db_path, "data/*.db is not tracked."),
        _source_runtime_check(settings),
        _source_health_check(settings),
        _required_scripts_check(root),
        _startup_commands_check(root),
        _readme_sections_check(root),
    ]
    return ReleaseCheckReport(items=items)


def format_release_check_report(report: ReleaseCheckReport) -> str:
    lines = [
        "Jarvis Release Check",
        "====================",
    ]
    for item in report.items:
        lines.append(f"{item.status} | {item.name}: {item.message}")
        lines.extend(f"  - {detail}" for detail in item.details)
    lines.extend(["", f"Final release readiness: {report.overall_status}"])
    return "\n".join(lines)


def _tests_command_reminder() -> ReleaseCheckItem:
    return ReleaseCheckItem(
        name="Tests command reminder",
        status="PASS",
        message="Run `python -m pytest` before release.",
    )


def _file_exists_check(name: str, path: Path, pass_message: str, fail_message: str) -> ReleaseCheckItem:
    if path.is_file():
        return ReleaseCheckItem(name=name, status="PASS", message=pass_message, details=[str(path)])
    return ReleaseCheckItem(name=name, status="FAIL", message=fail_message, details=[str(path)])


def _packaged_exe_check(root: Path) -> ReleaseCheckItem:
    exe_path = root / "dist" / "Jarvis" / "Jarvis.exe"
    if exe_path.is_file():
        return ReleaseCheckItem(
            name="Packaged EXE",
            status="PASS",
            message="dist/Jarvis/Jarvis.exe exists.",
            details=[str(exe_path)],
        )
    return ReleaseCheckItem(
        name="Packaged EXE",
        status="WARN",
        message="dist/Jarvis/Jarvis.exe is not present. Build before creating a release ZIP.",
        details=[str(exe_path)],
    )


def _tracked_secret_check(
    name: str,
    tracked_files: list[str],
    tracked_error: str | None,
    matcher,
    pass_message: str,
) -> ReleaseCheckItem:
    if tracked_error is not None:
        return ReleaseCheckItem(
            name=name,
            status="FAIL",
            message="Could not inspect tracked files.",
            details=[tracked_error],
        )

    matches = [path for path in tracked_files if matcher(path)]
    if not matches:
        return ReleaseCheckItem(name=name, status="PASS", message=pass_message)
    return ReleaseCheckItem(
        name=name,
        status="FAIL",
        message="Tracked sensitive or generated files were found.",
        details=_limited_paths(matches),
    )


def _source_runtime_check(settings: AppSettings) -> ReleaseCheckItem:
    try:
        source_settings = settings.model_copy(update={"runtime_mode": "source"})
        report = resolve_runtime_paths(source_settings, runtime_mode="source")
        text = format_runtime_check_report(report)
    except Exception as exc:
        return ReleaseCheckItem(
            name="Source runtime-check",
            status="FAIL",
            message="Source runtime check failed.",
            details=[_format_error(exc)],
        )

    if report.runtime_mode != "source" or "Runtime mode: source" not in text:
        return ReleaseCheckItem(
            name="Source runtime-check",
            status="FAIL",
            message="Source runtime check did not report source mode.",
            details=[text],
        )
    return ReleaseCheckItem(
        name="Source runtime-check",
        status="PASS",
        message="Source runtime check reports source mode.",
        details=[f"Config root: {report.config_root}"],
    )


def _source_health_check(settings: AppSettings) -> ReleaseCheckItem:
    try:
        source_settings = settings.model_copy(update={"runtime_mode": "source"})
        report = HealthService(source_settings).run_check()
        text = format_health_check_report(report)
    except Exception as exc:
        return ReleaseCheckItem(
            name="Source health-check",
            status="FAIL",
            message="Source health check failed.",
            details=[_format_error(exc)],
        )

    if not report.is_successful or "System" not in text:
        return ReleaseCheckItem(
            name="Source health-check",
            status="FAIL",
            message="Source health check did not produce the expected report.",
            details=[text],
        )
    return ReleaseCheckItem(
        name="Source health-check",
        status="PASS",
        message="Source health check runs successfully.",
        details=[f"Log file: {report.log_file}"],
    )


def _required_scripts_check(root: Path) -> ReleaseCheckItem:
    required = ["run_jarvis.bat", "run_jarvis_console.bat", "test_packaged_app.bat"]
    missing = [script for script in required if not (root / script).is_file()]
    if not missing:
        return ReleaseCheckItem(
            name="Packaged smoke scripts",
            status="PASS",
            message="Packaged run and smoke scripts exist.",
            details=required,
        )
    return ReleaseCheckItem(
        name="Packaged smoke scripts",
        status="FAIL",
        message="Required packaged scripts are missing.",
        details=missing,
    )


def _startup_commands_check(root: Path) -> ReleaseCheckItem:
    main_path = root / "main.py"
    try:
        text = main_path.read_text(encoding="utf-8")
    except Exception as exc:
        return ReleaseCheckItem(
            name="Startup CLI commands",
            status="FAIL",
            message="Could not inspect main.py.",
            details=[_format_error(exc)],
        )

    required = ["--startup-check", "--startup-enable", "--startup-disable"]
    missing = [flag for flag in required if flag not in text]
    if not missing:
        return ReleaseCheckItem(
            name="Startup CLI commands",
            status="PASS",
            message="Startup check, enable, and disable commands are present.",
            details=required,
        )
    return ReleaseCheckItem(
        name="Startup CLI commands",
        status="FAIL",
        message="Startup CLI commands are missing.",
        details=missing,
    )


def _readme_sections_check(root: Path) -> ReleaseCheckItem:
    readme_path = root / "README.md"
    try:
        text = readme_path.read_text(encoding="utf-8")
    except Exception as exc:
        return ReleaseCheckItem(
            name="README setup/run/build sections",
            status="FAIL",
            message="Could not inspect README.md.",
            details=[_format_error(exc)],
        )

    required = {
        "setup": "## Setup",
        "run": "## Run",
        "build": "## Packaging",
    }
    missing = [label for label, marker in required.items() if marker not in text]
    if not missing:
        return ReleaseCheckItem(
            name="README setup/run/build sections",
            status="PASS",
            message="README includes setup, run, and build sections.",
            details=list(required.values()),
        )
    return ReleaseCheckItem(
        name="README setup/run/build sections",
        status="FAIL",
        message="README is missing release-critical sections.",
        details=missing,
    )


def _resolve_tracked_files(root: Path, tracked_files: Iterable[str] | None) -> tuple[list[str], str | None]:
    if tracked_files is not None:
        return _normalize_paths(tracked_files), None

    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception as exc:
        return [], _format_error(exc)
    return _normalize_paths(result.stdout.splitlines()), None


def _normalize_paths(paths: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    for path in paths:
        cleaned = path.strip().replace("\\", "/").strip("/")
        if cleaned:
            normalized.append(cleaned)
    return normalized


def _is_env_file(path: str) -> bool:
    return path == ".env" or path.endswith("/.env")


def _is_credentials_path(path: str) -> bool:
    parts = path.lower().split("/")
    return "credentials" in parts


def _is_token_path(path: str) -> bool:
    parts = path.lower().split("/")
    filename = parts[-1]
    return (
        "tokens" in parts
        or filename in {"token", "token.json", "tokens.json"}
        or filename.startswith("token_")
        or filename.startswith("token-")
        or (filename.endswith(".json") and "token" in filename)
    )


def _is_log_path(path: str) -> bool:
    parts = path.lower().split("/")
    return "logs" in parts


def _is_data_db_path(path: str) -> bool:
    parts = path.lower().split("/")
    return "data" in parts and path.lower().endswith(".db")


def _limited_paths(paths: list[str], limit: int = 8) -> list[str]:
    if len(paths) <= limit:
        return paths
    return [*paths[:limit], f"... {len(paths) - limit} more"]


def _format_error(error: Exception) -> str:
    error_type = type(error).__name__
    message = str(error).strip() or "No error details provided."
    return f"{error_type}: {message}"
