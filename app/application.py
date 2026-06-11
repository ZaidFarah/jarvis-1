from __future__ import annotations

import sys
from collections.abc import Sequence

from PySide6.QtWidgets import QApplication

from assistant.core import AssistantCore
from config.settings import AppSettings, load_settings
from gui.main_window import JarvisMainWindow
from services.logging_service import configure_logging
from services.openai_service import OpenAIService


class JarvisApplication:
    """Coordinates settings, logging, assistant core, and the Qt GUI."""

    def __init__(self, argv: Sequence[str] | None = None, settings: AppSettings | None = None) -> None:
        self.argv = list(argv if argv is not None else sys.argv)
        self.settings = settings or load_settings()
        self.logger = configure_logging(self.settings)

        self.qt_app = QApplication.instance() or QApplication(self.argv)
        self.qt_app.setApplicationName(self.settings.app_name)
        self.qt_app.setOrganizationName("Jarvis")
        self.qt_app.setQuitOnLastWindowClosed(False)
        self.qt_app.aboutToQuit.connect(self.shutdown)

        self.assistant = AssistantCore(settings=self.settings, openai_service=OpenAIService(self.settings))
        self.window = JarvisMainWindow(settings=self.settings, assistant=self.assistant)

    def run(self) -> int:
        self.logger.info("Starting {}", self.settings.app_name)
        self.window.show()
        return int(self.qt_app.exec())

    def shutdown(self) -> None:
        self.logger.info("Shutting down {}", self.settings.app_name)
