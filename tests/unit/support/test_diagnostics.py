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
    invalid_project_root = tmp_path / "invalid_project"
    invalid_project_root.mkdir()

    report = run_project_health_check(invalid_project_root, state_root=tmp_path / "state")

    structure_check = next(check for check in report.checks if check.check_id == "project_structure")
    assert structure_check.is_ok is False
    assert "Missing required metadata directory" in structure_check.message
    assert any(check.check_id.startswith("runtime.") for check in report.checks)
