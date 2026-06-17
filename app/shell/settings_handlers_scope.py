"""Scope switching and reset-to-global handlers for SettingsDialog."""

from __future__ import annotations

from PySide2.QtGui import QFont

from app.shell.settings_models import (
    EditorSettingsSnapshot,
    SETTINGS_SCOPE_GLOBAL,
    SETTINGS_SCOPE_PROJECT,
)


class SettingsScopeHandlersMixin:
    """Mixin for settings scope visibility and reset-to-global handlers."""

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
