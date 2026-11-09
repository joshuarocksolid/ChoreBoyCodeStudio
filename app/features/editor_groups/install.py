from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.shell.shell_composition_context import ShellCompositionContext


def install_editor_groups(ctx: "ShellCompositionContext") -> None:
    from app.features.editor_groups.controller import EditorGroupsController
    from app.shell.shell_composition_context import bind_private_attrs

    bind_private_attrs(
        ctx.w,
        {
            "_editor_groups": EditorGroupsController(ctx.w),
        },
    )


__all__ = ["install_editor_groups"]
