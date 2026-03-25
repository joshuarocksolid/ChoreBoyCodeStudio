"""Unit tests for project metadata manifest loading and validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.errors import ProjectManifestValidationError
from app.core.models import ProjectMetadata
from app.project.project_manifest import (
    PROJECT_ID_PREFIX,
    PROJECT_METADATA_SCHEMA_VERSION,
    build_default_project_manifest_payload,
    ensure_project_id,
    load_project_manifest,
    parse_project_manifest,
    set_project_default_entry,
)

pytestmark = pytest.mark.unit


def test_load_project_manifest_returns_structured_model_for_minimal_valid_payload(tmp_path: Path) -> None:
    """Minimal valid payload should load into a structured metadata model."""
    manifest_path = tmp_path / "cbcs" / "project.json"
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
    assert metadata.project_id.startswith(PROJECT_ID_PREFIX)


def test_load_project_manifest_applies_explicit_defaults() -> None:
    """Defaults should be explicit and stable when optional fields are missing."""
    metadata = parse_project_manifest(
        {
            "schema_version": PROJECT_METADATA_SCHEMA_VERSION,
            "name": "Defaulted Project",
        }
    )

    payload = metadata.to_dict()

    assert payload.pop("project_id").startswith(PROJECT_ID_PREFIX)
    assert payload == {
        "schema_version": PROJECT_METADATA_SCHEMA_VERSION,
        "name": "Defaulted Project",
        "default_entry": "main.py",
        "default_argv": [],
        "working_directory": ".",
        "template": "utility_script",
        "run_configs": [],
        "env_overrides": {},
        "project_notes": "",
    }


def test_build_default_project_manifest_payload_returns_canonical_defaults() -> None:
    """Default payload helper should emit deterministic canonical manifest fields."""
    payload = build_default_project_manifest_payload(project_name="Imported Project")

    project_id = payload.pop("project_id")

    assert project_id.startswith(PROJECT_ID_PREFIX)
    assert payload == {
        "schema_version": PROJECT_METADATA_SCHEMA_VERSION,
        "name": "Imported Project",
        "default_entry": "main.py",
        "default_argv": [],
        "working_directory": ".",
        "template": "utility_script",
        "run_configs": [],
        "env_overrides": {},
        "project_notes": "",
    }


def test_parse_project_manifest_rejects_invalid_project_id() -> None:
    with pytest.raises(ProjectManifestValidationError) as exc_info:
        parse_project_manifest(
            {
                "schema_version": PROJECT_METADATA_SCHEMA_VERSION,
                "project_id": "bad-id",
                "name": "Bad Project Id",
            }
        )

    assert exc_info.value.field == "project_id"
    assert "project_id must be" in str(exc_info.value)


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


def test_load_project_manifest_rejects_invalid_default_argv_type() -> None:
    """default_argv must be a list of strings."""
    with pytest.raises(ProjectManifestValidationError) as exc_info:
        parse_project_manifest(
            {
                "schema_version": PROJECT_METADATA_SCHEMA_VERSION,
                "name": "Bad Argv",
                "default_argv": "not-a-list",
            }
        )

    assert exc_info.value.field == "default_argv"
    assert "must be a list" in str(exc_info.value)


def test_load_project_manifest_rejects_malformed_json_with_manifest_path(tmp_path: Path) -> None:
    """Malformed JSON should raise a validation error tied to the source path."""
    manifest_path = tmp_path / "cbcs" / "project.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text("{ this is not valid json", encoding="utf-8")

    with pytest.raises(ProjectManifestValidationError) as exc_info:
        load_project_manifest(manifest_path)

    assert exc_info.value.manifest_path == manifest_path.resolve()
    assert "Invalid JSON" in str(exc_info.value)


def test_set_project_default_entry_updates_manifest_file(tmp_path: Path) -> None:
    manifest_path = tmp_path / "cbcs" / "project.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": PROJECT_METADATA_SCHEMA_VERSION,
                "name": "Entry Test",
                "default_entry": "main.py",
            }
        ),
        encoding="utf-8",
    )

    updated = set_project_default_entry(manifest_path, default_entry="scripts/tool.py")

    assert updated.default_entry == "scripts/tool.py"
    reloaded = load_project_manifest(manifest_path)
    assert reloaded.default_entry == "scripts/tool.py"
    assert reloaded.project_id.startswith(PROJECT_ID_PREFIX)


def test_ensure_project_id_backfills_legacy_manifest(tmp_path: Path) -> None:
    manifest_path = tmp_path / "cbcs" / "project.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": PROJECT_METADATA_SCHEMA_VERSION,
                "name": "Legacy Project",
            }
        ),
        encoding="utf-8",
    )

    updated = ensure_project_id(manifest_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert updated.project_id.startswith(PROJECT_ID_PREFIX)
    assert payload["project_id"] == updated.project_id
