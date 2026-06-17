"""Composition helpers for shell workflow wiring."""

from __future__ import annotations

from typing import Any, Callable

from PySide2.QtWidgets import QMessageBox, QStatusBar, QTabWidget, QWidget

from app.core.models import LoadedProject, RuntimeIssue
from app.debug.debug_models import DebugExceptionPolicy
from app.editors.editor_manager import EditorManager
from app.persistence.settings_service import SettingsService
from app.shell.clear_console_policy import MainWindowClearConsoleHost
from app.shell.debug_control_workflow import DebugControlWorkflow
from app.shell.editor_tab_factory import EditorTabFactory
from app.shell.run_config_controller import RunConfigController
from app.shell.run_debug_presenter import RunDebugPresenterPort
from app.shell.editor_sync_factory import build_editor_sync_workflow
from app.shell.external_file_change_workflow import ExternalFileChangeWorkflow
from app.shell.file_project_commands_workflow import (
    FileProjectCommandsWorkflow,
    MainWindowFileProjectCommandsHost,
)
from app.shell.settings_apply_workflow import SettingsApplyWorkflow
from app.shell.python_console_workflow import PythonConsoleWorkflow
from app.shell.project_tree_action_workflow import ProjectTreeActionWorkflow
from app.shell.run_launch_workflow import RunLaunchWorkflow
from app.shell.save_workflow import SaveWorkflow
from app.shell.shell_preferences import ShellPreferencesBundle
from app.shell.shell_theme_surface_appliers import build_main_window_shell_theme_callbacks
from app.shell.shell_theme_workflow import ExplorerThemeHost, ShellThemeWorkflow
from app.shell.test_runner_workflow import TestRunnerWorkflow
from app.shell.theme_tokens import ShellThemeTokens


class MainWindowSaveDocumentHost:
    """Host ports for ``SaveWorkflow`` backed by a MainWindow instance."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def dialog_parent(self) -> QWidget:
        return self._window

    def editor_manager(self) -> EditorManager:
        return self._window._editor_manager

    def editor_exit_behavior(self) -> str:
        return self._window._editor_exit_behavior

    def refresh_save_action_states(self) -> None:
        self._window._refresh_save_action_states()

    def editor_auto_save(self) -> bool:
        return self._window._editor_auto_save

    def set_editor_auto_save(self, enabled: bool) -> None:
        self._window._editor_auto_save = enabled

    def stop_auto_save_timer(self) -> None:
        self._window._auto_save_to_file_timer.stop()

    def logger(self) -> Any:
        return self._window._logger

    def has_editor_tabs_widget(self) -> bool:
        return self._window._editor_tabs_widget is not None

    def editor_trim_trailing_whitespace_on_save(self) -> bool:
        return self._window._editor_trim_trailing_whitespace_on_save

    def editor_insert_final_newline_on_save(self) -> bool:
        return self._window._editor_insert_final_newline_on_save

    def editor_organize_imports_on_save(self) -> bool:
        return self._window._editor_organize_imports_on_save

    def editor_format_on_save(self) -> bool:
        return self._window._editor_format_on_save

    def resolve_python_tooling_project_root(self, file_path: str) -> str:
        return self._window._resolve_python_tooling_project_root(file_path)

    def apply_text_to_open_tab(self, file_path: str, transformed_text: str) -> None:
        self._window._apply_text_to_open_tab(file_path, transformed_text)

    def intelligence_runtime_settings(self) -> Any:
        return self._window._intelligence_runtime_settings

    def loaded_project(self) -> Any | None:
        return self._window._loaded_project

    def project_inventory_snapshot(self) -> Any:
        return self._window._project_inventory_orchestrator.snapshot

    def workflow_broker(self) -> Any:
        return self._window._workflow_broker

    def tab_index_for_path(self, file_path: str) -> int:
        return self._window._editor_tab_workflow.tab_index_for_path(file_path)

    def refresh_tab_presentation(self, file_path: str) -> None:
        self._window._editor_tab_workflow.refresh_tab_presentation(file_path)

    def update_editor_status_for_path(self, file_path: str) -> None:
        self._window._editor_tab_workflow.update_editor_status_for_path(file_path)

    def rescan_project_from_disk(self, *, reload_plugins: bool, reindex: bool) -> None:
        self._window._project_rescan_workflow.rescan_from_disk(
            reload_plugins=reload_plugins,
            reindex=reindex,
        )

    def render_lint_for_file(self, file_path: str, *, trigger: str) -> None:
        self._window._lint_workflow.render_diagnostics_for_file(file_path, trigger=trigger)

    def refresh_test_discovery(self) -> None:
        test_runner_workflow = getattr(self._window, "_test_runner_workflow", None)
        if test_runner_workflow is not None:
            test_runner_workflow.refresh_discovery()


class MainWindowExternalFileChangeHost:
    """Host ports for ``ExternalFileChangeWorkflow`` backed by a MainWindow instance."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def editor_widget_for_path(self, file_path: str) -> object | None:
        return self._window._editor_widgets_by_path.get(file_path)

    def confirm_clean_tab_reload(self) -> bool:
        choice = QMessageBox.question(
            self._window,
            "External file change detected",
            "This file changed on disk. Reload the file from disk?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        return choice == QMessageBox.Yes

    def refresh_save_action_states(self) -> None:
        self._window._refresh_save_action_states()

    def update_editor_status_for_path(self, file_path: str) -> None:
        self._window._editor_tab_workflow.update_editor_status_for_path(file_path)


class MainWindowSettingsApplyHost:
    """Host ports for ``SettingsApplyWorkflow`` backed by a MainWindow instance."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def lint_rule_overrides(self) -> dict[str, dict[str, object]]:
        return self._window._lint_rule_overrides

    def diagnostics_enabled(self) -> bool:
        return self._window._diagnostics_enabled

    def selected_linter(self) -> str:
        return self._window._selected_linter

    def editor_enable_preview(self) -> bool:
        return self._window._editor_enable_preview

    def editor_auto_save(self) -> bool:
        return self._window._editor_auto_save

    def diagnostics_realtime(self) -> bool:
        return self._window._diagnostics_realtime

    def intelligence_cache_enabled(self) -> bool:
        return self._window._intelligence_runtime_settings.cache_enabled

    def loaded_project_root(self) -> str | None:
        loaded = self._window._loaded_project
        return None if loaded is None else loaded.project_root

    def loaded_project_name(self) -> str | None:
        loaded = self._window._loaded_project
        return None if loaded is None else loaded.metadata.name

    def set_ui_font_weight(self, ui_font_weight: str) -> None:
        self._window._ui_font_weight = ui_font_weight

    def set_dark_chrome_palette(self, dark_chrome_palette: str) -> None:
        from app.shell.settings_models import resolve_dark_chrome_palette

        self._window._dark_chrome_palette = resolve_dark_chrome_palette(dark_chrome_palette)

    def apply_theme_mode(self, theme_mode: str, *, skip_theme_styles: bool = False) -> None:
        self._window._shell_preferences_runtime.handle_set_theme(
            theme_mode,
            skip_theme_styles=skip_theme_styles,
        )

    def apply_preferences_bundle(self, bundle: ShellPreferencesBundle) -> None:
        self._window._shell_preferences_runtime.apply_preferences_bundle(bundle)

    def sync_auto_save_menu_state(self) -> None:
        self._window._sync_auto_save_menu_state()

    def stop_auto_save_timer(self) -> None:
        self._window._auto_save_to_file_timer.stop()

    def stop_realtime_lint_timer(self) -> None:
        self._window._realtime_lint_timer.stop()

    def clear_pending_realtime_lint_path(self) -> None:
        self._window._pending_realtime_lint_file_path = None

    def cancel_symbol_index_worker_if_running(self) -> None:
        self._window._intelligence_cache_workflow.cancel_symbol_indexing()

    def start_symbol_indexing(self, project_root: str) -> None:
        self._window._intelligence_cache_workflow.start_symbol_indexing(
            project_root,
            inventory_snapshot=self._window._project_inventory_orchestrator.snapshot,
        )

    def apply_editor_preferences_to_open_editors(self) -> None:
        self._window._editor_tab_workflow.apply_editor_preferences_to_open_editors()

    def apply_runtime_intelligence_preferences_to_open_editors(self) -> None:
        self._window._editor_tab_workflow.apply_runtime_intelligence_preferences_to_open_editors()

    def apply_shortcut_overrides_runtime(self) -> None:
        self._window._shell_preferences_runtime.apply_shortcut_overrides_runtime()

    def apply_theme_styles(self) -> None:
        self._window._shell_theme_workflow.apply_theme_styles()

    def cancel_pending_project_tree_preview(self) -> None:
        self._window._project_tree_ui_workflow.cancel_pending_project_tree_preview()

    def promote_existing_preview_tab(self) -> None:
        self._window._editor_tab_workflow.promote_existing_preview_tab()

    def relint_open_python_files(self) -> None:
        self._window._diagnostics_orchestrator.relint_open_python_files()

    def clear_stored_lint_diagnostics(self) -> None:
        self._window._stored_lint_diagnostics.clear()

    def render_merged_problems_panel(self) -> None:
        self._window._problems_controller.render_merged_problems_panel()

    def load_effective_exclude_patterns(self, project_root: str | None) -> list[str]:
        return self._window._file_project_commands_workflow.load_effective_exclude_patterns(project_root)

    def reload_current_project(self) -> None:
        self._window._project_tree_ui_workflow.reload_current_project()

    def refresh_search_sidebar_excludes(self) -> None:
        sidebar = self._window._search_sidebar
        loaded = self._window._loaded_project
        if sidebar is None or loaded is None:
            return
        from app.project.file_excludes import EffectiveExcludes

        sidebar.set_exclude_patterns(
            EffectiveExcludes.merge(
                self._window._file_project_commands_workflow.load_effective_exclude_patterns(
                    loaded.project_root
                ),
                loaded.metadata.exclude_patterns,
            ).as_list()
        )

    def set_project_placeholder(self, project_name: str) -> None:
        self._window.set_project_placeholder(project_name)

    def log_settings_updated(self) -> None:
        self._window._logger.info("Settings updated.")


class MainWindowPythonConsoleHost:
    """Host ports for ``PythonConsoleWorkflow`` backed by a MainWindow instance."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def python_console_widget(self) -> object | None:
        return self._window._python_console_widget

    def dispatch_to_main_thread(self, callback: Callable[[], None]) -> None:
        self._window._dispatch_to_main_thread(callback)

    def show_status_message(self, message: str, timeout_ms: int) -> None:
        self._window.statusBar().showMessage(message, timeout_ms)

    def focus_python_console_tab(self) -> None:
        bottom_tabs = self._window._bottom_tabs_widget
        container = self._window._python_console_container
        if bottom_tabs is not None and container is not None:
            index = bottom_tabs.indexOf(container)
            if index >= 0:
                bottom_tabs.setCurrentIndex(index)

    def log_repl_warning(self, message: str, exc: Exception) -> None:
        self._window._logger.warning(message, exc)

    def clear_console_host(self) -> MainWindowClearConsoleHost:
        return MainWindowClearConsoleHost(self._window)


def build_save_workflow(window: Any) -> SaveWorkflow:
    return SaveWorkflow(
        local_history=window._local_history_workflow,
        intelligence_cache=window._intelligence_cache_workflow,
        host=MainWindowSaveDocumentHost(window),
        settings_service=window._settings_service,
    )


def build_external_file_change_workflow(window: Any) -> ExternalFileChangeWorkflow:
    editor_sync = build_editor_sync_workflow(window)
    return ExternalFileChangeWorkflow(
        editor_manager=window._editor_manager,
        editor_sync=editor_sync,
        save_workflow=window._save_workflow,
        local_history=window._local_history_workflow,
        host=MainWindowExternalFileChangeHost(window),
    )


def build_project_tree_action_workflow(window: Any) -> ProjectTreeActionWorkflow:
    return ProjectTreeActionWorkflow(
        save_workflow=window._save_workflow,
        local_history_workflow=window._local_history_workflow,
        project_tree_action_coordinator=window._project_tree_action_coordinator,
        dialog_parent=window,
    )


def build_settings_apply_workflow(window: Any) -> SettingsApplyWorkflow:
    return SettingsApplyWorkflow(
        settings_service=window._settings_service,
        host=MainWindowSettingsApplyHost(window),
    )


def build_python_console_workflow(window: Any) -> PythonConsoleWorkflow:
    def _start_background_work(work: Callable[[], None]) -> None:
        window._background_tasks.run(
            key="python_console_completion",
            task=lambda _cancellation: work(),
        )

    return PythonConsoleWorkflow(
        repl_manager=window._repl_manager,
        host=MainWindowPythonConsoleHost(window),
        start_background_work=_start_background_work,
    )


def build_find_replace_workflow(window: Any) -> Any:
    from app.shell.find_replace_workflow import FindReplaceWorkflow, MainWindowFindReplaceHost

    return FindReplaceWorkflow(MainWindowFindReplaceHost(window))


def build_semantic_navigation_workflow(window: Any) -> Any:
    from app.shell.semantic_navigation_workflow import (
        MainWindowSemanticNavigationHost,
        SemanticNavigationWorkflow,
    )

    return SemanticNavigationWorkflow(MainWindowSemanticNavigationHost(window))


class MainWindowRunLaunchHost:
    """Host ports for ``RunLaunchWorkflow`` backed by a MainWindow instance."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def dialog_parent(self) -> QWidget:
        return self._window

    def loaded_project(self) -> LoadedProject | None:
        return self._window._loaded_project

    def set_loaded_project(self, project: LoadedProject) -> None:
        self._window._loaded_project = project

    def active_named_run_config_name(self) -> str | None:
        return self._window._active_named_run_config_name

    def set_active_named_run_config_name(self, name: str | None) -> None:
        self._window._active_named_run_config_name = name

    def editor_manager(self) -> EditorManager:
        return self._window._editor_manager

    def debug_control_workflow(self) -> DebugControlWorkflow:
        return self._window._debug_control_workflow

    def debug_exception_policy(self) -> DebugExceptionPolicy:
        return self._window._debug_exception_policy

    def run_config_controller(self) -> RunConfigController:
        return self._window._run_config_controller

    def run_debug_presenter(self) -> RunDebugPresenterPort:
        return self._window._run_debug_presenter

    def settings_service(self) -> SettingsService:
        return self._window._settings_service

    def resolve_theme_tokens(self) -> ShellThemeTokens:
        return self._window._shell_theme_workflow.resolve_theme_tokens()

    def show_run_preflight_result(self, title: str, summary: str, issues: list[RuntimeIssue]) -> None:
        self._window._run_event_workflow.show_run_preflight_result(title, summary, issues)

    def refresh_run_action_states(self) -> None:
        self._window._run_event_workflow.refresh_run_action_states()

    def editor_tab_factory(self) -> EditorTabFactory:
        return self._window._editor_tab_factory

    def editor_tabs_widget(self) -> QTabWidget | None:
        return self._window._editor_tabs_widget

    def tab_index_for_path(self, file_path: str) -> int:
        return self._window._editor_tab_workflow.tab_index_for_path(file_path)

    def test_runner_workflow(self) -> TestRunnerWorkflow:
        return self._window._test_runner_workflow

    def active_transient_entry_file_path(self) -> str | None:
        return self._window._active_transient_entry_file_path

    def set_active_transient_entry_file_path(self, path: str | None) -> None:
        self._window._active_transient_entry_file_path = path

    def status_bar(self) -> QStatusBar:
        return self._window.statusBar()

    def show_warning(self, title: str, message: str) -> None:
        QMessageBox.warning(self._window, title, message)

    def show_information(self, title: str, message: str) -> None:
        QMessageBox.information(self._window, title, message)

    def logger(self) -> Any:
        return self._window._logger


def build_run_launch_workflow(window: Any) -> RunLaunchWorkflow:
    return RunLaunchWorkflow(MainWindowRunLaunchHost(window))


class _WindowBackedExplorerThemeSink:
    """Explorer icon fields stored on ``MainWindow`` for project tree rendering."""

    def __init__(self, window: Any) -> None:
        self._window = window

    @property
    def tree_file_icon(self) -> Any:
        return self._window._tree_file_icon

    @tree_file_icon.setter
    def tree_file_icon(self, value: Any) -> None:
        self._window._tree_file_icon = value

    @property
    def tree_file_icon_map(self) -> dict[str, Any]:
        return self._window._tree_file_icon_map

    @tree_file_icon_map.setter
    def tree_file_icon_map(self, value: dict[str, Any]) -> None:
        self._window._tree_file_icon_map = value

    @property
    def tree_filename_icon_map(self) -> dict[str, Any]:
        return self._window._tree_filename_icon_map

    @tree_filename_icon_map.setter
    def tree_filename_icon_map(self, value: dict[str, Any]) -> None:
        self._window._tree_filename_icon_map = value

    @property
    def tree_folder_icon(self) -> Any:
        return self._window._tree_folder_icon

    @tree_folder_icon.setter
    def tree_folder_icon(self, value: Any) -> None:
        self._window._tree_folder_icon = value

    @property
    def tree_folder_open_icon(self) -> Any:
        return self._window._tree_folder_open_icon

    @tree_folder_open_icon.setter
    def tree_folder_open_icon(self, value: Any) -> None:
        self._window._tree_folder_open_icon = value

    @property
    def tree_entrypoint_icon(self) -> Any:
        return self._window._tree_entrypoint_icon

    @tree_entrypoint_icon.setter
    def tree_entrypoint_icon(self, value: Any) -> None:
        self._window._tree_entrypoint_icon = value


class MainWindowShellThemeHost:
    """Live ``MainWindow`` view for :class:`ShellThemeWorkflow`."""

    def __init__(self, window: Any) -> None:
        self._window = window
        self.is_applying_theme_styles = False
        self.system_dark_theme_preference: bool | None = None
        self.child_callbacks = build_main_window_shell_theme_callbacks(window)
        self.explorer = ExplorerThemeHost(
            sink=_WindowBackedExplorerThemeSink(window),
            explorer_new_file_btn=window._explorer_new_file_btn,
            explorer_new_folder_btn=window._explorer_new_folder_btn,
            explorer_refresh_btn=window._explorer_refresh_btn,
            loaded_project=window._loaded_project,
        )

    @property
    def palette_accessor(self) -> Any:
        return self._window

    @property
    def theme_mode(self) -> str:
        return self._window._theme_mode

    @property
    def ui_font_weight(self) -> str:
        return self._window._ui_font_weight

    @property
    def dark_chrome_palette(self) -> str:
        return self._window._dark_chrome_palette

    @property
    def syntax_color_overrides(self) -> dict[str, dict[str, str]]:
        return self._window._syntax_color_overrides


def build_shell_theme_workflow(window: Any) -> ShellThemeWorkflow:
    return ShellThemeWorkflow(MainWindowShellThemeHost(window))


def build_file_project_commands_workflow(window: Any) -> FileProjectCommandsWorkflow:
    return FileProjectCommandsWorkflow(MainWindowFileProjectCommandsHost(window))


def build_realtime_lint_runner(
    *,
    is_shutting_down: Callable[[], bool],
    orchestrator: Any,
) -> Callable[[], None]:
    def run_scheduled_realtime_lint() -> None:
        if is_shutting_down():
            return
        orchestrator.run_scheduled_realtime_lint()

    return run_scheduled_realtime_lint
