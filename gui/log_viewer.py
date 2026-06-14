from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from config.settings import AppSettings
from diagnostics.logs import format_log_tail_report, format_logs_list_report, list_log_files, tail_log


class LogViewerWindow(QDialog):
    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Jarvis Log Viewer")
        self.setModal(True)
        self.setMinimumSize(760, 520)

        self.log_list = QListWidget(self)
        self.log_display = QPlainTextEdit(self)
        self.log_display.setReadOnly(True)
        self.lines_spin = QSpinBox(self)
        self.lines_spin.setRange(10, 5000)
        self.lines_spin.setValue(100)
        self.lines_spin.setSingleStep(25)
        self.refresh_button = QPushButton("Refresh")
        self.clear_button = QPushButton("Clear Display")
        self.status_label = QLabel("")

        self._build_ui()
        self.refresh_logs()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        title = QLabel("Log Viewer")
        title.setObjectName("title")
        subtitle = QLabel("Read logs from the configured logs directory only. Secrets are redacted in the display.")
        subtitle.setObjectName("sectionNote")
        root.addWidget(title)
        root.addWidget(subtitle)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Tail lines"))
        controls.addWidget(self.lines_spin)
        controls.addWidget(self.refresh_button)
        controls.addWidget(self.clear_button)
        controls.addStretch(1)
        root.addLayout(controls)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(self.log_list)
        splitter.addWidget(self.log_display)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        root.addWidget(splitter, stretch=1)

        root.addWidget(self.status_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.close)
        root.addWidget(buttons)

        self.refresh_button.clicked.connect(self.refresh_logs)
        self.clear_button.clicked.connect(self.clear_display)
        self.log_list.currentTextChanged.connect(self.show_selected_log)

    def refresh_logs(self) -> None:
        report = list_log_files(self.settings)
        current_name = self.log_list.currentItem().text() if self.log_list.currentItem() is not None else ""
        self.log_list.blockSignals(True)
        self.log_list.clear()
        for item in report.items:
            self.log_list.addItem(item.name)
        self.log_list.blockSignals(False)
        self.status_label.setText(format_logs_list_report(report))
        if current_name and self._find_row(current_name) >= 0:
            self.log_list.setCurrentRow(self._find_row(current_name))
        elif self.log_list.count() > 0:
            self.log_list.setCurrentRow(0)
        else:
            self.log_display.setPlainText("No log files found.")

    def clear_display(self) -> None:
        self.log_display.clear()

    def show_selected_log(self, log_name: str) -> None:
        if not log_name:
            return
        report = tail_log(self.settings, log_name, lines=self.lines_spin.value())
        self.status_label.setText(
            f"Logs dir: {report.logs_dir} | {report.log_name} | {'ready' if report.is_successful else 'blocked'}"
        )
        self.log_display.setPlainText(format_log_tail_report(report))

    def _find_row(self, log_name: str) -> int:
        for index in range(self.log_list.count()):
            if self.log_list.item(index).text() == log_name:
                return index
        return -1
