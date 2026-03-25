"""Integration tests for support bundle artifact generation."""

from __future__ import annotations

import json
from pathlib import Path
import zipfile

import pytest

from app.bootstrap.logging_setup import configure_app_logging
from app.persistence.local_history_store import LocalHistoryStore
from app.persistence.settings_service import SettingsService
from app.project.project_manifest import load_project_manifest
from app.support.diagnostics import run_project_health_check
from app.support.support_bundle import build_support_bundle

pytestmark = pytest.mark.integration


def _write_valid_project(project_root: Path) -> None:
    (project_root / "cbcs").mkdir(parents=True, exist_ok=True)
    (project_root / "run.py").write_text("print('ok')\n", encoding="utf-8")
    (project_root / "cbcs" / "project.json").write_text(
        json.dumps({"schema_version": 1, "name": "bundle_project"}, indent=2),
        encoding="utf-8",
    )


def test_build_support_bundle_includes_expected_artifacts(tmp_path: Path) -> None:
    """Support bundle zip should contain manifest, app log, and diagnostics."""
    project_root = tmp_path / "project"
    state_root = tmp_path / "state"
    _write_valid_project(project_root)

    app_log_path = configure_app_logging(state_root=state_root).log_path
    app_log_path.write_text("app log\n", encoding="utf-8")
    health_report = run_project_health_check(project_root, state_root=state_root)

    bundle_path = build_support_bundle(
        project_root,
        diagnostics_report=health_report,
        state_root=state_root,
        destination_dir=tmp_path / "bundles",
    )

    assert bundle_path.exists()
    with zipfile.ZipFile(bundle_path, "r") as archive:
        names = set(archive.namelist())
        assert "project/cbcs/project.json" in names
        assert "global_logs/app.log" in names
        assert "diagnostics/project_health.json" in names


def test_build_support_bundle_includes_run_log_when_provided(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    state_root = tmp_path / "state"
    _write_valid_project(project_root)

    app_log_path = configure_app_logging(state_root=state_root).log_path
    app_log_path.write_text("app log\n", encoding="utf-8")
    run_log_path = project_root / "cbcs" / "logs" / "run_20260302_120000.log"
    run_log_path.parent.mkdir(parents=True, exist_ok=True)
    run_log_path.write_text("stdout line\nstderr line\n", encoding="utf-8")

    bundle_path = build_support_bundle(
        project_root,
        state_root=state_root,
        destination_dir=tmp_path / "bundles",
        last_run_log_path=run_log_path,
    )

    with zipfile.ZipFile(bundle_path, "r") as archive:
        names = set(archive.namelist())
        assert f"project_logs/{run_log_path.name}" in names


def test_build_support_bundle_includes_fallback_app_log(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    state_root = tmp_path / "state"
    _write_valid_project(project_root)

    blocker = state_root / "logs"
    blocker.parent.mkdir(parents=True, exist_ok=True)
    blocker.write_text("block mkdir", encoding="utf-8")

    logging_result = configure_app_logging(state_root=state_root)
    assert logging_result.tier == "fallback"
    assert logging_result.log_path is not None
    logging_result.log_path.write_text("fallback app log\n", encoding="utf-8")

    bundle_path = build_support_bundle(
        project_root,
        state_root=state_root,
        destination_dir=tmp_path / "bundles",
    )

    with zipfile.ZipFile(bundle_path, "r") as archive:
        names = set(archive.namelist())
        assert "global_logs/app.log" in names


def test_build_support_bundle_includes_local_history_diagnostics(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    state_root = tmp_path / "state"
    _write_valid_project(project_root)
    manifest = load_project_manifest(project_root / "cbcs" / "project.json")
    SettingsService(state_root=state_root).save_global(
        {
            "schema_version": 1,
            "local_history": {
                "max_checkpoints_per_file": 7,
                "retention_days": 14,
                "max_tracked_file_bytes": 2048,
                "exclude_patterns": ["*.bin"],
            },
        }
    )
    history_store = LocalHistoryStore(state_root=state_root)
    file_path = project_root / "run.py"
    history_store.create_checkpoint(
        str(file_path.resolve()),
        "print('v1')\n",
        project_id=manifest.project_id,
        project_root=str(project_root.resolve()),
        source="save",
    )
    history_store.save_draft(
        str(file_path.resolve()),
        "print('draft')\n",
        project_id=manifest.project_id,
        project_root=str(project_root.resolve()),
    )

    bundle_path = build_support_bundle(
        project_root,
        state_root=state_root,
        destination_dir=tmp_path / "bundles",
    )

    with zipfile.ZipFile(bundle_path, "r") as archive:
        names = set(archive.namelist())
        assert "diagnostics/local_history.json" in names
        payload = json.loads(archive.read("diagnostics/local_history.json").decode("utf-8"))
        assert payload["project_timeline_count"] == 1
        assert payload["project_checkpoint_count"] == 1
        assert payload["project_draft_count"] == 1
        assert payload["retention_policy"]["max_checkpoints_per_file"] == 7
        assert payload["retention_policy"]["excluded_glob_patterns"] == ["*.bin"]
