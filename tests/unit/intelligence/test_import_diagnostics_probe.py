"""Regression tests for static-only import diagnostics (CC-14)."""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

from app.intelligence.diagnostics_service import analyze_python_file
from app.intelligence.import_diagnostics import collect_unresolved_import_diagnostics

pytestmark = pytest.mark.unit


def test_collect_unresolved_import_diagnostics_default_path_never_probes_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "module.py"
    file_path.write_text("import definitely_not_a_project_module\n", encoding="utf-8")
    syntax_tree = ast.parse(file_path.read_text(encoding="utf-8"))

    def fail_subprocess(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise AssertionError("subprocess.run must not run on default import diagnostics path")

    def fail_runtime_probe(_module_name: str) -> bool:
        raise AssertionError("runtime import probe must not run on default import diagnostics path")

    monkeypatch.setattr("app.intelligence.runtime_import_probe.subprocess.run", fail_subprocess)
    monkeypatch.setattr(
        "app.project.dependency_classifier.is_runtime_module_importable",
        fail_runtime_probe,
    )

    diagnostics = collect_unresolved_import_diagnostics(
        project_root,
        file_path,
        syntax_tree,
    )

    assert len(diagnostics) == 1
    assert diagnostics[0].code == "PY200"
    assert "definitely_not_a_project_module" in diagnostics[0].message


def test_analyze_python_file_default_path_never_probes_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "module.py"
    file_path.write_text("import definitely_not_a_project_module\n", encoding="utf-8")

    def fail_subprocess(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise AssertionError("subprocess.run must not run on default analyze_python_file path")

    def fail_runtime_probe(_module_name: str) -> bool:
        raise AssertionError("runtime import probe must not run on default analyze_python_file path")

    monkeypatch.setattr("app.intelligence.runtime_import_probe.subprocess.run", fail_subprocess)
    monkeypatch.setattr(
        "app.project.dependency_classifier.is_runtime_module_importable",
        fail_runtime_probe,
    )

    diagnostics = analyze_python_file(str(file_path), project_root=str(project_root))

    py200 = [diagnostic for diagnostic in diagnostics if diagnostic.code == "PY200"]
    assert len(py200) == 1
    assert "definitely_not_a_project_module" in py200[0].message
