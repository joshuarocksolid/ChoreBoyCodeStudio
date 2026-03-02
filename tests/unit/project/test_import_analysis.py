"""Unit tests for imported-project analysis helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.project.import_analysis import analyze_imported_project

pytestmark = pytest.mark.unit


def test_analyze_imported_project_detects_signals_and_runtime_warnings(tmp_path: Path) -> None:
    project_root = tmp_path / "imported_project"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (project_root / "requirements.txt").write_text("requests\n", encoding="utf-8")
    (project_root / "src").mkdir()
    (project_root / "run.py").write_text(
        "import subprocess\nfrom PySide6 import QtWidgets\n",
        encoding="utf-8",
    )

    analysis = analyze_imported_project(project_root, "run.py")
    payload = analysis.to_metadata_payload()

    assert payload["source_type"] == "imported_external"
    assert payload["inferred_entry"] == "run.py"
    assert payload["onboarding_completed"] is False
    assert "pyproject.toml" in payload["detected_signals"]
    assert "requirements_file" in payload["detected_signals"]
    assert "src_layout" in payload["detected_signals"]
    warnings = payload["runtime_warnings"]
    assert isinstance(warnings, list)
    assert any("external dependencies" in warning for warning in warnings)
    assert any("safe mode" in warning for warning in warnings)


def test_analyze_imported_project_handles_signal_free_project(tmp_path: Path) -> None:
    project_root = tmp_path / "simple_project"
    project_root.mkdir()
    (project_root / "run.py").write_text("print('ok')\n", encoding="utf-8")

    analysis = analyze_imported_project(project_root, "run.py")
    payload = analysis.to_metadata_payload()

    assert payload["detected_signals"] == []
    assert payload["runtime_warnings"] == []
