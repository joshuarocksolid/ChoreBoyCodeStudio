"""Tools menu construction."""

from __future__ import annotations

from typing import Any, Callable

from app.shell.menu_action_builder import register_menu_action
from app.shell.menu_build_context import MenuBuildContext


def build_tools_menu(ctx: MenuBuildContext) -> object:
    callbacks = ctx.callbacks
    tools_menu = ctx.menu_bar.addMenu("&Tools")
    tools_menu.setObjectName("shell.menu.tools")
    ctx.menus["shell.menu.tools"] = tools_menu

    for action_id, label, callback in [
        ("shell.action.tools.pluginManager", "Plugin Manager...", callbacks.on_open_plugin_manager),
        ("shell.action.tools.dependencyInspector", "Dependency Inspector...", callbacks.on_open_dependency_inspector),
        ("shell.action.tools.addDependency", "Add Dependency...", callbacks.on_add_dependency),
    ]:
        _add_tools_action(ctx, tools_menu, action_id, label, callback)

    tools_menu.addSeparator()
    for action_id, label, callback in [
        ("shell.action.tools.formatCurrentFile", "Format Current File", callbacks.on_format_current_file),
        (
            "shell.action.tools.organizeImportsCurrentFile",
            "Organize Imports",
            callbacks.on_organize_imports_current_file,
        ),
        ("shell.action.tools.lintCurrentFile", "Lint Current File", callbacks.on_lint_current_file),
        ("shell.action.tools.applySafeFixes", "Apply Safe Fixes (Current File)", callbacks.on_apply_safe_fixes),
        (
            "shell.action.tools.reindentFlatPythonSelection",
            "Re-indent Flat Python Selection",
            callbacks.on_reindent_flat_python_selection,
        ),
        (
            "shell.action.tools.rebuildIntelligenceCache",
            "Rebuild Intelligence Cache",
            callbacks.on_rebuild_intelligence_cache,
        ),
        ("shell.action.tools.refreshRuntimeModules", "Refresh Runtime Modules", callbacks.on_refresh_runtime_modules),
        ("shell.action.tools.analyzeImports", "Analyze Imports", callbacks.on_analyze_imports),
    ]:
        _add_tools_action(ctx, tools_menu, action_id, label, callback)

    register_menu_action(
        qt_widgets=ctx.qt_widgets,
        menu=tools_menu,
        action_lookup=ctx.actions,
        action_id="shell.action.tools.gotoSymbolInFile",
        label="Go to Symbol in File",
        shortcut="Ctrl+R",
        enabled=True,
        callback=callbacks.on_goto_symbol_in_file,
        shortcut_overrides=ctx.shortcut_overrides,
    )

    for action_id, label, callback in [
        ("shell.action.tools.setLanguageMode", "Set Language Mode...", callbacks.on_set_language_mode),
        ("shell.action.tools.clearLanguageOverride", "Clear Language Override", callbacks.on_clear_language_override),
        ("shell.action.tools.inspectToken", "Inspect Token Under Cursor", callbacks.on_inspect_token),
        ("shell.action.tools.runtimeCenter", "Runtime Center...", callbacks.on_runtime_center),
        ("shell.action.tools.projectHealthCheck", "Project Health Check", callbacks.on_project_health_check),
        ("shell.action.tools.generateSupportBundle", "Generate Support Bundle", callbacks.on_generate_support_bundle),
        ("shell.action.tools.headlessNotes", "FreeCAD Headless Notes", callbacks.on_headless_notes),
    ]:
        _add_tools_action(ctx, tools_menu, action_id, label, callback)

    return tools_menu


def _add_tools_action(
    ctx: MenuBuildContext,
    tools_menu: Any,
    action_id: str,
    label: str,
    callback: Callable[[], object] | None,
) -> None:
    register_menu_action(
        qt_widgets=ctx.qt_widgets,
        menu=tools_menu,
        action_lookup=ctx.actions,
        action_id=action_id,
        label=label,
        enabled=True,
        callback=callback,
        shortcut_overrides=ctx.shortcut_overrides,
    )
