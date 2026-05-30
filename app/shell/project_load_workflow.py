"""Orchestrates shell-side work after a project finishes loading from disk."""

from __future__ import annotations

import time
import logging
from typing import Protocol

from app.core.models import LoadedProject
from app.project.file_excludes import compute_effective_excludes
from app.project.vendor_exclude_migration import maybe_persist_vendor_exclude
from app.shell.project_open_telemetry import ProjectOpenTelemetry


class ProjectLoadHost(Protocol):
    """Surface ``ProjectLoadWorkflow`` needs from the shell."""

    @property
    def loaded_project(self) -> LoadedProject | None:
        ...

    def set_loaded_project(self, loaded_project: LoadedProject) -> None:
        ...

    def cancel_pending_project_tree_preview(self) -> None:
        ...

    def persist_previous_session_state(self, project_root: str) -> None:
        ...

    def clear_runtime_issue_state(self) -> None:
        ...

    def refresh_run_config_indicator(self) -> None:
        ...

    def reload_lint_preferences(self) -> None:
        ...

    def reload_plugin_activation(self) -> None:
        ...

    def refresh_python_tooling_status(self) -> None:
        ...

    def show_editor_screen(self) -> None:
        ...

    def set_project_placeholder(self, name: str) -> None:
        ...

    def set_window_title_for_project(self, name: str) -> None:
        ...

    def log_info(self, message: str, *args: object) -> None:
        ...

    def update_explorer_buttons_enabled(self) -> None:
        ...

    def populate_project_tree(self, loaded_project: LoadedProject) -> None:
        ...

    def set_project_tree_structure_signature(self, loaded_project: LoadedProject) -> None:
        ...

    def reset_editor_tabs(self) -> None:
        ...

    def clear_stored_lint_diagnostics(self) -> None:
        ...

    def configure_search_sidebar(self, loaded_project: LoadedProject) -> None:
        ...

    def restore_session_state(self, project_root: str, telemetry: ProjectOpenTelemetry) -> None:
        ...

    def lint_all_open_files(self) -> None:
        ...

    def refresh_breakpoints_list(self) -> None:
        ...

    def refresh_open_recent_menu(self) -> None:
        ...

    def refresh_save_action_states(self) -> None:
        ...

    def refresh_run_action_states(self) -> None:
        ...

    def maybe_rebuild_intelligence_cache(self) -> None:
        ...

    def start_symbol_indexing(self, project_root: str, *, exclude_patterns: list[str]) -> None:
        ...

    def publish_project_opened(self, loaded_project: LoadedProject) -> None:
        ...

    def persist_last_project_path(self, project_root: str) -> None:
        ...

    def refresh_test_discovery(self) -> None:
        ...

    def show_status_message(self, message: str, timeout_ms: int) -> None:
        ...

    def load_effective_exclude_patterns(self, project_root: str) -> list[str]:
        ...

    def migration_logger(self) -> logging.Logger:
        ...


class ProjectLoadWorkflow:
    """Applies a loaded project to the shell in measured phases."""

    def __init__(self, host: ProjectLoadHost) -> None:
        self._host = host

    def apply(self, loaded_project: LoadedProject, *, started_at: float) -> ProjectOpenTelemetry:
        telemetry = ProjectOpenTelemetry(
            project_root=loaded_project.project_root,
            started_at=started_at,
        )
        self._host.show_status_message("Opening project…", 0)
        self._host.cancel_pending_project_tree_preview()

        previous_project = self._host.loaded_project
        if previous_project is not None:
            self._host.persist_previous_session_state(previous_project.project_root)

        enumerate_started = time.perf_counter()
        loaded_project = maybe_persist_vendor_exclude(
            loaded_project,
            logger=self._host.migration_logger(),
        )
        telemetry.mark_enumerate(entry_count=len(loaded_project.entries))
        telemetry.enumerate_ms = (time.perf_counter() - enumerate_started) * 1000.0

        self._host.set_loaded_project(loaded_project)
        self._host.clear_runtime_issue_state()
        self._host.refresh_run_config_indicator()
        self._host.reload_lint_preferences()
        self._host.reload_plugin_activation()
        self._host.refresh_python_tooling_status()
        self._host.show_editor_screen()
        self._host.set_project_placeholder(loaded_project.metadata.name)
        self._host.set_window_title_for_project(loaded_project.metadata.name)
        self._host.log_info("Project loaded: %s", loaded_project.project_root)
        self._host.update_explorer_buttons_enabled()

        self._host.show_status_message("Building project tree…", 0)
        tree_started = time.perf_counter()
        self._host.populate_project_tree(loaded_project)
        telemetry.tree_ms = (time.perf_counter() - tree_started) * 1000.0

        self._host.set_project_tree_structure_signature(loaded_project)
        self._host.reset_editor_tabs()
        self._host.clear_stored_lint_diagnostics()
        self._host.configure_search_sidebar(loaded_project)

        session_started = time.perf_counter()
        self._host.restore_session_state(loaded_project.project_root, telemetry)
        telemetry.session_restore_ms = (time.perf_counter() - session_started) * 1000.0

        self._host.lint_all_open_files()
        self._host.refresh_breakpoints_list()
        self._host.refresh_open_recent_menu()
        self._host.refresh_save_action_states()
        self._host.refresh_run_action_states()
        self._host.maybe_rebuild_intelligence_cache()

        effective_excludes = compute_effective_excludes(
            self._host.load_effective_exclude_patterns(loaded_project.project_root),
            loaded_project.metadata.exclude_patterns,
        )
        self._host.start_symbol_indexing(loaded_project.project_root, exclude_patterns=effective_excludes)
        telemetry.log(self._host.migration_logger())
        self._host.publish_project_opened(loaded_project)
        self._host.persist_last_project_path(loaded_project.project_root)
        self._host.refresh_test_discovery()
        self._host.show_status_message(
            f"Opened project — {loaded_project.metadata.name}",
            3000,
        )
        return telemetry

