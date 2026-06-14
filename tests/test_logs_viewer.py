from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from config.settings import AppSettings
from diagnostics.logs import format_log_tail_report, format_logs_list_report, list_log_files, tail_log
from gui.log_viewer import LogViewerWindow
from gui.main_window import JarvisMainWindow


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_list_logs_reports_available_files(tmp_path: Path) -> None:
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "jarvis.log").write_text("one\n", encoding="utf-8")
    (tmp_path / "logs" / "sub").mkdir()
    (tmp_path / "logs" / "sub" / "audio.log").write_text("two\n", encoding="utf-8")

    settings = AppSettings(_env_file=None, log_dir=tmp_path / "logs")
    report = list_log_files(settings)
    text = format_logs_list_report(report)

    assert [item.name for item in report.items] == ["jarvis.log", "sub/audio.log"]
    assert "jarvis.log" in text
    assert "sub/audio.log" in text


def test_tail_log_redacts_secrets(tmp_path: Path) -> None:
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    log_file = logs_dir / "openai.log"
    log_file.write_text(
        "\n".join(
            [
                "api_key=sk-test-abcdef1234567890",
                "Authorization: Bearer token-123",
                "oauth_token=oauth-secret",
                "client_secret=client-secret-value",
                "normal line",
            ]
        ),
        encoding="utf-8",
    )

    report = tail_log(AppSettings(_env_file=None, log_dir=logs_dir), "openai.log", lines=10)
    text = format_log_tail_report(report)

    assert report.is_successful is True
    assert "sk-test-abcdef1234567890" not in text
    assert "token-123" not in text
    assert "oauth-secret" not in text
    assert "client-secret-value" not in text
    assert "[redacted]" in text
    assert "normal line" in text


def test_tail_log_rejects_traversal(tmp_path: Path) -> None:
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    settings = AppSettings(_env_file=None, log_dir=logs_dir)

    report = tail_log(settings, "..\\secret.log", lines=20)

    assert report.is_successful is False
    assert report.path is None
    assert "escapes" in (report.error or "").lower() or "invalid" in (report.error or "").lower()


def test_log_viewer_constructs(tmp_path: Path) -> None:
    app = _app()
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    (logs_dir / "jarvis.log").write_text("line one\nline two\n", encoding="utf-8")

    window = LogViewerWindow(AppSettings(_env_file=None, log_dir=logs_dir))

    assert window.windowTitle() == "Jarvis Log Viewer"
    assert window.refresh_button.text() == "Refresh"
    assert window.clear_button.text() == "Clear Display"
    assert window.log_list.count() == 1
    assert window.log_display.toPlainText()

    window.clear_display()
    assert window.log_display.toPlainText() == ""

    window.close()
    app.processEvents()


def test_gui_log_viewer_action_exists() -> None:
    app = _app()
    window = JarvisMainWindow(settings=AppSettings(_env_file=None), assistant=_StubAssistant())

    tray_actions = [action.text() for action in window.tray_icon.contextMenu().actions()]
    assert "Log Viewer" in tray_actions
    assert window.log_viewer_action is not None
    assert window.log_viewer_button.text() == "Log Viewer"

    window.close()
    app.processEvents()


class _StubAssistant:
    def handle_command(self, command: str) -> object:
        del command

        class Response:
            text = "handled"
            accepted = True

        return Response()
