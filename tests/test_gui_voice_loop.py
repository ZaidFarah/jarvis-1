from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from config.settings import AppSettings
from gui.main_window import JarvisMainWindow
from voice.voice_command_test import NO_COMMAND_DETECTED_MESSAGE
from voice.voice_loop import (
    ACCEPTED_COMMAND_PREFIX,
    ACCEPTED_FOLLOW_UP_PREFIX,
    CAPTURE_DIAGNOSTICS_PREFIX,
    LISTENING_FOR_FOLLOW_UP_PROMPT,
    REJECTED_COMMAND_PREFIX,
    REJECTED_FOLLOW_UP_PREFIX,
    RETURNING_TO_SLEEP_MESSAGE,
    RETRYING_COMMAND_CAPTURE_MESSAGE,
    RETRYING_FOLLOW_UP_CAPTURE_MESSAGE,
    SPEECH_REPAIR_PREFIX,
    WAKE_DIAGNOSTICS_PREFIX,
)


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
    assert window.voice_state_value.text() == "Sleeping"
    assert window.voice_detail_value.text() == "Waiting for wake phrase"
    assert window.voice_response_panel.toPlainText() == "Jarvis responses will appear here."
    assert window.voice_provider_value.text() == settings.speech_to_text_provider
    assert window.voice_raw_speech_value.text() == "--"
    assert window.voice_interpreted_value.text() == "--"
    assert window.voice_repair_confidence_value.text() == "--"
    assert window.voice_repair_strategy_value.text() == "--"
    assert window.agent_enabled_value.text() in {"Enabled", "Disabled"}
    assert window.start_voice_loop_button.isEnabled() is True
    assert window.stop_voice_loop_button.isEnabled() is False
    assert window.chat_test_button.text() == "Chat Test"
    assert window.weather_check_button.text() == "Weather Check"
    assert window.vision_check_button.text() == "Vision Check"
    assert window.agent_test_button.text() == "Agent Test"
    assert window.health_check_button.text() == "Run Health Check"
    assert window.settings_button.text() == "Settings"
    assert window.startup_check_button.text() == "Startup Check"
    assert window.startup_enable_button.text() == "Enable Startup"
    assert window.startup_disable_button.text() == "Disable Startup"
    assert window.backup_create_button.text() == "Create Backup"
    assert window.backup_list_button.text() == "List Backups"

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
    assert window.voice_response_panel.toPlainText() == "handled status report"
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
    assert "Settings" in tray_actions
    assert "Log Viewer" in tray_actions
    assert "Create Backup" in tray_actions
    assert "List Backups" in tray_actions
    assert window.settings_action is not None
    assert window.log_viewer_action is not None
    assert window.backup_create_action is not None
    assert window.backup_list_action is not None

    window.close()
    app.processEvents()


def test_voice_loop_gui_displays_reject_retry_accept_response_and_sleep() -> None:
    app = _app()
    settings = AppSettings(_env_file=None)
    window = JarvisMainWindow(settings=settings, assistant=StubAssistant())

    window._handle_voice_loop_status("Last recognized command: you")
    window._handle_voice_loop_status(f"{REJECTED_COMMAND_PREFIX} you (rejected phrase: you)")
    window._handle_voice_loop_status(NO_COMMAND_DETECTED_MESSAGE)
    window._handle_voice_loop_status(RETRYING_COMMAND_CAPTURE_MESSAGE)
    window._handle_voice_loop_status("Last recognized command: status report")
    window._handle_voice_loop_status(f"{ACCEPTED_COMMAND_PREFIX} status report")
    window._handle_voice_loop_status("Last Jarvis response: handled status report")
    window._handle_voice_loop_status(RETURNING_TO_SLEEP_MESSAGE)

    assert window.voice_loop_last_command_value.text() == "status report"
    assert window.voice_loop_last_response_value.text() == "handled status report"
    assert window.voice_loop_status_value.text() == RETURNING_TO_SLEEP_MESSAGE
    transcript = window.transcript.toPlainText()
    assert f"{REJECTED_COMMAND_PREFIX} you (rejected phrase: you)" in transcript
    assert NO_COMMAND_DETECTED_MESSAGE in transcript
    assert RETRYING_COMMAND_CAPTURE_MESSAGE in transcript
    assert f"{ACCEPTED_COMMAND_PREFIX} status report" in transcript
    assert "Jarvis: handled status report" in transcript

    window.close()
    app.processEvents()


def test_voice_loop_gui_displays_follow_up_states() -> None:
    app = _app()
    settings = AppSettings(_env_file=None)
    window = JarvisMainWindow(settings=settings, assistant=StubAssistant())

    window._handle_voice_loop_status(LISTENING_FOR_FOLLOW_UP_PROMPT)
    assert window.voice_loop_status_value.text() == LISTENING_FOR_FOLLOW_UP_PROMPT

    window._handle_voice_loop_status(f"{REJECTED_FOLLOW_UP_PREFIX} you (rejected phrase: you)")
    assert window.voice_loop_last_command_value.text() == "Rejected follow-up: you"
    assert window.voice_loop_status_value.text() == "Rejected follow-up"

    window._handle_voice_loop_status(NO_COMMAND_DETECTED_MESSAGE)
    window._handle_voice_loop_status(RETRYING_FOLLOW_UP_CAPTURE_MESSAGE)
    assert window.voice_loop_status_value.text() == "Retrying follow-up capture"

    window._handle_voice_loop_status("Last recognized command: weather report")
    window._handle_voice_loop_status(f"{ACCEPTED_FOLLOW_UP_PREFIX} weather report")
    window._handle_voice_loop_status("Last Jarvis response: handled weather report")
    window._handle_voice_loop_status(RETURNING_TO_SLEEP_MESSAGE)

    assert window.voice_loop_last_command_value.text() == "weather report"
    assert window.voice_loop_last_response_value.text() == "handled weather report"
    assert window.voice_loop_status_value.text() == RETURNING_TO_SLEEP_MESSAGE
    assert window.voice_response_panel.toPlainText() == "handled weather report"
    transcript = window.transcript.toPlainText()
    assert LISTENING_FOR_FOLLOW_UP_PROMPT in transcript
    assert f"{REJECTED_FOLLOW_UP_PREFIX} you (rejected phrase: you)" in transcript
    assert RETRYING_FOLLOW_UP_CAPTURE_MESSAGE in transcript
    assert f"{ACCEPTED_FOLLOW_UP_PREFIX} weather report" in transcript
    assert "Jarvis: handled weather report" in transcript

    window.close()
    app.processEvents()


def test_voice_loop_gui_updates_live_diagnostics_without_state_regression() -> None:
    app = _app()
    settings = AppSettings(_env_file=None)
    window = JarvisMainWindow(settings=settings, assistant=StubAssistant())

    window._handle_voice_loop_status(LISTENING_FOR_FOLLOW_UP_PROMPT)
    assert window.status.value == "Follow-up"

    window._handle_voice_loop_status(
        f"{WAKE_DIAGNOSTICS_PREFIX} provider=whisper_fuzzy score=0.810 threshold=0.720 "
        "average_rms=0.010000 max_rms=0.020000 vad_crossed=yes"
    )
    window._handle_voice_loop_status(
        f"{CAPTURE_DIAGNOSTICS_PREFIX} provider=fake_stt sample_rate=16000 record_seconds=15.00 "
        "average_rms=0.015000 max_rms=0.040000 vad_crossed=yes"
    )

    assert window.status.value == "Follow-up"
    assert window.voice_provider_value.text() == "fake_stt"
    assert window.voice_wake_score_value.text() == "0.810 / 0.720"
    assert window.voice_rms_value.text() == "0.015000 / 0.040000"
    assert window.voice_vad_value.text() == "yes"

    window.close()
    app.processEvents()


def test_voice_loop_gui_updates_speech_repair_display() -> None:
    app = _app()
    settings = AppSettings(_env_file=None)
    window = JarvisMainWindow(settings=settings, assistant=StubAssistant())

    window._handle_voice_loop_status(
        f"{SPEECH_REPAIR_PREFIX} raw=Did it noting him today? What's the | "
        "repaired=what's the weather in Nottingham today | "
        "confidence=0.92 | strategy=rule | reason=matched repair rule"
    )
    window._handle_voice_loop_status("Did you mean: what's the weather in Nottingham today?")

    assert window.voice_raw_speech_value.text() == "Did it noting him today? What's the"
    assert window.voice_interpreted_value.text() == "what's the weather in Nottingham today"
    assert window.voice_repair_confidence_value.text() == "92%"
    assert window.voice_repair_strategy_value.text() == "rule"
    assert window.voice_loop_status_value.text() == "Confirming repair"

    window.close()
    app.processEvents()
