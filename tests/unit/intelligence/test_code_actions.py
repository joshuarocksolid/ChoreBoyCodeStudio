"""Unit tests for diagnostics quick-fix planning and apply helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.intelligence.code_actions import QuickFix, apply_quick_fixes, plan_safe_fixes_for_file
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
    assert fixes[0].expected_line_text == "import json"


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


def test_plan_safe_fixes_for_file_prefers_typo_import_replacement_when_available(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "transformer.py").write_text("VALUE = 1\n", encoding="utf-8")
    file_path = project_root / "module.py"
    file_path.write_text("import trasnformer\n", encoding="utf-8")
    diagnostics = [
        CodeDiagnostic(
            code="PY200",
            severity=DiagnosticSeverity.ERROR,
            file_path=str(file_path.resolve()),
            line_number=1,
            message="Unresolved import: trasnformer",
        )
    ]

    fixes = plan_safe_fixes_for_file(str(file_path), diagnostics, project_root=str(project_root))

    assert len(fixes) == 1
    assert fixes[0].action_kind == "replace_import_module"
    assert fixes[0].match_text == "trasnformer"
    assert fixes[0].replacement_text == "transformer"


def test_apply_quick_fixes_replaces_typo_import_module_name(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "transformer.py").write_text("VALUE = 1\n", encoding="utf-8")
    file_path = project_root / "module.py"
    file_path.write_text("import trasnformer as runtime\n", encoding="utf-8")
    diagnostics = [
        CodeDiagnostic(
            code="PY200",
            severity=DiagnosticSeverity.ERROR,
            file_path=str(file_path.resolve()),
            line_number=1,
            message="Unresolved import: trasnformer",
        )
    ]

    fixes = plan_safe_fixes_for_file(str(file_path), diagnostics, project_root=str(project_root))
    changed = apply_quick_fixes(fixes)

    assert changed == 1
    assert file_path.read_text(encoding="utf-8") == "import transformer as runtime\n"


def test_plan_safe_fixes_for_file_returns_duplicate_import_removal_fixes(tmp_path: Path) -> None:
    file_path = tmp_path / "module.py"
    file_path.write_text("import json\nimport json\n", encoding="utf-8")
    diagnostics = [
        CodeDiagnostic(
            code="PY221",
            severity=DiagnosticSeverity.WARNING,
            file_path=str(file_path.resolve()),
            line_number=2,
            message="Duplicate import statement.",
        )
    ]

    fixes = plan_safe_fixes_for_file(str(file_path), diagnostics)

    assert len(fixes) == 1
    assert fixes[0].action_kind == "remove_line"
    assert fixes[0].line_number == 2
    assert fixes[0].expected_line_text == "import json"


def test_apply_quick_fixes_skips_when_target_line_changed_since_planning(tmp_path: Path) -> None:
    file_path = tmp_path / "module.py"
    file_path.write_text("import json\nvalue = 1\n", encoding="utf-8")
    diagnostics = [
        CodeDiagnostic(
            code="PY220",
            severity=DiagnosticSeverity.WARNING,
            file_path=str(file_path.resolve()),
            line_number=1,
            message="Imported name 'json' is not used.",
        )
    ]
    fixes = plan_safe_fixes_for_file(str(file_path), diagnostics)

    file_path.write_text("import pathlib\nvalue = 1\n", encoding="utf-8")
    changed = apply_quick_fixes(fixes)

    assert changed == 0
    assert file_path.read_text(encoding="utf-8") == "import pathlib\nvalue = 1\n"


def test_apply_quick_fixes_rolls_back_file_edits_on_write_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file_a = tmp_path / "a.py"
    file_b = tmp_path / "b.py"
    original_a = "import json\nvalue = 1\n"
    original_b = "import math\nvalue = 2\n"
    file_a.write_text(original_a, encoding="utf-8")
    file_b.write_text(original_b, encoding="utf-8")
    fixes = [
        QuickFix(
            title="remove import a",
            file_path=str(file_a.resolve()),
            line_number=1,
            action_kind="remove_line",
        ),
        QuickFix(
            title="remove import b",
            file_path=str(file_b.resolve()),
            line_number=1,
            action_kind="remove_line",
        ),
    ]

    original_write_text = Path.write_text
    failure_state = {"pending": True}

    def flaky_write_text(self: Path, data: str, encoding: str = "utf-8", errors=None, newline=None) -> int:  # type: ignore[no-untyped-def]
        if self.resolve() == file_b.resolve() and failure_state["pending"]:
            failure_state["pending"] = False
            raise OSError("simulated write failure")
        return original_write_text(self, data, encoding=encoding, errors=errors, newline=newline)

    monkeypatch.setattr(Path, "write_text", flaky_write_text)

    with pytest.raises(OSError, match="simulated write failure"):
        apply_quick_fixes(fixes)

    assert file_a.read_text(encoding="utf-8") == original_a
    assert file_b.read_text(encoding="utf-8") == original_b


def test_apply_quick_fixes_rolls_back_created_module_files_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    assert fixes and fixes[0].target_path is not None

    target_module = project_root / "missing" / "module.py"
    target_init = project_root / "missing" / "__init__.py"

    original_write_text = Path.write_text
    failure_state = {"pending": True}

    def flaky_write_text(self: Path, data: str, encoding: str = "utf-8", errors=None, newline=None) -> int:  # type: ignore[no-untyped-def]
        if self.resolve() == target_module.resolve() and failure_state["pending"]:
            failure_state["pending"] = False
            raise OSError("simulated create-module failure")
        return original_write_text(self, data, encoding=encoding, errors=errors, newline=newline)

    monkeypatch.setattr(Path, "write_text", flaky_write_text)

    with pytest.raises(OSError, match="simulated create-module failure"):
        apply_quick_fixes(fixes)

    assert not target_module.exists()
    assert not target_init.exists()
