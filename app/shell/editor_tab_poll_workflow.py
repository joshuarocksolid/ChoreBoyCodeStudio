"""External file-change poll tick and project tree signature compare."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from app.bootstrap.logging_setup import get_subsystem_logger
from app.core.errors import ProjectEnumerationError
from app.core.models import LoadedProject
from app.editors.editor_manager import EditorManager
from app.shell.editor_sync_workflow import EditorDiskSyncSource, EditorSyncWorkflow
from app.shell.editor_tab_host_protocols import EditorTabPollHost
from app.shell.external_file_change_workflow import ExternalFileChangeWorkflow

_LOGGER = get_subsystem_logger("shell")


class EditorTabPollWorkflow:
    """Owns external-change polling and disk refresh for open tabs."""

    def __init__(
        self,
        *,
        host: EditorTabPollHost,
        editor_manager: EditorManager,
        editor_sync_workflow: EditorSyncWorkflow,
        external_file_change_workflow: ExternalFileChangeWorkflow,
        refresh_save_action_states: Callable[[], None],
    ) -> None:
        self._host = host
        self._editor_manager = editor_manager
        self._editor_sync_workflow = editor_sync_workflow
        self._external_file_change_workflow = external_file_change_workflow
        self._refresh_save_action_states = refresh_save_action_states
        self._last_poll_inventory_generation: int | None = None
        self._poll_signature_stable = False
        self._last_poll_project_mtime: float | None = None

    def set_editor_manager(self, editor_manager: EditorManager) -> None:
        self._editor_manager = editor_manager

    def reset_poll_state(self) -> None:
        """Clear stable-signature skip state after project open or full rescan."""
        self._last_poll_inventory_generation = self._host.project_inventory_generation()
        self._poll_signature_stable = False
        self._last_poll_project_mtime = None

    def refresh_open_tabs_from_disk(self, file_paths: list[str]) -> None:
        for file_path in file_paths:
            try:
                refreshed = Path(file_path).read_text(encoding="utf-8")
            except OSError:
                continue
            self._editor_sync_workflow.apply_disk_content(
                file_path,
                refreshed,
                source=EditorDiskSyncSource.TOOL_REFRESH,
            )
        self._refresh_save_action_states()

    def check_for_external_file_change(self, file_path: str) -> None:
        self._external_file_change_workflow.check_and_handle(file_path)

    def poll_external_file_changes(self) -> None:
        stale_paths = self._editor_manager.stale_open_paths()
        if stale_paths:
            active_tab = self._editor_manager.active_tab()
            if active_tab is not None and active_tab.file_path in stale_paths:
                self.check_for_external_file_change(active_tab.file_path)

        loaded_project = self._host.loaded_project()
        if loaded_project is None:
            return

        try:
            project_mtime = Path(loaded_project.project_root).stat().st_mtime
            inventory_generation = self._host.project_inventory_generation()
            if (
                self._poll_signature_stable
                and self._last_poll_inventory_generation == inventory_generation
                and self._last_poll_project_mtime == project_mtime
            ):
                return

            current_signature = self.scan_project_tree_signature(loaded_project)
            stored_signature = self._host.project_tree_structure_signature()
            self._poll_signature_stable = (
                stored_signature is not None and current_signature == stored_signature
            )
            self._last_poll_inventory_generation = inventory_generation
            self._last_poll_project_mtime = project_mtime

            previous_signature = stored_signature
            if previous_signature is None:
                self._host.set_project_tree_structure_signature(current_signature)
                return
            if current_signature == previous_signature:
                return
            self._host.set_project_tree_structure_signature(current_signature)
            previous_python_fingerprint = self._host.project_python_paths_fingerprint()
            self._host.rescan_project_from_disk(reload_plugins=False, reindex=False)
            self._last_poll_inventory_generation = self._host.project_inventory_generation()
            self._poll_signature_stable = True
            self._last_poll_project_mtime = project_mtime
            current_python_fingerprint = self._host.project_python_paths_fingerprint()
            if previous_python_fingerprint != current_python_fingerprint:
                self._host.start_symbol_indexing_for_loaded_project()
        except (OSError, ProjectEnumerationError) as exc:
            _LOGGER.warning("External file poll skipped: %s", exc)
            return

    def scan_project_tree_signature(self, loaded_project: LoadedProject) -> tuple[str, ...]:
        orchestrator_signature = self._host.project_inventory_tree_signature()
        if orchestrator_signature is not None:
            return orchestrator_signature
        return ()


__all__ = ["EditorTabPollWorkflow"]
