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
        class Response:
            def __init__(self, text: str, accepted: bool = True) -> None:
                self.text = text
                self.accepted = accepted

        if command == "check reminders":
            return Response("Due reminders:\n1. stretch at 2026-06-12 18:00", accepted=True)
        return Response("handled")


def test_voice_loop_gui_state_updates_controls_and_status_fields() -> None:
    app = _app()
    settings = AppSettings(_env_file=None)
    window = JarvisMainWindow(settings=settings, assistant=StubAssistant())

    assert window.tabs.count() == 5
    assert [window.tabs.tabText(index) for index in range(window.tabs.count())] == [
        "Voice",
        "Tools",
        "Reminders",
        "Memory",
        "Diagnostics",
    ]
    assert window.mode_value.text() == "Idle"
    assert window.agent_enabled_value.text() in {"Enabled", "Disabled"}
    assert window.start_voice_loop_button.isEnabled() is True
    assert window.stop_voice_loop_button.isEnabled() is False
    assert window.chat_test_button.text() == "Chat Test"
    assert window.weather_check_button.text() == "Weather Check"
    assert window.vision_check_button.text() == "Vision Check"
    assert window.agent_test_button.text() == "Agent Test"
    assert window.health_check_button.text() == "Run Health Check"

    window._set_voice_loop_running(True)

    assert window.start_voice_loop_button.isEnabled() is False
    assert window.stop_voice_loop_button.isEnabled() is True
    assert window.start_voice_loop_action is not None
    assert window.stop_voice_loop_action is not None
    assert window.start_voice_loop_action.isEnabled() is False
    assert window.stop_voice_loop_action.isEnabled() is True
    assert window.check_reminders_button.isEnabled() is True
    assert window.notification_test_button.isEnabled() is True
    assert window.launch_notepad_button.isEnabled() is True
    assert window.start_reminder_watch_button.isEnabled() is True
    assert window.stop_reminder_watch_button.isEnabled() is False
    assert window.mode_value.text() == "Voice Loop"

    window._set_reminder_watch_running(True)
    assert window.start_reminder_watch_button.isEnabled() is False
    assert window.stop_reminder_watch_button.isEnabled() is True
    assert window.start_reminder_watch_action is not None
    assert window.stop_reminder_watch_action is not None
    assert window.start_reminder_watch_action.isEnabled() is False
    assert window.stop_reminder_watch_action.isEnabled() is True
    window._handle_reminder_watch_status("Reminder watcher started.")
    window._handle_reminder_watch_status("Due reminders:\n1. stretch at 2026-06-12 18:00")
    window._handle_reminder_watch_status("Reminder watcher summary: checks=1, due notifications=1, errors=0")
    window._set_reminder_watch_running(False)
    window._set_notification_result("Delivered")
    window._set_app_launch_result("Launched")

    window._handle_voice_loop_status("Last recognized command: status report")
    window._handle_voice_loop_status("Last Jarvis response: handled status report")
    window._handle_voice_loop_status(RETURNING_TO_SLEEP_MESSAGE)
    window.check_reminders()
    window.run_health_check()

    assert window.voice_loop_status_value.text() == RETURNING_TO_SLEEP_MESSAGE
    assert window.voice_loop_last_command_value.text() == "status report"
    assert window.voice_loop_last_response_value.text() == "handled status report"
    assert window.reminders_check_value.text() == "Due reminders:"
    assert window.notification_result_value.text() == "Delivered"
    assert window.health_result_value.text() == "Completed"
    assert window.app_launch_result_value.text() == "Launched"
    assert window.reminder_watch_status_value.text() == "Idle"

    tray_actions = [action.text() for action in window.tray_icon.contextMenu().actions()]
    assert "Show Jarvis" in tray_actions
    assert "Start Voice Loop" in tray_actions
    assert "Stop Voice Loop" in tray_actions
    assert "Check Reminders" in tray_actions
    assert "Test Notification" in tray_actions
    assert "Exit Jarvis" in tray_actions

    window.close()
    app.processEvents()
