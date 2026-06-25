from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote_plus
import webbrowser

from config.settings import AppSettings
from tools.website_launcher import WebsiteLauncher, WebsiteOpenResult


@dataclass(frozen=True)
class BrowserSearchResult:
    enabled: bool
    provider: str
    query: str
    resolved_url: str | None
    opened: bool
    log_file: Path
    safe_error: str | None = None
    fallback_reason: str | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        return self.enabled and self.opened


class BrowserControl:
    """Safe browser actions for whitelisted sites and fixed search providers."""

    _SEARCH_URLS = {
        "google": "https://www.google.com/search?q={query}",
        "youtube": "https://www.youtube.com/results?search_query={query}",
    }

    def __init__(self, settings: AppSettings, browser_open: Callable[..., object] | None = None) -> None:
        self.settings = settings
        self.browser_open = browser_open or webbrowser.open
        self.website_launcher = WebsiteLauncher(settings, browser_open=self.browser_open)
        self.log_file = self.settings.log_dir / "browser_control.log"

    @property
    def enabled(self) -> bool:
        return self.settings.website_launcher_enabled

    def open_site(self, site_name: str) -> WebsiteOpenResult:
        return self.website_launcher.open_site(site_name)

    def search_google(self, query: str) -> BrowserSearchResult:
        return self.search("google", query)

    def search_youtube(self, query: str) -> BrowserSearchResult:
        return self.search("youtube", query)

    def search(self, provider: str, query: str) -> BrowserSearchResult:
        cleaned_provider = self._clean_provider_name(provider)
        cleaned_query = " ".join(query.strip().split())
        if not self.enabled:
            message = "Website launcher is disabled."
            return self._result(
                provider=cleaned_provider,
                query=cleaned_query,
                resolved_url=None,
                opened=False,
                safe_error=message,
                fallback_reason=message,
                errors=[message],
            )

        if cleaned_provider not in self._SEARCH_URLS:
            message = f"Search provider '{cleaned_provider}' is not allowed."
            return self._result(
                provider=cleaned_provider,
                query=cleaned_query,
                resolved_url=None,
                opened=False,
                safe_error=message,
                fallback_reason=message,
                errors=[message],
            )

        if not cleaned_query:
            message = "Please provide something to search for."
            return self._result(
                provider=cleaned_provider,
                query=cleaned_query,
                resolved_url=None,
                opened=False,
                safe_error=message,
                fallback_reason=message,
                errors=[message],
            )

        encoded_query = quote_plus(cleaned_query)
        resolved_url = self._SEARCH_URLS[cleaned_provider].format(query=encoded_query)

        try:
            opened = bool(self.browser_open(resolved_url, new=0, autoraise=True))
        except Exception as exc:  # pragma: no cover - defensive boundary
            safe_error = f"{type(exc).__name__}: {exc}"
            return self._result(
                provider=cleaned_provider,
                query=cleaned_query,
                resolved_url=resolved_url,
                opened=False,
                safe_error=safe_error,
                fallback_reason=safe_error,
                errors=[safe_error],
            )

        if opened:
            return self._result(
                provider=cleaned_provider,
                query=cleaned_query,
                resolved_url=resolved_url,
                opened=True,
                safe_error=None,
                fallback_reason=None,
                errors=[],
            )

        message = f"Browser reported it could not open {cleaned_provider} search."
        return self._result(
            provider=cleaned_provider,
            query=cleaned_query,
            resolved_url=resolved_url,
            opened=False,
            safe_error=message,
            fallback_reason=message,
            errors=[message],
        )

    def _result(
        self,
        *,
        provider: str,
        query: str,
        resolved_url: str | None,
        opened: bool,
        safe_error: str | None,
        fallback_reason: str | None,
        errors: list[str],
    ) -> BrowserSearchResult:
        return BrowserSearchResult(
            enabled=self.enabled,
            provider=provider,
            query=query,
            resolved_url=resolved_url,
            opened=opened,
            log_file=self.log_file,
            safe_error=safe_error,
            fallback_reason=fallback_reason,
            errors=errors,
        )

    @staticmethod
    def _clean_provider_name(provider: str) -> str:
        return " ".join(provider.strip().lower().split())
