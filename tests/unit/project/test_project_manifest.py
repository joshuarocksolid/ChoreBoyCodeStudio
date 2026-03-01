"""Unit tests for project metadata manifest loading and validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.errors import ProjectManifestValidationError
from app.core.models import ProjectMetadata
from app.project.project_manifest import (
    PROJECT_METADATA_SCHEMA_VERSION,
    load_project_manifest,
    parse_project_manifest,
)

pytestmark = pytest.mark.unit


def test_load_project_manifest_returns_structured_model_for_minimal_valid_payload(tmp_path: Path) -> None:
    """Minimal valid payload should load into a structured metadata model."""
    manifest_path = tmp_path / ".cbcs" / "project.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": PROJECT_METADATA_SCHEMA_VERSION,
                "name": "Alpha Project",
            }
        ),
        encoding="utf-8",
    )

    metadata = load_project_manifest(manifest_path)

    assert isinstance(metadata, ProjectMetadata)
    assert metadata.schema_version == PROJECT_METADATA_SCHEMA_VERSION
    assert metadata.name == "Alpha Project"


def test_load_project_manifest_applies_explicit_defaults() -> None:
    """Defaults should be explicit and stable when optional fields are missing."""
    metadata = parse_project_manifest(
        {
            "schema_version": PROJECT_METADATA_SCHEMA_VERSION,
            "name": "Defaulted Project",
        }
    )

    assert metadata.to_dict() == {
        "schema_version": PROJECT_METADATA_SCHEMA_VERSION,
        "name": "Defaulted Project",
        "default_entry": "run.py",
        "default_mode": "python_script",
        "working_directory": ".",
        "template": "utility_script",
        "safe_mode": True,
        "run_configs": [],
        "env_overrides": {},
        "project_notes": "",
    }


def test_load_project_manifest_rejects_non_object_payload() -> None:
    """The manifest root must be a JSON object."""
    with pytest.raises(ProjectManifestValidationError) as exc_info:
        parse_project_manifest(["not", "an", "object"])  # type: ignore[arg-type]

    assert "must be a JSON object" in str(exc_info.value)


def test_load_project_manifest_rejects_missing_required_name() -> None:
    """A clear validation error should be raised for missing required keys."""
    with pytest.raises(ProjectManifestValidationError) as exc_info:
        parse_project_manifest({"schema_version": PROJECT_METADATA_SCHEMA_VERSION})

    assert exc_info.value.field == "name"
    assert "Missing required field" in str(exc_info.value)


def test_load_project_manifest_rejects_invalid_safe_mode_type() -> None:
    """safe_mode must be boolean when provided."""
    with pytest.raises(ProjectManifestValidationError) as exc_info:
        parse_project_manifest(
            {
                "schema_version": PROJECT_METADATA_SCHEMA_VERSION,
                "name": "Bad Safe Mode",
                "safe_mode": "yes",
            }
        )

    assert exc_info.value.field == "safe_mode"
    assert "must be a boolean" in str(exc_info.value)


def test_load_project_manifest_rejects_invalid_run_configs_type() -> None:
    """run_configs must be a list for predictable downstream behavior."""
    with pytest.raises(ProjectManifestValidationError) as exc_info:
        parse_project_manifest(
            {
                "schema_version": PROJECT_METADATA_SCHEMA_VERSION,
                "name": "Bad Run Configs",
                "run_configs": {"name": "not-a-list"},
            }
        )

    assert exc_info.value.field == "run_configs"
    assert "must be a list" in str(exc_info.value)


def test_load_project_manifest_rejects_unsupported_schema_version() -> None:
    """Unknown schema versions should fail with actionable messaging."""
    with pytest.raises(ProjectManifestValidationError) as exc_info:
        parse_project_manifest({"schema_version": 999, "name": "Future Project"})

    assert exc_info.value.field == "schema_version"
    assert "Unsupported schema_version" in str(exc_info.value)


def test_load_project_manifest_rejects_unknown_default_mode() -> None:
    """default_mode must be an allowed runtime mode value."""
    with pytest.raises(ProjectManifestValidationError) as exc_info:
        parse_project_manifest(
            {
                "schema_version": PROJECT_METADATA_SCHEMA_VERSION,
                "name": "Bad Mode",
                "default_mode": "future_mode",
            }
        )

    assert exc_info.value.field == "default_mode"
    assert "Unsupported default_mode" in str(exc_info.value)


def test_load_project_manifest_rejects_malformed_json_with_manifest_path(tmp_path: Path) -> None:
    """Malformed JSON should raise a validation error tied to the source path."""
    manifest_path = tmp_path / ".cbcs" / "project.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text("{ this is not valid json", encoding="utf-8")

    with pytest.raises(ProjectManifestValidationError) as exc_info:
        load_project_manifest(manifest_path)

    assert exc_info.value.manifest_path == manifest_path.resolve()
    assert "Invalid JSON" in str(exc_info.value)
