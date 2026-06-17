"""Unit tests for project rescan workflow tiers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.core.models import LoadedProject, ProjectMetadata
from app.shell.project_rescan_workflow import ProjectRescanWorkflow

pytestmark = pytest.mark.unit


def _loaded_project(tmp_path: Path) -> LoadedProject:
    metadata = ProjectMetadata(schema_version=2, name="demo")
    return LoadedProject(
        project_root=str(tmp_path),
        manifest_path=str(tmp_path / "cbcs" / "project.json"),
        metadata=metadata,
        entries=(),
    )


def test_rescan_from_disk_reindexes_when_requested(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "cbcs").mkdir()
    (project_root / "cbcs" / "project.json").write_text(
        '{"schema_version": 2, "name": "demo"}',
        encoding="utf-8",
    )
    (project_root / "main.py").write_text("print('hi')\n", encoding="utf-8")
    loaded = _loaded_project(project_root)

    host = MagicMock()
    host.loaded_project.return_value = loaded
    host.load_effective_exclude_patterns.return_value = []
    host.project_inventory_snapshot.return_value = MagicMock()

    workflow = ProjectRescanWorkflow(host)

    with patch("app.shell.project_rescan_workflow.open_project", return_value=loaded):
        workflow.rescan_from_disk(reload_plugins=False, reindex=True)

    host.start_symbol_indexing.assert_called_once()
    host.refresh_test_discovery.assert_called_once()


def test_rescan_from_disk_skips_reindex_when_disabled(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "cbcs").mkdir()
    (project_root / "cbcs" / "project.json").write_text(
        '{"schema_version": 2, "name": "demo"}',
        encoding="utf-8",
    )
    loaded = _loaded_project(project_root)

    host = MagicMock()
    host.loaded_project.return_value = loaded
    host.load_effective_exclude_patterns.return_value = []

    workflow = ProjectRescanWorkflow(host)

    with patch("app.shell.project_rescan_workflow.open_project", return_value=loaded):
        workflow.rescan_from_disk(reload_plugins=False, reindex=False)

    host.start_symbol_indexing.assert_not_called()
    host.refresh_test_discovery.assert_not_called()
