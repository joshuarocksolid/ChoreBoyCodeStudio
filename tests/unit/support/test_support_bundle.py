"""Unit tests for support-bundle build identity artifacts."""

from __future__ import annotations

from pathlib import Path
import zipfile

import pytest

from app.bootstrap.paths import global_app_log_path
from app.core import constants
from app.support.support_bundle import build_support_bundle
from tests.support.minimal_project import write_minimal_project

pytestmark = pytest.mark.unit

_FIXED_GIT_SHA = "0123456789abcdef0123456789abcdef01234567"


def _write_git_identity(repo_root: Path, sha: str) -> None:
    git_dir = repo_root / ".git"
    ref_path = git_dir / "refs" / "heads" / "main"
    ref_path.parent.mkdir(parents=True, exist_ok=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    ref_path.write_text(f"{sha}\n", encoding="utf-8")


def _write_project_with_app_log(tmp_path: Path) -> tuple[Path, Path]:
    project_root = tmp_path / "project"
    state_root = tmp_path / "state"
    write_minimal_project(project_root, name="bundle_project")
    log_path = global_app_log_path(state_root)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("app log\n", encoding="utf-8")
    return project_root, state_root


def test_support_bundle_includes_build_txt_with_git_sha(tmp_path: Path) -> None:
    project_root, state_root = _write_project_with_app_log(tmp_path)
    identity_root = tmp_path / "identity"
    _write_git_identity(identity_root, _FIXED_GIT_SHA)

    bundle_path = build_support_bundle(
        project_root,
        state_root=state_root,
        destination_dir=tmp_path / "bundles",
        identity_root=identity_root,
    )

    with zipfile.ZipFile(bundle_path, "r") as archive:
        names = set(archive.namelist())
        build_text = archive.read("build.txt").decode("utf-8")
        project_json = archive.read("project/cbcs/project.json").decode("utf-8")
        app_log = archive.read("global_logs/app.log").decode("utf-8")

    assert "build.txt" in names
    assert f"app_version={constants.APP_VERSION}" in build_text
    assert f"git_sha={_FIXED_GIT_SHA}" in build_text
    assert '"name": "bundle_project"' in project_json
    assert app_log == "app log\n"


def test_support_bundle_writes_build_txt_when_git_is_absent(tmp_path: Path) -> None:
    project_root, state_root = _write_project_with_app_log(tmp_path)

    bundle_path = build_support_bundle(
        project_root,
        state_root=state_root,
        destination_dir=tmp_path / "bundles",
        identity_root=tmp_path / "no-git",
    )

    with zipfile.ZipFile(bundle_path, "r") as archive:
        build_text = archive.read("build.txt").decode("utf-8")

    assert f"app_version={constants.APP_VERSION}" in build_text
    assert "git_sha=unknown" in build_text
