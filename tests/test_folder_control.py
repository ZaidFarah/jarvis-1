from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from assistant.core import AssistantCore
from config.settings import AppSettings
from tools.folder_control import (
    FolderControl,
    FolderOpenResult,
    RecentDownloadsResult,
    format_folder_control_open_report,
    format_recent_downloads_report,
)


class FakeOpenAIService:
    def chat(self, *args, **kwargs):  # pragma: no cover - defensive helper
        del args, kwargs
        raise AssertionError("OpenAI should not be called")


@dataclass
class FakeAppLauncherResult:
    resolved_path: str | None
    safe_error: str | None = None


class FakeAppLauncher:
    def __init__(self, resolved_path: str | None) -> None:
        self.resolved_path = resolved_path

    def resolve_only(self, app_name: str) -> FakeAppLauncherResult:
        assert app_name == "vscode"
        return FakeAppLauncherResult(resolved_path=self.resolved_path)


def _build_settings(tmp_path: Path) -> AppSettings:
    root = tmp_path / "folders"
    documents = root / "Documents"
    desktop = root / "Desktop"
    downloads = root / "Downloads"
    pictures = root / "Pictures"
    videos = root / "Videos"
    music = root / "Music"
    for folder in (documents, desktop, downloads, pictures, videos, music):
        folder.mkdir(parents=True, exist_ok=True)

    (downloads / "old.txt").write_text("old", encoding="utf-8")
    (downloads / "new.txt").write_text("new", encoding="utf-8")
    old_time = 1_700_000_000
    new_time = 1_700_000_100
    import os

    os.utime(downloads / "old.txt", (old_time, old_time))
    os.utime(downloads / "new.txt", (new_time, new_time))

    allowed = ",".join(
        [
            f"documents={documents}",
            f"desktop={desktop}",
            f"downloads={downloads}",
            f"pictures={pictures}",
            f"videos={videos}",
            f"music={music}",
        ]
    )
    return AppSettings(
        _env_file=None,
        log_dir=tmp_path,
        file_access_enabled=True,
        file_access_allowed_folders=allowed,
    )


def test_folder_control_open_whitelisted_folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    opened: list[str] = []

    def fake_startfile(path: str) -> None:
        opened.append(path)

    control = FolderControl(settings, startfile=fake_startfile)
    result = control.open_folder("downloads")

    assert result.opened is True
    assert opened
    assert Path(opened[0]).name == "Downloads"


def test_folder_control_rejects_unlisted_folder(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    control = FolderControl(settings, startfile=lambda *_args, **_kwargs: None)

    result = control.open_folder("system32")

    assert result.opened is False
    assert result.allowed is False
    assert "not allowed" in (result.safe_error or "")


def test_folder_control_opens_jarvis_project(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    opened: list[str] = []

    def fake_startfile(path: str) -> None:
        opened.append(path)

    monkeypatch.setattr("tools.folder_control.PROJECT_ROOT", tmp_path / "JarvisProject")
    (tmp_path / "JarvisProject").mkdir()

    control = FolderControl(settings, startfile=fake_startfile)
    result = control.open_jarvis_project()

    assert result.opened is True
    assert opened[0].endswith("JarvisProject")


def test_folder_control_opens_jarvis_in_vscode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    launched: list[list[str]] = []
    monkeypatch.setattr("tools.folder_control.PROJECT_ROOT", tmp_path / "JarvisProject")
    (tmp_path / "JarvisProject").mkdir()

    def fake_popen(args, shell=False):
        launched.append(list(args))
        assert shell is False
        return object()

    control = FolderControl(
        settings,
        app_launcher=FakeAppLauncher("C:/Program Files/Microsoft VS Code/Code.exe"),
        popen_factory=fake_popen,
    )
    result = control.open_jarvis_in_vscode()

    assert result.opened is True
    assert launched
    assert launched[0][1].endswith("JarvisProject")


def test_folder_control_recent_downloads_lists_latest_first(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    control = FolderControl(settings, startfile=lambda *_args, **_kwargs: None)

    result = control.show_recent_downloads(limit=2)

    assert result.request_attempted is True
    assert result.safe_error is None
    assert result.recent_entries == ["new.txt", "old.txt"]


def test_assistant_core_routes_folder_commands_locally(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    opened: list[str] = []
    launched: list[list[str]] = []

    def fake_startfile(path: str) -> None:
        opened.append(path)

    def fake_popen(args, shell=False):
        launched.append(list(args))
        assert shell is False
        return object()

    monkeypatch.setattr("tools.folder_control.PROJECT_ROOT", tmp_path / "JarvisProject")
    (tmp_path / "JarvisProject").mkdir()

    assistant = AssistantCore(
        settings=settings,
        openai_service=FakeOpenAIService(),
    )
    assistant.folder_control = FolderControl(
        settings,
        app_launcher=FakeAppLauncher("C:/Program Files/Microsoft VS Code/Code.exe"),
        startfile=fake_startfile,
        popen_factory=fake_popen,
    )

    for command in [
        "open downloads",
        "open documents",
        "open desktop",
        "open pictures",
        "open videos",
        "open music",
        "open my jarvis folder",
        "open jarvis project",
        "open jarvis in vs code",
        "show recent downloads",
    ]:
        response = assistant.handle_command(command)
        assert response.source == "folder_control"
        assert response.accepted is True

    assert opened
    assert launched
    recent_response = assistant.handle_command("show recent downloads")
    assert "Recent downloads:" in recent_response.text


def test_folder_control_reports_include_details(tmp_path: Path) -> None:
    result = FolderOpenResult(
        enabled=True,
        folder_name="downloads",
        allowed=True,
        configured=True,
        request_attempted=True,
        opened=True,
        resolved_path="C:/Users/Test/Downloads",
        log_file=tmp_path / "folder_control.log",
    )
    recent = RecentDownloadsResult(
        enabled=True,
        folder_name="downloads",
        allowed=True,
        configured=True,
        request_attempted=True,
        opened=True,
        resolved_path="C:/Users/Test/Downloads",
        recent_entries=["new.txt", "old.txt"],
        log_file=tmp_path / "folder_control.log",
    )

    open_text = format_folder_control_open_report(result)
    recent_text = format_recent_downloads_report(recent)

    assert "Jarvis Folder Open" in open_text
    assert "Jarvis Recent Downloads" in recent_text
