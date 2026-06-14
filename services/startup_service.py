from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from loguru import logger

from config.settings import AppSettings, PROJECT_ROOT
from jarvis_runtime.runtime_paths import resolve_runtime_paths
from security.confirmation import ConfirmationResult
from security.permissions import PermissionBroker, PermissionDecision


RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_ENABLE_ACTION = "register startup"
STARTUP_DISABLE_ACTION = "unregister startup"
STARTUP_LOG_SINK_ID: int | None = None
STARTUP_LOG_FILE: Path | None = None


class StartupRegistry(Protocol):
    def get_value(self, name: str) -> str | None: ...

    def set_value(self, name: str, value: str) -> None: ...

    def delete_value(self, name: str) -> None: ...


@dataclass(frozen=True)
class StartupTarget:
    supported: bool
    runtime_mode: str
    target_path: Path | None
    command: str
    reason: str


@dataclass(frozen=True)
class StartupCheckReport:
    supported: bool
    startup_enabled_setting: bool
    registered: bool
    runtime_mode: str
    app_name: str
    target_path: Path | None
    target_command: str
    registered_command: str
    registry_key: str
    log_file: Path
    safe_error: str | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        return True


@dataclass(frozen=True)
class StartupActionReport:
    action: str
    check: StartupCheckReport
    permission: PermissionDecision | None
    confirmation: ConfirmationResult | None
    changed: bool
    success: bool
    message: str
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        return self.success


class WindowsRunRegistry:
    def __init__(self) -> None:
        import winreg

        self._winreg = winreg
        self._root = winreg.HKEY_CURRENT_USER

    def get_value(self, name: str) -> str | None:
        try:
            with self._winreg.OpenKey(self._root, RUN_KEY_PATH, 0, self._winreg.KEY_READ) as key:
                value, value_type = self._winreg.QueryValueEx(key, name)
        except FileNotFoundError:
            return None
        if value_type != self._winreg.REG_SZ:
            return None
        return str(value)

    def set_value(self, name: str, value: str) -> None:
        with self._winreg.CreateKeyEx(self._root, RUN_KEY_PATH, 0, self._winreg.KEY_SET_VALUE) as key:
            self._winreg.SetValueEx(key, name, 0, self._winreg.REG_SZ, value)

    def delete_value(self, name: str) -> None:
        try:
            with self._winreg.OpenKey(self._root, RUN_KEY_PATH, 0, self._winreg.KEY_SET_VALUE) as key:
                self._winreg.DeleteValue(key, name)
        except FileNotFoundError:
            return


class StartupService:
    def __init__(
        self,
        settings: AppSettings,
        *,
        registry: StartupRegistry | None = None,
        permission_broker: PermissionBroker | None = None,
        runtime_mode: str | None = None,
        project_root: Path | None = None,
        executable_path: Path | None = None,
        os_name: str | None = None,
    ) -> None:
        self.settings = settings
        self.registry = registry if registry is not None else self._default_registry()
        self.permission_broker = permission_broker or PermissionBroker(settings)
        self.project_root = (project_root or PROJECT_ROOT).expanduser().resolve()
        self.runtime_mode = runtime_mode
        self.executable_path = executable_path.expanduser().resolve() if executable_path is not None else None
        self.os_name = os_name or os.name
        self.log_file = self.settings.log_dir / "startup.log"
        self.startup_logger = logger.bind(startup=True)
        self._ensure_log_sink()

    def run_check(self) -> StartupCheckReport:
        target = self.resolve_target()
        registered_command = ""
        safe_error = None
        errors: list[str] = []
        if not target.supported:
            safe_error = target.reason
            errors.append(target.reason)
        elif self.registry is None:
            safe_error = "Startup registry is unavailable."
            errors.append(safe_error)
        else:
            try:
                registered_command = self.registry.get_value(self.settings.startup_app_name) or ""
            except Exception as exc:
                safe_error = _format_startup_error(exc)
                errors.append(safe_error)

        registered = bool(target.command and registered_command == target.command)
        report = StartupCheckReport(
            supported=target.supported and self.registry is not None,
            startup_enabled_setting=self.settings.startup_enabled,
            registered=registered,
            runtime_mode=target.runtime_mode,
            app_name=self.settings.startup_app_name,
            target_path=target.target_path,
            target_command=target.command,
            registered_command=_safe_command_for_display(registered_command),
            registry_key=f"HKCU\\{RUN_KEY_PATH}",
            log_file=self.log_file,
            safe_error=safe_error,
            errors=errors,
        )
        self.startup_logger.info(
            "Startup check supported={} registered={} runtime_mode={} target={}",
            report.supported,
            report.registered,
            report.runtime_mode,
            report.target_path,
        )
        return report

    def enable_startup(self, confirmation_handler) -> StartupActionReport:
        check = self.run_check()
        permission = self.permission_broker.check(
            STARTUP_ENABLE_ACTION,
            description=f"Register {self.settings.app_name} to start for the current Windows user.",
        )
        confirmation = self._confirm_if_required(permission, confirmation_handler)
        if not self._can_modify(check, permission, confirmation):
            return StartupActionReport(
                action=STARTUP_ENABLE_ACTION,
                check=check,
                permission=permission,
                confirmation=confirmation,
                changed=False,
                success=False,
                message="Startup registration was not changed.",
                errors=_action_errors(check, permission, confirmation),
            )

        try:
            self.registry.set_value(check.app_name, check.target_command)  # type: ignore[union-attr]
        except Exception as exc:
            safe_error = _format_startup_error(exc)
            self.startup_logger.error("Startup enable failed: {}", safe_error)
            return StartupActionReport(
                action=STARTUP_ENABLE_ACTION,
                check=check,
                permission=permission,
                confirmation=confirmation,
                changed=False,
                success=False,
                message="Startup registration failed.",
                errors=[safe_error],
            )

        self.startup_logger.info("Startup registered app_name={} command={}", check.app_name, check.target_command)
        return StartupActionReport(
            action=STARTUP_ENABLE_ACTION,
            check=self.run_check(),
            permission=permission,
            confirmation=confirmation,
            changed=True,
            success=True,
            message="Startup registration enabled.",
            errors=[],
        )

    def disable_startup(self, confirmation_handler) -> StartupActionReport:
        check = self.run_check()
        permission = self.permission_broker.check(
            STARTUP_DISABLE_ACTION,
            description=f"Remove {self.settings.app_name} from current-user Windows startup.",
        )
        confirmation = self._confirm_if_required(permission, confirmation_handler)
        if not self._can_modify(check, permission, confirmation):
            return StartupActionReport(
                action=STARTUP_DISABLE_ACTION,
                check=check,
                permission=permission,
                confirmation=confirmation,
                changed=False,
                success=False,
                message="Startup registration was not changed.",
                errors=_action_errors(check, permission, confirmation),
            )

        try:
            self.registry.delete_value(check.app_name)  # type: ignore[union-attr]
        except Exception as exc:
            safe_error = _format_startup_error(exc)
            self.startup_logger.error("Startup disable failed: {}", safe_error)
            return StartupActionReport(
                action=STARTUP_DISABLE_ACTION,
                check=check,
                permission=permission,
                confirmation=confirmation,
                changed=False,
                success=False,
                message="Startup registration removal failed.",
                errors=[safe_error],
            )

        self.startup_logger.info("Startup unregistered app_name={}", check.app_name)
        return StartupActionReport(
            action=STARTUP_DISABLE_ACTION,
            check=self.run_check(),
            permission=permission,
            confirmation=confirmation,
            changed=check.registered,
            success=True,
            message="Startup registration disabled.",
            errors=[],
        )

    def resolve_target(self) -> StartupTarget:
        if self.os_name != "nt":
            return StartupTarget(False, self._runtime_mode(), None, "", "Windows startup is supported only on Windows.")

        runtime_mode = self._runtime_mode()
        if runtime_mode == "packaged":
            executable = self.executable_path or Path(sys.executable).resolve()
            if executable.name.lower() != "jarvis.exe":
                return StartupTarget(False, runtime_mode, executable, "", "Packaged startup target must be Jarvis.exe.")
            return StartupTarget(True, runtime_mode, executable, _quote_path(executable), "Supported.")

        launcher = self.project_root / "run_jarvis.bat"
        if launcher.exists():
            return StartupTarget(True, runtime_mode, launcher, _quote_path(launcher), "Supported.")
        return StartupTarget(
            False,
            runtime_mode,
            launcher,
            "",
            "Source startup requires run_jarvis.bat in the project root.",
        )

    def _runtime_mode(self) -> str:
        if self.runtime_mode:
            cleaned = self.runtime_mode.strip().lower()
            if cleaned in {"source", "packaged"}:
                return cleaned
        return resolve_runtime_paths(self.settings).runtime_mode

    def _confirm_if_required(self, permission: PermissionDecision, confirmation_handler) -> ConfirmationResult | None:
        if not permission.allowed or not permission.requires_confirmation:
            return None
        return confirmation_handler(permission.action_name, permission.risk_level, permission.description)

    @staticmethod
    def _can_modify(
        check: StartupCheckReport,
        permission: PermissionDecision,
        confirmation: ConfirmationResult | None,
    ) -> bool:
        if not check.supported:
            return False
        if not permission.allowed:
            return False
        if permission.requires_confirmation and (confirmation is None or not confirmation.approved):
            return False
        return True

    def _default_registry(self) -> StartupRegistry | None:
        if os.name != "nt":
            return None
        return WindowsRunRegistry()

    def _ensure_log_sink(self) -> None:
        global STARTUP_LOG_FILE, STARTUP_LOG_SINK_ID
        if STARTUP_LOG_SINK_ID is not None and STARTUP_LOG_FILE == self.log_file:
            return
        if STARTUP_LOG_SINK_ID is not None:
            try:
                logger.remove(STARTUP_LOG_SINK_ID)
            except ValueError:
                pass

        self.settings.log_dir.mkdir(parents=True, exist_ok=True)
        STARTUP_LOG_SINK_ID = logger.add(
            self.log_file,
            level="DEBUG",
            rotation="1 MB",
            retention="7 days",
            encoding="utf-8",
            backtrace=False,
            diagnose=False,
            filter=lambda record: bool(record["extra"].get("startup")),
        )
        STARTUP_LOG_FILE = self.log_file


def format_startup_check_report(report: StartupCheckReport) -> str:
    lines = [
        "Jarvis Startup Check",
        "====================",
        f"Startup supported: {_yes_no(report.supported)}",
        f"Startup setting enabled: {_yes_no(report.startup_enabled_setting)}",
        f"Currently registered: {_yes_no(report.registered)}",
        f"Runtime mode: {report.runtime_mode}",
        f"App name: {report.app_name}",
        f"Registry key: {report.registry_key}",
        f"Target path: {report.target_path or ''}",
        f"Target command: {report.target_command}",
        f"Registered command: {report.registered_command}",
        f"Diagnostic log: {report.log_file}",
    ]
    if report.safe_error:
        lines.extend(["", "Error:", f"  {report.safe_error}"])
    return "\n".join(lines)


def format_startup_action_report(report: StartupActionReport) -> str:
    lines = [
        "Jarvis Startup Action",
        "=====================",
        f"Action: {report.action}",
        f"Success: {_yes_no(report.success)}",
        f"Changed: {_yes_no(report.changed)}",
        f"Message: {report.message}",
    ]
    if report.permission is not None:
        lines.extend(
            [
                f"Permission risk: {report.permission.risk_level}",
                f"Permission allowed: {_yes_no(report.permission.allowed)}",
                f"Confirmation required: {_yes_no(report.permission.requires_confirmation)}",
            ]
        )
    if report.confirmation is not None:
        lines.extend(
            [
                f"Confirmation approved: {_yes_no(report.confirmation.approved)}",
                f"Confirmation reason: {report.confirmation.reason}",
            ]
        )
    lines.extend(["", format_startup_check_report(report.check)])
    if report.errors:
        lines.extend(["", "Errors:"])
        lines.extend(f"  {error}" for error in report.errors)
    return "\n".join(lines)


def _quote_path(path: Path) -> str:
    return f'"{path}"'


def _safe_command_for_display(command: str) -> str:
    if not command:
        return ""
    lowered = command.lower()
    if any(marker in lowered for marker in ("openai_api_key", "weather_api_key", "sk-", "token_", "secret")):
        return "[redacted]"
    return command


def _format_startup_error(error: Exception) -> str:
    error_type = type(error).__name__
    message = str(error).strip() or "No error details provided."
    return f"{error_type}: {message}"


def _action_errors(
    check: StartupCheckReport,
    permission: PermissionDecision,
    confirmation: ConfirmationResult | None,
) -> list[str]:
    errors: list[str] = []
    errors.extend(check.errors)
    errors.extend(permission.errors)
    if confirmation is not None:
        errors.extend(confirmation.errors)
    if permission.requires_confirmation and confirmation is None:
        errors.append("Confirmation was required but not completed.")
    return errors


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
