from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from loguru import logger
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout

from config.settings import AppSettings


_CONFIRMATIONS_LOG_SINK_ID: int | None = None


@dataclass(frozen=True)
class ConfirmationResult:
    approved: bool
    denied: bool
    timed_out: bool
    reason: str
    log_file: Path | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        return self.approved


class ConfirmationDialog(QDialog):
    """Simple modal confirmation dialog for sensitive Jarvis actions."""

    def __init__(self, action_name: str, risk_level: str, description: str, parent=None) -> None:
        super().__init__(parent)
        self.action_name = action_name
        self.risk_level = risk_level
        self.description = description
        self.approved = False
        self.denied = False
        self.timed_out = False
        self.reason = "Denied."

        self.setWindowTitle("Jarvis Confirmation")
        self.setModal(True)

        layout = QVBoxLayout(self)
        self.action_label = QLabel(f"Action: {action_name}")
        self.risk_label = QLabel(f"Risk level: {risk_level}")
        self.description_label = QLabel(description)
        self.description_label.setWordWrap(True)
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No)
        self.button_box.accepted.connect(self._approve)
        self.button_box.rejected.connect(self._deny)

        layout.addWidget(self.action_label)
        layout.addWidget(self.risk_label)
        layout.addWidget(self.description_label)
        layout.addWidget(self.button_box)

    def _approve(self) -> None:
        self.approved = True
        self.denied = False
        self.timed_out = False
        self.reason = "Approved."
        self.accept()

    def _deny(self) -> None:
        self.approved = False
        self.denied = True
        self.timed_out = False
        self.reason = "Denied."
        self.reject()


def confirm_action_cli(
    settings: AppSettings,
    action_description: str,
    timeout_seconds: int | None = None,
    input_func: Callable[[str], str] = input,
    output_func: Callable[[str], None] = print,
) -> ConfirmationResult:
    """Prompt for CLI confirmation with a safe default-deny timeout."""

    log_file = _ensure_log_sink(settings)
    if not settings.confirmation_required:
        confirmation_logger = logger.bind(confirmations=True)
        confirmation_logger.info("Confirmation skipped action={} because confirmations are disabled.", action_description)
        return ConfirmationResult(
            approved=True,
            denied=False,
            timed_out=False,
            reason="Confirmation is disabled.",
            log_file=log_file,
        )

    timeout = timeout_seconds if timeout_seconds is not None else settings.confirmation_timeout_seconds
    prompt = f"Allow Jarvis to {action_description}? yes/no"
    output_func(prompt)
    confirmation_logger = logger.bind(confirmations=True)
    confirmation_logger.info("Prompting for confirmation action={} timeout_seconds={}", action_description, timeout)

    response_queue: queue.Queue[str] = queue.Queue(maxsize=1)

    def _reader() -> None:
        try:
            response_queue.put(input_func(""), block=False)
        except Exception as exc:  # pragma: no cover - defensive boundary
            response_queue.put(format_confirmation_error(exc))

    reader = threading.Thread(target=_reader, daemon=True)
    reader.start()
    try:
        response = response_queue.get(timeout=timeout)
    except queue.Empty:
        result = ConfirmationResult(
            approved=False,
            denied=True,
            timed_out=True,
            reason=f"Timed out after {timeout} seconds.",
            log_file=log_file,
            errors=[f"Timed out after {timeout} seconds."],
        )
        confirmation_logger.warning("Confirmation timed out action={} timeout_seconds={}", action_description, timeout)
        return result

    cleaned = response.strip().lower()
    approved = cleaned in {"y", "yes"}
    denied = cleaned in {"n", "no", ""}
    if approved:
        result = ConfirmationResult(approved=True, denied=False, timed_out=False, reason="Approved.", log_file=log_file)
        confirmation_logger.info("Confirmation approved action={}", action_description)
        return result

    result = ConfirmationResult(
        approved=False,
        denied=True,
        timed_out=False,
        reason="Denied.",
        log_file=log_file,
        errors=["Denied."],
    )
    confirmation_logger.info("Confirmation denied action={}", action_description)
    return result


def confirm_action_gui(
    action_name: str,
    risk_level: str,
    description: str,
    parent=None,
) -> ConfirmationResult:
    dialog = ConfirmationDialog(action_name, risk_level, description, parent=parent)
    dialog.exec()
    return ConfirmationResult(
        approved=dialog.approved,
        denied=dialog.denied,
        timed_out=dialog.timed_out,
        reason=dialog.reason,
        errors=[] if dialog.approved else [dialog.reason],
    )


def format_confirmation_result(result: ConfirmationResult) -> str:
    lines = [
        "Jarvis Confirmation Result",
        "==========================",
        f"Approved: {_yes_no(result.approved)}",
        f"Denied: {_yes_no(result.denied)}",
        f"Timed out: {_yes_no(result.timed_out)}",
        f"Reason: {result.reason}",
    ]
    if result.log_file:
        lines.append(f"Diagnostic log: {result.log_file}")
    return "\n".join(lines)


def format_confirmation_error(error: Exception) -> str:
    error_type = type(error).__name__
    message = str(error).strip() or "No error details provided."
    return f"{error_type}: {message}"


def _ensure_log_sink(settings: AppSettings) -> Path:
    global _CONFIRMATIONS_LOG_SINK_ID
    log_file = settings.log_dir / "confirmations.log"
    if _CONFIRMATIONS_LOG_SINK_ID is not None:
        return log_file

    settings.log_dir.mkdir(parents=True, exist_ok=True)
    _CONFIRMATIONS_LOG_SINK_ID = logger.add(
        log_file,
        level="DEBUG",
        rotation="1 MB",
        retention="7 days",
        encoding="utf-8",
        backtrace=False,
        diagnose=False,
        filter=lambda record: bool(record["extra"].get("confirmations")),
    )
    return log_file


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
