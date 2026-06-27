from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from config.settings import AppSettings


@dataclass(frozen=True)
class AgentToolDescriptor:
    name: str
    description: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentRoute:
    tool_name: str
    reason: str
    matched_phrase: str | None = None


def build_default_tool_registry(settings: AppSettings | None = None) -> dict[str, AgentToolDescriptor]:
    settings = settings or AppSettings(_env_file=None)
    return {
        "weather": AgentToolDescriptor("weather", "Weather lookup and diagnostics."),
        "reminders": AgentToolDescriptor("reminders", "List, create, and check reminders."),
        "app_launcher": AgentToolDescriptor("app_launcher", "Launch allowed local apps."),
        "website_launcher": AgentToolDescriptor("website_launcher", "Open allowed websites."),
        "file_access": AgentToolDescriptor("file_access", "List, read, and summarize whitelisted files."),
        "calendar": AgentToolDescriptor("calendar", "Read or create calendar events."),
        "gmail": AgentToolDescriptor("gmail", "Read or manage Gmail drafts and unread mail."),
        "vision": AgentToolDescriptor("vision", "Screenshot, OCR, and OpenAI vision analysis."),
        "workflows": AgentToolDescriptor("workflows", "Run fixed local multi-step workflows."),
        "chat": AgentToolDescriptor("chat", "Fallback OpenAI chat."),
    }


class AgentRouter:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.tool_registry = build_default_tool_registry(settings)
        self._website_names = set(self.settings.website_allowed_sites_map)
        self._app_names = set(self.settings.app_launcher_allowed_apps_map)

    def route(self, user_input: str, conversation_history: str = "") -> AgentRoute:
        cleaned = " ".join(user_input.strip().split())
        normalized = cleaned.lower()
        del conversation_history

        if self._matches_weather(normalized):
            return AgentRoute("weather", "Matched weather keywords.", matched_phrase=cleaned)
        if self._matches_reminders(normalized):
            return AgentRoute("reminders", "Matched reminder keywords.", matched_phrase=cleaned)
        if self._matches_workflows(normalized):
            return AgentRoute("workflows", "Matched workflow keywords.", matched_phrase=cleaned)
        if self._matches_vision(normalized):
            return AgentRoute("vision", "Matched vision keywords.", matched_phrase=cleaned)
        if self._matches_calendar(normalized):
            return AgentRoute("calendar", "Matched calendar keywords.", matched_phrase=cleaned)
        if self._matches_gmail(normalized):
            return AgentRoute("gmail", "Matched Gmail keywords.", matched_phrase=cleaned)
        if self._matches_file_access(normalized):
            return AgentRoute("file_access", "Matched file access keywords.", matched_phrase=cleaned)
        if self._matches_website(normalized):
            return AgentRoute("website_launcher", "Matched website launcher keywords.", matched_phrase=cleaned)
        if self._matches_app_launcher(normalized):
            return AgentRoute("app_launcher", "Matched app launcher keywords.", matched_phrase=cleaned)
        return AgentRoute("chat", "No tool matched; falling back to chat.", matched_phrase=cleaned or None)

    def _matches_weather(self, normalized: str) -> bool:
        return bool(
            normalized in {"what is the weather", "what's the weather", "weather today"}
            or re.match(r"^(?:what(?:'s| is) the weather|weather today)\s+in\s+.+$", normalized)
            or normalized.startswith("weather in ")
        )

    def _matches_reminders(self, normalized: str) -> bool:
        reminder_prefixes = (
            "remind me to ",
            "list reminders",
            "show reminders",
            "cancel reminder ",
            "complete reminder ",
            "due reminders",
            "check reminders",
        )
        return normalized.startswith(reminder_prefixes) if isinstance(reminder_prefixes, tuple) else False

    def _matches_workflows(self, normalized: str) -> bool:
        cleaned = re.sub(r"[^a-z0-9\s]", " ", normalized.replace("’", "'"))
        compact = " ".join(cleaned.split())
        return compact in {
            "start coding session",
            "start a coding session",
            "review todays work",
            "review today s work",
            "review today work",
        }

    def _matches_vision(self, normalized: str) -> bool:
        return normalized in {
            "take screenshot",
            "read screen text",
            "analyze screenshot",
            "what is on my screen",
            "describe screen",
        }

    def _matches_calendar(self, normalized: str) -> bool:
        return bool(
            normalized.startswith(("create calendar event ", "schedule "))
            or normalized in {
                "what is on my calendar today",
                "show my calendar today",
                "what events do i have today",
                "what is on my calendar tomorrow",
                "show my calendar tomorrow",
                "what events do i have tomorrow",
            }
        )

    def _matches_gmail(self, normalized: str) -> bool:
        return bool(
            normalized in {
                "read my unread emails",
                "show unread emails",
                "check my gmail",
                "check my emails",
                "list email drafts",
                "show email drafts",
            }
            or normalized.startswith(("draft email to ", "create email draft to ", "send email draft "))
        )

    def _matches_file_access(self, normalized: str) -> bool:
        return bool(
            normalized.startswith(("list documents", "list desktop", "list downloads", "find file ", "read file ", "summarize file "))
        )

    def _matches_website(self, normalized: str) -> bool:
        website_names = self._website_names
        return bool(normalized.startswith("open ") and any(name in normalized for name in website_names))

    def _matches_app_launcher(self, normalized: str) -> bool:
        app_names = self._app_names
        if not normalized.startswith(("open ", "launch ")):
            return False
        return any(
            re.search(rf"\b{name}\b", normalized) for name in app_names
        )
