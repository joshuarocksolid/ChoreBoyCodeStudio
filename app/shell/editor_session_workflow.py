"""Persist and restore per-project editor session state (tabs, cursors, breakpoints)."""

from __future__ import annotations

import logging
from typing import Callable

from PySide2.QtCore import QTimer

from app.core.models import LoadedProject
from app.editors.code_editor_widget import CodeEditorWidget
from app.editors.editor_manager import EditorManager
from app.shell.breakpoint_store import BreakpointStore
from app.shell.session_persistence import (
    SessionFileState,
    SessionState,
    SessionTreeState,
    load_session_file,
    save_session_file,
)


class EditorSessionWorkflow:
    """Owns project session file persist/restore for open editors."""

    def __init__(
        self,
        *,
        loaded_project: Callable[[], LoadedProject | None],
        editor_manager: EditorManager,
        editor_widget_for_path: Callable[[str], CodeEditorWidget | None],
        open_file_in_editor: Callable[[str], bool],
        tab_index_for_path: Callable[[str], int],
        set_current_tab_index: Callable[[int], None],
        logger: logging.Logger,
        breakpoint_store: BreakpointStore | None = None,
        refresh_breakpoints_list: Callable[[], None] | None = None,
        capture_tree_state: Callable[[], SessionTreeState | None] | None = None,
        restore_tree_state: Callable[[SessionTreeState], None] | None = None,
        reveal_tree_path: Callable[[str], None] | None = None,
        set_tree_reveal_suppressed: Callable[[bool], None] | None = None,
    ) -> None:
        self._loaded_project = loaded_project
        self._editor_manager = editor_manager
        self._editor_widget_for_path = editor_widget_for_path
        self._open_file_in_editor = open_file_in_editor
        self._tab_index_for_path = tab_index_for_path
        self._set_current_tab_index = set_current_tab_index
        self._logger = logger
        self._breakpoint_store = breakpoint_store
        self._refresh_breakpoints_list = refresh_breakpoints_list
        self._capture_tree_state = capture_tree_state
        self._restore_tree_state = restore_tree_state
        self._reveal_tree_path = reveal_tree_path
        self._set_tree_reveal_suppressed = set_tree_reveal_suppressed

    def set_editor_manager(self, editor_manager: EditorManager) -> None:
        self._editor_manager = editor_manager

    def persist_session_state(self, project_root: str | None = None) -> None:
        target_project_root = project_root
        if target_project_root is None:
            loaded_project = self._loaded_project()
            if loaded_project is None:
                return
            target_project_root = loaded_project.project_root

        open_files: list[SessionFileState] = []
        lines_snapshot = (
            self._breakpoint_store.lines_snapshot() if self._breakpoint_store is not None else {}
        )
        for file_path in self._editor_manager.open_paths():
            cursor_line = 1
            cursor_column = 1
            scroll_position = 0
            editor_widget = self._editor_widget_for_path(file_path)
            if editor_widget is not None:
                cursor = editor_widget.textCursor()
                cursor_line = cursor.blockNumber() + 1
                cursor_column = cursor.positionInBlock() + 1
                scroll_position = editor_widget.verticalScrollBar().value()
            breakpoints = set(lines_snapshot.get(file_path, set()))
            open_files.append(
                SessionFileState(
                    file_path=file_path,
                    cursor_line=cursor_line,
                    cursor_column=cursor_column,
                    scroll_position=scroll_position,
                    breakpoints=tuple(sorted(breakpoints)),
                )
            )

        active_tab = self._editor_manager.active_tab()
        active_file_path = None if active_tab is None else active_tab.file_path
        project_tree = None
        if self._capture_tree_state is not None:
            project_tree = self._capture_tree_state()
        session_state = SessionState(
            open_files=tuple(open_files),
            active_file_path=active_file_path,
            project_tree=project_tree,
        )
        try:
            save_session_file(target_project_root, session_state)
        except Exception as exc:
            self._logger.warning("Failed to persist project session state for %s: %s", target_project_root, exc)

    def restore_session_state(self, project_root: str) -> None:
        try:
            session_state = load_session_file(project_root)
        except Exception as exc:
            self._logger.warning("Failed to load project session state for %s: %s", project_root, exc)
            return
        if session_state is None:
            return

        if self._set_tree_reveal_suppressed is not None:
            self._set_tree_reveal_suppressed(True)
        try:
            restored_by_file: dict[str, set[int]] = {}
            for file_state in session_state.open_files:
                if file_state.breakpoints:
                    restored_by_file[file_state.file_path] = set(file_state.breakpoints)
            if self._breakpoint_store is not None:
                self._breakpoint_store.restore_session_breakpoints(
                    restored_by_file,
                    ensure_spec=self._breakpoint_store.ensure_spec,
                )

            for file_state in session_state.open_files:
                if not self._open_file_in_editor(file_state.file_path):
                    if self._breakpoint_store is not None:
                        self._breakpoint_store.clear_file(file_state.file_path)
                    continue
                editor_widget = self._editor_widget_for_path(file_state.file_path)
                if editor_widget is None:
                    continue
                restore_editor_cursor_and_scroll(editor_widget, file_state)

            if session_state.active_file_path is not None:
                tab_index = self._tab_index_for_path(session_state.active_file_path)
                if tab_index >= 0:
                    self._set_current_tab_index(tab_index)

            if session_state.project_tree is not None and self._restore_tree_state is not None:
                self._restore_tree_state(session_state.project_tree)
            elif session_state.active_file_path and self._reveal_tree_path is not None:
                self._reveal_tree_path(session_state.active_file_path)

            if self._refresh_breakpoints_list is not None:
                self._refresh_breakpoints_list()
        finally:
            if self._set_tree_reveal_suppressed is not None:
                self._set_tree_reveal_suppressed(False)


def restore_editor_cursor_and_scroll(editor_widget: CodeEditorWidget, file_state: SessionFileState) -> None:
    """Apply saved cursor and scroll position to an open editor widget."""
    target_line = max(1, file_state.cursor_line)
    target_column = max(1, file_state.cursor_column)
    document = editor_widget.document()
    block = document.findBlockByNumber(target_line - 1)
    if block.isValid():
        max_column_offset = max(0, block.length() - 1)
        column_offset = min(target_column - 1, max_column_offset)
        target_position = block.position() + column_offset
    else:
        target_position = max(0, document.characterCount() - 1)
    cursor = editor_widget.textCursor()
    cursor.setPosition(target_position)
    editor_widget.setTextCursor(cursor)
    scroll_position = max(0, file_state.scroll_position)
    QTimer.singleShot(0, lambda widget=editor_widget, value=scroll_position: widget.verticalScrollBar().setValue(value))
