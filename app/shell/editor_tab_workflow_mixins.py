"""One-line delegate methods for :class:`EditorTabWorkflow`."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide2.QtCore import QPoint

from app.core.models import LoadedProject
from app.editors.code_editor_widget import CodeEditorWidget
from app.editors.markdown_editor_pane import MarkdownEditorPane
from app.intelligence.outline_service import OutlineSymbol


class EditorTabOutlineDelegates:
    _outline_workflow: Any

    def refresh_outline_for_active_tab(self) -> None:
        self._outline_workflow.refresh_for_active_tab()

    def flat_outline_symbols_for_path(self, file_path: str, *, fallback_source: str) -> tuple[OutlineSymbol, ...]:
        return self._outline_workflow.flat_symbols_for_path(file_path, fallback_source=fallback_source)

    def request_flat_outline_symbols_async(
        self,
        file_path: str,
        *,
        fallback_source: str,
        on_success: Callable[[tuple[OutlineSymbol, ...]], None],
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self._outline_workflow.request_flat_outline_symbols_async(
            file_path,
            fallback_source=fallback_source,
            on_success=on_success,
            on_error=on_error,
        )

    def handle_outline_symbol_activated(self, file_path: str, line_number: int) -> None:
        self._outline_workflow.handle_symbol_activated(file_path, line_number)

    def open_file_at_line(self, file_path: str, line_number: int | None, *, preview: bool = False) -> None:
        self._outline_workflow.open_file_at_line(file_path, line_number, preview=preview)


class EditorTabMarkdownDelegates:
    _markdown_workflow: Any

    def active_markdown_pane(self) -> MarkdownEditorPane | None:
        return self._markdown_workflow.active_markdown_pane()

    def set_active_markdown_mode(self, mode: str) -> None:
        self._markdown_workflow.set_active_markdown_mode(mode)

    def handle_markdown_show_source_action(self) -> None:
        self._markdown_workflow.handle_markdown_show_source_action()

    def handle_markdown_show_preview_action(self) -> None:
        self._markdown_workflow.handle_markdown_show_preview_action()

    def handle_markdown_show_split_action(self) -> None:
        self._markdown_workflow.handle_markdown_show_split_action()

    def handle_markdown_toggle_preview_action(self) -> None:
        self._markdown_workflow.handle_markdown_toggle_preview_action()

    def refresh_markdown_action_states(self) -> None:
        self._markdown_workflow.refresh_markdown_action_states()

    def wrap_tab_content_if_markdown(
        self, *, editor_widget: CodeEditorWidget, file_path: str, parent: Any, theme_tokens: Any, open_linked_file: Any
    ) -> Any:
        return self._markdown_workflow.wrap_tab_content_if_markdown(
            editor_widget=editor_widget,
            file_path=file_path,
            parent=parent,
            theme_tokens=theme_tokens,
            open_linked_file=open_linked_file,
        )


class EditorTabBufferDelegates:
    _buffer_workflow: Any
    _editor_tabs_coordinator: Any

    def handle_editor_text_changed(self, file_path: str, editor_widget: CodeEditorWidget) -> None:
        self._buffer_workflow.handle_editor_text_changed(file_path, editor_widget)

    def handle_editor_cursor_position_changed(self, file_path: str, editor_widget: CodeEditorWidget) -> None:
        self._buffer_workflow.handle_editor_cursor_position_changed(file_path, editor_widget)

    def update_editor_status_for_path(self, file_path: str) -> None:
        self._buffer_workflow.update_editor_status_for_path(file_path)

    def active_editor_widget(self) -> CodeEditorWidget | None:
        return self._editor_tabs_coordinator.active_editor_widget()  # type: ignore[return-value]

    def advance_buffer_revision(self, file_path: str) -> int:
        return self._editor_tabs_coordinator.advance_buffer_revision(file_path)

    def buffer_revision(self, file_path: str) -> int | None:
        return self._editor_tabs_coordinator.buffer_revision(file_path)

    def handle_editor_tab_changed(self, tab_index: int) -> None:
        self._buffer_workflow.handle_editor_tab_changed(tab_index)


class EditorTabLifecycleDelegates:
    _lifecycle_workflow: Any
    _editor_tabs_coordinator: Any

    def release_editor_widget(self, widget: CodeEditorWidget) -> None:
        self._lifecycle_workflow.release_editor_widget(widget)

    def tab_index_for_path(self, file_path: str) -> int:
        return self._editor_tabs_coordinator.tab_index_for_path(file_path)

    def remove_tab_widget_for_path(self, file_path: str) -> None:
        self._lifecycle_workflow.remove_tab_widget_for_path(file_path)

    def refresh_tab_presentation(self, file_path: str) -> None:
        self._editor_tabs_coordinator.refresh_tab_presentation(file_path)

    def promote_preview_tab(self, file_path: str) -> bool:
        return self._editor_tabs_coordinator.promote_preview_tab(file_path)

    def promote_existing_preview_tab(self) -> bool:
        return self._editor_tabs_coordinator.promote_existing_preview_tab()

    def handle_editor_tab_header_double_click(self, tab_index: int) -> None:
        self._lifecycle_workflow.handle_editor_tab_header_double_click(tab_index)

    def handle_keep_preview_open_shortcut(self) -> None:
        self._lifecycle_workflow.handle_keep_preview_open_shortcut()

    def show_editor_tab_context_menu(self, position: QPoint) -> None:
        self._lifecycle_workflow.show_editor_tab_context_menu(position)

    def handle_tab_close_requested(self, tab_index: int) -> None:
        self._lifecycle_workflow.handle_tab_close_requested(tab_index)

    def close_active_tab(self) -> None:
        self._lifecycle_workflow.close_active_tab()

    def reset_editor_tabs(self) -> None:
        self._lifecycle_workflow.reset_editor_tabs()
        self._poll_workflow.reset_poll_state()


class EditorTabPreferencesDelegates:
    _preferences_workflow: Any
    _host: Any
    _latency_recorder: Any

    def effective_font_size(self) -> int:
        return self._preferences_workflow.effective_font_size()

    def apply_editor_preferences_to_open_editors(self) -> None:
        self._preferences_workflow.apply_editor_preferences_to_open_editors()

    def apply_runtime_intelligence_preferences_to_open_editors(self) -> None:
        self._preferences_workflow.apply_runtime_intelligence_preferences_to_open_editors()

    def apply_runtime_intelligence_preferences_to_editor(self, editor_widget: CodeEditorWidget) -> None:
        from app.shell.editor_latency_recorder import attach_editor_latency_recorder

        self._preferences_workflow.apply_runtime_intelligence_preferences_to_editor(editor_widget)
        runtime_settings = self._host.intelligence_runtime_settings()
        attach_editor_latency_recorder(
            editor_widget, recorder=self._latency_recorder, logging_enabled=runtime_settings.metrics_logging_enabled
        )

    def apply_detected_indentation_for_widget(
        self, file_path: str, editor_widget: CodeEditorWidget, source_text: str
    ) -> None:
        self._preferences_workflow.apply_detected_indentation_for_widget(file_path, editor_widget, source_text)

    def record_indent_source(self, file_path: str, style: str, size: int, source: str) -> None:
        self._preferences_workflow.record_indent_source(file_path, style, size, source)

    def update_indent_status_for_path(self, file_path: str | None) -> None:
        self._preferences_workflow.update_indent_status_for_path(file_path)

    def handle_zoom_in(self) -> None:
        self._preferences_workflow.handle_zoom_in()

    def handle_zoom_out(self) -> None:
        self._preferences_workflow.handle_zoom_out()

    def handle_zoom_reset(self) -> None:
        self._preferences_workflow.handle_zoom_reset()


class EditorTabPollDelegates:
    _poll_workflow: Any

    def refresh_open_tabs_from_disk(self, file_paths: list[str]) -> None:
        self._poll_workflow.refresh_open_tabs_from_disk(file_paths)

    def check_for_external_file_change(self, file_path: str) -> None:
        self._poll_workflow.check_for_external_file_change(file_path)

    def poll_external_file_changes(self) -> None:
        self._poll_workflow.poll_external_file_changes()

    def scan_project_tree_signature(self, loaded_project: LoadedProject) -> tuple[str, ...]:
        return self._poll_workflow.scan_project_tree_signature(loaded_project)


__all__ = [
    "EditorTabBufferDelegates",
    "EditorTabLifecycleDelegates",
    "EditorTabMarkdownDelegates",
    "EditorTabOutlineDelegates",
    "EditorTabPollDelegates",
    "EditorTabPreferencesDelegates",
]
