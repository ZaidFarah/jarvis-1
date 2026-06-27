from __future__ import annotations

from pathlib import Path

from agent.runtime import AgentRuntime
from agent.router import AgentRouter
from assistant.core import AssistantCore
from config.settings import AppSettings
from tools.developer_tools import DeveloperCommandResult
from tools.workflows import WorkflowEngine, format_workflow_result


class FakeOpenAIService:
    def chat(self, *args, **kwargs):  # pragma: no cover - defensive helper
        del args, kwargs
        raise AssertionError("OpenAI should not be called")


class FakeDeveloperTools:
    def __init__(self, log_file: Path, *, fast_tests_succeeded: bool = True) -> None:
        self.calls: list[str] = []
        self.log_file = log_file
        self.fast_tests_succeeded = fast_tests_succeeded

    def open_jarvis_in_vscode(self) -> DeveloperCommandResult:
        self.calls.append("open_jarvis_in_vscode")
        return self._result("open jarvis in vs code", "Opened the Jarvis project in VS Code.")

    def check_git_status(self) -> DeveloperCommandResult:
        self.calls.append("check_git_status")
        return self._result("git status", "Git status: working tree clean.")

    def show_last_commit(self) -> DeveloperCommandResult:
        self.calls.append("show_last_commit")
        return self._result("show last commit", "abc1234 Add developer workflow")

    def run_fast_tests(self) -> DeveloperCommandResult:
        self.calls.append("run_fast_tests")
        if not self.fast_tests_succeeded:
            return self._result(
                "run fast tests",
                "Pytest failed: 1 failed, 5 passed",
                succeeded=False,
                safe_error="Fast tests failed.",
            )
        return self._result("run fast tests", "Pytest passed: 6 passed in 0.42s")

    def _result(
        self,
        command_name: str,
        text: str,
        *,
        succeeded: bool = True,
        safe_error: str | None = None,
    ) -> DeveloperCommandResult:
        return DeveloperCommandResult(
            enabled=True,
            command_name=command_name,
            request_attempted=True,
            succeeded=succeeded,
            text=text,
            log_file=self.log_file,
            safe_error=safe_error,
            errors=[safe_error] if safe_error else [],
        )


def test_workflow_engine_start_coding_session_runs_fixed_safe_steps(tmp_path: Path) -> None:
    tools = FakeDeveloperTools(tmp_path / "developer.log")
    engine = WorkflowEngine(tools)

    result = engine.handle_command("start coding session")

    assert result is not None
    assert result.succeeded is True
    assert tools.calls == [
        "open_jarvis_in_vscode",
        "check_git_status",
        "run_fast_tests",
    ]
    text = format_workflow_result(result)
    assert "Workflow: Start coding session" in text
    assert "Open Jarvis in VS Code: OK" in text
    assert "Git status: working tree clean" in text
    assert "Pytest passed" in text


def test_workflow_engine_review_todays_work_runs_review_steps(tmp_path: Path) -> None:
    tools = FakeDeveloperTools(tmp_path / "developer.log")
    engine = WorkflowEngine(tools)

    result = engine.handle_command("review today's work")

    assert result is not None
    assert result.succeeded is True
    assert tools.calls == [
        "check_git_status",
        "show_last_commit",
        "run_fast_tests",
    ]
    text = format_workflow_result(result)
    assert "Workflow: Review today's work" in text
    assert "Last commit: abc1234 Add developer workflow" in text


def test_workflow_engine_reports_failed_step_in_summary(tmp_path: Path) -> None:
    tools = FakeDeveloperTools(tmp_path / "developer.log", fast_tests_succeeded=False)
    engine = WorkflowEngine(tools)

    result = engine.handle_command("review todays work")

    assert result is not None
    assert result.succeeded is False
    assert result.safe_error == "Fast tests failed."
    text = format_workflow_result(result)
    assert "Status: needs attention" in text
    assert "Run fast tests: FAILED" in text
    assert "Failed step(s): Run fast tests" in text


def test_assistant_core_routes_workflow_commands_locally(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, log_dir=tmp_path, developer_mode_enabled=True)
    tools = FakeDeveloperTools(tmp_path / "developer.log")
    assistant = AssistantCore(settings=settings, openai_service=FakeOpenAIService())
    assistant.developer_tools = tools
    assistant.workflow_engine = WorkflowEngine(tools)

    response = assistant.handle_command("start coding session")

    assert response.source == "workflow"
    assert response.accepted is True
    assert "Workflow: Start coding session" in response.text
    assert tools.calls == [
        "open_jarvis_in_vscode",
        "check_git_status",
        "run_fast_tests",
    ]


def test_assistant_core_reports_workflow_disabled_when_developer_mode_is_off(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, log_dir=tmp_path, developer_mode_enabled=False)
    assistant = AssistantCore(settings=settings, openai_service=FakeOpenAIService())

    response = assistant.handle_command("review today's work")

    assert response.source == "local"
    assert response.accepted is True
    assert response.text == "Developer mode is disabled."


def test_agent_router_recognizes_workflow_commands(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, log_dir=tmp_path)
    route = AgentRouter(settings).route("review today's work")

    assert route.tool_name == "workflows"


def test_agent_runtime_dispatches_workflow_through_assistant_core(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, log_dir=tmp_path, developer_mode_enabled=True)
    tools = FakeDeveloperTools(tmp_path / "developer.log")
    assistant = AssistantCore(settings=settings, openai_service=FakeOpenAIService())
    assistant.developer_tools = tools
    assistant.workflow_engine = WorkflowEngine(tools)
    runtime = AgentRuntime(settings=settings, assistant=assistant)

    result = runtime.run("review today's work")

    assert result.selected_tool == "workflows"
    assert result.response.source == "workflow"
    assert "Workflow: Review today's work" in result.final_response
    assert tools.calls == [
        "check_git_status",
        "show_last_commit",
        "run_fast_tests",
    ]
