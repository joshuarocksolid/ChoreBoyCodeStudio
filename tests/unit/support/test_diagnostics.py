"""Unit tests for project/runtime diagnostics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.support.diagnostics import run_project_health_check

pytestmark = pytest.mark.unit


def _write_valid_project(project_root: Path) -> None:
    (project_root / "cbcs").mkdir(parents=True, exist_ok=True)
    (project_root / "run.py").write_text("print('ok')\n", encoding="utf-8")
    (project_root / "cbcs" / "project.json").write_text(
        json.dumps({"schema_version": 1, "name": "diag_project"}, indent=2),
        encoding="utf-8",
    )


def test_run_project_health_check_reports_valid_project_structure(tmp_path: Path) -> None:
    """Valid projects should pass structure and manifest checks."""
    project_root = tmp_path / "project"
    _write_valid_project(project_root)

    report = run_project_health_check(project_root, state_root=tmp_path / "state")
    check_ids = [check.check_id for check in report.checks]

    assert report.project_root == str(project_root.resolve())
    assert "project_structure" in check_ids
    assert "project_manifest" in check_ids
    assert any(check.check_id.startswith("runtime.") for check in report.checks)


def test_run_project_health_check_reports_invalid_project_structure(tmp_path: Path) -> None:
    """Invalid project roots should fail structure checks with diagnostics."""
    missing_project_root = tmp_path / "missing_project"

    report = run_project_health_check(missing_project_root, state_root=tmp_path / "state")

    structure_check = next(check for check in report.checks if check.check_id == "project_structure")
    assert structure_check.is_ok is False
    assert "Project folder not found" in structure_check.message
    assert any(check.check_id.startswith("runtime.") for check in report.checks)


def test_run_project_health_check_flags_importable_python_folder_state(tmp_path: Path) -> None:
    project_root = tmp_path / "importable_project"
    project_root.mkdir()
    (project_root / "run.py").write_text("print('ok')\n", encoding="utf-8")

    report = run_project_health_check(project_root, state_root=tmp_path / "state")

    structure_check = next(check for check in report.checks if check.check_id == "project_structure")
    manifest_check = next(check for check in report.checks if check.check_id == "project_manifest")
    assert structure_check.is_ok is True
    assert structure_check.details["state"] == "importable_python_folder"
    assert structure_check.details["inferred_entry"] == "run.py"
    assert manifest_check.is_ok is True
    assert manifest_check.details["manifest_materialized"] is False
    assert "in-memory" in manifest_check.message
