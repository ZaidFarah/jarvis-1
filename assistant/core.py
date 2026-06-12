from __future__ import annotations

import re
from dataclasses import dataclass

from assistant.conversation import ConversationHistory
from integrations.weather_service import WeatherService
from memory.store import SensitiveMemoryError, SQLiteMemoryStore
from config.settings import AppSettings, load_settings
from tools.app_launcher import AppLauncher
from tools.website_launcher import WebsiteLauncher
from reminders.service import ReminderService
from services.openai_service import OpenAIService


@dataclass(frozen=True)
class AssistantResponse:
    text: str
    accepted: bool = True
    source: str = "fallback"
    error: str | None = None


class AssistantCore:
    """Assistant routing core.

    Phase 7 supports OpenAI chat responses with a local placeholder fallback.
    """

    placeholder = "Jarvis foundation is running. OpenAI is disabled or unavailable, so local fallback is active."

    def __init__(
        self,
        settings: AppSettings | None = None,
        openai_service: OpenAIService | None = None,
        memory_store: SQLiteMemoryStore | None = None,
        weather_service: WeatherService | None = None,
        reminder_service: ReminderService | None = None,
    ) -> None:
        self.settings = settings or load_settings()
        self.openai_service = openai_service or OpenAIService(self.settings)
        self.weather_service = weather_service or WeatherService(self.settings)
        if self.settings.app_launcher_enabled:
            self.app_launcher = AppLauncher(self.settings)
        else:
            self.app_launcher = None
        if self.settings.website_launcher_enabled:
            self.website_launcher = WebsiteLauncher(self.settings)
        else:
            self.website_launcher = None
        if reminder_service is not None:
            self.reminder_service = reminder_service
        elif self.settings.reminders_enabled:
            self.reminder_service = ReminderService(self.settings)
        else:
            self.reminder_service = None
        self.conversation_history = ConversationHistory(
            enabled=self.settings.conversation_history_enabled,
            max_messages=self.settings.conversation_history_max_messages,
        )
        if memory_store is not None:
            self.memory_store = memory_store
        elif self.settings.memory_enabled:
            self.memory_store = SQLiteMemoryStore(self.settings.memory_database_path)
        else:
            self.memory_store = None

    def reset_conversation(self) -> None:
        self.conversation_history.reset()

    def handle_command(self, command: str) -> AssistantResponse:
        cleaned = command.strip()
        if not cleaned:
            return AssistantResponse(text="Please enter a command first.", accepted=False)

        if cleaned.lower() == "reset conversation":
            self.reset_conversation()
            return AssistantResponse(text="Conversation history cleared.", accepted=True, source="local")

        weather_response = self._handle_weather_command(cleaned)
        if weather_response is not None:
            return weather_response

        app_launch_response = self._handle_app_launcher_command(cleaned)
        if app_launch_response is not None:
            return app_launch_response

        website_response = self._handle_website_command(cleaned)
        if website_response is not None:
            return website_response

        reminder_response = self._handle_reminder_command(cleaned)
        if reminder_response is not None:
            return reminder_response

        memory_response = self._handle_memory_command(cleaned)
        if memory_response is not None:
            return memory_response

        history_context = self.conversation_history.format_recent_history()
        self.conversation_history.add_user(cleaned)

        try:
            chat_result = self.openai_service.chat(
                cleaned,
                system_prompt=self.settings.system_prompt,
                conversation_history=history_context or None,
            )
        except Exception as exc:
            response = self._fallback_response(cleaned, error=f"{type(exc).__name__}: {exc}")
            self.conversation_history.add_assistant(response.text)
            return response

        if chat_result.success and chat_result.text:
            response = AssistantResponse(text=chat_result.text, accepted=True, source="openai")
            self.conversation_history.add_assistant(response.text)
            return response

        response = self._fallback_response(cleaned, error=chat_result.safe_error)
        self.conversation_history.add_assistant(response.text)
        return response

    def _fallback_response(self, command: str, error: str | None = None) -> AssistantResponse:
        return AssistantResponse(
            text=f"{self.placeholder} You said: {command}",
            accepted=True,
            source="fallback",
            error=error,
        )

    def _handle_memory_command(self, command: str) -> AssistantResponse | None:
        normalized = " ".join(command.lower().strip().split())

        remember_match = re.match(r"(?i)^remember that\s+(.+)$", command.strip())
        if remember_match:
            return self._remember_fact(remember_match.group(1))
        if normalized == "what do you remember":
            return self._list_memories()
        forget_match = re.match(r"(?i)^forget that\s+(.+)$", command.strip())
        if forget_match:
            return self._forget_fact(forget_match.group(1))
        if normalized == "reset memory":
            return self._reset_memory()
        return None

    def _handle_weather_command(self, command: str) -> AssistantResponse | None:
        command_text = command.strip()
        normalized = " ".join(command_text.lower().split())

        weather_city: str | None = None
        if normalized in {"what is the weather", "what's the weather", "weather today"}:
            weather_city = None
        else:
            match = re.match(
                r"(?i)^(?:what(?:'s| is) the weather|weather today)\s+in\s+(.+)$",
                command_text,
            )
            if match:
                weather_city = match.group(1).strip()
            else:
                return None

        result = self.weather_service.current_weather(weather_city)
        response = AssistantResponse(
            text=result.text,
            accepted=True,
            source="weather",
            error=result.safe_error,
        )
        self.conversation_history.add_user(command_text)
        self.conversation_history.add_assistant(response.text)
        return response

    def _handle_app_launcher_command(self, command: str) -> AssistantResponse | None:
        match = re.match(r"(?i)^(open|launch)\s+(.+)$", command.strip())
        if not match:
            return None

        verb = match.group(1).strip().lower()
        app_name = match.group(2).strip().lower()
        if app_name not in self.settings.app_launcher_allowed_apps_map:
            if verb == "open":
                return None
            return AssistantResponse(text=f"App '{app_name}' is not allowed.", accepted=True, source="local")

        if not self.settings.app_launcher_enabled or self.app_launcher is None:
            return AssistantResponse(text="App launcher is disabled.", accepted=True, source="local")

        result = self.app_launcher.launch_app(app_name)
        return AssistantResponse(text=self._app_launcher_response_text(result), accepted=result.launched, source="launcher", error=result.safe_error)

    def _handle_website_command(self, command: str) -> AssistantResponse | None:
        match = re.match(r"(?i)^open\s+(.+)$", command.strip())
        if not match:
            return None

        site_name = match.group(1).strip().lower()
        if self._looks_like_raw_url(site_name):
            return AssistantResponse(
                text="Please use a whitelisted site name, not a raw URL.",
                accepted=False,
                source="local",
            )

        if site_name not in self.settings.website_allowed_sites_map:
            return AssistantResponse(text=f"Site '{site_name}' is not allowed.", accepted=True, source="local")

        if not self.settings.website_launcher_enabled or self.website_launcher is None:
            return AssistantResponse(text="Website launcher is disabled.", accepted=True, source="local")

        result = self.website_launcher.open_site(site_name)
        return AssistantResponse(
            text=self._website_launcher_response_text(result),
            accepted=result.opened,
            source="website",
            error=result.safe_error,
        )

    def _handle_reminder_command(self, command: str) -> AssistantResponse | None:
        if not self.settings.reminders_enabled or self.reminder_service is None:
            normalized = " ".join(command.lower().strip().split())
            if (
                normalized.startswith("remind me to ")
                or normalized in {"list reminders", "show reminders"}
                or normalized.startswith("cancel reminder ")
                or normalized.startswith("complete reminder ")
                or ReminderService.is_due_reminder_command(command)
            ):
                return AssistantResponse(text="Reminders are disabled.", accepted=True, source="local")
            return None

        normalized = " ".join(command.lower().strip().split())
        if ReminderService.is_due_reminder_command(command):
            result = self.reminder_service.check_due_reminders()
            return AssistantResponse(
                text=result.text,
                accepted=result.success,
                source="reminders",
                error=result.safe_error,
            )

        if normalized in {"list reminders", "show reminders"}:
            result = self.reminder_service.list_reminders()
            return AssistantResponse(text=result.text, accepted=result.success, source="reminders", error=result.safe_error)

        if normalized.startswith("cancel reminder "):
            reminder_id = self._parse_reminder_id(normalized.removeprefix("cancel reminder "))
            if reminder_id is None:
                return AssistantResponse(
                    text="Please provide a numeric reminder id.",
                    accepted=False,
                    source="reminders",
                )
            result = self.reminder_service.cancel_reminder(reminder_id)
            return AssistantResponse(text=result.text, accepted=result.success, source="reminders", error=result.safe_error)

        if normalized.startswith("complete reminder "):
            reminder_id = self._parse_reminder_id(normalized.removeprefix("complete reminder "))
            if reminder_id is None:
                return AssistantResponse(
                    text="Please provide a numeric reminder id.",
                    accepted=False,
                    source="reminders",
                )
            result = self.reminder_service.complete_reminder(reminder_id)
            return AssistantResponse(text=result.text, accepted=result.success, source="reminders", error=result.safe_error)

        try:
            title, remind_at_text = self.reminder_service.parse_reminder_command(command)
        except ValueError:
            return None

        if normalized.startswith("remind me to "):
            result = self.reminder_service.create_reminder(title, remind_at_text)
            return AssistantResponse(text=result.text, accepted=result.success, source="reminders", error=result.safe_error)

        return None

    def _remember_fact(self, fact: str) -> AssistantResponse:
        if not self.settings.memory_enabled or self.memory_store is None:
            return AssistantResponse(text="Memory is disabled.", accepted=True, source="local")

        if not fact.strip():
            return AssistantResponse(text="Please say what you want me to remember.", accepted=False, source="local")

        try:
            entry = self.memory_store.remember(fact, source="explicit")
        except SensitiveMemoryError as exc:
            return AssistantResponse(text=str(exc), accepted=False, source="local", error=str(exc))
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            return AssistantResponse(text="I couldn't store that memory.", accepted=False, source="local", error=error)

        return AssistantResponse(
            text=f"I'll remember that: {entry.text}",
            accepted=True,
            source="local",
        )

    def _list_memories(self) -> AssistantResponse:
        if not self.settings.memory_enabled or self.memory_store is None:
            return AssistantResponse(text="Memory is disabled.", accepted=True, source="local")

        memories = self.memory_store.list_memories()
        if not memories:
            return AssistantResponse(text="I don't remember anything yet.", accepted=True, source="local")

        lines = ["Here is what I remember:"]
        lines.extend(f"{index}. {entry.text}" for index, entry in enumerate(memories, start=1))
        return AssistantResponse(text="\n".join(lines), accepted=True, source="local")

    def _forget_fact(self, fact: str) -> AssistantResponse:
        if not self.settings.memory_enabled or self.memory_store is None:
            return AssistantResponse(text="Memory is disabled.", accepted=True, source="local")

        if not fact.strip():
            return AssistantResponse(text="Please say what you want me to forget.", accepted=False, source="local")

        removed = self.memory_store.forget(fact)
        if removed:
            return AssistantResponse(text=f"I forgot that: {fact.strip()}", accepted=True, source="local")
        return AssistantResponse(text="I couldn't find that memory.", accepted=True, source="local")

    def _reset_memory(self) -> AssistantResponse:
        if not self.settings.memory_enabled or self.memory_store is None:
            return AssistantResponse(text="Memory is disabled.", accepted=True, source="local")

        removed = self.memory_store.reset()
        return AssistantResponse(text=f"Memory cleared. Removed {removed} memories.", accepted=True, source="local")

    @staticmethod
    def _parse_reminder_id(value: str) -> int | None:
        cleaned = value.strip()
        if not cleaned.isdigit():
            return None
        return int(cleaned)

    @staticmethod
    def _app_launcher_response_text(result) -> str:
        if result.launched:
            return f"Launched {result.app_name}."
        if result.fallback_reason:
            return result.fallback_reason
        if result.safe_error:
            return result.safe_error
        return f"Unable to launch {result.app_name}."

    @staticmethod
    def _website_launcher_response_text(result) -> str:
        if result.opened:
            return f"Opened {result.site_name}."
        if result.fallback_reason:
            return result.fallback_reason
        if result.safe_error:
            return result.safe_error
        return f"Unable to open {result.site_name}."

    @staticmethod
    def _looks_like_raw_url(value: str) -> bool:
        cleaned = value.strip().lower()
        return bool(re.match(r"^(https?://|www\.)", cleaned) or any(sep in cleaned for sep in ("://", "/", "\\", "?", "#", "&", "=")) or "." in cleaned)
