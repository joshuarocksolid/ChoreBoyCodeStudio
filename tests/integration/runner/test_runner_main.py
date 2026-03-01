"""Integration tests for runner execution path and log persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core import constants
from app.run.run_manifest import RunManifest, save_run_manifest
from app.runner.runner_main import run_from_manifest_path

pytestmark = pytest.mark.integration


def _build_manifest(tmp_path: Path, script_contents: str) -> tuple[Path, Path]:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)
    (project_root / "run.py").write_text(script_contents, encoding="utf-8")
    logs_dir = project_root / "logs"
    log_file = logs_dir / "run_test.log"
    manifest_path = tmp_path / "manifest.json"

    manifest = RunManifest(
        manifest_version=constants.RUN_MANIFEST_VERSION,
        run_id="20260301_010101_ab12cd",
        project_root=str(project_root.resolve()),
        entry_file="run.py",
        working_directory=str(project_root.resolve()),
        mode=constants.RUN_MODE_PYTHON_SCRIPT,
        argv=[],
        env={},
        safe_mode=True,
        log_file=str(log_file.resolve()),
        timestamp="2026-03-01T01:01:01",
    )
    save_run_manifest(manifest_path, manifest)
    return manifest_path, log_file


def test_runner_executes_success_script_and_writes_log(tmp_path: Path) -> None:
    """Successful script should exit 0 and persist output in log file."""
    manifest_path, log_file = _build_manifest(tmp_path, "print('SUCCESS_MARKER')\n")

    exit_code = run_from_manifest_path(str(manifest_path))

    assert exit_code == constants.RUN_EXIT_SUCCESS
    assert log_file.exists()
    assert "SUCCESS_MARKER" in log_file.read_text(encoding="utf-8")


def test_runner_captures_traceback_on_failure(tmp_path: Path) -> None:
    """Failed script should return user-code error and write traceback log."""
    manifest_path, log_file = _build_manifest(tmp_path, "print('BEFORE_FAIL')\nraise RuntimeError('boom')\n")

    exit_code = run_from_manifest_path(str(manifest_path))

    assert exit_code == constants.RUN_EXIT_USER_CODE_ERROR
    contents = log_file.read_text(encoding="utf-8")
    assert "BEFORE_FAIL" in contents
    assert "RuntimeError: boom" in contents
    assert "Traceback (most recent call last)" in contents


def test_runner_returns_invalid_manifest_code_for_missing_manifest(tmp_path: Path) -> None:
    """Missing manifest should fail with explicit invalid-manifest exit code."""
    missing_manifest = tmp_path / "missing_manifest.json"
    exit_code = run_from_manifest_path(str(missing_manifest))
    assert exit_code == constants.RUN_EXIT_INVALID_MANIFEST
