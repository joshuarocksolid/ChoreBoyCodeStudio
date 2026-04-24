"""Unit tests for shared core models."""

from app.core.models import (
    CapabilityCheckResult,
    CapabilityProbeReport,
    LoadedProject,
    ProjectFileEntry,
    ProjectMetadata,
)

import pytest

pytestmark = pytest.mark.unit


def test_capability_check_result_serializes_to_stable_schema() -> None:
    """Check model serialization should keep a predictable shape."""
    check = CapabilityCheckResult(
        check_id="pyside2_import",
        is_available=True,
        message="PySide2 import succeeded.",
        details={"module": "PySide2"},
    )

    assert check.to_dict() == {
        "check_id": "pyside2_import",
        "is_available": True,
        "message": "PySide2 import succeeded.",
        "details": {"module": "PySide2"},
    }


def test_capability_probe_report_preserves_check_order() -> None:
    """Report should preserve check order for deterministic UI rendering."""
    checks = [
        CapabilityCheckResult("apprun_path", True, "found"),
        CapabilityCheckResult("freecad_import", False, "missing"),
    ]
    report = CapabilityProbeReport(checks=checks)

    payload = report.to_dict()
    assert [item["check_id"] for item in payload["checks"]] == [
        "apprun_path",
        "freecad_import",
    ]


def test_capability_probe_report_exposes_aggregate_fields() -> None:
    """Report should expose aggregate availability fields."""
    report = CapabilityProbeReport(
        checks=[
            CapabilityCheckResult("apprun_path", True, "found"),
            CapabilityCheckResult("pyside2_import", False, "missing"),
            CapabilityCheckResult("freecad_import", False, "missing"),
        ]
    )

    payload = report.to_dict()
    assert payload["all_available"] is False
    assert payload["available_count"] == 1
    assert payload["total_count"] == 3
    assert payload["failed_check_ids"] == ["pyside2_import", "freecad_import"]


def test_project_metadata_defaults_are_explicit_and_stable() -> None:
    """Project metadata should expose explicit defaults for omitted optional fields."""
    metadata = ProjectMetadata(schema_version=1, name="My Project")

    assert metadata.project_id == "proj_legacy_unknown"
    assert metadata.default_entry == "main.py"
    assert metadata.default_argv == []
    assert metadata.working_directory == "."
    assert metadata.template == "utility_script"
    assert metadata.run_configs == []
    assert metadata.env_overrides == {}
    assert metadata.project_notes == ""


def test_project_metadata_to_dict_uses_canonical_external_keys() -> None:
    """`project.json` is read by other tools; field names are an external contract."""
    metadata = ProjectMetadata(
        schema_version=1,
        name="Custom Project",
        project_id="proj_custom123",
        default_entry="app/start.py",
        working_directory="app",
    )
    payload = metadata.to_dict()

    assert set(payload.keys()) == {
        "schema_version",
        "project_id",
        "name",
        "default_entry",
        "default_argv",
        "working_directory",
        "template",
        "run_configs",
        "env_overrides",
        "project_notes",
    }
    assert payload["name"] == "Custom Project"
    assert payload["default_entry"] == "app/start.py"


def test_project_file_entry_to_dict_uses_canonical_external_keys() -> None:
    entry = ProjectFileEntry(
        relative_path="app/main.py",
        absolute_path="/tmp/project/app/main.py",
        is_directory=False,
    )

    payload = entry.to_dict()
    assert set(payload.keys()) == {"relative_path", "absolute_path", "is_directory"}
    assert payload["is_directory"] is False


def test_loaded_project_to_dict_nests_metadata_and_entries() -> None:
    """Verify the nested-payload contract without re-pinning every dataclass field."""
    metadata = ProjectMetadata(schema_version=1, name="Project Alpha", project_id="proj_alpha")
    loaded_project = LoadedProject(
        project_root="/tmp/project_alpha",
        manifest_path="/tmp/project_alpha/cbcs/project.json",
        metadata=metadata,
        entries=[
            ProjectFileEntry(
                relative_path="run.py",
                absolute_path="/tmp/project_alpha/run.py",
                is_directory=False,
            ),
        ],
        manifest_materialized=True,
    )

    payload = loaded_project.to_dict()
    assert set(payload.keys()) == {
        "project_root",
        "manifest_path",
        "manifest_materialized",
        "metadata",
        "entries",
    }
    assert payload["metadata"] == metadata.to_dict()
    assert payload["entries"] == [loaded_project.entries[0].to_dict()]
