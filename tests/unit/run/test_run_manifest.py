"""Unit tests for run manifest contract helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core import constants
from app.core.errors import RunManifestValidationError
from app.run.run_manifest import RunManifest, load_run_manifest, parse_run_manifest, save_run_manifest

pytestmark = pytest.mark.unit


def test_run_manifest_round_trip_save_and_load(tmp_path: Path) -> None:
    """Manifest save/load should preserve deterministic payload shape."""
    manifest = RunManifest(
        manifest_version=constants.RUN_MANIFEST_VERSION,
        run_id="20260301_010101_ab12cd",
        project_root=str((tmp_path / "project").resolve()),
        entry_file="run.py",
        working_directory=str((tmp_path / "project").resolve()),
        log_file=str((tmp_path / "project" / "logs" / "run_20260301_010101_ab12cd.log").resolve()),
        mode=constants.RUN_MODE_PYTHON_SCRIPT,
        argv=["--foo", "bar"],
        env={"ENV_A": "1"},
        safe_mode=True,
        timestamp="2026-03-01T01:01:01",
        breakpoints=[{"file_path": str((tmp_path / "project" / "run.py").resolve()), "line_number": 3}],
    )
    manifest_path = tmp_path / "manifest.json"
    save_run_manifest(manifest_path, manifest)

    loaded = load_run_manifest(manifest_path)
    assert loaded == manifest


def test_parse_run_manifest_rejects_invalid_mode() -> None:
    """Unsupported run modes should fail with actionable validation details."""
    with pytest.raises(RunManifestValidationError, match="Unsupported mode"):
        parse_run_manifest(
            {
                "manifest_version": constants.RUN_MANIFEST_VERSION,
                "run_id": "run_1",
                "project_root": "/tmp/project",
                "entry_file": "run.py",
                "working_directory": "/tmp/project",
                "log_file": "/tmp/project/logs/run_1.log",
                "mode": "unknown",
                "argv": [],
                "env": {},
                "safe_mode": True,
                "timestamp": "2026-03-01T01:01:01",
            }
        )


def test_parse_run_manifest_requires_absolute_paths() -> None:
    """Path fields must remain absolute to avoid cwd-coupled behavior."""
    with pytest.raises(RunManifestValidationError, match="project_root must be an absolute path"):
        parse_run_manifest(
            {
                "manifest_version": constants.RUN_MANIFEST_VERSION,
                "run_id": "run_1",
                "project_root": "relative/project",
                "entry_file": "run.py",
                "working_directory": "/tmp/project",
                "log_file": "/tmp/project/logs/run_1.log",
                "mode": constants.RUN_MODE_PYTHON_SCRIPT,
                "argv": [],
                "env": {},
                "safe_mode": True,
                "timestamp": "2026-03-01T01:01:01",
            }
        )


def test_parse_run_manifest_validates_breakpoint_shape() -> None:
    """Breakpoint payloads must contain file path and positive line number."""
    with pytest.raises(RunManifestValidationError, match="line_number must be a positive integer"):
        parse_run_manifest(
            {
                "manifest_version": constants.RUN_MANIFEST_VERSION,
                "run_id": "run_1",
                "project_root": "/tmp/project",
                "entry_file": "run.py",
                "working_directory": "/tmp/project",
                "log_file": "/tmp/project/logs/run_1.log",
                "mode": constants.RUN_MODE_PYTHON_DEBUG,
                "argv": [],
                "env": {},
                "safe_mode": True,
                "timestamp": "2026-03-01T01:01:01",
                "breakpoints": [{"file_path": "/tmp/project/run.py", "line_number": 0}],
            }
        )
