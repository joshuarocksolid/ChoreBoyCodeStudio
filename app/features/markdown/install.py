"""Install the Markdown tab-content provider.

Module-level imports stay light. The pane and the provider are imported inside
``install_markdown``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.shell.shell_composition_context import ShellCompositionContext


def install_markdown(ctx: "ShellCompositionContext") -> None:
    from app.features.markdown.markdown_editor_pane import MarkdownEditorPane
    from app.features.markdown.provider import MarkdownTabContentProvider
    from app.shell.shell_composition_context import bind_private_attrs

    window = ctx.w
    panes_by_path: dict[str, MarkdownEditorPane] = {}

    def on_mode_changed() -> None:
        workflow = getattr(window, "_editor_tab_workflow", None)
        if workflow is not None:
            workflow.refresh_markdown_action_states()

    window._tab_content_registry.register(
        MarkdownTabContentProvider(panes_by_path, on_mode_changed=on_mode_changed)
    )
    bind_private_attrs(window, {"_markdown_panes_by_path": panes_by_path})


__all__ = ["install_markdown"]
