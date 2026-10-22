"""Markdown tab mode actions and menu state.

The first pane is created by the Markdown tab-content provider. A second editor
group builds its own pane in the editor-groups feature. This workflow talks to
whichever pane the focused tab is showing, and does not import the feature package.
"""

from __future__ import annotations

from typing import Any

from app.qt.QtWidgets import QMenu, QTabWidget, QWidget

from app.editors.editor_manager import EditorManager
from app.shell.editor_tab_host_protocols import EditorTabMarkdownHost
from app.shell.editor_tab_page import EditorTabPage


_MODE_SOURCE = "source"
_MODE_PREVIEW = "preview"
_MODE_SPLIT = "split"


def _pane_of_widget(widget: QWidget | None) -> Any | None:
    if not hasattr(widget, "set_mode") or not hasattr(widget, "toggle_preview"):
        return None
    return widget


def markdown_pane_of_page(page: QWidget | None) -> Any | None:
    """The markdown pane an editor tab page shows, or None."""
    if not isinstance(page, EditorTabPage):
        return None
    return _pane_of_widget(page.content())


class EditorTabMarkdownWorkflow:
    """Owns markdown view-mode command handlers for the active tab."""

    def __init__(
        self,
        *,
        host: EditorTabMarkdownHost,
        editor_manager: EditorManager,
        refresh_markdown_action_states: Any,
    ) -> None:
        self._host = host
        self._editor_manager = editor_manager
        self._refresh_markdown_action_states = refresh_markdown_action_states

    def set_editor_manager(self, editor_manager: EditorManager) -> None:
        self._editor_manager = editor_manager

    def active_markdown_pane(self) -> Any | None:
        tabs = self._host.editor_tabs_widget()
        if tabs is not None:
            pane = markdown_pane_of_page(tabs.currentWidget())
            if pane is not None:
                return pane
        active_tab = self._editor_manager.active_tab()
        if active_tab is None:
            return None
        return self.pane_for_path(active_tab.file_path)

    def markdown_pane_for_tab(self, tabs: QTabWidget, tab_index: int, file_path: str) -> Any | None:
        """The pane that tab shows, else the buffer's registered surface."""
        pane = markdown_pane_of_page(tabs.widget(tab_index))
        if pane is not None:
            return pane
        return self.pane_for_path(file_path)

    def set_active_markdown_mode(self, mode: str) -> None:
        markdown_pane = self.active_markdown_pane()
        if markdown_pane is None:
            return
        markdown_pane.set_mode(mode)
        self._refresh_markdown_action_states()

    def handle_markdown_show_source_action(self) -> None:
        self.set_active_markdown_mode(_MODE_SOURCE)

    def handle_markdown_show_preview_action(self) -> None:
        self.set_active_markdown_mode(_MODE_PREVIEW)

    def handle_markdown_show_split_action(self) -> None:
        self.set_active_markdown_mode(_MODE_SPLIT)

    def handle_markdown_toggle_preview_action(self) -> None:
        markdown_pane = self.active_markdown_pane()
        if markdown_pane is None:
            toggle = self._source_view_toggle()
            if toggle is not None:
                toggle()
            return
        markdown_pane.toggle_preview()
        self._refresh_markdown_action_states()

    def _source_view_toggle(self) -> Any | None:
        active_tab = self._editor_manager.active_tab()
        if active_tab is None:
            return None
        surface = self._host.tab_content_registry().surface_for_path(active_tab.file_path)
        if surface is None:
            return None
        toggle = getattr(surface, "toggle_source_view", None)
        if not callable(toggle):
            return None
        return toggle

    def refresh_markdown_action_states(self) -> None:
        menu_registry = self._host.menu_registry()
        if menu_registry is None:
            return
        markdown_pane = self.active_markdown_pane()
        enabled = markdown_pane is not None
        current_mode = markdown_pane.mode() if markdown_pane is not None else None
        for action_id, mode in (
            ("shell.action.view.markdownShowSource", _MODE_SOURCE),
            ("shell.action.view.markdownShowPreview", _MODE_PREVIEW),
            ("shell.action.view.markdownShowSplit", _MODE_SPLIT),
        ):
            action = menu_registry.action(action_id)
            if action is not None:
                action.setEnabled(enabled)
                if enabled and action.isCheckable():
                    action.setChecked(current_mode == mode)
        toggle_action = menu_registry.action("shell.action.view.markdownTogglePreview")
        if toggle_action is not None:
            toggle_action.setEnabled(enabled or self._source_view_toggle() is not None)

    def append_context_menu_actions(
        self,
        menu: QMenu,
        markdown_pane: Any | None,
    ) -> tuple[Any | None, Any | None, Any | None]:
        if markdown_pane is None:
            return None, None, None
        markdown_source_action = menu.addAction("Markdown: Show Source")
        markdown_preview_action = menu.addAction("Markdown: Show Preview")
        markdown_split_action = menu.addAction("Markdown: Show Split View")
        menu.addSeparator()
        return markdown_source_action, markdown_preview_action, markdown_split_action

    def handle_context_menu_choice(
        self,
        *,
        markdown_pane: Any | None,
        chosen: Any,
        markdown_source_action: Any | None,
        markdown_preview_action: Any | None,
        markdown_split_action: Any | None,
    ) -> bool:
        if markdown_pane is None:
            return False
        modes = (
            (markdown_source_action, _MODE_SOURCE),
            (markdown_preview_action, _MODE_PREVIEW),
            (markdown_split_action, _MODE_SPLIT),
        )
        for action, mode in modes:
            if action is not None and chosen == action:
                markdown_pane.set_mode(mode)
                self._refresh_markdown_action_states()
                return True
        return False

    def clear_registry(self) -> None:
        self._host.tab_content_registry().forget_all()

    def pane_for_path(self, file_path: str) -> Any | None:
        surface = self._host.tab_content_registry().surface_for_path(file_path)
        if surface is None:
            panes = self._host.markdown_panes_by_path()
            return _pane_of_widget(panes.get(file_path))
        return _pane_of_widget(surface.widget())


__all__ = ["EditorTabMarkdownWorkflow", "markdown_pane_of_page"]
