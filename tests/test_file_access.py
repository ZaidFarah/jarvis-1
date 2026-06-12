from __future__ import annotations

from pathlib import Path

import pytest

from assistant.core import AssistantCore, AssistantResponse
from config.settings import AppSettings
from security.confirmation import ConfirmationResult
from tools.file_access import (
    FileAccess,
    FileAccessCheckReport,
    FileEntry,
    FileSearchResult,
    FolderListingResult,
    format_file_access_check_report,
    format_file_access_error,
    format_file_search_report,
    format_folder_listing_report,
)


class FakeOpenAIService:
    def chat(self, *args, **kwargs):  # pragma: no cover - defensive helper
        del args, kwargs
        raise AssertionError("OpenAI should not be called")


def _build_file_access(tmp_path: Path) -> FileAccess:
    folder = tmp_path / "documents"
    folder.mkdir()
    (folder / "alpha.txt").write_text("alpha", encoding="utf-8")
    (folder / "beta.log").write_text("beta", encoding="utf-8")
    (folder / "notes.md").write_text("line 1\nline 2", encoding="utf-8")
    (folder / "binary.txt").write_bytes(b"\x00\x01\x02")
    (folder / "large.txt").write_text("x" * 30000, encoding="utf-8")
    (folder / "nested").mkdir()
    (folder / "nested" / "alpha_nested.txt").write_text("nested", encoding="utf-8")
    settings = AppSettings(
        _env_file=None,
        log_dir=tmp_path,
        file_access_enabled=True,
        file_read_enabled=True,
        file_access_allowed_folders=f"documents={folder}",
    )
    return FileAccess(settings)


def test_file_access_disabled_fallback(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, log_dir=tmp_path, file_access_enabled=False)
    access = FileAccess(settings)

    result = access.list_folder("documents")

    assert result.enabled is False
    assert result.safe_error == "File access is disabled."


def test_file_access_allowed_folder_listing(tmp_path: Path) -> None:
    access = _build_file_access(tmp_path)

    result = access.list_folder("documents")

    assert result.allowed is True
    assert result.configured is True
    assert [entry.name for entry in result.entries][:2] == ["alpha.txt", "beta.log"]
    assert any(entry.name == "nested" and entry.is_directory for entry in result.entries)


def test_file_access_unknown_folder_rejected(tmp_path: Path) -> None:
    access = _build_file_access(tmp_path)

    result = access.list_folder("music")

    assert result.allowed is False
    assert "not allowed" in (result.safe_error or "")


def test_file_access_path_traversal_rejected(tmp_path: Path) -> None:
    access = _build_file_access(tmp_path)

    result = access.find_file("..\\secret", "documents")

    assert result.request_attempted is False
    assert "plain filename" in (result.safe_error or "")


def test_file_access_absolute_path_rejected(tmp_path: Path) -> None:
    access = _build_file_access(tmp_path)

    result = access.find_file("C:\\Windows\\win.ini", "documents")

    assert result.request_attempted is False
    assert "plain filename" in (result.safe_error or "")


def test_file_access_find_file_behavior(tmp_path: Path) -> None:
    access = _build_file_access(tmp_path)

    result = access.find_file("alpha", "documents")

    assert result.request_attempted is True
    assert len(result.matches) == 2
    assert {entry.name for entry in result.matches} == {"alpha.txt", "alpha_nested.txt"}


def test_file_access_read_allowed_text_file(tmp_path: Path) -> None:
    access = _build_file_access(tmp_path)

    result = access.read_file("notes.md", "documents")

    assert result.request_attempted is True
    assert result.safe_error is None
    assert result.content_preview == "line 1\nline 2"


def test_file_access_read_disabled_fallback(tmp_path: Path) -> None:
    folder = tmp_path / "documents"
    folder.mkdir()
    (folder / "notes.md").write_text("line 1", encoding="utf-8")
    settings = AppSettings(
        _env_file=None,
        log_dir=tmp_path,
        file_access_enabled=True,
        file_read_enabled=False,
        file_access_allowed_folders=f"documents={folder}",
    )
    access = FileAccess(settings)

    result = access.read_file("notes.md", "documents")

    assert result.request_attempted is False
    assert result.safe_error == "File reading is disabled."


def test_file_access_absolute_path_read_rejected(tmp_path: Path) -> None:
    access = _build_file_access(tmp_path)

    result = access.read_file("C:\\Windows\\win.ini", "documents")

    assert result.request_attempted is False
    assert "plain filenames" in (result.safe_error or "")


def test_file_access_traversal_read_rejected(tmp_path: Path) -> None:
    access = _build_file_access(tmp_path)

    result = access.read_file("..\\secret.txt", "documents")

    assert result.request_attempted is False
    assert "plain filenames" in (result.safe_error or "")


def test_file_access_binary_file_rejected(tmp_path: Path) -> None:
    access = _build_file_access(tmp_path)

    result = access.read_file("binary.txt", "documents")

    assert result.request_attempted is True
    assert result.safe_error == "Binary files cannot be read safely."


def test_file_access_large_file_truncated_safely(tmp_path: Path) -> None:
    access = _build_file_access(tmp_path)

    result = access.read_file("large.txt", "documents")

    assert result.request_attempted is True
    assert result.safe_error is None
    assert result.truncated is True
    assert result.content_preview is not None
    assert len(result.content_preview) <= 4003


def test_file_access_disallowed_extension_rejected(tmp_path: Path) -> None:
    access = _build_file_access(tmp_path)

    result = access.read_file("beta.log", "documents")

    assert result.request_attempted is True
    assert "not allowed" in (result.safe_error or "")


def test_file_access_check_formats_safe_error() -> None:
    error = format_file_access_error(RuntimeError("failed with OPENAI_API_KEY=sk-test-secret"))

    assert "sk-test-secret" not in error
    assert "OPENAI_API_KEY" not in error


def test_file_access_reports_include_details(tmp_path: Path) -> None:
    listing = FolderListingResult(
        enabled=True,
        folder_name="documents",
        configured_path="C:/Users/Test/Documents",
        resolved_path="C:/Users/Test/Documents",
        allowed=True,
        configured=True,
        entries=[FileEntry(name="alpha.txt", is_directory=False, size_bytes=5, modified_at="2026-06-12T12:00:00")],
        log_file=tmp_path / "file_access.log",
    )
    search = FileSearchResult(
        enabled=True,
        folder_name="documents",
        query="alpha",
        configured_path="C:/Users/Test/Documents",
        resolved_path="C:/Users/Test/Documents",
        allowed=True,
        configured=True,
        request_attempted=True,
        matches=[FileEntry(name="alpha.txt", is_directory=False, size_bytes=5, modified_at="2026-06-12T12:00:00")],
        log_file=tmp_path / "file_access.log",
    )

    listing_text = format_folder_listing_report(listing)
    search_text = format_file_search_report(search)

    assert "Jarvis Folder Listing" in listing_text
    assert "alpha.txt" in listing_text
    assert "Jarvis File Search" in search_text
    assert "alpha.txt" in search_text


def test_assistant_core_routes_file_access_commands(tmp_path: Path) -> None:
    folder = tmp_path / "downloads"
    folder.mkdir()
    (folder / "report.txt").write_text("report", encoding="utf-8")
    settings = AppSettings(
        _env_file=None,
        log_dir=tmp_path,
        openai_enabled=False,
        file_access_enabled=True,
        file_access_allowed_folders=f"downloads={folder}",
    )
    assistant = AssistantCore(settings=settings, openai_service=FakeOpenAIService())

    list_response = assistant.handle_command("list downloads")
    find_response = assistant.handle_command("find file report in downloads")

    assert list_response.source == "file_access"
    assert "report.txt" in list_response.text or "Found" in list_response.text
    assert find_response.source == "file_access"
    assert "report.txt" in find_response.text


def test_assistant_core_routes_read_file_with_confirmation(tmp_path: Path) -> None:
    folder = tmp_path / "documents"
    folder.mkdir()
    (folder / "notes.md").write_text("line 1\nline 2", encoding="utf-8")
    settings = AppSettings(
        _env_file=None,
        log_dir=tmp_path,
        openai_enabled=False,
        file_access_enabled=True,
        file_read_enabled=True,
        confirmation_required=True,
        file_access_allowed_folders=f"documents={folder}",
    )
    confirmations: list[tuple[str, str, str]] = []

    def approve(action_name: str, risk_level: str, description: str):
        confirmations.append((action_name, risk_level, description))
        return ConfirmationResult(approved=True, denied=False, timed_out=False, reason="Approved.", log_file=tmp_path / "confirmations.log")

    assistant = AssistantCore(settings=settings, openai_service=FakeOpenAIService(), confirmation_handler=approve)

    response = assistant.handle_command("read file notes.md in documents")

    assert response.source == "file_access"
    assert response.accepted is True
    assert response.text == "line 1\nline 2"
    assert confirmations and confirmations[0][0] == "read file contents"


def test_assistant_core_read_file_confirmation_denied_blocks_read(tmp_path: Path) -> None:
    folder = tmp_path / "documents"
    folder.mkdir()
    (folder / "notes.md").write_text("line 1\nline 2", encoding="utf-8")
    settings = AppSettings(
        _env_file=None,
        log_dir=tmp_path,
        openai_enabled=False,
        file_access_enabled=True,
        file_read_enabled=True,
        confirmation_required=True,
        file_access_allowed_folders=f"documents={folder}",
    )

    def deny(action_name: str, risk_level: str, description: str):
        del action_name, risk_level, description
        return ConfirmationResult(approved=False, denied=True, timed_out=False, reason="Denied.", log_file=tmp_path / "confirmations.log")

    assistant = AssistantCore(settings=settings, openai_service=FakeOpenAIService(), confirmation_handler=deny)

    response = assistant.handle_command("read file notes.md in documents")

    assert response.source == "local"
    assert response.accepted is False
    assert response.text == "Denied."


def test_assistant_core_disabled_file_access_fallback(tmp_path: Path) -> None:
    assistant = AssistantCore(
        settings=AppSettings(_env_file=None, file_access_enabled=False, log_dir=tmp_path, openai_enabled=False),
        openai_service=FakeOpenAIService(),
    )

    response = assistant.handle_command("list documents")

    assert response.source == "local"
    assert response.text == "File access is disabled."


def test_file_access_cli_commands(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    from main import main

    class DummyFileAccess:
        def __init__(self, settings: AppSettings) -> None:
            del settings

        def run_check(self) -> FileAccessCheckReport:
            return FileAccessCheckReport(
                enabled=True,
                allowed_folders={"documents": "C:/Users/Test/Documents"},
                log_file=Path("logs/file_access.log"),
            )

        def list_folder(self, folder_name: str) -> FolderListingResult:
            return FolderListingResult(
                enabled=True,
                folder_name=folder_name,
                configured_path="C:/Users/Test/Documents",
                resolved_path="C:/Users/Test/Documents",
                allowed=True,
                configured=True,
                entries=[FileEntry(name="alpha.txt", is_directory=False, size_bytes=5, modified_at="2026-06-12T12:00:00")],
                log_file=Path("logs/file_access.log"),
            )

        def find_file(self, query: str, folder_name: str) -> FileSearchResult:
            return FileSearchResult(
                enabled=True,
                folder_name=folder_name,
                query=query,
                configured_path="C:/Users/Test/Documents",
                resolved_path="C:/Users/Test/Documents",
                allowed=True,
                configured=True,
                request_attempted=True,
                matches=[FileEntry(name="alpha.txt", is_directory=False, size_bytes=5, modified_at="2026-06-12T12:00:00")],
                log_file=Path("logs/file_access.log"),
            )

    monkeypatch.setattr("main.FileAccess", DummyFileAccess)

    check_exit = main(["--file-access-check"])
    check_output = capsys.readouterr().out
    list_exit = main(["--list-folder", "documents"])
    list_output = capsys.readouterr().out
    find_exit = main(["--find-file", "alpha", "documents"])
    find_output = capsys.readouterr().out

    assert check_exit == 0
    assert "Jarvis File Access Check" in check_output
    assert list_exit == 0
    assert "Jarvis Folder Listing" in list_output
    assert find_exit == 0
    assert "Jarvis File Search" in find_output


def test_file_read_cli_command(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    from main import main

    class DummyAssistant:
        def handle_command(self, command: str) -> AssistantResponse:
            assert command == "read file notes.md in documents"
            return AssistantResponse(text="line 1\nline 2", accepted=True, source="file_access")

    monkeypatch.setattr("main._build_cli_assistant", lambda settings: DummyAssistant())

    exit_code = main(["--read-file", "notes.md", "documents"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "line 1" in output
    assert "line 2" in output


def test_file_summary_cli_command(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    from main import main

    class DummyAssistant:
        def handle_command(self, command: str) -> AssistantResponse:
            assert command == "summarize file notes.md in documents"
            return AssistantResponse(text="A concise summary.", accepted=True, source="openai")

    monkeypatch.setattr("main._build_cli_assistant", lambda settings: DummyAssistant())

    exit_code = main(["--summarize-file", "notes.md", "documents"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "A concise summary." in output
