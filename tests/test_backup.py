from __future__ import annotations

import os
import time
import zipfile
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from config.settings import AppSettings
from diagnostics.backup import (
    create_backup,
    format_backup_list_report,
    list_backups,
    plan_restore_backup,
    restore_backup,
)
from security.confirmation import ConfirmationResult


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _approve(*args) -> ConfirmationResult:
    del args
    return ConfirmationResult(approved=True, denied=False, timed_out=False, reason="Approved.")


def _deny(*args) -> ConfirmationResult:
    del args
    return ConfirmationResult(approved=False, denied=True, timed_out=False, reason="Denied.", errors=["Denied."])


def _runtime_paths(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        runtime_mode="source",
        runtime_root=tmp_path,
        config_root=tmp_path,
        env_path=tmp_path / ".env",
        logs_path=tmp_path / "logs",
        data_path=tmp_path / "data",
        credentials_path=tmp_path / "credentials",
    )


def test_backup_create_excludes_secrets_by_default(tmp_path: Path, monkeypatch) -> None:
    config_root = tmp_path / "config"
    config_root.mkdir()
    env_path = config_root / ".env"
    data_path = config_root / "data"
    credentials_path = config_root / "credentials"
    data_path.mkdir()
    credentials_path.mkdir()
    env_path.write_text("OPENAI_API_KEY=sk-secret\nWAKE_PHRASE=hey jarvis\n", encoding="utf-8")
    (data_path / "memory.db").write_bytes(b"sqlite")
    (credentials_path / "token_gmail.json").write_text("token-secret", encoding="utf-8")
    (credentials_path / "google_client_secret.json").write_text("client-secret", encoding="utf-8")

    fake_paths = _runtime_paths(config_root)
    monkeypatch.setattr("diagnostics.backup.resolve_runtime_paths", lambda settings: fake_paths)

    settings = AppSettings(
        _env_file=None,
        log_dir=config_root / "logs",
        backup_include_env=False,
        backup_include_tokens=False,
        backup_include_client_secret=False,
    )
    report = create_backup(settings, _approve)

    assert report.created is True
    assert report.archive_path.exists()
    with zipfile.ZipFile(report.archive_path, "r") as archive:
        names = sorted(archive.namelist())
        assert "README.backup.md" in names
        assert "data/memory.db" in names
        assert "credentials/token_gmail.json" not in names
        assert "credentials/google_client_secret.json" not in names
        env_text = archive.read("env/.env").decode("utf-8")
        assert "OPENAI_API_KEY" in env_text
        assert "sk-secret" not in env_text
        assert "[redacted]" in env_text


def test_backup_create_can_include_tokens_env_and_client_secret(tmp_path: Path, monkeypatch) -> None:
    config_root = tmp_path / "config"
    config_root.mkdir()
    env_path = config_root / ".env"
    data_path = config_root / "data"
    credentials_path = config_root / "credentials"
    data_path.mkdir()
    credentials_path.mkdir()
    env_path.write_text("OPENAI_API_KEY=sk-secret\nWAKE_PHRASE=hey jarvis\n", encoding="utf-8")
    (data_path / "memory.db").write_bytes(b"sqlite")
    (credentials_path / "token_gmail.json").write_text("token-secret", encoding="utf-8")
    (credentials_path / "google_client_secret.json").write_text("client-secret", encoding="utf-8")

    fake_paths = _runtime_paths(config_root)
    monkeypatch.setattr("diagnostics.backup.resolve_runtime_paths", lambda settings: fake_paths)

    settings = AppSettings(
        _env_file=None,
        log_dir=config_root / "logs",
        backup_include_env=True,
        backup_include_tokens=True,
        backup_include_client_secret=True,
    )
    report = create_backup(settings, _approve)

    with zipfile.ZipFile(report.archive_path, "r") as archive:
        names = archive.namelist()
        assert "credentials/token_gmail.json" in names
        assert "credentials/google_client_secret.json" in names
        env_text = archive.read("env/.env").decode("utf-8")
        assert "sk-secret" in env_text


def test_backup_list_reports_backups(tmp_path: Path, monkeypatch) -> None:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    first = backup_dir / "Jarvis-0.1.0-20260614_120000.zip"
    second = backup_dir / "Jarvis-0.1.0-20260614_121000.zip"
    first.write_bytes(b"one")
    time.sleep(0.05)
    second.write_bytes(b"two")
    os.utime(first, (1_700_000_000, 1_700_000_000))
    os.utime(second, (1_700_000_100, 1_700_000_100))

    monkeypatch.setattr("diagnostics.backup.get_backup_dir", lambda settings: backup_dir)
    report = list_backups(AppSettings(_env_file=None, log_dir=tmp_path / "logs"))
    text = format_backup_list_report(report)

    assert [item.path.name for item in report.items] == [second.name, first.name]
    assert "Backups: 2" in text
    assert second.name in text


def test_backup_restore_confirmation_denied(tmp_path: Path, monkeypatch) -> None:
    config_root = tmp_path / "config"
    config_root.mkdir()
    env_path = config_root / ".env"
    data_path = config_root / "data"
    credentials_path = config_root / "credentials"
    data_path.mkdir()
    credentials_path.mkdir()
    env_path.write_text("WAKE_PHRASE=old\n", encoding="utf-8")
    (data_path / "memory.db").write_bytes(b"old")

    fake_paths = _runtime_paths(config_root)
    monkeypatch.setattr("diagnostics.backup.resolve_runtime_paths", lambda settings: fake_paths)

    settings = AppSettings(_env_file=None, log_dir=config_root / "logs")
    create_result = create_backup(settings, _approve)

    env_path.write_text("WAKE_PHRASE=old\n", encoding="utf-8")
    (data_path / "memory.db").write_bytes(b"old")
    restore_result = restore_backup(settings, create_result.archive_path, _deny)

    assert restore_result.is_successful is False
    assert env_path.read_text(encoding="utf-8") == "WAKE_PHRASE=old\n"
    assert (data_path / "memory.db").read_bytes() == b"old"


def test_backup_restore_rejects_zip_slip(tmp_path: Path, monkeypatch) -> None:
    config_root = tmp_path / "config"
    config_root.mkdir()
    fake_paths = _runtime_paths(config_root)
    monkeypatch.setattr("diagnostics.backup.resolve_runtime_paths", lambda settings: fake_paths)

    backup_zip = tmp_path / "bad.zip"
    with zipfile.ZipFile(backup_zip, "w") as archive:
        archive.writestr("../evil.txt", "evil")

    plan = plan_restore_backup(AppSettings(_env_file=None, log_dir=config_root / "logs"), backup_zip)

    assert plan.is_successful is False
    assert plan.errors
    assert "unsafe" in plan.errors[0].lower() or "unsupported" in plan.errors[0].lower()


def test_backup_gui_actions_exist() -> None:
    app = _app()
    from gui.main_window import JarvisMainWindow

    window = JarvisMainWindow(settings=AppSettings(_env_file=None), assistant=_StubAssistant())

    tray_actions = [action.text() for action in window.tray_icon.contextMenu().actions()]
    assert "Create Backup" in tray_actions
    assert "List Backups" in tray_actions
    assert window.backup_create_button.text() == "Create Backup"
    assert window.backup_list_button.text() == "List Backups"
    assert window.backup_create_action is not None
    assert window.backup_list_action is not None

    window.close()
    app.processEvents()


class _StubAssistant:
    def handle_command(self, command: str) -> object:
        del command

        class Response:
            text = "handled"
            accepted = True

        return Response()
