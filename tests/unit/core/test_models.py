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

    assert metadata.default_entry == "run.py"
    assert metadata.default_mode == "python_script"
    assert metadata.working_directory == "."
    assert metadata.template == "utility_script"
    assert metadata.safe_mode is True
    assert metadata.run_configs == []
    assert metadata.env_overrides == {}
    assert metadata.project_notes == ""
    assert metadata.import_metadata == {}


def test_project_metadata_serializes_to_stable_schema() -> None:
    """Project metadata serialization should preserve the canonical key shape."""
    metadata = ProjectMetadata(
        schema_version=1,
        name="Custom Project",
        default_entry="app/start.py",
        default_mode="qt_app",
        working_directory="app",
        template="qt_app",
        safe_mode=False,
        run_configs=[{"id": "default", "mode": "qt_app"}],
        env_overrides={"APP_ENV": "dev"},
        project_notes="Launches a Qt UI.",
    )

    assert metadata.to_dict() == {
        "schema_version": 1,
        "name": "Custom Project",
        "default_entry": "app/start.py",
        "default_mode": "qt_app",
        "working_directory": "app",
        "template": "qt_app",
        "safe_mode": False,
        "run_configs": [{"id": "default", "mode": "qt_app"}],
        "env_overrides": {"APP_ENV": "dev"},
        "project_notes": "Launches a Qt UI.",
        "import_metadata": {},
    }


def test_project_file_entry_serializes_to_stable_schema() -> None:
    """Project file entries should expose deterministic tree metadata."""
    entry = ProjectFileEntry(
        relative_path="app/main.py",
        absolute_path="/tmp/project/app/main.py",
        is_directory=False,
    )

    assert entry.to_dict() == {
        "relative_path": "app/main.py",
        "absolute_path": "/tmp/project/app/main.py",
        "is_directory": False,
    }


def test_loaded_project_serializes_to_stable_schema() -> None:
    """Loaded project payload should be stable for shell and tree wiring."""
    metadata = ProjectMetadata(schema_version=1, name="Project Alpha")
    loaded_project = LoadedProject(
        project_root="/tmp/project_alpha",
        manifest_path="/tmp/project_alpha/.cbcs/project.json",
        metadata=metadata,
        entries=[
            ProjectFileEntry(
                relative_path="run.py",
                absolute_path="/tmp/project_alpha/run.py",
                is_directory=False,
            ),
            ProjectFileEntry(
                relative_path="app",
                absolute_path="/tmp/project_alpha/app",
                is_directory=True,
            ),
        ],
    )

    assert loaded_project.to_dict() == {
        "project_root": "/tmp/project_alpha",
        "manifest_path": "/tmp/project_alpha/.cbcs/project.json",
        "metadata": {
            "schema_version": 1,
            "name": "Project Alpha",
            "default_entry": "run.py",
            "default_mode": "python_script",
            "working_directory": ".",
            "template": "utility_script",
            "safe_mode": True,
            "run_configs": [],
            "env_overrides": {},
            "project_notes": "",
            "import_metadata": {},
        },
        "entries": [
            {
                "relative_path": "run.py",
                "absolute_path": "/tmp/project_alpha/run.py",
                "is_directory": False,
            },
            {
                "relative_path": "app",
                "absolute_path": "/tmp/project_alpha/app",
                "is_directory": True,
            },
        ],
    }
