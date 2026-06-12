from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

from config.settings import AppSettings
from security.policies import PolicyRule, default_policies


_PERMISSIONS_LOG_SINK_ID: int | None = None


@dataclass(frozen=True)
class PermissionDecision:
    action_name: str
    risk_level: str
    description: str
    requires_confirmation: bool
    allowed: bool
    reason: str
    log_file: Path
    policy_name: str | None = None
    safe_error: str | None = None
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PermissionCheckReport:
    enabled: bool
    decisions: list[PermissionDecision]
    log_file: Path
    safe_error: str | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        return True


class PermissionBroker:
    """Central policy classifier for sensitive actions."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.log_file = self.settings.log_dir / "permissions.log"
        self.permission_logger = logger.bind(permissions=True)
        self._ensure_log_sink()
        self._policies = {policy.action_name: policy for policy in default_policies()}

    def check(self, action_name: str, description: str | None = None) -> PermissionDecision:
        normalized = self._normalize_action(action_name)
        policy = self._policies.get(normalized)
        if policy is None:
            policy = PolicyRule(
                action_name=normalized,
                risk_level="medium",
                description=description or "Unknown action.",
                requires_confirmation=True,
                allowed=False,
                reason="Unknown action defaults to confirmation required.",
            )

        decision = PermissionDecision(
            action_name=normalized,
            risk_level=policy.risk_level,
            description=description or policy.description,
            requires_confirmation=policy.requires_confirmation,
            allowed=policy.allowed,
            reason=policy.reason,
            log_file=self.log_file,
            policy_name=policy.action_name,
            safe_error=None if policy.allowed else policy.reason,
            errors=[] if policy.allowed else [policy.reason],
        )
        self.permission_logger.info(
            "Permission decision action={} risk_level={} allowed={} requires_confirmation={} reason={}",
            decision.action_name,
            decision.risk_level,
            decision.allowed,
            decision.requires_confirmation,
            decision.reason,
        )
        return decision

    def run_check(self) -> PermissionCheckReport:
        decisions = [self.check(policy.action_name, policy.description) for policy in default_policies()]
        return PermissionCheckReport(enabled=True, decisions=decisions, log_file=self.log_file)

    def _ensure_log_sink(self) -> None:
        global _PERMISSIONS_LOG_SINK_ID
        if _PERMISSIONS_LOG_SINK_ID is not None:
            return

        self.settings.log_dir.mkdir(parents=True, exist_ok=True)
        _PERMISSIONS_LOG_SINK_ID = logger.add(
            self.log_file,
            level="DEBUG",
            rotation="1 MB",
            retention="7 days",
            encoding="utf-8",
            backtrace=False,
            diagnose=False,
            filter=lambda record: bool(record["extra"].get("permissions")),
        )

    @staticmethod
    def _normalize_action(action_name: str) -> str:
        return " ".join(action_name.strip().split()).lower()


def format_permission_check_report(report: PermissionCheckReport) -> str:
    lines = [
        "Jarvis Permission Check",
        "=======================",
        f"Diagnostic log: {report.log_file}",
        "",
        "Policy decisions:",
    ]
    for decision in report.decisions:
        lines.append(
            f"  {decision.action_name} | risk={decision.risk_level} | allowed={_yes_no(decision.allowed)} | confirmation={_yes_no(decision.requires_confirmation)}"
        )
    return "\n".join(lines)


def format_permission_decision(decision: PermissionDecision) -> str:
    lines = [
        "Jarvis Permission Decision",
        "==========================",
        f"Action: {decision.action_name}",
        f"Risk level: {decision.risk_level}",
        f"Allowed: {_yes_no(decision.allowed)}",
        f"Requires confirmation: {_yes_no(decision.requires_confirmation)}",
        f"Reason: {decision.reason}",
        f"Diagnostic log: {decision.log_file}",
    ]
    if decision.safe_error:
        lines.extend(["", "Error:", f"  {decision.safe_error}"])
    return "\n".join(lines)


def format_permission_error(error: Exception) -> str:
    error_type = type(error).__name__
    message = str(error).strip() or "No error details provided."
    return f"{error_type}: {message}"


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
