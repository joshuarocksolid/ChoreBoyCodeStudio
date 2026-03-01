"""Shell toolbar construction helpers."""

from __future__ import annotations

from typing import Any

from app.shell.menus import MenuStubRegistry


def build_shell_toolbar(main_window: Any, menu_registry: MenuStubRegistry | None) -> Any | None:
    """Build and attach top run/debug toolbar from shared action registry."""
    if menu_registry is None:
        return None

    qtoolbar_class = __import__("PySide2.QtWidgets", fromlist=["QToolBar"]).QToolBar
    toolbar = qtoolbar_class("Run & Debug", main_window)
    toolbar.setObjectName("shell.toolbar.runDebug")
    toolbar.setMovable(False)

    for action_id in (
        "shell.action.run.run",
        "shell.action.run.debug",
        "shell.action.run.stop",
        "shell.action.run.restart",
        "shell.action.run.pythonConsole",
    ):
        action = menu_registry.action(action_id)
        if action is not None:
            toolbar.addAction(action)

    toolbar.addSeparator()
    for action_id in (
        "shell.action.run.continue",
        "shell.action.run.pause",
        "shell.action.run.stepOver",
        "shell.action.run.stepInto",
        "shell.action.run.stepOut",
        "shell.action.run.toggleBreakpoint",
    ):
        action = menu_registry.action(action_id)
        if action is not None:
            toolbar.addAction(action)

    main_window.addToolBar(toolbar)
    return toolbar
