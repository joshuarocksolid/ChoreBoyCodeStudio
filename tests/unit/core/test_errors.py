"""Unit tests for core error contracts."""

from pathlib import Path

import pytest

from app.core.errors import (
    AppValidationError,
    ProjectEnumerationError,
    ProjectLoadValidationError,
    ProjectManifestValidationError,
    ProjectStructureValidationError,
)

pytestmark = pytest.mark.unit


def test_project_manifest_validation_error_keeps_field_and_manifest_path_context() -> None:
    """Project manifest errors should preserve actionable context for diagnostics."""
    error = ProjectManifestValidationError(
        "Missing required field.",
        field="name",
        manifest_path=Path("/tmp/example/.cbcs/project.json"),
    )

    assert error.field == "name"
    assert error.manifest_path == Path("/tmp/example/.cbcs/project.json")
    assert "field=name" in str(error)
    assert "path=/tmp/example/.cbcs/project.json" in str(error)


def test_project_manifest_validation_error_is_validation_error() -> None:
    """Project manifest error should remain catchable as generic validation error."""
    error = ProjectManifestValidationError("Invalid manifest")
    assert isinstance(error, AppValidationError)
    assert isinstance(error, ValueError)


def test_project_structure_validation_error_keeps_project_root_context() -> None:
    """Project structure errors should preserve root context for diagnostics."""
    error = ProjectStructureValidationError(
        "Project folder is missing .cbcs directory.",
        project_root=Path("/tmp/example_project"),
    )

    assert error.project_root == Path("/tmp/example_project")
    assert "project_root=/tmp/example_project" in str(error)
    assert isinstance(error, ProjectLoadValidationError)


def test_project_enumeration_error_is_project_load_validation_error() -> None:
    """Enumeration failures should share the project-load validation hierarchy."""
    error = ProjectEnumerationError(
        "Failed to enumerate project files.",
        project_root=Path("/tmp/example_project"),
    )

    assert isinstance(error, ProjectLoadValidationError)
    assert isinstance(error, AppValidationError)
