"""Factory for :class:`EditorSyncWorkflow` wired to a MainWindow instance."""

from __future__ import annotations

from typing import Any

from app.shell.editor_sync_workflow import EditorSyncWorkflow


class MainWindowEditorSyncHost:
    """Host ports for ``EditorSyncWorkflow`` backed by a MainWindow instance."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def advance_buffer_revision(self, file_path: str) -> None:
        self._window._editor_tab_workflow.advance_buffer_revision(file_path)

    def apply_detected_indentation(
        self,
        file_path: str,
        editor_widget: object,
        content: str,
    ) -> None:
        self._window._editor_tab_workflow.apply_detected_indentation_for_widget(
            file_path,
            editor_widget,
            content,
        )

    def tab_index_for_path(self, file_path: str) -> int:
        return self._window._editor_tab_workflow.tab_index_for_path(file_path)

    def has_editor_tabs_widget(self) -> bool:
        return self._window._editor_tabs_widget is not None

    def refresh_tab_presentation(self, file_path: str) -> None:
        self._window._editor_tab_workflow.refresh_tab_presentation(file_path)


def build_editor_sync_workflow(window: Any) -> EditorSyncWorkflow:
    return EditorSyncWorkflow(
        editor_manager=window._editor_manager,
        host=MainWindowEditorSyncHost(window),
    )


__all__ = ["MainWindowEditorSyncHost", "build_editor_sync_workflow"]
