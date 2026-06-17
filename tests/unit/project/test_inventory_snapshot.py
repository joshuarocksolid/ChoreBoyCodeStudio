"""Unit tests for project inventory snapshot builder."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.project.file_inventory import (
    ProjectInventorySnapshot,
    build_project_inventory_snapshot,
    module_names_from_snapshot,
)
from tests.unit.project.inventory_parity_fixtures import build_fixture_tree

pytestmark = pytest.mark.unit


def test_build_project_inventory_snapshot_collects_python_paths_and_modules(tmp_path: Path) -> None:
    build_fixture_tree(tmp_path, "src_layout")

    snapshot = build_project_inventory_snapshot(tmp_path)

    assert isinstance(snapshot, ProjectInventorySnapshot)
    assert snapshot.project_root == str(tmp_path.resolve())
    assert any(path.endswith("module.py") for path in snapshot.python_file_paths)
    assert "my_pkg.module" in snapshot.module_names
    assert module_names_from_snapshot(snapshot) == list(snapshot.module_names)


def test_build_project_inventory_snapshot_honors_exclude_patterns(tmp_path: Path) -> None:
    build_fixture_tree(tmp_path, "slash_exclude")

    snapshot = build_project_inventory_snapshot(
        tmp_path,
        exclude_patterns=["src/generated/*"],
    )

    relative_paths = {
        Path(path).relative_to(tmp_path).as_posix() for path in snapshot.python_file_paths
    }
    assert "src/generated/code.py" not in relative_paths
    assert "src/my_pkg/module.py" in relative_paths
