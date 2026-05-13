"""Main-window menu callback wiring."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from PySide2.QtWidgets import QMessageBox

from app.core import constants
from app.debug.debug_command_service import continue_command, step_into_command, step_out_command, step_over_command
from app.shell.menus import MenuCallbacks, MenuStubRegistry, build_menu_stubs


def build_main_window_menus(
    window: Any,
    *,
    shortcut_overrides: Mapping[str, str],
) -> MenuStubRegistry:
    """Create shell menus with callbacks bound to the existing window graph."""

    def show_test_explorer_action() -> None:
        if window._loaded_project is None:
            QMessageBox.warning(window, "Test Explorer", "Open a project first.")
            return
        if window._activity_bar is not None:
            window._activity_bar.set_active_view("test_explorer")
        window._test_runner_workflow.refresh_discovery()

    callbacks = MenuCallbacks(
        on_open_project=window._handle_open_project_action,
        on_open_file=window._handle_open_file_action,
        on_new_window=window._handle_new_window_action,
        on_file_menu_about_to_show=window._refresh_open_recent_menu,
        on_save=window._save_workflow.handle_save_action,
        on_save_all=window._save_workflow.handle_save_all_action,
        on_toggle_auto_save=window._save_workflow.handle_toggle_auto_save,
        on_open_settings=window._handle_open_settings_action,
        on_exit=window.close,
        on_run=window._handle_run_action,
        on_debug=window._handle_debug_action,
        on_run_project=window._handle_run_project_action,
        on_debug_project=window._handle_debug_project_action,
        on_run_pytest_project=window._test_runner_workflow.run_all_tests,
        on_run_pytest_current_file=window._test_runner_workflow.run_file_tests,
        on_run_pytest_at_cursor=window._test_runner_workflow.run_test_at_cursor,
        on_debug_pytest_current_file=window._test_runner_workflow.debug_current_file_tests,
        on_debug_pytest_failed=window._test_runner_workflow.debug_failed_test,
        on_run_with_config=window._handle_run_with_configuration_action,
        on_run_with_args=window._handle_run_with_arguments_action,
        on_stop=window._handle_stop_action,
        on_restart=window._handle_restart_action,
        on_rerun_last_debug_target=window._handle_rerun_last_debug_target_action,
        on_continue_debug=lambda: window._debug_control_workflow.dispatch_debug_transport_command(continue_command),
        on_pause_debug=window._debug_control_workflow.handle_pause_debug_action,
        on_step_over=lambda: window._debug_control_workflow.dispatch_debug_transport_command(step_over_command),
        on_step_into=lambda: window._debug_control_workflow.dispatch_debug_transport_command(step_into_command),
        on_step_out=lambda: window._debug_control_workflow.dispatch_debug_transport_command(step_out_command),
        on_toggle_breakpoint=window._debug_control_workflow.handle_toggle_breakpoint_action,
        on_remove_all_breakpoints=window._debug_control_workflow.handle_remove_all_breakpoints_action,
        on_debug_exception_stops=window._debug_control_workflow.handle_debug_exception_settings_action,
        on_start_python_console=window._handle_start_python_console_action,
        on_clear_console=window._handle_clear_console_action,
        on_reset_layout=window._handle_reset_layout_action,
        on_set_theme_system=lambda: window._handle_set_theme(constants.UI_THEME_MODE_SYSTEM),
        on_set_theme_light=lambda: window._handle_set_theme(constants.UI_THEME_MODE_LIGHT),
        on_set_theme_dark=lambda: window._handle_set_theme(constants.UI_THEME_MODE_DARK),
        on_set_theme_high_contrast_light=lambda: window._handle_set_theme(
            constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT
        ),
        on_set_theme_high_contrast_dark=lambda: window._handle_set_theme(
            constants.UI_THEME_MODE_HIGH_CONTRAST_DARK
        ),
        on_zoom_in=window._handle_zoom_in,
        on_zoom_out=window._handle_zoom_out,
        on_zoom_reset=window._handle_zoom_reset,
        on_markdown_show_source=window._handle_markdown_show_source_action,
        on_markdown_show_preview=window._handle_markdown_show_preview_action,
        on_markdown_show_split=window._handle_markdown_show_split_action,
        on_markdown_toggle_preview=window._handle_markdown_toggle_preview_action,
        on_format_current_file=window._python_style_workflow.handle_format_current_file_action,
        on_organize_imports_current_file=window._python_style_workflow.handle_organize_imports_action,
        on_lint_current_file=window._python_style_workflow.handle_lint_current_file_action,
        on_apply_safe_fixes=window._python_style_workflow.handle_apply_safe_fixes_action,
        on_open_plugin_manager=window._handle_open_plugin_manager_action,
        on_open_dependency_inspector=window._handle_open_dependency_inspector_action,
        on_add_dependency=window._handle_add_dependency_action,
        on_rebuild_intelligence_cache=window._handle_rebuild_intelligence_cache_action,
        on_refresh_runtime_modules=window._handle_refresh_runtime_modules_action,
        on_runtime_center=window._handle_runtime_center_action,
        on_project_health_check=window._runtime_support_workflow.handle_project_health_check_action,
        on_generate_support_bundle=window._runtime_support_workflow.handle_generate_support_bundle_action,
        on_package_project=window._runtime_support_workflow.handle_package_project_action,
        on_new_project=window._handle_new_project_action,
        on_new_project_from_template=window._handle_new_project_from_template_action,
        on_quick_open=window._handle_quick_open_action,
        on_open_recovery_center=window._local_history_workflow.open_recovery_center,
        on_open_global_history=window._local_history_workflow.open_global_history,
        on_find=window._handle_find_action,
        on_replace=window._handle_replace_action,
        on_go_to_line=window._handle_go_to_line_action,
        on_find_in_files=window._handle_find_in_files_action,
        on_show_test_explorer=show_test_explorer_action,
        on_find_references=window._handle_find_references_action,
        on_rename_symbol=window._handle_rename_symbol_action,
        on_toggle_comment=window._handle_toggle_comment_action,
        on_indent=window._handle_indent_action,
        on_outdent=window._handle_outdent_action,
        on_paste_reindented_flat_python=window._handle_paste_reindented_flat_python_action,
        on_reindent_flat_python_selection=window._handle_reindent_flat_python_selection_action,
        on_go_to_definition=window._handle_go_to_definition_action,
        on_signature_help=window._handle_signature_help_action,
        on_hover_info=window._handle_hover_info_action,
        on_analyze_imports=window._handle_analyze_imports_action,
        on_goto_symbol_in_file=window._handle_goto_symbol_in_file_action,
        on_set_language_mode=window._handle_set_language_mode_action,
        on_clear_language_override=window._handle_clear_language_override_action,
        on_inspect_token=window._handle_inspect_token_action,
        on_headless_notes=window._handle_headless_notes_action,
        on_help_load_example_project=window._handle_load_example_project_action,
        on_help_open_app_log=window._handle_open_app_log_action,
        on_help_open_log_folder=window._handle_open_log_folder_action,
        on_help_runtime_onboarding=window._handle_runtime_onboarding_action,
        on_help_getting_started=window._handle_getting_started_action,
        on_help_shortcuts=window._handle_shortcuts_action,
        on_help_about=window._handle_about_action,
    )
    return build_menu_stubs(
        window.menuBar(),
        callbacks=callbacks,
        shortcut_overrides=shortcut_overrides,
    )


def connect_test_explorer_navigation(window: Any) -> None:
    """Wire Test Explorer signals that need access to the editor workspace."""
    if window._test_explorer_panel is None:
        return

    def navigate_to_test(file_path: str, line_number: int) -> None:
        if window._editor_tab_factory.open_file_in_editor(file_path, preview=False):
            editor_widget = window._editor_widgets_by_path.get(str(Path(file_path).expanduser().resolve()))
            if editor_widget is not None:
                editor_widget.go_to_line(max(1, line_number))

    window._test_explorer_panel.run_test_requested.connect(window._test_runner_workflow.run_test_node)
    window._test_explorer_panel.debug_test_requested.connect(window._test_runner_workflow.debug_test_node)
    window._test_explorer_panel.run_all_requested.connect(window._test_runner_workflow.run_all_tests)
    window._test_explorer_panel.run_failed_requested.connect(window._test_runner_workflow.rerun_failed_tests)
    window._test_explorer_panel.debug_failed_requested.connect(window._test_runner_workflow.debug_failed_test)
    window._test_explorer_panel.refresh_requested.connect(window._test_runner_workflow.refresh_discovery)
    window._test_explorer_panel.navigate_to_test.connect(navigate_to_test)
