"""Editor buffer change hooks, status updates, and active-tab transitions."""

from __future__ import annotations

from typing import Any

from app.editors.code_editor_widget import CodeEditorWidget
from app.editors.editor_manager import EditorManager
from app.editors.editor_tab import DISK_CONFLICT_CHANGED, DISK_CONFLICT_MISSING, EditorTabState
from app.shell.active_surface_chrome import ActiveSurfaceChrome
from app.shell.editor_tab_host_protocols import EditorTabWorkflowHost
from app.shell.status_bar import EDITOR_DISK_STATE_MISSING, EDITOR_DISK_STATE_STALE


def editor_disk_state(tab_state: object) -> str | None:
    """``"stale"`` / ``"missing"`` for the status bar, from the buffer's disk conflict."""
    conflict = getattr(tab_state, "disk_conflict", None)
    kind = getattr(conflict, "kind", None)
    if kind == DISK_CONFLICT_MISSING:
        return EDITOR_DISK_STATE_MISSING
    if kind == DISK_CONFLICT_CHANGED:
        return EDITOR_DISK_STATE_STALE
    return None


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
        active_surface_chrome: ActiveSurfaceChrome,
    ) -> None:
        self._host = host
        self._editor_manager = editor_manager
        self._editor_tabs_coordinator = editor_tabs_coordinator
        self._outline_workflow = outline_workflow
        self._markdown_workflow = markdown_workflow
        self._tab_workflow = tab_workflow
        self._active_surface_chrome = active_surface_chrome

    def set_editor_manager(self, editor_manager: EditorManager) -> None:
        self._editor_manager = editor_manager

    def handle_editor_text_changed(self, file_path: str, editor_widget: CodeEditorWidget) -> None:
        if self._editor_manager.get_tab(file_path) is None:
            return
        self._editor_tabs_coordinator.advance_buffer_revision(file_path)
        existing = self._editor_manager.get_tab(file_path)
        if existing is not None and getattr(existing, "content_source", None) is not None:
            tab_state = existing
        else:
            tab_state = self._editor_manager.update_tab_content(file_path, editor_widget.toPlainText())
        if tab_state.is_preview and tab_state.is_dirty:
            self._editor_tabs_coordinator.promote_preview_tab(file_path)
            refreshed_state = self._editor_manager.get_tab(file_path)
            if refreshed_state is not None:
                tab_state = refreshed_state
        if self._host.editor_tabs_widget() is None:
            return
        # Every group showing the buffer gets the dirty marker.
        self._editor_tabs_coordinator.refresh_tab_presentation(tab_state.file_path)
        if tab_state.is_dirty:
            if getattr(tab_state, "content_source", None) is None:
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

    def handle_content_source_changed(self, tab_state: EditorTabState) -> None:
        """Dirty-state half of a sourced edit. Reads ``tab_state.file_path`` at fire time."""
        file_path = tab_state.file_path
        if self._editor_manager.get_tab(file_path) is None:
            return
        if tab_state.is_preview and tab_state.is_dirty:
            self._editor_tabs_coordinator.promote_preview_tab(file_path)
            refreshed = self._editor_manager.get_tab(file_path)
            if refreshed is not None:
                tab_state = refreshed
                file_path = tab_state.file_path
        if self._host.editor_tabs_widget() is None:
            return
        if self._editor_tabs_coordinator.tab_index_for_path(file_path) < 0:
            return
        self._editor_tabs_coordinator.refresh_tab_presentation(file_path)
        if tab_state.is_dirty:
            self._host.local_history_note_source_changed(file_path)
            if self._host.editor_auto_save():
                self._host.start_auto_save_to_file_timer()
        else:
            self._host.local_history_discard_pending_autosave(file_path)
            self._host.local_history_delete_draft(file_path)
        self._host.refresh_save_action_states()

    def handle_editor_cursor_position_changed(self, file_path: str, editor_widget: CodeEditorWidget) -> None:
        tab_state = self._editor_manager.get_tab(file_path)
        status_controller = self._host.status_controller()
        if tab_state is None or status_controller is None:
            return
        if self._editor_manager.active_tab() is not tab_state:
            # A background tab's cursor moved (session restore, an edit in another view).
            return
        if self._surface_sentence(file_path) is not None:
            return
        line_number = editor_widget.textCursor().blockNumber() + 1
        status_controller.set_editor_status(
            file_name=tab_state.display_name,
            line=line_number,
            column=editor_widget.textCursor().positionInBlock() + 1,
            is_dirty=tab_state.is_dirty,
            disk_state=editor_disk_state(tab_state),
        )
        self._outline_workflow.highlight_symbol_at_line(line_number)

    def update_editor_status_for_path(self, file_path: str) -> None:
        status_controller = self._host.status_controller()
        if status_controller is None:
            return
        tab_state = self._editor_manager.get_tab(file_path)
        sentence = self._surface_sentence(file_path)
        if tab_state is not None and sentence is not None:
            status_controller.set_editor_status(
                file_name=tab_state.display_name,
                line=None,
                column=None,
                is_dirty=tab_state.is_dirty,
                sentence=sentence,
            )
            return
        editor_widget = self._host.editor_widgets_by_path().get(file_path)
        if tab_state is None or editor_widget is None:
            status_controller.set_editor_status(file_name=None, line=None, column=None, is_dirty=False)
            return
        status_controller.set_editor_status(
            file_name=tab_state.display_name,
            line=editor_widget.textCursor().blockNumber() + 1,
            column=editor_widget.textCursor().positionInBlock() + 1,
            is_dirty=tab_state.is_dirty,
            disk_state=editor_disk_state(tab_state),
        )

    def _surface_sentence(self, file_path: str) -> str | None:
        surface = self._host.tab_content_registry().surface_for_path(file_path)
        if surface is None:
            return None
        return surface.shell_state().sentence

    def handle_editor_tab_changed(self, tab_index: int) -> None:
        editor_tabs_widget = self._host.editor_tabs_widget()
        tab_path = None
        if tab_index >= 0 and editor_tabs_widget is not None:
            tab_path = self._editor_tabs_coordinator.file_path_for_tab_index(tab_index) or None
        if tab_path is not None:
            self._editor_manager.set_active_file(tab_path)
        self._active_surface_chrome.follow(tab_path)
        if tab_path is None:
            return
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
