"""MainWindow adapter for ``ProjectLoadWorkflow``."""

from __future__ import annotations

import logging
from typing import Any

from app.core.models import LoadedProject
from app.shell.project_load_surface import apply_project_surface, finalize_project_open
from app.shell.project_open_telemetry import ProjectOpenTelemetry


class MainWindowProjectLoadHost:
    """Maps ``MainWindow`` state mutations into ``ProjectLoadWorkflow`` phases."""

    def __init__(self, window: Any) -> None:
        self._window = window

    @property
    def loaded_project(self) -> LoadedProject | None:
        return self._window._loaded_project

    @property
    def logger(self) -> logging.Logger:
        return self._window._logger

    def load_effective_exclude_patterns(self, project_root: str) -> list[str]:
        return self._window._load_effective_exclude_patterns(project_root)

    def prepare_project_switch(self) -> None:
        window = self._window
        window.statusBar().showMessage("Opening project…", 0)
        window._cancel_pending_project_tree_preview()
        previous_project = window._loaded_project
        if previous_project is not None:
            window._local_history_workflow.persist_session_state(
                project_root=previous_project.project_root
            )

    def populate_project_tree(self, loaded_project: LoadedProject) -> None:
        self._window.statusBar().showMessage("Building project tree…", 0)
        self._window._populate_project_tree(loaded_project)

    def apply_project_surface(self, loaded_project: LoadedProject) -> None:
        apply_project_surface(
            self._window,
            loaded_project,
            load_effective_exclude_patterns=self.load_effective_exclude_patterns,
        )

    def restore_project_session(self, project_root: str) -> None:
        self._window._local_history_workflow.restore_session_state(project_root)

    def finalize_project_open(
        self,
        loaded_project: LoadedProject,
        telemetry: ProjectOpenTelemetry,
        *,
        exclude_patterns: list[str],
    ) -> None:
        finalize_project_open(
            self._window,
            loaded_project,
            telemetry,
            exclude_patterns=exclude_patterns,
        )
