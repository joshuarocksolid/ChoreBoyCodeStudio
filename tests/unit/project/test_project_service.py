"""Unit tests for project open/load orchestration helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.errors import ProjectManifestValidationError, ProjectStructureValidationError
from app.core.models import LoadedProject
from app.project import project_service
from app.project.project_service import (
    enumerate_project_entries,
    open_project,
    validate_project_structure,
)
from app.project.recent_projects import load_recent_projects, remember_recent_project

pytestmark = pytest.mark.unit


def test_validate_project_structure_returns_resolved_project_root(tmp_path: Path) -> None:
    """A valid project layout should resolve to a stable absolute root path."""
    project_root = tmp_path / "project_alpha"
    _write_valid_manifest(project_root, name="Project Alpha")

    resolved_root = validate_project_structure(project_root)

    assert resolved_root == project_root.resolve()


def test_open_project_returns_loaded_project_for_valid_minimal_layout(tmp_path: Path) -> None:
    """Open flow should return structured project data for a valid layout."""
    project_root = tmp_path / "project_alpha"
    _write_valid_manifest(project_root, name="Project Alpha")
    (project_root / "run.py").write_text("print('hello')\n", encoding="utf-8")
    (project_root / "app").mkdir()
    (project_root / "app" / "main.py").write_text("print('app')\n", encoding="utf-8")
    (project_root / "readme.md").write_text("# project alpha\n", encoding="utf-8")

    loaded_project = open_project(project_root)

    assert isinstance(loaded_project, LoadedProject)
    assert loaded_project.project_root == str(project_root.resolve())
    assert loaded_project.manifest_path == str((project_root / ".cbcs" / "project.json").resolve())
    assert loaded_project.metadata.name == "Project Alpha"
    assert [entry.relative_path for entry in loaded_project.entries] == [
        "app",
        "app/main.py",
        "readme.md",
        "run.py",
    ]


def test_open_project_rejects_missing_project_root(tmp_path: Path) -> None:
    """Missing project folders should fail with actionable structure errors."""
    missing_root = tmp_path / "missing_project"

    with pytest.raises(ProjectStructureValidationError) as exc_info:
        open_project(missing_root)

    assert "Project folder not found" in str(exc_info.value)


def test_open_project_rejects_non_directory_project_root(tmp_path: Path) -> None:
    """Project root must be a directory path."""
    not_a_directory = tmp_path / "not_a_directory.txt"
    not_a_directory.write_text("stub\n", encoding="utf-8")

    with pytest.raises(ProjectStructureValidationError) as exc_info:
        open_project(not_a_directory)

    assert "must be a directory" in str(exc_info.value)


def test_open_project_rejects_missing_cbcs_directory(tmp_path: Path) -> None:
    """Project open should fail clearly when `.cbcs` is missing."""
    project_root = tmp_path / "project_without_cbcs"
    project_root.mkdir()

    with pytest.raises(ProjectStructureValidationError) as exc_info:
        open_project(project_root)

    assert "Missing required metadata directory" in str(exc_info.value)


def test_open_project_rejects_missing_manifest_file(tmp_path: Path) -> None:
    """Project open should fail clearly when `.cbcs/project.json` is missing."""
    project_root = tmp_path / "project_without_manifest"
    (project_root / ".cbcs").mkdir(parents=True)

    with pytest.raises(ProjectStructureValidationError) as exc_info:
        open_project(project_root)

    assert "Missing required project manifest file" in str(exc_info.value)


def test_open_project_propagates_manifest_validation_error_with_path_context(tmp_path: Path) -> None:
    """Manifest parse failures should bubble as project-manifest validation errors."""
    project_root = tmp_path / "project_bad_manifest"
    manifest_path = project_root / ".cbcs" / "project.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text("{ not valid json", encoding="utf-8")

    with pytest.raises(ProjectManifestValidationError) as exc_info:
        open_project(project_root)

    assert exc_info.value.manifest_path == manifest_path.resolve()
    assert "Invalid JSON" in str(exc_info.value)


def test_enumerate_project_entries_is_deterministic_and_excludes_cbcs(tmp_path: Path) -> None:
    """Enumeration should be stable across calls and skip internal metadata noise."""
    project_root = tmp_path / "project_tree"
    _write_valid_manifest(project_root, name="Project Tree")
    (project_root / "run.py").write_text("print('run')\n", encoding="utf-8")
    (project_root / "app").mkdir()
    (project_root / "app" / "main.py").write_text("print('main')\n", encoding="utf-8")
    (project_root / "app" / "utils").mkdir()
    (project_root / "app" / "utils" / "helpers.py").write_text("print('helpers')\n", encoding="utf-8")
    (project_root / "notes.txt").write_text("notes\n", encoding="utf-8")

    first = enumerate_project_entries(project_root)
    second = enumerate_project_entries(project_root)

    assert [entry.to_dict() for entry in first] == [entry.to_dict() for entry in second]
    assert [entry.relative_path for entry in first] == [
        "app",
        "app/main.py",
        "app/utils",
        "app/utils/helpers.py",
        "notes.txt",
        "run.py",
    ]
    assert all(not entry.relative_path.startswith(".cbcs") for entry in first)


def test_open_project_and_track_recent_updates_recents_on_success(tmp_path: Path) -> None:
    """Successful open should persist project path into recent projects."""
    project_root = tmp_path / "tracked_project"
    _write_valid_manifest(project_root, name="Tracked Project")

    loaded_project = project_service.open_project_and_track_recent(project_root, state_root=tmp_path / "state")

    assert loaded_project.project_root == str(project_root.resolve())
    assert load_recent_projects(state_root=tmp_path / "state") == [str(project_root.resolve())]


def test_open_project_and_track_recent_does_not_mutate_recents_on_failure(tmp_path: Path) -> None:
    """Failed open should leave the existing recent-project list unchanged."""
    state_root = tmp_path / "state"
    valid_project = tmp_path / "valid_project"
    _write_valid_manifest(valid_project, name="Valid Project")
    remember_recent_project(valid_project, state_root=state_root)

    with pytest.raises(ProjectStructureValidationError):
        project_service.open_project_and_track_recent(tmp_path / "missing_project", state_root=state_root)

    assert load_recent_projects(state_root=state_root) == [str(valid_project.resolve())]


def _write_valid_manifest(project_root: Path, *, name: str) -> Path:
    manifest_path = project_root / ".cbcs" / "project.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": name,
            }
        ),
        encoding="utf-8",
    )
    return manifest_path
