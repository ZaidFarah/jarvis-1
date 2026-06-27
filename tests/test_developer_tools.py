from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess
import sys
from types import SimpleNamespace

import pytest

from assistant.core import AssistantCore
from config.settings import AppSettings
from tools.developer_tools import DeveloperTools


class FakeOpenAIService:
    def chat(self, *args, **kwargs):  # pragma: no cover - defensive helper
        del args, kwargs
        raise AssertionError("OpenAI should not be called")


class FakeRunner:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        self.calls: list[tuple[list[str], dict[str, object]]] = []
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode

    def __call__(self, args, **kwargs):
        self.calls.append((list(args), dict(kwargs)))
        return CompletedProcess(args=args, returncode=self.returncode, stdout=self.stdout, stderr=self.stderr)


def test_developer_tools_runs_tests_with_timeout(tmp_path: Path) -> None:
    runner = FakeRunner(stdout="================ 3 passed in 0.25s ================")
    settings = AppSettings(_env_file=None, log_dir=tmp_path, developer_mode_enabled=True, developer_command_timeout_seconds=120)
    tools = DeveloperTools(settings, runner=runner)

    result = tools.run_tests()

    assert result.succeeded is True
    assert "Pytest passed" in result.text
    assert runner.calls[0][0][:3] == [sys.executable, "-m", "pytest"]
    assert runner.calls[0][1]["shell"] is False


def test_developer_tools_reports_git_status_and_last_commit(tmp_path: Path) -> None:
    status_runner = FakeRunner(stdout=" M assistant/core.py\n?? tests/test_developer_tools.py\n")
    commit_runner = FakeRunner(stdout="abc1234 Add developer tools")
    settings = AppSettings(_env_file=None, log_dir=tmp_path, developer_mode_enabled=True)
    tools = DeveloperTools(settings, runner=status_runner)

    status = tools.check_git_status()
    assert status.succeeded is True
    assert "Git status:" in status.text
    assert "assistant/core.py" in status.text

    tools.runner = commit_runner
    commit = tools.show_last_commit()
    assert commit.succeeded is True
    assert commit.text.startswith("abc1234")


def test_developer_tools_opens_project_files_and_tests_folder(tmp_path: Path) -> None:
    opened: list[str] = []
    settings = AppSettings(_env_file=None, log_dir=tmp_path, developer_mode_enabled=True)
    tools = DeveloperTools(settings, startfile=lambda value: opened.append(value))

    main_result = tools.open_main_py()
    core_result = tools.open_assistant_core()
    settings_result = tools.open_settings()
    tests_result = tools.open_tests_folder()

    assert main_result.succeeded is True
    assert core_result.succeeded is True
    assert settings_result.succeeded is True
    assert tests_result.succeeded is True
    assert any(path.endswith("main.py") for path in opened)
    assert any(path.endswith("assistant\\core.py") or path.endswith("assistant/core.py") for path in opened)
    assert any(path.endswith("config\\settings.py") or path.endswith("config/settings.py") for path in opened)
    assert any(path.endswith("tests") for path in opened)


def test_developer_tools_open_jarvis_in_vscode_uses_runner(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = FakeRunner()
    settings = AppSettings(_env_file=None, log_dir=tmp_path, developer_mode_enabled=True)
    tools = DeveloperTools(
        settings,
        runner=runner,
        app_launcher=SimpleNamespace(resolve_only=lambda name: SimpleNamespace(resolved_path=None)),
    )
    monkeypatch.setattr("tools.developer_tools.shutil.which", lambda value: "C:/Program Files/VS Code/Code.exe" if value in {"code", "code-insiders"} else None)

    result = tools.open_jarvis_in_vscode()

    assert result.succeeded is True
    assert runner.calls
    assert runner.calls[0][0][0].endswith("Code.exe")
    assert runner.calls[0][0][1].endswith("Jarvis")


def test_assistant_core_routes_developer_commands_locally(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, log_dir=tmp_path, developer_mode_enabled=True)
    tools = DeveloperTools(settings, runner=FakeRunner(stdout=" M assistant/core.py"))
    assistant = AssistantCore(settings=settings, openai_service=FakeOpenAIService())
    assistant.developer_tools = tools

    response = assistant.handle_command("show git status")

    assert response.source == "developer"
    assert "Git status:" in response.text


def test_developer_mode_disabled_returns_local_message(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, log_dir=tmp_path, developer_mode_enabled=False)
    assistant = AssistantCore(settings=settings, openai_service=FakeOpenAIService())

    response = assistant.handle_command("run tests")

    assert response.source == "local"
    assert "Developer mode is disabled" in response.text
