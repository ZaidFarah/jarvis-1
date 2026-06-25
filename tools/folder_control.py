from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

from config.settings import AppSettings, PROJECT_ROOT
from tools.app_launcher import AppLauncher


_FOLDER_CONTROL_LOG_SINK_ID: int | None = None


@dataclass(frozen=True)
class FolderOpenResult:
    enabled: bool
    folder_name: str
    allowed: bool
    configured: bool
    request_attempted: bool
    opened: bool
    resolved_path: str | None
    log_file: Path
    safe_error: str | None = None
    fallback_reason: str | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        return self.enabled and self.opened


@dataclass(frozen=True)
class RecentDownloadsResult:
    enabled: bool
    folder_name: str
    allowed: bool
    configured: bool
    request_attempted: bool
    opened: bool
    resolved_path: str | None
    recent_entries: list[str]
    log_file: Path
    safe_error: str | None = None
    fallback_reason: str | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        return self.enabled and self.request_attempted and self.safe_error is None


class FolderControl:
    """Safe folder opener for whitelisted Windows locations only."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        app_launcher: AppLauncher | None = None,
        startfile: Callable[[str], None] | None = None,
        popen_factory: Callable[..., subprocess.Popen] | None = None,
    ) -> None:
        self.settings = settings
        self.app_launcher = app_launcher or (AppLauncher(settings, popen_factory=popen_factory) if settings.app_launcher_enabled else None)
        self.startfile = startfile or getattr(os, "startfile", None)
        self.popen_factory = popen_factory or subprocess.Popen
        self.log_file = self.settings.log_dir / "folder_control.log"
        self.folder_control_logger = logger.bind(folder_control=True)
        self._ensure_log_sink()

    @property
    def enabled(self) -> bool:
        return self.settings.file_access_enabled

    @property
    def allowed_folders(self) -> dict[str, str]:
        return self.settings.file_access_allowed_folders_map

    def open_folder(self, folder_name: str) -> FolderOpenResult:
        normalized = self._clean_folder_name(folder_name)
        if not self.enabled:
            message = "File access is disabled."
            return self._result(
                normalized,
                allowed=False,
                configured=False,
                request_attempted=False,
                opened=False,
                resolved_path=None,
                safe_error=message,
                fallback_reason=message,
                errors=[message],
            )

        resolved_path = self._resolve_folder_target(normalized)
        if resolved_path is None:
            message = f"Folder '{normalized}' is not allowed."
            return self._result(
                normalized,
                allowed=False,
                configured=False,
                request_attempted=False,
                opened=False,
                resolved_path=None,
                safe_error=message,
                fallback_reason=message,
                errors=[message],
            )

        if not resolved_path.exists() or not resolved_path.is_dir():
            message = f"Folder '{normalized}' could not be found."
            return self._result(
                normalized,
                allowed=True,
                configured=True,
                request_attempted=False,
                opened=False,
                resolved_path=str(resolved_path),
                safe_error=message,
                fallback_reason=message,
                errors=[message],
            )

        if os.name != "nt" or self.startfile is None:
            message = "Folder opening is only available on Windows."
            return self._result(
                normalized,
                allowed=True,
                configured=True,
                request_attempted=False,
                opened=False,
                resolved_path=str(resolved_path),
                safe_error=message,
                fallback_reason=message,
                errors=[message],
            )

        try:
            self.startfile(str(resolved_path))
        except Exception as exc:  # pragma: no cover - defensive boundary
            safe_error = f"{type(exc).__name__}: {exc}"
            return self._result(
                normalized,
                allowed=True,
                configured=True,
                request_attempted=True,
                opened=False,
                resolved_path=str(resolved_path),
                safe_error=safe_error,
                fallback_reason=safe_error,
                errors=[safe_error],
            )

        self.folder_control_logger.info("Opened folder folder={} resolved_path={}", normalized, resolved_path)
        return self._result(
            normalized,
            allowed=True,
            configured=True,
            request_attempted=True,
            opened=True,
            resolved_path=str(resolved_path),
            safe_error=None,
            fallback_reason=None,
            errors=[],
        )

    def open_jarvis_project(self) -> FolderOpenResult:
        if not self.enabled:
            return self._result(
                "jarvis project",
                allowed=True,
                configured=True,
                request_attempted=False,
                opened=False,
                resolved_path=str(PROJECT_ROOT),
                safe_error="File access is disabled.",
                fallback_reason="File access is disabled.",
                errors=["File access is disabled."],
            )
        return self.open_folder("jarvis project")

    def open_jarvis_in_vscode(self) -> FolderOpenResult:
        normalized = "jarvis in vs code"
        if not self.enabled:
            message = "File access is disabled."
            return self._result(
                normalized,
                allowed=True,
                configured=True,
                request_attempted=False,
                opened=False,
                resolved_path=str(PROJECT_ROOT),
                safe_error=message,
                fallback_reason=message,
                errors=[message],
            )
        if self.app_launcher is None:
            message = "App launcher is disabled."
            return self._result(
                normalized,
                allowed=True,
                configured=True,
                request_attempted=False,
                opened=False,
                resolved_path=str(PROJECT_ROOT),
                safe_error=message,
                fallback_reason=message,
                errors=[message],
            )

        resolution = self.app_launcher.resolve_only("vscode")
        if not resolution.resolved_path:
            message = resolution.safe_error or "VS Code is not installed or could not be found."
            return self._result(
                normalized,
                allowed=True,
                configured=True,
                request_attempted=False,
                opened=False,
                resolved_path=str(PROJECT_ROOT),
                safe_error=message,
                fallback_reason=message,
                errors=[message],
            )

        if os.name != "nt":
            message = "VS Code folder opening is only available on Windows."
            return self._result(
                normalized,
                allowed=True,
                configured=True,
                request_attempted=False,
                opened=False,
                resolved_path=str(PROJECT_ROOT),
                safe_error=message,
                fallback_reason=message,
                errors=[message],
            )

        try:
            self.popen_factory([resolution.resolved_path, str(PROJECT_ROOT)], shell=False)
        except Exception as exc:  # pragma: no cover - defensive boundary
            safe_error = f"{type(exc).__name__}: {exc}"
            return self._result(
                normalized,
                allowed=True,
                configured=True,
                request_attempted=True,
                opened=False,
                resolved_path=str(PROJECT_ROOT),
                safe_error=safe_error,
                fallback_reason=safe_error,
                errors=[safe_error],
            )

        self.folder_control_logger.info(
            "Opened project in VS Code resolved_path={} vscode_path={}",
            PROJECT_ROOT,
            resolution.resolved_path,
        )
        return self._result(
            normalized,
            allowed=True,
            configured=True,
            request_attempted=True,
            opened=True,
            resolved_path=str(PROJECT_ROOT),
            safe_error=None,
            fallback_reason=None,
            errors=[],
        )

    def show_recent_downloads(self, limit: int = 5) -> RecentDownloadsResult:
        normalized = "downloads"
        if not self.enabled:
            message = "File access is disabled."
            return self._recent_result(normalized, False, False, False, False, None, [], message, message, [message])

        downloads_path = self._resolve_folder_target("downloads")
        if downloads_path is None:
            message = "Downloads folder is not allowed."
            return self._recent_result(normalized, False, False, False, False, None, [], message, message, [message])

        if not downloads_path.exists() or not downloads_path.is_dir():
            message = "Downloads folder could not be found."
            return self._recent_result(normalized, True, True, False, False, str(downloads_path), [], message, message, [message])

        entries: list[tuple[float, str]] = []
        for path in downloads_path.iterdir():
            try:
                stat = path.stat()
            except OSError:
                continue
            if path.is_file():
                entries.append((stat.st_mtime, path.name))
        entries.sort(key=lambda item: item[0], reverse=True)
        recent_entries = [name for _, name in entries[: max(1, limit)]]
        self.folder_control_logger.info(
            "Listed recent downloads resolved_path={} count={}",
            downloads_path,
            len(recent_entries),
        )
        return self._recent_result(normalized, True, True, True, True, str(downloads_path), recent_entries, None, None, [])

    def _resolve_folder_target(self, folder_name: str) -> Path | None:
        normalized = self._clean_folder_name(folder_name)
        if normalized in self.allowed_folders:
            configured = self.allowed_folders[normalized]
            return self._resolve_configured_path(configured)
        if normalized in {"jarvis project", "my jarvis folder", "jarvis folder"}:
            return PROJECT_ROOT.resolve()
        return None

    @staticmethod
    def _resolve_configured_path(configured_path: str) -> Path | None:
        expanded = os.path.expandvars(configured_path)
        path = Path(expanded).expanduser()
        if not path.exists() or not path.is_dir():
            return None
        return path.resolve()

    def _result(
        self,
        folder_name: str,
        *,
        allowed: bool,
        configured: bool,
        request_attempted: bool,
        opened: bool,
        resolved_path: str | None,
        safe_error: str | None,
        fallback_reason: str | None,
        errors: list[str],
    ) -> FolderOpenResult:
        return FolderOpenResult(
            enabled=self.enabled,
            folder_name=folder_name,
            allowed=allowed,
            configured=configured,
            request_attempted=request_attempted,
            opened=opened,
            resolved_path=resolved_path,
            log_file=self.log_file,
            safe_error=safe_error,
            fallback_reason=fallback_reason,
            errors=errors,
        )

    def _recent_result(
        self,
        folder_name: str,
        allowed: bool,
        configured: bool,
        request_attempted: bool,
        opened: bool,
        resolved_path: str | None,
        recent_entries: list[str],
        safe_error: str | None,
        fallback_reason: str | None,
        errors: list[str],
    ) -> RecentDownloadsResult:
        return RecentDownloadsResult(
            enabled=self.enabled,
            folder_name=folder_name,
            allowed=allowed,
            configured=configured,
            request_attempted=request_attempted,
            opened=opened,
            resolved_path=resolved_path,
            recent_entries=recent_entries,
            log_file=self.log_file,
            safe_error=safe_error,
            fallback_reason=fallback_reason,
            errors=errors,
        )

    def _ensure_log_sink(self) -> None:
        global _FOLDER_CONTROL_LOG_SINK_ID
        if _FOLDER_CONTROL_LOG_SINK_ID is not None:
            return

        self.settings.log_dir.mkdir(parents=True, exist_ok=True)
        _FOLDER_CONTROL_LOG_SINK_ID = logger.add(
            self.log_file,
            level="DEBUG",
            rotation="1 MB",
            retention="7 days",
            encoding="utf-8",
            backtrace=False,
            diagnose=False,
            filter=lambda record: bool(record["extra"].get("folder_control")),
        )

    @staticmethod
    def _clean_folder_name(folder_name: str) -> str:
        return " ".join(folder_name.strip().lower().split())


def format_folder_control_open_report(result: FolderOpenResult) -> str:
    lines = [
        "Jarvis Folder Open",
        "==================",
        f"File access enabled: {'yes' if result.enabled else 'no'}",
        f"Folder: {result.folder_name}",
        f"Allowed: {'yes' if result.allowed else 'no'}",
        f"Configured: {'yes' if result.configured else 'no'}",
        f"Request attempted: {'yes' if result.request_attempted else 'no'}",
        f"Opened: {'yes' if result.opened else 'no'}",
        f"Diagnostic log: {result.log_file}",
    ]
    if result.resolved_path:
        lines.extend(["", f"Resolved path: {result.resolved_path}"])
    if result.fallback_reason:
        lines.extend(["", "Fallback reason:", f"  {result.fallback_reason}"])
    if result.safe_error:
        lines.extend(["", "Error:", f"  {result.safe_error}"])
    return "\n".join(lines)


def format_recent_downloads_report(result: RecentDownloadsResult) -> str:
    lines = [
        "Jarvis Recent Downloads",
        "=======================",
        f"File access enabled: {'yes' if result.enabled else 'no'}",
        f"Folder: {result.folder_name}",
        f"Allowed: {'yes' if result.allowed else 'no'}",
        f"Configured: {'yes' if result.configured else 'no'}",
        f"Request attempted: {'yes' if result.request_attempted else 'no'}",
        f"Diagnostic log: {result.log_file}",
    ]
    if result.resolved_path:
        lines.extend(["", f"Resolved path: {result.resolved_path}"])
    if result.recent_entries:
        lines.extend(["", "Recent files:"])
        lines.extend(f"  {name}" for name in result.recent_entries)
    else:
        lines.extend(["", "Recent files:", "  None."])
    if result.fallback_reason:
        lines.extend(["", "Fallback reason:", f"  {result.fallback_reason}"])
    if result.safe_error:
        lines.extend(["", "Error:", f"  {result.safe_error}"])
    return "\n".join(lines)
