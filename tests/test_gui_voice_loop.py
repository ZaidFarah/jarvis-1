from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from config.settings import AppSettings
from gui.main_window import JarvisMainWindow
from voice.voice_loop import RETURNING_TO_SLEEP_MESSAGE


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


class StubAssistant:
    def handle_command(self, command: str) -> object:
        del command
        return object()


def test_voice_loop_gui_state_updates_controls_and_status_fields() -> None:
    app = _app()
    settings = AppSettings(_env_file=None)
    window = JarvisMainWindow(settings=settings, assistant=StubAssistant())

    assert window.start_voice_loop_button.isEnabled() is True
    assert window.stop_voice_loop_button.isEnabled() is False

    window._set_voice_loop_running(True)

    assert window.start_voice_loop_button.isEnabled() is False
    assert window.stop_voice_loop_button.isEnabled() is True
    assert window.start_voice_loop_action is not None
    assert window.stop_voice_loop_action is not None
    assert window.start_voice_loop_action.isEnabled() is False
    assert window.stop_voice_loop_action.isEnabled() is True

    window._handle_voice_loop_status("Last recognized command: status report")
    window._handle_voice_loop_status("Last Jarvis response: handled status report")
    window._handle_voice_loop_status(RETURNING_TO_SLEEP_MESSAGE)

    assert window.voice_loop_status_value.text() == RETURNING_TO_SLEEP_MESSAGE
    assert window.voice_loop_last_command_value.text() == "status report"
    assert window.voice_loop_last_response_value.text() == "handled status report"

    window.close()
    app.processEvents()
