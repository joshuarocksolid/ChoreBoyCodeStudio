"""Workspace controller for open editor widgets and buffer generations."""
from __future__ import annotations

from collections.abc import Callable

from app.editors.code_editor_widget import CodeEditorWidget
from app.editors.editor_manager import EditorManager


class EditorWorkspaceController:
    """Owns open-editor widgets and monotonic buffer revisions, keyed by buffer id.

    Path lookups resolve through the live editor manager at call time so a
    rename or move never has to rewrite these maps.
    """

    def __init__(self, editor_manager: Callable[[], EditorManager]) -> None:
        self._editor_manager = editor_manager
        self._editor_widgets_by_path: dict[str, CodeEditorWidget] = {}
        self._buffer_revisions: dict[str, int] = {}
        self._next_buffer_revision = 0

    @property
    def editor_widgets_by_path(self) -> dict[str, CodeEditorWidget]:
        """Widgets keyed by buffer id (attribute name kept for the shell field contract)."""
        return self._editor_widgets_by_path

    def buffer_id_for_path(self, file_path: str) -> str | None:
        tab = self._editor_manager().get_tab(file_path)
        return None if tab is None else tab.buffer_id

    def register_editor(self, buffer_id: str, editor_widget: CodeEditorWidget) -> int:
        self._editor_widgets_by_path[buffer_id] = editor_widget
        return self._advance(buffer_id)

    def repoint_editor(self, buffer_id: str, editor_widget: CodeEditorWidget) -> None:
        """Make another view of an open buffer its primary view (focus moved groups)."""
        if buffer_id in self._editor_widgets_by_path:
            self._editor_widgets_by_path[buffer_id] = editor_widget

    def widget_for_path(self, file_path: str) -> CodeEditorWidget | None:
        buffer_id = self.buffer_id_for_path(file_path)
        return None if buffer_id is None else self._editor_widgets_by_path.get(buffer_id)

    def widget_for_buffer_id(self, buffer_id: str) -> CodeEditorWidget | None:
        return self._editor_widgets_by_path.get(buffer_id)

    def pop_editor(self, buffer_id: str) -> CodeEditorWidget | None:
        self._buffer_revisions.pop(buffer_id, None)
        return self._editor_widgets_by_path.pop(buffer_id, None)

    def pop_editor_for_path(self, file_path: str) -> CodeEditorWidget | None:
        buffer_id = self.buffer_id_for_path(file_path)
        return None if buffer_id is None else self.pop_editor(buffer_id)

    def open_editor_paths(self) -> list[str]:
        return [
            tab.file_path
            for tab in self._editor_manager().all_tabs()
            if tab.buffer_id in self._editor_widgets_by_path
        ]

    def widgets_by_open_path(self) -> dict[str, CodeEditorWidget]:
        """Snapshot of open widgets keyed by each buffer's current path."""
        return {
            tab.file_path: self._editor_widgets_by_path[tab.buffer_id]
            for tab in self._editor_manager().all_tabs()
            if tab.buffer_id in self._editor_widgets_by_path
        }

    def advance_buffer_revision(self, file_path: str) -> int:
        buffer_id = self.buffer_id_for_path(file_path)
        if buffer_id is None:
            self._next_buffer_revision += 1
            return self._next_buffer_revision
        return self._advance(buffer_id)

    def buffer_revision(self, file_path: str) -> int | None:
        buffer_id = self.buffer_id_for_path(file_path)
        return None if buffer_id is None else self._buffer_revisions.get(buffer_id)

    def buffer_revision_for_buffer_id(self, buffer_id: str) -> int | None:
        return self._buffer_revisions.get(buffer_id)

    def clear(self) -> None:
        self._editor_widgets_by_path.clear()
        self._buffer_revisions.clear()
        self._next_buffer_revision = 0

    def _advance(self, buffer_id: str) -> int:
        self._next_buffer_revision += 1
        self._buffer_revisions[buffer_id] = self._next_buffer_revision
        return self._next_buffer_revision
