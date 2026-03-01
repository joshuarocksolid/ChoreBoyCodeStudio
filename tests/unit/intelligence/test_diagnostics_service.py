"""Unit tests for unresolved import diagnostics."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.intelligence.diagnostics_service import find_unresolved_imports

pytestmark = pytest.mark.unit


def test_find_unresolved_imports_flags_missing_project_modules(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "module.py").write_text("import missing.module\n", encoding="utf-8")

    diagnostics = find_unresolved_imports(str(project_root))

    assert len(diagnostics) == 1
    assert "missing.module" in diagnostics[0].message
