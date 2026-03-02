"""Unit tests for run service helper contracts."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys

import pytest

from app.core.models import LoadedProject, ProjectMetadata
from app.run.run_manifest import load_run_manifest
from app.run.run_service import (
    RunService,
    build_run_log_path,
    build_run_manifest_path,
    generate_run_id,
    resolve_runtime_executable,
)

pytestmark = pytest.mark.unit


def test_generate_run_id_includes_timestamp_and_random_suffix() -> None:
    """Run IDs should include deterministic timestamp prefix and unique suffix."""
    now = datetime(2026, 3, 1, 5, 6, 7)
    first = generate_run_id(now=now)
    second = generate_run_id(now=now)

    assert first.startswith("20260301_050607_")
    assert second.startswith("20260301_050607_")
    assert first != second


def test_build_run_manifest_path_uses_project_contract(tmp_path: Path) -> None:
    """Run manifest should target .cbcs/runs directory."""
    project_root = tmp_path / "project_alpha"
    run_id = "20260301_050607_abcd12"

    manifest_path = build_run_manifest_path(project_root, run_id)

    assert manifest_path == project_root / ".cbcs" / "runs" / f"run_manifest_{run_id}.json"


def test_build_run_log_path_uses_project_logs_contract(tmp_path: Path) -> None:
    """Run log should target project logs directory."""
    project_root = tmp_path / "project_alpha"
    run_id = "20260301_050607_abcd12"

    log_path = build_run_log_path(project_root, run_id)

    assert log_path == project_root / "logs" / f"run_{run_id}.log"


def test_resolve_runtime_executable_prefers_explicit_config(tmp_path: Path) -> None:
    """Configured runtime path should override automatic resolution."""
    custom_runtime = tmp_path / "custom_runtime"
    custom_runtime.write_text("", encoding="utf-8")

    assert resolve_runtime_executable(str(custom_runtime)) == str(custom_runtime.resolve())


def test_resolve_runtime_executable_falls_back_to_python_when_apprun_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """When AppRun path is missing in cloud dev env, fallback should use current python."""
    monkeypatch.setattr("app.run.run_service.constants.APP_RUN_PATH", "/path/that/does/not/exist")
    assert resolve_runtime_executable(None) == sys.executable


def test_build_runner_command_for_apprun_bootstraps_runner_parent_path(tmp_path: Path) -> None:
    """AppRun command payload should include repo path so `app` imports resolve."""
    runner_boot = tmp_path / "run_runner.py"
    runner_boot.write_text("print('stub')\n", encoding="utf-8")
    service = RunService(runtime_executable="/opt/freecad/AppRun", runner_boot_path=str(runner_boot))

    command = service._build_runner_command("/tmp/run_manifest.json")

    assert command[0] == "/opt/freecad/AppRun"
    assert command[1] == "-c"
    payload = command[2]
    assert "sys.path.insert(0" in payload
    assert str(tmp_path.resolve()) in payload
    assert "runpy.run_path" in payload


def test_start_run_applies_explicit_run_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicit run overrides should flow into generated run manifest fields."""
    project_root = tmp_path / "project"
    (project_root / "app").mkdir(parents=True)
    (project_root / "run.py").write_text("print('run')\n", encoding="utf-8")
    (project_root / "app" / "main.py").write_text("print('main')\n", encoding="utf-8")
    loaded_project = LoadedProject(
        project_root=str(project_root.resolve()),
        manifest_path=str((project_root / ".cbcs" / "project.json").resolve()),
        metadata=ProjectMetadata(
            schema_version=1,
            name="demo",
            default_entry="run.py",
            default_mode="python_script",
            working_directory=".",
            env_overrides={"BASE_ENV": "1"},
            safe_mode=True,
        ),
        entries=[],
    )
    service = RunService(runtime_executable=sys.executable, runner_boot_path=str(tmp_path / "run_runner.py"))
    monkeypatch.setattr(service.supervisor, "start", lambda *args, **kwargs: None)

    session = service.start_run(
        loaded_project,
        entry_file="app/main.py",
        mode="qt_app",
        argv=["--flag"],
        working_directory="app",
        env_overrides={"EXTRA_ENV": "2"},
        safe_mode=False,
    )
    manifest = load_run_manifest(session.manifest_path)

    assert manifest.entry_file == "app/main.py"
    assert manifest.mode == "qt_app"
    assert manifest.working_directory == str((project_root / "app").resolve())
    assert manifest.argv == ["--flag"]
    assert manifest.env["BASE_ENV"] == "1"
    assert manifest.env["EXTRA_ENV"] == "2"
    assert manifest.safe_mode is False
    assert manifest.log_file == session.log_file_path
    assert Path(manifest.log_file).name.endswith(".log")


def test_start_run_uses_project_default_argv_when_not_overridden(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When argv is omitted, metadata default_argv should populate run manifest."""
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)
    (project_root / "run.py").write_text("print('run')\n", encoding="utf-8")
    loaded_project = LoadedProject(
        project_root=str(project_root.resolve()),
        manifest_path=str((project_root / ".cbcs" / "project.json").resolve()),
        metadata=ProjectMetadata(
            schema_version=1,
            name="demo",
            default_entry="run.py",
            default_mode="python_script",
            default_argv=["--from-default"],
        ),
        entries=[],
    )
    service = RunService(runtime_executable=sys.executable, runner_boot_path=str(tmp_path / "run_runner.py"))
    monkeypatch.setattr(service.supervisor, "start", lambda *args, **kwargs: None)

    session = service.start_run(loaded_project)
    manifest = load_run_manifest(session.manifest_path)

    assert manifest.argv == ["--from-default"]


def test_start_run_supports_projectless_repl_with_home_working_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Projectless REPL runs should default to home cwd and safe mode off."""
    state_root = tmp_path / "state"
    service = RunService(
        runtime_executable=sys.executable,
        runner_boot_path=str(tmp_path / "run_runner.py"),
        state_root=str(state_root.resolve()),
    )
    launch_context: dict[str, str] = {}

    def _capture_start(_command: list[str], *, cwd: str, env) -> None:  # type: ignore[no-untyped-def]
        launch_context["cwd"] = cwd

    monkeypatch.setattr(service.supervisor, "start", _capture_start)

    session = service.start_run(None, mode="python_repl")
    manifest = load_run_manifest(session.manifest_path)
    expected_home = str(Path.home().expanduser().resolve())

    assert manifest.mode == "python_repl"
    assert manifest.safe_mode is False
    assert manifest.working_directory == expected_home
    assert manifest.log_file == session.log_file_path
    assert launch_context["cwd"] == expected_home
    assert "/repl/runs/" in session.manifest_path
    assert "/repl/logs/" in session.log_file_path
