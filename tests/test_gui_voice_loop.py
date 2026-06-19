from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from config.settings import AppSettings
import gui.main_window as main_window_module
from gui.main_window import JarvisMainWindow
from voice.fast_voice import FastVoiceProgress
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
    assert window.voice_stt_model_value.text() == settings.whisper_model
    assert window.voice_stt_device_value.text() == f"{settings.whisper_device} / {settings.whisper_compute_type}"
    assert window.voice_wake_provider_value.text() == settings.wake_provider
    assert window.voice_tts_provider_value.text() == settings.tts_provider
    assert window.voice_response_mode_value.text() == settings.voice_response_mode
    assert window.voice_wake_ack_value.text() == "Off"
    assert window.voice_response_speech_value.text() == "TTS OFF: text-only mode"
    assert window.voice_raw_speech_value.text() == "--"
    assert window.voice_cleaned_value.text() == "--"
    assert window.voice_interpreted_value.text() == "--"
    assert window.voice_wake_only_value.text() == "--"
    assert window.voice_repair_confidence_value.text() == "--"
    assert window.voice_repair_strategy_value.text() == "--"
    assert window.voice_wake_score_bar.value() == 0
    assert window.voice_transcript_confidence_bar.value() == 0
    assert window.voice_command_score_bar.value() == 0
    assert window.voice_repair_confidence_bar.value() == 0
    assert window.voice_timing_wake_capture_value.text() == "--"
    assert window.voice_timing_total_value.text() == "--"
    assert window.agent_enabled_value.text() in {"Enabled", "Disabled"}
    assert window.start_voice_loop_button.text() == "Start Listening"
    assert window.stop_voice_loop_button.text() == "Stop Voice"
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
    assert "Start Listening" in tray_actions
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
        "average_rms=0.015000 max_rms=0.040000 vad_crossed=yes transcript_confidence=0.85 command_score=0.67"
    )
    window._handle_voice_loop_status(
        f"{SPEECH_REPAIR_PREFIX} raw=Did it noting him today? What's the | "
        "repaired=what's the weather in Nottingham today | confidence=0.92 | "
        "strategy=rule | reason=matched repair rule"
    )
    window._handle_voice_loop_status(
        "Timing summary: wake_capture_ms=12.3 wake_transcribe_ms=34.5 command_capture_ms=56.7 "
        "command_transcribe_ms=78.9 openai_ms=0.0 tts_ms=0.0 total_turn_ms=123.4 slow_stages=command_capture_ms"
    )

    assert window.status.value == "Follow-up"
    assert window.voice_provider_value.text() == "fake_stt"
    assert window.voice_wake_score_value.text() == "0.810 / 0.720"
    assert window.voice_rms_value.text() == "0.015000 / 0.040000"
    assert window.voice_vad_value.text() == "yes"
    assert window.voice_command_score_value.text() == "0.67"
    assert window.voice_wake_score_bar.value() == 81
    assert window.voice_transcript_confidence_bar.value() == 85
    assert window.voice_command_score_bar.value() == 67
    assert window.voice_repair_confidence_bar.value() == 92
    assert window.voice_timing_wake_capture_value.text() == "12 ms"
    assert window.voice_timing_wake_transcribe_value.text() == "34 ms"
    assert window.voice_timing_command_capture_value.text() == "57 ms"
    assert window.voice_timing_command_transcribe_value.text() == "79 ms"
    assert window.voice_timing_total_value.text() == "123 ms"
    assert window.voice_timing_slow_value.text() == "command_capture_ms"

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


def test_fast_voice_gui_report_populates_existing_hud_panels() -> None:
    app = _app()
    window = JarvisMainWindow(
        settings=AppSettings(_env_file=None, gui_voice_engine="fast"),
        assistant=StubAssistant(),
    )
    report = SimpleNamespace(
        provider_name="faster_whisper",
        transcript_confidence=0.91,
        raw_transcript="Hey Jarvis, status reports",
        cleaned_transcript="status reports",
        command="status report",
        assistant_response=SimpleNamespace(text="Systems nominal."),
        command_accepted=True,
        validation=SimpleNamespace(rejection_reason=None),
        tts_result=None,
        vad_crossed=True,
        wake_only=False,
        speech_repair=SimpleNamespace(strategy="common_intent", confidence=0.94),
        timing=SimpleNamespace(
            vad_wait_ms=160.0,
            audio_prepare_ms=12.0,
            capture_ms=1280.0,
            transcribe_ms=545.0,
            openai_ms=1387.0,
            tts_ms=0.0,
            total_ms=3700.0,
            speech_ms=720.0,
            trailing_silence_ms=320.0,
        ),
        errors=[],
    )

    for status in ("Listening", "Transcribing", "Thinking", "Responding"):
        window._handle_fast_voice_status(status)
        assert window.voice_loop_status_value.text() == status

    window._handle_fast_voice_report(report)  # type: ignore[arg-type]

    assert window.voice_raw_speech_value.text() == "Hey Jarvis, status reports"
    assert window.voice_cleaned_value.text() == "status reports"
    assert window.voice_interpreted_value.text() == "status report"
    assert window.voice_response_panel.toPlainText() == "Systems nominal."
    assert window.voice_vad_value.text() == "yes"
    assert window.voice_wake_only_value.text() == "no"
    assert window.voice_transcript_confidence_bar.value() == 91
    assert window.voice_timing_command_capture_value.text() == "1280 ms"
    assert window.voice_timing_command_transcribe_value.text() == "545 ms"
    assert window.voice_timing_openai_value.text() == "1387 ms"
    assert window.voice_timing_total_value.text() == "3700 ms"
    assert window.voice_response_speech_value.text() == "TTS OFF: text-only mode"

    report.command_accepted = False
    report.validation = SimpleNamespace(
        rejection_reason="likely misheard or incomplete command"
    )
    report.assistant_response = SimpleNamespace(
        text="That sounded incomplete or misheard. Please try again and speak clearly."
    )
    window._handle_fast_voice_report(report)  # type: ignore[arg-type]
    assert window.voice_detail_value.text() == (
        "Command rejected: likely misheard or incomplete command. Please try again."
    )
    assert "misheard" in window.voice_response_panel.toPlainText()

    window._allow_close = True
    window.close()
    app.processEvents()


def test_fast_voice_gui_shows_live_capture_progress() -> None:
    app = _app()
    window = JarvisMainWindow(
        settings=AppSettings(_env_file=None, gui_voice_engine="fast"),
        assistant=StubAssistant(),
    )
    events = [
        FastVoiceProgress(stage="listening_started"),
        FastVoiceProgress(
            stage="vad_waiting",
            capture_elapsed_ms=240.0,
            capture_progress=0.2,
        ),
        FastVoiceProgress(
            stage="vad_triggered",
            vad_crossed=True,
            capture_elapsed_ms=320.0,
            capture_progress=0.3,
        ),
        FastVoiceProgress(
            stage="speech_detected",
            vad_crossed=True,
            speech_ms=640.0,
            capture_elapsed_ms=960.0,
            capture_progress=0.6,
        ),
        FastVoiceProgress(
            stage="silence_detected",
            vad_crossed=True,
            speech_ms=640.0,
            trailing_silence_ms=160.0,
            capture_elapsed_ms=1120.0,
            capture_progress=0.8,
        ),
        FastVoiceProgress(
            stage="capture_complete",
            vad_crossed=True,
            speech_ms=640.0,
            trailing_silence_ms=160.0,
            capture_elapsed_ms=1120.0,
            capture_progress=1.0,
        ),
        FastVoiceProgress(stage="transcribing", vad_crossed=True, capture_progress=1.0),
        FastVoiceProgress(
            stage="transcript_ready",
            vad_crossed=True,
            capture_progress=1.0,
            transcript="status report",
        ),
        FastVoiceProgress(stage="thinking", vad_crossed=True, capture_progress=1.0),
        FastVoiceProgress(
            stage="response_ready",
            vad_crossed=True,
            capture_progress=1.0,
            transcript="status report",
            response="Systems nominal.",
        ),
    ]

    for event in events:
        window._handle_fast_voice_progress(event)

    assert window.voice_loop_status_value.text() == "Response ready"
    assert window.voice_detail_value.text() == "Response ready"
    assert window.voice_vad_value.text() == "yes"
    assert window.voice_command_score_value.text() == "100%"
    assert window.voice_command_score_bar.value() == 100
    assert window.transcript.toPlainText() == "status report"
    assert window.voice_raw_speech_value.text() == "status report"
    assert window.voice_response_panel.toPlainText() == "Systems nominal."

    window._allow_close = True
    window.close()
    app.processEvents()


def test_fast_voice_gui_appends_streaming_response_chunks() -> None:
    app = _app()
    window = JarvisMainWindow(
        settings=AppSettings(
            _env_file=None,
            gui_voice_engine="fast",
            gui_stream_response=True,
            fast_voice_stream_openai=True,
        ),
        assistant=StubAssistant(),
    )
    window.voice_response_panel.setText("Previous response")

    window._handle_fast_voice_progress(
        FastVoiceProgress(stage="thinking", vad_crossed=True, capture_progress=1.0)
    )
    assert window.voice_response_panel.toPlainText() == ""

    window._handle_fast_voice_response_chunk("Systems ")
    window._handle_fast_voice_response_chunk("nominal.")

    assert window.voice_loop_status_value.text() == "Responding"
    assert window.voice_detail_value.text() == "Streaming response"
    assert window.voice_response_panel.toPlainText() == "Systems nominal."

    window._handle_fast_voice_progress(
        FastVoiceProgress(
            stage="response_ready",
            vad_crossed=True,
            capture_progress=1.0,
            response="Systems nominal.",
        )
    )
    assert window.voice_response_panel.toPlainText() == "Systems nominal."

    window._allow_close = True
    window.close()
    app.processEvents()


def test_fast_voice_gui_preserves_response_when_streaming_is_disabled() -> None:
    app = _app()
    window = JarvisMainWindow(
        settings=AppSettings(
            _env_file=None,
            gui_voice_engine="fast",
            gui_stream_response=False,
            fast_voice_stream_openai=False,
        ),
        assistant=StubAssistant(),
    )
    window.voice_response_panel.setText("Previous response")

    window._handle_fast_voice_progress(
        FastVoiceProgress(stage="thinking", vad_crossed=True, capture_progress=1.0)
    )
    window._handle_fast_voice_response_chunk("ignored")

    assert window.voice_response_panel.toPlainText() == "Previous response"

    window._allow_close = True
    window.close()
    app.processEvents()


def test_fast_voice_gui_shows_tts_enabled_status() -> None:
    app = _app()
    window = JarvisMainWindow(
        settings=AppSettings(
            _env_file=None,
            gui_voice_engine="fast",
            fast_voice_tts_enabled=True,
        ),
        assistant=StubAssistant(),
    )

    assert window.voice_response_speech_value.text() == "TTS ON: speaking enabled"

    window._allow_close = True
    window.close()
    app.processEvents()


def test_gui_start_voice_selects_fast_engine_and_stop_requests_shutdown(monkeypatch) -> None:
    app = _app()

    class FakeFastRunner:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.stop_requested = False

        def run_continuous(self, *, max_turns: int | None = None) -> int:
            self.max_turns = max_turns
            return 0

        def request_stop(self) -> None:
            self.stop_requested = True

    class FakeThread:
        def __init__(self, *, target, daemon: bool) -> None:
            self.target = target
            self.daemon = daemon
            self.started = False

        def start(self) -> None:
            self.started = True

        def is_alive(self) -> bool:
            return self.started

    monkeypatch.setattr(main_window_module, "FastVoiceRunner", FakeFastRunner)
    monkeypatch.setattr(main_window_module.threading, "Thread", FakeThread)
    window = JarvisMainWindow(
        settings=AppSettings(_env_file=None, gui_voice_engine="fast"),
        assistant=StubAssistant(),
    )

    window.start_voice_loop()

    assert isinstance(window.fast_voice_runner, FakeFastRunner)
    assert window.voice_loop_runner is None
    assert window.current_mode == "Fast Voice"
    assert window.start_voice_loop_button.isEnabled() is False
    assert window.stop_voice_loop_button.isEnabled() is True
    assert window.fast_voice_runner.kwargs["strict_command_validation"] is True
    assert callable(window.fast_voice_runner.kwargs["progress_callback"])
    assert callable(window.fast_voice_runner.kwargs["response_chunk_callback"])
    assert window.fast_voice_runner.kwargs["capture_max_seconds"] == 2.5

    window._run_fast_voice_worker()
    assert window.fast_voice_runner.max_turns == 1

    runner = window.fast_voice_runner
    window.stop_voice_loop()
    assert runner.stop_requested is True

    window.voice_loop_event_timer.stop()
    window.fast_voice_runner = None
    window.voice_loop_thread = None
    window._allow_close = True
    window.close()
    app.processEvents()


def test_gui_voice_engine_legacy_keeps_voice_loop_available(monkeypatch) -> None:
    app = _app()

    class FakeLegacyRunner:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.stop_requested = False

        def run(self) -> int:
            return 0

        def request_stop(self) -> None:
            self.stop_requested = True

    class FakeThread:
        def __init__(self, *, target, daemon: bool) -> None:
            self.target = target
            self.started = False

        def start(self) -> None:
            self.started = True

        def is_alive(self) -> bool:
            return self.started

    monkeypatch.setattr(main_window_module, "VoiceLoopRunner", FakeLegacyRunner)
    monkeypatch.setattr(main_window_module.threading, "Thread", FakeThread)
    window = JarvisMainWindow(
        settings=AppSettings(_env_file=None, gui_voice_engine="legacy"),
        assistant=StubAssistant(),
    )

    window.start_voice_loop()

    assert isinstance(window.voice_loop_runner, FakeLegacyRunner)
    assert window.fast_voice_runner is None
    assert window.current_mode == "Voice Loop"

    window.voice_loop_event_timer.stop()
    window.voice_loop_runner = None
    window.voice_loop_thread = None
    window._allow_close = True
    window.close()
    app.processEvents()
