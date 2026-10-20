from __future__ import annotations

from app.shell.shell_composition_context import ShellCompositionContext, bind_private_attrs


def install_editor_groups(ctx: ShellCompositionContext) -> None:
    from app.features.editor_groups.controller import EditorGroupsController

    bind_private_attrs(
        ctx.w,
        {
            "_editor_groups": EditorGroupsController(ctx.w),
        },
    )


__all__ = ["install_editor_groups"]
