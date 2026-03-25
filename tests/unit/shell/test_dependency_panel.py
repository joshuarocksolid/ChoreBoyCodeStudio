"""Unit tests for dependency inspector panel helpers."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.project.dependency_manifest import (
    CLASSIFICATION_NATIVE_EXTENSION,
    CLASSIFICATION_PURE_PYTHON,
    DependencyEntry,
    DependencyManifest,
    STATUS_ACTIVE,
    STATUS_REMOVED,
    load_dependency_manifest,
    save_dependency_manifest,
)
from app.project.dependency_ingest import remove_vendored_dependency
from app.shell.dependency_panel import _display_classification

pytestmark = pytest.mark.unit


def _project_root(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    (project / "cbcs").mkdir()
    return project


def test_display_classification_pure_python() -> None:
    assert _display_classification(CLASSIFICATION_PURE_PYTHON) == "Pure Python"


def test_display_classification_native_extension() -> None:
    result = _display_classification(CLASSIFICATION_NATIVE_EXTENSION)
    assert "Native Extension" in result


def test_display_classification_unknown() -> None:
    result = _display_classification("some_unknown")
    assert result == "Some Unknown"


def test_remove_via_panel_marks_removed_in_manifest(tmp_path: Path) -> None:
    project = _project_root(tmp_path)
    manifest = DependencyManifest()
    manifest.add_entry(DependencyEntry(
        name="test_pkg", version="1.0", source="wheel",
        classification=CLASSIFICATION_PURE_PYTHON,
    ))
    save_dependency_manifest(str(project), manifest)

    success = remove_vendored_dependency(project_root=str(project), name="test_pkg")
    assert success is True

    loaded = load_dependency_manifest(str(project))
    assert loaded.find_by_name("test_pkg").status == STATUS_REMOVED


def test_inspector_shows_active_and_removed_entries(tmp_path: Path) -> None:
    project = _project_root(tmp_path)
    manifest = DependencyManifest()
    manifest.add_entry(DependencyEntry(
        name="active_pkg", version="1.0", source="wheel",
        classification=CLASSIFICATION_PURE_PYTHON,
    ))
    manifest.add_entry(DependencyEntry(
        name="removed_pkg", version="2.0", source="folder",
        classification=CLASSIFICATION_NATIVE_EXTENSION, status=STATUS_REMOVED,
    ))
    save_dependency_manifest(str(project), manifest)

    loaded = load_dependency_manifest(str(project))
    assert len(loaded.active_entries()) == 1
    assert len(loaded.removed_entries()) == 1
