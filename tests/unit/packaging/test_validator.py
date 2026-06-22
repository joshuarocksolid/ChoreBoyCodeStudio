"""Unit tests for packaging validation orchestration."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.packaging.models import ProjectPackageConfig
from app.packaging.validator import build_package_validation_report

pytestmark = pytest.mark.unit


def _valid_package_config() -> ProjectPackageConfig:
    return ProjectPackageConfig(
        schema_version=1,
        package_id="demo_project",
        display_name="Demo Project",
        version="1.0.0",
        description="Demo package",
        entry_file="main.py",
        icon_path="",
    )


def test_build_package_validation_report_disables_runtime_probe_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "main.py").write_text("import json\n", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_run_dependency_audit(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        from app.packaging.models import DependencyAuditReport

        return DependencyAuditReport(
            project_root=str(project_root.resolve()),
            records=[],
            issues=[],
            summary="ok",
        )

    monkeypatch.setattr("app.packaging.validator.run_dependency_audit", fake_run_dependency_audit)

    report = build_package_validation_report(
        project_root=str(project_root),
        package_config=_valid_package_config(),
        project_name="Demo Project",
        project_default_entry="main.py",
        output_dir=str(tmp_path / "exports"),
        profile="installable",
        known_runtime_modules=frozenset({"json"}),
    )

    assert report.preflight.is_ready is True
    assert captured["allow_runtime_import_probe"] is False
    assert captured["known_runtime_modules"] == frozenset({"json"})


def test_build_package_validation_report_uses_cached_runtime_modules_when_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "main.py").write_text("import json\n", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_run_dependency_audit(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        from app.packaging.models import DependencyAuditReport

        return DependencyAuditReport(
            project_root=str(project_root.resolve()),
            records=[],
            issues=[],
            summary="ok",
        )

    monkeypatch.setattr("app.packaging.validator.run_dependency_audit", fake_run_dependency_audit)
    monkeypatch.setattr("app.packaging.validator.load_cached_runtime_modules", lambda: frozenset({"json"}))

    report = build_package_validation_report(
        project_root=str(project_root),
        package_config=_valid_package_config(),
        project_name="Demo Project",
        project_default_entry="main.py",
        output_dir=str(tmp_path / "exports"),
        profile="installable",
        known_runtime_modules=None,
    )

    assert report.preflight.is_ready is True
    assert captured["known_runtime_modules"] == frozenset({"json"})


def test_build_package_validation_report_short_circuits_dependency_audit_for_blocking_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "main.py").write_text("print('ok')\n", encoding="utf-8")
    called = {"value": False}

    def fake_run_dependency_audit(**_kwargs):  # type: ignore[no-untyped-def]
        called["value"] = True
        raise AssertionError("dependency audit should not run when preflight blocks")

    monkeypatch.setattr("app.packaging.validator.run_dependency_audit", fake_run_dependency_audit)

    blocking_config = _valid_package_config()
    report = build_package_validation_report(
        project_root=str(project_root),
        package_config=blocking_config,
        project_name="Demo Project",
        project_default_entry="main.py",
        output_dir=str(tmp_path / "exports"),
        profile="portable",
        known_runtime_modules=frozenset({"json"}),
    )

    assert called["value"] is False
    assert report.preflight.is_ready is False
    assert report.dependency_audit.records == []
    assert report.dependency_audit.summary.startswith("Dependency audit skipped")
    assert report.issue_report.issues == report.preflight.issues


def test_validate_package_config_flags_orphan_vendor_native(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    vendor_dir = project_root / "vendor"
    vendor_dir.mkdir(parents=True)
    (project_root / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (vendor_dir / "orphan.so").write_bytes(b"\x7fELF")

    report = build_package_validation_report(
        project_root=str(project_root),
        package_config=_valid_package_config(),
        project_name="Demo Project",
        project_default_entry="main.py",
        output_dir=str(tmp_path / "exports"),
        profile="installable",
        known_runtime_modules=frozenset(),
    )

    assert any(
        issue.issue_id == "package.dependency.orphan_native.orphan"
        for issue in report.issue_report.issues
    )
    assert report.is_ready is False


def test_validate_package_config_discovers_hidden_paths_via_inventory_walk(tmp_path: Path) -> None:
    from app.packaging.validator import validate_package_config

    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (project_root / ".secret").mkdir()
    (project_root / ".secret" / "data.txt").write_text("hidden\n", encoding="utf-8")

    issues = validate_package_config(
        project_root=str(project_root),
        package_config=_valid_package_config(),
        project_default_entry="main.py",
        profile="installable",
    )

    hidden_issue = next(
        issue for issue in issues if issue.issue_id == "package.project.hidden_paths_present"
    )
    assert ".secret" in hidden_issue.evidence["hidden_paths"]
    assert ".secret/data.txt" in hidden_issue.evidence["hidden_paths"]


def test_build_package_validation_report_blocks_when_manifest_vendor_missing(
    tmp_path: Path,
) -> None:
    from app.project.dependency_manifest import (
        CLASSIFICATION_PURE_PYTHON,
        DependencyEntry,
        DependencyManifest,
        SOURCE_WHEEL,
        save_dependency_manifest,
    )

    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "cbcs").mkdir()
    (project_root / "main.py").write_text("print('ok')\n", encoding="utf-8")
    manifest = DependencyManifest()
    manifest.add_entry(
        DependencyEntry(
            name="missing_pkg",
            version="1.0",
            source=SOURCE_WHEEL,
            classification=CLASSIFICATION_PURE_PYTHON,
            vendor_path="vendor/missing_pkg",
        )
    )
    save_dependency_manifest(str(project_root), manifest)

    report = build_package_validation_report(
        project_root=str(project_root),
        package_config=_valid_package_config(),
        project_name="Demo Project",
        project_default_entry="main.py",
        output_dir=str(tmp_path / "exports"),
        profile="installable",
        known_runtime_modules=frozenset(),
    )

    assert report.is_ready is False
    assert any(
        issue.issue_id == "package.dependency.manifest_missing_vendor.missing_pkg"
        for issue in report.issue_report.issues
    )


def test_build_project_package_artifact_refuses_export_when_manifest_vendor_missing(
    tmp_path: Path,
) -> None:
    from app.core.models import ProjectMetadata
    from app.packaging.artifact_builder import build_project_package_artifact
    from app.project.dependency_manifest import (
        CLASSIFICATION_PURE_PYTHON,
        DependencyEntry,
        DependencyManifest,
        SOURCE_WHEEL,
        save_dependency_manifest,
    )

    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "cbcs").mkdir()
    (project_root / "main.py").write_text("print('ok')\n", encoding="utf-8")
    manifest = DependencyManifest()
    manifest.add_entry(
        DependencyEntry(
            name="missing_pkg",
            version="1.0",
            source=SOURCE_WHEEL,
            classification=CLASSIFICATION_PURE_PYTHON,
            vendor_path="vendor/missing_pkg",
        )
    )
    save_dependency_manifest(str(project_root), manifest)

    result = build_project_package_artifact(
        project_root=str(project_root),
        project_metadata=ProjectMetadata(
            schema_version=1,
            project_id="demo",
            name="Demo Project",
            default_entry="main.py",
        ),
        package_config=_valid_package_config(),
        output_dir=str(tmp_path / "exports"),
        profile="installable",
        known_runtime_modules=frozenset(),
    )

    assert result.success is False
    assert result.validation.is_ready is False
    assert result.error == "Packaging validation failed."


def test_validate_package_config_advises_when_user_excluded_python_will_ship(
    tmp_path: Path,
) -> None:
    from app.packaging.validator import validate_package_config

    project_root = tmp_path / "project"
    (project_root / "cbcs").mkdir(parents=True)
    (project_root / "cbcs" / "project.json").write_text(
        '{"schema_version":1,"name":"Demo","exclude_patterns":["scratch"]}\n',
        encoding="utf-8",
    )
    (project_root / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (project_root / "scratch").mkdir()
    (project_root / "scratch" / "draft.py").write_text("# draft\n", encoding="utf-8")

    issues = validate_package_config(
        project_root=str(project_root),
        package_config=_valid_package_config(),
        project_default_entry="main.py",
        profile="installable",
    )

    issue = next(
        issue
        for issue in issues
        if issue.issue_id == "package.project.user_excluded_python_will_ship"
    )
    assert "scratch/draft.py" in issue.evidence["python_files"]
