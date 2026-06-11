from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from config.settings import AppSettings


_OPENAI_LOG_SINK_ID: int | None = None
_CHAT_LOG_SINK_ID: int | None = None


@dataclass(frozen=True)
class OpenAICheckReport:
    enabled: bool
    api_key_detected: bool
    model: str
    request_attempted: bool
    success: bool
    response_text: str
    safe_error: str | None
    log_file: Path
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        if not self.enabled:
            return True
        if not self.api_key_detected:
            return True
        return self.success


@dataclass(frozen=True)
class OpenAIChatResult:
    success: bool
    text: str
    used_openai: bool
    safe_error: str | None = None


class OpenAIService:
    """OpenAI diagnostics service.

    This class only checks connectivity. It is not wired into AssistantCore.
    """

    def __init__(
        self,
        settings: AppSettings,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.settings = settings
        self.client_factory = client_factory or self._default_client_factory
        self.log_file = self.settings.log_dir / "openai_diagnostics.log"
        self.chat_log_file = self.settings.log_dir / "chat.log"
        self.openai_logger = logger.bind(openai_diagnostics=True)
        self.chat_logger = logger.bind(chat=True)
        self._ensure_openai_log_sink()
        self._ensure_chat_log_sink()

    def run_check(self) -> OpenAICheckReport:
        enabled = self.settings.openai_enabled
        api_key_detected = self.settings.has_openai_api_key
        model = self.settings.openai_model

        self.openai_logger.info(
            "Running OpenAI diagnostic enabled={} api_key_detected={} model={}",
            enabled,
            api_key_detected,
            model,
        )

        if not enabled:
            return self._report(
                enabled=enabled,
                api_key_detected=api_key_detected,
                model=model,
                request_attempted=False,
                success=False,
                response_text="",
                safe_error=None,
                errors=[],
            )

        if not api_key_detected:
            message = "OpenAI is enabled, but OPENAI_API_KEY is not set."
            self.openai_logger.warning(message)
            return self._report(
                enabled=enabled,
                api_key_detected=False,
                model=model,
                request_attempted=False,
                success=False,
                response_text="",
                safe_error=message,
                errors=[message],
            )

        try:
            client = self.client_factory(api_key=self.settings.openai_api_key)
            response = client.responses.create(
                model=model,
                input="Reply with exactly: Jarvis OpenAI check OK.",
                max_output_tokens=20,
            )
            response_text = self._extract_response_text(response)
            self.openai_logger.info("OpenAI diagnostic request succeeded")
            return self._report(
                enabled=enabled,
                api_key_detected=api_key_detected,
                model=model,
                request_attempted=True,
                success=True,
                response_text=response_text,
                safe_error=None,
                errors=[],
            )
        except Exception as exc:
            safe_error = format_openai_error(exc)
            self.openai_logger.error("OpenAI diagnostic request failed: {}", safe_error)
            return self._report(
                enabled=enabled,
                api_key_detected=api_key_detected,
                model=model,
                request_attempted=True,
                success=False,
                response_text="",
                safe_error=safe_error,
                errors=[safe_error],
            )

    def chat(self, user_text: str, system_prompt: str | None = None) -> OpenAIChatResult:
        cleaned = user_text.strip()
        if not cleaned:
            return OpenAIChatResult(
                success=False,
                text="",
                used_openai=False,
                safe_error="Cannot send an empty message to OpenAI.",
            )

        if not self.settings.openai_enabled:
            self.chat_logger.info("OpenAI chat fallback: OpenAI disabled")
            return OpenAIChatResult(
                success=False,
                text="",
                used_openai=False,
                safe_error="OpenAI is disabled.",
            )

        if not self.settings.has_openai_api_key:
            self.chat_logger.warning("OpenAI chat fallback: missing API key")
            return OpenAIChatResult(
                success=False,
                text="",
                used_openai=False,
                safe_error="OpenAI is enabled, but OPENAI_API_KEY is not set.",
            )

        prompt = system_prompt or self.settings.system_prompt
        try:
            client = self.client_factory(api_key=self.settings.openai_api_key)
            self.chat_logger.info(
                "Sending OpenAI chat request model={} prompt_chars={} user_chars={}",
                self.settings.openai_model,
                len(prompt),
                len(cleaned),
            )
            response = client.responses.create(
                model=self.settings.openai_model,
                instructions=prompt,
                input=cleaned,
                max_output_tokens=400,
            )
            text = self._extract_response_text(response)
            if not text:
                raise RuntimeError("OpenAI returned an empty response.")
            self.chat_logger.info("OpenAI chat request succeeded response_chars={}", len(text))
            return OpenAIChatResult(success=True, text=text, used_openai=True)
        except Exception as exc:
            safe_error = format_openai_error(exc)
            self.chat_logger.error("OpenAI chat request failed: {}", safe_error)
            return OpenAIChatResult(success=False, text="", used_openai=False, safe_error=safe_error)

    def _report(
        self,
        enabled: bool,
        api_key_detected: bool,
        model: str,
        request_attempted: bool,
        success: bool,
        response_text: str,
        safe_error: str | None,
        errors: list[str],
    ) -> OpenAICheckReport:
        return OpenAICheckReport(
            enabled=enabled,
            api_key_detected=api_key_detected,
            model=model,
            request_attempted=request_attempted,
            success=success,
            response_text=response_text,
            safe_error=safe_error,
            log_file=self.log_file,
            errors=errors,
        )

    @staticmethod
    def _default_client_factory(api_key: str) -> Any:
        from openai import OpenAI

        return OpenAI(api_key=api_key)

    @staticmethod
    def _extract_response_text(response: Any) -> str:
        output_text = getattr(response, "output_text", None)
        if output_text:
            return str(output_text).strip()
        return ""

    def _ensure_openai_log_sink(self) -> None:
        global _OPENAI_LOG_SINK_ID
        if _OPENAI_LOG_SINK_ID is not None:
            return

        self.settings.log_dir.mkdir(parents=True, exist_ok=True)
        _OPENAI_LOG_SINK_ID = logger.add(
            self.log_file,
            level="DEBUG",
            rotation="1 MB",
            retention="7 days",
            encoding="utf-8",
            backtrace=False,
            diagnose=False,
            filter=lambda record: bool(record["extra"].get("openai_diagnostics")),
        )

    def _ensure_chat_log_sink(self) -> None:
        global _CHAT_LOG_SINK_ID
        if _CHAT_LOG_SINK_ID is not None:
            return

        self.settings.log_dir.mkdir(parents=True, exist_ok=True)
        _CHAT_LOG_SINK_ID = logger.add(
            self.chat_log_file,
            level="DEBUG",
            rotation="1 MB",
            retention="7 days",
            encoding="utf-8",
            backtrace=False,
            diagnose=False,
            filter=lambda record: bool(record["extra"].get("chat")),
        )


def format_openai_error(error: Exception) -> str:
    error_type = type(error).__name__
    message = str(error).strip() or "No error details provided."
    return f"{error_type}: {_redact_secret_like_text(message)}"


def format_openai_check_report(report: OpenAICheckReport) -> str:
    lines = [
        "Jarvis OpenAI Check",
        "===================",
        f"OpenAI enabled: {_yes_no(report.enabled)}",
        f"API key detected: {_yes_no(report.api_key_detected)}",
        f"model: {report.model}",
        f"diagnostic log: {report.log_file}",
        f"request attempted: {_yes_no(report.request_attempted)}",
        f"request success: {_yes_no(report.success)}",
    ]

    if report.response_text:
        lines.extend(["", "Response:", f"  {report.response_text}"])

    if report.safe_error:
        lines.extend(["", "Error:", f"  {report.safe_error}"])

    return "\n".join(lines)


def _redact_secret_like_text(text: str) -> str:
    redacted_words: list[str] = []
    for word in text.split():
        if word.startswith("sk-") or "OPENAI_API_KEY" in word:
            redacted_words.append("[redacted]")
        else:
            redacted_words.append(word)
    return " ".join(redacted_words)


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
