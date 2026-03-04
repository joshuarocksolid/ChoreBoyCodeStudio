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
    QColorDialog,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from PySide2.QtGui import QColor, QFont
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
from app.shell.syntax_color_preferences import (
    SYNTAX_COLOR_TOKENS,
    THEME_DARK,
    THEME_LIGHT,
    normalize_hex_color,
)
from app.editors.syntax_engine import DEFAULT_DARK_PALETTE, DEFAULT_LIGHT_PALETTE
from app.intelligence.lint_profile import (
    LINT_RULE_DEFINITIONS,
    LINT_SEVERITY_ERROR,
    LINT_SEVERITY_INFO,
    LINT_SEVERITY_WARNING,
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
        self._syntax_color_inputs: dict[str, QLineEdit] = {}
        self._syntax_color_row_by_token: dict[str, int] = {}
        self._syntax_color_overrides_by_theme: dict[str, dict[str, str]] = {
            THEME_LIGHT: dict(snapshot.syntax_color_overrides_light),
            THEME_DARK: dict(snapshot.syntax_color_overrides_dark),
        }
        self._lint_rule_overrides: dict[str, dict[str, object]] = {
            code: dict(value) for code, value in snapshot.lint_rule_overrides.items()
        }
        self._lint_enabled_inputs: dict[str, QCheckBox] = {}
        self._lint_severity_inputs: dict[str, QComboBox] = {}
        self._active_syntax_theme_key = THEME_LIGHT
        self._has_shortcut_conflicts = False
        self._has_invalid_syntax_colors = False

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

        syntax_tab = QWidget(tabs)
        syntax_layout = QVBoxLayout(syntax_tab)
        tabs.addTab(syntax_tab, "Syntax Colors")

        self._syntax_theme_input = QComboBox(syntax_tab)
        self._syntax_theme_input.addItem("Light Theme", THEME_LIGHT)
        self._syntax_theme_input.addItem("Dark Theme", THEME_DARK)
        self._syntax_theme_input.currentIndexChanged.connect(self._handle_syntax_theme_changed)
        syntax_layout.addWidget(self._syntax_theme_input)

        self._syntax_validation_label = QLabel(syntax_tab)
        self._syntax_validation_label.setStyleSheet("color: #C92A2A;")
        self._syntax_validation_label.setWordWrap(True)
        self._syntax_validation_label.setVisible(False)
        syntax_layout.addWidget(self._syntax_validation_label)

        self._syntax_color_table = QTableWidget(0, 4, syntax_tab)
        self._syntax_color_table.setHorizontalHeaderLabels(["Token", "Color", "Pick", "Reset"])
        self._syntax_color_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._syntax_color_table.setSelectionMode(QAbstractItemView.NoSelection)
        self._syntax_color_table.setFocusPolicy(Qt.NoFocus)
        self._syntax_color_table.verticalHeader().setVisible(False)
        syntax_header = self._syntax_color_table.horizontalHeader()
        syntax_header.setSectionResizeMode(0, QHeaderView.Stretch)
        syntax_header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        syntax_header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        syntax_header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        syntax_layout.addWidget(self._syntax_color_table, 1)
        self._populate_syntax_color_table(self._active_syntax_theme_key)

        linter_tab = QWidget(tabs)
        linter_layout = QVBoxLayout(linter_tab)
        tabs.addTab(linter_tab, "Linter")

        self._linter_table = QTableWidget(0, 5, linter_tab)
        self._linter_table.setHorizontalHeaderLabels(["Code", "Rule", "Enabled", "Severity", "Reset"])
        self._linter_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._linter_table.setSelectionMode(QAbstractItemView.NoSelection)
        self._linter_table.setFocusPolicy(Qt.NoFocus)
        self._linter_table.verticalHeader().setVisible(False)
        linter_header = self._linter_table.horizontalHeader()
        linter_header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        linter_header.setSectionResizeMode(1, QHeaderView.Stretch)
        linter_header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        linter_header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        linter_header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        linter_layout.addWidget(self._linter_table, 1)
        self._populate_linter_table()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._ok_button = buttons.button(QDialogButtonBox.Ok)
        self._refresh_shortcut_conflicts()
        self._refresh_syntax_validation()
        self._refresh_validation_state()

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
            syntax_color_overrides_light=dict(self._syntax_color_overrides_by_theme.get(THEME_LIGHT, {})),
            syntax_color_overrides_dark=dict(self._syntax_color_overrides_by_theme.get(THEME_DARK, {})),
            lint_rule_overrides=self._lint_rule_overrides_snapshot(),
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
            self._has_shortcut_conflicts = True
        else:
            self._shortcut_conflict_label.clear()
            self._shortcut_conflict_label.setVisible(False)
            self._has_shortcut_conflicts = False
        self._refresh_validation_state()

    def _shortcut_overrides_snapshot(self) -> dict[str, str]:
        overrides: dict[str, str] = {}
        defaults = default_shortcut_map()
        for action_id, current_shortcut in self._current_shortcut_map().items():
            default_shortcut = normalize_shortcut(defaults.get(action_id, ""))
            if current_shortcut == default_shortcut:
                continue
            overrides[action_id] = current_shortcut if current_shortcut else ""
        return overrides

    def _syntax_defaults_for_theme(self, theme_key: str) -> dict[str, str]:
        return dict(DEFAULT_DARK_PALETTE if theme_key == THEME_DARK else DEFAULT_LIGHT_PALETTE)

    def _populate_syntax_color_table(self, theme_key: str) -> None:
        self._active_syntax_theme_key = theme_key
        self._syntax_color_inputs.clear()
        self._syntax_color_row_by_token.clear()
        defaults = self._syntax_defaults_for_theme(theme_key)
        overrides = self._syntax_color_overrides_by_theme.setdefault(theme_key, {})
        self._syntax_color_table.setRowCount(len(SYNTAX_COLOR_TOKENS))
        for row_index, token in enumerate(SYNTAX_COLOR_TOKENS):
            self._syntax_color_row_by_token[token.key] = row_index
            label_item = QTableWidgetItem(f"{token.category} / {token.label}")
            self._syntax_color_table.setItem(row_index, 0, label_item)

            color_input = QLineEdit(self._syntax_color_table)
            color_input.setPlaceholderText(defaults.get(token.key, ""))
            effective_color = overrides.get(token.key, defaults.get(token.key, ""))
            color_input.setText(effective_color)
            color_input.textEdited.connect(
                lambda _text, key=token.key: self._handle_syntax_color_text_edited(key)
            )
            self._syntax_color_inputs[token.key] = color_input
            self._syntax_color_table.setCellWidget(row_index, 1, color_input)

            pick_button = QPushButton("Pick", self._syntax_color_table)
            pick_button.clicked.connect(
                lambda _checked=False, key=token.key: self._handle_pick_syntax_color(key)
            )
            self._syntax_color_table.setCellWidget(row_index, 2, pick_button)

            reset_button = QPushButton("Reset", self._syntax_color_table)
            reset_button.clicked.connect(
                lambda _checked=False, key=token.key: self._handle_reset_syntax_color(key)
            )
            self._syntax_color_table.setCellWidget(row_index, 3, reset_button)

        self._refresh_syntax_validation()

    def _handle_syntax_theme_changed(self, _index: int) -> None:
        theme_key = str(self._syntax_theme_input.currentData())
        if theme_key not in {THEME_LIGHT, THEME_DARK}:
            theme_key = THEME_LIGHT
        self._populate_syntax_color_table(theme_key)

    def _handle_pick_syntax_color(self, token_key: str) -> None:
        input_widget = self._syntax_color_inputs.get(token_key)
        if input_widget is None:
            return
        current = normalize_hex_color(input_widget.text()) or input_widget.placeholderText()
        chosen = QColorDialog.getColor(
            initial=QColor(current if current else "#FFFFFF"),
            parent=self,
            title="Choose syntax color",
        )
        if not chosen.isValid():
            return
        input_widget.setText(chosen.name().upper())
        self._handle_syntax_color_text_edited(token_key)

    def _handle_reset_syntax_color(self, token_key: str) -> None:
        defaults = self._syntax_defaults_for_theme(self._active_syntax_theme_key)
        overrides = self._syntax_color_overrides_by_theme.setdefault(self._active_syntax_theme_key, {})
        overrides.pop(token_key, None)
        input_widget = self._syntax_color_inputs.get(token_key)
        if input_widget is not None:
            input_widget.setText(defaults.get(token_key, ""))
        self._refresh_syntax_validation()

    def _handle_syntax_color_text_edited(self, token_key: str) -> None:
        input_widget = self._syntax_color_inputs.get(token_key)
        if input_widget is None:
            return
        overrides = self._syntax_color_overrides_by_theme.setdefault(self._active_syntax_theme_key, {})
        defaults = self._syntax_defaults_for_theme(self._active_syntax_theme_key)
        raw_text = input_widget.text().strip()
        if not raw_text:
            overrides.pop(token_key, None)
            input_widget.setText(defaults.get(token_key, ""))
            self._refresh_syntax_validation()
            return
        normalized = normalize_hex_color(input_widget.text())
        if normalized is None:
            self._refresh_syntax_validation()
            return
        if normalized == defaults.get(token_key):
            overrides.pop(token_key, None)
        else:
            overrides[token_key] = normalized
        input_widget.setText(normalized)
        self._refresh_syntax_validation()

    def _refresh_syntax_validation(self) -> None:
        invalid_entries: list[str] = []
        for token_key, input_widget in self._syntax_color_inputs.items():
            if not input_widget.text().strip():
                input_widget.setStyleSheet("")
                continue
            normalized = normalize_hex_color(input_widget.text())
            if normalized is None:
                input_widget.setStyleSheet("border: 1px solid #C92A2A;")
                invalid_entries.append(token_key)
            else:
                input_widget.setStyleSheet("")
        if invalid_entries:
            preview = ", ".join(invalid_entries[:5])
            self._syntax_validation_label.setText(
                f"Invalid syntax colors for: {preview}. Use #RRGGBB format."
            )
            self._syntax_validation_label.setVisible(True)
            self._has_invalid_syntax_colors = True
        else:
            self._syntax_validation_label.clear()
            self._syntax_validation_label.setVisible(False)
            self._has_invalid_syntax_colors = False
        self._refresh_validation_state()

    def _populate_linter_table(self) -> None:
        self._lint_enabled_inputs.clear()
        self._lint_severity_inputs.clear()
        self._linter_table.setRowCount(len(LINT_RULE_DEFINITIONS))
        severity_values = [LINT_SEVERITY_ERROR, LINT_SEVERITY_WARNING, LINT_SEVERITY_INFO]
        for row_index, definition in enumerate(LINT_RULE_DEFINITIONS):
            code_item = QTableWidgetItem(definition.code)
            self._linter_table.setItem(row_index, 0, code_item)
            rule_item = QTableWidgetItem(definition.title)
            self._linter_table.setItem(row_index, 1, rule_item)

            override_payload = self._lint_rule_overrides.get(definition.code, {})
            enabled_value = bool(override_payload.get("enabled", definition.default_enabled))
            enabled_input = QCheckBox(self._linter_table)
            enabled_input.setChecked(enabled_value)
            enabled_input.setEnabled(definition.allow_disable)
            enabled_input.stateChanged.connect(
                lambda _state, code=definition.code: self._handle_lint_enabled_changed(code)
            )
            self._linter_table.setCellWidget(row_index, 2, enabled_input)
            self._lint_enabled_inputs[definition.code] = enabled_input

            severity_input = QComboBox(self._linter_table)
            for severity in severity_values:
                severity_input.addItem(severity.upper(), severity)
            severity_value = str(override_payload.get("severity", definition.default_severity))
            selected_index = severity_input.findData(severity_value)
            severity_input.setCurrentIndex(selected_index if selected_index >= 0 else 0)
            severity_input.setEnabled(definition.allow_severity_override)
            severity_input.currentIndexChanged.connect(
                lambda _idx, code=definition.code: self._handle_lint_severity_changed(code)
            )
            self._linter_table.setCellWidget(row_index, 3, severity_input)
            self._lint_severity_inputs[definition.code] = severity_input

            reset_button = QPushButton("Reset", self._linter_table)
            reset_button.clicked.connect(
                lambda _checked=False, code=definition.code: self._handle_reset_lint_rule(code)
            )
            self._linter_table.setCellWidget(row_index, 4, reset_button)

    def _handle_lint_enabled_changed(self, code: str) -> None:
        definition = next((item for item in LINT_RULE_DEFINITIONS if item.code == code), None)
        if definition is None:
            return
        enabled_input = self._lint_enabled_inputs.get(code)
        if enabled_input is None:
            return
        override = self._lint_rule_overrides.setdefault(code, {})
        if definition.allow_disable:
            override["enabled"] = enabled_input.isChecked()
        self._normalize_lint_rule_override(code)

    def _handle_lint_severity_changed(self, code: str) -> None:
        definition = next((item for item in LINT_RULE_DEFINITIONS if item.code == code), None)
        if definition is None:
            return
        severity_input = self._lint_severity_inputs.get(code)
        if severity_input is None:
            return
        override = self._lint_rule_overrides.setdefault(code, {})
        if definition.allow_severity_override:
            override["severity"] = str(severity_input.currentData())
        self._normalize_lint_rule_override(code)

    def _handle_reset_lint_rule(self, code: str) -> None:
        definition = next((item for item in LINT_RULE_DEFINITIONS if item.code == code), None)
        if definition is None:
            return
        self._lint_rule_overrides.pop(code, None)
        enabled_input = self._lint_enabled_inputs.get(code)
        if enabled_input is not None:
            enabled_input.setChecked(definition.default_enabled)
        severity_input = self._lint_severity_inputs.get(code)
        if severity_input is not None:
            index = severity_input.findData(definition.default_severity)
            severity_input.setCurrentIndex(index if index >= 0 else 0)

    def _normalize_lint_rule_override(self, code: str) -> None:
        definition = next((item for item in LINT_RULE_DEFINITIONS if item.code == code), None)
        if definition is None:
            self._lint_rule_overrides.pop(code, None)
            return
        override = self._lint_rule_overrides.get(code, {})
        normalized: dict[str, object] = {}
        enabled = override.get("enabled")
        if definition.allow_disable and isinstance(enabled, bool) and enabled != definition.default_enabled:
            normalized["enabled"] = enabled
        severity = override.get("severity")
        if (
            definition.allow_severity_override
            and isinstance(severity, str)
            and severity in {LINT_SEVERITY_ERROR, LINT_SEVERITY_WARNING, LINT_SEVERITY_INFO}
            and severity != definition.default_severity
        ):
            normalized["severity"] = severity
        if normalized:
            self._lint_rule_overrides[code] = normalized
        else:
            self._lint_rule_overrides.pop(code, None)

    def _lint_rule_overrides_snapshot(self) -> dict[str, dict[str, object]]:
        return {code: dict(value) for code, value in self._lint_rule_overrides.items()}

    def _refresh_validation_state(self) -> None:
        if self._ok_button is None:
            return
        self._ok_button.setEnabled(not (self._has_shortcut_conflicts or self._has_invalid_syntax_colors))
