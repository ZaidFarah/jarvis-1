from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


RISK_LEVELS = ("low", "medium", "high", "blocked")


@dataclass(frozen=True)
class PolicyRule:
    action_name: str
    risk_level: str
    description: str
    requires_confirmation: bool
    allowed: bool
    reason: str


def default_policies() -> list[PolicyRule]:
    return [
        PolicyRule("weather query", "low", "Fetch current weather for a known city.", False, True, "Allowed."),
        PolicyRule("list reminders", "low", "List reminders from local SQLite storage.", False, True, "Allowed."),
        PolicyRule("list whitelisted folder filenames", "low", "List filenames and metadata in an allowed folder.", False, True, "Allowed."),
        PolicyRule("open whitelisted website", "low", "Open a whitelisted website in the browser.", False, True, "Allowed."),
        PolicyRule("open whitelisted app", "low", "Launch a whitelisted local app.", False, True, "Allowed."),
        PolicyRule("read file contents", "medium", "Read file contents from a local file.", True, True, "Requires confirmation."),
        PolicyRule("send text to openai", "medium", "Send user text to OpenAI chat or TTS.", True, True, "Requires confirmation."),
        PolicyRule("create reminder", "medium", "Create a local reminder entry.", True, True, "Requires confirmation."),
        PolicyRule("show notification", "medium", "Display a local notification.", True, True, "Requires confirmation."),
        PolicyRule("register startup", "medium", "Register Jarvis for current-user Windows startup.", True, True, "Requires confirmation."),
        PolicyRule("unregister startup", "medium", "Remove Jarvis from current-user Windows startup.", True, True, "Requires confirmation."),
        PolicyRule("create backup", "medium", "Create a local backup archive.", True, True, "Requires confirmation."),
        PolicyRule("restore backup", "high", "Restore files from a local backup archive.", True, True, "Requires confirmation."),
        PolicyRule("send image to openai", "high", "Send an image to OpenAI for analysis.", True, True, "Requires confirmation."),
        PolicyRule("take screenshot", "high", "Capture a screenshot of the current screen.", True, True, "Requires confirmation."),
        PolicyRule("read screen text", "high", "Run OCR on a screenshot or image.", True, True, "Requires confirmation."),
        PolicyRule("analyze screenshot", "high", "Capture and analyze a screenshot with OpenAI.", True, True, "Requires confirmation."),
        PolicyRule("send email", "high", "Send an email.", True, True, "Requires confirmation."),
        PolicyRule("create calendar event", "high", "Create a calendar event.", True, True, "Requires confirmation."),
        PolicyRule("read emails", "high", "Read email content.", True, True, "Requires confirmation."),
        PolicyRule("read calendar", "high", "Read calendar content.", True, True, "Requires confirmation."),
        PolicyRule("delete files", "blocked", "Delete files from disk.", False, False, "Blocked by policy."),
        PolicyRule("modify files", "blocked", "Modify existing files on disk.", False, False, "Blocked by policy."),
        PolicyRule("run arbitrary terminal commands", "blocked", "Execute arbitrary shell commands.", False, False, "Blocked by policy."),
        PolicyRule("access passwords", "blocked", "Access passwords or secrets.", False, False, "Blocked by policy."),
        PolicyRule("access banking data", "blocked", "Access banking or payment data.", False, False, "Blocked by policy."),
        PolicyRule("open raw user-provided executable paths", "blocked", "Launch arbitrary user-supplied executable paths.", False, False, "Blocked by policy."),
    ]
