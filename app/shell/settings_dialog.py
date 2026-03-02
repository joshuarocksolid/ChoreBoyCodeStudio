"""Qt settings dialog for editor/intelligence preferences."""

from __future__ import annotations

from PySide2.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QSpinBox,
    QVBoxLayout,
)

from app.shell.settings_models import EditorSettingsSnapshot


class SettingsDialog(QDialog):
    """Simple settings editor for core editor/intelligence preferences."""

    def __init__(self, snapshot: EditorSettingsSnapshot, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(420, 360)

        layout = QVBoxLayout(self)

        editor_group = QGroupBox("Editor")
        editor_form = QFormLayout(editor_group)
        self._tab_width_input = QSpinBox(editor_group)
        self._tab_width_input.setRange(2, 16)
        self._tab_width_input.setValue(snapshot.tab_width)
        editor_form.addRow("Tab width", self._tab_width_input)

        self._font_size_input = QSpinBox(editor_group)
        self._font_size_input.setRange(8, 28)
        self._font_size_input.setValue(snapshot.font_size)
        editor_form.addRow("Font size", self._font_size_input)

        self._indent_style_input = QComboBox(editor_group)
        self._indent_style_input.addItems(["spaces", "tabs"])
        self._indent_style_input.setCurrentText(snapshot.indent_style)
        editor_form.addRow("Indent style", self._indent_style_input)

        self._indent_size_input = QSpinBox(editor_group)
        self._indent_size_input.setRange(1, 16)
        self._indent_size_input.setValue(snapshot.indent_size)
        editor_form.addRow("Indent size", self._indent_size_input)

        self._detect_indentation_input = QCheckBox(editor_group)
        self._detect_indentation_input.setChecked(snapshot.detect_indentation_from_file)
        editor_form.addRow("Detect indentation from file", self._detect_indentation_input)
        layout.addWidget(editor_group)

        intelligence_group = QGroupBox("Intelligence")
        intelligence_form = QFormLayout(intelligence_group)
        self._completion_enabled_input = QCheckBox(intelligence_group)
        self._completion_enabled_input.setChecked(snapshot.completion_enabled)
        intelligence_form.addRow("Enable completion", self._completion_enabled_input)

        self._completion_auto_trigger_input = QCheckBox(intelligence_group)
        self._completion_auto_trigger_input.setChecked(snapshot.completion_auto_trigger)
        intelligence_form.addRow("Auto-trigger completion", self._completion_auto_trigger_input)

        self._completion_min_chars_input = QSpinBox(intelligence_group)
        self._completion_min_chars_input.setRange(1, 8)
        self._completion_min_chars_input.setValue(snapshot.completion_min_chars)
        intelligence_form.addRow("Completion min chars", self._completion_min_chars_input)

        self._cache_enabled_input = QCheckBox(intelligence_group)
        self._cache_enabled_input.setChecked(snapshot.cache_enabled)
        intelligence_form.addRow("Enable intelligence cache", self._cache_enabled_input)

        self._incremental_indexing_input = QCheckBox(intelligence_group)
        self._incremental_indexing_input.setChecked(snapshot.incremental_indexing)
        intelligence_form.addRow("Incremental indexing", self._incremental_indexing_input)

        self._metrics_logging_input = QCheckBox(intelligence_group)
        self._metrics_logging_input.setChecked(snapshot.metrics_logging_enabled)
        intelligence_form.addRow("Metrics logging", self._metrics_logging_input)

        self._force_reindex_on_open_input = QCheckBox(intelligence_group)
        self._force_reindex_on_open_input.setChecked(snapshot.force_full_reindex_on_open)
        intelligence_form.addRow("Force full reindex on open", self._force_reindex_on_open_input)
        layout.addWidget(intelligence_group)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def snapshot(self) -> EditorSettingsSnapshot:
        """Return settings snapshot from current dialog values."""
        return EditorSettingsSnapshot(
            tab_width=int(self._tab_width_input.value()),
            font_size=int(self._font_size_input.value()),
            indent_style=str(self._indent_style_input.currentText()),
            indent_size=int(self._indent_size_input.value()),
            detect_indentation_from_file=self._detect_indentation_input.isChecked(),
            completion_enabled=self._completion_enabled_input.isChecked(),
            completion_auto_trigger=self._completion_auto_trigger_input.isChecked(),
            completion_min_chars=int(self._completion_min_chars_input.value()),
            cache_enabled=self._cache_enabled_input.isChecked(),
            incremental_indexing=self._incremental_indexing_input.isChecked(),
            metrics_logging_enabled=self._metrics_logging_input.isChecked(),
            force_full_reindex_on_open=self._force_reindex_on_open_input.isChecked(),
        )
