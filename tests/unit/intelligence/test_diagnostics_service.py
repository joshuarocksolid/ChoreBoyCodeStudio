"""Unit tests for unresolved import diagnostics."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.intelligence.diagnostics_service import (
    DiagnosticSeverity,
    analyze_python_file,
    find_unresolved_imports,
)

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


# ---------------------------------------------------------------------------
# known_runtime_modules integration
# ---------------------------------------------------------------------------


def test_analyze_python_file_skips_known_runtime_modules(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "run.py"
    file_path.write_text(
        "import FreeCAD\nimport os\nimport totally_fake\nFreeCAD.open('x')\nos.getcwd()\n",
        encoding="utf-8",
    )
    known = frozenset(["FreeCAD", "os", "sys"])

    diagnostics = analyze_python_file(
        str(file_path), project_root=str(project_root), known_runtime_modules=known,
    )
    py200 = [d for d in diagnostics if d.code == "PY200"]

    assert len(py200) == 1
    assert "totally_fake" in py200[0].message


def test_analyze_python_file_skips_dotted_import_when_top_level_known(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "run.py"
    file_path.write_text("from FreeCAD import Part\nPart.show()\n", encoding="utf-8")
    known = frozenset(["FreeCAD"])

    diagnostics = analyze_python_file(
        str(file_path), project_root=str(project_root), known_runtime_modules=known,
    )
    py200 = [d for d in diagnostics if d.code == "PY200"]

    assert len(py200) == 0


def test_analyze_python_file_still_flags_without_known_modules(tmp_path: Path) -> None:
    """Non-stdlib modules are still flagged when known_runtime_modules is None."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "run.py"
    file_path.write_text("import nonexistent_package\nnonexistent_package.run()\n", encoding="utf-8")

    diagnostics = analyze_python_file(
        str(file_path), project_root=str(project_root), known_runtime_modules=None,
    )
    py200 = [d for d in diagnostics if d.code == "PY200"]

    assert len(py200) == 1
    assert "nonexistent_package" in py200[0].message


def test_find_unresolved_imports_respects_known_runtime_modules(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "module.py").write_text(
        "import FreeCAD\nimport nonexistent\n", encoding="utf-8",
    )
    known = frozenset(["FreeCAD"])

    diagnostics = find_unresolved_imports(str(project_root), known_runtime_modules=known)

    assert len(diagnostics) == 1
    assert "nonexistent" in diagnostics[0].message


def test_analyze_python_file_runtime_probe_can_resolve_imports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Optional runtime probe fallback should resolve modules importable in runtime."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "run.py"
    file_path.write_text("import FreeCAD\n", encoding="utf-8")

    monkeypatch.setattr(
        "app.intelligence.diagnostics_service.is_runtime_module_importable",
        lambda module_name: module_name == "FreeCAD",
    )
    diagnostics = analyze_python_file(
        str(file_path),
        project_root=str(project_root),
        known_runtime_modules=frozenset(),
        allow_runtime_import_probe=True,
    )
    py200 = [d for d in diagnostics if d.code == "PY200"]

    assert py200 == []


def test_analyze_python_file_runtime_probe_disabled_keeps_unresolved(tmp_path: Path) -> None:
    """Runtime fallback is opt-in and should not run unless explicitly enabled."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "run.py"
    file_path.write_text("import FreeCAD\n", encoding="utf-8")

    diagnostics = analyze_python_file(
        str(file_path),
        project_root=str(project_root),
        known_runtime_modules=frozenset(),
        allow_runtime_import_probe=False,
    )
    py200 = [d for d in diagnostics if d.code == "PY200"]

    assert len(py200) == 1
    assert "FreeCAD" in py200[0].message


# ---------------------------------------------------------------------------
# vendor/ directory import resolution
# ---------------------------------------------------------------------------


def test_analyze_resolves_import_from_vendor_module(tmp_path: Path) -> None:
    """A .py module under vendor/ should be treated as resolvable."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    vendor_dir = project_root / "vendor"
    vendor_dir.mkdir()
    (vendor_dir / "vendored_lib.py").write_text("x = 1\n", encoding="utf-8")
    file_path = project_root / "main.py"
    file_path.write_text("import vendored_lib\nvendored_lib.x\n", encoding="utf-8")

    diagnostics = analyze_python_file(
        str(file_path), project_root=str(project_root), known_runtime_modules=frozenset(),
    )
    py200 = [d for d in diagnostics if d.code == "PY200"]

    assert len(py200) == 0


def test_analyze_resolves_import_from_vendor_package(tmp_path: Path) -> None:
    """A package under vendor/ should be treated as resolvable."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    vendor_pkg = project_root / "vendor" / "mypkg"
    vendor_pkg.mkdir(parents=True)
    (vendor_pkg / "__init__.py").write_text("", encoding="utf-8")
    file_path = project_root / "main.py"
    file_path.write_text("import mypkg\nmypkg\n", encoding="utf-8")

    diagnostics = analyze_python_file(
        str(file_path), project_root=str(project_root), known_runtime_modules=frozenset(),
    )
    py200 = [d for d in diagnostics if d.code == "PY200"]

    assert len(py200) == 0


def test_find_unresolved_imports_resolves_vendor_module(tmp_path: Path) -> None:
    """find_unresolved_imports should also respect vendor/ modules."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    vendor_dir = project_root / "vendor"
    vendor_dir.mkdir()
    (vendor_dir / "vendored_lib.py").write_text("x = 1\n", encoding="utf-8")
    (project_root / "main.py").write_text("import vendored_lib\nvendored_lib.x\n", encoding="utf-8")

    diagnostics = find_unresolved_imports(str(project_root), known_runtime_modules=frozenset())

    assert len(diagnostics) == 0


# ---------------------------------------------------------------------------
# stdlib fallback (defensive, when probe has not completed)
# ---------------------------------------------------------------------------


def test_analyze_does_not_flag_stdlib_when_known_modules_is_none(tmp_path: Path) -> None:
    """stdlib modules like os, sys must not be flagged even when known_runtime_modules is None."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "main.py"
    file_path.write_text(
        "import os\nimport sys\nimport json\nimport traceback\n"
        "from datetime import datetime\nfrom pathlib import Path\n"
        "os.getcwd()\nsys.exit()\njson.dumps({})\ntraceback.format_exc()\n"
        "datetime.now()\nPath('.')\n",
        encoding="utf-8",
    )

    diagnostics = analyze_python_file(
        str(file_path), project_root=str(project_root), known_runtime_modules=None,
    )
    py200 = [d for d in diagnostics if d.code == "PY200"]

    assert len(py200) == 0


def test_analyze_does_not_flag_stdlib_when_known_modules_is_empty(tmp_path: Path) -> None:
    """stdlib modules must not be flagged even when known_runtime_modules is an empty set."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "main.py"
    file_path.write_text("import os\nimport sys\nos.getcwd()\nsys.exit()\n", encoding="utf-8")

    diagnostics = analyze_python_file(
        str(file_path), project_root=str(project_root), known_runtime_modules=frozenset(),
    )
    py200 = [d for d in diagnostics if d.code == "PY200"]

    assert len(py200) == 0


def test_analyze_still_flags_unknown_module_with_stdlib_fallback(tmp_path: Path) -> None:
    """Non-stdlib modules should still be flagged even with fallback active."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "main.py"
    file_path.write_text("import os\nimport totally_fake\nos.getcwd()\ntotally_fake.run()\n", encoding="utf-8")

    diagnostics = analyze_python_file(
        str(file_path), project_root=str(project_root), known_runtime_modules=None,
    )
    py200 = [d for d in diagnostics if d.code == "PY200"]

    assert len(py200) == 1
    assert "totally_fake" in py200[0].message


def test_analyze_flags_tomllib_when_runtime_modules_are_unavailable(tmp_path: Path) -> None:
    """Fallback should reflect Python 3.9 target runtime and flag tomllib."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "main.py"
    file_path.write_text("import tomllib\n", encoding="utf-8")

    diagnostics = analyze_python_file(
        str(file_path),
        project_root=str(project_root),
        known_runtime_modules=None,
        allow_runtime_import_probe=False,
    )
    py200 = [d for d in diagnostics if d.code == "PY200"]

    assert len(py200) == 1
    assert "tomllib" in py200[0].message


def test_analyze_accepts_tomllib_when_runtime_probe_provides_module_set(tmp_path: Path) -> None:
    """Known runtime module list should remain authoritative when provided."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "main.py"
    file_path.write_text("import tomllib\n", encoding="utf-8")

    diagnostics = analyze_python_file(
        str(file_path),
        project_root=str(project_root),
        known_runtime_modules=frozenset({"tomllib"}),
        allow_runtime_import_probe=False,
    )
    py200 = [d for d in diagnostics if d.code == "PY200"]

    assert py200 == []


def test_analyze_python_file_applies_lint_override_disable(tmp_path: Path) -> None:
    file_path = tmp_path / "module.py"
    file_path.write_text("import json\n", encoding="utf-8")

    diagnostics = analyze_python_file(
        str(file_path),
        lint_rule_overrides={"PY220": {"enabled": False}},
    )
    assert all(d.code != "PY220" for d in diagnostics)


def test_analyze_python_file_applies_lint_override_severity(tmp_path: Path) -> None:
    file_path = tmp_path / "module.py"
    file_path.write_text(
        "def run():\n"
        "    return 1\n"
        "    value = 2\n",
        encoding="utf-8",
    )

    diagnostics = analyze_python_file(
        str(file_path),
        lint_rule_overrides={"PY230": {"severity": "warning"}},
    )
    py230 = [d for d in diagnostics if d.code == "PY230"]
    assert len(py230) == 1
    assert py230[0].severity == DiagnosticSeverity.WARNING


def test_unresolved_import_respects_lint_profile_disable(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "run.py"
    file_path.write_text("import nonexistent_package\n", encoding="utf-8")

    diagnostics = analyze_python_file(
        str(file_path),
        project_root=str(project_root),
        lint_rule_overrides={"PY200": {"enabled": False}},
    )
    assert all(d.code != "PY200" for d in diagnostics)
