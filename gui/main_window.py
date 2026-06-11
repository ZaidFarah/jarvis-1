from __future__ import annotations

from enum import Enum

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
from voice.audio_diagnostics import AudioDiagnostics, format_microphone_test_summary
from voice.voice_command_test import VoiceCommandTestRunner, format_voice_command_report


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
        self.send_button = QPushButton("Send")
        self.audio_diagnostics = AudioDiagnostics(settings)
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
        self.send_button.setObjectName("sendButton")

        input_row = QHBoxLayout()
        input_row.addWidget(self.command_input)
        input_row.addWidget(self.mic_test_button)
        input_row.addWidget(self.voice_command_button)
        input_row.addWidget(self.send_button)

        layout = QVBoxLayout(shell)
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setSpacing(16)
        layout.addLayout(title_row)
        layout.addWidget(self.orb, alignment=Qt.AlignmentFlag.AlignHCenter)
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
        exit_action = QAction("Exit Jarvis", self)
        exit_action.triggered.connect(self.request_quit)
        menu.addAction(show_action)
        menu.addAction(mic_test_action)
        menu.addAction(voice_command_action)
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
        self._allow_close = True
        self.tray_icon.hide()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._allow_close or not self.settings.minimize_to_tray:
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
