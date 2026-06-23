"""Unit tests for manifest-driven project packaging."""

from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from app.packaging import artifact_builder
from app.packaging.packager import (
    PackageResult,
    _paths_overlap,
    package_project,
    sanitize_project_name,
)

pytestmark = pytest.mark.unit


def _make_project(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "main.py").write_text("print('hello')\n", encoding="utf-8")
    (path / "helpers.py").write_text("VALUE = 1\n", encoding="utf-8")
    (path / "cbcs").mkdir(parents=True, exist_ok=True)
    (path / "cbcs" / "project.json").write_text('{"name":"Demo"}\n', encoding="utf-8")
    return path


def test_sanitize_project_name_normalizes_expected_cases() -> None:
    assert sanitize_project_name("My Cool App") == "my_cool_app"
    assert sanitize_project_name("app@v2!#test") == "app_v2_test"
    assert sanitize_project_name("my-app_v2") == "my-app_v2"
    assert sanitize_project_name("!!!") == "project"


def test_package_project_builds_installable_artifact_by_default(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "project")

    result = package_project(
        project_root=str(project),
        project_name="My Project",
        entry_file="main.py",
        output_dir=str(tmp_path / "exports"),
    )

    assert isinstance(result, PackageResult)
    assert result.success is True
    artifact_root = Path(result.artifact_root)
    assert artifact_root.is_dir()
    assert (artifact_root / "package_manifest.json").is_file()
    assert (artifact_root / "package_report.json").is_file()
    assert (artifact_root / "README.txt").is_file()
    assert (artifact_root / "INSTALL.txt").is_file()
    assert (artifact_root / "installer" / "bootstrap.py").is_file()
    assert (artifact_root / "installer" / "install.py").is_file()
    assert (artifact_root / "installer" / "launcher_bootstrap.py").is_file()
    assert (artifact_root / "payload" / "app_files" / "main.py").is_file()
    assert (artifact_root / "payload" / "app_files" / "helpers.py").is_file()
    assert (artifact_root / "install_my_project.desktop").is_file()


def test_package_project_writes_project_package_config_on_export(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "project")

    result = package_project(
        project_root=str(project),
        project_name="My Project",
        entry_file="main.py",
        output_dir=str(tmp_path / "exports"),
    )

    assert result.success is True
    assert (project / "cbcs" / "package.json").is_file()


def test_package_project_rejects_portable_profile(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "project")

    result = package_project(
        project_root=str(project),
        project_name="Portable Tool",
        entry_file="main.py",
        output_dir=str(tmp_path / "exports"),
        profile="portable",
    )

    assert result.success is False
    assert result.error == "Unsupported package profile: portable. Use installable."
    assert any(issue.issue_id == "package.profile.unsupported" for issue in result.validation.issue_report.issues)


def test_package_project_excludes_hidden_cache_and_log_content(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "project")
    (project / "__pycache__").mkdir()
    (project / "__pycache__" / "main.pyc").write_bytes(b"\x00")
    (project / ".git").mkdir()
    (project / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    (project / "cbcs" / "logs").mkdir()
    (project / "cbcs" / "logs" / "run.log").write_text("log\n", encoding="utf-8")
    (project / "cbcs" / "runs").mkdir()
    (project / "cbcs" / "runs" / "run.json").write_text("{}\n", encoding="utf-8")

    result = package_project(
        project_root=str(project),
        project_name="My Project",
        entry_file="main.py",
        output_dir=str(tmp_path / "exports"),
    )

    payload_root = Path(result.artifact_root) / "payload" / "app_files"
    assert not (payload_root / "__pycache__").exists()
    assert not (payload_root / ".git").exists()
    assert not (payload_root / "cbcs" / "logs").exists()
    assert not (payload_root / "cbcs" / "runs").exists()


def test_package_project_fails_validation_when_entry_is_missing(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "project")

    result = package_project(
        project_root=str(project),
        project_name="My Project",
        entry_file="missing.py",
        output_dir=str(tmp_path / "exports"),
    )

    assert result.success is False
    assert result.validation.issue_report.issues
    assert any(issue.issue_id == "package.entry_invalid" for issue in result.validation.issue_report.issues)


def test_package_project_rejects_output_overlap(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "project")

    result = package_project(
        project_root=str(project),
        project_name="project",
        entry_file="main.py",
        output_dir=str(project),
    )

    assert result.success is False
    assert any(issue.issue_id == "package.output_overlaps_project" for issue in result.validation.issue_report.issues)


def test_paths_overlap_handles_same_parent_child_and_symlink(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    child = parent / "child"
    parent.mkdir()
    child.mkdir()
    link = tmp_path / "link"
    link.symlink_to(parent)

    assert _paths_overlap(parent, parent) is True
    assert _paths_overlap(parent, child) is True
    assert _paths_overlap(child, parent) is True
    assert _paths_overlap(parent, link) is True


def test_package_project_rebuild_removes_stale_files(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "project")
    extra = project / "extra.py"
    extra.write_text("print('extra')\n", encoding="utf-8")
    output_dir = tmp_path / "exports"

    first = package_project(
        project_root=str(project),
        project_name="My Project",
        entry_file="main.py",
        output_dir=str(output_dir),
    )
    assert first.success is True
    payload_root = Path(first.artifact_root) / "payload" / "app_files"
    assert (payload_root / "extra.py").is_file()

    extra.unlink()
    second = package_project(
        project_root=str(project),
        project_name="My Project",
        entry_file="main.py",
        output_dir=str(output_dir),
    )
    assert second.success is True
    payload_root = Path(second.artifact_root) / "payload" / "app_files"
    assert not (payload_root / "extra.py").exists()


def _make_installed_app_root(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "packaging").mkdir(parents=True, exist_ok=True)
    (path / "packaging" / "install.py").write_text("print('install')\n", encoding="utf-8")
    (path / "packaging" / "bootstrap.py").write_text("print('bootstrap')\n", encoding="utf-8")
    (path / "app" / "packaging").mkdir(parents=True, exist_ok=True)
    (path / "app" / "packaging" / "launcher_bootstrap.py").write_text(
        "def build_fixed_root_bootstrap(*_args, **_kwargs): return ''\n",
        encoding="utf-8",
    )
    return path


def test_package_project_succeeds_from_installed_app_root_layout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _make_project(tmp_path / "project")
    installed_root = _make_installed_app_root(tmp_path / "installed_code_studio")
    monkeypatch.setattr(artifact_builder, "resolve_app_root", lambda: installed_root)

    result = package_project(
        project_root=str(project),
        project_name="My Project",
        entry_file="main.py",
        output_dir=str(tmp_path / "exports"),
    )

    assert result.success is True
    artifact_root = Path(result.artifact_root)
    assert (artifact_root / "install_my_project.desktop").is_file()
    assert (artifact_root / "installer" / "install.py").is_file()


def test_package_project_removes_partial_artifact_when_export_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _make_project(tmp_path / "project")
    installed_root = _make_installed_app_root(tmp_path / "installed_code_studio")
    monkeypatch.setattr(artifact_builder, "resolve_app_root", lambda: installed_root)

    original_copy2 = shutil.copy2

    def _copy2_fail_on_installer(source: str | Path, destination: str | Path, **kwargs: object) -> None:
        destination_path = Path(destination)
        if destination_path.name == "install.py" and destination_path.parent.name == "installer":
            raise FileNotFoundError(f"Simulated installer copy failure: {source}")
        original_copy2(source, destination, **kwargs)

    monkeypatch.setattr(artifact_builder.shutil, "copy2", _copy2_fail_on_installer)

    output_dir = tmp_path / "exports"
    result = package_project(
        project_root=str(project),
        project_name="My Project",
        entry_file="main.py",
        output_dir=str(output_dir),
    )

    assert result.success is False
    assert result.artifact_root == ""
    assert result.error is not None
    assert "Simulated installer copy failure" in result.error
    assert not (output_dir / "my_project_installer_v0.1.0").exists()
