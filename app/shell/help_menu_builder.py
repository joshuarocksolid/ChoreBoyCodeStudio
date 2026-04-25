"""Help menu construction."""

from __future__ import annotations

from app.shell.menu_action_builder import register_menu_action
from app.shell.menu_build_context import MenuBuildContext


def build_help_menu(ctx: MenuBuildContext) -> object:
    callbacks = ctx.callbacks
    help_menu = ctx.menu_bar.addMenu("&Help")
    help_menu.setObjectName("shell.menu.help")
    ctx.menus["shell.menu.help"] = help_menu

    register_menu_action(
        qt_widgets=ctx.qt_widgets,
        menu=help_menu,
        action_lookup=ctx.actions,
        action_id="shell.action.help.loadExampleProject",
        label="Load Example Project...",
        enabled=True,
        callback=callbacks.on_help_load_example_project,
    )
    help_menu.addSeparator()
    for action_id, label, callback in [
        ("shell.action.help.openAppLog", "Open Application Log", callbacks.on_help_open_app_log),
        ("shell.action.help.openLogFolder", "Open Log Folder", callbacks.on_help_open_log_folder),
    ]:
        register_menu_action(
            qt_widgets=ctx.qt_widgets,
            menu=help_menu,
            action_lookup=ctx.actions,
            action_id=action_id,
            label=label,
            enabled=True,
            callback=callback,
        )

    help_menu.addSeparator()
    for action_id, label, callback in [
        ("shell.action.help.runtimeOnboarding", "Runtime Onboarding...", callbacks.on_help_runtime_onboarding),
        ("shell.action.help.gettingStarted", "Getting Started", callbacks.on_help_getting_started),
        ("shell.action.help.shortcuts", "Keyboard Shortcuts", callbacks.on_help_shortcuts),
        ("shell.action.help.about", "About", callbacks.on_help_about),
    ]:
        register_menu_action(
            qt_widgets=ctx.qt_widgets,
            menu=help_menu,
            action_lookup=ctx.actions,
            action_id=action_id,
            label=label,
            enabled=True,
            callback=callback,
        )

    return help_menu
