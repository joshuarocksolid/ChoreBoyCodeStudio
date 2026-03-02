"""Unit tests for diagnostics quick-fix planning and apply helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.intelligence.code_actions import apply_quick_fixes, plan_safe_fixes_for_file
from app.intelligence.diagnostics_service import CodeDiagnostic, DiagnosticSeverity

pytestmark = pytest.mark.unit


def test_plan_safe_fixes_for_file_returns_unused_import_removal_fixes(tmp_path: Path) -> None:
    file_path = tmp_path / "module.py"
    file_path.write_text("import json\nprint('ok')\n", encoding="utf-8")
    diagnostics = [
        CodeDiagnostic(
            code="PY220",
            severity=DiagnosticSeverity.WARNING,
            file_path=str(file_path.resolve()),
            line_number=1,
            message="Imported name 'json' is not used.",
        ),
        CodeDiagnostic(
            code="PY210",
            severity=DiagnosticSeverity.WARNING,
            file_path=str(file_path.resolve()),
            line_number=2,
            message="Duplicate definition.",
        ),
    ]

    fixes = plan_safe_fixes_for_file(str(file_path), diagnostics)

    assert len(fixes) == 1
    assert fixes[0].action_kind == "remove_line"
    assert fixes[0].line_number == 1


def test_apply_quick_fixes_removes_import_lines(tmp_path: Path) -> None:
    file_path = tmp_path / "module.py"
    file_path.write_text("import json\nfrom math import sin\nvalue = 1\n", encoding="utf-8")
    diagnostics = [
        CodeDiagnostic(
            code="PY220",
            severity=DiagnosticSeverity.WARNING,
            file_path=str(file_path.resolve()),
            line_number=1,
            message="Imported name 'json' is not used.",
        ),
        CodeDiagnostic(
            code="PY220",
            severity=DiagnosticSeverity.WARNING,
            file_path=str(file_path.resolve()),
            line_number=2,
            message="Imported name 'sin' is not used.",
        ),
    ]
    fixes = plan_safe_fixes_for_file(str(file_path), diagnostics)

    changed_lines = apply_quick_fixes(fixes)

    assert changed_lines == 2
    updated = file_path.read_text(encoding="utf-8")
    assert "import json" not in updated
    assert "from math import sin" not in updated
    assert "value = 1" in updated


def test_plan_safe_fixes_for_file_includes_create_module_fix_for_unresolved_import(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "module.py"
    file_path.write_text("import missing.module\n", encoding="utf-8")
    diagnostics = [
        CodeDiagnostic(
            code="PY200",
            severity=DiagnosticSeverity.ERROR,
            file_path=str(file_path.resolve()),
            line_number=1,
            message="Unresolved import: missing.module",
        )
    ]

    fixes = plan_safe_fixes_for_file(str(file_path), diagnostics, project_root=str(project_root))

    assert len(fixes) == 1
    assert fixes[0].action_kind == "create_module_file"
    assert fixes[0].target_path is not None
    assert fixes[0].target_path.endswith("missing/module.py")


def test_apply_quick_fixes_creates_missing_module_and_package_init(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "module.py"
    file_path.write_text("import missing.module\n", encoding="utf-8")
    diagnostics = [
        CodeDiagnostic(
            code="PY200",
            severity=DiagnosticSeverity.ERROR,
            file_path=str(file_path.resolve()),
            line_number=1,
            message="Unresolved import: missing.module",
        )
    ]
    fixes = plan_safe_fixes_for_file(str(file_path), diagnostics, project_root=str(project_root))

    changed = apply_quick_fixes(fixes)

    assert changed == 1
    assert (project_root / "missing" / "module.py").exists()
    assert (project_root / "missing" / "__init__.py").exists()
