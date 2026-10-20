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


def test_dependency_audit_flags_orphan_vendor_native_without_import(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    vendor_dir = project_root / "vendor"
    vendor_dir.mkdir(parents=True)
    (project_root / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (vendor_dir / "orphan.so").write_bytes(b"\x7fELF")

    report = run_dependency_audit(project_root=str(project_root), known_runtime_modules=frozenset())

    assert any(issue.issue_id == "package.dependency.orphan_native.orphan" for issue in report.issues)
    assert report.is_ready is False


def test_dependency_audit_does_not_flag_referenced_vendor_native_as_orphan(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    vendor_dir = project_root / "vendor"
    vendor_dir.mkdir(parents=True)
    (project_root / "main.py").write_text("import fastmath\n", encoding="utf-8")
    (vendor_dir / "fastmath.so").write_bytes(b"\x7fELF")

    report = run_dependency_audit(project_root=str(project_root), known_runtime_modules=frozenset())

    assert not any(issue.issue_id.startswith("package.dependency.orphan_native") for issue in report.issues)


def test_dependency_audit_flags_direct_subprocess_binary(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "main.py").write_text(
        "import subprocess\nsubprocess.run(['/usr/bin/python3', 'tool.py'])\n",
        encoding="utf-8",
    )

    report = run_dependency_audit(project_root=str(project_root), known_runtime_modules=frozenset())

    assert any(issue.issue_id.startswith("package.subprocess.denied") for issue in report.issues)
    assert any(issue.evidence.get("freecad_version") == "1.0.0" for issue in report.issues)


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


def test_dependency_audit_classifies_same_package_relative_import(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    package_dir = project_root / "pkg"
    package_dir.mkdir(parents=True)
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "sibling.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package_dir / "mod.py").write_text("from . import sibling\n", encoding="utf-8")
    (project_root / "main.py").write_text("from pkg import mod\n", encoding="utf-8")

    report = run_dependency_audit(
        project_root=str(project_root),
        known_runtime_modules=frozenset(),
    )

    relative = [
        record
        for record in report.records
        if record.classification == "first_party_relative"
    ]
    assert relative
    assert not any(
        issue.issue_id.startswith("package.dependency.relative_missing")
        for issue in report.issues
    )


def _audit(project_root: Path, source: str, *, entry_file: str = "main.py"):
    (project_root / "main.py").write_text(source, encoding="utf-8")
    return run_dependency_audit(
        project_root=str(project_root),
        known_runtime_modules=frozenset(),
        entry_file=entry_file,
    )


def test_apprun_call_is_allowed(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    report = _audit(
        project_root,
        'import subprocess\nsubprocess.Popen(["/opt/freecad/AppRun", "app.py"])\n',
    )

    assert not any(issue.issue_id.startswith("package.subprocess") for issue in report.issues)


def test_denied_programs_cite_freecad_1_measurement(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    report = _audit(
        project_root,
        "import subprocess\n"
        'subprocess.run(["/usr/bin/pdftoppm"])\n'
        'subprocess.run(["/bin/bash"])\n'
        'subprocess.run(["/usr/bin/python3"])\n',
    )

    denied = [issue for issue in report.issues if issue.issue_id.startswith("package.subprocess.denied")]
    names = {issue.evidence["command_name"] for issue in denied}
    assert {"/usr/bin/pdftoppm", "/bin/bash", "/usr/bin/python3"} <= names
    assert all(issue.severity == "blocking" for issue in denied)
    assert all(issue.evidence["freecad_version"] == "1.0.0" for issue in denied)
    assert all(issue.evidence["tested_on"] == "2026-10-20" for issue in denied)
    assert all("FreeCAD 1.0.0" in issue.why_it_happened for issue in denied)


def test_denied_program_is_blocked_from_any_system_bin_folder(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    report = _audit(project_root, 'import subprocess\nsubprocess.Popen(["/usr/bin/pcmanfm", "."])\n')

    denied = [issue for issue in report.issues if issue.issue_id.startswith("package.subprocess.denied")]
    assert [issue.evidence["command_name"] for issue in denied] == ["/usr/bin/pcmanfm"]


def test_unknown_program_is_a_warning(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    report = _audit(project_root, 'import subprocess\nsubprocess.run(["/usr/bin/figlet"])\n')

    untested = [issue for issue in report.issues if issue.issue_id.startswith("package.subprocess.untested")]
    assert untested
    assert untested[0].severity == "degraded"


def test_shell_string_pdftoppm_is_blocked(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    report = _audit(project_root, 'import subprocess\nsubprocess.run(["/bin/sh", "-c", "pdftoppm -v"])\n')

    denied = [issue for issue in report.issues if issue.issue_id.startswith("package.subprocess.denied")]
    assert denied
    assert denied[0].evidence["command_name"] == "pdftoppm"


def test_os_system_is_blocked_like_shell_true(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    report = _audit(project_root, 'import os\nos.system("pdftoppm -v")\n')

    assert any(issue.issue_id.startswith("package.subprocess.shell_true") for issue in report.issues)
    assert any(
        issue.issue_id.startswith("package.subprocess.denied") and issue.evidence.get("command_name") == "pdftoppm"
        for issue in report.issues
    )


def test_aliased_subprocess_import_is_matched(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    report = _audit(project_root, 'import subprocess as sp\nsp.run(["/bin/bash", "-c", "true"])\n')

    assert any(issue.issue_id.startswith("package.subprocess.denied") for issue in report.issues)


def test_reachable_top_level_missing_import_blocks(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    report = _audit(project_root, "import definitely_missing_for_entry\n")

    missing = [
        issue
        for issue in report.issues
        if issue.issue_id == "package.dependency.missing.definitely_missing_for_entry"
    ]
    assert missing
    assert missing[0].severity == "blocking"
    assert missing[0].evidence["import_path"] == "main.py"


def test_guarded_missing_import_warns(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    report = _audit(
        project_root,
        "try:\n    import definitely_missing_guarded\nexcept ImportError:\n    definitely_missing_guarded = None\n",
    )

    missing = [
        issue
        for issue in report.issues
        if issue.issue_id == "package.dependency.missing.definitely_missing_guarded"
    ]
    assert missing
    assert missing[0].severity == "degraded"
    assert report.is_ready is True


def test_unreachable_missing_import_warns(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (project_root / "unused.py").write_text("import definitely_missing_unused\n", encoding="utf-8")

    report = run_dependency_audit(
        project_root=str(project_root),
        known_runtime_modules=frozenset(),
        entry_file="main.py",
    )

    missing = [
        issue
        for issue in report.issues
        if issue.issue_id == "package.dependency.missing.definitely_missing_unused"
    ]
    assert missing
    assert missing[0].severity == "degraded"
    assert missing[0].evidence["import_path"] == "not imported by any file the app loads"
