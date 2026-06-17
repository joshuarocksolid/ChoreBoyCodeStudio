"""Shared markdown pane registry operations for editor and project-tree workflows."""

from __future__ import annotations

from collections.abc import Callable

from app.editors.code_editor_widget import CodeEditorWidget
from app.editors.markdown_editor_pane import MarkdownEditorPane
from app.shell.theme_tokens import ShellThemeTokens


class MarkdownTabRegistry:
    """Single source of truth for path-keyed markdown pane registry operations."""

    def __init__(self, panes_by_path: dict[str, MarkdownEditorPane]) -> None:
        self._panes_by_path = panes_by_path

    def pane_for_path(self, file_path: str) -> MarkdownEditorPane | None:
        return self._panes_by_path.get(file_path)

    def register(self, file_path: str, pane: MarkdownEditorPane) -> None:
        self._panes_by_path[file_path] = pane

    def clear(self) -> None:
        self._panes_by_path.clear()

    def release_widget(self, widget: CodeEditorWidget) -> bool:
        """Release the markdown pane wrapping ``widget``. Returns True if handled."""
        for file_path, markdown_pane in list(self._panes_by_path.items()):
            if markdown_pane.source_editor() is widget:
                self._panes_by_path.pop(file_path, None)
                markdown_pane.deleteLater()
                return True
        return False

    def rekey_for_widget(
        self,
        widget: CodeEditorWidget,
        new_path: str,
        *,
        is_markdown_path: Callable[[str], bool],
        on_unwrap: Callable[[MarkdownEditorPane, CodeEditorWidget], None] | None = None,
    ) -> None:
        for old_path, markdown_pane in list(self._panes_by_path.items()):
            if markdown_pane.source_editor() is widget:
                self._panes_by_path.pop(old_path, None)
                if is_markdown_path(new_path):
                    markdown_pane.set_file_path(new_path)
                    self._panes_by_path[new_path] = markdown_pane
                elif on_unwrap is not None:
                    on_unwrap(markdown_pane, widget)
                    markdown_pane.deleteLater()
                else:
                    markdown_pane.deleteLater()
                break

    def apply_all_themes(self, tokens: ShellThemeTokens) -> None:
        for markdown_pane in self._panes_by_path.values():
            markdown_pane.apply_theme(tokens)


def release_editor_widget(
    widget: CodeEditorWidget,
    *,
    registry: MarkdownTabRegistry,
    is_debug_execution_editor: Callable[[CodeEditorWidget], bool],
    clear_debug_execution_indicator: Callable[[], None],
) -> None:
    """Release an editor widget, unwrapping markdown panes when needed."""
    if is_debug_execution_editor(widget):
        clear_debug_execution_indicator()
    if registry.release_widget(widget):
        return
    widget.deleteLater()


__all__ = ["MarkdownTabRegistry", "release_editor_widget"]
