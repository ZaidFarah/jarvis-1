from __future__ import annotations

import os
import shlex
import subprocess
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from loguru import logger

from config.settings import AppSettings


_APP_LAUNCHER_LOG_SINK_ID: int | None = None
APP_NAME_ALIASES = {
    "calc": "calculator",
    "code": "vscode",
    "explorer": "file explorer",
    "google chrome": "chrome",
    "microsoft edge": "edge",
    "visual studio code": "vscode",
    "vs code": "vscode",
    "windows explorer": "file explorer",
}


def canonical_app_name(app_name: str) -> str:
    cleaned = " ".join(app_name.strip().split()).lower()
    return APP_NAME_ALIASES.get(cleaned, cleaned)


@dataclass(frozen=True)
class AppLauncherCheckReport:
    enabled: bool
    platform_supported: bool
    allowed_apps: dict[str, str]
    log_file: Path
    safe_error: str | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        return True


@dataclass(frozen=True)
class AppResolutionResult:
    enabled: bool
    app_name: str
    configured_command: str
    resolved_command: str | None
    resolved_path: str | None
    launch_method: str | None
    allowed: bool
    configured: bool
    platform_supported: bool
    log_file: Path
    safe_error: str | None = None
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AppLaunchResult:
    enabled: bool
    platform_supported: bool
    app_name: str
    allowed: bool
    configured: bool
    request_attempted: bool
    launched: bool
    command: str | None
    resolved_path: str | None
    launch_method: str | None
    log_file: Path
    safe_error: str | None = None
    fallback_reason: str | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        if not self.enabled:
            return False
        if not self.platform_supported:
            return False
        return self.launched


class AppLauncher:
    """Safe local application launcher backed only by whitelisted commands."""

    def __init__(
        self,
        settings: AppSettings,
        popen_factory: Callable[..., subprocess.Popen] | None = None,
    ) -> None:
        self.settings = settings
        self.popen_factory = popen_factory or subprocess.Popen
        self.log_file = self.settings.log_dir / "app_launcher.log"
        self.app_launcher_logger = logger.bind(app_launcher=True)
        self._ensure_log_sink()

    @property
    def enabled(self) -> bool:
        return self.settings.app_launcher_enabled

    @property
    def platform_supported(self) -> bool:
        return os.name == "nt"

    @property
    def allowed_apps(self) -> dict[str, str]:
        return self.settings.app_launcher_allowed_apps_map

    def resolve_app(self, app_name: str) -> AppResolutionResult:
        cleaned_name = self._clean_app_name(app_name)
        configured_command = self.allowed_apps.get(cleaned_name, "")
        resolved_path, launch_method = self._resolve_command(cleaned_name, configured_command)
        allowed = cleaned_name in self.allowed_apps
        configured = allowed
        safe_error: str | None = None
        if not allowed:
            safe_error = f"App '{cleaned_name}' is not allowed."
        elif resolved_path is None:
            safe_error = f"App '{cleaned_name}' is not installed or could not be found."
        return AppResolutionResult(
            enabled=self.enabled,
            app_name=cleaned_name,
            configured_command=configured_command,
            resolved_command=resolved_path,
            resolved_path=resolved_path,
            launch_method=launch_method,
            allowed=allowed,
            configured=configured,
            platform_supported=self.platform_supported,
            log_file=self.log_file,
            safe_error=safe_error,
            errors=[safe_error] if safe_error else [],
        )

    def run_check(self) -> AppLauncherCheckReport:
        self.app_launcher_logger.info(
            "Running app launcher diagnostic enabled={} platform_supported={}",
            self.enabled,
            self.platform_supported,
        )
        if not self.enabled:
            return self._check_report(safe_error=None, errors=[])

        if not self.platform_supported:
            message = "App launcher is only available on Windows."
            self.app_launcher_logger.warning(message)
            return self._check_report(safe_error=message, errors=[message])

        return self._check_report(safe_error=None, errors=[])

    def launch_app(self, app_name: str) -> AppLaunchResult:
        resolution = self.resolve_app(app_name)
        cleaned_name = resolution.app_name
        self.app_launcher_logger.info(
            "Launch request app={} configured_command={} resolved_path={} method={}",
            cleaned_name,
            resolution.configured_command or "[not configured]",
            resolution.resolved_path or "[unresolved]",
            resolution.launch_method or "[none]",
        )

        if not self.enabled:
            return self._launch_result(
                app_name=cleaned_name,
                allowed=resolution.allowed,
                configured=resolution.configured,
                request_attempted=False,
                launched=False,
                command=resolution.configured_command or None,
                resolved_path=resolution.resolved_path,
                launch_method=resolution.launch_method,
                safe_error="App launcher is disabled.",
                fallback_reason="App launcher is disabled.",
                errors=[],
            )

        if not self.platform_supported:
            message = "App launcher is only available on Windows."
            return self._launch_result(
                app_name=cleaned_name,
                allowed=resolution.allowed,
                configured=resolution.configured,
                request_attempted=False,
                launched=False,
                command=resolution.configured_command or None,
                resolved_path=resolution.resolved_path,
                launch_method=resolution.launch_method,
                safe_error=message,
                fallback_reason=message,
                errors=[message],
            )

        if not resolution.allowed:
            message = resolution.safe_error or f"App '{cleaned_name}' is not allowed."
            return self._launch_result(
                app_name=cleaned_name,
                allowed=False,
                configured=resolution.configured,
                request_attempted=False,
                launched=False,
                command=resolution.configured_command or None,
                resolved_path=resolution.resolved_path,
                launch_method=resolution.launch_method,
                safe_error=message,
                fallback_reason=message,
                errors=[message],
            )

        command = resolution.configured_command.strip()
        resolved_path = resolution.resolved_path
        launch_method = resolution.launch_method
        if resolved_path is None:
            message = resolution.safe_error or f"App '{cleaned_name}' could not be resolved."
            return self._launch_result(
                app_name=cleaned_name,
                allowed=True,
                configured=resolution.configured,
                request_attempted=False,
                launched=False,
                command=command,
                resolved_path=None,
                launch_method=None,
                safe_error=message,
                fallback_reason=message,
                errors=[message],
            )

        try:
            command_parts = [resolved_path]
            if command.lower().endswith((".cmd", ".bat")) and len(shlex.split(command, posix=False)) > 1:
                command_parts = shlex.split(command, posix=False)
            if not command_parts:
                raise ValueError("Configured launch command is empty.")
            self.popen_factory(command_parts, shell=False)
            self.app_launcher_logger.info(
                "Launched app={} command={} resolved_path={} method={}",
                cleaned_name,
                command,
                resolved_path,
                launch_method or "subprocess.Popen",
            )
            return self._launch_result(
                app_name=cleaned_name,
                allowed=True,
                configured=True,
                request_attempted=True,
                launched=True,
                command=command,
                resolved_path=resolved_path,
                launch_method=launch_method or "subprocess.Popen",
                safe_error=None,
                fallback_reason=None,
                errors=[],
            )
        except OSError as exc:
            try:
                os.startfile(resolved_path)
                self.app_launcher_logger.info(
                    "Launched app via os.startfile app={} command={} resolved_path={}",
                    cleaned_name,
                    command,
                    resolved_path,
                )
                return self._launch_result(
                    app_name=cleaned_name,
                    allowed=True,
                    configured=True,
                    request_attempted=True,
                    launched=True,
                    command=command,
                    resolved_path=resolved_path,
                    launch_method="os.startfile",
                    safe_error=None,
                    fallback_reason="Used Windows startfile fallback.",
                    errors=[],
                )
            except Exception as fallback_exc:  # pragma: no cover - defensive boundary
                safe_error = format_app_launcher_error(fallback_exc)
                self.app_launcher_logger.error("App launch fallback failed: {}", safe_error)
                return self._launch_result(
                    app_name=cleaned_name,
                    allowed=True,
                    configured=True,
                    request_attempted=True,
                    launched=False,
                    command=command,
                    resolved_path=resolved_path,
                    launch_method=launch_method,
                    safe_error=safe_error,
                    fallback_reason=safe_error,
                    errors=[safe_error],
                )
        except Exception as exc:  # pragma: no cover - defensive boundary
            safe_error = format_app_launcher_error(exc)
            self.app_launcher_logger.error("App launch failed: {}", safe_error)
            return self._launch_result(
                app_name=cleaned_name,
                allowed=True,
                configured=True,
                request_attempted=True,
                launched=False,
                command=command,
                resolved_path=resolved_path,
                launch_method=launch_method,
                safe_error=safe_error,
                fallback_reason=safe_error,
                errors=[safe_error],
            )

    def resolve_only(self, app_name: str) -> AppResolutionResult:
        resolution = self.resolve_app(app_name)
        self.app_launcher_logger.info(
            "Resolved app={} configured_command={} resolved_path={} method={}",
            resolution.app_name,
            resolution.configured_command or "[not configured]",
            resolution.resolved_path or "[unresolved]",
            resolution.launch_method or "[none]",
        )
        return resolution

    def _check_report(self, safe_error: str | None, errors: list[str]) -> AppLauncherCheckReport:
        return AppLauncherCheckReport(
            enabled=self.enabled,
            platform_supported=self.platform_supported,
            allowed_apps=self.allowed_apps,
            log_file=self.log_file,
            safe_error=safe_error,
            errors=errors,
        )

    def _launch_result(
        self,
        app_name: str,
        allowed: bool,
        configured: bool,
        request_attempted: bool,
        launched: bool,
        command: str | None,
        resolved_path: str | None,
        launch_method: str | None,
        safe_error: str | None,
        fallback_reason: str | None,
        errors: list[str],
    ) -> AppLaunchResult:
        return AppLaunchResult(
            enabled=self.enabled,
            platform_supported=self.platform_supported,
            app_name=app_name,
            allowed=allowed,
            configured=configured,
            request_attempted=request_attempted,
            launched=launched,
            command=command,
            resolved_path=resolved_path,
            launch_method=launch_method,
            log_file=self.log_file,
            safe_error=safe_error,
            fallback_reason=fallback_reason,
            errors=errors,
        )

    def _ensure_log_sink(self) -> None:
        global _APP_LAUNCHER_LOG_SINK_ID
        if _APP_LAUNCHER_LOG_SINK_ID is not None:
            return

        self.settings.log_dir.mkdir(parents=True, exist_ok=True)
        _APP_LAUNCHER_LOG_SINK_ID = logger.add(
            self.log_file,
            level="DEBUG",
            rotation="1 MB",
            retention="7 days",
            encoding="utf-8",
            backtrace=False,
            diagnose=False,
            filter=lambda record: bool(record["extra"].get("app_launcher")),
        )

    @staticmethod
    def _clean_app_name(app_name: str) -> str:
        return canonical_app_name(app_name)

    def _resolve_command(self, app_name: str, configured_command: str) -> tuple[str | None, str | None]:
        candidates = self._resolution_candidates(app_name, configured_command)
        if not candidates:
            return None, None

        for method, candidate in candidates:
            if not candidate:
                continue
            expanded = os.path.expandvars(os.path.expanduser(candidate))
            if os.path.isabs(expanded) and Path(expanded).exists():
                return expanded, method
            if any(separator in expanded for separator in ("\\", "/")) and Path(expanded).exists():
                return expanded, method
            found = shutil.which(expanded)
            if found:
                return found, method
        return None, None

    @staticmethod
    def _resolution_candidates(app_name: str, configured_command: str) -> list[tuple[str, str]]:
        command = configured_command.strip()
        candidates: list[tuple[str, str]] = []
        if command:
            candidates.append(("subprocess.Popen", command))

        if app_name == "edge":
            candidates.extend(
                [
                    ("shutil.which", "msedge.exe"),
                    ("shutil.which", "msedge"),
                    ("known_path", r"%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe"),
                    ("known_path", r"%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe"),
                ]
            )
        elif app_name == "chrome":
            candidates.extend(
                [
                    ("shutil.which", "chrome.exe"),
                    ("shutil.which", "chrome"),
                    ("known_path", r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
                    ("known_path", r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
                    ("known_path", r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
                ]
            )
        elif app_name == "vscode":
            candidates.extend(
                [
                    ("shutil.which", "code.cmd"),
                    ("shutil.which", "Code.exe"),
                    ("shutil.which", "code"),
                    ("known_path", r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
                    ("known_path", r"%PROGRAMFILES%\Microsoft VS Code\Code.exe"),
                ]
            )
        elif app_name == "spotify":
            candidates.extend(
                [
                    ("shutil.which", "Spotify.exe"),
                    ("known_path", r"%APPDATA%\Spotify\Spotify.exe"),
                    ("known_path", r"%LOCALAPPDATA%\Microsoft\WindowsApps\Spotify.exe"),
                ]
            )
        elif app_name == "file explorer":
            candidates.extend(
                [
                    ("shutil.which", "explorer.exe"),
                    ("known_path", r"%WINDIR%\explorer.exe"),
                ]
            )
        elif app_name == "docker":
            candidates.extend([("shutil.which", "Docker Desktop.exe"), ("shutil.which", "Docker Desktop"), ("shutil.which", "docker")])
        return candidates


def format_app_launcher_error(error: Exception) -> str:
    error_type = type(error).__name__
    message = str(error).strip() or "No error details provided."
    return f"{error_type}: {_redact_secret_like_text(message)}"


def format_app_launcher_check_report(report: AppLauncherCheckReport) -> str:
    lines = [
        "Jarvis App Launcher Check",
        "=========================",
        f"App launcher enabled: {_yes_no(report.enabled)}",
        f"Platform supported: {_yes_no(report.platform_supported)}",
        f"Diagnostic log: {report.log_file}",
        "",
        "Allowed apps:",
    ]
    if report.allowed_apps:
        lines.extend(f"  {name} -> {command or '[not configured]'}" for name, command in report.allowed_apps.items())
    else:
        lines.append("  None configured.")
    if report.safe_error:
        lines.extend(["", "Error:", f"  {report.safe_error}"])
    return "\n".join(lines)


def format_app_launch_report(result: AppLaunchResult) -> str:
    lines = [
        "Jarvis App Launch",
        "=================",
        f"App launcher enabled: {_yes_no(result.enabled)}",
        f"Platform supported: {_yes_no(result.platform_supported)}",
        f"App: {result.app_name}",
        f"Allowed: {_yes_no(result.allowed)}",
        f"Configured: {_yes_no(result.configured)}",
        f"Request attempted: {_yes_no(result.request_attempted)}",
        f"Launched: {_yes_no(result.launched)}",
        f"Diagnostic log: {result.log_file}",
    ]
    if result.resolved_path:
        lines.extend(["", f"Resolved path: {result.resolved_path}"])
    if result.launch_method:
        lines.extend(["", f"Launch method: {result.launch_method}"])
    if result.command:
        lines.extend(["", f"Command: {result.command}"])
    if result.fallback_reason:
        lines.extend(["", "Fallback reason:", f"  {result.fallback_reason}"])
    if result.safe_error:
        lines.extend(["", "Error:", f"  {result.safe_error}"])
    return "\n".join(lines)


def format_app_resolution_report(result: AppResolutionResult) -> str:
    lines = [
        "Jarvis App Resolution",
        "=====================",
        f"App launcher enabled: {_yes_no(result.enabled)}",
        f"Platform supported: {_yes_no(result.platform_supported)}",
        f"App: {result.app_name}",
        f"Allowed: {_yes_no(result.allowed)}",
        f"Configured: {_yes_no(result.configured)}",
        f"Configured command: {result.configured_command or '[not configured]'}",
        f"Diagnostic log: {result.log_file}",
    ]
    if result.resolved_path:
        lines.extend(["", f"Resolved path: {result.resolved_path}"])
    if result.launch_method:
        lines.extend(["", f"Launch method: {result.launch_method}"])
    if result.safe_error:
        lines.extend(["", "Error:", f"  {result.safe_error}"])
    return "\n".join(lines)


def _redact_secret_like_text(text: str) -> str:
    redacted_words: list[str] = []
    for word in text.split():
        if word.startswith("sk-") or "API_KEY" in word or "TOKEN" in word or "PASSWORD" in word:
            redacted_words.append("[redacted]")
        else:
            redacted_words.append(word)
    return " ".join(redacted_words)


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
