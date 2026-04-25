"""Editor tab materialization for the shell workspace."""

from __future__ import annotations

import time
from typing import Any, Optional

from PySide2.QtWidgets import QMessageBox

from app.editors.code_editor_widget import CodeEditorWidget
from app.editors.editor_manager import OpenedTabResult
from app.intelligence.completion_models import CompletionItem


class EditorTabFactory:
    """Creates editor widgets and wires their shell callbacks."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def open_file_in_editor(self, file_path: str, *, preview: bool = False) -> bool:
        window = self._window
        if window._editor_tabs_widget is None:
            return False

        started_at = time.perf_counter()
        try:
            use_preview = preview and window._editor_enable_preview
            opened_result = window._editor_manager.open_file(file_path, preview=use_preview)
        except ValueError as exc:
            QMessageBox.warning(window, "Unable to open file", str(exc))
            return False
        return self._materialize_opened_editor_tab(opened_result, started_at=started_at, restore_draft=True)

    def open_restored_history_buffer(self, file_path: str, content: str) -> bool:
        window = self._window
        if window._editor_tabs_widget is None:
            return False
        opened_result = window._editor_manager.open_file_with_content(
            file_path,
            content,
            original_content="",
            preview=False,
            last_known_mtime=None,
        )
        return self._materialize_opened_editor_tab(opened_result, started_at=None, restore_draft=False)

    def _materialize_opened_editor_tab(
        self,
        opened_result: OpenedTabResult,
        *,
        started_at: Optional[float],
        restore_draft: bool,
    ) -> bool:
        window = self._window
        if window._editor_tabs_widget is None:
            return False

        if opened_result.closed_preview_path:
            window._remove_tab_widget_for_path(opened_result.closed_preview_path)

        if opened_result.was_already_open:
            existing_index = window._tab_index_for_path(opened_result.tab.file_path)
            if existing_index >= 0:
                window._editor_tabs_widget.setCurrentIndex(existing_index)
                window._refresh_tab_presentation(opened_result.tab.file_path)
            window._refresh_save_action_states()
            window._update_editor_status_for_path(opened_result.tab.file_path)
            return True

        editor_widget = CodeEditorWidget(window._editor_tabs_widget)
        editor_widget.setObjectName("shell.editorTabs.textEditor")
        editor_widget.set_editor_preferences(
            tab_width=window._editor_tab_width,
            font_point_size=window._effective_font_size(),
            font_family=window._editor_font_family,
            indent_style=window._editor_indent_style,
            indent_size=window._editor_indent_size,
            hover_tooltip_enabled=window._editor_hover_tooltip_enabled,
            auto_reindent_flat_python_paste=window._editor_auto_reindent_flat_python_paste,
        )
        editor_widget.set_completion_preferences(
            enabled=window._completion_enabled,
            auto_trigger=window._completion_auto_trigger,
            min_chars=window._completion_min_chars,
        )
        window._apply_runtime_intelligence_preferences_to_editor(editor_widget)
        editor_widget.apply_theme(window._resolve_theme_tokens())
        editor_widget.setPlainText(opened_result.tab.current_content)
        editor_widget.set_language_for_path(opened_result.tab.file_path)
        tab_file_path = opened_result.tab.file_path

        def completion_requester(
            prefix: str,
            source_text: str,
            cursor_position: int,
            manual_trigger: bool,
            request_generation: int,
        ) -> None:
            window._request_editor_completions_async(
                file_path=tab_file_path,
                editor_widget=editor_widget,
                prefix=prefix,
                source_text=source_text,
                cursor_position=cursor_position,
                manual_trigger=manual_trigger,
                request_generation=request_generation,
            )

        def hover_requester(source_text: str, cursor_position: int, request_generation: int) -> None:
            window._request_inline_hover_text_async(
                file_path=tab_file_path,
                editor_widget=editor_widget,
                source_text=source_text,
                cursor_position=cursor_position,
                request_generation=request_generation,
            )

        def signature_requester(source_text: str, cursor_position: int, request_generation: int) -> None:
            window._request_inline_signature_text_async(
                file_path=tab_file_path,
                editor_widget=editor_widget,
                source_text=source_text,
                cursor_position=cursor_position,
                request_generation=request_generation,
            )

        def on_breakpoint_toggled(line_number: int, enabled: bool) -> None:
            window._debug_control_workflow.handle_editor_breakpoint_toggled(tab_file_path, line_number, enabled)

        def on_text_changed() -> None:
            window._handle_editor_text_changed(tab_file_path, editor_widget)

        def on_cursor_position_changed() -> None:
            window._handle_editor_cursor_position_changed(tab_file_path, editor_widget)

        def on_completion_accepted(item: CompletionItem) -> None:
            window._intelligence_controller.record_completion_acceptance(item)

        editor_widget.set_breakpoint_toggled_callback(on_breakpoint_toggled)
        editor_widget.set_completion_requester(completion_requester)
        editor_widget.set_completion_accepted_callback(on_completion_accepted)
        editor_widget.set_hover_requester(hover_requester)
        editor_widget.set_signature_help_requester(signature_requester)
        editor_widget.set_breakpoints(window._breakpoints_by_file.get(opened_result.tab.file_path, set()))
        editor_widget.textChanged.connect(on_text_changed)
        editor_widget.cursorPositionChanged.connect(on_cursor_position_changed)
        window._workspace_controller.register_editor(opened_result.tab.file_path, editor_widget)

        tab_index = window._editor_tabs_widget.addTab(editor_widget, opened_result.tab.display_name)
        window._editor_tabs_widget.setTabToolTip(tab_index, opened_result.tab.file_path)
        window._editor_tabs_widget.setCurrentIndex(tab_index)
        window._refresh_tab_presentation(opened_result.tab.file_path)
        if restore_draft:
            window._local_history_workflow.maybe_restore_draft(opened_result.tab, editor_widget)
        window._apply_detected_indentation_for_widget(
            opened_result.tab.file_path,
            editor_widget,
            editor_widget.toPlainText(),
        )
        window._handle_editor_tab_changed(tab_index)
        window._refresh_save_action_states()
        window._update_editor_status_for_path(opened_result.tab.file_path)
        if started_at is not None:
            window._logger.info(
                "File open telemetry: file=%s elapsed_ms=%.2f",
                opened_result.tab.file_path,
                (time.perf_counter() - started_at) * 1000.0,
            )
        return True
