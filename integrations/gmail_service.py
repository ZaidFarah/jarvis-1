from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from loguru import logger

from config.settings import AppSettings


_GMAIL_LOG_SINK_ID: int | None = None
_GMAIL_LOG_FILE: Path | None = None


class GmailClient(Protocol):
    def list_unread_messages(self, max_results: int) -> list[dict[str, Any]]: ...


GmailClientFactory = Callable[[AppSettings], GmailClient]


@dataclass(frozen=True)
class GmailUnreadEmail:
    sender: str
    subject: str
    snippet: str
    date: str
    message_id: str | None = None


@dataclass(frozen=True)
class GmailCheckReport:
    enabled: bool
    provider: str
    client_secret_detected: bool
    token_detected: bool
    authenticated: bool
    authentication_status: str
    setup_guide: str | None
    request_attempted: bool
    success: bool
    text: str
    safe_error: str | None
    log_file: Path
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        if not self.enabled:
            return True
        if not self.client_secret_detected or not self.token_detected:
            return True
        return self.success


@dataclass(frozen=True)
class GmailAuthReport:
    enabled: bool
    client_secret_detected: bool
    token_detected: bool
    token_path: Path
    credentials_dir_created: bool
    authenticated: bool
    setup_status: str
    text: str
    safe_error: str | None
    log_file: Path
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        if not self.enabled:
            return True
        if not self.client_secret_detected:
            return True
        return self.authenticated


@dataclass(frozen=True)
class GmailUnreadResult:
    enabled: bool
    success: bool
    text: str
    provider: str
    request_attempted: bool
    authenticated: bool
    client_secret_detected: bool
    token_detected: bool
    unread_count: int
    emails: list[GmailUnreadEmail]
    safe_error: str | None = None
    log_file: Path | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        return self.success


class GmailService:
    """Safe Gmail foundation with explicit diagnostics and unread metadata only."""

    def __init__(
        self,
        settings: AppSettings,
        client_factory: GmailClientFactory | None = None,
    ) -> None:
        self.settings = settings
        self.client_factory = client_factory or self._default_client_factory
        self._custom_client_factory = client_factory is not None
        self.log_file = self.settings.log_dir / "gmail.log"
        self.gmail_logger = logger.bind(gmail=True)
        self._ensure_gmail_log_sink()

    def run_check(self) -> GmailCheckReport:
        provider = "google_gmail"
        client_secret_detected = self.settings.has_gmail_client_secret
        token_detected = self.settings.has_gmail_token
        self.gmail_logger.info(
            "Gmail check enabled={} client_secret_detected={} token_detected={}",
            self.settings.gmail_enabled,
            client_secret_detected,
            token_detected,
        )

        if not self.settings.gmail_enabled:
            message = self._disabled_message()
            return self._check_report(
                client_secret_detected=client_secret_detected,
                token_detected=token_detected,
                authenticated=False,
                authentication_status="disabled",
                setup_guide=self._setup_guide(client_secret_detected, token_detected),
                request_attempted=False,
                success=False,
                text=message,
                safe_error=message,
                provider=provider,
            )

        if not client_secret_detected:
            message = "Gmail is enabled, but the Google client secret file is missing."
            return self._check_report(
                client_secret_detected=False,
                token_detected=token_detected,
                authenticated=False,
                authentication_status="missing client secret",
                setup_guide=self._setup_guide(False, token_detected),
                request_attempted=False,
                success=False,
                text="Gmail credentials are incomplete.",
                safe_error=message,
                provider=provider,
            )

        if not token_detected:
            message = "Gmail is enabled, but the Gmail token file is missing."
            return self._check_report(
                client_secret_detected=True,
                token_detected=False,
                authenticated=False,
                authentication_status="missing token",
                setup_guide=self._setup_guide(True, False),
                request_attempted=False,
                success=False,
                text="Gmail credentials are incomplete.",
                safe_error=message,
                provider=provider,
            )

        try:
            credentials = self._load_credentials()
            authenticated = bool(credentials and getattr(credentials, "valid", False))
            status = "authenticated" if authenticated else "unavailable"
            return self._check_report(
                client_secret_detected=True,
                token_detected=True,
                authenticated=authenticated,
                authentication_status=status,
                setup_guide=self._setup_guide(True, True),
                request_attempted=False,
                success=authenticated,
                text="Gmail is ready." if authenticated else "Gmail authentication is unavailable.",
                safe_error=None if authenticated else "Gmail authentication is unavailable.",
                provider=provider,
            )
        except Exception as exc:
            safe_error = format_gmail_error(exc)
            self.gmail_logger.error("Gmail check failed: {}", safe_error)
            return self._check_report(
                client_secret_detected=True,
                token_detected=True,
                authenticated=False,
                authentication_status="unavailable",
                setup_guide=self._setup_guide(True, True),
                request_attempted=False,
                success=False,
                text="Gmail authentication is unavailable.",
                safe_error=safe_error,
                provider=provider,
            )

    def auth_gmail(self) -> GmailAuthReport:
        credentials_dir_created = self.settings.gmail_token_path.parent.exists()
        self.settings.gmail_token_path.parent.mkdir(parents=True, exist_ok=True)
        credentials_dir_created = credentials_dir_created or self.settings.gmail_token_path.parent.exists()

        client_secret_detected = self.settings.has_gmail_client_secret
        token_detected = self.settings.has_gmail_token
        self.gmail_logger.info(
            "Gmail auth enabled={} client_secret_detected={} token_detected={}",
            self.settings.gmail_enabled,
            client_secret_detected,
            token_detected,
        )

        if not client_secret_detected:
            message = self._auth_guide_message(missing_client_secret=True, missing_token=not token_detected)
            return self._auth_report(
                client_secret_detected=False,
                token_detected=token_detected,
                credentials_dir_created=credentials_dir_created,
                authenticated=False,
                setup_status="missing client secret",
                text=message,
                safe_error="Google client secret file is missing.",
            )

        try:
            credentials = self._load_credentials()
            if credentials is not None and credentials.valid:
                self._save_credentials(credentials)
                return self._auth_report(
                    client_secret_detected=True,
                    token_detected=True,
                    credentials_dir_created=credentials_dir_created,
                    authenticated=True,
                    setup_status="authenticated",
                    text="Google Gmail is already authenticated.",
                    safe_error=None,
                )

            if credentials is not None and getattr(credentials, "expired", False) and getattr(credentials, "refresh_token", None):
                credentials.refresh(self._request_adapter())
                self._save_credentials(credentials)
                return self._auth_report(
                    client_secret_detected=True,
                    token_detected=True,
                    credentials_dir_created=credentials_dir_created,
                    authenticated=True,
                    setup_status="authenticated",
                    text="Google Gmail authentication refreshed successfully.",
                    safe_error=None,
                )

            flow = self._build_flow()
            try:
                credentials = flow.run_local_server(port=0)
            except Exception:
                credentials = flow.run_console()
            self._save_credentials(credentials)
            return self._auth_report(
                client_secret_detected=True,
                token_detected=True,
                credentials_dir_created=credentials_dir_created,
                authenticated=True,
                setup_status="authenticated",
                text="Google Gmail authentication completed successfully.",
                safe_error=None,
            )
        except Exception as exc:
            safe_error = format_gmail_error(exc)
            self.gmail_logger.error("Gmail auth failed: {}", safe_error)
            return self._auth_report(
                client_secret_detected=True,
                token_detected=self.settings.has_gmail_token,
                credentials_dir_created=credentials_dir_created,
                authenticated=False,
                setup_status="authentication failed",
                text=self._auth_guide_message(missing_client_secret=False, missing_token=not self.settings.has_gmail_token),
                safe_error=safe_error,
            )

    def unread_emails(self) -> GmailUnreadResult:
        provider = "google_gmail"
        client_secret_detected = self.settings.has_gmail_client_secret
        token_detected = self.settings.has_gmail_token

        self.gmail_logger.info(
            "Gmail unread enabled={} client_secret_detected={} token_detected={} max_results={}",
            self.settings.gmail_enabled,
            client_secret_detected,
            token_detected,
            self.settings.gmail_max_results,
        )

        if not self.settings.gmail_enabled:
            message = self._disabled_message()
            return self._unread_result(
                enabled=self.settings.gmail_enabled,
                success=False,
                text=message,
                provider=provider,
                request_attempted=False,
                authenticated=False,
                client_secret_detected=client_secret_detected,
                token_detected=token_detected,
                unread_count=0,
                emails=[],
                safe_error=message,
            )

        if not client_secret_detected:
            message = "Gmail is enabled, but the Google client secret file is missing."
            return self._unread_result(
                enabled=self.settings.gmail_enabled,
                success=False,
                text=self._credentials_missing_message(),
                provider=provider,
                request_attempted=False,
                authenticated=False,
                client_secret_detected=False,
                token_detected=token_detected,
                unread_count=0,
                emails=[],
                safe_error=message,
            )

        if not token_detected:
            message = "Gmail is enabled, but the Gmail token file is missing."
            return self._unread_result(
                enabled=self.settings.gmail_enabled,
                success=False,
                text=self._credentials_missing_message(),
                provider=provider,
                request_attempted=False,
                authenticated=False,
                client_secret_detected=True,
                token_detected=False,
                unread_count=0,
                emails=[],
                safe_error=message,
            )

        try:
            client = self.client_factory(self.settings)
            emails = client.list_unread_messages(self.settings.gmail_max_results)
            unread = [self._normalize_email(item) for item in emails]
            text = self._format_unread_emails(unread)
            self.gmail_logger.info("Gmail unread request succeeded count={}", len(unread))
            return self._unread_result(
                enabled=self.settings.gmail_enabled,
                success=True,
                text=text,
                provider=provider,
                request_attempted=True,
                authenticated=True,
                client_secret_detected=True,
                token_detected=True,
                unread_count=len(unread),
                emails=unread,
            )
        except Exception as exc:
            safe_error = format_gmail_error(exc)
            self.gmail_logger.error("Gmail unread request failed: {}", safe_error)
            return self._unread_result(
                enabled=self.settings.gmail_enabled,
                success=False,
                text="I couldn't fetch unread Gmail messages right now. Please try again later.",
                provider=provider,
                request_attempted=True,
                authenticated=False,
                client_secret_detected=True,
                token_detected=True,
                unread_count=0,
                emails=[],
                safe_error=safe_error,
            )

    def _default_client_factory(self, settings: AppSettings) -> GmailClient:
        return self._build_gmail_client(settings, scopes=settings.gmail_scopes_list)

    def _check_report(
        self,
        client_secret_detected: bool,
        token_detected: bool,
        authenticated: bool,
        authentication_status: str,
        setup_guide: str | None,
        request_attempted: bool,
        success: bool,
        text: str,
        safe_error: str | None,
        provider: str,
    ) -> GmailCheckReport:
        errors = [safe_error] if safe_error else []
        return GmailCheckReport(
            enabled=self.settings.gmail_enabled,
            provider=provider,
            client_secret_detected=client_secret_detected,
            token_detected=token_detected,
            authenticated=authenticated,
            authentication_status=authentication_status,
            setup_guide=setup_guide,
            request_attempted=request_attempted,
            success=success,
            text=text,
            safe_error=safe_error,
            log_file=self.log_file,
            errors=errors,
        )

    def _auth_report(
        self,
        client_secret_detected: bool,
        token_detected: bool,
        credentials_dir_created: bool,
        authenticated: bool,
        setup_status: str,
        text: str,
        safe_error: str | None,
    ) -> GmailAuthReport:
        errors = [safe_error] if safe_error else []
        return GmailAuthReport(
            enabled=self.settings.gmail_enabled,
            client_secret_detected=client_secret_detected,
            token_detected=token_detected,
            token_path=self.settings.gmail_token_path,
            credentials_dir_created=credentials_dir_created,
            authenticated=authenticated,
            setup_status=setup_status,
            text=text,
            safe_error=safe_error,
            log_file=self.log_file,
            errors=errors,
        )

    def _unread_result(
        self,
        enabled: bool,
        success: bool,
        text: str,
        provider: str,
        request_attempted: bool,
        authenticated: bool,
        client_secret_detected: bool,
        token_detected: bool,
        unread_count: int,
        emails: list[GmailUnreadEmail],
        safe_error: str | None = None,
    ) -> GmailUnreadResult:
        errors = [safe_error] if safe_error else []
        return GmailUnreadResult(
            enabled=enabled,
            success=success,
            text=text,
            provider=provider,
            request_attempted=request_attempted,
            authenticated=authenticated,
            client_secret_detected=client_secret_detected,
            token_detected=token_detected,
            unread_count=unread_count,
            emails=emails,
            safe_error=safe_error,
            log_file=self.log_file,
            errors=errors,
        )

    def _auth_guide_message(self, missing_client_secret: bool, missing_token: bool) -> str:
        lines = [
            "Gmail setup is incomplete.",
            "Client secret path: GMAIL_CLIENT_SECRET_PATH",
            "Token path: GMAIL_TOKEN_PATH",
            "",
            "Next steps:",
        ]
        if missing_client_secret:
            lines.append("1. Place your Google OAuth client secret JSON at the client secret path.")
        if missing_token:
            lines.append("2. Run `python main.py --gmail-auth` to create or refresh the token file.")
        else:
            lines.append("1. Run `python main.py --gmail-auth` to sign in and save the token.")
        return "\n".join(lines)

    def _setup_guide(self, client_secret_detected: bool, token_detected: bool) -> str | None:
        if not self.settings.gmail_enabled:
            return (
                "Enable GMAIL_ENABLED, place the Google OAuth client secret JSON at GMAIL_CLIENT_SECRET_PATH, then run `python main.py --gmail-auth`."
            )
        if not client_secret_detected:
            return (
                "Place your Google OAuth client secret JSON at GMAIL_CLIENT_SECRET_PATH and run `python main.py --gmail-auth`."
            )
        if not token_detected:
            return "Run `python main.py --gmail-auth` to create the token file at GMAIL_TOKEN_PATH."
        return None

    def _credentials_missing_message(self) -> str:
        return "Gmail credentials are incomplete, so I cannot read unread messages yet."

    def _disabled_message(self) -> str:
        return (
            "Gmail is disabled. Enable GMAIL_ENABLED and provide Google credentials "
            "before reading unread emails."
        )

    def _load_credentials(self, scopes: list[str] | None = None) -> Any | None:
        if not self.settings.has_gmail_token:
            return None

        try:
            from google.oauth2.credentials import Credentials
        except Exception as exc:
            raise RuntimeError(
                "Google authentication libraries are missing. Install google-auth and google-auth-oauthlib."
            ) from exc

        scopes_to_use = scopes if scopes is not None else self.settings.gmail_scopes_list
        return Credentials.from_authorized_user_file(str(self.settings.gmail_token_path), scopes=scopes_to_use)

    def _save_credentials(self, credentials: Any) -> None:
        token_path = self.settings.gmail_token_path
        token_path.parent.mkdir(parents=True, exist_ok=True)
        serialized = getattr(credentials, "to_json", None)
        if callable(serialized):
            token_path.write_text(serialized(), encoding="utf-8")
            return
        raise RuntimeError("Unable to serialize Gmail credentials.")

    def _build_flow(self) -> Any:
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
        except Exception as exc:
            raise RuntimeError(
                "Google authentication libraries are missing. Install google-auth and google-auth-oauthlib."
            ) from exc

        return InstalledAppFlow.from_client_secrets_file(
            str(self.settings.gmail_client_secret_path),
            scopes=self.settings.gmail_scopes_list,
        )

    def _build_gmail_client(self, settings: AppSettings, scopes: list[str] | None = None) -> GmailClient:
        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build
        except Exception as exc:
            raise RuntimeError(
                "Google Gmail libraries are missing. Install google-api-python-client, google-auth, and google-auth-oauthlib."
            ) from exc

        if not settings.has_gmail_client_secret:
            raise RuntimeError("Google client secret file is missing.")

        credentials = None
        scopes_to_use = scopes if scopes is not None else settings.gmail_scopes_list
        if settings.has_gmail_token:
            credentials = Credentials.from_authorized_user_file(str(settings.gmail_token_path), scopes=scopes_to_use)
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
                settings.gmail_token_path.parent.mkdir(parents=True, exist_ok=True)
                settings.gmail_token_path.write_text(credentials.to_json(), encoding="utf-8")

        if credentials is None or not credentials.valid:
            raise RuntimeError("Gmail is not authenticated. Run `python main.py --gmail-auth` to sign in.")

        service = build("gmail", "v1", credentials=credentials, cache_discovery=False)

        class _GoogleGmailClient:
            def __init__(self, gmail_service: Any) -> None:
                self.gmail_service = gmail_service

            def list_unread_messages(self, max_results: int) -> list[dict[str, Any]]:
                response = (
                    self.gmail_service.users()
                    .messages()
                    .list(userId="me", q="is:unread", maxResults=max_results)
                    .execute()
                )
                messages = list(response.get("messages", []))
                results: list[dict[str, Any]] = []
                for message in messages:
                    message_id = message.get("id")
                    if not message_id:
                        continue
                    details = (
                        self.gmail_service.users()
                        .messages()
                        .get(
                            userId="me",
                            id=message_id,
                            format="metadata",
                            metadataHeaders=["From", "Subject", "Date"],
                        )
                        .execute()
                    )
                    results.append(dict(details))
                return results

        return _GoogleGmailClient(service)

    def _request_adapter(self) -> Any:
        try:
            from google.auth.transport.requests import Request
        except Exception as exc:
            raise RuntimeError(
                "Google authentication libraries are missing. Install google-auth and google-auth-oauthlib."
            ) from exc

        return Request()

    def _format_unread_emails(self, emails: list[GmailUnreadEmail]) -> str:
        if not emails:
            return "No unread Gmail messages found."

        lines = [f"Unread Gmail messages ({len(emails)}):"]
        for index, email in enumerate(emails, start=1):
            lines.append(f"{index}. From: {email.sender}")
            lines.append(f"   Subject: {email.subject}")
            if email.date:
                lines.append(f"   Date: {email.date}")
            if email.snippet:
                lines.append(f"   Snippet: {email.snippet}")
        return "\n".join(lines)

    @staticmethod
    def _normalize_email(message: dict[str, Any]) -> GmailUnreadEmail:
        payload = message.get("payload") or {}
        headers = payload.get("headers") or []
        header_map = {
            str(header.get("name") or "").lower(): str(header.get("value") or "").strip()
            for header in headers
            if isinstance(header, dict)
        }
        return GmailUnreadEmail(
            sender=header_map.get("from", "Unknown sender"),
            subject=header_map.get("subject", "No subject"),
            snippet=str(message.get("snippet") or "").strip(),
            date=header_map.get("date", ""),
            message_id=str(message.get("id") or "").strip() or None,
        )

    def _ensure_gmail_log_sink(self) -> None:
        global _GMAIL_LOG_FILE, _GMAIL_LOG_SINK_ID
        if _GMAIL_LOG_SINK_ID is not None and _GMAIL_LOG_FILE == self.log_file:
            return

        if _GMAIL_LOG_SINK_ID is not None:
            try:
                logger.remove(_GMAIL_LOG_SINK_ID)
            except ValueError:
                pass

        self.settings.log_dir.mkdir(parents=True, exist_ok=True)
        _GMAIL_LOG_SINK_ID = logger.add(
            self.log_file,
            level="DEBUG",
            rotation="1 MB",
            retention="7 days",
            encoding="utf-8",
            backtrace=False,
            diagnose=False,
            filter=lambda record: bool(record["extra"].get("gmail")),
        )
        _GMAIL_LOG_FILE = self.log_file


def format_gmail_error(error: Exception) -> str:
    error_type = type(error).__name__
    message = str(error).strip() or "No error details provided."
    return f"{error_type}: {_redact_secret_like_text(message)}"


def format_gmail_check_report(report: GmailCheckReport) -> str:
    lines = [
        "Jarvis Gmail Check",
        "==================",
        f"Gmail enabled: {_yes_no(report.enabled)}",
        f"Provider: {report.provider}",
        f"Client secret detected: {_yes_no(report.client_secret_detected)}",
        f"Token detected: {_yes_no(report.token_detected)}",
        f"Authenticated: {_yes_no(report.authenticated)}",
        f"Authentication status: {report.authentication_status}",
        f"Diagnostic log: {report.log_file}",
        f"Request attempted: {_yes_no(report.request_attempted)}",
        f"Request success: {_yes_no(report.success)}",
    ]
    if report.setup_guide:
        lines.extend(["", "Setup:", f"  {report.setup_guide}"])
    if report.text:
        lines.extend(["", "Result:", f"  {report.text}"])
    if report.safe_error:
        lines.extend(["", "Error:", f"  {report.safe_error}"])
    return "\n".join(lines)


def format_gmail_auth_report(report: GmailAuthReport) -> str:
    lines = [
        "Jarvis Gmail Auth",
        "=================",
        f"Gmail enabled: {_yes_no(report.enabled)}",
        f"Client secret detected: {_yes_no(report.client_secret_detected)}",
        f"Token detected: {_yes_no(report.token_detected)}",
        f"Credentials directory created: {_yes_no(report.credentials_dir_created)}",
        f"Authenticated: {_yes_no(report.authenticated)}",
        f"Setup status: {report.setup_status}",
        f"Diagnostic log: {report.log_file}",
    ]
    if report.text:
        lines.extend(["", "Result:", f"  {report.text}"])
    if report.safe_error:
        lines.extend(["", "Error:", f"  {report.safe_error}"])
    return "\n".join(lines)


def format_gmail_unread_report(report: GmailUnreadResult) -> str:
    lines = [
        "Jarvis Gmail Unread",
        "===================",
        f"Gmail enabled: {_yes_no(report.enabled)}",
        f"Provider: {report.provider}",
        f"Unread count: {report.unread_count}",
        f"Request attempted: {_yes_no(report.request_attempted)}",
        f"Authenticated: {_yes_no(report.authenticated)}",
        f"Diagnostic log: {report.log_file}",
    ]
    if report.text:
        lines.extend(["", "Result:", f"  {report.text}"])
    if report.safe_error:
        lines.extend(["", "Error:", f"  {report.safe_error}"])
    return "\n".join(lines)


def _redact_secret_like_text(text: str) -> str:
    redacted = text
    redacted = redacted.replace("token_gmail.json", "[redacted]")
    redacted = redacted.replace("google_client_secret.json", "[redacted]")
    redacted = redacted.replace("token_calendar.json", "[redacted]")
    redacted = re.sub(r"(token=)[^\s&]+", r"\1[redacted]", redacted, flags=re.IGNORECASE)
    redacted = re.sub(r"(secret=)[^\s&]+", r"\1[redacted]", redacted, flags=re.IGNORECASE)
    return redacted


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
