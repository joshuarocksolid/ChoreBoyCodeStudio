"""Editor buffer change hooks, status updates, and active-tab transitions."""

from __future__ import annotations

from typing import Any

from app.editors.code_editor_widget import CodeEditorWidget
from app.editors.editor_manager import EditorManager
from app.shell.editor_tab_host_protocols import EditorTabWorkflowHost


class EditorTabBufferWorkflow:
    """Owns text/cursor change handlers and editor status refresh."""

    def __init__(
        self,
        *,
        host: EditorTabWorkflowHost,
        editor_manager: EditorManager,
        editor_tabs_coordinator: Any,
        outline_workflow: Any,
        markdown_workflow: Any,
        tab_workflow: Any,
    ) -> None:
        self._host = host
        self._editor_manager = editor_manager
        self._editor_tabs_coordinator = editor_tabs_coordinator
        self._outline_workflow = outline_workflow
        self._markdown_workflow = markdown_workflow
        self._tab_workflow = tab_workflow

    def set_editor_manager(self, editor_manager: EditorManager) -> None:
        self._editor_manager = editor_manager

    def handle_editor_text_changed(self, file_path: str, editor_widget: CodeEditorWidget) -> None:
        if self._editor_manager.get_tab(file_path) is None:
            return
        self._editor_tabs_coordinator.advance_buffer_revision(file_path)
        tab_state = self._editor_manager.update_tab_content(file_path, editor_widget.toPlainText())
        if tab_state.is_preview and tab_state.is_dirty:
            self._editor_tabs_coordinator.promote_preview_tab(file_path)
            refreshed_state = self._editor_manager.get_tab(file_path)
            if refreshed_state is not None:
                tab_state = refreshed_state
        editor_tabs_widget = self._host.editor_tabs_widget()
        if editor_tabs_widget is None:
            return

        tab_index = self._editor_tabs_coordinator.tab_index_for_path(tab_state.file_path)
        if tab_index < 0:
            return
        self._editor_tabs_coordinator.refresh_tab_presentation(tab_state.file_path)
        if tab_state.is_dirty:
            self._host.local_history_schedule_autosave(tab_state.file_path, tab_state.current_content)
            if self._host.editor_auto_save():
                self._host.start_auto_save_to_file_timer()
        else:
            self._host.local_history_discard_pending_autosave(tab_state.file_path)
            self._host.local_history_delete_draft(tab_state.file_path)
        self._host.refresh_save_action_states()
        self.update_editor_status_for_path(tab_state.file_path)
        if not self._host.is_shutting_down():
            self._host.diagnostics_schedule_realtime_lint(tab_state.file_path)
        self._outline_workflow.schedule_refresh()

    def handle_editor_cursor_position_changed(self, file_path: str, editor_widget: CodeEditorWidget) -> None:
        tab_state = self._editor_manager.get_tab(file_path)
        status_controller = self._host.status_controller()
        if tab_state is None or status_controller is None:
            return
        line_number = editor_widget.textCursor().blockNumber() + 1
        status_controller.set_editor_status(
            file_name=tab_state.display_name,
            line=line_number,
            column=editor_widget.textCursor().positionInBlock() + 1,
            is_dirty=tab_state.is_dirty,
        )
        self._outline_workflow.highlight_symbol_at_line(line_number)

    def update_editor_status_for_path(self, file_path: str) -> None:
        status_controller = self._host.status_controller()
        if status_controller is None:
            return
        tab_state = self._editor_manager.get_tab(file_path)
        editor_widget = self._host.editor_widgets_by_path().get(file_path)
        if tab_state is None or editor_widget is None:
            status_controller.set_editor_status(file_name=None, line=None, column=None, is_dirty=False)
            return
        status_controller.set_editor_status(
            file_name=tab_state.display_name,
            line=editor_widget.textCursor().blockNumber() + 1,
            column=editor_widget.textCursor().positionInBlock() + 1,
            is_dirty=tab_state.is_dirty,
        )

    def handle_editor_tab_changed(self, tab_index: int) -> None:
        editor_tabs_widget = self._host.editor_tabs_widget()
        if tab_index < 0 or editor_tabs_widget is None:
            return

        tab_path = editor_tabs_widget.tabToolTip(tab_index)
        if not tab_path:
            return
        self._editor_manager.set_active_file(tab_path)
        self._host.refresh_save_action_states()
        self._host.refresh_run_action_states()
        self._markdown_workflow.refresh_markdown_action_states()
        self.update_editor_status_for_path(tab_path)
        self._tab_workflow.update_indent_status_for_path(tab_path)
        self._tab_workflow.check_for_external_file_change(tab_path)
        self._host.render_lint_diagnostics_for_file(tab_path, trigger="tab_change")
        self._outline_workflow.handle_active_tab_changed()
        self._host.reveal_project_tree_path(tab_path)


__all__ = ["EditorTabBufferWorkflow"]
