"""Editor-tab presentation and state coordination helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide2.QtWidgets import QTabBar


class EditorTabsCoordinator:
    """Keeps editor-manager tab state and Qt tab chrome in sync."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def tab_index_for_path(self, file_path: str) -> int:
        window = self._window
        if window._editor_tabs_widget is None:
            return -1

        normalized_path = str(Path(file_path).expanduser().resolve())
        for index in range(window._editor_tabs_widget.count()):
            if window._editor_tabs_widget.tabToolTip(index) == normalized_path:
                return index
        return -1

    def refresh_tab_presentation(self, file_path: str) -> None:
        window = self._window
        if window._editor_tabs_widget is None:
            return
        tab_state = window._editor_manager.get_tab(file_path)
        if tab_state is None:
            return
        tab_index = window._tab_index_for_path(file_path)
        if tab_index < 0:
            return
        suffix = " *" if tab_state.is_dirty else ""
        window._editor_tabs_widget.setTabText(tab_index, f"{tab_state.display_name}{suffix}")
        tab_bar = window._editor_tabs_widget.tabBar()
        if isinstance(tab_bar, QTabBar):
            tab_bar.setTabData(
                tab_index,
                {"is_preview": tab_state.is_preview, "file_path": tab_state.file_path},
            )
            tab_bar.update()

    def promote_preview_tab(self, file_path: str) -> bool:
        window = self._window
        promoted_tab = window._editor_manager.promote_tab(file_path)
        if promoted_tab is None:
            return False
        if not promoted_tab.is_preview:
            window._refresh_tab_presentation(promoted_tab.file_path)
        return True

    def promote_existing_preview_tab(self) -> bool:
        window = self._window
        preview_tab = window._editor_manager.preview_tab()
        if preview_tab is None:
            return False
        return window._promote_preview_tab(preview_tab.file_path)

    def active_editor_widget(self) -> object | None:
        window = self._window
        active_tab = window._editor_manager.active_tab()
        if active_tab is None:
            return None
        return window._editor_widgets_by_path.get(active_tab.file_path)

    def advance_buffer_revision(self, file_path: str) -> int:
        return self._window._workspace_controller.advance_buffer_revision(file_path)

    def buffer_revision(self, file_path: str) -> int | None:
        return self._window._workspace_controller.buffer_revision(file_path)
