"""Unit tests for shell project inventory orchestration."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.project.file_excludes import EffectiveExcludes
from app.project.file_inventory import build_project_inventory_snapshot
from app.shell.project_inventory_orchestrator import ProjectInventoryOrchestrator
from tests.unit.project.inventory_parity_fixtures import build_fixture_tree

pytestmark = pytest.mark.unit


def test_orchestrator_rebuild_increments_generation_and_caches_snapshot(tmp_path: Path) -> None:
    build_fixture_tree(tmp_path, "flat_layout")
    orchestrator = ProjectInventoryOrchestrator()
    effective = EffectiveExcludes.merge()

    first = orchestrator.rebuild(str(tmp_path), effective)
    second = orchestrator.rebuild(str(tmp_path), effective)

    assert first.generation == 1
    assert second.generation == 2
    assert orchestrator.snapshot is second.snapshot
    assert orchestrator.python_paths_fingerprint() == second.snapshot.python_file_paths


def test_orchestrator_snapshot_matches_direct_builder(tmp_path: Path) -> None:
    build_fixture_tree(tmp_path, "vendor")
    effective = EffectiveExcludes.merge("vendor")
    orchestrator = ProjectInventoryOrchestrator()

    owned = orchestrator.rebuild(str(tmp_path), effective)
    direct = build_project_inventory_snapshot(tmp_path, exclude_patterns=effective.as_list())

    assert owned.snapshot.python_file_paths == direct.python_file_paths
    assert owned.snapshot.module_names == direct.module_names


def test_orchestrator_rebuild_increments_walk_count(tmp_path: Path) -> None:
    build_fixture_tree(tmp_path, "flat_layout")
    orchestrator = ProjectInventoryOrchestrator()
    effective = EffectiveExcludes.merge()

    assert orchestrator.walk_count == 0
    orchestrator.rebuild(str(tmp_path), effective)
    assert orchestrator.walk_count == 1
    orchestrator.rebuild(str(tmp_path), effective)
    assert orchestrator.walk_count == 2


def test_orchestrator_rebuild_from_loaded_does_not_walk_disk(tmp_path: Path) -> None:
    from app.core.models import LoadedProject, ProjectMetadata, ProjectFileEntry

    build_fixture_tree(tmp_path, "flat_layout")
    orchestrator = ProjectInventoryOrchestrator()
    effective = EffectiveExcludes.merge()
    main_py = tmp_path / "main.py"
    loaded = LoadedProject(
        project_root=str(tmp_path),
        manifest_path=str(tmp_path / "cbcs" / "project.json"),
        metadata=ProjectMetadata(schema_version=2, name="demo"),
        entries=(
            ProjectFileEntry(
                relative_path="main.py",
                absolute_path=str(main_py),
                is_directory=False,
            ),
        ),
    )

    orchestrator.rebuild_from_loaded(loaded, effective)

    assert orchestrator.walk_count == 0
    assert orchestrator.snapshot is not None
    assert orchestrator.snapshot.python_file_paths == (str(main_py.resolve()),)
