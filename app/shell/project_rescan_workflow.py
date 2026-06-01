"""Light vs full disk rescan for the currently loaded project."""

from __future__ import annotations

from typing import Any, Callable, Protocol

from app.core.models import LoadedProject
from app.project.project_service import open_project
from app.shell.project_tree_utils import effective_excludes_for, filter_tree_signature_entries


class ProjectRescanHost(Protocol):
    def loaded_project(self) -> LoadedProject | None: ...

    def set_loaded_project(self, project: LoadedProject) -> None: ...

    def load_effective_exclude_patterns(self, project_root: str) -> list[str]: ...

    def populate_project_tree(self, project: LoadedProject, *, preserve_state: bool) -> None: ...

    def configure_search_sidebar(self, project: LoadedProject) -> None: ...

    def set_project_tree_structure_signature(self, signature: tuple[str, ...]) -> None: ...

    def reload_plugin_activation(self) -> None: ...

    def refresh_python_tooling_status(self) -> None: ...

    def start_symbol_indexing(self, project_root: str, *, exclude_patterns: list[str]) -> None: ...

    def refresh_test_discovery(self) -> None: ...


class ProjectRescanWorkflow:
    """Rescans project files from disk without repeating open-project orchestration."""

    def __init__(self, host: ProjectRescanHost) -> None:
        self._host = host

    def rescan_from_disk(
        self,
        *,
        reload_plugins: bool = False,
        reindex: bool = False,
    ) -> None:
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
        self._host.configure_search_sidebar(refreshed)
        signature = filter_tree_signature_entries(
            tuple(entry.relative_path for entry in refreshed.entries)
        )
        self._host.set_project_tree_structure_signature(signature)
        if reindex:
            excludes = effective_excludes_for(
                refreshed,
                load_effective_exclude_patterns=self._host.load_effective_exclude_patterns,
            )
            self._host.start_symbol_indexing(refreshed.project_root, exclude_patterns=excludes)
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

    def populate_project_tree(self, project: LoadedProject, *, preserve_state: bool) -> None:
        self._window._project_tree_ui_workflow.populate_project_tree(project, preserve_state=preserve_state)

    def configure_search_sidebar(self, project: LoadedProject) -> None:
        if self._window._search_sidebar is None:
            return
        from app.shell.project_tree_utils import effective_excludes_for

        self._window._search_sidebar.set_project_root(project.project_root)
        self._window._search_sidebar.set_exclude_patterns(
            effective_excludes_for(
                project,
                load_effective_exclude_patterns=self._window._file_project_commands_workflow.load_effective_exclude_patterns,
            )
        )

    def set_project_tree_structure_signature(self, signature: tuple[str, ...]) -> None:
        self._window._project_tree_structure_signature = signature

    def reload_plugin_activation(self) -> None:
        self._window._plugin_activation_workflow.reload()

    def refresh_python_tooling_status(self) -> None:
        self._window._refresh_python_tooling_status()

    def start_symbol_indexing(self, project_root: str, *, exclude_patterns: list[str]) -> None:
        self._window._intelligence_cache_workflow.start_symbol_indexing(project_root, exclude_patterns=exclude_patterns)

    def refresh_test_discovery(self) -> None:
        test_runner_workflow = getattr(self._window, "_test_runner_workflow", None)
        if test_runner_workflow is not None:
            test_runner_workflow.refresh_discovery()
