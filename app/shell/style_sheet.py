"""Shell stylesheet generation."""

from __future__ import annotations

from app.shell.style_sheet_sections import (
    settings_section_checkbox_and_line_edit,
    settings_section_combo_spin_font,
    settings_section_dialog_and_tabs,
    settings_section_group_boxes_and_labels,
    settings_section_push_buttons,
    settings_section_scope_controls,
    settings_section_scrollbars_shortcuts_validation,
    settings_section_tables_lists_scroll_area,
    shell_section_activity_bar,
    shell_section_debug_panel,
    shell_section_explorer_status_toolbar_chrome,
    shell_section_find_bar,
    shell_section_help_dialog,
    shell_section_main_window_menus,
    shell_section_package_wizard,
    shell_section_problems_panel,
    shell_section_quick_open,
    shell_section_run_log_panel,
    shell_section_runtime_center_dialog,
    shell_section_search_sidebar,
    shell_section_tab_bar,
    shell_section_toolbar_buttons,
    shell_section_welcome,
    shell_section_workspace_tree_editors,
)
from app.shell.theme_tokens import ShellThemeTokens


def build_shell_style_sheet(tokens: ShellThemeTokens) -> str:
    """Return stylesheet string for shell components."""
    return "\n" + (
        shell_section_main_window_menus(tokens)
        + shell_section_workspace_tree_editors(tokens)
        + shell_section_run_log_panel(tokens)
        + shell_section_problems_panel(tokens)
        + shell_section_debug_panel(tokens)
        + shell_section_explorer_status_toolbar_chrome(tokens)
        + shell_section_toolbar_buttons(tokens)
        + shell_section_tab_bar(tokens)
        + shell_section_welcome(tokens)
        + shell_section_find_bar(tokens)
        + shell_section_quick_open(tokens)
        + shell_section_activity_bar(tokens)
        + shell_section_search_sidebar(tokens)
        + shell_section_help_dialog(tokens)
        + shell_section_runtime_center_dialog(tokens)
        + shell_section_package_wizard(tokens)
    )


def build_settings_style_sheet(tokens: ShellThemeTokens) -> str:
    """Return stylesheet string for the settings dialog."""
    return "\n" + (
        settings_section_dialog_and_tabs(tokens)
        + settings_section_scope_controls(tokens)
        + settings_section_group_boxes_and_labels(tokens)
        + settings_section_combo_spin_font(tokens)
        + settings_section_checkbox_and_line_edit(tokens)
        + settings_section_push_buttons(tokens)
        + settings_section_tables_lists_scroll_area(tokens)
        + settings_section_scrollbars_shortcuts_validation(tokens)
    )
