from __future__ import annotations

import threading
from enum import Enum
from queue import Empty, Queue

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QIcon, QLinearGradient, QMouseEvent, QPainter, QPixmap, QRadialGradient
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from assistant.core import AssistantCore
from config.settings import AppSettings
from reminders.scheduler import ReminderWatcher
from services.notification_service import NotificationService, format_notification_check_report
from voice.audio_diagnostics import AudioDiagnostics, format_microphone_test_summary
from voice.voice_command_test import COMMAND_PROMPT, LISTENING_FOR_COMMAND_PROMPT, VoiceCommandTestRunner, format_voice_command_report
from voice.voice_loop import (
    RETURNING_TO_SLEEP_MESSAGE,
    STOP_COMMAND_DETECTED_MESSAGE,
    VOICE_LOOP_STARTED_MESSAGE,
    VOICE_LOOP_STOPPED_MESSAGE,
    VoiceLoopRunner,
)


class AssistantStatus(str, Enum):
    SLEEPING = "Sleeping"
    LISTENING = "Listening"
    THINKING = "Thinking"
    SPEAKING = "Speaking"
    WAKE_DETECTED = "Wake detected"
    ERROR = "Error"


STATUS_COLORS = {
    AssistantStatus.SLEEPING: "#5f7d95",
    AssistantStatus.LISTENING: "#37d6ff",
    AssistantStatus.THINKING: "#a78bfa",
    AssistantStatus.SPEAKING: "#6ee7b7",
    AssistantStatus.WAKE_DETECTED: "#facc15",
    AssistantStatus.ERROR: "#fb7185",
}


class OrbWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._status = AssistantStatus.SLEEPING
        self._pulse = 0
        self.setFixedSize(170, 170)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(60)

    def set_status(self, status: AssistantStatus) -> None:
        self._status = status
        self.update()

    def _tick(self) -> None:
        self._pulse = (self._pulse + 1) % 80
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        color = QColor(STATUS_COLORS[self._status])
        pulse_size = 10 + abs(40 - self._pulse) / 4

        glow = QRadialGradient(self.rect().center(), 84)
        glow.setColorAt(0.0, QColor(color.red(), color.green(), color.blue(), 130))
        glow.setColorAt(0.65, QColor(color.red(), color.green(), color.blue(), 45))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(glow)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(self.rect().adjusted(int(pulse_size), int(pulse_size), -int(pulse_size), -int(pulse_size)))

        body = QRadialGradient(self.rect().center(), 56)
        body.setColorAt(0.0, QColor("#e0f7ff"))
        body.setColorAt(0.35, color)
        body.setColorAt(1.0, QColor("#07111d"))
        painter.setBrush(body)
        painter.drawEllipse(self.rect().adjusted(38, 38, -38, -38))

        ring = QLinearGradient(38, 38, 132, 132)
        ring.setColorAt(0.0, QColor("#88f7ff"))
        ring.setColorAt(1.0, QColor("#3b82f6"))
        painter.setPen(color)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(self.rect().adjusted(30, 30, -30, -30))


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
        self.resize(self.settings.window_width, self.settings.window_height)

        self.orb = OrbWidget()
        self.status = AssistantStatus.SLEEPING
        self.status_label = QLabel(self.status.value)
        self.transcript = QTextEdit()
        self.command_input = QLineEdit()
        self.mic_test_button = QPushButton("Mic Test")
        self.voice_command_button = QPushButton("Voice Test")
        self.start_voice_loop_button = QPushButton("Start Loop")
        self.stop_voice_loop_button = QPushButton("Stop Loop")
        self.check_reminders_button = QPushButton("Check Reminders")
        self.notification_test_button = QPushButton("Test Notification")
        self.launch_notepad_button = QPushButton("Launch Notepad")
        self.open_google_button = QPushButton("Open Google")
        self.list_downloads_button = QPushButton("List Downloads")
        self.start_reminder_watch_button = QPushButton("Start Watch")
        self.stop_reminder_watch_button = QPushButton("Stop Watch")
        self.send_button = QPushButton("Send")
        self.audio_diagnostics = AudioDiagnostics(settings)
        self.voice_loop_status_value = QLabel("Idle")
        self.voice_loop_last_command_value = QLabel("None")
        self.voice_loop_last_response_value = QLabel("None")
        self.reminders_check_value = QLabel("Idle")
        self.notification_result_value = QLabel("Idle")
        self.app_launch_result_value = QLabel("Idle")
        self.website_result_value = QLabel("Idle")
        self.file_access_result_value = QLabel("Idle")
        self.reminder_watch_status_value = QLabel("Idle")
        self.voice_loop_runner: VoiceLoopRunner | None = None
        self.voice_loop_thread: threading.Thread | None = None
        self.voice_loop_events: Queue[str] = Queue()
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
        self.launch_notepad_action: QAction | None = None
        self.open_google_action: QAction | None = None
        self.list_downloads_action: QAction | None = None
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
        self.voice_loop_status_value.setObjectName("voiceLoopValue")
        self.voice_loop_last_command_value.setObjectName("voiceLoopValue")
        self.voice_loop_last_response_value.setObjectName("voiceLoopValue")
        self.reminders_check_value.setObjectName("voiceLoopValue")
        self.notification_result_value.setObjectName("voiceLoopValue")
        self.app_launch_result_value.setObjectName("voiceLoopValue")
        self.website_result_value.setObjectName("voiceLoopValue")
        self.file_access_result_value.setObjectName("voiceLoopValue")
        self.reminder_watch_status_value.setObjectName("voiceLoopValue")

        minimize_button = QPushButton("-")
        minimize_button.setObjectName("windowButton")
        minimize_button.clicked.connect(self.hide)
        close_button = QPushButton("x")
        close_button.setObjectName("windowButton")
        close_button.clicked.connect(self.close)

        title_row = QHBoxLayout()
        title_block = QVBoxLayout()
        title_block.addWidget(title)
        title_block.addWidget(subtitle)
        title_row.addLayout(title_block)
        title_row.addStretch(1)
        title_row.addWidget(self.status_label)
        title_row.addWidget(minimize_button)
        title_row.addWidget(close_button)

        self.transcript.setReadOnly(True)
        self.transcript.setObjectName("transcript")
        self.transcript.setText("Jarvis foundation online.\nType a command to test the Phase 1 assistant stub.")

        self.command_input.setPlaceholderText("Type a command...")
        self.command_input.setObjectName("commandInput")
        self.mic_test_button.setObjectName("secondaryButton")
        self.voice_command_button.setObjectName("secondaryButton")
        self.start_voice_loop_button.setObjectName("secondaryButton")
        self.stop_voice_loop_button.setObjectName("secondaryButton")
        self.stop_voice_loop_button.setEnabled(False)
        self.check_reminders_button.setObjectName("secondaryButton")
        self.notification_test_button.setObjectName("secondaryButton")
        self.launch_notepad_button.setObjectName("secondaryButton")
        self.open_google_button.setObjectName("secondaryButton")
        self.list_downloads_button.setObjectName("secondaryButton")
        self.start_reminder_watch_button.setObjectName("secondaryButton")
        self.stop_reminder_watch_button.setObjectName("secondaryButton")
        self.stop_reminder_watch_button.setEnabled(False)
        self.send_button.setObjectName("sendButton")

        input_row = QHBoxLayout()
        input_row.addWidget(self.command_input)
        input_row.addWidget(self.mic_test_button)
        input_row.addWidget(self.voice_command_button)
        input_row.addWidget(self.start_voice_loop_button)
        input_row.addWidget(self.stop_voice_loop_button)
        input_row.addWidget(self.check_reminders_button)
        input_row.addWidget(self.notification_test_button)
        input_row.addWidget(self.launch_notepad_button)
        input_row.addWidget(self.open_google_button)
        input_row.addWidget(self.list_downloads_button)
        input_row.addWidget(self.start_reminder_watch_button)
        input_row.addWidget(self.stop_reminder_watch_button)
        input_row.addWidget(self.send_button)

        loop_info = QFrame()
        loop_info.setObjectName("loopInfo")
        loop_info_layout = QVBoxLayout(loop_info)
        loop_info_layout.setContentsMargins(12, 10, 12, 10)
        loop_info_layout.setSpacing(4)

        loop_status_row = QHBoxLayout()
        loop_status_row.addWidget(QLabel("Loop status"))
        loop_status_row.addWidget(self.voice_loop_status_value, stretch=1)

        loop_command_row = QHBoxLayout()
        loop_command_row.addWidget(QLabel("Last command"))
        loop_command_row.addWidget(self.voice_loop_last_command_value, stretch=1)

        loop_response_row = QHBoxLayout()
        loop_response_row.addWidget(QLabel("Last response"))
        loop_response_row.addWidget(self.voice_loop_last_response_value, stretch=1)

        reminders_row = QHBoxLayout()
        reminders_row.addWidget(QLabel("Reminder check"))
        reminders_row.addWidget(self.reminders_check_value, stretch=1)

        notification_row = QHBoxLayout()
        notification_row.addWidget(QLabel("Notification test"))
        notification_row.addWidget(self.notification_result_value, stretch=1)

        launch_row = QHBoxLayout()
        launch_row.addWidget(QLabel("App launch"))
        launch_row.addWidget(self.app_launch_result_value, stretch=1)

        website_row = QHBoxLayout()
        website_row.addWidget(QLabel("Website open"))
        website_row.addWidget(self.website_result_value, stretch=1)

        file_access_row = QHBoxLayout()
        file_access_row.addWidget(QLabel("File access"))
        file_access_row.addWidget(self.file_access_result_value, stretch=1)

        watch_row = QHBoxLayout()
        watch_row.addWidget(QLabel("Reminder watch"))
        watch_row.addWidget(self.reminder_watch_status_value, stretch=1)

        loop_info_layout.addLayout(loop_status_row)
        loop_info_layout.addLayout(loop_command_row)
        loop_info_layout.addLayout(loop_response_row)
        loop_info_layout.addLayout(reminders_row)
        loop_info_layout.addLayout(notification_row)
        loop_info_layout.addLayout(launch_row)
        loop_info_layout.addLayout(website_row)
        loop_info_layout.addLayout(file_access_row)
        loop_info_layout.addLayout(watch_row)

        layout = QVBoxLayout(shell)
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setSpacing(16)
        layout.addLayout(title_row)
        layout.addWidget(self.orb, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(loop_info)
        layout.addWidget(self.transcript, stretch=1)
        layout.addLayout(input_row)

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.addWidget(shell)
        self.setCentralWidget(root)

        self.setStyleSheet(
            """
            #shell {
                background: rgba(10, 18, 32, 238);
                border: 1px solid rgba(86, 204, 242, 95);
                border-radius: 18px;
            }
            #title {
                color: #e5fbff;
                font-size: 30px;
                font-weight: 700;
                letter-spacing: 0px;
            }
            #subtitle {
                color: #8fb3c8;
                font-size: 12px;
            }
            #statusPill {
                color: #dff9ff;
                background: rgba(37, 99, 235, 70);
                border: 1px solid rgba(125, 211, 252, 120);
                border-radius: 12px;
                padding: 6px 10px;
                font-weight: 600;
            }
            #loopInfo {
                background: rgba(3, 7, 18, 95);
                border: 1px solid rgba(71, 85, 105, 100);
                border-radius: 12px;
            }
            #voiceLoopValue {
                color: #dff9ff;
                font-weight: 500;
            }
            #windowButton {
                color: #dff9ff;
                background: rgba(148, 163, 184, 35);
                border: 1px solid rgba(148, 163, 184, 70);
                border-radius: 10px;
                min-width: 28px;
                min-height: 28px;
            }
            #windowButton:hover {
                background: rgba(125, 211, 252, 55);
            }
            #transcript {
                color: #e2eef7;
                background: rgba(3, 7, 18, 125);
                border: 1px solid rgba(71, 85, 105, 120);
                border-radius: 12px;
                padding: 12px;
                font-size: 13px;
            }
            #commandInput {
                color: #f8fbff;
                background: rgba(15, 23, 42, 210);
                border: 1px solid rgba(96, 165, 250, 110);
                border-radius: 12px;
                padding: 11px 12px;
                font-size: 13px;
            }
            #commandInput:focus {
                border: 1px solid rgba(34, 211, 238, 190);
            }
            #sendButton {
                color: #031525;
                background: #67e8f9;
                border: 0;
                border-radius: 12px;
                padding: 11px 18px;
                font-weight: 700;
            }
            #sendButton:hover {
                background: #a5f3fc;
            }
            #secondaryButton {
                color: #dff9ff;
                background: rgba(15, 23, 42, 210);
                border: 1px solid rgba(125, 211, 252, 100);
                border-radius: 12px;
                padding: 11px 14px;
                font-weight: 600;
            }
            #secondaryButton:hover {
                background: rgba(34, 211, 238, 55);
            }
            """
        )

    def _connect_signals(self) -> None:
        self.command_input.returnPressed.connect(self.handle_command)
        self.send_button.clicked.connect(self.handle_command)
        self.mic_test_button.clicked.connect(self.run_microphone_test)
        self.voice_command_button.clicked.connect(self.run_voice_command_test)
        self.start_voice_loop_button.clicked.connect(self.start_voice_loop)
        self.stop_voice_loop_button.clicked.connect(self.stop_voice_loop)
        self.check_reminders_button.clicked.connect(self.check_reminders)
        self.notification_test_button.clicked.connect(self.test_notification)
        self.launch_notepad_button.clicked.connect(self.launch_notepad)
        self.open_google_button.clicked.connect(self.open_google)
        self.list_downloads_button.clicked.connect(self.list_downloads)
        self.start_reminder_watch_button.clicked.connect(self.start_reminder_watch)
        self.stop_reminder_watch_button.clicked.connect(self.stop_reminder_watch)

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
        self.start_voice_loop_action = QAction("Start Voice Loop", self)
        self.start_voice_loop_action.triggered.connect(self.start_voice_loop)
        self.stop_voice_loop_action = QAction("Stop Voice Loop", self)
        self.stop_voice_loop_action.triggered.connect(self.stop_voice_loop)
        check_reminders_action = QAction("Check Reminders", self)
        check_reminders_action.triggered.connect(self.check_reminders)
        self.notification_test_action = QAction("Test Notification", self)
        self.notification_test_action.triggered.connect(self.test_notification)
        self.launch_notepad_action = QAction("Launch Notepad", self)
        self.launch_notepad_action.triggered.connect(self.launch_notepad)
        self.open_google_action = QAction("Open Google", self)
        self.open_google_action.triggered.connect(self.open_google)
        self.list_downloads_action = QAction("List Downloads", self)
        self.list_downloads_action.triggered.connect(self.list_downloads)
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
        menu.addAction(self.launch_notepad_action)
        menu.addAction(self.open_google_action)
        menu.addAction(self.list_downloads_action)
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

        self.command_input.clear()
        self._append_message("You", command)
        self.set_status(AssistantStatus.THINKING)

        try:
            response = self.assistant.handle_command(command)
            self._append_message("Jarvis", response.text)
            self.set_status(AssistantStatus.SPEAKING if response.accepted else AssistantStatus.ERROR)
        except Exception as exc:  # pragma: no cover - defensive GUI boundary
            self._append_message("Jarvis", f"Phase 1 error: {exc}")
            self.set_status(AssistantStatus.ERROR)
            return

        QTimer.singleShot(1200, lambda: self.set_status(AssistantStatus.SLEEPING))

    def run_microphone_test(self) -> None:
        self._append_message("Jarvis", "Running a short local microphone test...")
        self.set_status(AssistantStatus.LISTENING)
        QApplication.processEvents()

        report = self.audio_diagnostics.run_full_check()
        self._append_message("Jarvis", format_microphone_test_summary(report))
        if report.microphone_test and report.microphone_test.stream_opened:
            self.set_status(AssistantStatus.SPEAKING)
        else:
            self.set_status(AssistantStatus.ERROR)

        QTimer.singleShot(1600, lambda: self.set_status(AssistantStatus.SLEEPING))

    def run_voice_command_test(self) -> None:
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

    def check_reminders(self) -> None:
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
            return

        QTimer.singleShot(1200, lambda: self.set_status(AssistantStatus.SLEEPING))

    def test_notification(self) -> None:
        self._append_message("Jarvis", "Testing notification...")
        self.notification_result_value.setText("Checking")
        self.set_status(AssistantStatus.THINKING)
        QApplication.processEvents()

        try:
            result = NotificationService(self.settings).send_notification("Jarvis", "Hello from Jarvis")
            self._append_message("Jarvis", format_notification_check_report(result))
            self.notification_result_value.setText("Delivered" if result.delivered else "Unavailable")
            self.set_status(AssistantStatus.SPEAKING if result.delivered else AssistantStatus.ERROR)
        except Exception as exc:  # pragma: no cover - defensive GUI boundary
            self._append_message("Jarvis", f"Notification test failed: {exc}")
            self.notification_result_value.setText("Error")
            self.set_status(AssistantStatus.ERROR)
            return

        QTimer.singleShot(1200, lambda: self.set_status(AssistantStatus.SLEEPING))

    def launch_notepad(self) -> None:
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
            return

        QTimer.singleShot(1200, lambda: self.set_status(AssistantStatus.SLEEPING))

    def open_google(self) -> None:
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
            return

        QTimer.singleShot(1200, lambda: self.set_status(AssistantStatus.SLEEPING))

    def list_downloads(self) -> None:
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
            return

        QTimer.singleShot(1200, lambda: self.set_status(AssistantStatus.SLEEPING))

    def start_reminder_watch(self) -> None:
        if self.reminder_watch_thread is not None and self.reminder_watch_thread.is_alive():
            self._append_message("Jarvis", "Reminder watch is already running.")
            return

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
        self.voice_loop_event_timer.start(250)
        self.voice_loop_thread.start()

    def stop_voice_loop(self) -> None:
        if self.voice_loop_runner is None:
            self._append_message("Jarvis", "Voice loop is not running.")
            self._set_voice_loop_running(False)
            return

        self._append_message("Jarvis", "Stopping voice loop...")
        self.voice_loop_runner.request_stop()

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
                status = self.voice_loop_events.get_nowait()
            except Empty:
                break
            self._handle_voice_loop_status(status)

        if self.voice_loop_thread is not None and not self.voice_loop_thread.is_alive():
            self._set_voice_loop_running(False)
            self.voice_loop_event_timer.stop()
            self.voice_loop_runner = None
            self.voice_loop_thread = None

    def _handle_voice_loop_status(self, status: str) -> None:
        status_map = {
            VOICE_LOOP_STARTED_MESSAGE: AssistantStatus.SLEEPING,
            "Sleeping": AssistantStatus.SLEEPING,
            "Listening for wake phrase": AssistantStatus.LISTENING,
            "Wake detected": AssistantStatus.WAKE_DETECTED,
            COMMAND_PROMPT: AssistantStatus.WAKE_DETECTED,
            LISTENING_FOR_COMMAND_PROMPT: AssistantStatus.LISTENING,
            "Thinking": AssistantStatus.THINKING,
            "Speaking": AssistantStatus.SPEAKING,
            RETURNING_TO_SLEEP_MESSAGE: AssistantStatus.SLEEPING,
            "I didn't catch that.": AssistantStatus.SLEEPING,
            STOP_COMMAND_DETECTED_MESSAGE: AssistantStatus.SLEEPING,
            VOICE_LOOP_STOPPED_MESSAGE: AssistantStatus.SLEEPING,
        }
        if status.startswith("Last recognized command:"):
            command_text = status.split(":", 1)[1].strip() or "None"
            self.voice_loop_last_command_value.setText(command_text)
            self.voice_loop_status_value.setText("No command detected" if command_text == "<empty>" else "Command received")
            self._append_message("Jarvis", status)
            return
        if status.startswith("Last Jarvis response:"):
            self.voice_loop_last_response_value.setText(status.split(":", 1)[1].strip() or "None")
            self.voice_loop_status_value.setText("Response ready")
            self._append_message("Jarvis", status)
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
        if self.start_voice_loop_action is not None:
            self.start_voice_loop_action.setEnabled(not running)
        if self.stop_voice_loop_action is not None:
            self.stop_voice_loop_action.setEnabled(running)
        if running:
            self.voice_loop_status_value.setText("Running")
        elif self.voice_loop_runner is None:
            self.voice_loop_status_value.setText("Idle")

    def _set_reminder_watch_running(self, running: bool) -> None:
        self.start_reminder_watch_button.setEnabled(not running)
        self.stop_reminder_watch_button.setEnabled(running)
        if self.start_reminder_watch_action is not None:
            self.start_reminder_watch_action.setEnabled(not running)
        if self.stop_reminder_watch_action is not None:
            self.stop_reminder_watch_action.setEnabled(running)
        if running:
            self.reminder_watch_status_value.setText("Running")
        elif self.reminder_watch_runner is None:
            self.reminder_watch_status_value.setText("Idle")

    def set_status(self, status: AssistantStatus) -> None:
        self.status = status
        self.status_label.setText(status.value)
        color = STATUS_COLORS[status]
        self.status_label.setStyleSheet(
            f"background: rgba(37, 99, 235, 70); border: 1px solid {color}; color: #dff9ff;"
        )
        self.orb.set_status(status)

    def _append_message(self, speaker: str, message: str) -> None:
        self.transcript.append(f"\n{speaker}: {message}")

    def request_quit(self) -> None:
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
