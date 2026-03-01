"""Menu bar stubs for the T05 shell.

Menus in this module intentionally avoid wiring project/editor/run logic.
They provide stable action IDs so future tasks can connect behavior.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class MenuStubRegistry:
    """Stores stable references to menu actions by ID."""

    actions: dict[str, Any]

    def action(self, action_id: str) -> Any:
        return self.actions.get(action_id)


def build_menu_stubs(main_window: Any) -> MenuStubRegistry:
    """Create top-level shell menus with placeholder actions."""
    actions: dict[str, Any] = {}
    menu_bar = main_window.menuBar()
    menu_bar.setObjectName("shell.menuBar")

    file_menu = menu_bar.addMenu("&File")
    file_menu.setObjectName("shell.menu.file")
    _register_menu_action(file_menu, actions, "shell.action.file.newProject", "New Project...", "Ctrl+N")
    _register_menu_action(file_menu, actions, "shell.action.file.openProject", "Open Project...", "Ctrl+O")
    _register_menu_action(file_menu, actions, "shell.action.file.openRecent", "Open Recent")
    file_menu.addSeparator()
    _register_menu_action(file_menu, actions, "shell.action.file.save", "Save", "Ctrl+S")
    _register_menu_action(file_menu, actions, "shell.action.file.saveAs", "Save As...")
    _register_menu_action(file_menu, actions, "shell.action.file.saveAll", "Save All", "Ctrl+Shift+S")
    file_menu.addSeparator()
    _register_menu_action(file_menu, actions, "shell.action.file.settings", "Settings...")
    file_menu.addSeparator()
    _register_menu_action(
        file_menu,
        actions,
        "shell.action.file.exit",
        "Exit",
        "Ctrl+Q",
        enabled=True,
        callback=main_window.close,
    )

    edit_menu = menu_bar.addMenu("&Edit")
    edit_menu.setObjectName("shell.menu.edit")
    _register_menu_action(edit_menu, actions, "shell.action.edit.undo", "Undo", "Ctrl+Z")
    _register_menu_action(edit_menu, actions, "shell.action.edit.redo", "Redo", "Ctrl+Shift+Z")
    edit_menu.addSeparator()
    _register_menu_action(edit_menu, actions, "shell.action.edit.find", "Find", "Ctrl+F")
    _register_menu_action(edit_menu, actions, "shell.action.edit.replace", "Replace", "Ctrl+H")
    _register_menu_action(edit_menu, actions, "shell.action.edit.goToLine", "Go To Line", "Ctrl+G")

    run_menu = menu_bar.addMenu("&Run")
    run_menu.setObjectName("shell.menu.run")
    _register_menu_action(run_menu, actions, "shell.action.run.run", "Run", "F5")
    _register_menu_action(run_menu, actions, "shell.action.run.stop", "Stop", "Shift+F5")
    _register_menu_action(run_menu, actions, "shell.action.run.clearConsole", "Clear Console")

    tools_menu = menu_bar.addMenu("&Tools")
    tools_menu.setObjectName("shell.menu.tools")
    _register_menu_action(tools_menu, actions, "shell.action.tools.lintCurrentFile", "Lint Current File")
    _register_menu_action(
        tools_menu,
        actions,
        "shell.action.tools.projectHealthCheck",
        "Project Health Check",
    )
    _register_menu_action(
        tools_menu,
        actions,
        "shell.action.tools.headlessNotes",
        "FreeCAD Headless Notes",
    )

    help_menu = menu_bar.addMenu("&Help")
    help_menu.setObjectName("shell.menu.help")
    _register_menu_action(help_menu, actions, "shell.action.help.gettingStarted", "Getting Started")
    _register_menu_action(help_menu, actions, "shell.action.help.shortcuts", "Keyboard Shortcuts")
    _register_menu_action(help_menu, actions, "shell.action.help.about", "About")

    return MenuStubRegistry(actions=actions)


def _register_menu_action(
    menu: Any,
    action_lookup: dict[str, Any],
    action_id: str,
    label: str,
    shortcut: str | None = None,
    enabled: bool = False,
    callback: Callable[[], None] | None = None,
) -> None:
    action_class = importlib.import_module("PySide2.QtWidgets").QAction

    action = action_class(label, menu)
    action.setObjectName(action_id)
    if shortcut:
        action.setShortcut(shortcut)
    action.setEnabled(enabled)
    if callback is not None:
        action.triggered.connect(callback)
    menu.addAction(action)
    action_lookup[action_id] = action
