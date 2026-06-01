"""Orchestrates shell-side work after a project finishes loading from disk."""

from __future__ import annotations

import logging
import time
from typing import Protocol

from app.core.models import LoadedProject
from app.project.vendor_exclude_migration import maybe_persist_vendor_exclude
from app.shell.project_open_telemetry import ProjectOpenTelemetry
from app.shell.project_tree_utils import effective_excludes_for


class ProjectLoadHost(Protocol):
    """Phase-sized ports ``ProjectLoadWorkflow`` needs from the shell."""

    @property
    def loaded_project(self) -> LoadedProject | None:
        ...

    @property
    def logger(self) -> logging.Logger:
        ...

    def prepare_project_switch(self) -> None:
        ...

    def apply_project_surface(self, loaded_project: LoadedProject) -> None:
        ...

    def populate_project_tree(self, loaded_project: LoadedProject) -> None:
        ...

    def restore_project_session(self, project_root: str) -> None:
        ...

    def finalize_project_open(
        self,
        loaded_project: LoadedProject,
        telemetry: ProjectOpenTelemetry,
        *,
        exclude_patterns: list[str],
    ) -> None:
        ...

    def load_effective_exclude_patterns(self, project_root: str) -> list[str]:
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
        self.prepare_switch(loaded_project, telemetry)
        loaded_project = self.enumerate_project(loaded_project, telemetry)
        self.apply_surface(loaded_project, telemetry)
        self.restore_session(loaded_project, telemetry)
        exclude_patterns = self._effective_excludes(loaded_project)
        self.finalize_open(loaded_project, telemetry, exclude_patterns=exclude_patterns)
        return telemetry

    def prepare_switch(self, loaded_project: LoadedProject, telemetry: ProjectOpenTelemetry) -> None:
        del loaded_project, telemetry
        self._host.prepare_project_switch()

    def enumerate_project(
        self,
        loaded_project: LoadedProject,
        telemetry: ProjectOpenTelemetry,
    ) -> LoadedProject:
        enumerate_started = time.perf_counter()
        loaded_project = maybe_persist_vendor_exclude(
            loaded_project,
            logger=self._host.logger,
        )
        telemetry.mark_enumerate(entry_count=len(loaded_project.entries))
        telemetry.enumerate_ms = (time.perf_counter() - enumerate_started) * 1000.0
        return loaded_project

    def apply_surface(self, loaded_project: LoadedProject, telemetry: ProjectOpenTelemetry) -> None:
        self._host.apply_project_surface(loaded_project)
        tree_started = time.perf_counter()
        self._host.populate_project_tree(loaded_project)
        telemetry.tree_ms = (time.perf_counter() - tree_started) * 1000.0

    def restore_session(self, loaded_project: LoadedProject, telemetry: ProjectOpenTelemetry) -> None:
        session_started = time.perf_counter()
        self._host.restore_project_session(loaded_project.project_root)
        telemetry.session_restore_ms = (time.perf_counter() - session_started) * 1000.0

    def finalize_open(
        self,
        loaded_project: LoadedProject,
        telemetry: ProjectOpenTelemetry,
        *,
        exclude_patterns: list[str],
    ) -> None:
        self._host.finalize_project_open(
            loaded_project,
            telemetry,
            exclude_patterns=exclude_patterns,
        )

    def _effective_excludes(self, loaded_project: LoadedProject) -> list[str]:
        return effective_excludes_for(
            loaded_project,
            load_effective_exclude_patterns=self._host.load_effective_exclude_patterns,
        )
