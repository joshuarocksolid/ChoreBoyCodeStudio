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
    on_open_settings: Callable[[], object] | None = None
    on_quick_open: Callable[[], object] | None = None
    on_find: Callable[[], object] | None = None
    on_replace: Callable[[], object] | None = None
    on_go_to_line: Callable[[], object] | None = None
    on_find_in_files: Callable[[], object] | None = None
    on_find_references: Callable[[], object] | None = None
    on_rename_symbol: Callable[[], object] | None = None
    on_toggle_comment: Callable[[], object] | None = None
    on_indent: Callable[[], object] | None = None
    on_outdent: Callable[[], object] | None = None
    on_go_to_definition: Callable[[], object] | None = None
    on_signature_help: Callable[[], object] | None = None
    on_hover_info: Callable[[], object] | None = None
    on_analyze_imports: Callable[[], object] | None = None
    on_show_outline: Callable[[], object] | None = None
    on_run: Callable[[], object] | None = None
    on_debug: Callable[[], object] | None = None
    on_run_pytest_project: Callable[[], object] | None = None
    on_run_pytest_current_file: Callable[[], object] | None = None
    on_run_with_config: Callable[[], object] | None = None
    on_manage_run_configs: Callable[[], object] | None = None
    on_stop: Callable[[], object] | None = None
    on_restart: Callable[[], object] | None = None
    on_continue_debug: Callable[[], object] | None = None
    on_pause_debug: Callable[[], object] | None = None
    on_step_over: Callable[[], object] | None = None
    on_step_into: Callable[[], object] | None = None
    on_step_out: Callable[[], object] | None = None
    on_toggle_breakpoint: Callable[[], object] | None = None
    on_start_python_console: Callable[[], object] | None = None
    on_clear_console: Callable[[], object] | None = None
    on_reset_layout: Callable[[], object] | None = None
    on_set_theme_system: Callable[[], object] | None = None
    on_set_theme_light: Callable[[], object] | None = None
    on_set_theme_dark: Callable[[], object] | None = None
    on_format_current_file: Callable[[], object] | None = None
    on_lint_current_file: Callable[[], object] | None = None
    on_apply_safe_fixes: Callable[[], object] | None = None
    on_rebuild_intelligence_cache: Callable[[], object] | None = None
    on_project_health_check: Callable[[], object] | None = None
    on_generate_support_bundle: Callable[[], object] | None = None
    on_headless_notes: Callable[[], object] | None = None
    on_help_getting_started: Callable[[], object] | None = None
    on_help_shortcuts: Callable[[], object] | None = None
    on_help_about: Callable[[], object] | None = None


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
    _register_menu_action(
        file_menu,
        actions,
        "shell.action.file.quickOpen",
        "Quick Open...",
        "Ctrl+P",
        enabled=True,
        callback=callback_registry.on_quick_open,
    )
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
    _register_menu_action(
        file_menu,
        actions,
        "shell.action.file.settings",
        "Settings...",
        enabled=True,
        callback=callback_registry.on_open_settings,
    )
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
    _register_menu_action(
        edit_menu,
        actions,
        "shell.action.edit.find",
        "Find",
        "Ctrl+F",
        enabled=True,
        callback=callback_registry.on_find,
    )
    _register_menu_action(
        edit_menu,
        actions,
        "shell.action.edit.replace",
        "Replace",
        "Ctrl+H",
        enabled=True,
        callback=callback_registry.on_replace,
    )
    _register_menu_action(
        edit_menu,
        actions,
        "shell.action.edit.goToLine",
        "Go To Line",
        "Ctrl+G",
        enabled=True,
        callback=callback_registry.on_go_to_line,
    )
    _register_menu_action(
        edit_menu,
        actions,
        "shell.action.edit.findInFiles",
        "Find in Files",
        "Ctrl+Shift+F",
        enabled=True,
        callback=callback_registry.on_find_in_files,
    )
    _register_menu_action(
        edit_menu,
        actions,
        "shell.action.edit.findReferences",
        "Find References",
        "Shift+F12",
        enabled=True,
        callback=callback_registry.on_find_references,
    )
    _register_menu_action(
        edit_menu,
        actions,
        "shell.action.edit.renameSymbol",
        "Rename Symbol",
        "F2",
        enabled=True,
        callback=callback_registry.on_rename_symbol,
    )
    _register_menu_action(
        edit_menu,
        actions,
        "shell.action.edit.toggleComment",
        "Toggle Comment",
        "Ctrl+/",
        enabled=True,
        callback=callback_registry.on_toggle_comment,
    )
    _register_menu_action(
        edit_menu,
        actions,
        "shell.action.edit.indent",
        "Indent",
        "Tab",
        enabled=True,
        callback=callback_registry.on_indent,
    )
    _register_menu_action(
        edit_menu,
        actions,
        "shell.action.edit.outdent",
        "Outdent",
        "Shift+Tab",
        enabled=True,
        callback=callback_registry.on_outdent,
    )
    _register_menu_action(
        edit_menu,
        actions,
        "shell.action.edit.goToDefinition",
        "Go To Definition",
        "F12",
        enabled=True,
        callback=callback_registry.on_go_to_definition,
    )
    _register_menu_action(
        edit_menu,
        actions,
        "shell.action.edit.signatureHelp",
        "Signature Help",
        "Ctrl+Shift+Space",
        enabled=True,
        callback=callback_registry.on_signature_help,
    )
    _register_menu_action(
        edit_menu,
        actions,
        "shell.action.edit.hoverInfo",
        "Show Hover Info",
        "Ctrl+K",
        enabled=True,
        callback=callback_registry.on_hover_info,
    )

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
        "shell.action.run.debug",
        "Debug",
        "Ctrl+F5",
        callback=callback_registry.on_debug,
    )
    _register_menu_action(
        run_menu,
        actions,
        "shell.action.run.pytestProject",
        "Run Project Tests",
        "Ctrl+Shift+T",
        callback=callback_registry.on_run_pytest_project,
    )
    _register_menu_action(
        run_menu,
        actions,
        "shell.action.run.pytestCurrentFile",
        "Run Current File Tests",
        "Ctrl+Alt+T",
        callback=callback_registry.on_run_pytest_current_file,
    )
    _register_menu_action(
        run_menu,
        actions,
        "shell.action.run.runWithConfig",
        "Run With Configuration...",
        callback=callback_registry.on_run_with_config,
    )
    _register_menu_action(
        run_menu,
        actions,
        "shell.action.run.manageRunConfigs",
        "Manage Run Configurations...",
        callback=callback_registry.on_manage_run_configs,
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
        "shell.action.run.restart",
        "Restart",
        "Ctrl+Shift+F5",
        callback=callback_registry.on_restart,
    )
    run_menu.addSeparator()
    _register_menu_action(
        run_menu,
        actions,
        "shell.action.run.continue",
        "Continue",
        "F6",
        callback=callback_registry.on_continue_debug,
    )
    _register_menu_action(
        run_menu,
        actions,
        "shell.action.run.pause",
        "Pause",
        "Ctrl+F6",
        callback=callback_registry.on_pause_debug,
    )
    _register_menu_action(
        run_menu,
        actions,
        "shell.action.run.stepOver",
        "Step Over",
        "F10",
        callback=callback_registry.on_step_over,
    )
    _register_menu_action(
        run_menu,
        actions,
        "shell.action.run.stepInto",
        "Step Into",
        "F11",
        callback=callback_registry.on_step_into,
    )
    _register_menu_action(
        run_menu,
        actions,
        "shell.action.run.stepOut",
        "Step Out",
        "Shift+F11",
        callback=callback_registry.on_step_out,
    )
    _register_menu_action(
        run_menu,
        actions,
        "shell.action.run.toggleBreakpoint",
        "Toggle Breakpoint",
        "F9",
        callback=callback_registry.on_toggle_breakpoint,
    )
    run_menu.addSeparator()
    _register_menu_action(
        run_menu,
        actions,
        "shell.action.run.pythonConsole",
        "Start Python Console",
        "Ctrl+`",
        callback=callback_registry.on_start_python_console,
    )
    _register_menu_action(
        run_menu,
        actions,
        "shell.action.run.clearConsole",
        "Clear Console",
        callback=callback_registry.on_clear_console,
    )

    view_menu = menu_bar.addMenu("&View")
    view_menu.setObjectName("shell.menu.view")
    _register_menu_action(
        view_menu,
        actions,
        "shell.action.view.resetLayout",
        "Reset Layout",
        callback=callback_registry.on_reset_layout,
    )
    view_menu.addSeparator()
    theme_menu = view_menu.addMenu("Theme")
    theme_menu.setObjectName("shell.menu.view.theme")
    menus["shell.menu.view.theme"] = theme_menu

    qt_gui = importlib.import_module("PySide2.QtWidgets")
    action_group = qt_gui.QActionGroup(theme_menu)
    action_group.setExclusive(True)
    for action_id, label, mode_callback in [
        ("shell.action.view.theme.system", "System", callback_registry.on_set_theme_system),
        ("shell.action.view.theme.light", "Light", callback_registry.on_set_theme_light),
        ("shell.action.view.theme.dark", "Dark", callback_registry.on_set_theme_dark),
    ]:
        act = qt_gui.QAction(label, theme_menu)
        act.setObjectName(action_id)
        act.setCheckable(True)
        act.setEnabled(True)
        if mode_callback is not None:
            act.triggered.connect(mode_callback)
        action_group.addAction(act)
        theme_menu.addAction(act)
        actions[action_id] = act

    tools_menu = menu_bar.addMenu("&Tools")
    tools_menu.setObjectName("shell.menu.tools")
    _register_menu_action(
        tools_menu,
        actions,
        "shell.action.tools.formatCurrentFile",
        "Format Current File",
        enabled=True,
        callback=callback_registry.on_format_current_file,
    )
    _register_menu_action(
        tools_menu,
        actions,
        "shell.action.tools.lintCurrentFile",
        "Lint Current File",
        enabled=True,
        callback=callback_registry.on_lint_current_file,
    )
    _register_menu_action(
        tools_menu,
        actions,
        "shell.action.tools.applySafeFixes",
        "Apply Safe Fixes (Current File)",
        enabled=True,
        callback=callback_registry.on_apply_safe_fixes,
    )
    _register_menu_action(
        tools_menu,
        actions,
        "shell.action.tools.rebuildIntelligenceCache",
        "Rebuild Intelligence Cache",
        enabled=True,
        callback=callback_registry.on_rebuild_intelligence_cache,
    )
    _register_menu_action(
        tools_menu,
        actions,
        "shell.action.tools.analyzeImports",
        "Analyze Imports",
        enabled=True,
        callback=callback_registry.on_analyze_imports,
    )
    _register_menu_action(
        tools_menu,
        actions,
        "shell.action.tools.showOutline",
        "Show Current File Outline",
        enabled=True,
        callback=callback_registry.on_show_outline,
    )
    _register_menu_action(
        tools_menu,
        actions,
        "shell.action.tools.projectHealthCheck",
        "Project Health Check",
        enabled=True,
        callback=callback_registry.on_project_health_check,
    )
    _register_menu_action(
        tools_menu,
        actions,
        "shell.action.tools.generateSupportBundle",
        "Generate Support Bundle",
        enabled=True,
        callback=callback_registry.on_generate_support_bundle,
    )
    _register_menu_action(
        tools_menu,
        actions,
        "shell.action.tools.headlessNotes",
        "FreeCAD Headless Notes",
        enabled=True,
        callback=callback_registry.on_headless_notes,
    )

    help_menu = menu_bar.addMenu("&Help")
    help_menu.setObjectName("shell.menu.help")
    _register_menu_action(
        help_menu,
        actions,
        "shell.action.help.gettingStarted",
        "Getting Started",
        enabled=True,
        callback=callback_registry.on_help_getting_started,
    )
    _register_menu_action(
        help_menu,
        actions,
        "shell.action.help.shortcuts",
        "Keyboard Shortcuts",
        enabled=True,
        callback=callback_registry.on_help_shortcuts,
    )
    _register_menu_action(
        help_menu,
        actions,
        "shell.action.help.about",
        "About",
        enabled=True,
        callback=callback_registry.on_help_about,
    )

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
