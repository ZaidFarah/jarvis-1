from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from config.settings import AppSettings
from jarvis_runtime.settings_editor import SAFE_SETTING_SPECS, SafeSettingsWriteResult, save_safe_settings


@dataclass(frozen=True)
class SettingsSaveOutcome:
    result: SafeSettingsWriteResult
    updated_fields: tuple[str, ...]


class SettingsWindow(QDialog):
    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.field_widgets: dict[str, QWidget] = {}
        self.save_outcome: SettingsSaveOutcome | None = None

        self.setWindowTitle("Jarvis Settings")
        self.setModal(True)
        self.setMinimumWidth(560)
        self._build_ui()
        self._load_values()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        title = QLabel("Safe Settings")
        title.setObjectName("title")
        subtitle = QLabel("Only non-secret, user-editable settings are shown here.")
        subtitle.setObjectName("sectionNote")
        root.addWidget(title)
        root.addWidget(subtitle)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget(scroll)
        form = QFormLayout(content)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        for spec in SAFE_SETTING_SPECS:
            widget = self._create_widget(spec)
            self.field_widgets[spec.field_name] = widget
            form.addRow(spec.label, widget)

        scroll.setWidget(content)
        root.addWidget(scroll, stretch=1)

        self.status_label = QLabel("")
        self.status_label.setObjectName("sectionNote")
        root.addWidget(self.status_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self.save_settings)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        helper_row = QHBoxLayout()
        helper_row.addStretch(1)
        root.addLayout(helper_row)

    def _create_widget(self, spec):
        if spec.kind == "boolean":
            widget = QCheckBox()
            return widget
        if spec.kind == "float":
            widget = QDoubleSpinBox()
            widget.setDecimals(spec.decimals)
            widget.setMinimum(spec.minimum if spec.minimum is not None else -1_000_000)
            widget.setMaximum(spec.maximum if spec.maximum is not None else 1_000_000)
            widget.setSingleStep(spec.step if spec.step is not None else 0.1)
            widget.setKeyboardTracking(False)
            return widget
        if spec.kind == "choice":
            widget = QComboBox()
            widget.addItems(list(spec.choices))
            return widget
        widget = QLineEdit()
        widget.setClearButtonEnabled(True)
        return widget

    def _load_values(self) -> None:
        for spec in SAFE_SETTING_SPECS:
            widget = self.field_widgets[spec.field_name]
            value = getattr(self.settings, spec.field_name)
            if spec.kind == "boolean":
                assert isinstance(widget, QCheckBox)
                widget.setChecked(bool(value))
            elif spec.kind == "float":
                assert isinstance(widget, QDoubleSpinBox)
                widget.setValue(float(value))
            elif spec.kind == "choice":
                assert isinstance(widget, QComboBox)
                current = str(value)
                if widget.findText(current) < 0:
                    widget.addItem(current)
                widget.setCurrentText(current)
            else:
                assert isinstance(widget, QLineEdit)
                widget.setText(str(value))

    def save_settings(self) -> None:
        updates = self._collect_updates()
        try:
            result = save_safe_settings(self.settings, updates)
        except Exception as exc:  # pragma: no cover - defensive GUI boundary
            QMessageBox.critical(self, "Jarvis Settings", f"Could not save settings: {exc}")
            return

        for field_name, value in updates.items():
            setattr(self.settings, field_name, value)

        self.save_outcome = SettingsSaveOutcome(
            result=result,
            updated_fields=tuple(updates.keys()),
        )
        self.status_label.setText(f"Saved safe settings to {result.env_path}")
        self.accept()

    def _collect_updates(self) -> dict[str, object]:
        updates: dict[str, object] = {}
        for spec in SAFE_SETTING_SPECS:
            widget = self.field_widgets[spec.field_name]
            if spec.kind == "boolean":
                assert isinstance(widget, QCheckBox)
                updates[spec.field_name] = widget.isChecked()
            elif spec.kind == "float":
                assert isinstance(widget, QDoubleSpinBox)
                updates[spec.field_name] = float(widget.value())
            elif spec.kind == "choice":
                assert isinstance(widget, QComboBox)
                updates[spec.field_name] = widget.currentText().strip().lower()
            else:
                assert isinstance(widget, QLineEdit)
                updates[spec.field_name] = widget.text().strip()
        return updates
