"""Qt settings dialog for editor/intelligence preferences."""

from __future__ import annotations

from PySide2.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHeaderView,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QFontComboBox,
    QFormLayout,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from PySide2.QtGui import QFont
from PySide2.QtCore import Qt
from PySide2.QtGui import QKeySequence

from app.shell.settings_models import EditorSettingsSnapshot
from app.shell.shortcut_preferences import (
    SHORTCUT_COMMANDS,
    build_effective_shortcut_map,
    default_shortcut_map,
    find_shortcut_conflicts,
    normalize_shortcut,
)


class SettingsDialog(QDialog):
    """Simple settings editor for core editor/intelligence preferences."""

    def __init__(self, snapshot: EditorSettingsSnapshot, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(860, 640)
        self._shortcut_editors: dict[str, QKeySequenceEdit] = {}
        self._shortcut_rows: dict[str, int] = {}

        layout = QVBoxLayout(self)
        tabs = QTabWidget(self)
        layout.addWidget(tabs)

        general_tab = QWidget(tabs)
        general_layout = QVBoxLayout(general_tab)
        tabs.addTab(general_tab, "General")
        appearance_group = QGroupBox("Appearance")
        appearance_form = QFormLayout(appearance_group)
        self._theme_mode_input = QComboBox(appearance_group)
        self._theme_mode_input.addItems(["System", "Light", "Dark"])
        _mode_to_index = {"system": 0, "light": 1, "dark": 2}
        self._theme_mode_input.setCurrentIndex(_mode_to_index.get(snapshot.theme_mode, 0))
        appearance_form.addRow("Theme", self._theme_mode_input)
        general_layout.addWidget(appearance_group)

        output_group = QGroupBox("Output")
        output_form = QFormLayout(output_group)
        self._auto_open_console_on_run_output_input = QCheckBox(output_group)
        self._auto_open_console_on_run_output_input.setChecked(snapshot.auto_open_console_on_run_output)
        output_form.addRow("Auto-open Run Log on run output", self._auto_open_console_on_run_output_input)
        self._auto_open_problems_on_run_failure_input = QCheckBox(output_group)
        self._auto_open_problems_on_run_failure_input.setChecked(snapshot.auto_open_problems_on_run_failure)
        output_form.addRow("Auto-open Problems on run failure", self._auto_open_problems_on_run_failure_input)
        general_layout.addWidget(output_group)

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
        general_layout.addWidget(editor_group)

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
        general_layout.addWidget(intelligence_group)
        general_layout.addStretch(1)

        keybindings_tab = QWidget(tabs)
        keybindings_layout = QVBoxLayout(keybindings_tab)
        tabs.addTab(keybindings_tab, "Keybindings")

        self._shortcut_search_input = QLineEdit(keybindings_tab)
        self._shortcut_search_input.setPlaceholderText("Search commands...")
        self._shortcut_search_input.textChanged.connect(self._filter_shortcut_rows)
        keybindings_layout.addWidget(self._shortcut_search_input)

        self._shortcut_conflict_label = QLabel(keybindings_tab)
        self._shortcut_conflict_label.setStyleSheet("color: #C92A2A;")
        self._shortcut_conflict_label.setWordWrap(True)
        self._shortcut_conflict_label.setVisible(False)
        keybindings_layout.addWidget(self._shortcut_conflict_label)

        self._shortcut_table = QTableWidget(0, 4, keybindings_tab)
        self._shortcut_table.setHorizontalHeaderLabels(["Command", "Shortcut", "Default", "Reset"])
        self._shortcut_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._shortcut_table.setSelectionMode(QAbstractItemView.NoSelection)
        self._shortcut_table.setFocusPolicy(Qt.NoFocus)
        self._shortcut_table.verticalHeader().setVisible(False)
        header = self._shortcut_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        keybindings_layout.addWidget(self._shortcut_table, 1)
        self._populate_shortcut_table(snapshot)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._ok_button = buttons.button(QDialogButtonBox.Ok)
        self._refresh_shortcut_conflicts()

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
            shortcut_overrides=self._shortcut_overrides_snapshot(),
        )

    def _populate_shortcut_table(self, snapshot: EditorSettingsSnapshot) -> None:
        defaults = default_shortcut_map()
        effective = build_effective_shortcut_map(snapshot.shortcut_overrides)
        self._shortcut_table.setRowCount(len(SHORTCUT_COMMANDS))
        for row_index, command in enumerate(SHORTCUT_COMMANDS):
            self._shortcut_rows[command.action_id] = row_index
            command_item = QTableWidgetItem(f"{command.category} / {command.label}")
            command_item.setData(Qt.UserRole, command.action_id)
            self._shortcut_table.setItem(row_index, 0, command_item)

            editor = QKeySequenceEdit(self._shortcut_table)
            current_shortcut = effective.get(command.action_id, "")
            if current_shortcut:
                editor.setKeySequence(QKeySequence(current_shortcut))
            editor.keySequenceChanged.connect(
                lambda _sequence, action_id=command.action_id: self._handle_shortcut_changed(action_id)
            )
            self._shortcut_editors[command.action_id] = editor
            self._shortcut_table.setCellWidget(row_index, 1, editor)

            default_item = QTableWidgetItem(defaults.get(command.action_id, ""))
            self._shortcut_table.setItem(row_index, 2, default_item)

            reset_button = QPushButton("Reset", self._shortcut_table)
            reset_button.clicked.connect(
                lambda _checked=False, action_id=command.action_id: self._handle_reset_shortcut(action_id)
            )
            self._shortcut_table.setCellWidget(row_index, 3, reset_button)

    def _handle_reset_shortcut(self, action_id: str) -> None:
        editor = self._shortcut_editors.get(action_id)
        if editor is None:
            return
        default_shortcuts = default_shortcut_map()
        editor.setKeySequence(QKeySequence(default_shortcuts.get(action_id, "")))
        self._refresh_shortcut_conflicts()

    def _handle_shortcut_changed(self, _action_id: str) -> None:
        self._refresh_shortcut_conflicts()

    def _filter_shortcut_rows(self, query: str) -> None:
        lowered = query.strip().lower()
        for action_id, row_index in self._shortcut_rows.items():
            item = self._shortcut_table.item(row_index, 0)
            if item is None:
                continue
            text = item.text().lower()
            should_show = not lowered or lowered in text or lowered in action_id.lower()
            self._shortcut_table.setRowHidden(row_index, not should_show)

    def _current_shortcut_map(self) -> dict[str, str]:
        current: dict[str, str] = {}
        for action_id, editor in self._shortcut_editors.items():
            current[action_id] = normalize_shortcut(editor.keySequence().toString())
        return current

    def _refresh_shortcut_conflicts(self) -> None:
        conflicts = find_shortcut_conflicts(self._current_shortcut_map())
        if conflicts:
            details = [f"{shortcut}: {', '.join(action_ids)}" for shortcut, action_ids in sorted(conflicts.items())]
            self._shortcut_conflict_label.setText("Conflicting shortcuts:\n" + "\n".join(details[:4]))
            self._shortcut_conflict_label.setVisible(True)
            if self._ok_button is not None:
                self._ok_button.setEnabled(False)
            return
        self._shortcut_conflict_label.clear()
        self._shortcut_conflict_label.setVisible(False)
        if self._ok_button is not None:
            self._ok_button.setEnabled(True)

    def _shortcut_overrides_snapshot(self) -> dict[str, str]:
        overrides: dict[str, str] = {}
        defaults = default_shortcut_map()
        for action_id, current_shortcut in self._current_shortcut_map().items():
            default_shortcut = normalize_shortcut(defaults.get(action_id, ""))
            if current_shortcut == default_shortcut:
                continue
            overrides[action_id] = current_shortcut if current_shortcut else ""
        return overrides
