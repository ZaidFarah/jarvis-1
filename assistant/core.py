from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from assistant.conversation import ConversationHistory
from integrations.calendar_service import CalendarCreateResult, CalendarService, CalendarQueryResult
from integrations.weather_service import WeatherService
from memory.store import SensitiveMemoryError, SQLiteMemoryStore
from security.confirmation import ConfirmationResult
from config.settings import AppSettings, load_settings
from security.permissions import PermissionBroker
from tools.file_access import FileAccess, FileReadResult, FileSummaryResult
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
        calendar_service: CalendarService | None = None,
        reminder_service: ReminderService | None = None,
        confirmation_handler: Callable[[str, str, str], ConfirmationResult] | None = None,
    ) -> None:
        self.settings = settings or load_settings()
        self.permission_broker = PermissionBroker(self.settings)
        self.confirmation_handler = confirmation_handler
        self.openai_service = openai_service or OpenAIService(self.settings)
        self.weather_service = weather_service or WeatherService(self.settings)
        if calendar_service is not None:
            self.calendar_service = calendar_service
        elif self.settings.calendar_enabled:
            self.calendar_service = CalendarService(self.settings)
        else:
            self.calendar_service = None
        if self.settings.app_launcher_enabled:
            self.app_launcher = AppLauncher(self.settings)
        else:
            self.app_launcher = None
        if self.settings.website_launcher_enabled:
            self.website_launcher = WebsiteLauncher(self.settings)
        else:
            self.website_launcher = None
        if self.settings.file_access_enabled:
            self.file_access = FileAccess(self.settings)
        else:
            self.file_access = None
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

        calendar_response = self._handle_calendar_command(cleaned)
        if calendar_response is not None:
            return calendar_response

        file_access_response = self._handle_file_access_command(cleaned)
        if file_access_response is not None:
            return file_access_response

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
        self.permission_broker.check(
            "weather query",
            description=f"Weather lookup for {weather_city or self.settings.weather_default_city}.",
        )
        response = AssistantResponse(
            text=result.text,
            accepted=True,
            source="weather",
            error=result.safe_error,
        )
        self.conversation_history.add_user(command_text)
        self.conversation_history.add_assistant(response.text)
        return response

    def _handle_calendar_command(self, command: str) -> AssistantResponse | None:
        normalized = " ".join(command.lower().strip().split())
        create_request = self._parse_calendar_create_command(command)
        if create_request is not None:
            title, start_text, duration_minutes = create_request
            return self._create_calendar_event(title, start_text, duration_minutes)

        day_label = self._parse_calendar_day_label(normalized)
        if day_label is None:
            return None

        if self.calendar_service is None or not self.settings.calendar_enabled:
            return AssistantResponse(text="Calendar is disabled.", accepted=True, source="local")

        decision = self.permission_broker.check(
            "read calendar",
            description=f"Read calendar events for {day_label}.",
        )
        if not decision.allowed:
            return AssistantResponse(text=decision.reason, accepted=False, source="local", error=decision.reason)
        if self.confirmation_handler is None:
            return AssistantResponse(
                text="Confirmation is required before reading calendar events.",
                accepted=False,
                source="local",
                error="Confirmation handler is unavailable.",
            )

        confirmation = self.confirmation_handler(decision.action_name, decision.risk_level, decision.description)
        if not confirmation.approved:
            reason = confirmation.reason or "Calendar read canceled."
            return AssistantResponse(text=reason, accepted=False, source="local", error=reason)

        result = self.calendar_service.current_events(day_label)
        return AssistantResponse(
            text=self._calendar_response_text(result),
            accepted=result.success,
            source="calendar",
            error=result.safe_error,
        )

    def _create_calendar_event(self, title: str, start_text: str, duration_minutes: int, location: str | None = None, description: str | None = None) -> AssistantResponse:
        if self.calendar_service is None or not self.settings.calendar_enabled or not self.settings.calendar_create_enabled:
            return AssistantResponse(text="Calendar creation is disabled.", accepted=True, source="local")

        decision = self.permission_broker.check(
            "create calendar event",
            description=f"Create calendar event '{title}' at {start_text} for {duration_minutes} minutes.",
        )
        if not decision.allowed:
            return AssistantResponse(text=decision.reason, accepted=False, source="local", error=decision.reason)

        if self.confirmation_handler is None:
            return AssistantResponse(
                text="Confirmation is required before creating calendar events.",
                accepted=False,
                source="local",
                error="Confirmation handler is unavailable.",
            )

        confirmation = self.confirmation_handler(decision.action_name, decision.risk_level, decision.description)
        if not confirmation.approved:
            reason = confirmation.reason or "Calendar creation canceled."
            return AssistantResponse(text=reason, accepted=False, source="local", error=reason)

        result = self.calendar_service.create_event(title, start_text, duration_minutes, location=location, description=description)
        return AssistantResponse(
            text=self._calendar_create_response_text(result),
            accepted=result.success,
            source="calendar",
            error=result.safe_error,
        )

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

        self.permission_broker.check("open whitelisted app", description=f"Launch local app {app_name}.")
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

        self.permission_broker.check("open whitelisted website", description=f"Open site {site_name}.")
        result = self.website_launcher.open_site(site_name)
        return AssistantResponse(
            text=self._website_launcher_response_text(result),
            accepted=result.opened,
            source="website",
            error=result.safe_error,
        )

    def _handle_file_access_command(self, command: str) -> AssistantResponse | None:
        normalized = " ".join(command.lower().strip().split())
        if normalized in {"list documents", "list desktop", "list downloads"}:
            folder_name = normalized.removeprefix("list ").strip()
            if not self.settings.file_access_enabled or self.file_access is None:
                return AssistantResponse(text="File access is disabled.", accepted=True, source="local")
            self.permission_broker.check(
                "list whitelisted folder filenames",
                description=f"List files in {folder_name}.",
            )
            result = self.file_access.list_folder(folder_name)
            return AssistantResponse(
                text=self._file_listing_response_text(result),
                accepted=result.safe_error is None,
                source="file_access",
                error=result.safe_error,
            )

        read_match = re.match(r"(?i)^read file\s+(.+?)\s+in\s+(documents|desktop|downloads)$", command.strip())
        if read_match:
            filename = read_match.group(1).strip()
            folder_name = read_match.group(2).strip().lower()
            if self._looks_like_raw_path(filename):
                return AssistantResponse(
                    text="Please use a plain filename, not a path.",
                    accepted=False,
                    source="local",
                )
            if not self.settings.file_access_enabled or self.file_access is None:
                return AssistantResponse(text="File access is disabled.", accepted=True, source="local")
            return self._read_file(filename, folder_name)

        summarize_match = re.match(r"(?i)^summarize file\s+(.+?)\s+in\s+(documents|desktop|downloads)$", command.strip())
        if summarize_match:
            filename = summarize_match.group(1).strip()
            folder_name = summarize_match.group(2).strip().lower()
            if self._looks_like_raw_path(filename):
                return AssistantResponse(text="Please use a plain filename, not a path.", accepted=False, source="local")
            if not self.settings.file_access_enabled or self.file_access is None:
                return AssistantResponse(text="File access is disabled.", accepted=True, source="local")
            return self._summarize_file(filename, folder_name)

        match = re.match(r"(?i)^find file\s+(.+?)\s+in\s+(documents|desktop|downloads)$", command.strip())
        if not match:
            return None

        query = match.group(1).strip()
        folder_name = match.group(2).strip().lower()

        if self._looks_like_raw_path(query):
            return AssistantResponse(
                text="Please use a plain filename search term, not a path.",
                accepted=False,
                source="local",
            )

        if not self.settings.file_access_enabled or self.file_access is None:
            return AssistantResponse(text="File access is disabled.", accepted=True, source="local")

        result = self.file_access.find_file(query, folder_name)
        self.permission_broker.check(
            "list whitelisted folder filenames",
            description=f"Search files in {folder_name} for {query}.",
        )
        return AssistantResponse(
            text=self._file_search_response_text(result),
            accepted=result.request_attempted and not result.safe_error,
            source="file_access",
            error=result.safe_error,
        )

    def _read_file(self, filename: str, folder_name: str) -> AssistantResponse:
        if not self.settings.file_access_enabled or self.file_access is None:
            return AssistantResponse(text="File access is disabled.", accepted=True, source="local")
        if not self.settings.file_read_enabled:
            return AssistantResponse(text="File reading is disabled.", accepted=True, source="local")

        decision = self.permission_broker.check(
            "read file contents",
            description=f"Read file {filename} from {folder_name}.",
        )
        if not decision.allowed:
            return AssistantResponse(text=decision.reason, accepted=False, source="local", error=decision.reason)

        if decision.requires_confirmation and self.settings.confirmation_required:
            if self.confirmation_handler is None:
                return AssistantResponse(
                    text="Confirmation is required before reading file contents.",
                    accepted=False,
                    source="local",
                    error="Confirmation handler is unavailable.",
                )
            confirmation = self.confirmation_handler(decision.action_name, decision.risk_level, decision.description)
            if not confirmation.approved:
                reason = confirmation.reason or "Read canceled."
                return AssistantResponse(text=reason, accepted=False, source="local", error=reason)

        result: FileReadResult = self.file_access.read_file(filename, folder_name)
        if result.safe_error:
            return AssistantResponse(text=result.safe_error, accepted=False, source="file_access", error=result.safe_error)
        if result.content_preview is None:
            return AssistantResponse(text="I couldn't read that file.", accepted=False, source="file_access")
        return AssistantResponse(text=result.content_preview, accepted=True, source="file_access")

    def _summarize_file(self, filename: str, folder_name: str) -> AssistantResponse:
        if not self.settings.file_access_enabled or self.file_access is None:
            return AssistantResponse(text="File access is disabled.", accepted=True, source="local")
        if not self.settings.file_summary_enabled:
            return AssistantResponse(text="File summarization is disabled.", accepted=True, source="local")

        decision = self.permission_broker.check(
            "read file contents",
            description=f"Read file {filename} from {folder_name} for summarization.",
        )
        if not decision.allowed:
            return AssistantResponse(text=decision.reason, accepted=False, source="local", error=decision.reason)
        if decision.requires_confirmation and self.settings.confirmation_required:
            if self.confirmation_handler is None:
                return AssistantResponse(
                    text="Confirmation is required before reading file contents.",
                    accepted=False,
                    source="local",
                    error="Confirmation handler is unavailable.",
                )
            confirmation = self.confirmation_handler(decision.action_name, decision.risk_level, decision.description)
            if not confirmation.approved:
                reason = confirmation.reason or "Read canceled."
                return AssistantResponse(text=reason, accepted=False, source="local", error=reason)

        read_result = self.file_access.read_file(filename, folder_name)
        if read_result.safe_error:
            return AssistantResponse(text=read_result.safe_error, accepted=False, source="file_access", error=read_result.safe_error)

        if read_result.content_preview is None:
            return AssistantResponse(text="I couldn't read that file.", accepted=False, source="file_access")

        file_text = read_result.content_preview[: self.settings.file_summary_max_chars]
        openai_decision = self.permission_broker.check(
            "send text to openai",
            description=f"Summarize file {filename} from {folder_name} with OpenAI.",
        )
        if not openai_decision.allowed:
            return AssistantResponse(text=openai_decision.reason, accepted=False, source="local", error=openai_decision.reason)

        if openai_decision.requires_confirmation and self.settings.confirmation_required:
            if self.confirmation_handler is None:
                return AssistantResponse(
                    text="Confirmation is required before sending file content to OpenAI.",
                    accepted=False,
                    source="local",
                    error="Confirmation handler is unavailable.",
                )
            confirmation = self.confirmation_handler(openai_decision.action_name, openai_decision.risk_level, openai_decision.description)
            if not confirmation.approved:
                reason = confirmation.reason or "Summary canceled."
                return AssistantResponse(text=reason, accepted=False, source="local", error=reason)

        prompt = (
            f"Summarize this file clearly and concisely in a few short paragraphs.\n"
            f"File name: {filename}\n\n"
            f"{file_text}"
        )
        result = self.openai_service.chat(prompt, system_prompt=self.settings.system_prompt)
        if result.success and result.text:
            summary_text = result.text[: self.settings.file_summary_max_chars]
            return AssistantResponse(text=summary_text, accepted=True, source="openai")

        fallback_text = "OpenAI is unavailable, so I could not summarize the file."
        if result.safe_error:
            fallback_text = f"{fallback_text} {result.safe_error}"
        return AssistantResponse(text=fallback_text, accepted=False, source="local", error=result.safe_error or fallback_text)

    @staticmethod
    def _parse_calendar_day_label(command: str) -> str | None:
        normalized = " ".join(command.lower().strip().split())
        if normalized in {
            "what is on my calendar today",
            "show my calendar today",
            "what events do i have today",
        }:
            return "today"
        if normalized in {
            "what is on my calendar tomorrow",
            "show my calendar tomorrow",
            "what events do i have tomorrow",
        }:
            return "tomorrow"
        return None

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
            self.permission_broker.check("list reminders", description="Check due reminders from local storage.")
            result = self.reminder_service.check_due_reminders()
            return AssistantResponse(
                text=result.text,
                accepted=result.success,
                source="reminders",
                error=result.safe_error,
            )

        if normalized in {"list reminders", "show reminders"}:
            self.permission_broker.check("list reminders", description="List reminders from local storage.")
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
            self.permission_broker.check("create reminder", description=f"Create reminder {title}.")
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

    @staticmethod
    def _looks_like_raw_path(value: str) -> bool:
        cleaned = value.strip()
        if not cleaned:
            return False
        return bool(
            cleaned.startswith(("..", "/", "\\"))
            or re.match(r"^[a-zA-Z]:[\\/]", cleaned)
            or any(sep in cleaned for sep in ("\\", "/"))
        )

    @staticmethod
    def _calendar_response_text(result: CalendarQueryResult) -> str:
        if result.safe_error:
            return result.safe_error
        return result.text

    @staticmethod
    def _calendar_create_response_text(result: CalendarCreateResult) -> str:
        if result.safe_error:
            return result.safe_error
        return result.text

    @staticmethod
    def _parse_calendar_create_command(command: str) -> tuple[str, str, int] | None:
        match = re.match(
            r"(?i)^(?:create calendar event|schedule)\s+(.+?)\s+at\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\s+for\s+(\d+)\s*$",
            command.strip(),
        )
        if not match:
            return None

        title = " ".join(match.group(1).strip().split())
        start_text = " ".join(match.group(2).strip().split())
        duration_minutes = int(match.group(3))
        if not title:
            return None
        return title, start_text, duration_minutes

    @staticmethod
    def _file_listing_response_text(result) -> str:
        if result.safe_error:
            return result.safe_error
        if not result.entries:
            return f"No items found in {result.folder_name}."
        entries = ", ".join(entry.name for entry in result.entries[:8])
        suffix = "" if len(result.entries) <= 8 else f" and {len(result.entries) - 8} more"
        return f"Found {len(result.entries)} items in {result.folder_name}: {entries}{suffix}."

    @staticmethod
    def _file_search_response_text(result) -> str:
        if result.safe_error:
            return result.safe_error
        if not result.matches:
            return f"No files matching '{result.query}' were found in {result.folder_name}."
        matches = ", ".join(entry.name for entry in result.matches[:8])
        suffix = "" if len(result.matches) <= 8 else f" and {len(result.matches) - 8} more"
        return f"Found {len(result.matches)} matches in {result.folder_name}: {matches}{suffix}."
