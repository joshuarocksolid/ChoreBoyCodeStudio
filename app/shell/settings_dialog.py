"""Qt settings dialog for editor/intelligence preferences."""

from __future__ import annotations

from PySide2.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFontComboBox,
    QFormLayout,
    QGroupBox,
    QSpinBox,
    QVBoxLayout,
)

from PySide2.QtGui import QFont

from app.shell.settings_models import EditorSettingsSnapshot


class SettingsDialog(QDialog):
    """Simple settings editor for core editor/intelligence preferences."""

    def __init__(self, snapshot: EditorSettingsSnapshot, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(460, 480)

        layout = QVBoxLayout(self)

        appearance_group = QGroupBox("Appearance")
        appearance_form = QFormLayout(appearance_group)
        self._theme_mode_input = QComboBox(appearance_group)
        self._theme_mode_input.addItems(["System", "Light", "Dark"])
        _mode_to_index = {"system": 0, "light": 1, "dark": 2}
        self._theme_mode_input.setCurrentIndex(_mode_to_index.get(snapshot.theme_mode, 0))
        appearance_form.addRow("Theme", self._theme_mode_input)
        layout.addWidget(appearance_group)

        output_group = QGroupBox("Output")
        output_form = QFormLayout(output_group)
        self._auto_open_console_on_run_output_input = QCheckBox(output_group)
        self._auto_open_console_on_run_output_input.setChecked(snapshot.auto_open_console_on_run_output)
        output_form.addRow("Auto-open Console on run output", self._auto_open_console_on_run_output_input)
        self._auto_open_problems_on_run_failure_input = QCheckBox(output_group)
        self._auto_open_problems_on_run_failure_input.setChecked(snapshot.auto_open_problems_on_run_failure)
        output_form.addRow("Auto-open Problems on run failure", self._auto_open_problems_on_run_failure_input)
        layout.addWidget(output_group)

        editor_group = QGroupBox("Editor")
        editor_form = QFormLayout(editor_group)
        self._tab_width_input = QSpinBox(editor_group)
        self._tab_width_input.setRange(2, 16)
        self._tab_width_input.setValue(snapshot.tab_width)
        editor_form.addRow("Tab width", self._tab_width_input)

        self._font_family_input = QFontComboBox(editor_group)
        self._font_family_input.setCurrentFont(QFont(snapshot.font_family))
        editor_form.addRow("Font family", self._font_family_input)

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

        self._format_on_save_input = QCheckBox(editor_group)
        self._format_on_save_input.setChecked(snapshot.format_on_save)
        editor_form.addRow("Format on save", self._format_on_save_input)

        self._trim_trailing_whitespace_on_save_input = QCheckBox(editor_group)
        self._trim_trailing_whitespace_on_save_input.setChecked(snapshot.trim_trailing_whitespace_on_save)
        editor_form.addRow("Trim trailing whitespace on save", self._trim_trailing_whitespace_on_save_input)

        self._insert_final_newline_on_save_input = QCheckBox(editor_group)
        self._insert_final_newline_on_save_input.setChecked(snapshot.insert_final_newline_on_save)
        editor_form.addRow("Insert final newline on save", self._insert_final_newline_on_save_input)
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

        self._diagnostics_enabled_input = QCheckBox(intelligence_group)
        self._diagnostics_enabled_input.setChecked(snapshot.diagnostics_enabled)
        intelligence_form.addRow("Enable diagnostics", self._diagnostics_enabled_input)

        self._diagnostics_realtime_input = QCheckBox(intelligence_group)
        self._diagnostics_realtime_input.setChecked(snapshot.diagnostics_realtime)
        intelligence_form.addRow("Realtime diagnostics", self._diagnostics_realtime_input)

        self._quick_fixes_enabled_input = QCheckBox(intelligence_group)
        self._quick_fixes_enabled_input.setChecked(snapshot.quick_fixes_enabled)
        intelligence_form.addRow("Enable quick fixes", self._quick_fixes_enabled_input)

        self._quick_fix_multifile_preview_input = QCheckBox(intelligence_group)
        self._quick_fix_multifile_preview_input.setChecked(snapshot.quick_fix_require_preview_for_multifile)
        intelligence_form.addRow("Preview required for multi-file fixes", self._quick_fix_multifile_preview_input)

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
            font_family=self._font_family_input.currentFont().family(),
            indent_style=str(self._indent_style_input.currentText()),
            indent_size=int(self._indent_size_input.value()),
            detect_indentation_from_file=self._detect_indentation_input.isChecked(),
            format_on_save=self._format_on_save_input.isChecked(),
            trim_trailing_whitespace_on_save=self._trim_trailing_whitespace_on_save_input.isChecked(),
            insert_final_newline_on_save=self._insert_final_newline_on_save_input.isChecked(),
            completion_enabled=self._completion_enabled_input.isChecked(),
            completion_auto_trigger=self._completion_auto_trigger_input.isChecked(),
            completion_min_chars=int(self._completion_min_chars_input.value()),
            diagnostics_enabled=self._diagnostics_enabled_input.isChecked(),
            diagnostics_realtime=self._diagnostics_realtime_input.isChecked(),
            quick_fixes_enabled=self._quick_fixes_enabled_input.isChecked(),
            quick_fix_require_preview_for_multifile=self._quick_fix_multifile_preview_input.isChecked(),
            cache_enabled=self._cache_enabled_input.isChecked(),
            incremental_indexing=self._incremental_indexing_input.isChecked(),
            metrics_logging_enabled=self._metrics_logging_input.isChecked(),
            force_full_reindex_on_open=self._force_reindex_on_open_input.isChecked(),
            theme_mode=["system", "light", "dark"][self._theme_mode_input.currentIndex()],
            auto_open_console_on_run_output=self._auto_open_console_on_run_output_input.isChecked(),
            auto_open_problems_on_run_failure=self._auto_open_problems_on_run_failure_input.isChecked(),
        )
