"""Unit tests for import resolver helper."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.intelligence.import_resolver import resolve_project_import

pytestmark = pytest.mark.unit


def test_resolve_project_import_handles_module_and_package(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "pkg").mkdir()
    (project_root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (project_root / "pkg" / "module.py").write_text("x=1\n", encoding="utf-8")

    module = resolve_project_import(str(project_root), "pkg.module")
    package = resolve_project_import(str(project_root), "pkg")
    missing = resolve_project_import(str(project_root), "missing.module")

    assert module.is_resolved is True
    assert module.resolved_path is not None and module.resolved_path.endswith("module.py")
    assert package.is_resolved is True
    assert package.resolved_path is not None and package.resolved_path.endswith("__init__.py")
    assert missing.is_resolved is False
