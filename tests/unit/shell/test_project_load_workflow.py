"""Unit tests for project load workflow phase orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from app.core.models import LoadedProject, ProjectMetadata
from app.shell.project_load_workflow import ProjectLoadWorkflow
from app.shell.project_open_telemetry import ProjectOpenTelemetry

pytestmark = pytest.mark.unit


@dataclass
class RecordingProjectLoadHost:
    loaded: LoadedProject | None = None
    phases: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)

    @property
    def loaded_project(self) -> LoadedProject | None:
        return self.loaded

    def load_effective_exclude_patterns(self, project_root: str) -> list[str]:
        return [f"exclude:{project_root}"]

    def prepare_project_switch(self, telemetry: ProjectOpenTelemetry) -> None:
        self.phases.append("prepare")

    def apply_project_surface(
        self,
        loaded_project: LoadedProject,
        telemetry: ProjectOpenTelemetry,
    ) -> None:
        self.loaded = loaded_project
        self.phases.append("surface")

    def restore_project_session(self, project_root: str, telemetry: ProjectOpenTelemetry) -> None:
        self.phases.append("session")

    def finalize_project_open(
        self,
        loaded_project: LoadedProject,
        telemetry: ProjectOpenTelemetry,
        *,
        exclude_patterns: list[str],
    ) -> None:
        self.exclude_patterns = list(exclude_patterns)
        self.phases.append("finalize")

    def migration_logger(self) -> Any:
        import logging

        return logging.getLogger("test.project_load_workflow")


def _loaded_project(tmp_path) -> LoadedProject:
    project_root = tmp_path / "demo"
    project_root.mkdir()
    (project_root / "main.py").write_text("print('hi')\n", encoding="utf-8")
    metadata = ProjectMetadata(schema_version=2, name="demo")
    return LoadedProject(
        project_root=str(project_root),
        manifest_path=str(project_root / "cbcs" / "project.json"),
        metadata=metadata,
        entries=(),
    )


def test_project_load_workflow_runs_phases_in_order(tmp_path) -> None:
    host = RecordingProjectLoadHost()
    workflow = ProjectLoadWorkflow(host)
    loaded_project = _loaded_project(tmp_path)

    telemetry = workflow.apply(loaded_project, started_at=0.0)

    assert host.phases == ["prepare", "surface", "session", "finalize"]
    assert telemetry.project_root == loaded_project.project_root
    assert host.exclude_patterns == [f"exclude:{loaded_project.project_root}"]
