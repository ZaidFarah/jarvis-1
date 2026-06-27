from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Protocol

from tools.developer_tools import DeveloperCommandResult, DeveloperTools


class DeveloperWorkflowService(Protocol):
    def open_jarvis_in_vscode(self) -> DeveloperCommandResult:
        ...

    def check_git_status(self) -> DeveloperCommandResult:
        ...

    def show_last_commit(self) -> DeveloperCommandResult:
        ...

    def run_fast_tests(self) -> DeveloperCommandResult:
        ...


@dataclass(frozen=True)
class WorkflowStepResult:
    name: str
    result: DeveloperCommandResult

    @property
    def succeeded(self) -> bool:
        return self.result.succeeded


@dataclass(frozen=True)
class WorkflowRunResult:
    workflow_name: str
    steps: tuple[WorkflowStepResult, ...]

    @property
    def succeeded(self) -> bool:
        return all(step.succeeded for step in self.steps)

    @property
    def safe_error(self) -> str | None:
        failed_steps = [step for step in self.steps if not step.succeeded]
        if not failed_steps:
            return None
        return "; ".join(
            step.result.safe_error or step.result.text or f"{step.name} failed."
            for step in failed_steps
        )


class WorkflowEngine:
    """Fixed local workflows built from existing safe developer tools."""

    def __init__(self, developer_tools: DeveloperWorkflowService | DeveloperTools) -> None:
        self.developer_tools = developer_tools

    def handle_command(self, command: str) -> WorkflowRunResult | None:
        normalized = normalize_workflow_command(command)
        handlers: dict[str, Callable[[], WorkflowRunResult]] = {
            "start coding session": self.start_coding_session,
            "start a coding session": self.start_coding_session,
            "review todays work": self.review_todays_work,
            "review today s work": self.review_todays_work,
            "review today work": self.review_todays_work,
        }
        handler = handlers.get(normalized)
        if handler is None:
            return None
        return handler()

    def start_coding_session(self) -> WorkflowRunResult:
        return self._run_workflow(
            "Start coding session",
            (
                ("Open Jarvis in VS Code", self.developer_tools.open_jarvis_in_vscode),
                ("Check git status", self.developer_tools.check_git_status),
                ("Run fast tests", self.developer_tools.run_fast_tests),
            ),
        )

    def review_todays_work(self) -> WorkflowRunResult:
        return self._run_workflow(
            "Review today's work",
            (
                ("Check git status", self.developer_tools.check_git_status),
                ("Show last commit", self.developer_tools.show_last_commit),
                ("Run fast tests", self.developer_tools.run_fast_tests),
            ),
        )

    @staticmethod
    def command_names() -> set[str]:
        return {
            "start coding session",
            "start a coding session",
            "review todays work",
            "review today s work",
            "review today work",
        }

    @staticmethod
    def _run_workflow(
        workflow_name: str,
        steps: tuple[tuple[str, Callable[[], DeveloperCommandResult]], ...],
    ) -> WorkflowRunResult:
        results = []
        for step_name, action in steps:
            results.append(WorkflowStepResult(name=step_name, result=action()))
        return WorkflowRunResult(workflow_name=workflow_name, steps=tuple(results))


def format_workflow_result(result: WorkflowRunResult) -> str:
    lines = [
        f"Workflow: {result.workflow_name}",
        f"Status: {'completed' if result.succeeded else 'needs attention'}",
        "",
        "Steps:",
    ]
    for step in result.steps:
        status = "OK" if step.succeeded else "FAILED"
        lines.append(f"- {step.name}: {status} - {_single_line(step.result.text)}")

    lines.extend(["", "Summary:", _workflow_summary(result)])
    return "\n".join(lines)


def normalize_workflow_command(command: str) -> str:
    lowered = command.casefold().replace("’", "'").replace("`", "'")
    without_punctuation = re.sub(r"[^a-z0-9\s]", " ", lowered)
    return " ".join(without_punctuation.split())


def _workflow_summary(result: WorkflowRunResult) -> str:
    if result.succeeded:
        return f"{result.workflow_name} completed. {_success_summary(result)}"
    failed = [step.name for step in result.steps if not step.succeeded]
    return f"{result.workflow_name} needs attention. Failed step(s): {', '.join(failed)}."


def _success_summary(result: WorkflowRunResult) -> str:
    status_step = _find_step(result, "Check git status")
    commit_step = _find_step(result, "Show last commit")
    tests_step = _find_step(result, "Run fast tests")
    parts = []
    if status_step is not None:
        parts.append(_single_line(status_step.result.text))
    if commit_step is not None:
        parts.append(f"Last commit: {_single_line(commit_step.result.text)}")
    if tests_step is not None:
        parts.append(_single_line(tests_step.result.text))
    return " ".join(parts) if parts else "All workflow steps completed."


def _find_step(result: WorkflowRunResult, name: str) -> WorkflowStepResult | None:
    for step in result.steps:
        if step.name == name:
            return step
    return None


def _single_line(text: str, max_chars: int = 180) -> str:
    compact = " ".join(line.strip() for line in text.splitlines() if line.strip())
    if not compact:
        return "No output."
    if len(compact) > max_chars:
        return compact[: max_chars - 3].rstrip() + "..."
    return compact
