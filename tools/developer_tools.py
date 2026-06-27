from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from loguru import logger

from config.settings import AppSettings, PROJECT_ROOT
from tools.app_launcher import AppLauncher


_DEVELOPER_LOG_SINK_ID: int | None = None
_DEVELOPER_LOG_FILE: Path | None = None


ProcessRunner = Callable[..., subprocess.CompletedProcess[str]]
StartFile = Callable[[str], None]


@dataclass(frozen=True)
class DeveloperCommandResult:
    enabled: bool
    command_name: str
    request_attempted: bool
    succeeded: bool
    text: str
    log_file: Path
    safe_error: str | None = None
    output: str | None = None
    exit_code: int | None = None
    timed_out: bool = False
    target_path: Path | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        return self.enabled and self.succeeded


class DeveloperTools:
    """Safe developer mode helpers for local project work."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        runner: ProcessRunner | None = None,
        startfile: StartFile | None = None,
        app_launcher: AppLauncher | None = None,
    ) -> None:
        self.settings = settings
        self.runner = runner or subprocess.run
        self.startfile = startfile or getattr(os, "startfile", None)
        self.app_launcher = app_launcher or (AppLauncher(settings) if settings.app_launcher_enabled else None)
        self.log_file = self.settings.log_dir / "developer.log"
        self.developer_logger = logger.bind(developer=True)
        self._ensure_log_sink()

    @property
    def enabled(self) -> bool:
        return self.settings.developer_mode_enabled

    def run_tests(self) -> DeveloperCommandResult:
        return self._run_pytest("run tests", [sys.executable, "-m", "pytest", "-q"], timeout_seconds=self.settings.developer_command_timeout_seconds)

    def run_pytest(self) -> DeveloperCommandResult:
        return self.run_tests()

    def run_fast_tests(self) -> DeveloperCommandResult:
        targets = [
            "tests/test_settings.py",
            "tests/test_app_launcher.py",
            "tests/test_folder_control.py",
            "tests/test_vision_service.py",
            "tests/test_gui_voice_loop.py",
            "tests/test_developer_tools.py",
        ]
        return self._run_pytest(
            "run fast tests",
            [sys.executable, "-m", "pytest", "-q", *targets],
            timeout_seconds=min(self.settings.developer_command_timeout_seconds, 60),
        )

    def check_git_status(self) -> DeveloperCommandResult:
        return self._run_process("git status", ["git", "status", "--short"], cwd=PROJECT_ROOT)

    def show_git_status(self) -> DeveloperCommandResult:
        return self.check_git_status()

    def show_last_commit(self) -> DeveloperCommandResult:
        return self._run_process("show last commit", ["git", "log", "-1", "--oneline", "--decorate"], cwd=PROJECT_ROOT)

    def open_main_py(self) -> DeveloperCommandResult:
        return self._open_path(PROJECT_ROOT / "main.py", "open main.py")

    def open_fast_voice_file(self) -> DeveloperCommandResult:
        return self._open_path(PROJECT_ROOT / "voice" / "fast_voice.py", "open fast voice file")

    def open_assistant_core(self) -> DeveloperCommandResult:
        return self._open_path(PROJECT_ROOT / "assistant" / "core.py", "open assistant core")

    def open_settings(self) -> DeveloperCommandResult:
        return self._open_path(PROJECT_ROOT / "config" / "settings.py", "open settings")

    def open_tests_folder(self) -> DeveloperCommandResult:
        return self._open_path(PROJECT_ROOT / "tests", "open tests folder")

    def open_jarvis_in_vscode(self) -> DeveloperCommandResult:
        command_name = "open jarvis in vs code"
        if not self.enabled:
            return self._disabled_result(command_name)

        code_path = self._resolve_vscode_executable()
        if code_path is None:
            message = "VS Code is not installed or could not be found."
            return self._result(
                command_name,
                succeeded=False,
                text=message,
                request_attempted=False,
                safe_error=message,
                target_path=PROJECT_ROOT,
                errors=[message],
            )

        try:
            self.runner([code_path, str(PROJECT_ROOT)], shell=False, cwd=str(PROJECT_ROOT), timeout=self.settings.developer_command_timeout_seconds, capture_output=True, text=True)
        except Exception as exc:  # pragma: no cover - defensive boundary
            safe_error = f"{type(exc).__name__}: {exc}"
            self.developer_logger.error("{} failed: {}", command_name, safe_error)
            return self._result(
                command_name,
                succeeded=False,
                text=safe_error,
                request_attempted=True,
                safe_error=safe_error,
                target_path=PROJECT_ROOT,
                errors=[safe_error],
            )

        text = "Opened the Jarvis project in VS Code."
        self.developer_logger.info("{} project={} editor={}", command_name, PROJECT_ROOT, code_path)
        return self._result(
            command_name,
            succeeded=True,
            text=text,
            request_attempted=True,
            target_path=PROJECT_ROOT,
        )

    def handle_command(self, command: str) -> DeveloperCommandResult | None:
        normalized = " ".join(command.lower().strip().split())
        handlers = {
            "run tests": self.run_tests,
            "run pytest": self.run_pytest,
            "run fast tests": self.run_fast_tests,
            "check git status": self.check_git_status,
            "show git status": self.show_git_status,
            "show last commit": self.show_last_commit,
            "open main.py": self.open_main_py,
            "open fast voice file": self.open_fast_voice_file,
            "open assistant core": self.open_assistant_core,
            "open settings": self.open_settings,
            "open tests folder": self.open_tests_folder,
            "open jarvis in vs code": self.open_jarvis_in_vscode,
        }
        handler = handlers.get(normalized)
        if handler is None:
            return None
        return handler()

    def _run_pytest(self, command_name: str, args: list[str], timeout_seconds: int) -> DeveloperCommandResult:
        return self._run_process(command_name, args, cwd=PROJECT_ROOT, timeout_seconds=timeout_seconds)

    def _run_process(
        self,
        command_name: str,
        args: list[str],
        *,
        cwd: Path,
        timeout_seconds: int | None = None,
    ) -> DeveloperCommandResult:
        if not self.enabled:
            return self._disabled_result(command_name)

        timeout = timeout_seconds or self.settings.developer_command_timeout_seconds
        try:
            completed = self.runner(
                args,
                shell=False,
                cwd=str(cwd),
                timeout=timeout,
                capture_output=True,
                text=True,
            )
        except subprocess.TimeoutExpired as exc:
            safe_error = f"Command timed out after {timeout} seconds."
            self.developer_logger.warning("{} timed out args={} timeout={}", command_name, args, timeout)
            return self._result(
                command_name,
                succeeded=False,
                text=safe_error,
                request_attempted=True,
                safe_error=safe_error,
                exit_code=None,
                timed_out=True,
                output=getattr(exc, "stdout", None) or "",
                errors=[safe_error],
            )
        except Exception as exc:  # pragma: no cover - defensive boundary
            safe_error = f"{type(exc).__name__}: {exc}"
            self.developer_logger.error("{} failed args={} error={}", command_name, args, safe_error)
            return self._result(
                command_name,
                succeeded=False,
                text=safe_error,
                request_attempted=True,
                safe_error=safe_error,
                errors=[safe_error],
            )

        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()
        exit_code = completed.returncode
        summary = self._summarize_process_output(command_name, stdout, stderr, exit_code)
        succeeded = exit_code == 0
        self.developer_logger.info(
            "{} exit_code={} args={} stdout_chars={} stderr_chars={}",
            command_name,
            exit_code,
            args,
            len(stdout),
            len(stderr),
        )
        if stdout:
            self.developer_logger.debug("{} stdout:\n{}", command_name, stdout)
        if stderr:
            self.developer_logger.debug("{} stderr:\n{}", command_name, stderr)
        return self._result(
            command_name,
            succeeded=succeeded,
            text=summary,
            request_attempted=True,
            output=stdout,
            exit_code=exit_code,
            errors=[stderr] if stderr else [],
        )

    def _open_path(self, path: Path, command_name: str) -> DeveloperCommandResult:
        if not self.enabled:
            return self._disabled_result(command_name)

        resolved = path.expanduser().resolve()
        if not resolved.exists():
            message = f"{resolved.name} could not be found."
            return self._result(
                command_name,
                succeeded=False,
                text=message,
                request_attempted=False,
                safe_error=message,
                target_path=resolved,
                errors=[message],
            )

        if os.name != "nt" or self.startfile is None:
            message = "Opening files and folders is only available on Windows."
            return self._result(
                command_name,
                succeeded=False,
                text=message,
                request_attempted=False,
                safe_error=message,
                target_path=resolved,
                errors=[message],
            )

        try:
            self.startfile(str(resolved))
        except Exception as exc:  # pragma: no cover - defensive boundary
            safe_error = f"{type(exc).__name__}: {exc}"
            self.developer_logger.error("{} failed path={} error={}", command_name, resolved, safe_error)
            return self._result(
                command_name,
                succeeded=False,
                text=safe_error,
                request_attempted=True,
                safe_error=safe_error,
                target_path=resolved,
                errors=[safe_error],
            )

        self.developer_logger.info("{} opened path={}", command_name, resolved)
        return self._result(
            command_name,
            succeeded=True,
            text=f"Opened {resolved.name}.",
            request_attempted=True,
            target_path=resolved,
        )

    def _resolve_vscode_executable(self) -> str | None:
        if self.app_launcher is not None:
            resolution = self.app_launcher.resolve_only("vscode")
            if resolution.resolved_path:
                return resolution.resolved_path
        for candidate in ("code", "code-insiders"):
            found = shutil.which(candidate)
            if found:
                return found
        return None

    def _summarize_process_output(self, command_name: str, stdout: str, stderr: str, exit_code: int) -> str:
        if command_name in {"run tests", "run pytest", "run fast tests"}:
            return self._summarize_pytest_output(stdout, stderr, exit_code)
        if command_name in {"git status", "check git status", "show git status"}:
            return self._summarize_git_status(stdout)
        if command_name == "show last commit":
            return stdout.splitlines()[0].strip() if stdout else "No commit information found."
        if stderr and exit_code != 0:
            first_line = stderr.splitlines()[0].strip()
            return first_line or f"{command_name} failed."
        return stdout.splitlines()[0].strip() if stdout else f"{command_name} completed."

    @staticmethod
    def _summarize_pytest_output(stdout: str, stderr: str, exit_code: int) -> str:
        text = stdout or stderr
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return "Pytest completed."
        summary_line = lines[-1]
        if exit_code == 0:
            return f"Pytest passed: {summary_line}"
        return f"Pytest failed: {summary_line}"

    @staticmethod
    def _summarize_git_status(stdout: str) -> str:
        lines = [line.strip() for line in stdout.splitlines() if line.strip()]
        if not lines:
            return "Git status: working tree clean."
        return "Git status:\n" + "\n".join(lines[:10])

    def _disabled_result(self, command_name: str) -> DeveloperCommandResult:
        message = "Developer mode is disabled."
        return self._result(
            command_name,
            succeeded=False,
            text=message,
            request_attempted=False,
            safe_error=message,
            errors=[message],
        )

    def _result(
        self,
        command_name: str,
        *,
        succeeded: bool,
        text: str,
        request_attempted: bool,
        safe_error: str | None = None,
        output: str | None = None,
        exit_code: int | None = None,
        timed_out: bool = False,
        target_path: Path | None = None,
        errors: list[str] | None = None,
    ) -> DeveloperCommandResult:
        error_list = errors or ([safe_error] if safe_error else [])
        return DeveloperCommandResult(
            enabled=self.enabled,
            command_name=command_name,
            request_attempted=request_attempted,
            succeeded=succeeded,
            text=text,
            log_file=self.log_file,
            safe_error=safe_error,
            output=output,
            exit_code=exit_code,
            timed_out=timed_out,
            target_path=target_path,
            errors=error_list,
        )

    def _ensure_log_sink(self) -> None:
        global _DEVELOPER_LOG_FILE, _DEVELOPER_LOG_SINK_ID
        if _DEVELOPER_LOG_SINK_ID is not None and _DEVELOPER_LOG_FILE == self.log_file:
            return

        if _DEVELOPER_LOG_SINK_ID is not None:
            try:
                logger.remove(_DEVELOPER_LOG_SINK_ID)
            except ValueError:
                pass

        self.settings.log_dir.mkdir(parents=True, exist_ok=True)
        _DEVELOPER_LOG_SINK_ID = logger.add(
            self.log_file,
            level="DEBUG",
            rotation="1 MB",
            retention="7 days",
            encoding="utf-8",
            backtrace=False,
            diagnose=False,
            filter=lambda record: bool(record["extra"].get("developer")),
        )
        _DEVELOPER_LOG_FILE = self.log_file
