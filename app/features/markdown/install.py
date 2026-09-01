from __future__ import annotations

from app.features.markdown.markdown_editor_pane import MarkdownEditorPane
from app.shell.editor_tab_content_registry import EditorTabContentRegistry
from app.shell.shell_composition_context import ShellCompositionContext, bind_private_attrs


def install_markdown(ctx: ShellCompositionContext) -> None:
    markdown_panes_by_path: dict[str, MarkdownEditorPane] = {}
    bind_private_attrs(
        ctx.w,
        {
            "_markdown_panes_by_path": markdown_panes_by_path,
            "_tab_content_registry": EditorTabContentRegistry(markdown_panes_by_path),
        },
    )


__all__ = ["install_markdown"]
