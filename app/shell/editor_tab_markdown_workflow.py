"""Markdown tab mode actions, menu state, and pane materialization."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide2.QtCore import QPoint
from PySide2.QtWidgets import QMenu, QTabWidget, QWidget

from app.editors.code_editor_widget import CodeEditorWidget
from app.editors.editor_manager import EditorManager
from app.editors.markdown_editor_pane import MarkdownEditorPane, MarkdownPreviewMode
from app.editors.markdown_rendering import is_markdown_path, qt_markdown_supported
from app.shell.editor_tab_host_protocols import EditorTabMarkdownHost
from app.shell.markdown_tab_registry import MarkdownTabRegistry
from app.shell.theme_tokens import ShellThemeTokens


class EditorTabMarkdownWorkflow:
    """Owns markdown pane registry helpers and view-mode command handlers."""

    def __init__(
        self,
        *,
        host: EditorTabMarkdownHost,
        editor_manager: EditorManager,
        markdown_registry: MarkdownTabRegistry,
        refresh_markdown_action_states: Callable[[], None],
    ) -> None:
        self._host = host
        self._editor_manager = editor_manager
        self._markdown_registry = markdown_registry
        self._refresh_markdown_action_states = refresh_markdown_action_states

    def set_editor_manager(self, editor_manager: EditorManager) -> None:
        self._editor_manager = editor_manager

    def active_markdown_pane(self) -> MarkdownEditorPane | None:
        active_tab = self._editor_manager.active_tab()
        if active_tab is None:
            return None
        return self._markdown_registry.pane_for_path(active_tab.file_path)

    def set_active_markdown_mode(self, mode: str) -> None:
        markdown_pane = self.active_markdown_pane()
        if markdown_pane is None:
            return
        markdown_pane.set_mode(mode)
        self._refresh_markdown_action_states()

    def handle_markdown_show_source_action(self) -> None:
        self.set_active_markdown_mode(MarkdownPreviewMode.SOURCE)

    def handle_markdown_show_preview_action(self) -> None:
        self.set_active_markdown_mode(MarkdownPreviewMode.PREVIEW)

    def handle_markdown_show_split_action(self) -> None:
        self.set_active_markdown_mode(MarkdownPreviewMode.SPLIT)

    def handle_markdown_toggle_preview_action(self) -> None:
        markdown_pane = self.active_markdown_pane()
        if markdown_pane is None:
            return
        markdown_pane.toggle_preview()
        self._refresh_markdown_action_states()

    def refresh_markdown_action_states(self) -> None:
        menu_registry = self._host.menu_registry()
        if menu_registry is None:
            return
        markdown_pane = self.active_markdown_pane()
        enabled = markdown_pane is not None
        current_mode = markdown_pane.mode() if markdown_pane is not None else None
        for action_id, mode in (
            ("shell.action.view.markdownShowSource", MarkdownPreviewMode.SOURCE),
            ("shell.action.view.markdownShowPreview", MarkdownPreviewMode.PREVIEW),
            ("shell.action.view.markdownShowSplit", MarkdownPreviewMode.SPLIT),
        ):
            action = menu_registry.action(action_id)
            if action is not None:
                action.setEnabled(enabled)
                if enabled and action.isCheckable():
                    action.setChecked(current_mode == mode)
        toggle_action = menu_registry.action("shell.action.view.markdownTogglePreview")
        if toggle_action is not None:
            toggle_action.setEnabled(enabled)

    def wrap_tab_content_if_markdown(
        self,
        *,
        editor_widget: CodeEditorWidget,
        file_path: str,
        parent: QTabWidget,
        theme_tokens: ShellThemeTokens,
        open_linked_file: Callable[[str], bool],
    ) -> QWidget:
        if not is_markdown_path(file_path) or not qt_markdown_supported():
            return editor_widget
        markdown_pane = MarkdownEditorPane(
            editor_widget,
            file_path,
            parent,
            local_link_callback=lambda linked_path: open_linked_file(linked_path),
            initial_mode=MarkdownPreviewMode.PREVIEW,
        )
        markdown_pane.apply_theme(theme_tokens)
        markdown_pane.mode_changed.connect(lambda _mode: self._refresh_markdown_action_states())
        self._markdown_registry.register(file_path, markdown_pane)
        return markdown_pane

    def append_context_menu_actions(
        self,
        menu: QMenu,
        file_path: str,
    ) -> tuple[Any | None, Any | None, Any | None]:
        markdown_pane = self._markdown_registry.pane_for_path(file_path)
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
        markdown_pane: MarkdownEditorPane | None,
        chosen: Any,
        markdown_source_action: Any | None,
        markdown_preview_action: Any | None,
        markdown_split_action: Any | None,
    ) -> bool:
        if markdown_pane is None:
            return False
        if chosen == markdown_source_action:
            self.set_active_markdown_mode(MarkdownPreviewMode.SOURCE)
            return True
        if chosen == markdown_preview_action:
            self.set_active_markdown_mode(MarkdownPreviewMode.PREVIEW)
            return True
        if chosen == markdown_split_action:
            self.set_active_markdown_mode(MarkdownPreviewMode.SPLIT)
            return True
        return False

    def clear_registry(self) -> None:
        self._markdown_registry.clear()


__all__ = ["EditorTabMarkdownWorkflow"]
