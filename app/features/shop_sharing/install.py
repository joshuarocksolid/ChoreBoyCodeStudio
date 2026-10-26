"""Bind the shop-sharing controller. Widgets are built later, after the status bar exists."""

from __future__ import annotations

from app.shell.shell_composition_context import ShellCompositionContext, bind_private_attrs


def install_shop_sharing(ctx: ShellCompositionContext) -> None:
    """Runs before the status bar exists. ``build()`` in finalize creates the chip and the prompt."""
    from app.features.shop_sharing.service import shop_sharing_service
    from app.features.shop_sharing.window import ShopSharingShell, ShopSharingWindowPorts
    from app.shell.main_window_panels import _restore_python_console_history

    w = ctx.w
    bind_private_attrs(
        w,
        {
            "_shop_sharing": ShopSharingShell(
                w,
                shop_sharing_service(ctx.state_root),
                ShopSharingWindowPorts(
                    reload_settings=lambda: w._settings_apply_workflow.apply_reloaded_settings(
                        project_root=w._current_project_root()
                    ),
                    restore_console_history=lambda: _restore_python_console_history(w),
                    refresh_open_recent=lambda: w._file_project_commands_workflow.refresh_open_recent_menu(),
                    refresh_welcome=lambda: w._runtime_onboarding_workflow.refresh_welcome_project_list(),
                    open_settings=lambda: w._file_project_commands_workflow.handle_open_shop_sharing_setting(),
                ),
            ),
        },
    )


__all__ = ["install_shop_sharing"]
