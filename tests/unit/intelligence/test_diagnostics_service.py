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


def test_analyze_python_file_reports_duplicate_import_statements(tmp_path: Path) -> None:
    file_path = tmp_path / "module.py"
    file_path.write_text(
        "import json\n"
        "from pathlib import Path\n"
        "import json\n"
        "from pathlib import Path\n",
        encoding="utf-8",
    )

    diagnostics = analyze_python_file(str(file_path))
    duplicate_imports = [diagnostic for diagnostic in diagnostics if diagnostic.code == "PY221"]

    assert len(duplicate_imports) == 2
    assert duplicate_imports[0].line_number == 3
    assert duplicate_imports[1].line_number == 4


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


def test_syntax_error_includes_column_info(tmp_path: Path) -> None:
    file_path = tmp_path / "broken.py"
    file_path.write_text("x = (\n", encoding="utf-8")

    diagnostics = analyze_python_file(str(file_path))

    assert len(diagnostics) == 1
    assert diagnostics[0].code == "PY100"
    assert diagnostics[0].col_start is not None


def test_unresolved_import_includes_column_range(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "module.py"
    file_path.write_text("import nonexistent\n", encoding="utf-8")

    diagnostics = analyze_python_file(str(file_path), project_root=str(project_root))

    py200 = [d for d in diagnostics if d.code == "PY200"]
    assert len(py200) == 1
    assert py200[0].col_start == 0
    assert py200[0].col_end is not None
    assert py200[0].col_end > py200[0].col_start


def test_duplicate_definition_includes_column_range(tmp_path: Path) -> None:
    file_path = tmp_path / "module.py"
    file_path.write_text(
        "def run():\n"
        "    return 1\n"
        "def run():\n"
        "    return 2\n",
        encoding="utf-8",
    )

    diagnostics = analyze_python_file(str(file_path))

    py210 = [d for d in diagnostics if d.code == "PY210"]
    assert len(py210) == 1
    assert py210[0].col_start == 0
    assert py210[0].col_end is not None


def test_unused_import_includes_column_range(tmp_path: Path) -> None:
    file_path = tmp_path / "module.py"
    file_path.write_text("import json\n", encoding="utf-8")

    diagnostics = analyze_python_file(str(file_path))

    py220 = [d for d in diagnostics if d.code == "PY220"]
    assert len(py220) == 1
    assert py220[0].col_start == 0
    assert py220[0].col_end is not None


def test_analyze_python_file_uses_source_over_disk(tmp_path: Path) -> None:
    file_path = tmp_path / "module.py"
    file_path.write_text("x = 1\n", encoding="utf-8")

    diagnostics_from_disk = analyze_python_file(str(file_path))
    assert not any(d.code == "PY100" for d in diagnostics_from_disk)

    diagnostics_from_buffer = analyze_python_file(str(file_path), source="def run(:\n    pass\n")
    assert any(d.code == "PY100" for d in diagnostics_from_buffer)


def test_unreachable_statement_includes_column_range(tmp_path: Path) -> None:
    file_path = tmp_path / "module.py"
    file_path.write_text(
        "def run():\n"
        "    return 1\n"
        "    value = 2\n",
        encoding="utf-8",
    )

    diagnostics = analyze_python_file(str(file_path))

    py230 = [d for d in diagnostics if d.code == "PY230"]
    assert len(py230) == 1
    assert py230[0].col_start is not None


def test_find_unresolved_imports_uses_source_overrides(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "module.py"
    file_path.write_text("x = 1\n", encoding="utf-8")

    diagnostics_disk = find_unresolved_imports(str(project_root))
    assert len(diagnostics_disk) == 0

    overrides = {str(file_path): "import nonexistent_module\n"}
    diagnostics_buffer = find_unresolved_imports(str(project_root), source_overrides=overrides)
    assert len(diagnostics_buffer) == 1
    assert "nonexistent_module" in diagnostics_buffer[0].message
