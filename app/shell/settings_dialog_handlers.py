"""Event handlers and tab population logic for SettingsDialog."""

from __future__ import annotations

from PySide2.QtCore import Qt
from PySide2.QtGui import QColor, QFont, QKeySequence
from PySide2.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidgetItem,
    QWidget,
)

from app.core import constants
from app.editors.syntax_engine import (
    DEFAULT_DARK_PALETTE,
    DEFAULT_HC_DARK_PALETTE,
    DEFAULT_HC_LIGHT_PALETTE,
    DEFAULT_LIGHT_PALETTE,
)
from app.intelligence.lint_profile import (
    LINT_RULE_DEFINITIONS,
    LINT_SEVERITY_ERROR,
    LINT_SEVERITY_INFO,
    LINT_SEVERITY_WARNING,
)
from app.project.file_excludes import DEFAULT_EXCLUDE_PATTERNS
from app.shell.settings_dialog_state import GeneralTabState
from app.shell.settings_dialog_tables import (
    finalize_settings_table_rows,
    settings_table_control_cell,
)
from app.shell.settings_models import (
    EditorSettingsSnapshot,
    SETTINGS_SCOPE_GLOBAL,
    SETTINGS_SCOPE_PROJECT,
)
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
    THEME_HC_DARK,
    THEME_HC_LIGHT,
    THEME_LIGHT,
    normalize_hex_color,
)

_VALID_SYNTAX_THEME_KEYS = frozenset({THEME_LIGHT, THEME_DARK, THEME_HC_LIGHT, THEME_HC_DARK})


class SettingsDialogHandlersMixin:
    """Mixin supplying SettingsDialog handler methods."""

    def _apply_shortcut_snapshot(self, snapshot: EditorSettingsSnapshot) -> None:
        effective = build_effective_shortcut_map(snapshot.shortcut_overrides)
        self._is_updating_shortcut_editors = True
        try:
            for action_id, editor in self._shortcut_editors.items():
                editor.setKeySequence(QKeySequence(effective.get(action_id, "")))
        finally:
            self._is_updating_shortcut_editors = False

    def _handle_scope_changed(self, selected_scope: str) -> None:
        if self._scope_input is None:
            return
        if selected_scope == SETTINGS_SCOPE_PROJECT and not self._project_scope_available:
            self._scope_input.set_selected(self._active_scope)
            return
        if selected_scope not in {SETTINGS_SCOPE_GLOBAL, SETTINGS_SCOPE_PROJECT}:
            return
        if selected_scope == self._active_scope:
            return
        self._set_scope(selected_scope, apply_snapshot=True)

    def _set_scope(self, scope: str, *, apply_snapshot: bool) -> None:
        normalized_scope = scope
        if normalized_scope == SETTINGS_SCOPE_PROJECT and not self._project_scope_available:
            normalized_scope = SETTINGS_SCOPE_GLOBAL
        if normalized_scope not in {SETTINGS_SCOPE_GLOBAL, SETTINGS_SCOPE_PROJECT}:
            normalized_scope = SETTINGS_SCOPE_GLOBAL

        if normalized_scope != self._active_scope:
            self._capture_active_scope_snapshot()
        self._active_scope = normalized_scope
        if self._scope_input is not None:
            self._scope_input.blockSignals(True)
            self._scope_input.set_selected(normalized_scope)
            self._scope_input.blockSignals(False)
        if apply_snapshot:
            snapshot = self._scope_snapshots.get(normalized_scope, self._scope_snapshots[SETTINGS_SCOPE_GLOBAL])
            self._apply_snapshot_to_controls(snapshot)
        self._apply_scope_visibility()

    def _apply_scope_visibility(self) -> None:
        is_project_scope = self._active_scope == SETTINGS_SCOPE_PROJECT and self._project_scope_available
        if self._scope_banner_label is not None:
            if is_project_scope:
                self._scope_banner_label.setText(
                    "Project overrides apply to this project only."
                )
            else:
                self._scope_banner_label.setText(
                    "Global settings apply by default across projects."
                )
        if self._appearance_group is not None:
            self._appearance_group.setVisible(not is_project_scope)
        self._enable_preview_input.setEnabled(not is_project_scope)
        if self._output_reset_to_global_btn is not None:
            self._output_reset_to_global_btn.setVisible(is_project_scope)
        if self._editor_reset_to_global_btn is not None:
            self._editor_reset_to_global_btn.setVisible(is_project_scope)
        if self._intelligence_reset_to_global_btn is not None:
            self._intelligence_reset_to_global_btn.setVisible(is_project_scope)
        if self._linter_reset_to_global_btn is not None:
            self._linter_reset_to_global_btn.setVisible(is_project_scope)
        if self._file_excludes_reset_btn is not None:
            self._file_excludes_reset_btn.setText(
                "Reset to Global" if is_project_scope else "Reset to Defaults"
            )
        if self._local_history_reset_btn is not None:
            self._local_history_reset_btn.setText(
                "Reset to Global" if is_project_scope else "Reset to Defaults"
            )

        if self._linter_provider_scope_hint is not None:
            self._linter_provider_scope_hint.setVisible(not is_project_scope)

        if self._tabs_widget is not None:
            if self._keybindings_tab_index is not None:
                self._set_tab_visible(self._keybindings_tab_index, not is_project_scope)
            if self._syntax_tab_index is not None:
                self._set_tab_visible(self._syntax_tab_index, not is_project_scope)

    def _set_tab_visible(self, index: int, visible: bool) -> None:
        if self._tabs_widget is None:
            return
        if hasattr(self._tabs_widget, "setTabVisible"):
            self._tabs_widget.setTabVisible(index, visible)
            return
        if self._tabs_widget.widget(index) is not None:
            self._tabs_widget.widget(index).setVisible(visible)

    def _handle_reset_output_group_to_global(self) -> None:
        baseline = self._scope_snapshots[SETTINGS_SCOPE_GLOBAL]
        self._auto_open_console_on_run_output_input.setChecked(baseline.auto_open_console_on_run_output)
        self._auto_open_problems_on_run_failure_input.setChecked(baseline.auto_open_problems_on_run_failure)

    def _handle_reset_editor_group_to_global(self) -> None:
        baseline = self._scope_snapshots[SETTINGS_SCOPE_GLOBAL]
        self._tab_width_input.setValue(baseline.tab_width)
        self._font_size_input.setValue(baseline.font_size)
        self._font_family_input.setCurrentFont(QFont(baseline.font_family))
        self._indent_style_input.setCurrentText(baseline.indent_style)
        self._indent_size_input.setValue(baseline.indent_size)
        self._detect_indentation_input.setChecked(baseline.detect_indentation_from_file)
        self._format_on_save_input.setChecked(baseline.format_on_save)
        self._organize_imports_on_save_input.setChecked(baseline.organize_imports_on_save)
        self._trim_trailing_whitespace_on_save_input.setChecked(baseline.trim_trailing_whitespace_on_save)
        self._insert_final_newline_on_save_input.setChecked(baseline.insert_final_newline_on_save)
        self._enable_preview_input.setChecked(baseline.enable_preview)
        self._auto_save_input.setChecked(baseline.auto_save)
        exit_behavior_index = self._exit_behavior_input.findData(baseline.exit_behavior)
        self._exit_behavior_input.setCurrentIndex(exit_behavior_index if exit_behavior_index >= 0 else 0)
        self._hover_tooltip_enabled_input.setChecked(baseline.hover_tooltip_enabled)
        self._auto_reindent_flat_python_paste_input.setChecked(baseline.auto_reindent_flat_python_paste)

    def _handle_reset_intelligence_group_to_global(self) -> None:
        baseline = self._scope_snapshots[SETTINGS_SCOPE_GLOBAL]
        self._completion_enabled_input.setChecked(baseline.completion_enabled)
        self._completion_auto_trigger_input.setChecked(baseline.completion_auto_trigger)
        self._completion_min_chars_input.setValue(baseline.completion_min_chars)
        self._linter_enabled_input.setChecked(baseline.diagnostics_enabled)
        self._diagnostics_realtime_input.setChecked(baseline.diagnostics_realtime)
        self._quick_fixes_enabled_input.setChecked(baseline.quick_fixes_enabled)
        self._quick_fix_multifile_preview_input.setChecked(baseline.quick_fix_require_preview_for_multifile)
        self._cache_enabled_input.setChecked(baseline.cache_enabled)
        self._incremental_indexing_input.setChecked(baseline.incremental_indexing)
        self._metrics_logging_input.setChecked(baseline.metrics_logging_enabled)
        self._force_reindex_on_open_input.setChecked(baseline.force_full_reindex_on_open)
        provider_index = self._linter_provider_input.findData(baseline.selected_linter)
        self._linter_provider_input.setCurrentIndex(provider_index if provider_index >= 0 else 0)
        self._sync_linter_control_states()

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

        self._finalize_keybindings_columns()

    def _handle_reset_shortcut(self, action_id: str) -> None:
        editor = self._shortcut_editors.get(action_id)
        if editor is None:
            return
        default_shortcuts = default_shortcut_map()
        self._is_updating_shortcut_editors = True
        editor.setKeySequence(QKeySequence(default_shortcuts.get(action_id, "")))
        self._is_updating_shortcut_editors = False
        self._refresh_shortcut_conflicts()

    def _handle_shortcut_changed(self, action_id: str) -> None:
        if self._is_updating_shortcut_editors:
            self._refresh_shortcut_conflicts()
            return
        editor = self._shortcut_editors.get(action_id)
        if editor is None:
            self._refresh_shortcut_conflicts()
            return
        assigned_shortcut = normalize_shortcut(editor.keySequence().toString())
        if not assigned_shortcut or not editor.hasFocus():
            self._refresh_shortcut_conflicts()
            return
        conflicting_action_ids = [
            conflict_action_id
            for conflict_action_id, shortcut in self._current_shortcut_map().items()
            if conflict_action_id != action_id and normalize_shortcut(shortcut) == assigned_shortcut
        ]
        if not conflicting_action_ids:
            self._refresh_shortcut_conflicts()
            return
        command_labels = {
            command.action_id: f"{command.category} / {command.label}"
            for command in SHORTCUT_COMMANDS
        }
        conflict_names = ", ".join(command_labels.get(item, item) for item in conflicting_action_ids)
        choice = QMessageBox.question(
            self,
            "Shortcut Conflict",
            (
                f"'{assigned_shortcut}' is already assigned to {conflict_names}.\n\n"
                "Do you want to reassign it to this command?"
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        self._is_updating_shortcut_editors = True
        try:
            if choice == QMessageBox.Yes:
                for conflict_action_id in conflicting_action_ids:
                    conflict_editor = self._shortcut_editors.get(conflict_action_id)
                    if conflict_editor is not None:
                        conflict_editor.setKeySequence(QKeySequence())
            else:
                editor.setKeySequence(QKeySequence())
        finally:
            self._is_updating_shortcut_editors = False
        self._refresh_shortcut_conflicts()

    def _handle_reset_all_shortcuts(self) -> None:
        defaults = default_shortcut_map()
        self._is_updating_shortcut_editors = True
        try:
            for action_id, editor in self._shortcut_editors.items():
                editor.setKeySequence(QKeySequence(defaults.get(action_id, "")))
        finally:
            self._is_updating_shortcut_editors = False
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
        if theme_key == THEME_HC_DARK:
            return dict(DEFAULT_HC_DARK_PALETTE)
        if theme_key == THEME_HC_LIGHT:
            return dict(DEFAULT_HC_LIGHT_PALETTE)
        if theme_key == THEME_DARK:
            return dict(DEFAULT_DARK_PALETTE)
        return dict(DEFAULT_LIGHT_PALETTE)

    def _populate_syntax_color_table(self, theme_key: str) -> None:
        self._active_syntax_theme_key = theme_key
        self._syntax_color_inputs.clear()
        self._syntax_color_swatches.clear()
        self._syntax_color_row_by_token.clear()
        defaults = self._syntax_defaults_for_theme(theme_key)
        overrides = self._syntax_color_overrides_by_theme.setdefault(theme_key, {})
        self._syntax_color_table.setRowCount(0)
        self._syntax_color_table.setRowCount(len(SYNTAX_COLOR_TOKENS))
        for row_index, token in enumerate(SYNTAX_COLOR_TOKENS):
            self._syntax_color_row_by_token[token.key] = row_index
            label_item = QTableWidgetItem(f"{token.category} / {token.label}")
            label_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            self._syntax_color_table.setItem(row_index, 0, label_item)

            color_container = QWidget(self._syntax_color_table)
            color_layout = QHBoxLayout(color_container)
            color_layout.setContentsMargins(4, 2, 4, 2)
            color_layout.setSpacing(6)

            swatch = QLabel(color_container)
            swatch.setFixedSize(16, 16)
            color_layout.addWidget(swatch)
            self._syntax_color_swatches[token.key] = swatch

            color_input = QLineEdit(color_container)
            color_input.setMaximumWidth(90)
            color_input.setPlaceholderText(defaults.get(token.key, ""))
            effective_color = overrides.get(token.key, defaults.get(token.key, ""))
            color_input.setText(effective_color)
            color_input.textEdited.connect(
                lambda _text, key=token.key: self._handle_syntax_color_text_edited(key)
            )
            self._syntax_color_inputs[token.key] = color_input
            color_layout.addWidget(color_input)

            self._syntax_color_table.setCellWidget(row_index, 1, color_container)
            self._update_syntax_swatch(token.key, effective_color)

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

        finalize_settings_table_rows(self._syntax_color_table)
        self._finalize_syntax_columns()
        self._refresh_syntax_validation()

    def _handle_syntax_theme_changed(self, _index: int) -> None:
        theme_key = str(self._syntax_theme_input.currentData())
        if theme_key not in _VALID_SYNTAX_THEME_KEYS:
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
        default_color = defaults.get(token_key, "")
        if input_widget is not None:
            input_widget.setText(default_color)
        self._update_syntax_swatch(token_key, default_color)
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
            default_color = defaults.get(token_key, "")
            input_widget.setText(default_color)
            self._update_syntax_swatch(token_key, default_color)
            self._refresh_syntax_validation()
            return
        normalized = normalize_hex_color(input_widget.text())
        if normalized is None:
            self._update_syntax_swatch(token_key, raw_text)
            self._refresh_syntax_validation()
            return
        if normalized == defaults.get(token_key):
            overrides.pop(token_key, None)
        else:
            overrides[token_key] = normalized
        input_widget.setText(normalized)
        self._update_syntax_swatch(token_key, normalized)
        self._refresh_syntax_validation()

    def _update_syntax_swatch(self, token_key: str, hex_color: str) -> None:
        swatch = self._syntax_color_swatches.get(token_key)
        if swatch is None:
            return
        normalized = normalize_hex_color(hex_color)
        border = self._tokens.border
        if normalized:
            swatch.setStyleSheet(
                f"background: {normalized}; border: 1px solid {border}; border-radius: 3px;"
            )
        else:
            swatch.setStyleSheet(
                f"background: transparent; border: 1px solid {border}; border-radius: 3px;"
            )

    def _refresh_syntax_validation(self) -> None:
        invalid_entries: list[str] = []
        error_color = self._tokens.diag_error_color
        for token_key, input_widget in self._syntax_color_inputs.items():
            if not input_widget.text().strip():
                input_widget.setStyleSheet("")
                continue
            normalized = normalize_hex_color(input_widget.text())
            if normalized is None:
                input_widget.setStyleSheet(f"border: 1px solid {error_color};")
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

    def _handle_linter_enabled_toggled(self, _checked: bool) -> None:
        self._sync_linter_control_states()

    def _sync_linter_control_states(self) -> None:
        enabled = self._linter_enabled_input.isChecked()
        self._linter_provider_input.setEnabled(enabled)
        self._linter_table.setEnabled(enabled)

    def _populate_linter_table(self) -> None:
        self._lint_enabled_inputs.clear()
        self._lint_severity_inputs.clear()
        self._linter_table.setRowCount(0)
        self._linter_table.setRowCount(len(LINT_RULE_DEFINITIONS))
        severity_values = [LINT_SEVERITY_ERROR, LINT_SEVERITY_WARNING, LINT_SEVERITY_INFO]
        for row_index, definition in enumerate(LINT_RULE_DEFINITIONS):
            code_item = QTableWidgetItem(definition.code)
            code_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            self._linter_table.setItem(row_index, 0, code_item)
            rule_item = QTableWidgetItem(definition.title)
            rule_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            self._linter_table.setItem(row_index, 1, rule_item)

            override_payload = self._lint_rule_overrides.get(definition.code, {})
            enabled_value = bool(override_payload.get("enabled", definition.default_enabled))
            enabled_input = QCheckBox(self._linter_table)
            enabled_input.setChecked(enabled_value)
            enabled_input.setEnabled(definition.allow_disable)
            enabled_input.stateChanged.connect(
                lambda _state, code=definition.code: self._handle_lint_enabled_changed(code)
            )
            self._linter_table.setCellWidget(
                row_index, 2, settings_table_control_cell(self._linter_table, enabled_input)
            )
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
            severity_input.setMinimumContentsLength(len("WARNING"))
            severity_input.setMinimumWidth(severity_input.sizeHint().width())
            self._linter_table.setCellWidget(
                row_index, 3, settings_table_control_cell(self._linter_table, severity_input)
            )
            self._lint_severity_inputs[definition.code] = severity_input

            reset_button = QPushButton("Reset", self._linter_table)
            reset_button.clicked.connect(
                lambda _checked=False, code=definition.code: self._handle_reset_lint_rule(code)
            )
            reset_button.setMinimumWidth(reset_button.sizeHint().width())
            self._linter_table.setCellWidget(
                row_index, 4, settings_table_control_cell(self._linter_table, reset_button)
            )

        finalize_settings_table_rows(self._linter_table)
        self._finalize_linter_columns()

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
        baseline_snapshot = self._scope_snapshots.get(SETTINGS_SCOPE_GLOBAL)
        baseline_override = None
        if (
            self._active_scope == SETTINGS_SCOPE_PROJECT
            and baseline_snapshot is not None
            and code in baseline_snapshot.lint_rule_overrides
        ):
            baseline_override = baseline_snapshot.lint_rule_overrides.get(code, {})
        enabled_input = self._lint_enabled_inputs.get(code)
        if enabled_input is not None:
            if isinstance(baseline_override, dict) and "enabled" in baseline_override:
                enabled_input.setChecked(bool(baseline_override.get("enabled")))
            else:
                enabled_input.setChecked(definition.default_enabled)
        severity_input = self._lint_severity_inputs.get(code)
        if severity_input is not None:
            baseline_severity = None
            if isinstance(baseline_override, dict):
                severity_raw = baseline_override.get("severity")
                if isinstance(severity_raw, str):
                    baseline_severity = severity_raw
            index = severity_input.findData(baseline_severity or definition.default_severity)
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

    def _file_exclude_patterns_snapshot(self) -> list[str]:
        patterns: list[str] = []
        for i in range(self._file_excludes_list.count()):
            item = self._file_excludes_list.item(i)
            if item is not None:
                text = item.text().strip()
                if text:
                    patterns.append(text)
        return patterns

    def _handle_add_file_exclude(self) -> None:
        text = self._file_exclude_input.text().strip()
        if not text:
            return
        for part in text.split(","):
            pattern = part.strip()
            if not pattern:
                continue
            existing = [
                self._file_excludes_list.item(i).text()
                for i in range(self._file_excludes_list.count())
                if self._file_excludes_list.item(i) is not None
            ]
            if pattern not in existing:
                self._file_excludes_list.addItem(pattern)
        self._file_exclude_input.clear()

    def _handle_remove_file_exclude(self) -> None:
        selected = self._file_excludes_list.currentRow()
        if selected >= 0:
            self._file_excludes_list.takeItem(selected)

    def _handle_reset_file_excludes(self) -> None:
        self._file_excludes_list.clear()
        baseline_patterns = DEFAULT_EXCLUDE_PATTERNS
        if self._active_scope == SETTINGS_SCOPE_PROJECT:
            baseline_patterns = self._scope_snapshots[SETTINGS_SCOPE_GLOBAL].file_exclude_patterns
        for pattern in baseline_patterns:
            self._file_excludes_list.addItem(pattern)

    def _local_history_exclude_patterns_snapshot(self) -> list[str]:
        patterns: list[str] = []
        for i in range(self._local_history_excludes_list.count()):
            item = self._local_history_excludes_list.item(i)
            if item is None:
                continue
            text = item.text().strip()
            if text:
                patterns.append(text)
        return patterns

    def _handle_add_local_history_exclude(self) -> None:
        text = self._local_history_exclude_input.text().strip()
        if not text:
            return
        existing = {
            self._local_history_excludes_list.item(i).text()
            for i in range(self._local_history_excludes_list.count())
            if self._local_history_excludes_list.item(i) is not None
        }
        for part in text.split(","):
            pattern = part.strip()
            if pattern and pattern not in existing:
                self._local_history_excludes_list.addItem(pattern)
                existing.add(pattern)
        self._local_history_exclude_input.clear()

    def _handle_remove_local_history_exclude(self) -> None:
        selected = self._local_history_excludes_list.currentRow()
        if selected >= 0:
            self._local_history_excludes_list.takeItem(selected)

    def _handle_reset_local_history_settings(self) -> None:
        baseline = EditorSettingsSnapshot()
        if self._active_scope == SETTINGS_SCOPE_PROJECT:
            baseline = self._scope_snapshots[SETTINGS_SCOPE_GLOBAL]
        self._local_history_max_checkpoints_input.setValue(baseline.local_history_max_checkpoints_per_file)
        self._local_history_retention_days_input.setValue(baseline.local_history_retention_days)
        self._local_history_max_tracked_file_kb_input.setValue(
            max(1, int((baseline.local_history_max_tracked_file_bytes + 1023) / 1024))
        )
        self._local_history_excludes_list.clear()
        for pattern in baseline.local_history_exclude_patterns:
            self._local_history_excludes_list.addItem(pattern)

    def _handle_reset_linter_overrides_to_global(self) -> None:
        self._lint_rule_overrides.clear()
        self._populate_linter_table()
        baseline_snapshot = self._scope_snapshots.get(SETTINGS_SCOPE_GLOBAL)
        if self._active_scope != SETTINGS_SCOPE_PROJECT or baseline_snapshot is None:
            return
        for definition in LINT_RULE_DEFINITIONS:
            baseline_override = baseline_snapshot.lint_rule_overrides.get(definition.code, {})
            enabled_input = self._lint_enabled_inputs.get(definition.code)
            if enabled_input is not None:
                if isinstance(baseline_override.get("enabled"), bool):
                    enabled_input.setChecked(bool(baseline_override["enabled"]))
                else:
                    enabled_input.setChecked(definition.default_enabled)
            severity_input = self._lint_severity_inputs.get(definition.code)
            if severity_input is not None:
                baseline_severity = baseline_override.get("severity")
                if not isinstance(baseline_severity, str):
                    baseline_severity = definition.default_severity
                index = severity_input.findData(baseline_severity)
                severity_input.setCurrentIndex(index if index >= 0 else 0)

    def _refresh_validation_state(self) -> None:
        if self._ok_button is None:
            return
        if self._active_scope == SETTINGS_SCOPE_PROJECT:
            self._ok_button.setEnabled(True)
            self._ok_button.setToolTip("")
            if self._validation_banner_label is not None:
                self._validation_banner_label.clear()
                self._validation_banner_label.setVisible(False)
            return

        has_conflicts = self._has_shortcut_conflicts
        has_invalid_colors = self._has_invalid_syntax_colors
        can_save = not (has_conflicts or has_invalid_colors)
        self._ok_button.setEnabled(can_save)

        messages: list[str] = []
        if has_conflicts:
            messages.append("Fix conflicting keybindings on the Keybindings tab before saving.")
        if has_invalid_colors:
            messages.append("Fix invalid syntax colors on the Syntax Colors tab before saving.")
        banner_text = " ".join(messages)
        if self._validation_banner_label is not None:
            if banner_text:
                self._validation_banner_label.setText(banner_text)
                self._validation_banner_label.setVisible(True)
            else:
                self._validation_banner_label.clear()
                self._validation_banner_label.setVisible(False)
        self._ok_button.setToolTip(banner_text if not can_save else "")
