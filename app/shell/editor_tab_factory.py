"""Editor tab materialization for the shell workspace."""

from __future__ import annotations

import time
from typing import Any, Optional

from PySide2.QtWidgets import QMessageBox, QWidget

from app.editors.code_editor_widget import CodeEditorWidget
from app.editors.editor_manager import OpenedTabResult
from app.shell.editor_tab_bindings_workflow import EditorTabBindingsHost


class MainWindowEditorBindingsHost:
    """Binding ports for :class:`EditorTabFactory` backed by a MainWindow instance."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def semantic_navigation_workflow(self) -> Any:
        return self._window._semantic_navigation_workflow

    def enable_auto_reindent_flat_python_paste_from_hint(self) -> Any:
        return self._window._enable_auto_reindent_flat_python_paste_from_hint

    def handle_paste_hint_repair_result(self) -> Any:
        return self._window._handle_paste_hint_repair_result


class EditorTabFactory:
    """Creates editor widgets and registers them with the shell workspace."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def open_file_in_editor(self, file_path: str, *, preview: bool = False, restore_draft: bool = True) -> bool:
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
        return self._materialize_opened_editor_tab(
            opened_result,
            started_at=started_at,
            restore_draft=restore_draft,
        )

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
            window._editor_tab_workflow.remove_tab_widget_for_path(opened_result.closed_preview_path)

        if opened_result.was_already_open:
            existing_index = window._editor_tab_workflow.tab_index_for_path(opened_result.tab.file_path)
            if existing_index >= 0:
                window._editor_tabs_widget.setCurrentIndex(existing_index)
                window._editor_tab_workflow.refresh_tab_presentation(opened_result.tab.file_path)
            window._refresh_save_action_states()
            window._editor_tab_workflow.update_editor_status_for_path(opened_result.tab.file_path)
            return True

        editor_widget = CodeEditorWidget(window._editor_tabs_widget)
        editor_widget.setObjectName("shell.editorTabs.textEditor")
        editor_widget.set_editor_preferences(
            tab_width=window._editor_tab_width,
            font_point_size=window._editor_tab_workflow.effective_font_size(),
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
        window._editor_tab_workflow.apply_runtime_intelligence_preferences_to_editor(editor_widget)
        editor_widget.apply_theme(window._shell_theme_workflow.resolve_theme_tokens())
        editor_widget.setPlainText(opened_result.tab.current_content)
        editor_widget.set_language_for_path(opened_result.tab.file_path)
        tab_file_path = opened_result.tab.file_path

        bindings_host: EditorTabBindingsHost = MainWindowEditorBindingsHost(window)
        window._editor_tab_workflow.attach_editor_bindings(bindings_host, editor_widget, tab_file_path)
        window._workspace_controller.register_editor(opened_result.tab.file_path, editor_widget)

        tab_content: QWidget = window._editor_tab_workflow.wrap_tab_content_if_markdown(
            editor_widget=editor_widget,
            file_path=tab_file_path,
            parent=window._editor_tabs_widget,
            theme_tokens=window._shell_theme_workflow.resolve_theme_tokens(),
            open_linked_file=lambda linked_path: self.open_file_in_editor(linked_path, preview=False),
        )

        tab_index = window._editor_tabs_widget.addTab(tab_content, opened_result.tab.display_name)
        window._editor_tabs_widget.setTabToolTip(tab_index, opened_result.tab.file_path)
        window._editor_tabs_widget.setCurrentIndex(tab_index)
        window._editor_tab_workflow.refresh_tab_presentation(opened_result.tab.file_path)
        if restore_draft:
            window._local_history_workflow.maybe_restore_draft(opened_result.tab, editor_widget)
        window._editor_tab_workflow.apply_detected_indentation_for_widget(
            opened_result.tab.file_path,
            editor_widget,
            editor_widget.toPlainText(),
        )
        window._editor_tab_workflow.handle_editor_tab_changed(tab_index)
        window._refresh_save_action_states()
        window._editor_tab_workflow.update_editor_status_for_path(opened_result.tab.file_path)
        if started_at is not None:
            window._logger.info(
                "File open telemetry: file=%s elapsed_ms=%.2f",
                opened_result.tab.file_path,
                (time.perf_counter() - started_at) * 1000.0,
            )
        return True


__all__ = ["EditorTabFactory", "MainWindowEditorBindingsHost"]
