"""Menu construction helpers for the shell window."""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from app.shell.edit_menu_builder import build_edit_menu
from app.shell.file_menu_builder import build_file_menu
from app.shell.help_menu_builder import build_help_menu
from app.shell.menu_build_context import MenuBuildContext
from app.shell.run_menu_builder import build_run_menu
from app.shell.tools_menu_builder import build_tools_menu
from app.shell.view_menu_builder import build_view_menu


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
    on_new_window: Callable[[], object] | None = None
    on_new_project_from_template: Callable[[], object] | None = None
    on_open_project: Callable[[], object] | None = None
    on_open_file: Callable[[], object] | None = None
    on_file_menu_about_to_show: Callable[[], object] | None = None
    on_save: Callable[[], object] | None = None
    on_save_all: Callable[[], object] | None = None
    on_toggle_auto_save: Callable[[bool], object] | None = None
    on_open_settings: Callable[[], object] | None = None
    on_exit: Callable[[], object] | None = None
    on_quick_open: Callable[[], object] | None = None
    on_open_global_history: Callable[[], object] | None = None
    on_find: Callable[[], object] | None = None
    on_replace: Callable[[], object] | None = None
    on_go_to_line: Callable[[], object] | None = None
    on_find_in_files: Callable[[], object] | None = None
    on_show_test_explorer: Callable[[], object] | None = None
    on_find_references: Callable[[], object] | None = None
    on_rename_symbol: Callable[[], object] | None = None
    on_toggle_comment: Callable[[], object] | None = None
    on_indent: Callable[[], object] | None = None
    on_outdent: Callable[[], object] | None = None
    on_paste_reindented_flat_python: Callable[[], object] | None = None
    on_reindent_flat_python_selection: Callable[[], object] | None = None
    on_go_to_definition: Callable[[], object] | None = None
    on_signature_help: Callable[[], object] | None = None
    on_hover_info: Callable[[], object] | None = None
    on_analyze_imports: Callable[[], object] | None = None
    on_goto_symbol_in_file: Callable[[], object] | None = None
    on_set_language_mode: Callable[[], object] | None = None
    on_clear_language_override: Callable[[], object] | None = None
    on_inspect_token: Callable[[], object] | None = None
    on_run: Callable[[], object] | None = None
    on_debug: Callable[[], object] | None = None
    on_run_project: Callable[[], object] | None = None
    on_debug_project: Callable[[], object] | None = None
    on_run_pytest_project: Callable[[], object] | None = None
    on_run_pytest_current_file: Callable[[], object] | None = None
    on_run_pytest_at_cursor: Callable[[], object] | None = None
    on_debug_pytest_current_file: Callable[[], object] | None = None
    on_debug_pytest_failed: Callable[[], object] | None = None
    on_run_with_config: Callable[[], object] | None = None
    on_stop: Callable[[], object] | None = None
    on_restart: Callable[[], object] | None = None
    on_rerun_last_debug_target: Callable[[], object] | None = None
    on_continue_debug: Callable[[], object] | None = None
    on_pause_debug: Callable[[], object] | None = None
    on_step_over: Callable[[], object] | None = None
    on_step_into: Callable[[], object] | None = None
    on_step_out: Callable[[], object] | None = None
    on_toggle_breakpoint: Callable[[], object] | None = None
    on_remove_all_breakpoints: Callable[[], object] | None = None
    on_debug_exception_stops: Callable[[], object] | None = None
    on_start_python_console: Callable[[], object] | None = None
    on_clear_console: Callable[[], object] | None = None
    on_package_project: Callable[[], object] | None = None
    on_reset_layout: Callable[[], object] | None = None
    on_set_theme_system: Callable[[], object] | None = None
    on_set_theme_light: Callable[[], object] | None = None
    on_set_theme_dark: Callable[[], object] | None = None
    on_zoom_in: Callable[[], object] | None = None
    on_zoom_out: Callable[[], object] | None = None
    on_zoom_reset: Callable[[], object] | None = None
    on_markdown_show_source: Callable[[], object] | None = None
    on_markdown_show_preview: Callable[[], object] | None = None
    on_markdown_show_split: Callable[[], object] | None = None
    on_markdown_toggle_preview: Callable[[], object] | None = None
    on_format_current_file: Callable[[], object] | None = None
    on_organize_imports_current_file: Callable[[], object] | None = None
    on_lint_current_file: Callable[[], object] | None = None
    on_apply_safe_fixes: Callable[[], object] | None = None
    on_open_plugin_manager: Callable[[], object] | None = None
    on_open_dependency_inspector: Callable[[], object] | None = None
    on_add_dependency: Callable[[], object] | None = None
    on_rebuild_intelligence_cache: Callable[[], object] | None = None
    on_refresh_runtime_modules: Callable[[], object] | None = None
    on_runtime_center: Callable[[], object] | None = None
    on_project_health_check: Callable[[], object] | None = None
    on_generate_support_bundle: Callable[[], object] | None = None
    on_headless_notes: Callable[[], object] | None = None
    on_help_load_example_project: Callable[[], object] | None = None
    on_help_open_app_log: Callable[[], object] | None = None
    on_help_open_log_folder: Callable[[], object] | None = None
    on_help_runtime_onboarding: Callable[[], object] | None = None
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


def build_menu_stubs(
    menu_bar: Any,
    callbacks: MenuCallbacks | None = None,
    *,
    shortcut_overrides: Mapping[str, str] | None = None,
) -> MenuStubRegistry:
    """Create top-level shell menus and stable action IDs."""
    qt_widgets = importlib.import_module("PySide2.QtWidgets")
    qt_core = importlib.import_module("PySide2.QtCore")
    actions: dict[str, Any] = {}
    menus: dict[str, Any] = {}

    menu_bar.setObjectName("shell.menuBar")
    ctx = MenuBuildContext(
        qt_widgets=qt_widgets,
        qt_core=qt_core,
        menu_bar=menu_bar,
        actions=actions,
        menus=menus,
        callbacks=callbacks or MenuCallbacks(),
        shortcut_overrides=shortcut_overrides,
    )

    build_file_menu(ctx)
    build_edit_menu(ctx)
    build_run_menu(ctx)
    build_view_menu(ctx)
    build_tools_menu(ctx)
    build_help_menu(ctx)
    _finalize_menu_chrome(ctx)

    return MenuStubRegistry(actions=actions, menus=menus)


def _finalize_menu_chrome(ctx: MenuBuildContext) -> None:
    quick_open_action = ctx.actions.get("shell.action.file.quickOpen")
    if quick_open_action is not None:
        quick_open_action.setShortcutContext(ctx.qt_core.Qt.ApplicationShortcut)

    goto_symbol_action = ctx.actions.get("shell.action.tools.gotoSymbolInFile")
    if goto_symbol_action is not None:
        goto_symbol_action.setShortcutContext(ctx.qt_core.Qt.ApplicationShortcut)

    for menu_id in (
        "shell.menu.file",
        "shell.menu.file.openRecent",
        "shell.menu.edit",
        "shell.menu.run",
        "shell.menu.view",
        "shell.menu.view.theme",
        "shell.menu.tools",
        "shell.menu.help",
    ):
        menu = ctx.menus.get(menu_id)
        if menu is not None:
            menu.setAttribute(ctx.qt_core.Qt.WA_TranslucentBackground)
