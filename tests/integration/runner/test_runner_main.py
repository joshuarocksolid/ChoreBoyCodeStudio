"""Integration tests for runner execution path."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core import constants
from app.run.run_manifest import RunManifest, load_run_manifest, save_run_manifest
from app.runner.runner_main import run_from_manifest_path

pytestmark = pytest.mark.integration


def _build_manifest(tmp_path: Path, script_contents: str, *, safe_mode: bool = True) -> Path:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)
    (project_root / "run.py").write_text(script_contents, encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"

    manifest = RunManifest(
        manifest_version=constants.RUN_MANIFEST_VERSION,
        run_id="20260301_010101_ab12cd",
        project_root=str(project_root.resolve()),
        entry_file="run.py",
        working_directory=str(project_root.resolve()),
        log_file=str((project_root / "logs" / "run_20260301_010101_ab12cd.log").resolve()),
        mode=constants.RUN_MODE_PYTHON_SCRIPT,
        argv=[],
        env={},
        safe_mode=safe_mode,
        timestamp="2026-03-01T01:01:01",
    )
    save_run_manifest(manifest_path, manifest)
    return manifest_path


def test_runner_executes_success_script(tmp_path: Path) -> None:
    """Successful script should exit 0."""
    manifest_path = _build_manifest(tmp_path, "print('SUCCESS_MARKER')\n")

    exit_code = run_from_manifest_path(str(manifest_path))
    manifest = load_run_manifest(manifest_path)

    assert exit_code == constants.RUN_EXIT_SUCCESS
    assert Path(manifest.log_file).exists()
    assert "SUCCESS_MARKER" in Path(manifest.log_file).read_text(encoding="utf-8")


def test_runner_captures_traceback_on_failure(tmp_path: Path) -> None:
    """Failed script should return user-code error exit code."""
    manifest_path = _build_manifest(tmp_path, "raise RuntimeError('boom')\n")

    exit_code = run_from_manifest_path(str(manifest_path))
    manifest = load_run_manifest(manifest_path)

    assert exit_code == constants.RUN_EXIT_USER_CODE_ERROR
    log_text = Path(manifest.log_file).read_text(encoding="utf-8")
    assert "RuntimeError: boom" in log_text


def test_runner_returns_invalid_manifest_code_for_missing_manifest(tmp_path: Path) -> None:
    """Missing manifest should fail with explicit invalid-manifest exit code."""
    missing_manifest = tmp_path / "missing_manifest.json"
    exit_code = run_from_manifest_path(str(missing_manifest))
    assert exit_code == constants.RUN_EXIT_INVALID_MANIFEST


def test_runner_blocks_subprocess_calls_when_safe_mode_enabled(tmp_path: Path) -> None:
    """Safe-mode runs should fail when script attempts subprocess execution."""
    script = (
        "import subprocess\n"
        "subprocess.run(['echo', 'SAFE_MODE_TEST'], check=False)\n"
    )
    manifest_path = _build_manifest(tmp_path, script, safe_mode=True)

    exit_code = run_from_manifest_path(str(manifest_path))

    assert exit_code == constants.RUN_EXIT_USER_CODE_ERROR


def test_runner_blocks_writes_outside_project_when_safe_mode_enabled(tmp_path: Path) -> None:
    """Safe-mode runs should block file writes outside project root."""
    outside_path = tmp_path / "outside.txt"
    script = f"open({str(outside_path)!r}, 'w').write('blocked')\n"
    manifest_path = _build_manifest(tmp_path, script, safe_mode=True)

    exit_code = run_from_manifest_path(str(manifest_path))

    assert exit_code == constants.RUN_EXIT_USER_CODE_ERROR
    assert not outside_path.exists()
