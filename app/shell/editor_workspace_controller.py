"""Workspace controller for open editor widgets and buffer generations."""
from __future__ import annotations

from app.editors.code_editor_widget import CodeEditorWidget


class EditorWorkspaceController:
    """Owns open-editor widget mapping and monotonic buffer revisions."""

    def __init__(self) -> None:
        self._editor_widgets_by_path: dict[str, CodeEditorWidget] = {}
        self._buffer_revisions: dict[str, int] = {}
        self._next_buffer_revision = 0

    @property
    def editor_widgets_by_path(self) -> dict[str, CodeEditorWidget]:
        return self._editor_widgets_by_path

    def register_editor(self, file_path: str, editor_widget: CodeEditorWidget) -> int:
        self._editor_widgets_by_path[file_path] = editor_widget
        return self.advance_buffer_revision(file_path)

    def widget_for_path(self, file_path: str) -> CodeEditorWidget | None:
        return self._editor_widgets_by_path.get(file_path)

    def pop_editor(self, file_path: str) -> CodeEditorWidget | None:
        self._buffer_revisions.pop(file_path, None)
        return self._editor_widgets_by_path.pop(file_path, None)

    def open_editor_paths(self) -> list[str]:
        return list(self._editor_widgets_by_path.keys())

    def advance_buffer_revision(self, file_path: str) -> int:
        self._next_buffer_revision += 1
        self._buffer_revisions[file_path] = self._next_buffer_revision
        return self._next_buffer_revision

    def buffer_revision(self, file_path: str) -> int | None:
        return self._buffer_revisions.get(file_path)

    def clear(self) -> None:
        self._editor_widgets_by_path.clear()
        self._buffer_revisions.clear()
        self._next_buffer_revision = 0
