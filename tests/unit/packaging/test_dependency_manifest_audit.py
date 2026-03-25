"""Unit tests for dependency manifest consistency checks."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.packaging.dependency_audit import check_manifest_consistency
from app.project.dependency_manifest import (
    CLASSIFICATION_PURE_PYTHON,
    DependencyEntry,
    DependencyManifest,
    SOURCE_WHEEL,
    save_dependency_manifest,
)

pytestmark = pytest.mark.unit


def _project_with_manifest(tmp_path: Path, entries: list[DependencyEntry]) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    (project / "cbcs").mkdir()
    manifest = DependencyManifest()
    for entry in entries:
        manifest.add_entry(entry)
    save_dependency_manifest(str(project), manifest)
    return project


def test_manifest_consistency_passes_when_vendor_exists(tmp_path: Path) -> None:
    entry = DependencyEntry(
        name="sample_pkg",
        version="1.0",
        source=SOURCE_WHEEL,
        classification=CLASSIFICATION_PURE_PYTHON,
        vendor_path="vendor/sample_pkg",
    )
    project = _project_with_manifest(tmp_path, [entry])
    (project / "vendor" / "sample_pkg").mkdir(parents=True)

    issues = check_manifest_consistency(project_root=str(project))
    assert len(issues) == 0


def test_manifest_consistency_reports_missing_vendor_dir(tmp_path: Path) -> None:
    entry = DependencyEntry(
        name="missing_pkg",
        version="1.0",
        source=SOURCE_WHEEL,
        classification=CLASSIFICATION_PURE_PYTHON,
        vendor_path="vendor/missing_pkg",
    )
    project = _project_with_manifest(tmp_path, [entry])

    issues = check_manifest_consistency(project_root=str(project))
    assert len(issues) == 1
    assert issues[0].severity == "blocking"
    assert "missing_pkg" in issues[0].title


def test_manifest_consistency_ignores_removed_entries(tmp_path: Path) -> None:
    entry = DependencyEntry(
        name="removed_pkg",
        version="1.0",
        source=SOURCE_WHEEL,
        classification=CLASSIFICATION_PURE_PYTHON,
        vendor_path="vendor/removed_pkg",
        status="removed",
    )
    project = _project_with_manifest(tmp_path, [entry])

    issues = check_manifest_consistency(project_root=str(project))
    assert len(issues) == 0


def test_manifest_consistency_empty_manifest(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    issues = check_manifest_consistency(project_root=str(project))
    assert len(issues) == 0
