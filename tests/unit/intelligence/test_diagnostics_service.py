"""Unit tests for unresolved import diagnostics."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.intelligence.diagnostics_service import analyze_python_file, find_unresolved_imports

pytestmark = pytest.mark.unit


def test_find_unresolved_imports_flags_missing_project_modules(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "module.py").write_text("import missing.module\n", encoding="utf-8")

    diagnostics = find_unresolved_imports(str(project_root))

    assert len(diagnostics) == 1
    assert "missing.module" in diagnostics[0].message


def test_analyze_python_file_reports_syntax_error(tmp_path: Path) -> None:
    file_path = tmp_path / "broken.py"
    file_path.write_text("def run(:\n    pass\n", encoding="utf-8")

    diagnostics = analyze_python_file(str(file_path))

    assert len(diagnostics) == 1
    assert diagnostics[0].code == "PY100"
    assert "Syntax error" in diagnostics[0].message


def test_analyze_python_file_reports_duplicate_and_unused_import(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "module.py"
    file_path.write_text(
        "import json\n"
        "def run():\n"
        "    return 1\n"
        "def run():\n"
        "    return 2\n",
        encoding="utf-8",
    )

    diagnostics = analyze_python_file(str(file_path), project_root=str(project_root))
    codes = {diagnostic.code for diagnostic in diagnostics}

    assert "PY210" in codes
    assert "PY220" in codes


def test_analyze_python_file_reports_unreachable_statement(tmp_path: Path) -> None:
    file_path = tmp_path / "module.py"
    file_path.write_text(
        "def run():\n"
        "    return 1\n"
        "    value = 2\n",
        encoding="utf-8",
    )

    diagnostics = analyze_python_file(str(file_path))

    assert any(diagnostic.code == "PY230" for diagnostic in diagnostics)
