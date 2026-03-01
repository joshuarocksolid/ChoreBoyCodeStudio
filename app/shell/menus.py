"""Menu construction helpers for the shell window."""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class MenuStubRegistry:
    """Stores stable references to menu actions by ID."""

    actions: dict[str, Any]
    menus: dict[str, Any] = field(default_factory=dict)

    def action(self, action_id: str) -> Any:
        return self.actions.get(action_id)

    def menu(self, menu_id: str) -> Any:
        return self.menus.get(menu_id)


@dataclass(frozen=True)
class MenuCallbacks:
    """Optional callbacks that wire shell behavior to menu actions."""

    on_new_project: Callable[[], object] | None = None
    on_open_project: Callable[[], object] | None = None
    on_file_menu_about_to_show: Callable[[], object] | None = None
    on_save: Callable[[], object] | None = None
    on_save_all: Callable[[], object] | None = None
    on_run: Callable[[], object] | None = None
    on_stop: Callable[[], object] | None = None
    on_clear_console: Callable[[], object] | None = None
    on_project_health_check: Callable[[], object] | None = None
    on_generate_support_bundle: Callable[[], object] | None = None


@dataclass(frozen=True)
class RecentProjectMenuItem:
    """Menu-display model for a recent project entry."""

    project_path: str
    display_text: str


def build_recent_project_menu_items(project_paths: list[str]) -> list[RecentProjectMenuItem]:
    """Normalize recent-project paths into deterministic menu items."""
    deduped: list[str] = []
    seen: set[str] = set()
    for raw_path in project_paths:
        normalized = raw_path.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)

    items: list[RecentProjectMenuItem] = []
    for project_path in deduped:
        leaf_name = Path(project_path).name or project_path
        items.append(RecentProjectMenuItem(project_path=project_path, display_text=f"{leaf_name} — {project_path}"))
    return items


def build_menu_stubs(main_window: Any, callbacks: MenuCallbacks | None = None) -> MenuStubRegistry:
    """Create top-level shell menus and stable action IDs."""
    callback_registry = callbacks or MenuCallbacks()
    actions: dict[str, Any] = {}
    menus: dict[str, Any] = {}
    menu_bar = main_window.menuBar()
    menu_bar.setObjectName("shell.menuBar")

    file_menu = menu_bar.addMenu("&File")
    file_menu.setObjectName("shell.menu.file")
    if callback_registry.on_file_menu_about_to_show is not None:
        file_menu.aboutToShow.connect(callback_registry.on_file_menu_about_to_show)
    _register_menu_action(
        file_menu,
        actions,
        "shell.action.file.newProject",
        "New Project...",
        "Ctrl+N",
        enabled=True,
        callback=callback_registry.on_new_project,
    )
    _register_menu_action(
        file_menu,
        actions,
        "shell.action.file.openProject",
        "Open Project...",
        "Ctrl+O",
        enabled=True,
        callback=callback_registry.on_open_project,
    )
    open_recent_menu = file_menu.addMenu("Open Recent")
    open_recent_menu.setObjectName("shell.menu.file.openRecent")
    menus["shell.menu.file.openRecent"] = open_recent_menu
    file_menu.addSeparator()
    _register_menu_action(
        file_menu,
        actions,
        "shell.action.file.save",
        "Save",
        "Ctrl+S",
        enabled=True,
        callback=callback_registry.on_save,
    )
    _register_menu_action(file_menu, actions, "shell.action.file.saveAs", "Save As...")
    _register_menu_action(
        file_menu,
        actions,
        "shell.action.file.saveAll",
        "Save All",
        "Ctrl+Shift+S",
        enabled=True,
        callback=callback_registry.on_save_all,
    )
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
    _register_menu_action(
        run_menu,
        actions,
        "shell.action.run.run",
        "Run",
        "F5",
        callback=callback_registry.on_run,
    )
    _register_menu_action(
        run_menu,
        actions,
        "shell.action.run.stop",
        "Stop",
        "Shift+F5",
        callback=callback_registry.on_stop,
    )
    _register_menu_action(
        run_menu,
        actions,
        "shell.action.run.clearConsole",
        "Clear Console",
        callback=callback_registry.on_clear_console,
    )

    tools_menu = menu_bar.addMenu("&Tools")
    tools_menu.setObjectName("shell.menu.tools")
    _register_menu_action(tools_menu, actions, "shell.action.tools.lintCurrentFile", "Lint Current File")
    _register_menu_action(
        tools_menu,
        actions,
        "shell.action.tools.projectHealthCheck",
        "Project Health Check",
        callback=callback_registry.on_project_health_check,
    )
    _register_menu_action(
        tools_menu,
        actions,
        "shell.action.tools.generateSupportBundle",
        "Generate Support Bundle",
        callback=callback_registry.on_generate_support_bundle,
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

    return MenuStubRegistry(actions=actions, menus=menus)


def _register_menu_action(
    menu: Any,
    action_lookup: dict[str, Any],
    action_id: str,
    label: str,
    shortcut: str | None = None,
    enabled: bool = False,
    callback: Callable[[], object] | None = None,
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
