"""Regression tests for PY200 under default and pyflakes linters."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core import constants
from app.intelligence.diagnostics_service import analyze_python_file

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "selected_linter",
    [
        constants.LINTER_PROVIDER_DEFAULT,
        constants.LINTER_PROVIDER_PYFLAKES,
    ],
)
def test_analyze_python_file_emits_py200_for_unresolved_import_under_both_linters(
    tmp_path: Path,
    selected_linter: str,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "module.py"
    file_path.write_text("import nonexistent\n", encoding="utf-8")

    diagnostics = analyze_python_file(
        str(file_path),
        project_root=str(project_root),
        selected_linter=selected_linter,
    )

    py200 = [diagnostic for diagnostic in diagnostics if diagnostic.code == "PY200"]
    assert len(py200) == 1
    assert "nonexistent" in py200[0].message
