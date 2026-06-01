"""MainWindow adapter for ``ProjectLoadWorkflow``."""

from __future__ import annotations

import logging
import time
from typing import Any

from app.core import constants
from app.core.models import LoadedProject
from app.shell.events import ProjectOpenedEvent
from app.shell.project_open_telemetry import ProjectOpenTelemetry
from app.shell.project_tree_utils import effective_excludes_for, filter_tree_signature_entries


class MainWindowProjectLoadHost:
    """Maps ``MainWindow`` state mutations into ``ProjectLoadWorkflow`` phases."""

    def __init__(self, window: Any) -> None:
        self._window = window

    @property
    def loaded_project(self) -> LoadedProject | None:
        return self._window._loaded_project

    def load_effective_exclude_patterns(self, project_root: str) -> list[str]:
        return self._window._load_effective_exclude_patterns(project_root)

    def prepare_project_switch(self, telemetry: ProjectOpenTelemetry) -> None:
        del telemetry
        window = self._window
        window.statusBar().showMessage("Opening project…", 0)
        window._cancel_pending_project_tree_preview()
        previous_project = window._loaded_project
        if previous_project is not None:
            window._local_history_workflow.persist_session_state(
                project_root=previous_project.project_root
            )

    def apply_project_surface(
        self,
        loaded_project: LoadedProject,
        telemetry: ProjectOpenTelemetry,
    ) -> None:
        window = self._window
        window._loaded_project = loaded_project
        window._runtime_support_workflow.clear_issue_state_for_project_change()
        window._run_launch_workflow.refresh_active_run_config_indicator()
        window._lint_rule_overrides = window._load_lint_rule_overrides()
        window._selected_linter = window._load_selected_linter()
        window._plugin_activation_workflow.reload()
        window._refresh_python_tooling_status()
        window._show_editor_screen()
        window.set_project_placeholder(loaded_project.metadata.name)
        window.setWindowTitle(
            f"ChoreBoy Code Studio v{constants.APP_VERSION} — {loaded_project.metadata.name}"
        )
        window._logger.info("Project loaded: %s", loaded_project.project_root)
        window._update_explorer_buttons_enabled()

        window.statusBar().showMessage("Building project tree…", 0)
        tree_started = time.perf_counter()
        window._populate_project_tree(loaded_project)
        telemetry.tree_ms = (time.perf_counter() - tree_started) * 1000.0

        window._project_tree_structure_signature = filter_tree_signature_entries(
            tuple(entry.relative_path for entry in loaded_project.entries)
        )
        window._reset_editor_tabs()
        window._stored_lint_diagnostics.clear()
        if window._search_sidebar is not None:
            window._search_sidebar.set_project_root(loaded_project.project_root)
            window._search_sidebar.set_exclude_patterns(
                effective_excludes_for(
                    loaded_project,
                    load_effective_exclude_patterns=self.load_effective_exclude_patterns,
                )
            )

    def restore_project_session(self, project_root: str, telemetry: ProjectOpenTelemetry) -> None:
        del telemetry
        self._window._local_history_workflow.restore_session_state(project_root)

    def finalize_project_open(
        self,
        loaded_project: LoadedProject,
        telemetry: ProjectOpenTelemetry,
        *,
        exclude_patterns: list[str],
    ) -> None:
        window = self._window
        window._lint_all_open_files()
        window._debug_control_workflow.refresh_breakpoints_list()
        window._refresh_open_recent_menu()
        window._refresh_save_action_states()
        window._refresh_run_action_states()
        if window._intelligence_runtime_settings.force_full_reindex_on_open:
            window._rebuild_intelligence_cache()
        window._start_symbol_indexing(loaded_project.project_root, exclude_patterns=exclude_patterns)
        telemetry.log(window._logger)
        window._event_bus.publish(
            ProjectOpenedEvent(
                project_root=loaded_project.project_root,
                project_name=loaded_project.metadata.name,
            )
        )
        window._persist_last_project_path(loaded_project.project_root)
        test_runner_workflow = getattr(window, "_test_runner_workflow", None)
        if test_runner_workflow is not None:
            test_runner_workflow.refresh_discovery()
        window.statusBar().showMessage(
            f"Opened project — {loaded_project.metadata.name}",
            3000,
        )

    def migration_logger(self) -> logging.Logger:
        return self._window._logger
