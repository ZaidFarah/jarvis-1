from __future__ import annotations

import threading
from collections.abc import Callable
from enum import Enum
from queue import Empty, Queue
from typing import Any

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QFontMetrics, QIcon, QLinearGradient, QMouseEvent, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QDialog,
    QPushButton,
    QProgressBar,
    QSizePolicy,
    QStyle,
    QStyleOptionButton,
    QSystemTrayIcon,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from assistant.core import AssistantCore
from config.settings import AppSettings
from diagnostics.backup import create_backup, format_backup_create_report, format_backup_list_report, list_backups
from diagnostics.health import HealthService, format_health_check_report
from security.confirmation import confirm_action_gui, format_confirmation_result
from reminders.scheduler import ReminderWatcher
from services.notification_service import NotificationService, format_notification_check_report
from services.startup_service import StartupService, format_startup_action_report, format_startup_check_report
from gui.settings_window import SettingsWindow
from gui.log_viewer import LogViewerWindow
from tools.developer_tools import DeveloperCommandResult, DeveloperTools
from tools.workflows import WorkflowEngine, WorkflowRunResult, format_workflow_result
from voice.audio_diagnostics import AudioDiagnostics, format_microphone_test_summary
from voice.fast_voice import (
    FastVoiceProgress,
    FastVoiceReport,
    FastVoiceRunner,
    resolve_fast_voice_tts_mode,
)
from voice.voice_command_test import (
    COMMAND_PROMPT,
    LISTENING_FOR_COMMAND_PROMPT,
    NO_COMMAND_DETECTED_MESSAGE,
    VoiceCommandTestRunner,
    format_voice_command_report,
)
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
    STOP_COMMAND_DETECTED_MESSAGE,
    VOICE_LOOP_STARTED_MESSAGE,
    VOICE_LOOP_STOPPED_MESSAGE,
    WAKE_DIAGNOSTICS_PREFIX,
    VoiceLoopRunner,
)
from vision.vision_service import format_vision_check_report


class AssistantStatus(str, Enum):
    SLEEPING = "Sleeping"
    LISTENING = "Listening"
    TRANSCRIBING = "Transcribing"
    THINKING = "Thinking"
    SPEAKING = "Speaking"
    RESPONDING = "Responding"
    FOLLOW_UP = "Follow-up"
    WAKE_DETECTED = "Wake detected"
    ERROR = "Error"


def _fast_voice_tts_status(settings: AppSettings, *, failed: bool = False) -> str:
    mode = resolve_fast_voice_tts_mode(settings)
    if mode == "off":
        return "TTS OFF: text-only mode"
    if mode == "short_ack_only":
        label = "TTS ACK: short acknowledgements only"
    else:
        label = "TTS FINAL: full responses enabled"
    return f"{label} (speech failed)" if failed else label


STATUS_COLORS = {
    AssistantStatus.SLEEPING: "#4a2525",
    AssistantStatus.LISTENING: "#d14f4f",
    AssistantStatus.TRANSCRIBING: "#b83b48",
    AssistantStatus.THINKING: "#8a2633",
    AssistantStatus.SPEAKING: "#b73a3a",
    AssistantStatus.RESPONDING: "#c94343",
    AssistantStatus.FOLLOW_UP: "#9d3030",
    AssistantStatus.WAKE_DETECTED: "#ef4444",
    AssistantStatus.ERROR: "#ff5a5a",
}


class HUDButton(QPushButton):
    def __init__(self, text: str, variant: str = "secondary") -> None:
        super().__init__(text)
        self.variant = variant
        self._hovered = False
        self._pressed = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(46)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFlat(True)

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._pressed = False
        self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        cut = 8.0
        path.moveTo(rect.left() + cut, rect.top())
        path.lineTo(rect.right() - cut, rect.top())
        path.lineTo(rect.right(), rect.top() + cut)
        path.lineTo(rect.right(), rect.bottom() - cut)
        path.lineTo(rect.right() - cut, rect.bottom())
        path.lineTo(rect.left() + cut, rect.bottom())
        path.lineTo(rect.left(), rect.bottom() - cut)
        path.lineTo(rect.left(), rect.top() + cut)
        path.closeSubpath()

        variants = {
            "primary": ("#1a0707", "#4f1010", "#ff4545"),
            "danger": ("#220808", "#6b1515", "#ff5656"),
            "ghost": ("#120505", "#431010", "#ff3232"),
            "secondary": ("#140606", "#541313", "#ff3e3e"),
        }
        start, end, border = variants.get(self.variant, variants["secondary"])
        if self._pressed:
            start = "#2a0a0a"
            end = "#6a1616"
        elif self._hovered:
            start = "#1f0909"
            end = "#621313"

        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0.0, QColor(start))
        gradient.setColorAt(0.55, QColor(end))
        gradient.setColorAt(1.0, QColor("#080101"))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawPath(path)

        glow_alpha = 120 if self._hovered or self._pressed else 55
        glow_pen = QPen(QColor(255, 74, 74, glow_alpha), 3.0)
        painter.setPen(glow_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        border_pen = QPen(QColor(border), 1.4)
        painter.setPen(border_pen)
        painter.drawPath(path)

        accent_rect = QRectF(rect.left() + 10, rect.top() + 9, 22, rect.height() - 18)
        accent_gradient = QLinearGradient(accent_rect.topLeft(), accent_rect.bottomRight())
        accent_gradient.setColorAt(0.0, QColor("#ff4a4a"))
        accent_gradient.setColorAt(1.0, QColor("#8f1d1d"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(accent_gradient)
        painter.drawRoundedRect(accent_rect, 4, 4)
        painter.setBrush(QColor(255, 235, 235, 210))
        painter.drawEllipse(QRectF(accent_rect.center().x() - 2.5, accent_rect.center().y() - 2.5, 5, 5))

        painter.setPen(QColor("#f5eeee"))
        font = QFont(self.font())
        font.setWeight(QFont.Weight.DemiBold)
        font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 102)
        painter.setFont(font)
        fm = QFontMetrics(font)
        text = self.text().upper()
        available = rect.adjusted(42, 0, -14, 0)
        painter.drawText(
            available.adjusted(2, 0, 0, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            fm.elidedText(text, Qt.TextElideMode.ElideRight, available.width()),
        )


class OrbWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._status = AssistantStatus.SLEEPING
        self._pulse = 0
        self._sweep = 0
        self._density = 1.0
        self.setFixedSize(450, 450)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

    def set_status(self, status: AssistantStatus) -> None:
        self._status = status
        self._density = {
            AssistantStatus.SLEEPING: 0.65,
            AssistantStatus.LISTENING: 1.15,
            AssistantStatus.TRANSCRIBING: 1.0,
            AssistantStatus.THINKING: 0.95,
            AssistantStatus.SPEAKING: 1.2,
            AssistantStatus.RESPONDING: 1.2,
            AssistantStatus.FOLLOW_UP: 1.05,
            AssistantStatus.WAKE_DETECTED: 1.3,
            AssistantStatus.ERROR: 0.8,
        }[status]
        self.update()

    def _tick(self) -> None:
        self._pulse = (self._pulse + 1) % 120
        self._sweep = (self._sweep + int(3 * self._density)) % 360
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        color = QColor(STATUS_COLORS[self._status])
        rect = self.rect().adjusted(10, 10, -10, -10)
        center = rect.center()
        pulse_size = 8 + abs(60 - self._pulse) / 7
        intensity = {
            AssistantStatus.SLEEPING: 42,
            AssistantStatus.LISTENING: 172,
            AssistantStatus.TRANSCRIBING: 166,
            AssistantStatus.THINKING: 160,
            AssistantStatus.SPEAKING: 188,
            AssistantStatus.RESPONDING: 188,
            AssistantStatus.FOLLOW_UP: 165,
            AssistantStatus.WAKE_DETECTED: 220,
            AssistantStatus.ERROR: 235,
        }[self._status]

        outer_glow = QRadialGradient(center, 188)
        outer_glow.setColorAt(0.0, QColor(color.red(), color.green(), color.blue(), intensity))
        outer_glow.setColorAt(0.33, QColor(color.red(), color.green(), color.blue(), 70))
        outer_glow.setColorAt(0.68, QColor(color.red(), color.green(), color.blue(), 24))
        outer_glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(outer_glow)
        painter.drawEllipse(rect.adjusted(-pulse_size, -pulse_size, pulse_size, pulse_size))

        backdrop = QRadialGradient(center, 170)
        backdrop.setColorAt(0.0, QColor("#230707"))
        backdrop.setColorAt(0.48, QColor("#100202"))
        backdrop.setColorAt(1.0, QColor("#020000"))
        painter.setBrush(backdrop)
        painter.setPen(QPen(QColor("#5a1010"), 1))
        painter.drawEllipse(rect.adjusted(42, 42, -42, -42))

        for radius, alpha in ((164, 90), (148, 72), (132, 54)):
            painter.setPen(QPen(QColor(255, 74, 74, alpha), 1.1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(center, radius, radius)

        sweep_pen = QPen(QColor("#ff4a4a"), 4)
        sweep_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(sweep_pen)
        span = 64 + (self._pulse % 36) * 3
        painter.drawArc(rect.adjusted(30, 30, -30, -30), (self._sweep - 26) * 16, span * 16)
        painter.drawArc(rect.adjusted(30, 30, -30, -30), (self._sweep + 150) * 16, (span // 2) * 16)

        tick_pen = QPen(QColor("#ff2a2a"), 1.2)
        tick_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(tick_pen)
        import math

        for angle in range(0, 360, 10):
            outer = 182
            inner = 164 if angle % 30 else 154
            a = math.radians(angle - 90)
            x1 = center.x() + math.cos(a) * outer
            y1 = center.y() + math.sin(a) * outer
            x2 = center.x() + math.cos(a) * inner
            y2 = center.y() + math.sin(a) * inner
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))

        cross_pen = QPen(QColor(255, 74, 74, 120), 1.0)
        cross_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(cross_pen)
        painter.drawLine(center.x() - 182, center.y(), center.x() + 182, center.y())
        painter.drawLine(center.x(), center.y() - 182, center.x(), center.y() + 182)

        inner_glow = QRadialGradient(center, 100)
        inner_glow.setColorAt(0.0, QColor("#fff6f6"))
        inner_glow.setColorAt(0.24, QColor("#ffd0d0"))
        inner_glow.setColorAt(0.55, QColor(color.red(), color.green(), color.blue(), 170))
        inner_glow.setColorAt(1.0, QColor("#100000"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(inner_glow)
        painter.drawEllipse(rect.adjusted(86, 86, -86, -86))

        core_ring = QPen(QColor("#8f1d1d"), 3.0)
        painter.setPen(core_ring)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(rect.adjusted(118, 118, -118, -118))

        core = QRadialGradient(center, 62)
        core.setColorAt(0.0, QColor("#fff8f8"))
        core.setColorAt(0.30, QColor("#f3c5c5"))
        core.setColorAt(0.70, QColor(color.red(), color.green(), color.blue(), 220))
        core.setColorAt(1.0, QColor("#170202"))
        painter.setBrush(core)
        painter.setPen(QPen(QColor("#ffdada"), 1))
        painter.drawEllipse(rect.adjusted(140, 140, -140, -140))

        arc_pen = QPen(QColor("#ff6969"), 1.5)
        arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arc_pen)
        painter.drawArc(rect.adjusted(146, 146, -146, -146), (self._sweep + 18) * 16, 20 * 16)
        painter.drawArc(rect.adjusted(104, 104, -104, -104), (self._sweep - 86) * 16, 28 * 16)

        text_font = QFont("Segoe UI Variable", 18)
        text_font.setWeight(QFont.Weight.Bold)
        text_font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 114)
        painter.setFont(text_font)
        painter.setPen(QColor("#fff2f2"))
        painter.drawText(rect.adjusted(0, 20, 0, -10), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, "JARVIS")

        state_font = QFont("Segoe UI Variable", 10)
        state_font.setWeight(QFont.Weight.DemiBold)
        state_font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 112)
        painter.setFont(state_font)
        painter.setPen(QColor("#ff4a4a"))
        state_text = "ONLINE" if self._status != AssistantStatus.SLEEPING else "SLEEPING"
        painter.drawText(rect.adjusted(0, 54, 0, -22), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, state_text)

        wave_heights = [4, 7, 12, 8, 5, 10, 14, 9, 5]
        if self._status in {
            AssistantStatus.TRANSCRIBING,
            AssistantStatus.THINKING,
            AssistantStatus.SPEAKING,
            AssistantStatus.RESPONDING,
        }:
            wave_heights = [6, 12, 18, 24, 18, 12, 8, 14, 7]
        elif self._status == AssistantStatus.SLEEPING:
            wave_heights = [3, 4, 6, 4, 3, 5, 6, 4, 3]
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ff4a4a"))
        wave_y = center.y() + 42
        wave_x = center.x() - 42
        for index, height in enumerate(wave_heights):
            painter.drawRoundedRect(QRectF(wave_x + index * 10, wave_y - height / 2, 5, height), 2, 2)


class JarvisMainWindow(QMainWindow):
    def __init__(self, settings: AppSettings, assistant: AssistantCore) -> None:
        super().__init__()
        self.settings = settings
        self.assistant = assistant
        self._drag_position: QPoint | None = None
        self._allow_close = False
        self._tray_notice_shown = False

        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if self.settings.always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFont(QFont("Segoe UI Variable", 10))
        self.setMinimumSize(980, 840)
        self.resize(max(self.settings.window_width, 1040), max(self.settings.window_height, 880))

        self.orb = OrbWidget()
        self.status = AssistantStatus.SLEEPING
        self.status_label = QLabel(self.status.value)
        self.mode_label = QLabel("Mode")
        self.mode_value = QLabel("Idle")
        self.header_mode_value = QLabel("Idle")
        self.header_provider_value = QLabel(self.settings.speech_to_text_provider.upper())
        self.header_wake_value = QLabel(self.settings.wake_provider.upper())
        self.header_health_value = QLabel("READY")
        self.current_mode = "Idle"
        self.tabs = QTabWidget()
        self.transcript = QTextEdit()
        self.command_input = QLineEdit()
        self.mic_test_button = QPushButton("Mic Test")
        self.voice_command_button = QPushButton("Voice Test")
        self.start_voice_loop_button = QPushButton("Start Voice")
        self.stop_voice_loop_button = QPushButton("Stop / Interrupt")
        self.check_reminders_button = QPushButton("Check Reminders")
        self.notification_test_button = QPushButton("Test Notification")
        self.health_check_button = QPushButton("Run Health Check")
        self.settings_button = QPushButton("Settings")
        self.log_viewer_button = QPushButton("Log Viewer")
        self.backup_create_button = QPushButton("Create Backup")
        self.backup_list_button = QPushButton("List Backups")
        self.startup_check_button = QPushButton("Startup Check")
        self.startup_enable_button = QPushButton("Enable Startup")
        self.startup_disable_button = QPushButton("Disable Startup")
        self.launch_notepad_button = QPushButton("Launch Notepad")
        self.open_google_button = QPushButton("Open Google")
        self.list_downloads_button = QPushButton("List Downloads")
        self.list_screens_button = QPushButton("List Screens")
        self.look_screen_1_button = QPushButton("Look Screen 1")
        self.look_screen_2_button = QPushButton("Look Screen 2")
        self.read_screen_button = QPushButton("Read Screen")
        self.test_confirmation_button = QPushButton("Test Confirmation")
        self.start_reminder_watch_button = QPushButton("Start Watch")
        self.stop_reminder_watch_button = QPushButton("Stop Watch")
        self.developer_git_status_button = QPushButton("Git Status")
        self.developer_last_commit_button = QPushButton("Last Commit")
        self.developer_fast_tests_button = QPushButton("Run Fast Tests")
        self.developer_open_main_button = QPushButton("Open Main")
        self.developer_open_settings_button = QPushButton("Open Settings")
        self.developer_open_tests_button = QPushButton("Open Tests")
        self.developer_open_vscode_button = QPushButton("Open VS Code")
        self.workflow_start_coding_button = QPushButton("Start Coding Session")
        self.workflow_review_today_button = QPushButton("Review Today's Work")
        self.send_button = QPushButton("Send")
        self.audio_diagnostics = AudioDiagnostics(settings)
        self.voice_loop_status_value = QLabel("Idle")
        self.voice_loop_last_command_value = QLabel("None")
        self.voice_loop_last_response_value = QLabel("None")
        self.voice_state_value = QLabel("Sleeping")
        self.voice_detail_value = QLabel("Waiting for wake phrase")
        self.voice_provider_value = QLabel(self.settings.speech_to_text_provider)
        self.voice_stt_model_value = QLabel(self.settings.whisper_model)
        self.voice_stt_device_value = QLabel(f"{self.settings.whisper_device} / {self.settings.whisper_compute_type}")
        self.voice_wake_provider_value = QLabel(self.settings.wake_provider)
        self.voice_tts_provider_value = QLabel(self.settings.tts_provider)
        self.voice_response_mode_value = QLabel(self.settings.voice_response_mode)
        self.voice_wake_ack_value = QLabel("On" if self.settings.voice_loop_speak_wake_ack else "Off")
        if self.settings.gui_voice_engine == "fast":
            tts_status = _fast_voice_tts_status(self.settings)
        else:
            tts_status = "On" if self.settings.voice_loop_speak_responses else "Off"
        self.voice_response_speech_value = QLabel(tts_status)
        self.voice_wake_score_value = QLabel("--")
        self.voice_rms_value = QLabel("--")
        self.voice_vad_value = QLabel("--")
        self.voice_raw_speech_value = QLabel("--")
        self.voice_cleaned_value = QLabel("--")
        self.voice_interpreted_value = QLabel("--")
        self.voice_wake_only_value = QLabel("--")
        self.voice_repair_confidence_value = QLabel("--")
        self.voice_repair_strategy_value = QLabel("--")
        self.vision_capture_value = QLabel("--")
        self.vision_path_value = QLabel("--")
        self.vision_ocr_value = QLabel("--")
        self.vision_provider_status_value = QLabel("--")
        self.vision_summary_value = QLabel("--")
        self.voice_wake_score_bar = QProgressBar()
        self.voice_transcript_confidence_bar = QProgressBar()
        self.voice_command_score_bar = QProgressBar()
        self.voice_repair_confidence_bar = QProgressBar()
        self.voice_timing_wake_capture_value = QLabel("--")
        self.voice_timing_wake_transcribe_value = QLabel("--")
        self.voice_timing_command_capture_value = QLabel("--")
        self.voice_timing_command_transcribe_value = QLabel("--")
        self.voice_timing_openai_value = QLabel("--")
        self.voice_timing_tts_value = QLabel("--")
        self.voice_timing_total_value = QLabel("--")
        self.voice_timing_slow_value = QLabel("--")
        self.voice_response_panel = QTextEdit()
        self.voice_command_score_value = QLabel("--")
        self.agent_enabled_value = QLabel("Enabled" if settings.agent_enabled else "Disabled")
        self.developer_mode_value = QLabel(self._developer_mode_text())
        self.developer_status_value = QLabel("Not checked")
        self.developer_commit_value = QLabel("Not checked")
        self.developer_tests_value = QLabel("Not run")
        self.workflow_status_value = QLabel("Idle")
        self.workflow_steps_value = QLabel("No workflow run yet")
        self.command_examples_value = QLabel(
            "Voice: start listening\n"
            "Vision: list screens | what is on screen 1\n"
            "Developer: show git status | run fast tests\n"
            "Workflows: start coding session | review today's work"
        )
        self.reminders_check_value = QLabel("Idle")
        self.notification_result_value = QLabel("Idle")
        self.health_result_value = QLabel("Idle")
        self.settings_window: SettingsWindow | None = None
        self.log_viewer_window: LogViewerWindow | None = None
        self.startup_result_value = QLabel("Idle")
        self.backup_result_value = QLabel("Idle")
        self.app_launch_result_value = QLabel("Idle")
        self.website_result_value = QLabel("Idle")
        self.file_access_result_value = QLabel("Idle")
        self.confirmation_result_value = QLabel("Idle")
        self.reminder_watch_status_value = QLabel("Idle")
        self.voice_loop_runner: VoiceLoopRunner | None = None
        self.fast_voice_runner: FastVoiceRunner | None = None
        self.voice_loop_thread: threading.Thread | None = None
        self.voice_loop_events: Queue[Any] = Queue()
        self.voice_loop_event_timer = QTimer(self)
        self.voice_loop_event_timer.timeout.connect(self._drain_voice_loop_events)
        self.reminder_watch_runner: ReminderWatcher | None = None
        self.reminder_watch_thread: threading.Thread | None = None
        self.reminder_watch_events: Queue[str] = Queue()
        self.reminder_watch_event_timer = QTimer(self)
        self.reminder_watch_event_timer.timeout.connect(self._drain_reminder_watch_events)
        self.start_voice_loop_action: QAction | None = None
        self.stop_voice_loop_action: QAction | None = None
        self.start_reminder_watch_action: QAction | None = None
        self.stop_reminder_watch_action: QAction | None = None
        self.notification_test_action: QAction | None = None
        self.health_check_action: QAction | None = None
        self.settings_action: QAction | None = None
        self.log_viewer_action: QAction | None = None
        self.backup_create_action: QAction | None = None
        self.backup_list_action: QAction | None = None
        self.launch_notepad_action: QAction | None = None
        self.open_google_action: QAction | None = None
        self.list_downloads_action: QAction | None = None
        self.test_confirmation_action: QAction | None = None
        self.tray_icon = self._create_tray_icon()

        self._build_ui()
        self._connect_signals()
        self.set_status(AssistantStatus.SLEEPING)

    def _build_ui(self) -> None:
        shell = QFrame()
        shell.setObjectName("shell")
        shell.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setColor(QColor(0, 0, 0, 170))
        shadow.setOffset(0, 12)
        shell.setGraphicsEffect(shadow)

        title = QLabel("JARVIS")
        title.setObjectName("title")
        subtitle = QLabel("Desktop assistant foundation")
        subtitle.setObjectName("subtitle")
        self.status_label.setObjectName("statusPill")
        self.mode_label.setObjectName("modeLabel")
        self.mode_value.setObjectName("modeValue")
        self.header_mode_value.setObjectName("headerBadge")
        self.header_provider_value.setObjectName("headerBadge")
        self.header_wake_value.setObjectName("headerBadge")
        self.header_health_value.setObjectName("headerBadge")
        self.voice_loop_status_value.setObjectName("voiceLoopValue")
        self.voice_loop_last_command_value.setObjectName("voiceLoopValue")
        self.voice_loop_last_response_value.setObjectName("voiceLoopValue")
        self.voice_state_value.setObjectName("stateValue")
        self.voice_detail_value.setObjectName("stateDetail")
        self.voice_provider_value.setObjectName("voiceLoopValue")
        self.voice_stt_model_value.setObjectName("voiceLoopValue")
        self.voice_stt_device_value.setObjectName("voiceLoopValue")
        self.voice_wake_provider_value.setObjectName("voiceLoopValue")
        self.voice_tts_provider_value.setObjectName("voiceLoopValue")
        self.voice_response_mode_value.setObjectName("voiceLoopValue")
        self.voice_wake_ack_value.setObjectName("voiceLoopValue")
        self.voice_response_speech_value.setObjectName("voiceLoopValue")
        self.voice_wake_score_value.setObjectName("voiceLoopValue")
        self.voice_rms_value.setObjectName("voiceLoopValue")
        self.voice_vad_value.setObjectName("voiceLoopValue")
        self.voice_raw_speech_value.setObjectName("voiceLoopValue")
        self.voice_cleaned_value.setObjectName("voiceLoopValue")
        self.voice_interpreted_value.setObjectName("voiceLoopValue")
        self.voice_wake_only_value.setObjectName("voiceLoopValue")
        self.voice_repair_confidence_value.setObjectName("voiceLoopValue")
        self.voice_repair_strategy_value.setObjectName("voiceLoopValue")
        self.voice_command_score_value.setObjectName("voiceLoopValue")
        self.voice_timing_wake_capture_value.setObjectName("voiceLoopValue")
        self.voice_timing_wake_transcribe_value.setObjectName("voiceLoopValue")
        self.voice_timing_command_capture_value.setObjectName("voiceLoopValue")
        self.voice_timing_command_transcribe_value.setObjectName("voiceLoopValue")
        self.voice_timing_openai_value.setObjectName("voiceLoopValue")
        self.voice_timing_tts_value.setObjectName("voiceLoopValue")
        self.voice_timing_total_value.setObjectName("voiceLoopValue")
        self.voice_timing_slow_value.setObjectName("voiceLoopValue")
        self.agent_enabled_value.setObjectName("voiceLoopValue")
        self.command_examples_value.setObjectName("smallHudBody")
        self.command_examples_value.setWordWrap(True)
        self.command_examples_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        for developer_value in (
            self.developer_mode_value,
            self.developer_status_value,
            self.developer_commit_value,
            self.developer_tests_value,
        ):
            developer_value.setObjectName("voiceLoopValue")
            developer_value.setWordWrap(True)
            developer_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        for workflow_value in (
            self.workflow_status_value,
            self.workflow_steps_value,
        ):
            workflow_value.setObjectName("voiceLoopValue")
            workflow_value.setWordWrap(True)
            workflow_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.reminders_check_value.setObjectName("voiceLoopValue")
        self.notification_result_value.setObjectName("voiceLoopValue")
        self.health_result_value.setObjectName("voiceLoopValue")
        self.startup_result_value.setObjectName("voiceLoopValue")
        self.app_launch_result_value.setObjectName("voiceLoopValue")
        self.website_result_value.setObjectName("voiceLoopValue")
        self.file_access_result_value.setObjectName("voiceLoopValue")
        self.confirmation_result_value.setObjectName("voiceLoopValue")
        self.reminder_watch_status_value.setObjectName("voiceLoopValue")
        for bar in (
            self.voice_wake_score_bar,
            self.voice_transcript_confidence_bar,
            self.voice_command_score_bar,
            self.voice_repair_confidence_bar,
        ):
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setTextVisible(True)
            bar.setFormat("%v%")
            bar.setObjectName("confidenceBar")

        minimize_button = QPushButton("-")
        minimize_button.setObjectName("windowButton")
        minimize_button.clicked.connect(self.hide)
        close_button = QPushButton("x")
        close_button.setObjectName("windowButton")
        close_button.clicked.connect(self.close)

        top_bar = QFrame()
        top_bar.setObjectName("topBar")
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(18, 12, 18, 12)
        top_bar_layout.setSpacing(14)

        brand_block = QVBoxLayout()
        brand_block.setSpacing(0)
        title.setText("J A R V I S")
        subtitle.setText("DESKTOP ASSISTANT")
        brand_block.addWidget(title)
        brand_block.addWidget(subtitle)
        top_bar_layout.addLayout(brand_block, stretch=2)

        def make_metric_card(label_text: str, value_widget: QLabel, pulse_text: str) -> QFrame:
            card = QFrame()
            card.setObjectName("topMetricCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 10, 14, 10)
            card_layout.setSpacing(4)
            label = QLabel(label_text.upper())
            label.setObjectName("metricLabel")
            value_widget.setObjectName("metricValue")
            pulse = QLabel(pulse_text)
            pulse.setObjectName("metricPulse")
            card_layout.addWidget(label)
            card_layout.addWidget(value_widget)
            card_layout.addWidget(pulse)
            return card

        self.header_mode_value.setText("OPTIMAL")
        self.header_provider_value.setText("14%")
        self.header_wake_value.setText("37%")
        self.header_health_value.setText("ACTIVE")
        top_bar_layout.addWidget(make_metric_card("System Status", self.header_mode_value, "▁▂▃▄▅▆▇"))
        top_bar_layout.addWidget(make_metric_card("CPU", self.header_provider_value, "▁▂▁▃▆▅▂"))
        top_bar_layout.addWidget(make_metric_card("Memory", self.header_wake_value, "▁▃▆▅▃▁▂"))
        top_bar_layout.addWidget(make_metric_card("Voice Engine", self.header_health_value, "▁▂▃▅▇▅▃"))

        top_buttons = QHBoxLayout()
        minimize_button = HUDButton("-", "ghost")
        minimize_button.setObjectName("windowButton")
        minimize_button.clicked.connect(self.hide)
        close_button = HUDButton("x", "danger")
        close_button.setObjectName("windowButton")
        close_button.clicked.connect(self.close)
        top_buttons.addWidget(minimize_button)
        top_buttons.addWidget(close_button)
        top_bar_layout.addLayout(top_buttons)

        self.transcript.setReadOnly(True)
        self.transcript.setObjectName("transcript")
        self.transcript.setText("Waiting for you to speak...")
        self.voice_response_panel.setReadOnly(True)
        self.voice_response_panel.setObjectName("responsePanel")
        self.voice_response_panel.setText("Jarvis responses will appear here.")

        self.command_input.setPlaceholderText("Type a command...")
        self.command_input.setObjectName("commandInput")

        self.mic_test_button = HUDButton("Mic Test")
        self.voice_command_button = HUDButton("Voice Test")
        self.chat_test_button = HUDButton("Chat Test")
        start_voice_text = (
            "Start Listening" if self.settings.gui_voice_engine == "fast" else "Start Voice"
        )
        self.start_voice_loop_button = HUDButton(start_voice_text, "primary")
        self.stop_voice_loop_button = HUDButton("Stop / Interrupt", "danger")
        self.stop_voice_loop_button.setEnabled(False)
        self.check_reminders_button = HUDButton("Check Reminders")
        self.notification_test_button = HUDButton("Test Notification")
        self.health_check_button = HUDButton("Run Health Check")
        self.settings_button = HUDButton("Settings")
        self.log_viewer_button = HUDButton("Log Viewer")
        self.backup_create_button = HUDButton("Create Backup")
        self.backup_list_button = HUDButton("List Backups")
        self.startup_check_button = HUDButton("Startup Check")
        self.startup_enable_button = HUDButton("Enable Startup")
        self.startup_disable_button = HUDButton("Disable Startup")
        self.weather_check_button = HUDButton("Weather Check")
        self.vision_check_button = HUDButton("Vision Check")
        self.launch_notepad_button = HUDButton("Launch Notepad")
        self.open_google_button = HUDButton("Open Google")
        self.list_downloads_button = HUDButton("List Downloads")
        self.list_screens_button = HUDButton("List Screens")
        self.look_screen_1_button = HUDButton("Look Screen 1")
        self.look_screen_2_button = HUDButton("Look Screen 2")
        self.read_screen_button = HUDButton("Read Screen")
        self.test_confirmation_button = HUDButton("Test Confirmation")
        self.start_reminder_watch_button = HUDButton("Start Watch")
        self.stop_reminder_watch_button = HUDButton("Stop Watch")
        self.stop_reminder_watch_button.setEnabled(False)
        self.send_button = HUDButton("Send", "primary")
        self.agent_test_button = HUDButton("Agent Test")
        self.developer_git_status_button = HUDButton("Git Status")
        self.developer_last_commit_button = HUDButton("Last Commit")
        self.developer_fast_tests_button = HUDButton("Run Fast Tests")
        self.developer_open_main_button = HUDButton("Open Main")
        self.developer_open_settings_button = HUDButton("Open Settings")
        self.developer_open_tests_button = HUDButton("Open Tests")
        self.developer_open_vscode_button = HUDButton("Open VS Code")
        self.workflow_start_coding_button = HUDButton("Start Coding Session")
        self.workflow_review_today_button = HUDButton("Review Today's Work")
        for developer_button in (
            self.developer_git_status_button,
            self.developer_last_commit_button,
            self.developer_fast_tests_button,
            self.developer_open_main_button,
            self.developer_open_settings_button,
            self.developer_open_tests_button,
            self.developer_open_vscode_button,
        ):
            developer_button.setMinimumHeight(34)
        for workflow_button in (
            self.workflow_start_coding_button,
            self.workflow_review_today_button,
        ):
            workflow_button.setMinimumHeight(34)

        left_panel = QFrame()
        left_panel.setObjectName("sidePanel")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(16, 14, 16, 14)
        left_layout.setSpacing(12)

        voice_status_card = QFrame()
        voice_status_card.setObjectName("stackCard")
        voice_status_layout = QVBoxLayout(voice_status_card)
        voice_status_layout.setContentsMargins(14, 12, 14, 12)
        voice_status_layout.setSpacing(8)
        voice_title_row = QHBoxLayout()
        voice_title = QLabel("VOICE STATUS")
        voice_title.setObjectName("panelTitle")
        voice_dot = QLabel("●")
        voice_dot.setObjectName("statusDot")
        voice_title_row.addWidget(voice_title)
        voice_title_row.addStretch(1)
        voice_title_row.addWidget(voice_dot)
        voice_status_layout.addLayout(voice_title_row)
        state_row = QHBoxLayout()
        state_label = QLabel("CURRENT STATE")
        state_label.setObjectName("smallHudLabel")
        self.voice_state_value.setText("Sleeping")
        self.voice_state_value.setObjectName("stateValue")
        state_row.addWidget(state_label)
        state_row.addStretch(1)
        voice_status_layout.addLayout(state_row)
        voice_status_layout.addWidget(self.voice_state_value)
        self.voice_detail_value.setText("Waiting for wake phrase")
        voice_status_layout.addWidget(self.voice_detail_value)
        mode_row = QHBoxLayout()
        mode_row.addWidget(self.mode_label)
        mode_row.addWidget(self.mode_value)
        mode_row.addStretch(1)
        voice_status_layout.addLayout(mode_row)
        voice_status_layout.addWidget(self.status_label)
        voice_wave = QLabel("▁▂▃▄▅▆▇▆▅▄▃▂")
        voice_wave.setObjectName("voiceWave")
        voice_status_layout.addWidget(voice_wave)
        voice_status_layout.addSpacing(4)
        wake_row = QHBoxLayout()
        wake_row.addWidget(QLabel("WAKE PHRASE"))
        wake_row.addWidget(QLabel(self.settings.wake_phrase))
        voice_status_layout.addLayout(wake_row)
        provider_row = QHBoxLayout()
        provider_row.addWidget(QLabel("WAKE PROVIDER"))
        provider_row.addWidget(QLabel(self.settings.wake_provider.upper()))
        voice_status_layout.addLayout(provider_row)
        sensitivity_percent = int(round(float(getattr(self.settings, "wake_match_threshold", 0.72)) * 100))
        sensitivity_row = QHBoxLayout()
        sensitivity_label = QLabel("LISTENING SENSITIVITY")
        sensitivity_value = QLabel(f"{sensitivity_percent}%")
        sensitivity_row.addWidget(sensitivity_label)
        sensitivity_row.addStretch(1)
        sensitivity_row.addWidget(sensitivity_value)
        voice_status_layout.addLayout(sensitivity_row)
        sensitivity_bar = QProgressBar()
        sensitivity_bar.setRange(0, 100)
        sensitivity_bar.setValue(sensitivity_percent)
        sensitivity_bar.setTextVisible(False)
        sensitivity_bar.setObjectName("sensorBar")
        voice_status_layout.addWidget(sensitivity_bar)

        voice_control_card = QFrame()
        voice_control_card.setObjectName("stackCard")
        control_layout = QVBoxLayout(voice_control_card)
        control_layout.setContentsMargins(14, 12, 14, 12)
        control_layout.setSpacing(8)
        control_title = QLabel("VOICE CONTROLS")
        control_title.setObjectName("panelTitle")
        control_layout.addWidget(control_title)
        control_layout.addWidget(self.start_voice_loop_button)
        control_layout.addWidget(self.stop_voice_loop_button)
        control_layout.addWidget(self.settings_button)
        command_examples_card = QFrame()
        command_examples_card.setObjectName("stackCard")
        command_examples_layout = QVBoxLayout(command_examples_card)
        command_examples_layout.setContentsMargins(14, 12, 14, 12)
        command_examples_layout.setSpacing(8)
        command_examples_title = QLabel("COMMAND EXAMPLES")
        command_examples_title.setObjectName("panelTitle")
        command_examples_layout.addWidget(command_examples_title)
        command_examples_layout.addWidget(self.command_examples_value)
        left_layout.addWidget(voice_status_card)
        left_layout.addWidget(voice_control_card)
        left_layout.addWidget(command_examples_card)
        left_layout.addStretch(1)

        center_panel = QFrame()
        center_panel.setObjectName("centerPanel")
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(16, 14, 16, 14)
        center_layout.setSpacing(12)
        orb_shell = QFrame()
        orb_shell.setObjectName("orbShell")
        orb_layout = QVBoxLayout(orb_shell)
        orb_layout.setContentsMargins(12, 12, 12, 12)
        orb_layout.setSpacing(0)
        orb_layout.addWidget(self.orb, alignment=Qt.AlignmentFlag.AlignCenter)
        center_layout.addWidget(orb_shell, stretch=5)

        timing_panel = QFrame()
        timing_panel.setObjectName("stackCard")
        timing_grid = QGridLayout(timing_panel)
        timing_grid.setContentsMargins(14, 12, 14, 12)
        timing_grid.setHorizontalSpacing(10)
        timing_grid.setVerticalSpacing(6)
        timing_title = QLabel("TIMING METRICS")
        timing_title.setObjectName("panelTitle")
        timing_grid.addWidget(timing_title, 0, 0, 1, 4)
        timing_metrics = [
            (
                "VAD WAIT" if self.settings.gui_voice_engine == "fast" else "WAKE CAPTURE",
                self.voice_timing_wake_capture_value,
            ),
            (
                "AUDIO PREP" if self.settings.gui_voice_engine == "fast" else "WAKE TRANSCRIBE",
                self.voice_timing_wake_transcribe_value,
            ),
            ("COMMAND CAPTURE", self.voice_timing_command_capture_value),
            ("COMMAND TRANSCRIBE", self.voice_timing_command_transcribe_value),
            ("OPENAI", self.voice_timing_openai_value),
            ("TTS", self.voice_timing_tts_value),
            ("TOTAL TIME", self.voice_timing_total_value),
            ("SLOW STAGES", self.voice_timing_slow_value),
        ]
        for index, (label_text, value_widget) in enumerate(timing_metrics):
            row = 1 + index // 4
            col = (index % 4) * 1
            cell = QFrame()
            cell.setObjectName("timingCell")
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(10, 8, 10, 8)
            cell_layout.setSpacing(2)
            label = QLabel(label_text)
            label.setObjectName("smallHudLabel")
            value_widget.setObjectName("voiceLoopValue")
            cell_layout.addWidget(label)
            cell_layout.addWidget(value_widget)
            timing_grid.addWidget(cell, row, col)
        center_layout.addWidget(timing_panel, stretch=1)

        right_panel = QFrame()
        right_panel.setObjectName("sidePanel")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(16, 14, 16, 14)
        right_layout.setSpacing(12)

        transcript_card = QFrame()
        transcript_card.setObjectName("stackCard")
        transcript_layout = QVBoxLayout(transcript_card)
        transcript_layout.setContentsMargins(14, 12, 14, 12)
        transcript_layout.setSpacing(8)
        transcript_title_row = QHBoxLayout()
        transcript_title = QLabel("LIVE TRANSCRIPT")
        transcript_title.setObjectName("panelTitle")
        transcript_dot = QLabel("●")
        transcript_dot.setObjectName("statusDot")
        transcript_title_row.addWidget(transcript_title)
        transcript_title_row.addStretch(1)
        transcript_title_row.addWidget(transcript_dot)
        transcript_layout.addLayout(transcript_title_row)
        self.transcript.setReadOnly(True)
        self.transcript.setObjectName("transcript")
        self.transcript.setText("Waiting for you to speak...")
        transcript_layout.addWidget(self.transcript)
        right_layout.addWidget(transcript_card, stretch=3)

        response_card = QFrame()
        response_card.setObjectName("stackCard")
        response_layout = QVBoxLayout(response_card)
        response_layout.setContentsMargins(14, 12, 14, 12)
        response_layout.setSpacing(8)
        response_title = QLabel("JARVIS RESPONSE")
        response_title.setObjectName("panelTitle")
        response_layout.addWidget(response_title)
        self.voice_response_panel.setReadOnly(True)
        self.voice_response_panel.setObjectName("responsePanel")
        self.voice_response_panel.setText("Jarvis responses will appear here.")
        response_layout.addWidget(self.voice_response_panel)
        right_layout.addWidget(response_card, stretch=2)

        vision_card = QFrame()
        vision_card.setObjectName("stackCard")
        vision_layout = QGridLayout(vision_card)
        vision_layout.setContentsMargins(14, 12, 14, 12)
        vision_layout.setHorizontalSpacing(10)
        vision_layout.setVerticalSpacing(6)
        vision_title = QLabel("SCREEN VISION")
        vision_title.setObjectName("panelTitle")
        vision_layout.addWidget(vision_title, 0, 0, 1, 2)
        vision_rows = [
            ("CAPTURE", self.vision_capture_value),
            ("PATH", self.vision_path_value),
            ("OCR", self.vision_ocr_value),
            ("PROVIDER", self.vision_provider_status_value),
            ("SUMMARY", self.vision_summary_value),
        ]
        for row_index, (label_text, value_widget) in enumerate(vision_rows, start=1):
            label = QLabel(label_text)
            label.setObjectName("smallHudLabel")
            value_widget.setObjectName("voiceLoopValue")
            vision_layout.addWidget(label, row_index, 0)
            vision_layout.addWidget(value_widget, row_index, 1)
        right_layout.addWidget(vision_card)

        developer_card = QFrame()
        developer_card.setObjectName("stackCard")
        developer_layout = QVBoxLayout(developer_card)
        developer_layout.setContentsMargins(14, 12, 14, 12)
        developer_layout.setSpacing(8)
        developer_title = QLabel("DEVELOPER")
        developer_title.setObjectName("panelTitle")
        developer_layout.addWidget(developer_title)
        developer_grid = QGridLayout()
        developer_grid.setHorizontalSpacing(10)
        developer_grid.setVerticalSpacing(5)
        developer_rows = [
            ("MODE", self.developer_mode_value),
            ("GIT", self.developer_status_value),
            ("COMMIT", self.developer_commit_value),
            ("TESTS", self.developer_tests_value),
        ]
        for row_index, (label_text, value_widget) in enumerate(developer_rows):
            label = QLabel(label_text)
            label.setObjectName("smallHudLabel")
            value_widget.setObjectName("voiceLoopValue")
            developer_grid.addWidget(label, row_index, 0)
            developer_grid.addWidget(value_widget, row_index, 1)
        developer_layout.addLayout(developer_grid)
        right_layout.addWidget(developer_card)

        workflow_card = QFrame()
        workflow_card.setObjectName("stackCard")
        workflow_layout = QVBoxLayout(workflow_card)
        workflow_layout.setContentsMargins(14, 12, 14, 12)
        workflow_layout.setSpacing(8)
        workflow_title = QLabel("WORKFLOWS")
        workflow_title.setObjectName("panelTitle")
        workflow_layout.addWidget(workflow_title)
        workflow_grid = QGridLayout()
        workflow_grid.setHorizontalSpacing(10)
        workflow_grid.setVerticalSpacing(5)
        workflow_rows = [
            ("STATUS", self.workflow_status_value),
            ("STEPS", self.workflow_steps_value),
        ]
        for row_index, (label_text, value_widget) in enumerate(workflow_rows):
            label = QLabel(label_text)
            label.setObjectName("smallHudLabel")
            value_widget.setObjectName("voiceLoopValue")
            workflow_grid.addWidget(label, row_index, 0)
            workflow_grid.addWidget(value_widget, row_index, 1)
        workflow_layout.addLayout(workflow_grid)
        right_layout.addWidget(workflow_card)

        command_bar = QFrame()
        command_bar.setObjectName("commandBar")
        command_bar_layout = QHBoxLayout(command_bar)
        command_bar_layout.setContentsMargins(14, 12, 14, 12)
        command_bar_layout.setSpacing(10)
        self.command_input.setObjectName("commandInput")
        command_bar_layout.addWidget(self.command_input, stretch=4)
        command_bar_layout.addWidget(self.send_button)

        footer = QFrame()
        footer.setObjectName("footerBar")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(14, 8, 14, 8)
        footer_layout.setSpacing(10)
        footer_version = QLabel(f"JARVIS v{self.settings.app_version}")
        footer_version.setObjectName("footerLabel")
        footer_status = QLabel("ALL SYSTEMS OPERATIONAL")
        footer_status.setObjectName("footerStatus")
        footer_layout.addWidget(footer_version)
        footer_layout.addStretch(1)
        footer_layout.addWidget(footer_status)

        content_row = QHBoxLayout()
        content_row.setSpacing(14)
        content_row.addWidget(left_panel, stretch=2)
        content_row.addWidget(center_panel, stretch=4)
        content_row.addWidget(right_panel, stretch=2)

        layout = QVBoxLayout(shell)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)
        layout.addWidget(top_bar)
        layout.addLayout(content_row)
        layout.addWidget(command_bar)
        layout.addWidget(footer)

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(14, 14, 14, 14)
        root_layout.addWidget(shell)
        self.setCentralWidget(root)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("mainTabs")
        self.tabs.setVisible(False)

        self.tabs.addTab(QWidget(), "Voice")
        self.tabs.addTab(QWidget(), "Tools")
        self.tabs.addTab(QWidget(), "Reminders")
        self.tabs.addTab(QWidget(), "Memory")
        self.tabs.addTab(QWidget(), "Diagnostics")
        self.tabs.hide()

        self.setStyleSheet(
            """
            #shell {
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #030000,
                    stop: 0.45 #080101,
                    stop: 1 #120404);
                border: 1px solid #5a1010;
                border-radius: 16px;
            }
            #topBar, #sidePanel, #centerPanel, #stackCard, #orbShell, #commandBar, #footerBar {
                background: rgba(8, 3, 3, 224);
                border: 1px solid #5a1010;
                border-radius: 8px;
            }
            #title {
                color: #f5eeee;
                font-size: 28px;
                font-weight: 800;
                letter-spacing: 0px;
            }
            #subtitle {
                color: #aa8888;
                font-size: 11px;
                font-weight: 600;
            }
            #metricLabel, #smallHudLabel, #panelTitle, #footerLabel, #footerStatus {
                letter-spacing: 0px;
            }
            #metricLabel {
                color: #aa8888;
                font-size: 10px;
                font-weight: 700;
            }
            #metricValue {
                color: #f5eeee;
                font-size: 16px;
                font-weight: 800;
            }
            #metricPulse {
                color: #ff4a4a;
                font-size: 10px;
            }
            #statusDot {
                color: #ff4a4a;
                font-size: 11px;
                font-weight: 700;
            }
            #panelTitle {
                color: #ff4a4a;
                font-size: 12px;
                font-weight: 800;
            }
            #smallHudLabel {
                color: #aa8888;
                font-size: 10px;
                font-weight: 700;
            }
            #voiceWave {
                color: #ff4a4a;
                font-size: 10px;
            }
            #stateValue {
                color: #f5eeee;
                font-size: 30px;
                font-weight: 800;
            }
            #stateDetail {
                color: #c5a2a2;
                font-size: 13px;
                font-weight: 600;
            }
            #modeLabel {
                color: #aa8888;
                font-size: 10px;
                font-weight: 700;
            }
            #modeValue {
                color: #f5eeee;
                background: rgba(18, 4, 4, 160);
                border: 1px solid #5a1010;
                border-radius: 8px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 700;
            }
            #voiceLoopValue {
                color: #f5eeee;
                font-weight: 600;
            }
            #cleanCommandValue {
                color: #f5eeee;
                font-size: 14px;
                font-weight: 700;
            }
            #smallHudBody {
                color: #aa8888;
                font-size: 10px;
                font-weight: 600;
            }
            #confidenceBar, #sensorBar {
                background: #120404;
                border: 1px solid #5a1010;
                text-align: center;
                color: #f5eeee;
            }
            #confidenceBar {
                border-radius: 6px;
                height: 14px;
            }
            #confidenceBar::chunk {
                border-radius: 5px;
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #7f1d1d,
                    stop: 1 #ff2a2a);
            }
            #sensorBar {
                border-radius: 5px;
                height: 10px;
            }
            #sensorBar::chunk {
                border-radius: 4px;
                background: #ff4a4a;
            }
            #transcript, #responsePanel, #commandInput {
                color: #f5eeee;
                background: #080303;
                border: 1px solid #5a1010;
                border-radius: 8px;
                padding: 10px 12px;
                font-size: 13px;
            }
            #transcript, #responsePanel {
                min-height: 160px;
            }
            #commandInput:focus {
                border: 1px solid #ff4a4a;
                background: #120404;
            }
            #footerLabel {
                color: #aa8888;
                font-size: 10px;
                font-weight: 700;
            }
            #footerStatus {
                color: #f5eeee;
                font-size: 10px;
                font-weight: 700;
            }
            #statusPill {
                color: #f5eeee;
                background: rgba(92, 18, 18, 100);
                border: 1px solid #8f1d1d;
                border-radius: 12px;
                padding: 6px 10px;
                font-size: 12px;
                font-weight: 700;
            }
            #mainTabs::pane {
                border: 1px solid #5a1010;
                background: #030000;
            }
            #mainTabs QTabBar::tab {
                color: #aa8888;
                background: #080303;
                border: 1px solid #5a1010;
                padding: 6px 10px;
                margin-right: 3px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }
            #mainTabs QTabBar::tab:selected {
                color: #f5eeee;
                background: rgba(143, 29, 29, 70);
                border-color: #ff2a2a;
            }
            #windowButton {
                color: #f5eeee;
                background: transparent;
                border: 0;
                min-width: 34px;
                min-height: 34px;
            }
            """
        )

    def _connect_signals(self) -> None:
        self.command_input.returnPressed.connect(self.handle_command)
        self.send_button.clicked.connect(self.handle_command)
        self.mic_test_button.clicked.connect(self.run_microphone_test)
        self.voice_command_button.clicked.connect(self.run_voice_command_test)
        self.chat_test_button.clicked.connect(self.run_chat_test)
        self.start_voice_loop_button.clicked.connect(self.start_voice_loop)
        self.stop_voice_loop_button.clicked.connect(self.stop_voice_loop)
        self.check_reminders_button.clicked.connect(self.check_reminders)
        self.notification_test_button.clicked.connect(self.test_notification)
        self.health_check_button.clicked.connect(self.run_health_check)
        self.settings_button.clicked.connect(self.open_settings)
        self.log_viewer_button.clicked.connect(self.open_log_viewer)
        self.backup_create_button.clicked.connect(self.create_backup)
        self.backup_list_button.clicked.connect(self.list_backups)
        self.startup_check_button.clicked.connect(self.startup_check)
        self.startup_enable_button.clicked.connect(self.startup_enable)
        self.startup_disable_button.clicked.connect(self.startup_disable)
        self.launch_notepad_button.clicked.connect(self.launch_notepad)
        self.weather_check_button.clicked.connect(self.weather_check)
        self.open_google_button.clicked.connect(self.open_google)
        self.list_downloads_button.clicked.connect(self.list_downloads)
        self.list_screens_button.clicked.connect(self.list_screens)
        self.look_screen_1_button.clicked.connect(self.look_screen_1)
        self.look_screen_2_button.clicked.connect(self.look_screen_2)
        self.read_screen_button.clicked.connect(self.read_screen)
        self.vision_check_button.clicked.connect(self.vision_check)
        self.test_confirmation_button.clicked.connect(self.test_confirmation)
        self.agent_test_button.clicked.connect(self.agent_test)
        self.start_reminder_watch_button.clicked.connect(self.start_reminder_watch)
        self.stop_reminder_watch_button.clicked.connect(self.stop_reminder_watch)
        self.developer_git_status_button.clicked.connect(self.developer_git_status)
        self.developer_last_commit_button.clicked.connect(self.developer_last_commit)
        self.developer_fast_tests_button.clicked.connect(self.developer_run_fast_tests)
        self.developer_open_main_button.clicked.connect(self.developer_open_main)
        self.developer_open_settings_button.clicked.connect(self.developer_open_settings)
        self.developer_open_tests_button.clicked.connect(self.developer_open_tests)
        self.developer_open_vscode_button.clicked.connect(self.developer_open_vscode)
        self.workflow_start_coding_button.clicked.connect(self.workflow_start_coding_session)
        self.workflow_review_today_button.clicked.connect(self.workflow_review_todays_work)

    def developer_git_status(self) -> None:
        self._run_developer_panel_action(
            "Git status",
            "status",
            lambda tools: tools.check_git_status(),
        )

    def developer_last_commit(self) -> None:
        self._run_developer_panel_action(
            "Last commit",
            "commit",
            lambda tools: tools.show_last_commit(),
        )

    def developer_run_fast_tests(self) -> None:
        self._run_developer_panel_action(
            "Fast tests",
            "tests",
            lambda tools: tools.run_fast_tests(),
        )

    def developer_open_main(self) -> None:
        self._run_developer_panel_action(
            "Open main.py",
            "action",
            lambda tools: tools.open_main_py(),
        )

    def developer_open_settings(self) -> None:
        self._run_developer_panel_action(
            "Open settings",
            "action",
            lambda tools: tools.open_settings(),
        )

    def developer_open_tests(self) -> None:
        self._run_developer_panel_action(
            "Open tests folder",
            "action",
            lambda tools: tools.open_tests_folder(),
        )

    def developer_open_vscode(self) -> None:
        self._run_developer_panel_action(
            "Open VS Code",
            "action",
            lambda tools: tools.open_jarvis_in_vscode(),
        )

    def workflow_start_coding_session(self) -> None:
        self._run_workflow_panel_action("start coding session")

    def workflow_review_todays_work(self) -> None:
        self._run_workflow_panel_action("review today's work")

    def _run_workflow_panel_action(self, command: str) -> None:
        self._set_mode("Workflow")
        self.workflow_status_value.setText("Running")
        self.workflow_steps_value.setText("Running workflow...")
        self._append_message("Jarvis", f"Workflow requested: {command}")
        self.set_status(AssistantStatus.THINKING)
        QApplication.processEvents()

        engine = self._workflow_engine_service()
        if engine is None:
            message = (
                "Developer mode is disabled."
                if not self.settings.developer_mode_enabled
                else "Workflow engine is unavailable."
            )
            self.workflow_status_value.setText("Failed")
            self.workflow_steps_value.setText(message)
            self.voice_response_panel.setText(message)
            self._append_message("Jarvis", message)
            self.set_status(AssistantStatus.ERROR)
            self._set_mode("Error")
            return

        try:
            result = engine.handle_command(command)
        except Exception as exc:  # pragma: no cover - defensive GUI boundary
            message = f"Workflow failed: {type(exc).__name__}: {exc}"
            self.workflow_status_value.setText("Failed")
            self.workflow_steps_value.setText(message)
            self.voice_response_panel.setText(message)
            self._append_message("Jarvis", message)
            self.set_status(AssistantStatus.ERROR)
            self._set_mode("Error")
            return

        if result is None:
            message = "Workflow command is not available."
            self.workflow_status_value.setText("Failed")
            self.workflow_steps_value.setText(message)
            self.voice_response_panel.setText(message)
            self._append_message("Jarvis", message)
            self.set_status(AssistantStatus.ERROR)
            self._set_mode("Error")
            return

        text = format_workflow_result(result)
        self.workflow_status_value.setText("Completed" if result.succeeded else "Failed")
        self.workflow_steps_value.setText(self._workflow_step_summary(result))
        self.voice_response_panel.setText(self._compact_developer_text(text, max_lines=8, max_chars=520))
        self._append_message("Jarvis", text)
        self.set_status(AssistantStatus.SLEEPING if result.succeeded else AssistantStatus.ERROR)
        QTimer.singleShot(1200, lambda: self.set_status(AssistantStatus.SLEEPING))
        QTimer.singleShot(1200, lambda: self._set_mode("Idle"))

    def _run_developer_panel_action(
        self,
        action_name: str,
        target: str,
        handler: Callable[[DeveloperTools], DeveloperCommandResult],
    ) -> None:
        self._set_mode("Developer")
        self._sync_developer_mode_label()
        self._append_message("Jarvis", f"{action_name} requested...")
        self.set_status(AssistantStatus.THINKING)
        if target == "tests":
            self.developer_tests_value.setText("Running")
        QApplication.processEvents()

        tools = self._developer_tools_service()
        if tools is None:
            message = (
                "Developer mode is disabled."
                if not self.settings.developer_mode_enabled
                else "Developer tools are unavailable."
            )
            self._append_message("Jarvis", message)
            self._set_developer_panel_value(target, message)
            self.voice_response_panel.setText(message)
            self.set_status(
                AssistantStatus.SLEEPING
                if not self.settings.developer_mode_enabled
                else AssistantStatus.ERROR
            )
            QTimer.singleShot(1200, lambda: self._set_mode("Idle"))
            return

        try:
            result = handler(tools)
        except Exception as exc:  # pragma: no cover - defensive GUI boundary
            message = f"Developer action failed: {type(exc).__name__}: {exc}"
            self._append_message("Jarvis", message)
            self._set_developer_panel_value(target, message)
            self.voice_response_panel.setText(message)
            self.set_status(AssistantStatus.ERROR)
            self._set_mode("Error")
            return

        text = self._developer_result_text(result)
        self._append_message("Jarvis", text)
        self._set_developer_panel_value(target, text)
        self.voice_response_panel.setText(self._compact_developer_text(text, max_lines=6, max_chars=420))
        if result.succeeded or text == "Developer mode is disabled.":
            self.set_status(AssistantStatus.SLEEPING)
        else:
            self.set_status(AssistantStatus.ERROR)
        QTimer.singleShot(1200, lambda: self.set_status(AssistantStatus.SLEEPING))
        QTimer.singleShot(1200, lambda: self._set_mode("Idle"))

    def _developer_tools_service(self) -> DeveloperTools | None:
        tools = getattr(self.assistant, "developer_tools", None)
        if tools is None and self.settings.developer_mode_enabled and isinstance(self.assistant, AssistantCore):
            tools = DeveloperTools(self.settings)
            self.assistant.developer_tools = tools
        return tools

    def _workflow_engine_service(self) -> WorkflowEngine | None:
        engine = getattr(self.assistant, "workflow_engine", None)
        if engine is not None:
            return engine
        if not isinstance(self.assistant, AssistantCore) or not self.settings.developer_mode_enabled:
            return None
        tools = self._developer_tools_service()
        if tools is None:
            return None
        engine = WorkflowEngine(tools)
        self.assistant.workflow_engine = engine
        return engine

    def _sync_developer_tools_from_settings(self) -> None:
        if not isinstance(self.assistant, AssistantCore):
            return
        if self.settings.developer_mode_enabled:
            if self.assistant.developer_tools is None:
                self.assistant.developer_tools = DeveloperTools(self.settings)
            if self.assistant.workflow_engine is None:
                self.assistant.workflow_engine = WorkflowEngine(self.assistant.developer_tools)
        else:
            self.assistant.developer_tools = None
            self.assistant.workflow_engine = None

    def _sync_developer_mode_label(self) -> None:
        self.developer_mode_value.setText(self._developer_mode_text())

    def _developer_mode_text(self) -> str:
        return "Enabled" if self.settings.developer_mode_enabled else "Disabled"

    def _set_developer_panel_value(self, target: str, text: str) -> None:
        compact = self._compact_developer_text(text)
        if target == "status":
            self.developer_status_value.setText(compact)
        elif target == "commit":
            self.developer_commit_value.setText(compact)
        elif target == "tests":
            self.developer_tests_value.setText(compact)

    @staticmethod
    def _developer_result_text(result: DeveloperCommandResult) -> str:
        if result.safe_error:
            return result.safe_error
        if result.text:
            return result.text
        return "Developer command completed."

    @staticmethod
    def _workflow_step_summary(result: WorkflowRunResult, max_chars: int = 260) -> str:
        lines = []
        for step in result.steps:
            status = "OK" if step.succeeded else "FAILED"
            compact = " ".join(line.strip() for line in step.result.text.splitlines() if line.strip())
            if len(compact) > 90:
                compact = compact[:87].rstrip() + "..."
            lines.append(f"{step.name}: {status} - {compact or 'No output.'}")
        summary = "\n".join(lines) or "No steps reported."
        if len(summary) > max_chars:
            summary = summary[: max_chars - 3].rstrip() + "..."
        return summary

    @staticmethod
    def _compact_developer_text(text: str, max_lines: int = 3, max_chars: int = 180) -> str:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return "--"
        extra_lines = max(0, len(lines) - max_lines)
        compact = "\n".join(lines[:max_lines])
        if extra_lines:
            compact = f"{compact}\n... +{extra_lines} more"
        if len(compact) > max_chars:
            compact = compact[: max_chars - 3].rstrip() + "..."
        return compact

    def _create_tray_icon(self) -> QSystemTrayIcon:
        tray = QSystemTrayIcon(self._make_icon(), self)
        tray.setToolTip(self.settings.app_name)

        menu = QMenu()
        show_action = QAction("Show Jarvis", self)
        show_action.triggered.connect(self.show_from_tray)
        mic_test_action = QAction("Microphone Test", self)
        mic_test_action.triggered.connect(self.run_microphone_test)
        voice_command_action = QAction("Voice Command Test", self)
        voice_command_action.triggered.connect(self.run_voice_command_test)
        start_voice_action_text = (
            "Start Listening" if self.settings.gui_voice_engine == "fast" else "Start Voice Loop"
        )
        self.start_voice_loop_action = QAction(start_voice_action_text, self)
        self.start_voice_loop_action.triggered.connect(self.start_voice_loop)
        self.stop_voice_loop_action = QAction("Stop Voice Loop", self)
        self.stop_voice_loop_action.triggered.connect(self.stop_voice_loop)
        check_reminders_action = QAction("Check Reminders", self)
        check_reminders_action.triggered.connect(self.check_reminders)
        self.notification_test_action = QAction("Test Notification", self)
        self.notification_test_action.triggered.connect(self.test_notification)
        self.health_check_action = QAction("Run Health Check", self)
        self.health_check_action.triggered.connect(self.run_health_check)
        self.settings_action = QAction("Settings", self)
        self.settings_action.triggered.connect(self.open_settings)
        self.log_viewer_action = QAction("Log Viewer", self)
        self.log_viewer_action.triggered.connect(self.open_log_viewer)
        self.backup_create_action = QAction("Create Backup", self)
        self.backup_create_action.triggered.connect(self.create_backup)
        self.backup_list_action = QAction("List Backups", self)
        self.backup_list_action.triggered.connect(self.list_backups)
        self.launch_notepad_action = QAction("Launch Notepad", self)
        self.launch_notepad_action.triggered.connect(self.launch_notepad)
        self.open_google_action = QAction("Open Google", self)
        self.open_google_action.triggered.connect(self.open_google)
        self.list_downloads_action = QAction("List Downloads", self)
        self.list_downloads_action.triggered.connect(self.list_downloads)
        self.test_confirmation_action = QAction("Test Confirmation", self)
        self.test_confirmation_action.triggered.connect(self.test_confirmation)
        self.start_reminder_watch_action = QAction("Start Reminder Watch", self)
        self.start_reminder_watch_action.triggered.connect(self.start_reminder_watch)
        self.stop_reminder_watch_action = QAction("Stop Reminder Watch", self)
        self.stop_reminder_watch_action.triggered.connect(self.stop_reminder_watch)
        exit_action = QAction("Exit Jarvis", self)
        exit_action.triggered.connect(self.request_quit)
        menu.addAction(show_action)
        menu.addAction(mic_test_action)
        menu.addAction(voice_command_action)
        menu.addAction(self.start_voice_loop_action)
        menu.addAction(self.stop_voice_loop_action)
        menu.addAction(check_reminders_action)
        menu.addAction(self.notification_test_action)
        menu.addAction(self.health_check_action)
        menu.addAction(self.settings_action)
        menu.addAction(self.log_viewer_action)
        menu.addAction(self.backup_create_action)
        menu.addAction(self.backup_list_action)
        menu.addAction(self.launch_notepad_action)
        menu.addAction(self.open_google_action)
        menu.addAction(self.list_downloads_action)
        menu.addAction(self.test_confirmation_action)
        menu.addAction(self.start_reminder_watch_action)
        menu.addAction(self.stop_reminder_watch_action)
        menu.addSeparator()
        menu.addAction(exit_action)
        tray.setContextMenu(menu)
        tray.activated.connect(self._handle_tray_activation)
        tray.show()
        return tray

    def _make_icon(self) -> QIcon:
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QRadialGradient(32, 32, 30)
        gradient.setColorAt(0.0, QColor("#e0f7ff"))
        gradient.setColorAt(0.45, QColor("#22d3ee"))
        gradient.setColorAt(1.0, QColor("#0f172a"))
        painter.setBrush(gradient)
        painter.setPen(QColor("#7dd3fc"))
        painter.drawEllipse(8, 8, 48, 48)
        painter.end()
        return QIcon(pixmap)

    def _handle_tray_activation(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in {QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick}:
            self.show_from_tray()

    def show_from_tray(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def handle_command(self) -> None:
        command = self.command_input.text().strip()
        if not command:
            return

        self._set_mode("Chat")
        self.command_input.clear()
        self._append_message("You", command)
        self.set_status(AssistantStatus.THINKING)

        try:
            response = self.assistant.handle_command(command)
            self._append_message("Jarvis", response.text)
            self._update_vision_panel(command, response.text)
            self.voice_response_panel.setText(self._compact_vision_response_text(response.text) if self._is_vision_command(command) else response.text)
            self.set_status(AssistantStatus.SPEAKING if response.accepted else AssistantStatus.ERROR)
        except Exception as exc:  # pragma: no cover - defensive GUI boundary
            self._append_message("Jarvis", f"Phase 1 error: {exc}")
            self.set_status(AssistantStatus.ERROR)
            self._set_mode("Error")
            return

        QTimer.singleShot(1200, lambda: self.set_status(AssistantStatus.SLEEPING))
        QTimer.singleShot(1200, lambda: self._set_mode("Idle"))

    def run_microphone_test(self) -> None:
        self._set_mode("Diagnostics")
        self._append_message("Jarvis", "Running a short local microphone test...")
        self.set_status(AssistantStatus.LISTENING)
        QApplication.processEvents()

        report = self.audio_diagnostics.run_full_check()
        self._append_message("Jarvis", format_microphone_test_summary(report))
        if report.microphone_test and report.microphone_test.stream_opened:
            self.set_status(AssistantStatus.SPEAKING)
        else:
            self.set_status(AssistantStatus.ERROR)
            self._set_mode("Error")

        QTimer.singleShot(1600, lambda: self.set_status(AssistantStatus.SLEEPING))
        QTimer.singleShot(1600, lambda: self._set_mode("Idle"))

    def run_voice_command_test(self) -> None:
        self._set_mode("Voice Test")
        self._append_message("Jarvis", "Starting controlled voice command test...")
        QApplication.processEvents()

        runner = VoiceCommandTestRunner(
            settings=self.settings,
            assistant=self.assistant,
            status_callback=self._handle_voice_command_status,
        )
        report = runner.run()
        self._append_message("Jarvis", format_voice_command_report(report))
        self.set_status(AssistantStatus.SPEAKING if report.wake_detected and report.assistant_response else AssistantStatus.SLEEPING)
        QTimer.singleShot(1800, lambda: self.set_status(AssistantStatus.SLEEPING))
        QTimer.singleShot(1800, lambda: self._set_mode("Idle"))

    def run_chat_test(self) -> None:
        command = self.command_input.text().strip() or "Say hello"
        self._set_mode("Chat Test")
        self._append_message("Jarvis", f"Running chat test: {command}")
        self.set_status(AssistantStatus.THINKING)
        QApplication.processEvents()

        try:
            response = self.assistant.handle_command(command)
            self._append_message("Jarvis", response.text)
            self.set_status(AssistantStatus.SPEAKING if response.accepted else AssistantStatus.ERROR)
        except Exception as exc:  # pragma: no cover - defensive GUI boundary
            self._append_message("Jarvis", f"Chat test failed: {exc}")
            self.set_status(AssistantStatus.ERROR)
            return

        QTimer.singleShot(1200, lambda: self.set_status(AssistantStatus.SLEEPING))
        QTimer.singleShot(1200, lambda: self._set_mode("Idle"))

    def check_reminders(self) -> None:
        self._set_mode("Reminders")
        self._append_message("Jarvis", "Checking reminders...")
        self.set_status(AssistantStatus.THINKING)
        QApplication.processEvents()

        try:
            response = self.assistant.handle_command("check reminders")
            self._append_message("Jarvis", response.text)
            self.reminders_check_value.setText(self._reminders_summary(response.text))
            self.set_status(AssistantStatus.SLEEPING if response.accepted else AssistantStatus.ERROR)
        except Exception as exc:  # pragma: no cover - defensive GUI boundary
            self._append_message("Jarvis", f"Reminder check failed: {exc}")
            self.reminders_check_value.setText("Error")
            self.set_status(AssistantStatus.ERROR)
            self._set_mode("Error")
            return

        QTimer.singleShot(1200, lambda: self.set_status(AssistantStatus.SLEEPING))
        QTimer.singleShot(1200, lambda: self._set_mode("Idle"))

    def test_notification(self) -> None:
        self._set_mode("Diagnostics")
        self._append_message("Jarvis", "Testing notification...")
        self.notification_result_value.setText("Checking")
        self.set_status(AssistantStatus.THINKING)
        QApplication.processEvents()

        try:
            self.assistant.permission_broker.check(
                "show notification",
                description="Show test notification from the GUI.",
            )
            result = NotificationService(self.settings).send_notification("Jarvis", "Hello from Jarvis")
            self._append_message("Jarvis", format_notification_check_report(result))
            self.notification_result_value.setText("Delivered" if result.delivered else "Unavailable")
            self.set_status(AssistantStatus.SPEAKING if result.delivered else AssistantStatus.ERROR)
        except Exception as exc:  # pragma: no cover - defensive GUI boundary
            self._append_message("Jarvis", f"Notification test failed: {exc}")
            self.notification_result_value.setText("Error")
            self.set_status(AssistantStatus.ERROR)
            self._set_mode("Error")
            return

        QTimer.singleShot(1200, lambda: self.set_status(AssistantStatus.SLEEPING))
        QTimer.singleShot(1200, lambda: self._set_mode("Idle"))

    def run_health_check(self) -> None:
        self._set_mode("Diagnostics")
        self._append_message("Jarvis", "Running health check...")
        self.health_result_value.setText("Checking")
        self.set_status(AssistantStatus.THINKING)
        QApplication.processEvents()

        try:
            report = HealthService(self.settings).run_check()
            self._append_message("Jarvis", format_health_check_report(report))
            self.health_result_value.setText("Completed")
            self.set_status(AssistantStatus.SLEEPING)
        except Exception as exc:  # pragma: no cover - defensive GUI boundary
            self._append_message("Jarvis", f"Health check failed: {exc}")
            self.health_result_value.setText("Error")
            self.set_status(AssistantStatus.ERROR)
            self._set_mode("Error")
            return

        QTimer.singleShot(1200, lambda: self.set_status(AssistantStatus.SLEEPING))
        QTimer.singleShot(1200, lambda: self._set_mode("Idle"))

    def startup_check(self) -> None:
        self._set_mode("Diagnostics")
        self._append_message("Jarvis", "Checking Windows startup registration...")
        self.startup_result_value.setText("Checking")
        self.set_status(AssistantStatus.THINKING)
        QApplication.processEvents()

        try:
            report = StartupService(self.settings).run_check()
            self._append_message("Jarvis", format_startup_check_report(report))
            self.startup_result_value.setText("Registered" if report.registered else "Not registered")
            self.set_status(AssistantStatus.SLEEPING if report.is_successful else AssistantStatus.ERROR)
        except Exception as exc:  # pragma: no cover - defensive GUI boundary
            self._append_message("Jarvis", f"Startup check failed: {exc}")
            self.startup_result_value.setText("Error")
            self.set_status(AssistantStatus.ERROR)
            self._set_mode("Error")
            return

        QTimer.singleShot(1200, lambda: self.set_status(AssistantStatus.SLEEPING))
        QTimer.singleShot(1200, lambda: self._set_mode("Idle"))

    def startup_enable(self) -> None:
        self._run_startup_action("enable")

    def startup_disable(self) -> None:
        self._run_startup_action("disable")

    def open_settings(self) -> None:
        self._set_mode("Settings")
        self._append_message("Jarvis", "Opening settings...")
        self.settings_window = SettingsWindow(self.settings, parent=self)
        result = self.settings_window.exec()
        self.settings_window = None

        if result == QDialog.DialogCode.Accepted:
            self._append_message("Jarvis", "Settings saved.")
            self.agent_enabled_value.setText("Enabled" if self.settings.agent_enabled else "Disabled")
            self._sync_developer_tools_from_settings()
            self._sync_developer_mode_label()
        else:
            self._append_message("Jarvis", "Settings closed without changes.")
        self._set_mode("Idle")

    def open_log_viewer(self) -> None:
        self._set_mode("Diagnostics")
        self._append_message("Jarvis", "Opening log viewer...")
        self.log_viewer_window = LogViewerWindow(self.settings, parent=self)
        self.log_viewer_window.exec()
        self.log_viewer_window = None
        self._set_mode("Idle")

    def create_backup(self) -> None:
        self._set_mode("Diagnostics")
        self._append_message("Jarvis", "Creating backup...")
        self.backup_result_value.setText("Checking")
        self.set_status(AssistantStatus.THINKING)
        QApplication.processEvents()

        try:
            result = create_backup(self.settings, self._gui_confirmation_handler())
            self._append_message("Jarvis", format_backup_create_report(result))
            self.backup_result_value.setText("Created" if result.created else "Failed")
            self.set_status(AssistantStatus.SLEEPING if result.is_successful else AssistantStatus.ERROR)
        except Exception as exc:  # pragma: no cover - defensive GUI boundary
            self._append_message("Jarvis", f"Backup create failed: {exc}")
            self.backup_result_value.setText("Error")
            self.set_status(AssistantStatus.ERROR)
            self._set_mode("Error")
            return

        QTimer.singleShot(1200, lambda: self.set_status(AssistantStatus.SLEEPING))
        QTimer.singleShot(1200, lambda: self._set_mode("Idle"))

    def list_backups(self) -> None:
        self._set_mode("Diagnostics")
        self._append_message("Jarvis", "Listing backups...")
        self.backup_result_value.setText("Checking")
        self.set_status(AssistantStatus.THINKING)
        QApplication.processEvents()

        try:
            report = list_backups(self.settings)
            self._append_message("Jarvis", format_backup_list_report(report))
            self.backup_result_value.setText(f"{len(report.items)} backups")
            self.set_status(AssistantStatus.SLEEPING)
        except Exception as exc:  # pragma: no cover - defensive GUI boundary
            self._append_message("Jarvis", f"Backup list failed: {exc}")
            self.backup_result_value.setText("Error")
            self.set_status(AssistantStatus.ERROR)
            self._set_mode("Error")
            return

        QTimer.singleShot(1200, lambda: self._set_mode("Idle"))

    def _run_startup_action(self, action: str) -> None:
        self._set_mode("Diagnostics")
        self._append_message("Jarvis", f"{action.title()} Windows startup requested...")
        self.startup_result_value.setText("Checking")
        self.set_status(AssistantStatus.THINKING)
        QApplication.processEvents()

        def _confirm(action_name: str, risk_level: str, description: str):
            return confirm_action_gui(action_name, risk_level, description, parent=self, settings=self.settings)

        try:
            service = StartupService(self.settings)
            if action == "enable":
                result = service.enable_startup(_confirm)
            else:
                result = service.disable_startup(_confirm)
            self._append_message("Jarvis", format_startup_action_report(result))
            self.startup_result_value.setText("Enabled" if result.check.registered else "Disabled")
            self.set_status(AssistantStatus.SLEEPING if result.success else AssistantStatus.ERROR)
        except Exception as exc:  # pragma: no cover - defensive GUI boundary
            self._append_message("Jarvis", f"Startup {action} failed: {exc}")
            self.startup_result_value.setText("Error")
            self.set_status(AssistantStatus.ERROR)
            self._set_mode("Error")
            return

        QTimer.singleShot(1200, lambda: self.set_status(AssistantStatus.SLEEPING))
        QTimer.singleShot(1200, lambda: self._set_mode("Idle"))

    def _gui_confirmation_handler(self):
        def _handler(action_name: str, risk_level: str, description: str):
            return confirm_action_gui(action_name, risk_level, description, parent=self, settings=self.settings)

        return _handler

    def weather_check(self) -> None:
        self._set_mode("Weather")
        self._append_message("Jarvis", "Checking weather...")
        self.set_status(AssistantStatus.THINKING)
        QApplication.processEvents()

        try:
            response = self.assistant.handle_command("what is the weather")
            self._append_message("Jarvis", response.text)
            self.set_status(AssistantStatus.SLEEPING if response.accepted else AssistantStatus.ERROR)
        except Exception as exc:  # pragma: no cover - defensive GUI boundary
            self._append_message("Jarvis", f"Weather check failed: {exc}")
            self.set_status(AssistantStatus.ERROR)
            self._set_mode("Error")
            return

        QTimer.singleShot(1200, lambda: self.set_status(AssistantStatus.SLEEPING))
        QTimer.singleShot(1200, lambda: self._set_mode("Idle"))

    def vision_check(self) -> None:
        self._set_mode("Diagnostics")
        self._append_message("Jarvis", "Checking vision diagnostics...")
        self.set_status(AssistantStatus.THINKING)
        QApplication.processEvents()

        try:
            report = self.assistant.vision_service.run_check()
            self._append_message("Jarvis", format_vision_check_report(report))
            self.set_status(AssistantStatus.SLEEPING if report.is_successful else AssistantStatus.ERROR)
        except Exception as exc:  # pragma: no cover - defensive GUI boundary
            self._append_message("Jarvis", f"Vision check failed: {exc}")
            self.set_status(AssistantStatus.ERROR)
            self._set_mode("Error")
            return

        QTimer.singleShot(1200, lambda: self.set_status(AssistantStatus.SLEEPING))
        QTimer.singleShot(1200, lambda: self._set_mode("Idle"))

    def list_screens(self) -> None:
        self._run_screen_vision_command("list screens")

    def look_screen_1(self) -> None:
        self._run_screen_vision_command("what is on screen 1")

    def look_screen_2(self) -> None:
        self._run_screen_vision_command("what is on screen 2")

    def read_screen(self) -> None:
        self._run_screen_vision_command("read my screen")

    def _run_screen_vision_command(self, command: str) -> None:
        self._set_mode("Vision")
        self._append_message("Jarvis", f"Running vision command: {command}")
        self.set_status(AssistantStatus.THINKING)
        QApplication.processEvents()

        try:
            response = self.assistant.handle_command(command)
            self._append_message("Jarvis", response.text)
            self._update_vision_panel(command, response.text)
            self.voice_response_panel.setText(self._compact_vision_response_text(response.text))
            self.set_status(AssistantStatus.SLEEPING if response.accepted else AssistantStatus.ERROR)
        except Exception as exc:  # pragma: no cover - defensive GUI boundary
            self._append_message("Jarvis", f"Vision command failed: {exc}")
            self.set_status(AssistantStatus.ERROR)
            self._set_mode("Error")
            return

        QTimer.singleShot(1200, lambda: self.set_status(AssistantStatus.SLEEPING))
        QTimer.singleShot(1200, lambda: self._set_mode("Idle"))

    def agent_test(self) -> None:
        self._set_mode("Diagnostics")
        self._append_message("Jarvis", "Running agent test...")
        self.agent_enabled_value.setText("Enabled" if self.settings.agent_enabled else "Disabled")
        self.set_status(AssistantStatus.THINKING)
        QApplication.processEvents()

        try:
            response = self.assistant.handle_command("what is the weather")
            self._append_message("Jarvis", response.text)
            self.set_status(AssistantStatus.SLEEPING if response.accepted else AssistantStatus.ERROR)
        except Exception as exc:  # pragma: no cover - defensive GUI boundary
            self._append_message("Jarvis", f"Agent test failed: {exc}")
            self.set_status(AssistantStatus.ERROR)
            self._set_mode("Error")
            return

        QTimer.singleShot(1200, lambda: self.set_status(AssistantStatus.SLEEPING))
        QTimer.singleShot(1200, lambda: self._set_mode("Idle"))

    def launch_notepad(self) -> None:
        self._set_mode("Tools")
        self._append_message("Jarvis", "Launching Notepad...")
        self.app_launch_result_value.setText("Checking")
        self.set_status(AssistantStatus.THINKING)
        QApplication.processEvents()

        try:
            response = self.assistant.handle_command("open notepad")
            self._append_message("Jarvis", response.text)
            self.app_launch_result_value.setText(self._reminders_summary(response.text))
            self.set_status(AssistantStatus.SLEEPING if response.accepted else AssistantStatus.ERROR)
        except Exception as exc:  # pragma: no cover - defensive GUI boundary
            self._append_message("Jarvis", f"App launch failed: {exc}")
            self.app_launch_result_value.setText("Error")
            self.set_status(AssistantStatus.ERROR)
            self._set_mode("Error")
            return

        QTimer.singleShot(1200, lambda: self.set_status(AssistantStatus.SLEEPING))
        QTimer.singleShot(1200, lambda: self._set_mode("Idle"))

    def open_google(self) -> None:
        self._set_mode("Tools")
        self._append_message("Jarvis", "Opening Google...")
        self.website_result_value.setText("Checking")
        self.set_status(AssistantStatus.THINKING)
        QApplication.processEvents()

        try:
            response = self.assistant.handle_command("open google")
            self._append_message("Jarvis", response.text)
            self.website_result_value.setText(self._reminders_summary(response.text))
            self.set_status(AssistantStatus.SLEEPING if response.accepted else AssistantStatus.ERROR)
        except Exception as exc:  # pragma: no cover - defensive GUI boundary
            self._append_message("Jarvis", f"Website open failed: {exc}")
            self.website_result_value.setText("Error")
            self.set_status(AssistantStatus.ERROR)
            self._set_mode("Error")
            return

        QTimer.singleShot(1200, lambda: self.set_status(AssistantStatus.SLEEPING))
        QTimer.singleShot(1200, lambda: self._set_mode("Idle"))

    def list_downloads(self) -> None:
        self._set_mode("Tools")
        self._append_message("Jarvis", "Listing Downloads...")
        self.file_access_result_value.setText("Checking")
        self.set_status(AssistantStatus.THINKING)
        QApplication.processEvents()

        try:
            response = self.assistant.handle_command("list downloads")
            self._append_message("Jarvis", response.text)
            self.file_access_result_value.setText(self._reminders_summary(response.text))
            self.set_status(AssistantStatus.SLEEPING if response.accepted else AssistantStatus.ERROR)
        except Exception as exc:  # pragma: no cover - defensive GUI boundary
            self._append_message("Jarvis", f"File access failed: {exc}")
            self.file_access_result_value.setText("Error")
            self.set_status(AssistantStatus.ERROR)
            self._set_mode("Error")
            return

        QTimer.singleShot(1200, lambda: self.set_status(AssistantStatus.SLEEPING))
        QTimer.singleShot(1200, lambda: self._set_mode("Idle"))

    def test_confirmation(self) -> None:
        self._set_mode("Diagnostics")
        self._append_message("Jarvis", "Testing confirmation...")
        self.confirmation_result_value.setText("Checking")
        self.set_status(AssistantStatus.THINKING)
        QApplication.processEvents()

        try:
            result = confirm_action_gui(
                action_name="read file contents",
                risk_level="medium",
                description="Read file contents from a local file.",
                parent=self,
                settings=self.settings,
            )
            self._append_message("Jarvis", format_confirmation_result(result))
            self.confirmation_result_value.setText("Approved" if result.approved else "Denied")
            self.set_status(AssistantStatus.SLEEPING if result.approved else AssistantStatus.ERROR)
        except Exception as exc:  # pragma: no cover - defensive GUI boundary
            self._append_message("Jarvis", f"Confirmation test failed: {exc}")
            self.confirmation_result_value.setText("Error")
            self.set_status(AssistantStatus.ERROR)
            self._set_mode("Error")
            return

        QTimer.singleShot(1200, lambda: self.set_status(AssistantStatus.SLEEPING))
        QTimer.singleShot(1200, lambda: self._set_mode("Idle"))

    def start_reminder_watch(self) -> None:
        if self.reminder_watch_thread is not None and self.reminder_watch_thread.is_alive():
            self._append_message("Jarvis", "Reminder watch is already running.")
            return

        self._set_mode("Reminder Watch")
        self._append_message("Jarvis", "Starting reminder watch...")
        self.reminder_watch_runner = ReminderWatcher(
            settings=self.settings,
            status_callback=self.reminder_watch_events.put,
        )
        if not self.reminder_watch_runner.available:
            self.reminder_watch_status_value.setText("Disabled")
            self._append_message("Jarvis", "Reminder watcher is disabled.")
            self._set_reminder_watch_running(False)
            self.reminder_watch_runner = None
            return

        self.reminder_watch_status_value.setText("Starting")
        self.reminder_watch_thread = threading.Thread(target=self._run_reminder_watch_worker, daemon=True)
        self._set_reminder_watch_running(True)
        self.reminder_watch_event_timer.start(250)
        self.reminder_watch_thread.start()

    def stop_reminder_watch(self) -> None:
        if self.reminder_watch_runner is None:
            self._append_message("Jarvis", "Reminder watch is not running.")
            self._set_reminder_watch_running(False)
            self._set_mode("Idle")
            return

        self._append_message("Jarvis", "Stopping reminder watch...")
        self.reminder_watch_runner.stop()

    def _run_reminder_watch_worker(self) -> None:
        try:
            if self.reminder_watch_runner is not None:
                self.reminder_watch_runner.run_forever()
        except Exception as exc:  # pragma: no cover - defensive GUI boundary
            self.reminder_watch_events.put(f"Reminder watcher failed: {exc}")
            self.reminder_watch_events.put("Reminder watcher stopped.")

    def _drain_reminder_watch_events(self) -> None:
        while True:
            try:
                status = self.reminder_watch_events.get_nowait()
            except Empty:
                break
            self._handle_reminder_watch_status(status)

        if self.reminder_watch_thread is not None and not self.reminder_watch_thread.is_alive():
            self._set_reminder_watch_running(False)
            self.reminder_watch_event_timer.stop()
            self.reminder_watch_runner = None
            self.reminder_watch_thread = None

    def _handle_reminder_watch_status(self, status: str) -> None:
        if status.startswith("Reminder watcher summary:"):
            self.reminder_watch_status_value.setText(status)
            self._append_message("Jarvis", status)
            return
        if status.startswith("Reminder watcher failed:"):
            self.reminder_watch_status_value.setText("Error")
            self.set_status(AssistantStatus.ERROR)
            self._append_message("Jarvis", status)
            return
        if status == "Reminder watcher started.":
            self.reminder_watch_status_value.setText("Running")
            self._append_message("Jarvis", status)
            return
        if status == "Reminder watcher stopped.":
            self.reminder_watch_status_value.setText("Stopped")
            self._append_message("Jarvis", status)
            return
        if status.startswith("Due reminders:"):
            self.reminder_watch_status_value.setText("Due reminders")
            self._append_message("Jarvis", status)
            return
        if status == "No reminders are due right now.":
            self.reminder_watch_status_value.setText("Idle")
            self._append_message("Jarvis", status)
            return
        if status == "Reminder watcher is disabled.":
            self.reminder_watch_status_value.setText("Disabled")
            self._append_message("Jarvis", status)
            return
        self.reminder_watch_status_value.setText(status)
        self._append_message("Jarvis", status)

    def _set_notification_result(self, text: str) -> None:
        self.notification_result_value.setText(text)

    def _set_app_launch_result(self, text: str) -> None:
        self.app_launch_result_value.setText(text)

    def _set_mode(self, mode: str) -> None:
        self.current_mode = mode
        self.mode_value.setText(mode)

    def _handle_voice_command_status(self, status: str) -> None:
        status_map = {
            "Listening for wake phrase": AssistantStatus.LISTENING,
            "Wake detected": AssistantStatus.WAKE_DETECTED,
            "Listening for command": AssistantStatus.LISTENING,
            "Thinking": AssistantStatus.THINKING,
            "Speaking": AssistantStatus.SPEAKING,
            "Sleeping": AssistantStatus.SLEEPING,
        }
        self.set_status(status_map.get(status, AssistantStatus.SLEEPING))
        self._append_message("Jarvis", status)
        QApplication.processEvents()

    def start_voice_loop(self) -> None:
        if self.voice_loop_thread is not None and self.voice_loop_thread.is_alive():
            self._append_message("Jarvis", "Voice loop is already running.")
            return

        if self.settings.gui_voice_engine == "fast":
            self._start_fast_voice_session()
            return

        self._set_mode("Voice Loop")
        self._append_message("Jarvis", "Starting continuous voice loop...")
        self.voice_loop_runner = VoiceLoopRunner(
            settings=self.settings,
            assistant=self.assistant,
            status_callback=self.voice_loop_events.put,
        )
        self.voice_loop_status_value.setText("Starting")
        self.voice_loop_last_command_value.setText("None")
        self.voice_loop_last_response_value.setText("None")
        self.voice_loop_thread = threading.Thread(target=self._run_voice_loop_worker, daemon=True)
        self._set_voice_loop_running(True)
        self.voice_loop_event_timer.start(100)
        self.voice_loop_thread.start()

    def _start_fast_voice_session(self) -> None:
        self._set_mode("Fast Voice")
        self._append_message("Jarvis", "Starting fast voice session...")
        self.fast_voice_runner = FastVoiceRunner(
            settings=self.settings,
            assistant=self.assistant,
            output_func=lambda _message: None,
            status_callback=lambda status: self.voice_loop_events.put(
                ("fast_status", status)
            ),
            report_callback=lambda report: self.voice_loop_events.put(
                ("fast_report", report)
            ),
            progress_callback=lambda progress: self.voice_loop_events.put(
                ("fast_progress", progress)
            ),
            response_chunk_callback=(
                lambda chunk: self.voice_loop_events.put(("fast_response_chunk", chunk))
                if self.settings.gui_stream_response
                else None
            ),
            capture_max_seconds=self.settings.gui_fast_voice_max_seconds,
            strict_command_validation=True,
        )
        self.voice_loop_status_value.setText("Starting")
        self.voice_loop_last_command_value.setText("None")
        self.voice_loop_last_response_value.setText("None")
        self.voice_loop_thread = threading.Thread(
            target=self._run_fast_voice_worker,
            daemon=True,
        )
        self._set_voice_loop_running(True)
        self.voice_loop_event_timer.start(100)
        self.voice_loop_thread.start()

    def stop_voice_loop(self) -> None:
        if self.fast_voice_runner is not None:
            if self.status == AssistantStatus.LISTENING:
                message = "Cancelling microphone capture..."
            elif self.status == AssistantStatus.SPEAKING:
                message = "Interrupting spoken response..."
            else:
                message = "Stopping fast voice session..."
            self._append_message("Jarvis", message)
            self.fast_voice_runner.request_stop()
            return
        if self.voice_loop_runner is None:
            self._append_message("Jarvis", "Voice loop is not running.")
            self._set_voice_loop_running(False)
            self._set_mode("Idle")
            return

        self._append_message("Jarvis", "Stopping voice loop...")
        self.voice_loop_runner.request_stop()

    def _run_fast_voice_worker(self) -> None:
        try:
            if self.fast_voice_runner is not None:
                self.fast_voice_runner.run_continuous(max_turns=1)
        except Exception as exc:  # pragma: no cover - defensive GUI boundary
            self.voice_loop_events.put(("fast_error", f"{type(exc).__name__}: {exc}"))

    def _run_voice_loop_worker(self) -> None:
        try:
            if self.voice_loop_runner is not None:
                self.voice_loop_runner.run()
        except Exception as exc:  # pragma: no cover - defensive GUI boundary
            self.voice_loop_events.put(f"Voice loop error: {exc}")
            self.voice_loop_events.put(VOICE_LOOP_STOPPED_MESSAGE)

    def _drain_voice_loop_events(self) -> None:
        while True:
            try:
                event = self.voice_loop_events.get_nowait()
            except Empty:
                break
            if isinstance(event, tuple) and len(event) == 2:
                event_type, payload = event
                if event_type == "fast_status":
                    self._handle_fast_voice_status(str(payload))
                elif event_type == "fast_progress" and isinstance(payload, FastVoiceProgress):
                    self._handle_fast_voice_progress(payload)
                elif event_type == "fast_response_chunk":
                    self._handle_fast_voice_response_chunk(str(payload))
                elif event_type == "fast_report" and isinstance(payload, FastVoiceReport):
                    self._handle_fast_voice_report(payload)
                elif event_type == "fast_error":
                    self._handle_fast_voice_error(str(payload))
                continue
            self._handle_voice_loop_status(str(event))

        if self.voice_loop_thread is not None and not self.voice_loop_thread.is_alive():
            self.voice_loop_event_timer.stop()
            self.voice_loop_runner = None
            self.fast_voice_runner = None
            self.voice_loop_thread = None
            self._set_voice_loop_running(False)

    def _handle_fast_voice_status(self, status: str) -> None:
        status_map = {
            "Listening": AssistantStatus.LISTENING,
            "Transcribing": AssistantStatus.TRANSCRIBING,
            "Thinking": AssistantStatus.THINKING,
            "Responding": AssistantStatus.RESPONDING,
            "Speaking": AssistantStatus.SPEAKING,
            "Stopping": AssistantStatus.RESPONDING,
            "Capture cancelled": AssistantStatus.SLEEPING,
            "Interrupted": AssistantStatus.SLEEPING,
            "TTS interruption unavailable": AssistantStatus.SPEAKING,
            "Error": AssistantStatus.ERROR,
            "Stopped": AssistantStatus.SLEEPING,
        }
        self.voice_loop_status_value.setText(status)
        self.set_status(status_map.get(status, AssistantStatus.SLEEPING))
        if status == "Listening":
            self.stop_voice_loop_button.setText("Stop Listening")
        elif status == "Speaking":
            self.stop_voice_loop_button.setText("Stop Speaking")
        elif status in {"Thinking", "Responding"}:
            self.stop_voice_loop_button.setText("Interrupt")
        else:
            self.stop_voice_loop_button.setText("Stop / Interrupt")
        if status == "Capture cancelled":
            self.voice_detail_value.setText("Microphone capture cancelled")
        elif status == "Interrupted":
            self.voice_detail_value.setText("Spoken response interrupted")
        elif status == "TTS interruption unavailable":
            self.voice_detail_value.setText(
                "This TTS provider cannot stop active playback; it will stop afterward."
            )

    def _handle_fast_voice_error(self, error: str) -> None:
        self.voice_loop_status_value.setText("Error")
        self.voice_detail_value.setText(error)
        self.set_status(AssistantStatus.ERROR)
        self._append_message("Error", error)

    def _handle_fast_voice_progress(self, progress: FastVoiceProgress) -> None:
        stage_labels = {
            "listening_started": "Listening started",
            "vad_waiting": "VAD waiting",
            "vad_triggered": "VAD triggered",
            "speech_detected": "Speech detected",
            "silence_detected": "Silence detected",
            "capture_complete": "Capture complete",
            "transcribing": "Transcribing",
            "transcript_ready": "Transcript ready",
            "thinking": "Thinking",
            "response_ready": "Response ready",
        }
        stage_status = {
            "listening_started": AssistantStatus.LISTENING,
            "vad_waiting": AssistantStatus.LISTENING,
            "vad_triggered": AssistantStatus.LISTENING,
            "speech_detected": AssistantStatus.LISTENING,
            "silence_detected": AssistantStatus.LISTENING,
            "capture_complete": AssistantStatus.LISTENING,
            "transcribing": AssistantStatus.TRANSCRIBING,
            "transcript_ready": AssistantStatus.TRANSCRIBING,
            "thinking": AssistantStatus.THINKING,
            "response_ready": AssistantStatus.RESPONDING,
        }
        label = stage_labels.get(progress.stage, progress.stage.replace("_", " ").title())
        self.voice_loop_status_value.setText(label)
        self.set_status(stage_status.get(progress.stage, AssistantStatus.LISTENING))

        if progress.stage == "listening_started":
            self.transcript.setText("Listening for your command...")
            self.voice_vad_value.setText("no")
            self.voice_command_score_value.setText("0%")
            self.voice_command_score_bar.setValue(0)

        progress_percent = int(round(progress.capture_progress * 100))
        self.voice_vad_value.setText("yes" if progress.vad_crossed else "no")
        self.voice_command_score_value.setText(f"{progress_percent}%")
        self.voice_command_score_bar.setValue(progress_percent)
        self.voice_timing_command_capture_value.setText(
            f"{progress.capture_elapsed_ms:.0f} ms"
        )
        self.voice_timing_slow_value.setText(
            f"speech={progress.speech_ms:.0f}ms silence={progress.trailing_silence_ms:.0f}ms"
        )

        detail = label
        if progress.stage == "vad_waiting":
            detail = f"Waiting for speech · capture {progress_percent}%"
        elif progress.stage == "speech_detected":
            detail = f"Speech detected · {progress.speech_ms:.0f} ms"
        elif progress.stage == "silence_detected":
            detail = f"Silence detected · {progress.trailing_silence_ms:.0f} ms trailing"
        self.voice_detail_value.setText(detail)

        if progress.stage == "transcript_ready":
            transcript = progress.transcript or "<empty>"
            self.transcript.setText(transcript)
            self.voice_raw_speech_value.setText(transcript)
        if (
            progress.stage == "thinking"
            and self.settings.fast_voice_stream_openai
            and self.settings.gui_stream_response
        ):
            self.voice_response_panel.clear()
        if progress.stage == "response_ready" and progress.response:
            self.voice_response_panel.setText(progress.response)

    def _handle_fast_voice_response_chunk(self, chunk: str) -> None:
        if not chunk or not self.settings.gui_stream_response:
            return
        self.voice_loop_status_value.setText("Responding")
        self.set_status(AssistantStatus.RESPONDING)
        self.voice_detail_value.setText("Streaming response")
        self.voice_response_panel.insertPlainText(chunk)
        self.voice_response_panel.ensureCursorVisible()

    def _handle_fast_voice_report(self, report: FastVoiceReport) -> None:
        raw = report.raw_transcript or "<empty>"
        cleaned = report.cleaned_transcript or "<empty>"
        repaired = report.command or "<empty>"
        response = report.assistant_response.text if report.assistant_response else "None"
        repair = report.speech_repair

        self.voice_provider_value.setText(report.provider_name)
        self.transcript.setText(raw)
        self.voice_raw_speech_value.setText(raw)
        self.voice_cleaned_value.setText(cleaned)
        self.voice_interpreted_value.setText(repaired)
        self.voice_loop_last_command_value.setText(repaired)
        self.voice_loop_last_response_value.setText(response)
        self.voice_response_panel.setText(self._compact_vision_response_text(response) if self._is_vision_command(repaired) else response)
        self.voice_vad_value.setText("yes" if report.vad_crossed else "no")
        self.voice_wake_only_value.setText("yes" if report.wake_only else "no")
        self.voice_repair_strategy_value.setText(repair.strategy if repair else "--")
        if report.transcript_confidence is not None:
            confidence_percent = int(round(report.transcript_confidence * 100))
            self.voice_transcript_confidence_bar.setValue(confidence_percent)
        if repair is not None:
            self.voice_repair_confidence_value.setText(f"{repair.confidence * 100:.0f}%")
            self.voice_repair_confidence_bar.setValue(int(round(repair.confidence * 100)))
        self._update_vision_panel(repaired, response)

        self.voice_response_speech_value.setText(
            _fast_voice_tts_status(
                self.settings,
                failed=bool(report.tts_result is not None and report.tts_result.error),
            )
        )
        if not report.command_accepted:
            reason = report.validation.rejection_reason or "unusable speech"
            self.voice_detail_value.setText(f"Command rejected: {reason}. Please try again.")

        timing = report.timing
        self.voice_timing_wake_capture_value.setText(f"{timing.vad_wait_ms:.0f} ms")
        self.voice_timing_wake_transcribe_value.setText(f"{timing.audio_prepare_ms:.0f} ms")
        self.voice_timing_command_capture_value.setText(f"{timing.capture_ms:.0f} ms")
        self.voice_timing_command_transcribe_value.setText(f"{timing.transcribe_ms:.0f} ms")
        self.voice_timing_openai_value.setText(f"{timing.openai_ms:.0f} ms")
        self.voice_timing_tts_value.setText(f"{timing.tts_ms:.0f} ms")
        self.voice_timing_total_value.setText(f"{timing.total_ms:.0f} ms")
        self.voice_timing_slow_value.setText(
            f"speech={timing.speech_ms:.0f}ms silence={timing.trailing_silence_ms:.0f}ms"
        )

        self._append_message("Heard", raw)
        if report.assistant_response is not None:
            self._append_message("Jarvis", response)
        if report.errors:
            self._handle_fast_voice_error("; ".join(report.errors))

    def _handle_voice_loop_status(self, status: str) -> None:
        status_map = {
            VOICE_LOOP_STARTED_MESSAGE: AssistantStatus.SLEEPING,
            "Sleeping": AssistantStatus.SLEEPING,
            "Listening for wake phrase": AssistantStatus.LISTENING,
            "Wake unavailable; manual command mode": AssistantStatus.SLEEPING,
            "Wake detected": AssistantStatus.WAKE_DETECTED,
            COMMAND_PROMPT: AssistantStatus.WAKE_DETECTED,
            LISTENING_FOR_COMMAND_PROMPT: AssistantStatus.LISTENING,
            LISTENING_FOR_FOLLOW_UP_PROMPT: AssistantStatus.FOLLOW_UP,
            "Thinking": AssistantStatus.THINKING,
            "Speaking": AssistantStatus.SPEAKING,
            RETURNING_TO_SLEEP_MESSAGE: AssistantStatus.SLEEPING,
            NO_COMMAND_DETECTED_MESSAGE: AssistantStatus.SLEEPING,
            RETRYING_COMMAND_CAPTURE_MESSAGE: AssistantStatus.LISTENING,
            RETRYING_FOLLOW_UP_CAPTURE_MESSAGE: AssistantStatus.LISTENING,
            STOP_COMMAND_DETECTED_MESSAGE: AssistantStatus.SLEEPING,
            VOICE_LOOP_STOPPED_MESSAGE: AssistantStatus.SLEEPING,
        }
        if status.startswith(WAKE_DIAGNOSTICS_PREFIX):
            self._update_wake_diagnostics(status)
            self._append_message("Diagnostics", status)
            return
        if status.startswith(CAPTURE_DIAGNOSTICS_PREFIX):
            self._update_capture_diagnostics(status)
            self._append_message("Diagnostics", status)
            return
        if status.startswith(SPEECH_REPAIR_PREFIX):
            self._update_speech_repair(status)
            self._append_message("Diagnostics", status)
            return
        if status.startswith("Timing summary:"):
            self._update_turn_timing(status)
            self._append_message("Diagnostics", status)
            return
        if status.startswith("Did you mean:"):
            self.voice_loop_status_value.setText("Confirming repair")
            self.set_status(AssistantStatus.LISTENING)
            self._append_message("Jarvis", status)
            return
        if status.startswith("Repair confirmation:"):
            self.voice_loop_status_value.setText(status)
            self._append_message("Jarvis", status)
            return
        if status.startswith("Last recognized command:"):
            command_text = status.split(":", 1)[1].strip() or "None"
            self.voice_loop_last_command_value.setText(command_text)
            self.voice_loop_status_value.setText("No command detected" if command_text == "<empty>" else "Command received")
            self._append_message("Heard", command_text)
            return
        if status.startswith(REJECTED_COMMAND_PREFIX):
            command_text = status.removeprefix(REJECTED_COMMAND_PREFIX).strip()
            if " (" in command_text:
                command_text = command_text.split(" (", 1)[0].strip()
            self.voice_loop_last_command_value.setText(f"Rejected: {command_text or '<empty>'}")
            self.voice_loop_status_value.setText("Rejected command")
            self.set_status(AssistantStatus.LISTENING)
            self._append_message("Jarvis", status)
            return
        if status.startswith(REJECTED_FOLLOW_UP_PREFIX):
            command_text = status.removeprefix(REJECTED_FOLLOW_UP_PREFIX).strip()
            if " (" in command_text:
                command_text = command_text.split(" (", 1)[0].strip()
            self.voice_loop_last_command_value.setText(f"Rejected follow-up: {command_text or '<empty>'}")
            self.voice_loop_status_value.setText("Rejected follow-up")
            self.set_status(AssistantStatus.FOLLOW_UP)
            self._append_message("Jarvis", status)
            return
        if status == RETRYING_COMMAND_CAPTURE_MESSAGE:
            self.voice_loop_status_value.setText("Retrying command capture")
            self.set_status(AssistantStatus.LISTENING)
            self._append_message("Jarvis", status)
            return
        if status == RETRYING_FOLLOW_UP_CAPTURE_MESSAGE:
            self.voice_loop_status_value.setText("Retrying follow-up capture")
            self.set_status(AssistantStatus.LISTENING)
            self._append_message("Jarvis", status)
            return
        if status.startswith(ACCEPTED_COMMAND_PREFIX):
            command_text = status.removeprefix(ACCEPTED_COMMAND_PREFIX).strip()
            self.voice_loop_last_command_value.setText(command_text or "None")
            self.voice_loop_status_value.setText("Accepted command")
            self.set_status(AssistantStatus.THINKING)
            self._append_message("Jarvis", status)
            return
        if status.startswith(ACCEPTED_FOLLOW_UP_PREFIX):
            command_text = status.removeprefix(ACCEPTED_FOLLOW_UP_PREFIX).strip()
            self.voice_loop_last_command_value.setText(command_text or "None")
            self.voice_loop_status_value.setText("Accepted follow-up")
            self.set_status(AssistantStatus.THINKING)
            self._append_message("Jarvis", status)
            return
        if status.startswith("Last Jarvis response:"):
            response_text = status.split(":", 1)[1].strip() or "None"
            self.voice_loop_last_response_value.setText(response_text)
            self.voice_response_panel.setText(response_text)
            self.voice_loop_status_value.setText("Response ready")
            self._append_message("Jarvis", response_text)
            return
        if status.startswith("Voice loop summary:"):
            self.voice_loop_status_value.setText(status)
            self._append_message("Jarvis", status)
            return
        if status.startswith("Voice loop error:"):
            self.set_status(AssistantStatus.ERROR)
        else:
            self.set_status(status_map.get(status, AssistantStatus.SLEEPING))
        if status == VOICE_LOOP_STARTED_MESSAGE:
            self.voice_loop_status_value.setText("Sleeping")
        elif status == VOICE_LOOP_STOPPED_MESSAGE:
            self.voice_loop_status_value.setText("Stopped")
        else:
            self.voice_loop_status_value.setText(status)
        self._append_message("Jarvis", status)

    @staticmethod
    def _reminders_summary(text: str) -> str:
        first_line = text.splitlines()[0].strip() if text.splitlines() else text.strip()
        return first_line or "Idle"

    def _set_voice_loop_running(self, running: bool) -> None:
        self.start_voice_loop_button.setEnabled(not running)
        self.stop_voice_loop_button.setEnabled(running)
        if not running:
            self.stop_voice_loop_button.setText("Stop / Interrupt")
        if self.start_voice_loop_action is not None:
            self.start_voice_loop_action.setEnabled(not running)
        if self.stop_voice_loop_action is not None:
            self.stop_voice_loop_action.setEnabled(running)
        if running:
            self.voice_loop_status_value.setText("Running")
            if self.fast_voice_runner is not None:
                self.voice_detail_value.setText("Fast voice active")
                self._set_mode("Fast Voice")
            else:
                self.voice_detail_value.setText("Voice loop active")
                self._set_mode("Voice Loop")
        elif self.voice_loop_runner is None and self.fast_voice_runner is None:
            self.voice_loop_status_value.setText("Idle")
            self.voice_detail_value.setText("Waiting to start voice")
            self._set_mode("Idle")

    def _set_reminder_watch_running(self, running: bool) -> None:
        self.start_reminder_watch_button.setEnabled(not running)
        self.stop_reminder_watch_button.setEnabled(running)
        if self.start_reminder_watch_action is not None:
            self.start_reminder_watch_action.setEnabled(not running)
        if self.stop_reminder_watch_action is not None:
            self.stop_reminder_watch_action.setEnabled(running)
        if running:
            self.reminder_watch_status_value.setText("Running")
            self._set_mode("Reminder Watch")
        elif self.reminder_watch_runner is None:
            self.reminder_watch_status_value.setText("Idle")
            self._set_mode("Idle")

    def set_status(self, status: AssistantStatus) -> None:
        self.status = status
        self.status_label.setText(status.value)
        self.header_mode_value.setText(status.value.upper())
        self.voice_state_value.setText(status.value)
        detail_map = {
            AssistantStatus.SLEEPING: "Waiting for wake phrase",
            AssistantStatus.LISTENING: "Listening through microphone",
            AssistantStatus.TRANSCRIBING: "Transcribing speech",
            AssistantStatus.THINKING: "Processing command",
            AssistantStatus.SPEAKING: "Speaking response",
            AssistantStatus.RESPONDING: "Response ready",
            AssistantStatus.FOLLOW_UP: "Listening for follow-up",
            AssistantStatus.WAKE_DETECTED: "Wake phrase detected",
            AssistantStatus.ERROR: "Attention needed",
        }
        self.voice_detail_value.setText(detail_map[status])
        self.header_health_value.setText("ERROR" if status == AssistantStatus.ERROR else "READY")
        color = STATUS_COLORS[status]
        self.status_label.setStyleSheet(
            f"background: rgba(82, 20, 20, 110); border: 1px solid {color}; color: #f7efef;"
        )
        self.orb.set_status(status)

    def _append_message(self, speaker: str, message: str) -> None:
        self.transcript.append(f"\n{speaker}: {message}")

    def _update_vision_panel(self, command: str, response_text: str) -> None:
        if not self._is_vision_command(command):
            return
        screen_label = self._vision_screen_label(command)
        path = self._extract_value(response_text, "Screenshot path")
        provider = self._extract_value(response_text, "Vision provider") or self._extract_value(response_text, "OCR provider")
        ocr_status = "Used" if "OCR text:" in response_text or "OCR provider:" in response_text else ("Available" if "OCR" in response_text else "Unknown")
        summary = self._vision_summary(response_text)

        self.vision_capture_value.setText(screen_label or "--")
        self.vision_path_value.setText(path or "--")
        self.vision_ocr_value.setText(ocr_status)
        self.vision_provider_status_value.setText(provider or "--")
        self.vision_summary_value.setText(summary or "--")

    def _compact_vision_response_text(self, response_text: str, max_lines: int = 6, max_chars: int = 420) -> str:
        lines = []
        for raw_line in response_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("Screenshot path:") or line.startswith("Image size:") or line.startswith("Screen:"):
                continue
            if line.startswith("Vision provider:") or line.startswith("OCR provider:"):
                continue
            if line.startswith("OCR text:"):
                continue
            lines.append(line)
        compact = "\n".join(lines[:max_lines]).strip()
        if len(compact) > max_chars:
            compact = compact[: max_chars - 1].rstrip() + "…"
        return compact or response_text.strip()

    @staticmethod
    def _is_vision_command(command: str) -> bool:
        normalized = " ".join(command.lower().strip().split())
        return any(
            normalized == phrase
            or normalized.startswith(phrase + " ")
            for phrase in (
                "take screenshot",
                "list screens",
                "read screen",
                "read my screen",
                "read my screen text",
                "read screen text",
                "what is on my screen",
                "look at my screen",
                "describe my screen",
                "describe screen",
                "what is on my primary screen",
                "what is on screen",
            )
        )

    @staticmethod
    def _vision_screen_label(command: str) -> str | None:
        normalized = " ".join(command.lower().strip().split())
        if "screen 1" in normalized:
            return "Screen 1"
        if "screen 2" in normalized:
            return "Screen 2"
        if "primary screen" in normalized or normalized in {"what is on my screen", "read my screen", "describe my screen", "look at my screen"}:
            return "Primary screen"
        if normalized == "list screens":
            return "All screens"
        return None

    @staticmethod
    def _extract_value(text: str, label: str) -> str | None:
        for line in text.splitlines():
            normalized = line.strip()
            prefix = f"{label}:"
            if normalized.startswith(prefix):
                return normalized.split(":", 1)[1].strip() or None
        return None

    @staticmethod
    def _vision_summary(response_text: str) -> str | None:
        lines = []
        for raw_line in response_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if any(
                line.startswith(prefix)
                for prefix in (
                    "Screenshot path:",
                    "Image size:",
                    "Screen:",
                    "Vision provider:",
                    "OCR provider:",
                )
            ):
                continue
            if line.startswith("OCR text:"):
                continue
            lines.append(line)
        if not lines:
            return None
        summary = lines[0]
        if len(summary) > 140:
            summary = summary[:139].rstrip() + "…"
        return summary

    def _update_wake_diagnostics(self, status: str) -> None:
        values = self._parse_diagnostics(status.removeprefix(WAKE_DIAGNOSTICS_PREFIX))
        if provider := values.get("provider"):
            self.voice_provider_value.setText(provider)
        score = values.get("score")
        threshold = values.get("threshold")
        if score and threshold:
            self.voice_wake_score_value.setText(f"{score} / {threshold}")
            self._set_percent_bar(self.voice_wake_score_bar, score)
        elif score:
            self.voice_wake_score_value.setText(score)
            self._set_percent_bar(self.voice_wake_score_bar, score)
        self._update_rms_labels(values)

    def _update_capture_diagnostics(self, status: str) -> None:
        values = self._parse_diagnostics(status.removeprefix(CAPTURE_DIAGNOSTICS_PREFIX))
        if provider := values.get("provider"):
            self.voice_provider_value.setText(provider)
        if command_score := values.get("command_score"):
            self.voice_command_score_value.setText(command_score)
            self._set_percent_bar(self.voice_command_score_bar, command_score)
        if transcript_confidence := values.get("transcript_confidence"):
            self._set_percent_bar(self.voice_transcript_confidence_bar, transcript_confidence)
        self._update_rms_labels(values)

    def _update_speech_repair(self, status: str) -> None:
        values = self._parse_pipe_diagnostics(status.removeprefix(SPEECH_REPAIR_PREFIX))
        self.voice_raw_speech_value.setText(values.get("raw", "--"))
        self.voice_interpreted_value.setText(values.get("repaired", "--"))
        confidence = values.get("confidence")
        if confidence:
            try:
                self.voice_repair_confidence_value.setText(f"{float(confidence) * 100:.0f}%")
            except ValueError:
                self.voice_repair_confidence_value.setText(confidence)
            self._set_percent_bar(self.voice_repair_confidence_bar, confidence)
        self.voice_repair_strategy_value.setText(values.get("strategy", "--"))

    def _update_turn_timing(self, status: str) -> None:
        values = self._parse_diagnostics(status.removeprefix("Timing summary:"))
        self.voice_timing_wake_capture_value.setText(self._format_ms(values.get("wake_capture_ms")))
        self.voice_timing_wake_transcribe_value.setText(self._format_ms(values.get("wake_transcribe_ms")))
        self.voice_timing_command_capture_value.setText(self._format_ms(values.get("command_capture_ms")))
        self.voice_timing_command_transcribe_value.setText(self._format_ms(values.get("command_transcribe_ms")))
        self.voice_timing_openai_value.setText(self._format_ms(values.get("openai_ms")))
        self.voice_timing_tts_value.setText(self._format_ms(values.get("tts_ms")))
        self.voice_timing_total_value.setText(self._format_ms(values.get("total_turn_ms")))
        self.voice_timing_slow_value.setText(values.get("slow_stages", "--"))

    def _update_rms_labels(self, values: dict[str, str]) -> None:
        average_rms = values.get("average_rms", "--")
        max_rms = values.get("max_rms", "--")
        self.voice_rms_value.setText(f"{average_rms} / {max_rms}")
        if vad_crossed := values.get("vad_crossed"):
            self.voice_vad_value.setText(vad_crossed)

    @staticmethod
    def _set_percent_bar(bar: QProgressBar, value: str | float | None) -> None:
        if value is None:
            bar.setValue(0)
            return
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            bar.setValue(0)
            return
        if numeric <= 1.0:
            numeric *= 100.0
        bar.setValue(max(0, min(100, int(round(numeric)))))

    @staticmethod
    def _format_ms(value: str | None) -> str:
        if not value:
            return "--"
        try:
            return f"{float(value):.0f} ms"
        except ValueError:
            return value

    @staticmethod
    def _parse_diagnostics(payload: str) -> dict[str, str]:
        values: dict[str, str] = {}
        for part in payload.strip().split():
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            values[key.strip()] = value.strip()
        return values

    @staticmethod
    def _parse_pipe_diagnostics(payload: str) -> dict[str, str]:
        values: dict[str, str] = {}
        for part in payload.strip().split("|"):
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            values[key.strip()] = value.strip()
        return values

    def request_quit(self) -> None:
        if self.fast_voice_runner is not None:
            self.fast_voice_runner.request_stop()
        if self.voice_loop_runner is not None:
            self.voice_loop_runner.request_stop()
        if self.reminder_watch_runner is not None:
            self.reminder_watch_runner.stop()
        self._allow_close = True
        self.tray_icon.hide()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._allow_close or not self.settings.minimize_to_tray:
            if self.fast_voice_runner is not None:
                self.fast_voice_runner.request_stop()
            if self.voice_loop_runner is not None:
                self.voice_loop_runner.request_stop()
            if self.reminder_watch_runner is not None:
                self.reminder_watch_runner.stop()
            event.accept()
            return

        event.ignore()
        self.hide()
        if not self._tray_notice_shown and self.tray_icon.isVisible():
            self.tray_icon.showMessage(
                self.settings.app_name,
                "Jarvis is still running in the system tray.",
                QSystemTrayIcon.MessageIcon.Information,
                2500,
            )
            self._tray_notice_shown = True

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_position is not None:
            self.move(event.globalPosition().toPoint() - self._drag_position)
            event.accept()
