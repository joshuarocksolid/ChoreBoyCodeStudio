"""Composition-level registry for editor tab content (code + markdown panes)."""

from __future__ import annotations

from app.editors.markdown_editor_pane import MarkdownEditorPane
from app.shell.markdown_tab_registry import MarkdownTabRegistry
from app.shell.theme_tokens import ShellThemeTokens


class EditorTabContentRegistry:
    """Single shell seam for markdown pane registry operations."""

    def __init__(self, markdown_panes_by_path: dict[str, MarkdownEditorPane]) -> None:
        self._markdown_panes_by_path = markdown_panes_by_path
        self._markdown_registry = MarkdownTabRegistry(markdown_panes_by_path)

    @property
    def markdown_panes_by_path(self) -> dict[str, MarkdownEditorPane]:
        return self._markdown_panes_by_path

    def markdown_registry(self) -> MarkdownTabRegistry:
        return self._markdown_registry

    def apply_all_markdown_themes(self, tokens: ShellThemeTokens) -> None:
        self._markdown_registry.apply_all_themes(tokens)


__all__ = ["EditorTabContentRegistry"]
