"""MainWindow adapter for ``ProjectLoadWorkflow``."""

from __future__ import annotations

import logging
from typing import Any

from app.core import constants
from app.core.models import LoadedProject
from app.project.file_excludes import compute_effective_excludes
from app.shell.events import ProjectOpenedEvent
from app.shell.project_open_telemetry import ProjectOpenTelemetry
from app.shell.settings_models import merge_last_project_path


class MainWindowProjectLoadHost:
    """Maps ``MainWindow`` state mutations into ``ProjectLoadWorkflow`` phases."""

    def __init__(self, window: Any) -> None:
        self._window = window

    @property
    def loaded_project(self) -> LoadedProject | None:
        return self._window._loaded_project

    def set_loaded_project(self, loaded_project: LoadedProject) -> None:
        self._window._loaded_project = loaded_project

    def cancel_pending_project_tree_preview(self) -> None:
        self._window._cancel_pending_project_tree_preview()

    def persist_previous_session_state(self, project_root: str) -> None:
        self._window._local_history_workflow.persist_session_state(project_root=project_root)

    def clear_runtime_issue_state(self) -> None:
        from app.core.models import RuntimeIssueReport

        window = self._window
        window._latest_health_report = None
        window._latest_import_issue_report = RuntimeIssueReport(workflow="import", issues=[])
        window._latest_run_issue_report = RuntimeIssueReport(workflow="run", issues=[])
        window._latest_package_issue_report = RuntimeIssueReport(workflow="package", issues=[])
        window._latest_run_issue_ids = ()
        window._latest_runtime_issue_report = window._build_runtime_issue_report()
        window._active_named_run_config_name = None

    def refresh_run_config_indicator(self) -> None:
        self._window._run_launch_workflow.refresh_active_run_config_indicator()

    def reload_lint_preferences(self) -> None:
        self._window._lint_rule_overrides = self._window._load_lint_rule_overrides()
        self._window._selected_linter = self._window._load_selected_linter()

    def reload_plugin_activation(self) -> None:
        self._window._plugin_activation_workflow.reload()

    def refresh_python_tooling_status(self) -> None:
        self._window._refresh_python_tooling_status()

    def show_editor_screen(self) -> None:
        self._window._show_editor_screen()

    def set_project_placeholder(self, name: str) -> None:
        self._window.set_project_placeholder(name)

    def set_window_title_for_project(self, name: str) -> None:
        self._window.setWindowTitle(f"ChoreBoy Code Studio v{constants.APP_VERSION} — {name}")

    def log_info(self, message: str, *args: object) -> None:
        self._window._logger.info(message, *args)

    def update_explorer_buttons_enabled(self) -> None:
        self._window._update_explorer_buttons_enabled()

    def populate_project_tree(self, loaded_project: LoadedProject) -> None:
        self._window._populate_project_tree(loaded_project)

    def set_project_tree_structure_signature(self, loaded_project: LoadedProject) -> None:
        from app.shell.main_window import _filter_tree_signature_entries

        self._window._project_tree_structure_signature = _filter_tree_signature_entries(
            tuple(entry.relative_path for entry in loaded_project.entries)
        )

    def reset_editor_tabs(self) -> None:
        self._window._reset_editor_tabs()

    def clear_stored_lint_diagnostics(self) -> None:
        self._window._stored_lint_diagnostics.clear()

    def configure_search_sidebar(self, loaded_project: LoadedProject) -> None:
        window = self._window
        if window._search_sidebar is None:
            return
        window._search_sidebar.set_project_root(loaded_project.project_root)
        effective_excludes = compute_effective_excludes(
            self.load_effective_exclude_patterns(loaded_project.project_root),
            loaded_project.metadata.exclude_patterns,
        )
        window._search_sidebar.set_exclude_patterns(effective_excludes)

    def restore_session_state(self, project_root: str, telemetry: ProjectOpenTelemetry) -> None:
        self._window._local_history_workflow.restore_session_state(project_root)

    def lint_all_open_files(self) -> None:
        self._window._lint_all_open_files()

    def refresh_breakpoints_list(self) -> None:
        self._window._debug_control_workflow.refresh_breakpoints_list()

    def refresh_open_recent_menu(self) -> None:
        self._window._refresh_open_recent_menu()

    def refresh_save_action_states(self) -> None:
        self._window._refresh_save_action_states()

    def refresh_run_action_states(self) -> None:
        self._window._refresh_run_action_states()

    def maybe_rebuild_intelligence_cache(self) -> None:
        if self._window._intelligence_runtime_settings.force_full_reindex_on_open:
            self._window._rebuild_intelligence_cache()

    def start_symbol_indexing(self, project_root: str, *, exclude_patterns: list[str]) -> None:
        self._window._start_symbol_indexing(project_root, exclude_patterns=exclude_patterns)

    def publish_project_opened(self, loaded_project: LoadedProject) -> None:
        self._window._event_bus.publish(
            ProjectOpenedEvent(
                project_root=loaded_project.project_root,
                project_name=loaded_project.metadata.name,
            )
        )

    def persist_last_project_path(self, project_root: str) -> None:
        self._window._persist_last_project_path(project_root)

    def refresh_test_discovery(self) -> None:
        test_runner_workflow = getattr(self._window, "_test_runner_workflow", None)
        if test_runner_workflow is not None:
            test_runner_workflow.refresh_discovery()

    def show_status_message(self, message: str, timeout_ms: int) -> None:
        self._window.statusBar().showMessage(message, timeout_ms)

    def load_effective_exclude_patterns(self, project_root: str) -> list[str]:
        return self._window._load_effective_exclude_patterns(project_root)

    def migration_logger(self) -> logging.Logger:
        return self._window._logger
