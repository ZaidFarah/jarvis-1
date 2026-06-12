from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from assistant.core import AssistantCore
from config.settings import AppSettings
from tools.app_launcher import (
    AppLaunchResult,
    AppLauncher,
    AppLauncherCheckReport,
    AppResolutionResult,
    format_app_launcher_error,
    format_app_launch_report,
    format_app_resolution_report,
)


class FakeOpenAIService:
    def chat(self, *args, **kwargs):  # pragma: no cover - defensive helper
        del args, kwargs
        raise AssertionError("OpenAI should not be called")


def test_app_launcher_allowed_app_lookup(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, log_dir=tmp_path)
    launcher = AppLauncher(settings, popen_factory=lambda *args, **kwargs: None)

    assert launcher.allowed_apps["notepad"] == "notepad.exe"
    assert launcher.allowed_apps["calculator"] == "calc.exe"


def test_app_launcher_resolve_configured_executable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("tools.app_launcher.shutil.which", lambda value: f"C:/Windows/System32/{value}")
    settings = AppSettings(_env_file=None, log_dir=tmp_path)
    launcher = AppLauncher(settings, popen_factory=lambda *args, **kwargs: None)

    result = launcher.resolve_app("notepad")

    assert result.allowed is True
    assert result.configured is True
    assert result.resolved_path == "C:/Windows/System32/notepad.exe"
    assert result.launch_method == "subprocess.Popen"


def test_app_launcher_unknown_app_rejected(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, log_dir=tmp_path)
    launcher = AppLauncher(settings, popen_factory=lambda *args, **kwargs: None)

    result = launcher.resolve_app("paint")

    assert result.allowed is False
    assert result.resolved_path is None
    assert "not allowed" in (result.safe_error or "")


def test_app_launcher_disabled_fallback(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, app_launcher_enabled=False, log_dir=tmp_path)
    launcher = AppLauncher(settings, popen_factory=lambda *args, **kwargs: None)

    result = launcher.launch_app("notepad")

    assert result.launched is False
    assert result.enabled is False
    assert result.fallback_reason == "App launcher is disabled."


def test_app_launcher_does_not_allow_arbitrary_commands(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_popen(*args, **kwargs):
        captured.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr("tools.app_launcher.shutil.which", lambda value: f"C:/Windows/System32/{value}")
    settings = AppSettings(_env_file=None, log_dir=tmp_path)
    launcher = AppLauncher(settings, popen_factory=fake_popen)

    result = launcher.launch_app("notepad")

    assert result.launched is True
    assert captured
    command_parts = captured[0][0][0]
    assert command_parts == ["C:/Windows/System32/notepad.exe"]
    assert captured[0][1]["shell"] is False


def test_app_launcher_rejects_raw_user_input(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("tools.app_launcher.shutil.which", lambda value: f"C:/Windows/System32/{value}")
    settings = AppSettings(_env_file=None, log_dir=tmp_path)
    launcher = AppLauncher(settings, popen_factory=lambda *args, **kwargs: None)

    result = launcher.launch_app("notepad.exe && calc.exe")

    assert result.launched is False
    assert result.allowed is False


def test_app_launcher_check_formats_safe_error() -> None:
    error = format_app_launcher_error(RuntimeError("failed with OPENAI_API_KEY=sk-test-secret"))

    assert "sk-test-secret" not in error
    assert "OPENAI_API_KEY" not in error


def test_app_launcher_resolution_report_includes_details(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("tools.app_launcher.shutil.which", lambda value: f"C:/Windows/System32/{value}")
    settings = AppSettings(_env_file=None, log_dir=tmp_path)
    launcher = AppLauncher(settings, popen_factory=lambda *args, **kwargs: None)

    report = launcher.resolve_app("vscode")
    text = format_app_resolution_report(report)

    assert "Jarvis App Resolution" in text
    assert "Configured command" in text
    assert "Resolved path" in text


def test_app_launcher_launch_report_includes_resolved_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("tools.app_launcher.shutil.which", lambda value: f"C:/Windows/System32/{value}")
    settings = AppSettings(_env_file=None, log_dir=tmp_path)
    launcher = AppLauncher(settings, popen_factory=lambda *args, **kwargs: None)

    result = launcher.launch_app("notepad")
    text = format_app_launch_report(result)

    assert "Resolved path" in text
    assert "Launch method" in text


def test_app_launcher_falls_back_to_startfile(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("tools.app_launcher.shutil.which", lambda value: f"C:/Windows/System32/{value}")
    startfile_calls: list[str] = []

    def fake_startfile(path: str) -> None:
        startfile_calls.append(path)

    monkeypatch.setattr("tools.app_launcher.os.startfile", fake_startfile)

    def failing_popen(*args, **kwargs):
        raise OSError("Popen failed")

    settings = AppSettings(_env_file=None, log_dir=tmp_path)
    launcher = AppLauncher(settings, popen_factory=failing_popen)

    result = launcher.launch_app("notepad")

    assert result.launched is True
    assert startfile_calls == ["C:/Windows/System32/notepad.exe"]
    assert result.launch_method == "os.startfile"


def test_assistant_core_routes_app_launcher_commands(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("tools.app_launcher.shutil.which", lambda value: f"C:/Windows/System32/{value}")
    settings = AppSettings(_env_file=None, log_dir=tmp_path)
    launcher = AppLauncher(settings, popen_factory=lambda *args, **kwargs: None)
    assistant = AssistantCore(settings=settings, openai_service=FakeOpenAIService())
    assistant.app_launcher = launcher

    response = assistant.handle_command("open notepad")

    assert response.source == "launcher"
    assert response.accepted is True
    assert "Launched notepad" in response.text


def test_assistant_core_disabled_app_launcher_fallback() -> None:
    settings = AppSettings(_env_file=None, app_launcher_enabled=False)
    assistant = AssistantCore(settings=settings, openai_service=FakeOpenAIService())

    response = assistant.handle_command("open notepad")

    assert response.source == "local"
    assert response.text == "App launcher is disabled."


def test_app_launcher_cli_commands(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    from main import main

    class DummyLauncher:
        def __init__(self, settings: AppSettings) -> None:
            del settings

        def run_check(self) -> AppLauncherCheckReport:
            return AppLauncherCheckReport(
                enabled=True,
                platform_supported=True,
                allowed_apps={"notepad": "notepad.exe"},
                log_file=Path("logs/app_launcher.log"),
            )

        def resolve_only(self, app_name: str) -> AppResolutionResult:
            return AppResolutionResult(
                enabled=True,
                app_name=app_name,
                configured_command="notepad.exe",
                resolved_command="C:/Windows/System32/notepad.exe",
                resolved_path="C:/Windows/System32/notepad.exe",
                launch_method="subprocess.Popen",
                allowed=True,
                configured=True,
                platform_supported=True,
                log_file=Path("logs/app_launcher.log"),
            )

        def launch_app(self, app_name: str) -> AppLaunchResult:
            return AppLaunchResult(
                enabled=True,
                platform_supported=True,
                app_name=app_name,
                allowed=True,
                configured=True,
                request_attempted=True,
                launched=True,
                command="notepad.exe",
                resolved_path="C:/Windows/System32/notepad.exe",
                launch_method="subprocess.Popen",
                log_file=Path("logs/app_launcher.log"),
            )

    monkeypatch.setattr("main.AppLauncher", DummyLauncher)

    check_exit = main(["--app-launcher-check"])
    check_output = capsys.readouterr().out
    resolve_exit = main(["--resolve-app", "notepad"])
    resolve_output = capsys.readouterr().out
    launch_exit = main(["--launch-app", "notepad"])
    launch_output = capsys.readouterr().out

    assert check_exit == 0
    assert "Jarvis App Launcher Check" in check_output
    assert resolve_exit == 0
    assert "Jarvis App Resolution" in resolve_output
    assert launch_exit == 0
    assert "Jarvis App Launch" in launch_output
