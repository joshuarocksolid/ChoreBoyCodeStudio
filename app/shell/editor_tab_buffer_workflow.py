"""Editor buffer change hooks, status updates, and active-tab transitions."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from app.editors.code_editor_widget import CodeEditorWidget
from app.editors.editor_manager import EditorManager
from app.editors.editor_tab import DISK_CONFLICT_CHANGED, DISK_CONFLICT_MISSING, EditorTabState
from app.shell.editor_tab_host_protocols import EditorTabWorkflowHost
from app.shell.status_bar import EDITOR_DISK_STATE_MISSING, EDITOR_DISK_STATE_STALE
from app.shell.tab_content_providers import focus_primary_surface


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
    ) -> None:
        self._host = host
        self._editor_manager = editor_manager
        self._editor_tabs_coordinator = editor_tabs_coordinator
        self._outline_workflow = outline_workflow
        self._markdown_workflow = markdown_workflow
        self._tab_workflow = tab_workflow
        self._text_revision_by_path: dict[str, int] = {}
        self._reveal_pending: str | None = None
        self._outline_idle_armed = False
        self._outline_needs_flush = False
        self._tab_change_depth = 0
        self._status_hold_depth = 0
        self._status_held: dict[str, None] = {}
        self._lint_held: dict[str, None] = {}

    def set_editor_manager(self, editor_manager: EditorManager) -> None:
        self._editor_manager = editor_manager

    def handle_editor_text_changed(self, file_path: str, editor_widget: CodeEditorWidget) -> None:
        document = editor_widget.document()
        revision = int(document.revision()) if document is not None else None
        if revision is not None and self._text_revision_by_path.get(file_path) == revision:
            return
        if revision is not None:
            self._text_revision_by_path[file_path] = revision
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
        line_number = editor_widget.textCursor().blockNumber() + 1
        status_controller.set_editor_status(
            file_name=tab_state.display_name,
            line=line_number,
            column=editor_widget.textCursor().positionInBlock() + 1,
            is_dirty=tab_state.is_dirty,
            disk_state=editor_disk_state(tab_state),
            sentence=self._editor_status_sentence(tab_state.file_path),
        )
        self._outline_workflow.highlight_symbol_at_line(line_number)

    @contextmanager
    def hold_status_updates(self) -> Iterator[None]:
        """Refresh each path's status once, when the outermost hold ends.

        Opening a tab and writing a handler into it ask for the same status
        nine times. Every ask reads the editor's cursor and rebuilds the same
        text, and the last one wins, so the asks inside the hold become one.
        The tab-change lint is asked for twice as well. It starts once, on the
        idle turn, so the worker does not compete with the open for the
        interpreter.
        """
        self._status_hold_depth += 1
        try:
            yield
        finally:
            self._status_hold_depth -= 1
            if self._status_hold_depth == 0:
                held = list(self._status_held)
                self._status_held.clear()
                for file_path in held:
                    self._refresh_editor_status(file_path)
                lint = list(self._lint_held)
                self._lint_held.clear()
                if lint:
                    from app.shell.idle_turn import run_when_idle

                    run_when_idle(lambda: self._lint_tabs(lint))

    def _lint_tabs(self, paths: list[str]) -> None:
        if self._host.is_shutting_down():
            return
        for file_path in paths:
            if self._editor_manager.get_tab(file_path) is not None:
                self._host.render_lint_diagnostics_for_file(file_path, trigger="tab_change")

    def _lint_for_tab_change(self, tab_path: str) -> None:
        if self._status_hold_depth:
            self._lint_held[tab_path] = None
            return
        self._host.render_lint_diagnostics_for_file(tab_path, trigger="tab_change")

    def update_editor_status_for_path(self, file_path: str) -> None:
        if self._status_hold_depth:
            self._status_held[file_path] = None
            return
        self._refresh_editor_status(file_path)

    def _refresh_editor_status(self, file_path: str) -> None:
        status_controller = self._host.status_controller()
        if status_controller is None:
            return
        tab_state = self._editor_manager.get_tab(file_path)
        editor_widget = self._host.editor_widgets_by_path().get(file_path)
        sentence = self._editor_status_sentence(file_path)
        if tab_state is None or editor_widget is None:
            if sentence:
                status_controller.set_editor_status(
                    file_name=None if tab_state is None else tab_state.display_name,
                    line=None,
                    column=None,
                    is_dirty=False if tab_state is None else tab_state.is_dirty,
                    disk_state=None if tab_state is None else editor_disk_state(tab_state),
                    sentence=sentence,
                )
                return
            status_controller.set_editor_status(file_name=None, line=None, column=None, is_dirty=False)
            return
        status_controller.set_editor_status(
            file_name=tab_state.display_name,
            line=editor_widget.textCursor().blockNumber() + 1,
            column=editor_widget.textCursor().positionInBlock() + 1,
            is_dirty=tab_state.is_dirty,
            disk_state=editor_disk_state(tab_state),
            sentence=sentence,
        )

    def handle_editor_tab_changed(self, tab_index: int) -> None:
        self._tab_change_depth += 1
        try:
            self._apply_editor_tab_changed(tab_index)
        finally:
            self._tab_change_depth -= 1
            if self._tab_change_depth == 0 and self._outline_needs_flush:
                self._outline_needs_flush = False
                self._arm_outline_timer()

    def _apply_editor_tab_changed(self, tab_index: int) -> None:
        editor_tabs_widget = self._host.editor_tabs_widget()
        if tab_index < 0 or editor_tabs_widget is None:
            return

        tab_path = self._editor_tabs_coordinator.file_path_for_tab_index(tab_index)
        if not tab_path:
            return
        self._editor_manager.set_active_file(tab_path)
        self._host.refresh_save_action_states()
        self._host.refresh_run_action_states()
        self._markdown_workflow.refresh_markdown_action_states()
        self.update_editor_status_for_path(tab_path)
        self._tab_workflow.update_indent_status_for_path(tab_path)
        self._tab_workflow.check_for_external_file_change(tab_path)
        self._lint_for_tab_change(tab_path)
        self._schedule_outline_refresh()
        self._schedule_tree_reveal(tab_path)
        tab_state = self._editor_manager.get_tab(tab_path)
        if tab_state is not None and not tab_state.is_preview:
            registry_getter = getattr(self._host, "tab_content_registry", None)
            registry = registry_getter() if callable(registry_getter) else None
            focus_primary_surface(registry, tab_state.file_path)

    def _schedule_outline_refresh(self) -> None:
        """The outline worker starts on the next idle turn, not inside the tab switch."""
        if self._tab_change_depth:
            self._outline_needs_flush = True
            return
        self._arm_outline_timer()

    def _arm_outline_timer(self) -> None:
        if self._outline_idle_armed:
            return
        self._outline_idle_armed = True
        from app.qt.QtCore import QTimer

        QTimer.singleShot(0, self._flush_outline)

    def _flush_outline(self) -> None:
        self._outline_idle_armed = False
        if self._tab_change_depth:
            self._outline_needs_flush = True
            return
        self._outline_workflow.handle_active_tab_changed()

    def _schedule_tree_reveal(self, tab_path: str) -> None:
        """One reveal for the two tab-changed signals, on the next idle turn."""
        already = self._reveal_pending is not None
        self._reveal_pending = tab_path
        if already:
            return
        from app.qt.QtCore import QTimer

        QTimer.singleShot(0, self._flush_tree_reveal)

    def _flush_tree_reveal(self) -> None:
        path = self._reveal_pending
        self._reveal_pending = None
        if not path:
            return
        self._host.reveal_project_tree_path(path)

    def _editor_status_sentence(self, file_path: str) -> str | None:
        """A tab surface may replace the line and column with its own sentence."""
        registry_getter = getattr(self._host, "tab_content_registry", None)
        if not callable(registry_getter):
            return None
        registry = registry_getter()
        if registry is None:
            return None
        surface = registry.surface_for_path(file_path)
        reader = getattr(surface, "editor_status_sentence", None)
        if not callable(reader):
            return None
        text = reader()
        if isinstance(text, str) and text:
            return text
        return None


__all__ = ["EditorTabBufferWorkflow"]
