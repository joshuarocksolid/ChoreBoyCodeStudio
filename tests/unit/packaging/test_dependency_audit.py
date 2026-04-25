"""Unit tests for packaging dependency audit."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.packaging.dependency_audit import run_dependency_audit

pytestmark = pytest.mark.unit


def test_dependency_audit_flags_missing_dependency(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "main.py").write_text("import missing_dep\n", encoding="utf-8")

    report = run_dependency_audit(project_root=str(project_root), known_runtime_modules=frozenset())

    assert any(record.classification == "missing" for record in report.records)
    assert any(issue.issue_id == "package.dependency.missing.missing_dep" for issue in report.issues)


def test_dependency_audit_flags_vendored_native_extension_without_loader_strategy(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    vendor_dir = project_root / "vendor"
    vendor_dir.mkdir(parents=True)
    (project_root / "main.py").write_text("import fastmath\n", encoding="utf-8")
    (vendor_dir / "fastmath.so").write_bytes(b"\x7fELF")

    report = run_dependency_audit(project_root=str(project_root), known_runtime_modules=frozenset())

    assert any(record.classification == "vendored_native" for record in report.records)
    assert any("native_extension" in issue.issue_id for issue in report.issues)


def test_dependency_audit_flags_direct_subprocess_binary(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "main.py").write_text(
        "import subprocess\nsubprocess.run(['/usr/bin/python3', 'tool.py'])\n",
        encoding="utf-8",
    )

    report = run_dependency_audit(project_root=str(project_root), known_runtime_modules=frozenset())

    assert any(issue.issue_id.startswith("package.subprocess.literal_binary") for issue in report.issues)


def test_dependency_audit_flags_shell_true_subprocess(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "main.py").write_text(
        "import subprocess\nsubprocess.run('echo unsafe', shell=True)\n",
        encoding="utf-8",
    )

    report = run_dependency_audit(project_root=str(project_root), known_runtime_modules=frozenset())

    assert any(issue.issue_id.startswith("package.subprocess.shell_true") for issue in report.issues)


def test_dependency_audit_uses_known_runtime_modules_when_provided(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "main.py").write_text("import FreeCAD\n", encoding="utf-8")

    report = run_dependency_audit(
        project_root=str(project_root),
        known_runtime_modules=frozenset({"FreeCAD"}),
        allow_runtime_import_probe=False,
    )

    assert any(record.classification == "runtime" for record in report.records)
    assert report.is_ready is True
