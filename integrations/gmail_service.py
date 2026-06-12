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
    def create_draft(self, to_address: str, subject: str, body: str) -> dict[str, Any]: ...
    def list_drafts(self, max_results: int) -> list[dict[str, Any]]: ...
    def send_draft(self, draft_id: str) -> dict[str, Any]: ...


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


@dataclass(frozen=True)
class GmailDraftResult:
    enabled: bool
    success: bool
    text: str
    provider: str
    request_attempted: bool
    authenticated: bool
    client_secret_detected: bool
    token_detected: bool
    draft_enabled: bool
    compose_scope_detected: bool
    recipient: str
    subject: str
    safe_error: str | None = None
    log_file: Path | None = None
    draft_id: str | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        return self.success


@dataclass(frozen=True)
class GmailDraftItem:
    draft_id: str
    recipient: str
    subject: str
    snippet: str


@dataclass(frozen=True)
class GmailDraftListResult:
    enabled: bool
    success: bool
    text: str
    provider: str
    request_attempted: bool
    authenticated: bool
    client_secret_detected: bool
    token_detected: bool
    draft_list_enabled: bool
    drafts: list[GmailDraftItem]
    safe_error: str | None = None
    log_file: Path | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        return self.success


@dataclass(frozen=True)
class GmailSendDraftResult:
    enabled: bool
    success: bool
    text: str
    provider: str
    request_attempted: bool
    authenticated: bool
    client_secret_detected: bool
    token_detected: bool
    send_enabled: bool
    draft_id: str
    safe_error: str | None = None
    log_file: Path | None = None
    sent_message_id: str | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        return self.success


class GmailService:
    """Safe Gmail foundation with explicit diagnostics, unread metadata, and drafts."""

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
            credentials = self._load_credentials(self.settings.gmail_auth_scopes_list)
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

    def create_draft(self, recipient: str, subject: str, body: str) -> GmailDraftResult:
        provider = "google_gmail"
        recipient_text = recipient.strip()
        subject_text = subject.strip()
        body_text = body.strip()
        client_secret_detected = self.settings.has_gmail_client_secret
        token_detected = self.settings.has_gmail_token
        compose_scope_detected = False

        self.gmail_logger.info(
            "Gmail draft enabled={} recipient={} subject={} client_secret_detected={} token_detected={}",
            self.settings.gmail_draft_enabled,
            recipient_text,
            subject_text,
            client_secret_detected,
            token_detected,
        )

        if not self.settings.gmail_enabled or not self.settings.gmail_draft_enabled:
            message = self._draft_disabled_message()
            return self._draft_result(
                enabled=self.settings.gmail_enabled,
                success=False,
                text=message,
                provider=provider,
                request_attempted=False,
                authenticated=False,
                client_secret_detected=client_secret_detected,
                token_detected=token_detected,
                draft_enabled=self.settings.gmail_draft_enabled,
                compose_scope_detected=compose_scope_detected,
                recipient=recipient_text,
                subject=subject_text,
                safe_error=message,
            )

        if not self._looks_like_email(recipient_text):
            message = "Please provide a valid recipient email address."
            return self._draft_result(
                enabled=self.settings.gmail_enabled,
                success=False,
                text=message,
                provider=provider,
                request_attempted=False,
                authenticated=False,
                client_secret_detected=client_secret_detected,
                token_detected=token_detected,
                draft_enabled=self.settings.gmail_draft_enabled,
                compose_scope_detected=compose_scope_detected,
                recipient=recipient_text,
                subject=subject_text,
                safe_error=message,
            )

        if not subject_text:
            message = "Subject cannot be empty."
            return self._draft_result(
                enabled=self.settings.gmail_enabled,
                success=False,
                text=message,
                provider=provider,
                request_attempted=False,
                authenticated=False,
                client_secret_detected=client_secret_detected,
                token_detected=token_detected,
                draft_enabled=self.settings.gmail_draft_enabled,
                compose_scope_detected=compose_scope_detected,
                recipient=recipient_text,
                subject=subject_text,
                safe_error=message,
            )

        if not body_text:
            message = "Body cannot be empty."
            return self._draft_result(
                enabled=self.settings.gmail_enabled,
                success=False,
                text=message,
                provider=provider,
                request_attempted=False,
                authenticated=False,
                client_secret_detected=client_secret_detected,
                token_detected=token_detected,
                draft_enabled=self.settings.gmail_draft_enabled,
                compose_scope_detected=compose_scope_detected,
                recipient=recipient_text,
                subject=subject_text,
                safe_error=message,
            )

        if not client_secret_detected:
            message = "Gmail is enabled, but the Google client secret file is missing."
            return self._draft_result(
                enabled=self.settings.gmail_enabled,
                success=False,
                text=self._credentials_missing_message(),
                provider=provider,
                request_attempted=False,
                authenticated=False,
                client_secret_detected=False,
                token_detected=token_detected,
                draft_enabled=self.settings.gmail_draft_enabled,
                compose_scope_detected=compose_scope_detected,
                recipient=recipient_text,
                subject=subject_text,
                safe_error=message,
            )

        if not token_detected:
            message = "Gmail is enabled, but the Gmail token file is missing."
            return self._draft_result(
                enabled=self.settings.gmail_enabled,
                success=False,
                text=self._credentials_missing_message(),
                provider=provider,
                request_attempted=False,
                authenticated=False,
                client_secret_detected=True,
                token_detected=False,
                draft_enabled=self.settings.gmail_draft_enabled,
                compose_scope_detected=compose_scope_detected,
                recipient=recipient_text,
                subject=subject_text,
                safe_error=message,
            )

        try:
            credentials = self._load_credentials(self.settings.gmail_draft_scopes_list)
            compose_scope_detected = self._credentials_has_scopes(credentials, self.settings.gmail_draft_scopes_list)
            if not compose_scope_detected:
                message = "Gmail compose scope is required. Re-run Gmail auth after enabling draft."
                return self._draft_result(
                    enabled=self.settings.gmail_enabled,
                    success=False,
                    text=message,
                    provider=provider,
                    request_attempted=False,
                    authenticated=False,
                    client_secret_detected=True,
                    token_detected=True,
                    draft_enabled=self.settings.gmail_draft_enabled,
                    compose_scope_detected=False,
                    recipient=recipient_text,
                    subject=subject_text,
                    safe_error=message,
                )

            if self._custom_client_factory:
                client = self.client_factory(self.settings)
            else:
                client = self._build_gmail_client(self.settings, scopes=self.settings.gmail_draft_scopes_list)
            draft = client.create_draft(recipient_text, subject_text, body_text)
            draft_id = str(draft.get("id") or "").strip() or None
            text = self._format_draft_result(recipient_text, subject_text, draft_id)
            self.gmail_logger.info("Gmail draft created recipient={} subject={} draft_id={}", recipient_text, subject_text, draft_id)
            return self._draft_result(
                enabled=self.settings.gmail_enabled,
                success=True,
                text=text,
                provider=provider,
                request_attempted=True,
                authenticated=True,
                client_secret_detected=True,
                token_detected=True,
                draft_enabled=self.settings.gmail_draft_enabled,
                compose_scope_detected=compose_scope_detected,
                recipient=recipient_text,
                subject=subject_text,
                draft_id=draft_id,
            )
        except Exception as exc:
            safe_error = format_gmail_error(exc)
            self.gmail_logger.error("Gmail draft request failed: {}", safe_error)
            return self._draft_result(
                enabled=self.settings.gmail_enabled,
                success=False,
                text="I couldn't create the Gmail draft right now. Please try again later.",
                provider=provider,
                request_attempted=True,
                authenticated=False,
                client_secret_detected=True,
                token_detected=True,
                draft_enabled=self.settings.gmail_draft_enabled,
                compose_scope_detected=compose_scope_detected,
                recipient=recipient_text,
                subject=subject_text,
                safe_error=safe_error,
            )

    def list_drafts(self) -> GmailDraftListResult:
        provider = "google_gmail"
        client_secret_detected = self.settings.has_gmail_client_secret
        token_detected = self.settings.has_gmail_token

        self.gmail_logger.info(
            "Gmail draft list enabled={} client_secret_detected={} token_detected={}",
            self.settings.gmail_send_draft_enabled,
            client_secret_detected,
            token_detected,
        )

        if not self.settings.gmail_enabled or not self.settings.gmail_send_draft_enabled:
            message = self._draft_list_disabled_message()
            return self._draft_list_result(
                enabled=self.settings.gmail_enabled,
                success=False,
                text=message,
                provider=provider,
                request_attempted=False,
                authenticated=False,
                client_secret_detected=client_secret_detected,
                token_detected=token_detected,
                draft_list_enabled=self.settings.gmail_send_draft_enabled,
                drafts=[],
                safe_error=message,
            )

        if not client_secret_detected:
            message = "Gmail is enabled, but the Google client secret file is missing."
            return self._draft_list_result(
                enabled=self.settings.gmail_enabled,
                success=False,
                text=self._credentials_missing_message(),
                provider=provider,
                request_attempted=False,
                authenticated=False,
                client_secret_detected=False,
                token_detected=token_detected,
                draft_list_enabled=self.settings.gmail_send_draft_enabled,
                drafts=[],
                safe_error=message,
            )

        if not token_detected:
            message = "Gmail is enabled, but the Gmail token file is missing."
            return self._draft_list_result(
                enabled=self.settings.gmail_enabled,
                success=False,
                text=self._credentials_missing_message(),
                provider=provider,
                request_attempted=False,
                authenticated=False,
                client_secret_detected=True,
                token_detected=False,
                draft_list_enabled=self.settings.gmail_send_draft_enabled,
                drafts=[],
                safe_error=message,
            )

        try:
            credentials = self._load_credentials(self.settings.gmail_send_scopes_list)
            send_scope_detected = self._credentials_has_scopes(credentials, self.settings.gmail_send_scopes_list)
            if not send_scope_detected:
                message = "Gmail send scope is required. Re-run Gmail auth after enabling send draft."
                return self._draft_list_result(
                    enabled=self.settings.gmail_enabled,
                    success=False,
                    text=message,
                    provider=provider,
                    request_attempted=False,
                    authenticated=False,
                    client_secret_detected=True,
                    token_detected=True,
                    draft_list_enabled=self.settings.gmail_send_draft_enabled,
                    drafts=[],
                    safe_error=message,
                )

            client = self.client_factory(self.settings) if self._custom_client_factory else self._build_gmail_client(
                self.settings,
                scopes=self.settings.gmail_send_scopes_list,
            )
            drafts = [self._normalize_draft(item) for item in client.list_drafts(self.settings.gmail_max_results)]
            text = self._format_draft_list(drafts)
            self.gmail_logger.info("Gmail draft list succeeded count={}", len(drafts))
            return self._draft_list_result(
                enabled=self.settings.gmail_enabled,
                success=True,
                text=text,
                provider=provider,
                request_attempted=True,
                authenticated=True,
                client_secret_detected=True,
                token_detected=True,
                draft_list_enabled=self.settings.gmail_send_draft_enabled,
                drafts=drafts,
            )
        except Exception as exc:
            safe_error = format_gmail_error(exc)
            self.gmail_logger.error("Gmail draft list failed: {}", safe_error)
            return self._draft_list_result(
                enabled=self.settings.gmail_enabled,
                success=False,
                text="I couldn't fetch Gmail drafts right now. Please try again later.",
                provider=provider,
                request_attempted=True,
                authenticated=False,
                client_secret_detected=True,
                token_detected=True,
                draft_list_enabled=self.settings.gmail_send_draft_enabled,
                drafts=[],
                safe_error=safe_error,
            )

    def send_draft(self, draft_id: str) -> GmailSendDraftResult:
        provider = "google_gmail"
        draft_id_text = draft_id.strip()
        client_secret_detected = self.settings.has_gmail_client_secret
        token_detected = self.settings.has_gmail_token
        send_scope_detected = False

        self.gmail_logger.info(
            "Gmail send draft enabled={} draft_id={} client_secret_detected={} token_detected={}",
            self.settings.gmail_send_draft_enabled,
            draft_id_text,
            client_secret_detected,
            token_detected,
        )

        if not self.settings.gmail_enabled or not self.settings.gmail_send_draft_enabled:
            message = self._send_draft_disabled_message()
            return self._send_draft_result(
                enabled=self.settings.gmail_enabled,
                success=False,
                text=message,
                provider=provider,
                request_attempted=False,
                authenticated=False,
                client_secret_detected=client_secret_detected,
                token_detected=token_detected,
                send_enabled=self.settings.gmail_send_draft_enabled,
                draft_id=draft_id_text,
                safe_error=message,
            )

        if not self._looks_like_draft_id(draft_id_text):
            message = "Please provide a valid Gmail draft ID."
            return self._send_draft_result(
                enabled=self.settings.gmail_enabled,
                success=False,
                text=message,
                provider=provider,
                request_attempted=False,
                authenticated=False,
                client_secret_detected=client_secret_detected,
                token_detected=token_detected,
                send_enabled=self.settings.gmail_send_draft_enabled,
                draft_id=draft_id_text,
                safe_error=message,
            )

        if not client_secret_detected:
            message = "Gmail is enabled, but the Google client secret file is missing."
            return self._send_draft_result(
                enabled=self.settings.gmail_enabled,
                success=False,
                text=self._credentials_missing_message(),
                provider=provider,
                request_attempted=False,
                authenticated=False,
                client_secret_detected=False,
                token_detected=token_detected,
                send_enabled=self.settings.gmail_send_draft_enabled,
                draft_id=draft_id_text,
                safe_error=message,
            )

        if not token_detected:
            message = "Gmail is enabled, but the Gmail token file is missing."
            return self._send_draft_result(
                enabled=self.settings.gmail_enabled,
                success=False,
                text=self._credentials_missing_message(),
                provider=provider,
                request_attempted=False,
                authenticated=False,
                client_secret_detected=True,
                token_detected=False,
                send_enabled=self.settings.gmail_send_draft_enabled,
                draft_id=draft_id_text,
                safe_error=message,
            )

        try:
            credentials = self._load_credentials(self.settings.gmail_send_scopes_list)
            send_scope_detected = self._credentials_has_scopes(credentials, self.settings.gmail_send_scopes_list)
            if not send_scope_detected:
                message = "Gmail send scope is required. Re-run Gmail auth after enabling send draft."
                return self._send_draft_result(
                    enabled=self.settings.gmail_enabled,
                    success=False,
                    text=message,
                    provider=provider,
                    request_attempted=False,
                    authenticated=False,
                    client_secret_detected=True,
                    token_detected=True,
                    send_enabled=self.settings.gmail_send_draft_enabled,
                    draft_id=draft_id_text,
                    safe_error=message,
                )

            client = self.client_factory(self.settings) if self._custom_client_factory else self._build_gmail_client(
                self.settings,
                scopes=self.settings.gmail_send_scopes_list,
            )
            sent = client.send_draft(draft_id_text)
            sent_message_id = str(sent.get("message", {}).get("id") or sent.get("id") or "").strip() or None
            text = self._format_send_draft_result(draft_id_text, sent_message_id)
            self.gmail_logger.info("Gmail draft sent draft_id={} message_id={}", draft_id_text, sent_message_id)
            return self._send_draft_result(
                enabled=self.settings.gmail_enabled,
                success=True,
                text=text,
                provider=provider,
                request_attempted=True,
                authenticated=True,
                client_secret_detected=True,
                token_detected=True,
                send_enabled=self.settings.gmail_send_draft_enabled,
                draft_id=draft_id_text,
                sent_message_id=sent_message_id,
            )
        except Exception as exc:
            safe_error = format_gmail_error(exc)
            self.gmail_logger.error("Gmail send draft failed: {}", safe_error)
            return self._send_draft_result(
                enabled=self.settings.gmail_enabled,
                success=False,
                text="I couldn't send that Gmail draft right now. Please try again later.",
                provider=provider,
                request_attempted=True,
                authenticated=False,
                client_secret_detected=True,
                token_detected=True,
                send_enabled=self.settings.gmail_send_draft_enabled,
                draft_id=draft_id_text,
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

    def _draft_result(
        self,
        enabled: bool,
        success: bool,
        text: str,
        provider: str,
        request_attempted: bool,
        authenticated: bool,
        client_secret_detected: bool,
        token_detected: bool,
        draft_enabled: bool,
        compose_scope_detected: bool,
        recipient: str,
        subject: str,
        safe_error: str | None = None,
        draft_id: str | None = None,
    ) -> GmailDraftResult:
        errors = [safe_error] if safe_error else []
        return GmailDraftResult(
            enabled=enabled,
            success=success,
            text=text,
            provider=provider,
            request_attempted=request_attempted,
            authenticated=authenticated,
            client_secret_detected=client_secret_detected,
            token_detected=token_detected,
            draft_enabled=draft_enabled,
            compose_scope_detected=compose_scope_detected,
            recipient=recipient,
            subject=subject,
            safe_error=safe_error,
            log_file=self.log_file,
            draft_id=draft_id,
            errors=errors,
        )

    def _draft_list_result(
        self,
        enabled: bool,
        success: bool,
        text: str,
        provider: str,
        request_attempted: bool,
        authenticated: bool,
        client_secret_detected: bool,
        token_detected: bool,
        draft_list_enabled: bool,
        drafts: list[GmailDraftItem],
        safe_error: str | None = None,
    ) -> GmailDraftListResult:
        errors = [safe_error] if safe_error else []
        return GmailDraftListResult(
            enabled=enabled,
            success=success,
            text=text,
            provider=provider,
            request_attempted=request_attempted,
            authenticated=authenticated,
            client_secret_detected=client_secret_detected,
            token_detected=token_detected,
            draft_list_enabled=draft_list_enabled,
            drafts=drafts,
            safe_error=safe_error,
            log_file=self.log_file,
            errors=errors,
        )

    def _send_draft_result(
        self,
        enabled: bool,
        success: bool,
        text: str,
        provider: str,
        request_attempted: bool,
        authenticated: bool,
        client_secret_detected: bool,
        token_detected: bool,
        send_enabled: bool,
        draft_id: str,
        safe_error: str | None = None,
        sent_message_id: str | None = None,
    ) -> GmailSendDraftResult:
        errors = [safe_error] if safe_error else []
        return GmailSendDraftResult(
            enabled=enabled,
            success=success,
            text=text,
            provider=provider,
            request_attempted=request_attempted,
            authenticated=authenticated,
            client_secret_detected=client_secret_detected,
            token_detected=token_detected,
            send_enabled=send_enabled,
            draft_id=draft_id,
            safe_error=safe_error,
            log_file=self.log_file,
            sent_message_id=sent_message_id,
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

    @staticmethod
    def _credentials_has_scopes(credentials: Any | None, scopes: list[str]) -> bool:
        if credentials is None or not scopes:
            return False

        has_scopes = getattr(credentials, "has_scopes", None)
        if callable(has_scopes):
            try:
                return bool(has_scopes(scopes))
            except Exception:
                pass

        credential_scopes = getattr(credentials, "scopes", None) or []
        credential_set = {str(scope).strip() for scope in credential_scopes if str(scope).strip()}
        return set(scopes).issubset(credential_set)

    def _credentials_missing_message(self) -> str:
        return "Gmail credentials are incomplete, so I cannot read unread messages yet."

    def _disabled_message(self) -> str:
        return (
            "Gmail is disabled. Enable GMAIL_ENABLED and provide Google credentials "
            "before reading unread emails."
        )

    def _draft_disabled_message(self) -> str:
        return (
            "Gmail draft creation is disabled. Enable GMAIL_DRAFT_ENABLED and provide Google credentials "
            "before creating drafts."
        )

    def _draft_list_disabled_message(self) -> str:
        return (
            "Gmail draft listing is disabled. Enable GMAIL_SEND_DRAFT_ENABLED and provide Google credentials "
            "before listing drafts."
        )

    def _send_draft_disabled_message(self) -> str:
        return (
            "Gmail draft sending is disabled. Enable GMAIL_SEND_DRAFT_ENABLED and provide Google credentials "
            "before sending drafts."
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
            scopes=self.settings.gmail_auth_scopes_list,
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

            def create_draft(self, to_address: str, subject: str, body: str) -> dict[str, Any]:
                draft_body = {
                    "message": {
                        "raw": self._encode_message(to_address, subject, body),
                    }
                }
                response = (
                    self.gmail_service.users()
                    .drafts()
                    .create(userId="me", body=draft_body)
                    .execute()
                )
                return dict(response)

            def list_drafts(self, max_results: int) -> list[dict[str, Any]]:
                response = (
                    self.gmail_service.users()
                    .drafts()
                    .list(userId="me", maxResults=max_results)
                    .execute()
                )
                drafts = list(response.get("drafts", []))
                results: list[dict[str, Any]] = []
                for draft in drafts:
                    draft_id = draft.get("id")
                    if not draft_id:
                        continue
                    details = (
                        self.gmail_service.users()
                        .drafts()
                        .get(userId="me", id=draft_id)
                        .execute()
                    )
                    results.append(dict(details))
                return results

            def send_draft(self, draft_id: str) -> dict[str, Any]:
                response = (
                    self.gmail_service.users()
                    .drafts()
                    .send(userId="me", body={"id": draft_id})
                    .execute()
                )
                return dict(response)

            @staticmethod
            def _encode_message(to_address: str, subject: str, body: str) -> str:
                import base64
                from email.message import EmailMessage

                message = EmailMessage()
                message["To"] = to_address
                message["Subject"] = subject
                message.set_content(body)
                raw = message.as_bytes()
                return base64.urlsafe_b64encode(raw).decode("utf-8")

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

    def _format_draft_result(self, recipient: str, subject: str, draft_id: str | None) -> str:
        lines = [
            f"Created Gmail draft for {recipient}.",
            f"Subject: {subject}",
        ]
        if draft_id:
            lines.append(f"Draft ID: {draft_id}")
        return "\n".join(lines)

    def _format_draft_list(self, drafts: list[GmailDraftItem]) -> str:
        if not drafts:
            return "No Gmail drafts found."

        lines = [f"Saved Gmail drafts ({len(drafts)}):"]
        for index, draft in enumerate(drafts, start=1):
            lines.append(f"{index}. Draft ID: {draft.draft_id}")
            lines.append(f"   Recipient: {draft.recipient}")
            lines.append(f"   Subject: {draft.subject}")
            if draft.snippet:
                lines.append(f"   Snippet: {draft.snippet}")
        return "\n".join(lines)

    def _format_send_draft_result(self, draft_id: str, sent_message_id: str | None) -> str:
        lines = [f"Sent Gmail draft {draft_id}."]
        if sent_message_id:
            lines.append(f"Message ID: {sent_message_id}")
        return "\n".join(lines)

    @staticmethod
    def _looks_like_email(value: str) -> bool:
        cleaned = value.strip()
        if not cleaned or any(sep in cleaned for sep in (" ", "/", "\\", "..")):
            return False
        return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", cleaned))

    @staticmethod
    def _looks_like_draft_id(value: str) -> bool:
        cleaned = value.strip()
        if not cleaned or any(sep in cleaned for sep in (" ", "/", "\\", "..")):
            return False
        return bool(re.match(r"^[A-Za-z0-9._-]+$", cleaned))

    @staticmethod
    def _normalize_draft(draft: dict[str, Any]) -> GmailDraftItem:
        draft_id = str(draft.get("id") or "").strip() or "unknown"
        message = draft.get("message") or {}
        payload = message.get("payload") or {}
        headers = payload.get("headers") or []
        header_map = {
            str(header.get("name") or "").lower(): str(header.get("value") or "").strip()
            for header in headers
            if isinstance(header, dict)
        }
        return GmailDraftItem(
            draft_id=draft_id,
            recipient=header_map.get("to", "Unknown recipient"),
            subject=header_map.get("subject", "No subject"),
            snippet=str(message.get("snippet") or draft.get("snippet") or "").strip(),
        )

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


def format_gmail_draft_report(report: GmailDraftResult) -> str:
    lines = [
        "Jarvis Gmail Draft",
        "==================",
        f"Gmail enabled: {_yes_no(report.enabled)}",
        f"Draft enabled: {_yes_no(report.draft_enabled)}",
        f"Provider: {report.provider}",
        f"Recipient: {report.recipient}",
        f"Subject: {report.subject}",
        f"Compose scope detected: {_yes_no(report.compose_scope_detected)}",
        f"Request attempted: {_yes_no(report.request_attempted)}",
        f"Authenticated: {_yes_no(report.authenticated)}",
        f"Diagnostic log: {report.log_file}",
    ]
    if report.text:
        lines.extend(["", "Result:", f"  {report.text}"])
    if report.safe_error:
        lines.extend(["", "Error:", f"  {report.safe_error}"])
    if report.draft_id:
        lines.extend(["", f"Draft ID: {report.draft_id}"])
    return "\n".join(lines)


def format_gmail_draft_list_report(report: GmailDraftListResult) -> str:
    lines = [
        "Jarvis Gmail Drafts",
        "===================",
        f"Gmail enabled: {_yes_no(report.enabled)}",
        f"Draft list enabled: {_yes_no(report.draft_list_enabled)}",
        f"Provider: {report.provider}",
        f"Draft count: {len(report.drafts)}",
        f"Request attempted: {_yes_no(report.request_attempted)}",
        f"Authenticated: {_yes_no(report.authenticated)}",
        f"Diagnostic log: {report.log_file}",
    ]
    if report.text:
        lines.extend(["", "Result:", f"  {report.text}"])
    if report.safe_error:
        lines.extend(["", "Error:", f"  {report.safe_error}"])
    return "\n".join(lines)


def format_gmail_send_draft_report(report: GmailSendDraftResult) -> str:
    lines = [
        "Jarvis Gmail Send Draft",
        "=======================",
        f"Gmail enabled: {_yes_no(report.enabled)}",
        f"Send enabled: {_yes_no(report.send_enabled)}",
        f"Provider: {report.provider}",
        f"Draft ID: {report.draft_id}",
        f"Request attempted: {_yes_no(report.request_attempted)}",
        f"Authenticated: {_yes_no(report.authenticated)}",
        f"Diagnostic log: {report.log_file}",
    ]
    if report.text:
        lines.extend(["", "Result:", f"  {report.text}"])
    if report.safe_error:
        lines.extend(["", "Error:", f"  {report.safe_error}"])
    if report.sent_message_id:
        lines.extend(["", f"Message ID: {report.sent_message_id}"])
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
