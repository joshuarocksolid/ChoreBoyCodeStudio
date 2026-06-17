"""Theme-aware icons for main menu bar actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from PySide2.QtCore import QSize
from PySide2.QtGui import QColor, QIcon

from app.shell import icon_provider
from app.shell.icons import test_icon
from app.shell.theme_tokens import ShellThemeTokens
from app.shell.toolbar_icons import (
    icon_continue,
    icon_debug,
    icon_debug_file,
    icon_package,
    icon_pause,
    icon_remove_all_breakpoints,
    icon_restart,
    icon_run,
    icon_run_file,
    icon_step_into,
    icon_step_out,
    icon_step_over,
    icon_stop,
)

if TYPE_CHECKING:
    from app.shell.menus import MenuStubRegistry


MENU_ICON_SIZE = 16


@dataclass(frozen=True)
class _MenuIconColors:
    primary: str
    muted: str
    accent: str
    running: str
    debug: str
    danger: str
    warning: str
    success: str


MenuIconBuilder = Callable[[_MenuIconColors], QIcon]


def _colors(tokens: ShellThemeTokens) -> _MenuIconColors:
    primary = tokens.icon_primary or tokens.text_primary
    muted = tokens.icon_muted or primary
    accent = tokens.accent or primary
    running = tokens.debug_running_color or tokens.test_passed_color or accent
    debug = tokens.debug_paused_color or tokens.diag_warning_color or accent
    danger = tokens.diag_error_color or primary
    warning = tokens.diag_warning_color or debug
    success = tokens.test_passed_color or running
    return _MenuIconColors(
        primary=primary,
        muted=muted,
        accent=accent,
        running=running,
        debug=debug,
        danger=danger,
        warning=warning,
        success=success,
    )


def _test_icon(color: str) -> QIcon:
    qcolor = QColor(color)
    return test_icon(size=MENU_ICON_SIZE, color_normal=qcolor, color_active=qcolor)


_ACTION_ICON_BUILDERS: dict[str, MenuIconBuilder] = {
    # File
    "shell.action.file.newProject": lambda c: icon_provider.project_new_icon(c.primary, c.accent),
    "shell.action.file.newWindow": lambda c: icon_provider.new_window_icon(c.primary, c.accent),
    "shell.action.file.newProjectFromTemplate": lambda c: icon_provider.template_icon(c.primary, c.accent),
    "shell.action.file.openProject": lambda c: icon_provider.project_icon(c.primary),
    "shell.action.file.openFile": lambda c: icon_provider.file_icon(c.primary),
    "shell.action.file.quickOpen": lambda c: icon_provider.search_icon(c.primary),
    "shell.action.file.recoveryCenter": lambda c: icon_provider.history_icon(c.warning),
    "shell.action.file.globalHistory": lambda c: icon_provider.history_icon(c.primary),
    "shell.action.file.save": lambda c: icon_provider.save_icon(c.primary),
    "shell.action.file.saveAs": lambda c: icon_provider.save_as_icon(c.primary, c.accent),
    "shell.action.file.saveAll": lambda c: icon_provider.save_all_icon(c.primary),
    "shell.action.file.autoSave": lambda c: icon_provider.auto_save_icon(c.primary, c.success),
    "shell.action.file.settings": lambda c: icon_provider.settings_icon(c.primary),
    "shell.action.file.exit": lambda c: icon_provider.exit_icon(c.danger),
    # Edit
    "shell.action.edit.undo": lambda c: icon_provider.undo_icon(c.primary),
    "shell.action.edit.redo": lambda c: icon_provider.redo_icon(c.primary),
    "shell.action.edit.find": lambda c: icon_provider.search_icon(c.primary),
    "shell.action.edit.replace": lambda c: icon_provider.replace_icon(c.primary),
    "shell.action.edit.goToLine": lambda c: icon_provider.go_to_line_icon(c.primary),
    "shell.action.edit.findInFiles": lambda c: icon_provider.find_in_files_icon(c.primary),
    "shell.action.edit.findReferences": lambda c: icon_provider.find_references_icon(c.primary),
    "shell.action.edit.renameSymbol": lambda c: icon_provider.rename_icon(c.primary),
    "shell.action.edit.toggleComment": lambda c: icon_provider.toggle_comment_icon(c.primary),
    "shell.action.edit.indent": lambda c: icon_provider.indent_icon(c.primary),
    "shell.action.edit.outdent": lambda c: icon_provider.outdent_icon(c.primary),
    "shell.action.edit.pasteReindentedFlatPython": lambda c: icon_provider.paste_reindent_icon(c.primary),
    "shell.action.edit.goToDefinition": lambda c: icon_provider.go_to_definition_icon(c.primary),
    "shell.action.edit.signatureHelp": lambda c: icon_provider.signature_help_icon(c.primary),
    "shell.action.edit.hoverInfo": lambda c: icon_provider.hover_info_icon(c.primary),
    # Run
    "shell.action.run.run": lambda c: icon_run_file(c.running),
    "shell.action.run.debug": lambda c: icon_debug_file(c.debug),
    "shell.action.run.runProject": lambda c: icon_run(c.running),
    "shell.action.run.debugProject": lambda c: icon_debug(c.debug),
    "shell.action.run.runWithArgs": lambda c: icon_provider.run_args_icon(c.running),
    "shell.action.run.runWithConfig": lambda c: icon_provider.run_config_icon(c.primary),
    "shell.action.run.pytestProject": lambda c: _test_icon(c.running),
    "shell.action.run.pytestCurrentFile": lambda c: _test_icon(c.running),
    "shell.action.run.pytestAtCursor": lambda c: _test_icon(c.running),
    "shell.action.run.debugPytestCurrentFile": lambda c: icon_debug_file(c.debug),
    "shell.action.run.debugPytestFailed": lambda c: icon_debug(c.danger),
    "shell.action.run.stop": lambda c: icon_stop(c.danger),
    "shell.action.run.restart": lambda c: icon_restart(c.accent),
    "shell.action.run.rerunLastDebugTarget": lambda c: icon_restart(c.accent),
    "shell.action.run.continue": lambda c: icon_continue(c.running),
    "shell.action.run.pause": lambda c: icon_pause(c.debug),
    "shell.action.run.stepOver": lambda c: icon_step_over(c.accent),
    "shell.action.run.stepInto": lambda c: icon_step_into(c.accent),
    "shell.action.run.stepOut": lambda c: icon_step_out(c.accent),
    "shell.action.run.toggleBreakpoint": lambda c: icon_provider.breakpoint_icon(c.danger),
    "shell.action.run.removeAllBreakpoints": lambda c: icon_remove_all_breakpoints(c.danger),
    "shell.action.run.debugExceptionStops": lambda c: icon_provider.exception_stops_icon(c.warning),
    "shell.action.run.pythonConsole": lambda c: icon_provider.python_console_icon(c.primary),
    "shell.action.run.clearConsole": lambda c: icon_provider.clear_console_icon(c.primary),
    "shell.action.build.package": lambda c: icon_package(c.accent),
    # View
    "shell.action.view.resetLayout": lambda c: icon_provider.reset_layout_icon(c.primary),
    "shell.action.view.showTestExplorer": lambda c: _test_icon(c.primary),
    "shell.action.view.theme.system": lambda c: icon_provider.theme_system_icon(c.primary),
    "shell.action.view.theme.light": lambda c: icon_provider.theme_light_icon(c.warning),
    "shell.action.view.theme.dark": lambda c: icon_provider.theme_dark_icon(c.primary),
    "shell.action.view.theme.high_contrast_light": lambda c: icon_provider.theme_high_contrast_light_icon(c.primary),
    "shell.action.view.theme.high_contrast_dark": lambda c: icon_provider.theme_high_contrast_dark_icon(c.primary),
    "shell.action.view.markdownTogglePreview": lambda c: icon_provider.markdown_preview_icon(c.primary),
    "shell.action.view.markdownShowSource": lambda c: icon_provider.markdown_source_icon(c.primary),
    "shell.action.view.markdownShowPreview": lambda c: icon_provider.markdown_preview_icon(c.primary),
    "shell.action.view.markdownShowSplit": lambda c: icon_provider.markdown_split_icon(c.primary),
    "shell.action.view.zoomIn": lambda c: icon_provider.zoom_in_icon(c.primary),
    "shell.action.view.zoomOut": lambda c: icon_provider.zoom_out_icon(c.primary),
    "shell.action.view.zoomReset": lambda c: icon_provider.zoom_reset_icon(c.primary),
    # Tools
    "shell.action.tools.pluginManager": lambda c: icon_provider.plugin_icon(c.primary),
    "shell.action.tools.dependencyInspector": lambda c: icon_provider.dependency_icon(c.primary),
    "shell.action.tools.addDependency": lambda c: icon_provider.add_dependency_icon(c.primary, c.accent),
    "shell.action.tools.formatCurrentFile": lambda c: icon_provider.format_icon(c.primary),
    "shell.action.tools.organizeImportsCurrentFile": lambda c: icon_provider.organize_imports_icon(c.primary),
    "shell.action.tools.lintCurrentFile": lambda c: icon_provider.lint_icon(c.primary),
    "shell.action.tools.applySafeFixes": lambda c: icon_provider.safe_fix_icon(c.primary, c.success),
    "shell.action.tools.reindentFlatPythonSelection": lambda c: icon_provider.paste_reindent_icon(c.primary),
    "shell.action.tools.rebuildIntelligenceCache": lambda c: icon_provider.rebuild_cache_icon(c.primary),
    "shell.action.tools.refreshRuntimeModules": lambda c: icon_provider.runtime_modules_icon(c.primary),
    "shell.action.tools.analyzeImports": lambda c: icon_provider.analyze_imports_icon(c.primary),
    "shell.action.tools.gotoSymbolInFile": lambda c: icon_provider.symbol_icon(c.primary),
    "shell.action.tools.setLanguageMode": lambda c: icon_provider.language_mode_icon(c.primary),
    "shell.action.tools.clearLanguageOverride": lambda c: icon_provider.clear_override_icon(c.primary),
    "shell.action.tools.inspectToken": lambda c: icon_provider.inspect_token_icon(c.primary),
    "shell.action.tools.runtimeCenter": lambda c: icon_provider.runtime_center_icon(c.primary),
    "shell.action.tools.projectHealthCheck": lambda c: icon_provider.health_check_icon(c.success),
    "shell.action.tools.generateSupportBundle": lambda c: icon_provider.support_bundle_icon(c.primary),
    "shell.action.tools.headlessNotes": lambda c: icon_provider.headless_notes_icon(c.primary),
    # Help
    "shell.action.help.loadExampleProject": lambda c: icon_provider.example_project_icon(c.primary),
    "shell.action.help.openAppLog": lambda c: icon_provider.app_log_icon(c.primary),
    "shell.action.help.openLogFolder": lambda c: icon_provider.folder_open_icon(c.primary),
    "shell.action.help.runtimeOnboarding": lambda c: icon_provider.onboarding_icon(c.primary),
    "shell.action.help.gettingStarted": lambda c: icon_provider.getting_started_icon(c.primary),
    "shell.action.help.shortcuts": lambda c: icon_provider.keyboard_icon(c.primary),
    "shell.action.help.about": lambda c: icon_provider.about_icon(c.primary),
}

_SUBMENU_ICON_BUILDERS: dict[str, MenuIconBuilder] = {
    "shell.menu.file.openRecent": lambda c: icon_provider.folder_open_icon(c.muted),
    "shell.menu.view.theme": lambda c: icon_provider.theme_system_icon(c.primary),
}


def all_static_menu_icon_action_ids() -> tuple[str, ...]:
    """Return action IDs that should receive menu bar icons."""
    return tuple(_ACTION_ICON_BUILDERS)


def build_menu_icon(action_id: str, tokens: ShellThemeTokens) -> QIcon | None:
    """Return a theme-aware icon for a registered menu action."""
    builder = _ACTION_ICON_BUILDERS.get(action_id)
    if builder is None:
        return None
    return builder(_colors(tokens))


def build_recent_project_icon(tokens: ShellThemeTokens) -> QIcon:
    """Return the folder icon used for dynamic Open Recent rows."""
    colors = _colors(tokens)
    return icon_provider.folder_open_icon(colors.muted)


def apply_menu_icons(registry: "MenuStubRegistry | None", tokens: ShellThemeTokens) -> None:
    """Apply theme-aware icons to menu actions and registered submenus."""
    if registry is None:
        return
    size = QSize(MENU_ICON_SIZE, MENU_ICON_SIZE)
    for menu in registry.menus.values():
        if menu is not None:
            set_icon_size = getattr(menu, "setIconSize", None)
            if callable(set_icon_size):
                set_icon_size(size)

    for action_id, action in registry.actions.items():
        if action is None:
            continue
        icon = build_menu_icon(action_id, tokens)
        if icon is not None:
            action.setIcon(icon)

    colors = _colors(tokens)
    for menu_id, builder in _SUBMENU_ICON_BUILDERS.items():
        menu = registry.menu(menu_id)
        if menu is None:
            continue
        menu_action = menu.menuAction()
        if menu_action is not None:
            menu_action.setIcon(builder(colors))
