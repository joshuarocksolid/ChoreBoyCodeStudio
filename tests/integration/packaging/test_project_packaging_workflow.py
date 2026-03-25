"""Integration tests for project packaging workflow artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.packaging.packager import package_project

pytestmark = pytest.mark.integration


def _make_project(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "main.py").write_text("print('hello from package')\n", encoding="utf-8")
    (path / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (path / "cbcs").mkdir(parents=True, exist_ok=True)
    (path / "cbcs" / "project.json").write_text(
        '{"schema_version":1,"name":"Integration Project","default_entry":"main.py"}\n',
        encoding="utf-8",
    )
    return path


def test_installable_project_packaging_writes_manifest_report_and_payload(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "project")

    result = package_project(
        project_root=str(project),
        project_name="Integration Project",
        entry_file="main.py",
        output_dir=str(tmp_path / "exports"),
    )

    assert result.success is True
    artifact_root = Path(result.artifact_root)
    manifest_payload = json.loads((artifact_root / "package_manifest.json").read_text(encoding="utf-8"))
    report_payload = json.loads((artifact_root / "package_report.json").read_text(encoding="utf-8"))

    assert manifest_payload["package_kind"] == "project"
    assert manifest_payload["profile"] == "installable"
    assert manifest_payload["entry_relative_path"] == "app_files/main.py"
    assert manifest_payload["launcher_filename"] == "integration_project.desktop"
    assert (artifact_root / "payload" / "app_files" / "main.py").is_file()
    assert (artifact_root / "payload" / "app_files" / "cbcs" / "package.json").is_file()
    assert (artifact_root / "installer" / "install.py").is_file()
    assert report_payload["success"] is True
    assert report_payload["validation"]["preflight"]["summary"] == "Packaging can continue, but there are warnings to review."


def test_portable_project_packaging_writes_portable_launcher_artifact(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "project")

    result = package_project(
        project_root=str(project),
        project_name="Portable Integration Project",
        entry_file="main.py",
        output_dir=str(tmp_path / "exports"),
        profile="portable",
    )

    assert result.success is True
    artifact_root = Path(result.artifact_root)
    manifest_payload = json.loads((artifact_root / "package_manifest.json").read_text(encoding="utf-8"))
    launcher_path = artifact_root / "portable_integration_project.desktop"

    assert manifest_payload["profile"] == "portable"
    assert manifest_payload["entry_relative_path"] == "app_files/main.py"
    assert launcher_path.is_file()
    assert "%k" in launcher_path.read_text(encoding="utf-8")
    assert (artifact_root / "app_files" / "main.py").is_file()
