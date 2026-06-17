"""Light vs full disk rescan for the currently loaded project."""

from __future__ import annotations

from dataclasses import replace
from enum import Enum
from typing import Any, Protocol

from app.core.models import LoadedProject
from app.project.file_inventory import ProjectInventorySnapshot
from app.project.project_service import enumerate_project_entries, open_project
from app.shell.project_load_surface import apply_tree_entries_surface
from app.shell.project_tree_utils import effective_excludes_for, filter_tree_signature_entries


class RefreshTier(str, Enum):
    """How aggressively to refresh the loaded project after a tree mutation."""

    METADATA_ONLY = "metadata_only"
    TREE_ENTRIES = "tree_entries"
    FULL_RESCAN = "full_rescan"


class ProjectRescanHost(Protocol):
    def loaded_project(self) -> LoadedProject | None: ...

    def load_effective_exclude_patterns(self, project_root: str) -> list[str]: ...

    def apply_tree_entries_surface(self, project: LoadedProject, *, preserve_state: bool) -> None: ...

    def set_loaded_project(self, project: LoadedProject) -> None: ...

    def populate_project_tree(self, project: LoadedProject, *, preserve_state: bool) -> None: ...

    def configure_search_sidebar(self, project: LoadedProject) -> None: ...

    def set_project_tree_structure_signature(self, signature: tuple[str, ...]) -> None: ...

    def reload_plugin_activation(self) -> None: ...

    def refresh_python_tooling_status(self) -> None: ...

    def start_symbol_indexing(
        self,
        project_root: str,
        *,
        exclude_patterns: list[str],
        inventory_snapshot: ProjectInventorySnapshot | None = None,
    ) -> None: ...

    def project_inventory_snapshot(self) -> ProjectInventorySnapshot | None: ...

    def refresh_test_discovery(self) -> None: ...

    def refresh_project_inventory(self, project: LoadedProject) -> None: ...


class ProjectRescanWorkflow:
    """Rescans project files from disk without repeating open-project orchestration."""

    def __init__(self, host: ProjectRescanHost) -> None:
        self._host = host

    def refresh(self, tier: RefreshTier, *, force_reindex: bool = False) -> None:
        if tier == RefreshTier.METADATA_ONLY:
            return
        if tier == RefreshTier.FULL_RESCAN:
            self._full_rescan(reload_plugins=True, reindex=True)
            return
        self._refresh_tree_entries(force_reindex=force_reindex)

    def rescan_from_disk(
        self,
        *,
        reload_plugins: bool = False,
        reindex: bool = False,
    ) -> None:
        if reload_plugins:
            self.refresh(RefreshTier.FULL_RESCAN)
            return
        self.refresh(RefreshTier.TREE_ENTRIES, force_reindex=reindex)

    def _refresh_tree_entries(self, *, force_reindex: bool = False) -> None:
        loaded = self._host.loaded_project()
        if loaded is None:
            return
        previous_python_fingerprint = self._python_paths_fingerprint()
        refreshed = self._enumerate_loaded_project(loaded)
        self._host.apply_tree_entries_surface(refreshed, preserve_state=True)
        if force_reindex or previous_python_fingerprint != self._python_paths_fingerprint():
            self._reindex(refreshed)

    def _full_rescan(self, *, reload_plugins: bool, reindex: bool) -> None:
        loaded = self._host.loaded_project()
        if loaded is None:
            return
        refreshed = open_project(
            loaded.project_root,
            exclude_patterns=self._host.load_effective_exclude_patterns(loaded.project_root),
        )
        self._host.set_loaded_project(refreshed)
        if reload_plugins:
            self._host.reload_plugin_activation()
            self._host.refresh_python_tooling_status()
        self._host.populate_project_tree(refreshed, preserve_state=True)
        self._host.refresh_project_inventory(refreshed)
        self._host.configure_search_sidebar(refreshed)
        signature = filter_tree_signature_entries(
            tuple(entry.relative_path for entry in refreshed.entries)
        )
        self._host.set_project_tree_structure_signature(signature)
        if reindex:
            self._reindex(refreshed)

    def _enumerate_loaded_project(self, loaded: LoadedProject) -> LoadedProject:
        effective = effective_excludes_for(
            loaded,
            load_effective_exclude_patterns=self._host.load_effective_exclude_patterns,
        )
        entries = enumerate_project_entries(
            loaded.project_root,
            exclude_patterns=effective.as_list(),
        )
        return replace(loaded, entries=entries)

    def _python_paths_fingerprint(self) -> tuple[str, ...] | None:
        snapshot = self._host.project_inventory_snapshot()
        if snapshot is None:
            return None
        return snapshot.python_file_paths

    def _reindex(self, loaded: LoadedProject) -> None:
        excludes = effective_excludes_for(
            loaded,
            load_effective_exclude_patterns=self._host.load_effective_exclude_patterns,
        )
        self._host.start_symbol_indexing(
            loaded.project_root,
            exclude_patterns=excludes.as_list(),
            inventory_snapshot=self._host.project_inventory_snapshot(),
        )
        self._host.refresh_test_discovery()


class MainWindowProjectRescanHost:
    """Adapts :class:`MainWindow` to :class:`ProjectRescanHost`."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def loaded_project(self) -> LoadedProject | None:
        return self._window._loaded_project

    def set_loaded_project(self, project: LoadedProject) -> None:
        self._window._loaded_project = project

    def load_effective_exclude_patterns(self, project_root: str) -> list[str]:
        return self._window._file_project_commands_workflow.load_effective_exclude_patterns(project_root)

    def apply_tree_entries_surface(self, project: LoadedProject, *, preserve_state: bool) -> None:
        apply_tree_entries_surface(
            self._window,
            project,
            load_effective_exclude_patterns=self._window._file_project_commands_workflow.load_effective_exclude_patterns,
            preserve_tree_state=preserve_state,
        )

    def populate_project_tree(self, project: LoadedProject, *, preserve_state: bool) -> None:
        self._window._project_tree_ui_workflow.populate_project_tree(project, preserve_state=preserve_state)

    def configure_search_sidebar(self, project: LoadedProject) -> None:
        if self._window._search_sidebar is None:
            return

        self._window._search_sidebar.set_project_root(project.project_root)
        effective = effective_excludes_for(
            project,
            load_effective_exclude_patterns=self._window._file_project_commands_workflow.load_effective_exclude_patterns,
        )
        self._window._search_sidebar.set_exclude_patterns(effective.as_list())

    def refresh_project_inventory(self, project: LoadedProject) -> None:
        effective = effective_excludes_for(
            project,
            load_effective_exclude_patterns=self._window._file_project_commands_workflow.load_effective_exclude_patterns,
        )
        self._window._project_inventory_orchestrator.rebuild_from_loaded(project, effective)

    def set_project_tree_structure_signature(self, signature: tuple[str, ...]) -> None:
        self._window._project_tree_structure_signature = signature
        self._window._project_inventory_orchestrator.set_tree_structure_signature(signature)

    def reload_plugin_activation(self) -> None:
        self._window._plugin_activation_workflow.reload()

    def refresh_python_tooling_status(self) -> None:
        self._window._refresh_python_tooling_status()

    def start_symbol_indexing(
        self,
        project_root: str,
        *,
        exclude_patterns: list[str],
        inventory_snapshot: ProjectInventorySnapshot | None = None,
    ) -> None:
        self._window._intelligence_cache_workflow.start_symbol_indexing(
            project_root,
            exclude_patterns=exclude_patterns,
            inventory_snapshot=inventory_snapshot,
        )

    def project_inventory_snapshot(self) -> ProjectInventorySnapshot | None:
        return self._window._project_inventory_orchestrator.snapshot

    def refresh_test_discovery(self) -> None:
        test_runner_workflow = getattr(self._window, "_test_runner_workflow", None)
        if test_runner_workflow is not None:
            test_runner_workflow.refresh_discovery()
