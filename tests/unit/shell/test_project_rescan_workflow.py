"""Unit tests for project rescan workflow tiers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.core.models import LoadedProject, ProjectFileEntry, ProjectMetadata
from app.shell.project_rescan_workflow import ProjectRescanWorkflow, RefreshTier

pytestmark = pytest.mark.unit


def _loaded_project(tmp_path: Path) -> LoadedProject:
    metadata = ProjectMetadata(schema_version=2, name="demo")
    return LoadedProject(
        project_root=str(tmp_path),
        manifest_path=str(tmp_path / "cbcs" / "project.json"),
        metadata=metadata,
        entries=(),
    )


def test_refresh_tree_entries_skips_open_project(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    loaded = _loaded_project(project_root)
    new_entry = ProjectFileEntry(
        relative_path="main.py",
        absolute_path=str(project_root / "main.py"),
        is_directory=False,
    )

    host = MagicMock()
    host.loaded_project.return_value = loaded
    host.load_effective_exclude_patterns.return_value = []
    host.project_inventory_snapshot.return_value = MagicMock(python_file_paths=("before",))

    workflow = ProjectRescanWorkflow(host)

    with patch("app.shell.project_rescan_workflow.open_project") as open_project:
        with patch(
            "app.shell.project_rescan_workflow.enumerate_project_entries",
            return_value=[new_entry],
        ) as enumerate_entries:
            workflow.refresh(RefreshTier.TREE_ENTRIES)

    open_project.assert_not_called()
    enumerate_entries.assert_called_once()
    host.apply_tree_entries_surface.assert_called_once()
    refreshed = host.apply_tree_entries_surface.call_args.args[0]
    assert refreshed.entries == [new_entry]


def test_refresh_metadata_only_is_noop(tmp_path: Path) -> None:
    loaded = _loaded_project(tmp_path / "project")
    host = MagicMock()
    host.loaded_project.return_value = loaded
    workflow = ProjectRescanWorkflow(host)

    with patch("app.shell.project_rescan_workflow.open_project") as open_project:
        with patch("app.shell.project_rescan_workflow.enumerate_project_entries") as enumerate_entries:
            workflow.refresh(RefreshTier.METADATA_ONLY)

    open_project.assert_not_called()
    enumerate_entries.assert_not_called()
    host.apply_tree_entries_surface.assert_not_called()


def test_rescan_from_disk_reindexes_when_requested(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    loaded = _loaded_project(project_root)

    host = MagicMock()
    host.loaded_project.return_value = loaded
    host.load_effective_exclude_patterns.return_value = []
    host.project_inventory_snapshot.return_value = MagicMock(python_file_paths=())

    workflow = ProjectRescanWorkflow(host)

    with patch("app.shell.project_rescan_workflow.open_project") as open_project:
        with patch("app.shell.project_rescan_workflow.enumerate_project_entries", return_value=[]):
            workflow.rescan_from_disk(reload_plugins=False, reindex=True)

    open_project.assert_not_called()
    host.start_symbol_indexing.assert_called_once()
    host.refresh_test_discovery.assert_called_once()


def test_rescan_from_disk_light_path_uses_tree_entries(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    loaded = _loaded_project(project_root)

    host = MagicMock()
    host.loaded_project.return_value = loaded
    host.load_effective_exclude_patterns.return_value = []
    host.project_inventory_snapshot.return_value = MagicMock(python_file_paths=())

    workflow = ProjectRescanWorkflow(host)

    with patch("app.shell.project_rescan_workflow.open_project") as open_project:
        with patch("app.shell.project_rescan_workflow.enumerate_project_entries", return_value=[]):
            workflow.rescan_from_disk(reload_plugins=False, reindex=False)

    open_project.assert_not_called()
    host.apply_tree_entries_surface.assert_called_once()


def test_rescan_from_disk_skips_reindex_when_disabled(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    loaded = _loaded_project(project_root)
    stable_snapshot = MagicMock(python_file_paths=("src/main.py",))

    host = MagicMock()
    host.loaded_project.return_value = loaded
    host.load_effective_exclude_patterns.return_value = []
    host.project_inventory_snapshot.return_value = stable_snapshot

    workflow = ProjectRescanWorkflow(host)

    with patch("app.shell.project_rescan_workflow.open_project") as open_project:
        with patch("app.shell.project_rescan_workflow.enumerate_project_entries", return_value=[]):
            workflow.rescan_from_disk(reload_plugins=False, reindex=False)

    open_project.assert_not_called()
    host.start_symbol_indexing.assert_not_called()
    host.refresh_test_discovery.assert_not_called()
