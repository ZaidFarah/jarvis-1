from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

from loguru import logger

from config.settings import AppSettings


_FILE_ACCESS_LOG_SINK_ID: int | None = None


@dataclass(frozen=True)
class FileEntry:
    name: str
    is_directory: bool
    size_bytes: int
    modified_at: str


@dataclass(frozen=True)
class FileAccessCheckReport:
    enabled: bool
    allowed_folders: dict[str, str]
    log_file: Path
    safe_error: str | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        return True


@dataclass(frozen=True)
class FolderListingResult:
    enabled: bool
    folder_name: str
    configured_path: str
    resolved_path: str | None
    allowed: bool
    configured: bool
    entries: list[FileEntry]
    log_file: Path
    safe_error: str | None = None
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FileSearchResult:
    enabled: bool
    folder_name: str
    query: str
    configured_path: str
    resolved_path: str | None
    allowed: bool
    configured: bool
    request_attempted: bool
    matches: list[FileEntry]
    log_file: Path
    safe_error: str | None = None
    fallback_reason: str | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        if not self.enabled:
            return False
        return self.request_attempted


class FileAccess:
    """Safe read-only access to whitelisted folders."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.log_file = self.settings.log_dir / "file_access.log"
        self.file_access_logger = logger.bind(file_access=True)
        self._ensure_log_sink()

    @property
    def enabled(self) -> bool:
        return self.settings.file_access_enabled

    @property
    def allowed_folders(self) -> dict[str, str]:
        return self.settings.file_access_allowed_folders_map

    def run_check(self) -> FileAccessCheckReport:
        self.file_access_logger.info("Running file access diagnostic enabled={}", self.enabled)
        return FileAccessCheckReport(
            enabled=self.enabled,
            allowed_folders=self.allowed_folders,
            log_file=self.log_file,
        )

    def list_folder(self, folder_name: str) -> FolderListingResult:
        cleaned_name = self._clean_folder_name(folder_name)
        if not self.enabled:
            message = "File access is disabled."
            return self._listing_result(cleaned_name, "", None, False, False, [], message, [message])
        if self._looks_like_path(cleaned_name):
            message = "Folder names must be selected from the whitelist."
            return self._listing_result(cleaned_name, "", None, False, False, [], message, [message])

        configured_path = self.allowed_folders.get(cleaned_name, "")
        allowed = cleaned_name in self.allowed_folders
        configured = allowed and bool(configured_path.strip())
        if not allowed:
            message = f"Folder '{cleaned_name}' is not allowed."
            return self._listing_result(cleaned_name, configured_path, None, False, False, [], message, [message])
        if not configured:
            message = f"Folder '{cleaned_name}' is not configured."
            return self._listing_result(cleaned_name, configured_path, None, True, False, [], message, [message])

        resolved_path = self._resolve_configured_path(configured_path)
        if resolved_path is None:
            message = f"Folder '{cleaned_name}' could not be resolved."
            return self._listing_result(cleaned_name, configured_path, None, True, True, [], message, [message])

        entries = self._read_folder_entries(resolved_path)
        self.file_access_logger.info(
            "Listed folder folder={} resolved_path={} entry_count={}",
            cleaned_name,
            resolved_path,
            len(entries),
        )
        return self._listing_result(cleaned_name, configured_path, str(resolved_path), True, True, entries, None, [])

    def find_file(self, query: str, folder_name: str) -> FileSearchResult:
        cleaned_name = self._clean_folder_name(folder_name)
        cleaned_query = self._clean_search_query(query)
        if not self.enabled:
            message = "File access is disabled."
            return self._search_result(cleaned_name, cleaned_query, "", None, False, False, False, [], message, message, [message])
        if self._looks_like_path(cleaned_query):
            message = "Search terms must be plain filenames, not paths."
            return self._search_result(cleaned_name, cleaned_query, "", None, False, False, False, [], message, message, [message])

        if self._looks_like_path(cleaned_name):
            message = "Folder names must be selected from the whitelist."
            return self._search_result(cleaned_name, cleaned_query, "", None, False, False, False, [], message, message, [message])

        configured_path = self.allowed_folders.get(cleaned_name, "")
        allowed = cleaned_name in self.allowed_folders
        configured = allowed and bool(configured_path.strip())
        if not allowed:
            message = f"Folder '{cleaned_name}' is not allowed."
            return self._search_result(cleaned_name, cleaned_query, configured_path, None, False, False, False, [], message, message, [message])
        if not configured:
            message = f"Folder '{cleaned_name}' is not configured."
            return self._search_result(cleaned_name, cleaned_query, configured_path, None, True, False, False, [], message, message, [message])

        resolved_path = self._resolve_configured_path(configured_path)
        if resolved_path is None:
            message = f"Folder '{cleaned_name}' could not be resolved."
            return self._search_result(cleaned_name, cleaned_query, configured_path, None, True, True, False, [], message, message, [message])

        matches: list[FileEntry] = []
        query_lower = cleaned_query.lower()
        for path in resolved_path.rglob("*"):
            if not path.is_file() and not path.is_dir():
                continue
            if query_lower not in path.name.lower():
                continue
            matches.append(self._build_entry(path))
        self.file_access_logger.info(
            "Searched folder folder={} resolved_path={} query={} match_count={}",
            cleaned_name,
            resolved_path,
            cleaned_query,
            len(matches),
        )
        return self._search_result(cleaned_name, cleaned_query, configured_path, str(resolved_path), True, True, True, matches, None, None, [])

    def _listing_result(
        self,
        folder_name: str,
        configured_path: str,
        resolved_path: str | None,
        allowed: bool,
        configured: bool,
        entries: list[FileEntry],
        safe_error: str | None,
        errors: list[str],
    ) -> FolderListingResult:
        return FolderListingResult(
            enabled=self.enabled,
            folder_name=folder_name,
            configured_path=configured_path,
            resolved_path=resolved_path,
            allowed=allowed,
            configured=configured,
            entries=entries,
            log_file=self.log_file,
            safe_error=safe_error,
            errors=errors,
        )

    def _search_result(
        self,
        folder_name: str,
        query: str,
        configured_path: str,
        resolved_path: str | None,
        allowed: bool,
        configured: bool,
        request_attempted: bool,
        matches: list[FileEntry],
        safe_error: str | None,
        fallback_reason: str | None,
        errors: list[str],
    ) -> FileSearchResult:
        return FileSearchResult(
            enabled=self.enabled,
            folder_name=folder_name,
            query=query,
            configured_path=configured_path,
            resolved_path=resolved_path,
            allowed=allowed,
            configured=configured,
            request_attempted=request_attempted,
            matches=matches,
            log_file=self.log_file,
            safe_error=safe_error,
            fallback_reason=fallback_reason,
            errors=errors,
        )

    def _ensure_log_sink(self) -> None:
        global _FILE_ACCESS_LOG_SINK_ID
        if _FILE_ACCESS_LOG_SINK_ID is not None:
            return

        self.settings.log_dir.mkdir(parents=True, exist_ok=True)
        _FILE_ACCESS_LOG_SINK_ID = logger.add(
            self.log_file,
            level="DEBUG",
            rotation="1 MB",
            retention="7 days",
            encoding="utf-8",
            backtrace=False,
            diagnose=False,
            filter=lambda record: bool(record["extra"].get("file_access")),
        )

    def _resolve_configured_path(self, configured_path: str) -> Path | None:
        expanded = os.path.expandvars(configured_path)
        path = Path(expanded).expanduser()
        if not path.exists() or not path.is_dir():
            return None
        return path.resolve()

    @staticmethod
    def _read_folder_entries(folder_path: Path) -> list[FileEntry]:
        entries: list[FileEntry] = []
        for child in sorted(folder_path.iterdir(), key=lambda item: item.name.lower()):
            try:
                stat = child.stat()
            except OSError:
                continue
            entries.append(
                FileEntry(
                    name=child.name,
                    is_directory=child.is_dir(),
                    size_bytes=0 if child.is_dir() else stat.st_size,
                    modified_at=datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                )
            )
        return entries

    @staticmethod
    def _build_entry(path: Path) -> FileEntry:
        stat = path.stat()
        return FileEntry(
            name=path.name,
            is_directory=path.is_dir(),
            size_bytes=0 if path.is_dir() else stat.st_size,
            modified_at=datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        )

    @staticmethod
    def _clean_folder_name(folder_name: str) -> str:
        return " ".join(folder_name.strip().split()).lower()

    @staticmethod
    def _clean_search_query(query: str) -> str:
        return " ".join(query.strip().split())

    @staticmethod
    def _looks_like_path(value: str) -> bool:
        if not value:
            return False
        normalized = value.strip()
        if normalized.startswith("..") or ".." in normalized:
            return True
        if re.match(r"^[a-zA-Z]:[\\/]", normalized):
            return True
        if normalized.startswith(("/", "\\")):
            return True
        if any(sep in normalized for sep in ("\\", "/")):
            return True
        return False


def format_file_access_error(error: Exception) -> str:
    error_type = type(error).__name__
    message = str(error).strip() or "No error details provided."
    return f"{error_type}: {_redact_secret_like_text(message)}"


def format_file_access_check_report(report: FileAccessCheckReport) -> str:
    lines = [
        "Jarvis File Access Check",
        "========================",
        f"File access enabled: {_yes_no(report.enabled)}",
        f"Diagnostic log: {report.log_file}",
        "",
        "Allowed folders:",
    ]
    if report.allowed_folders:
        lines.extend(f"  {name} -> {path or '[not configured]'}" for name, path in report.allowed_folders.items())
    else:
        lines.append("  None configured.")
    if report.safe_error:
        lines.extend(["", "Error:", f"  {report.safe_error}"])
    return "\n".join(lines)


def format_folder_listing_report(result: FolderListingResult) -> str:
    lines = [
        "Jarvis Folder Listing",
        "=====================",
        f"File access enabled: {_yes_no(result.enabled)}",
        f"Folder: {result.folder_name}",
        f"Allowed: {_yes_no(result.allowed)}",
        f"Configured: {_yes_no(result.configured)}",
        f"Diagnostic log: {result.log_file}",
    ]
    if result.resolved_path:
        lines.extend(["", f"Resolved path: {result.resolved_path}"])
    if result.safe_error:
        lines.extend(["", "Error:", f"  {result.safe_error}"])
    else:
        lines.append("")
        lines.append("Entries:")
        if result.entries:
            for entry in result.entries:
                kind = "dir" if entry.is_directory else "file"
                lines.append(f"  {entry.name} | {kind} | size={entry.size_bytes} | modified={entry.modified_at}")
        else:
            lines.append("  None.")
    return "\n".join(lines)


def format_file_search_report(result: FileSearchResult) -> str:
    lines = [
        "Jarvis File Search",
        "==================",
        f"File access enabled: {_yes_no(result.enabled)}",
        f"Folder: {result.folder_name}",
        f"Query: {result.query}",
        f"Allowed: {_yes_no(result.allowed)}",
        f"Configured: {_yes_no(result.configured)}",
        f"Request attempted: {_yes_no(result.request_attempted)}",
        f"Diagnostic log: {result.log_file}",
    ]
    if result.resolved_path:
        lines.extend(["", f"Resolved path: {result.resolved_path}"])
    if result.fallback_reason:
        lines.extend(["", "Fallback reason:", f"  {result.fallback_reason}"])
    if result.safe_error:
        lines.extend(["", "Error:", f"  {result.safe_error}"])
    if result.matches:
        lines.extend(["", "Matches:"])
        for entry in result.matches:
            kind = "dir" if entry.is_directory else "file"
            lines.append(f"  {entry.name} | {kind} | size={entry.size_bytes} | modified={entry.modified_at}")
    elif result.request_attempted and not result.safe_error:
        lines.extend(["", "Matches:", "  None."])
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
