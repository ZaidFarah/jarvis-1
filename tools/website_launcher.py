from __future__ import annotations

import re
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Callable

from loguru import logger

from config.settings import AppSettings


_WEBSITE_LAUNCHER_LOG_SINK_ID: int | None = None


@dataclass(frozen=True)
class WebsiteLauncherCheckReport:
    enabled: bool
    allowed_sites: dict[str, str]
    log_file: Path
    safe_error: str | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        return True


@dataclass(frozen=True)
class WebsiteResolutionResult:
    enabled: bool
    site_name: str
    configured_url: str
    resolved_url: str | None
    allowed: bool
    configured: bool
    log_file: Path
    safe_error: str | None = None
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class WebsiteOpenResult:
    enabled: bool
    site_name: str
    allowed: bool
    configured: bool
    request_attempted: bool
    opened: bool
    configured_url: str | None
    resolved_url: str | None
    log_file: Path
    safe_error: str | None = None
    fallback_reason: str | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        if not self.enabled:
            return False
        return self.opened


class WebsiteLauncher:
    """Safe website launcher for whitelisted destinations only."""

    def __init__(self, settings: AppSettings, browser_open: Callable[..., object] | None = None) -> None:
        self.settings = settings
        self.browser_open = browser_open or webbrowser.open
        self.log_file = self.settings.log_dir / "website_launcher.log"
        self.website_launcher_logger = logger.bind(website_launcher=True)
        self._ensure_log_sink()

    @property
    def enabled(self) -> bool:
        return self.settings.website_launcher_enabled

    @property
    def allowed_sites(self) -> dict[str, str]:
        return self.settings.website_allowed_sites_map

    def run_check(self) -> WebsiteLauncherCheckReport:
        self.website_launcher_logger.info("Running website launcher diagnostic enabled={}", self.enabled)
        return WebsiteLauncherCheckReport(
            enabled=self.enabled,
            allowed_sites=self.allowed_sites,
            log_file=self.log_file,
        )

    def resolve_site(self, site_name: str) -> WebsiteResolutionResult:
        cleaned_name = self._clean_site_name(site_name)
        if self._looks_like_raw_url(cleaned_name):
            message = "Website launch requests must use a whitelisted site name."
            return WebsiteResolutionResult(
                enabled=self.enabled,
                site_name=cleaned_name,
                configured_url="",
                resolved_url=None,
                allowed=False,
                configured=False,
                log_file=self.log_file,
                safe_error=message,
                errors=[message],
            )

        configured_url = self.allowed_sites.get(cleaned_name, "")
        allowed = cleaned_name in self.allowed_sites
        configured = allowed and bool(configured_url.strip())
        safe_error: str | None = None
        resolved_url = configured_url if configured else None
        if not allowed:
            safe_error = f"Site '{cleaned_name}' is not allowed."
        elif not configured:
            safe_error = f"Site '{cleaned_name}' is not configured."

        return WebsiteResolutionResult(
            enabled=self.enabled,
            site_name=cleaned_name,
            configured_url=configured_url,
            resolved_url=resolved_url,
            allowed=allowed,
            configured=configured,
            log_file=self.log_file,
            safe_error=safe_error,
            errors=[safe_error] if safe_error else [],
        )

    def open_site(self, site_name: str) -> WebsiteOpenResult:
        resolution = self.resolve_site(site_name)
        cleaned_name = resolution.site_name
        self.website_launcher_logger.info(
            "Website launch request site={} configured_url={} resolved_url={}",
            cleaned_name,
            resolution.configured_url or "[not configured]",
            resolution.resolved_url or "[unresolved]",
        )

        if not self.enabled:
            message = "Website launcher is disabled."
            return self._open_result(
                site_name=cleaned_name,
                allowed=resolution.allowed,
                configured=resolution.configured,
                request_attempted=False,
                opened=False,
                configured_url=resolution.configured_url or None,
                resolved_url=resolution.resolved_url,
                safe_error=message,
                fallback_reason=message,
                errors=[],
            )

        if not resolution.allowed:
            message = resolution.safe_error or f"Site '{cleaned_name}' is not allowed."
            return self._open_result(
                site_name=cleaned_name,
                allowed=False,
                configured=False,
                request_attempted=False,
                opened=False,
                configured_url=None,
                resolved_url=None,
                safe_error=message,
                fallback_reason=message,
                errors=[message],
            )

        if not resolution.configured or resolution.resolved_url is None:
            message = resolution.safe_error or f"Site '{cleaned_name}' is not configured."
            return self._open_result(
                site_name=cleaned_name,
                allowed=True,
                configured=False,
                request_attempted=False,
                opened=False,
                configured_url=resolution.configured_url or None,
                resolved_url=None,
                safe_error=message,
                fallback_reason=message,
                errors=[message],
            )

        try:
            opened = bool(self.browser_open(resolution.resolved_url, new=0, autoraise=True))
            if opened:
                self.website_launcher_logger.info(
                    "Opened website site={} url={}",
                    cleaned_name,
                    resolution.resolved_url,
                )
                return self._open_result(
                    site_name=cleaned_name,
                    allowed=True,
                    configured=True,
                    request_attempted=True,
                    opened=True,
                    configured_url=resolution.configured_url,
                    resolved_url=resolution.resolved_url,
                    safe_error=None,
                    fallback_reason=None,
                    errors=[],
                )
            message = f"Browser reported it could not open '{cleaned_name}'."
            self.website_launcher_logger.warning(message)
            return self._open_result(
                site_name=cleaned_name,
                allowed=True,
                configured=True,
                request_attempted=True,
                opened=False,
                configured_url=resolution.configured_url,
                resolved_url=resolution.resolved_url,
                safe_error=message,
                fallback_reason=message,
                errors=[message],
            )
        except Exception as exc:  # pragma: no cover - defensive boundary
            safe_error = format_website_launcher_error(exc)
            self.website_launcher_logger.error("Website launch failed: {}", safe_error)
            return self._open_result(
                site_name=cleaned_name,
                allowed=True,
                configured=True,
                request_attempted=True,
                opened=False,
                configured_url=resolution.configured_url,
                resolved_url=resolution.resolved_url,
                safe_error=safe_error,
                fallback_reason=safe_error,
                errors=[safe_error],
            )

    def _open_result(
        self,
        site_name: str,
        allowed: bool,
        configured: bool,
        request_attempted: bool,
        opened: bool,
        configured_url: str | None,
        resolved_url: str | None,
        safe_error: str | None,
        fallback_reason: str | None,
        errors: list[str],
    ) -> WebsiteOpenResult:
        return WebsiteOpenResult(
            enabled=self.enabled,
            site_name=site_name,
            allowed=allowed,
            configured=configured,
            request_attempted=request_attempted,
            opened=opened,
            configured_url=configured_url,
            resolved_url=resolved_url,
            log_file=self.log_file,
            safe_error=safe_error,
            fallback_reason=fallback_reason,
            errors=errors,
        )

    def _ensure_log_sink(self) -> None:
        global _WEBSITE_LAUNCHER_LOG_SINK_ID
        if _WEBSITE_LAUNCHER_LOG_SINK_ID is not None:
            return

        self.settings.log_dir.mkdir(parents=True, exist_ok=True)
        _WEBSITE_LAUNCHER_LOG_SINK_ID = logger.add(
            self.log_file,
            level="DEBUG",
            rotation="1 MB",
            retention="7 days",
            encoding="utf-8",
            backtrace=False,
            diagnose=False,
            filter=lambda record: bool(record["extra"].get("website_launcher")),
        )

    @staticmethod
    def _clean_site_name(site_name: str) -> str:
        return " ".join(site_name.strip().split()).lower()

    @staticmethod
    def _looks_like_raw_url(value: str) -> bool:
        if not value:
            return False
        if re.match(r"^(https?://|www\.)", value):
            return True
        return any(sep in value for sep in ("://", "/", "\\", "?", "#", "&", "=")) or "." in value


def format_website_launcher_error(error: Exception) -> str:
    error_type = type(error).__name__
    message = str(error).strip() or "No error details provided."
    return f"{error_type}: {_redact_secret_like_text(message)}"


def format_website_launcher_check_report(report: WebsiteLauncherCheckReport) -> str:
    lines = [
        "Jarvis Website Check",
        "====================",
        f"Website launcher enabled: {_yes_no(report.enabled)}",
        f"Diagnostic log: {report.log_file}",
        "",
        "Allowed sites:",
    ]
    if report.allowed_sites:
        lines.extend(f"  {name} -> {url or '[not configured]'}" for name, url in report.allowed_sites.items())
    else:
        lines.append("  None configured.")
    if report.safe_error:
        lines.extend(["", "Error:", f"  {report.safe_error}"])
    return "\n".join(lines)


def format_website_open_report(result: WebsiteOpenResult) -> str:
    lines = [
        "Jarvis Website Open",
        "===================",
        f"Website launcher enabled: {_yes_no(result.enabled)}",
        f"Site: {result.site_name}",
        f"Allowed: {_yes_no(result.allowed)}",
        f"Configured: {_yes_no(result.configured)}",
        f"Request attempted: {_yes_no(result.request_attempted)}",
        f"Opened: {_yes_no(result.opened)}",
        f"Diagnostic log: {result.log_file}",
    ]
    if result.configured_url:
        lines.extend(["", f"Configured URL: {result.configured_url}"])
    if result.resolved_url:
        lines.extend(["", f"Resolved URL: {result.resolved_url}"])
    if result.fallback_reason:
        lines.extend(["", "Fallback reason:", f"  {result.fallback_reason}"])
    if result.safe_error:
        lines.extend(["", "Error:", f"  {result.safe_error}"])
    return "\n".join(lines)


def format_website_resolution_report(result: WebsiteResolutionResult) -> str:
    lines = [
        "Jarvis Website Resolution",
        "=========================",
        f"Website launcher enabled: {_yes_no(result.enabled)}",
        f"Site: {result.site_name}",
        f"Allowed: {_yes_no(result.allowed)}",
        f"Configured: {_yes_no(result.configured)}",
        f"Configured URL: {result.configured_url or '[not configured]'}",
        f"Diagnostic log: {result.log_file}",
    ]
    if result.resolved_url:
        lines.extend(["", f"Resolved URL: {result.resolved_url}"])
    if result.safe_error:
        lines.extend(["", "Error:", f"  {result.safe_error}"])
    return "\n".join(lines)


def _redact_secret_like_text(text: str) -> str:
    redacted_words: list[str] = []
    for word in text.split():
        if word.startswith("sk-") or "API_KEY" in word or "TOKEN" in word or "PASSWORD" in word:
            redacted_words.append("[redacted]")
        else:
            redacted_words.append(word)
    return " ".join(redacted_words)


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
