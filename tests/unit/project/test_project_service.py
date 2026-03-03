"""Unit tests for project open/load orchestration helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.errors import AppValidationError, ProjectManifestValidationError, ProjectStructureValidationError
from app.core.models import LoadedProject
from app.project import project_service
from app.project.project_service import (
    create_blank_project,
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


def test_create_blank_project_writes_manifest_and_main_entrypoint(tmp_path: Path) -> None:
    """Blank project creation should seed canonical metadata and root main.py."""
    destination = tmp_path / "blank_project"

    created_path = create_blank_project(destination, project_name="Blank Project")
    manifest_path = created_path / ".cbcs" / "project.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert created_path == destination.resolve()
    assert (created_path / "main.py").exists()
    assert payload["name"] == "Blank Project"
    assert payload["default_entry"] == "main.py"
    assert payload["template"] == "blank_project"


def test_create_blank_project_rejects_non_empty_destination(tmp_path: Path) -> None:
    """Blank project creation should fail when destination has existing files."""
    destination = tmp_path / "existing_project"
    destination.mkdir(parents=True)
    (destination / "notes.txt").write_text("already here\n", encoding="utf-8")

    with pytest.raises(AppValidationError, match="Destination is not empty"):
        create_blank_project(destination, project_name="Existing Project")


def test_open_project_auto_initializes_missing_cbcs_directory(tmp_path: Path) -> None:
    """Opening a plain Python folder should create canonical project metadata."""
    project_root = tmp_path / "project_without_cbcs"
    project_root.mkdir()
    (project_root / "run.py").write_text("print('hello')\n", encoding="utf-8")

    loaded_project = open_project(project_root)
    manifest_path = project_root / ".cbcs" / "project.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert loaded_project.metadata.name == "project_without_cbcs"
    assert loaded_project.metadata.default_entry == "run.py"
    assert manifest_path.exists()
    assert payload["template"] == "imported_external"


def test_open_project_auto_initializes_missing_manifest_file(tmp_path: Path) -> None:
    """Opening a folder with `.cbcs` but no manifest should regenerate metadata."""
    project_root = tmp_path / "project_without_manifest"
    (project_root / ".cbcs").mkdir(parents=True)
    (project_root / "main.py").write_text("print('hello')\n", encoding="utf-8")

    loaded_project = open_project(project_root)

    assert loaded_project.metadata.default_entry == "main.py"
    assert (project_root / ".cbcs" / "project.json").exists()


def test_open_project_auto_initialize_prefers_priority_entrypoint_names(tmp_path: Path) -> None:
    """Entrypoint inference should prefer main.py over other common names."""
    project_root = tmp_path / "priority_project"
    project_root.mkdir()
    (project_root / "__main__.py").write_text("print('__main__')\n", encoding="utf-8")
    (project_root / "main.py").write_text("print('main')\n", encoding="utf-8")
    (project_root / "run.py").write_text("print('run')\n", encoding="utf-8")
    (project_root / "aaa.py").write_text("print('aaa')\n", encoding="utf-8")

    loaded_project = open_project(project_root)

    assert loaded_project.metadata.default_entry == "main.py"


def test_open_project_auto_initialize_prefers_pyproject_script_module_entrypoint(tmp_path: Path) -> None:
    """Pyproject script targets should inform inferred default entrypoint."""
    project_root = tmp_path / "pyproject_script_project"
    (project_root / "src" / "my_app").mkdir(parents=True)
    (project_root / "src" / "my_app" / "cli.py").write_text("def main():\n    return 0\n", encoding="utf-8")
    (project_root / "pyproject.toml").write_text(
        "[project]\n"
        "name = \"my-app\"\n"
        "[project.scripts]\n"
        "my-app = \"my_app.cli:main\"\n",
        encoding="utf-8",
    )
    (project_root / "run.py").write_text("print('legacy run')\n", encoding="utf-8")

    loaded_project = open_project(project_root)

    assert loaded_project.metadata.default_entry == "src/my_app/cli.py"


def test_open_project_auto_initialize_uses_top_level_python_before_recursive(tmp_path: Path) -> None:
    """Top-level python files should be preferred over nested files after priority names."""
    project_root = tmp_path / "top_level_project"
    (project_root / "pkg").mkdir(parents=True)
    (project_root / "pkg" / "nested.py").write_text("print('nested')\n", encoding="utf-8")
    (project_root / "b.py").write_text("print('b')\n", encoding="utf-8")
    (project_root / "a.py").write_text("print('a')\n", encoding="utf-8")

    loaded_project = open_project(project_root)

    assert loaded_project.metadata.default_entry == "a.py"


def test_open_project_auto_initialize_uses_recursive_python_when_no_top_level(tmp_path: Path) -> None:
    """When no top-level `.py` exists, first recursive `.py` should be used."""
    project_root = tmp_path / "recursive_project"
    (project_root / "app").mkdir(parents=True)
    (project_root / "app" / "entry.py").write_text("print('entry')\n", encoding="utf-8")

    loaded_project = open_project(project_root)

    assert loaded_project.metadata.default_entry == "app/entry.py"


def test_open_project_auto_initialize_prefers_recursive_package_main_before_generic_recursive(tmp_path: Path) -> None:
    """Nested package __main__.py should be preferred for package-like projects."""
    project_root = tmp_path / "package_main_project"
    (project_root / "src" / "package_a").mkdir(parents=True)
    (project_root / "src" / "package_a" / "__main__.py").write_text("print('pkg main')\n", encoding="utf-8")
    (project_root / "src" / "package_a" / "runner.py").write_text("print('runner')\n", encoding="utf-8")

    loaded_project = open_project(project_root)

    assert loaded_project.metadata.default_entry == "src/package_a/__main__.py"


def test_open_project_rejects_missing_metadata_when_no_python_files(tmp_path: Path) -> None:
    """Metadata auto-init should fail clearly when folder has no Python files."""
    project_root = tmp_path / "not_a_python_project"
    project_root.mkdir()
    (project_root / "README.md").write_text("# hello\n", encoding="utf-8")

    with pytest.raises(ProjectStructureValidationError) as exc_info:
        open_project(project_root)

    assert "no Python files were found" in str(exc_info.value)


def test_validate_project_structure_rejects_missing_cbcs_directory(tmp_path: Path) -> None:
    """Structure validation remains strict for callers that require canonical metadata."""
    project_root = tmp_path / "project_without_cbcs"
    project_root.mkdir()

    with pytest.raises(ProjectStructureValidationError) as exc_info:
        validate_project_structure(project_root)

    assert "Missing required metadata directory" in str(exc_info.value)


def test_validate_project_structure_rejects_missing_manifest_file(tmp_path: Path) -> None:
    """Structure validation should fail clearly when `.cbcs/project.json` is missing."""
    project_root = tmp_path / "project_without_manifest"
    (project_root / ".cbcs").mkdir(parents=True)

    with pytest.raises(ProjectStructureValidationError) as exc_info:
        validate_project_structure(project_root)

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
