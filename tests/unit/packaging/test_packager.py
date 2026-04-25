"""Unit tests for manifest-driven project packaging."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core import constants
from app.packaging.desktop_builder import build_portable_launcher
from app.packaging.installer_manifest import create_distribution_manifest
from app.packaging.models import (
    LAUNCHER_MODE_PORTABLE_DESKTOP_ARGUMENT,
    PACKAGE_KIND_PROJECT,
    PACKAGE_PROFILE_PORTABLE,
)
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


def _build_portable_desktop_entry(project_name: str, entry_file: str, install_dir: str) -> str:
    manifest = create_distribution_manifest(
        package_kind=PACKAGE_KIND_PROJECT,
        profile=PACKAGE_PROFILE_PORTABLE,
        package_id=sanitize_project_name(project_name),
        display_name=project_name,
        version="0.1.0",
        description="",
        entry_relative_path=Path(install_dir, entry_file).as_posix(),
        launcher_mode=LAUNCHER_MODE_PORTABLE_DESKTOP_ARGUMENT,
        app_run_path=constants.APP_RUN_PATH,
    )
    return build_portable_launcher(manifest)


def test_sanitize_project_name_normalizes_expected_cases() -> None:
    assert sanitize_project_name("My Cool App") == "my_cool_app"
    assert sanitize_project_name("app@v2!#test") == "app_v2_test"
    assert sanitize_project_name("my-app_v2") == "my-app_v2"
    assert sanitize_project_name("!!!") == "project"


def test_portable_launcher_uses_direct_apprun_with_percent_k_argument() -> None:
    content = _build_portable_desktop_entry("Cool Tool", "main.py", "app_files")

    assert "[Desktop Entry]" in content
    assert "Name=Cool Tool" in content
    assert "/opt/freecad/AppRun" in content
    assert "%k" in content
    assert '" dummy %k' in content
    assert "/bin/sh -c" in content
    assert 'entry=os.path.abspath(os.path.join(root, \\"app_files/main.py\\"))' in content


def test_portable_launcher_rejects_unsafe_entry_relative_path() -> None:
    with pytest.raises(ValueError, match="entry_relative_path"):
        _build_portable_desktop_entry("Unsafe Tool", "../main.py", "app_files")


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
    assert (artifact_root / "installer" / "install.py").is_file()
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


def test_package_project_portable_profile_uses_root_launcher_and_app_files(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "project")

    result = package_project(
        project_root=str(project),
        project_name="Portable Tool",
        entry_file="main.py",
        output_dir=str(tmp_path / "exports"),
        profile="portable",
    )

    assert result.success is True
    artifact_root = Path(result.artifact_root)
    launcher_path = artifact_root / "portable_tool.desktop"
    assert launcher_path.is_file()
    assert (artifact_root / "app_files" / "main.py").is_file()
    content = launcher_path.read_text(encoding="utf-8")
    assert "%k" in content
    assert "payload/" not in content


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
