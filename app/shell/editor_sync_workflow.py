"""Unified disk-to-editor synchronization for open tabs."""

from __future__ import annotations

from enum import Enum
from typing import Protocol

from app.editors.editor_manager import EditorManager


class EditorDiskSyncSource(str, Enum):
    """Origin of a disk-to-editor content apply."""

    EXTERNAL_RELOAD = "external_reload"
    TOOL_REFRESH = "tool_refresh"
    QUICK_FIX = "quick_fix"


class EditorWidgetPort(Protocol):
    """Minimal editor surface needed for disk-to-buffer sync."""

    def blockSignals(self, blocked: bool) -> bool:
        ...

    def setPlainText(self, text: str) -> None:
        ...


class EditorSyncHostPorts(Protocol):
    """Host callbacks required to mutate open editor tabs."""

    def editor_widget_for_path(self, file_path: str) -> EditorWidgetPort | None:
        ...

    def advance_buffer_revision(self, file_path: str) -> int:
        ...

    def apply_detected_indentation(
        self,
        file_path: str,
        editor_widget: EditorWidgetPort,
        source_text: str,
    ) -> None:
        ...

    def tab_index_for_path(self, file_path: str) -> int:
        ...

    def refresh_tab_presentation(self, file_path: str) -> None:
        ...

    def has_editor_tabs_widget(self) -> bool:
        ...


class EditorSyncWorkflow:
    """Owns applying on-disk text into open editor buffers."""

    def __init__(
        self,
        *,
        editor_manager: EditorManager,
        host: EditorSyncHostPorts,
    ) -> None:
        self._editor_manager = editor_manager
        self._host = host

    def apply_disk_content(
        self,
        file_path: str,
        text: str,
        *,
        source: EditorDiskSyncSource,
        last_known_mtime: float | None = None,
    ) -> bool:
        """Replace the open tab buffer with ``text`` and mark it saved."""
        del source  # reserved for caller-specific post-sync hooks
        tab_state = self._editor_manager.get_tab(file_path)
        editor_widget = self._host.editor_widget_for_path(file_path)
        if tab_state is None or editor_widget is None:
            return False

        editor_widget.blockSignals(True)
        editor_widget.setPlainText(text)
        editor_widget.blockSignals(False)
        self._host.advance_buffer_revision(file_path)
        self._host.apply_detected_indentation(file_path, editor_widget, text)
        updated_tab = self._editor_manager.update_tab_content(file_path, text)
        resolved_mtime = last_known_mtime
        if resolved_mtime is None:
            resolved_mtime = self._editor_manager.current_disk_mtime(file_path)
        updated_tab.mark_saved(last_known_mtime=resolved_mtime)
        tab_index = self._host.tab_index_for_path(file_path)
        if self._host.has_editor_tabs_widget() and tab_index >= 0:
            self._host.refresh_tab_presentation(file_path)
        return True
