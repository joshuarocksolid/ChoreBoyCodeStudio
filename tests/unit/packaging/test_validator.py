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

    blocking_config = ProjectPackageConfig(
        schema_version=1,
        package_id="bad package id",
        display_name="",
        version="bad-version",
        description="",
        entry_file="main.py",
        icon_path="",
    )
    report = build_package_validation_report(
        project_root=str(project_root),
        package_config=blocking_config,
        project_name="Demo Project",
        project_default_entry="main.py",
        output_dir=str(tmp_path / "exports"),
        profile="installable",
        known_runtime_modules=frozenset({"json"}),
    )

    assert called["value"] is False
    assert report.preflight.is_ready is False
    assert report.dependency_audit.records == []
    assert report.dependency_audit.summary.startswith("Dependency audit skipped")
    assert report.issue_report.issues == report.preflight.issues
