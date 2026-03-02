"""Unit tests for runner execution-context helpers."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import types

import pytest

from app.core import constants
from app.core.errors import RunLifecycleError
from app.run.run_manifest import RunManifest
from app.runner.execution_context import RunnerExecutionContext, apply_execution_context

pytestmark = pytest.mark.unit


def _build_manifest(tmp_path: Path, *, entry_file: str = "run.py", safe_mode: bool = True) -> RunManifest:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / entry_file).write_text("print('ok')\n", encoding="utf-8")
    return RunManifest(
        manifest_version=constants.RUN_MANIFEST_VERSION,
        run_id="run_1",
        project_root=str(project_root.resolve()),
        entry_file=entry_file,
        working_directory=str(project_root.resolve()),
        log_file=str((project_root / "logs" / "run_run_1.log").resolve()),
        mode="python_script",
        argv=["--arg"],
        env={"CUSTOM_ENV": "value"},
        safe_mode=safe_mode,
        timestamp="2026-03-01T01:01:01",
    )


def test_execution_context_from_manifest_resolves_paths(tmp_path: Path) -> None:
    """Execution context should resolve entry script and working directory paths."""
    manifest = _build_manifest(tmp_path)
    context = RunnerExecutionContext.from_manifest(manifest)

    assert context.project_root == str((tmp_path / "project").resolve())
    assert context.working_directory == str((tmp_path / "project").resolve())
    assert context.entry_script_path == str((tmp_path / "project" / "run.py").resolve())


def test_execution_context_from_manifest_rejects_missing_entry_file(tmp_path: Path) -> None:
    """Missing entry script should fail before runner executes user code."""
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)
    manifest = RunManifest(
        manifest_version=constants.RUN_MANIFEST_VERSION,
        run_id="run_1",
        project_root=str(project_root.resolve()),
        entry_file="missing.py",
        working_directory=str(project_root.resolve()),
        log_file=str((project_root / "logs" / "run_run_1.log").resolve()),
        mode="python_script",
        argv=[],
        env={},
        safe_mode=True,
        timestamp="2026-03-01T01:01:01",
    )

    with pytest.raises(RunLifecycleError, match="Entry file not found"):
        RunnerExecutionContext.from_manifest(manifest)


def test_execution_context_from_manifest_allows_repl_without_entry_file(tmp_path: Path) -> None:
    """REPL mode should not require an on-disk entry script."""
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)
    manifest = RunManifest(
        manifest_version=constants.RUN_MANIFEST_VERSION,
        run_id="run_1",
        project_root=str(project_root.resolve()),
        entry_file="__repl__.py",
        working_directory=str(project_root.resolve()),
        log_file=str((project_root / "logs" / "run_run_1.log").resolve()),
        mode=constants.RUN_MODE_PYTHON_REPL,
        argv=[],
        env={},
        safe_mode=False,
        timestamp="2026-03-01T01:01:01",
    )

    context = RunnerExecutionContext.from_manifest(manifest)
    assert context.entry_script_path == "<python_repl>"


def test_apply_execution_context_sets_and_restores_runtime_state(tmp_path: Path) -> None:
    """Context manager should restore cwd, argv, sys.path, and env after execution."""
    manifest = _build_manifest(tmp_path)
    context = RunnerExecutionContext.from_manifest(manifest)
    previous_cwd = Path.cwd()
    previous_argv = list(sys.argv)
    previous_sys_path = list(sys.path)
    original_app_module = sys.modules.get("app")
    sentinel_app_module = types.ModuleType("sentinel_app")
    sys.modules["app"] = sentinel_app_module

    with apply_execution_context(context):
        assert Path.cwd() == Path(context.working_directory)
        assert sys.argv[0] == context.entry_script_path
        assert sys.argv[1:] == ["--arg"]
        assert sys.path[0] == context.project_root
        assert "CUSTOM_ENV" in os.environ

    assert Path.cwd() == previous_cwd
    assert sys.argv == previous_argv
    assert sys.path == previous_sys_path
    assert "CUSTOM_ENV" not in os.environ
    assert sys.modules.get("app") is sentinel_app_module
    if original_app_module is not None:
        sys.modules["app"] = original_app_module
    else:
        sys.modules.pop("app", None)


def test_apply_execution_context_blocks_subprocess_in_safe_mode(tmp_path: Path) -> None:
    """Safe mode should prevent user subprocess execution primitives."""
    manifest = _build_manifest(tmp_path, safe_mode=True)
    context = RunnerExecutionContext.from_manifest(manifest)
    original_run = subprocess.run

    with apply_execution_context(context):
        assert subprocess.run is not original_run
        with pytest.raises(PermissionError, match="safe mode"):
            subprocess.run(["echo", "hi"], check=False)

    assert subprocess.run is original_run


def test_apply_execution_context_blocks_write_outside_project_in_safe_mode(tmp_path: Path) -> None:
    """Safe mode should block write attempts outside project root."""
    manifest = _build_manifest(tmp_path, safe_mode=True)
    context = RunnerExecutionContext.from_manifest(manifest)
    outside_target = tmp_path / "outside.txt"
    original_open = open

    with apply_execution_context(context):
        with pytest.raises(PermissionError, match="outside project root"):
            with open(outside_target, "w", encoding="utf-8"):
                pass

    assert open is original_open


def test_apply_execution_context_allows_write_within_project_in_safe_mode(tmp_path: Path) -> None:
    """Safe mode should allow writes under project root."""
    manifest = _build_manifest(tmp_path, safe_mode=True)
    context = RunnerExecutionContext.from_manifest(manifest)
    inside_target = Path(context.project_root) / "inside.txt"

    with apply_execution_context(context):
        with open(inside_target, "w", encoding="utf-8") as handle:
            handle.write("ok")

    assert inside_target.read_text(encoding="utf-8") == "ok"


def test_apply_execution_context_leaves_subprocess_available_when_safe_mode_disabled(tmp_path: Path) -> None:
    """Safe mode disabled should not monkeypatch subprocess APIs."""
    manifest = _build_manifest(tmp_path, safe_mode=False)
    context = RunnerExecutionContext.from_manifest(manifest)
    original_run = subprocess.run

    with apply_execution_context(context):
        assert subprocess.run is original_run


def test_apply_execution_context_blocks_write_outside_project_in_safe_mode(tmp_path: Path) -> None:
    """Safe mode should block writes targeting paths outside project root."""
    manifest = _build_manifest(tmp_path, safe_mode=True)
    context = RunnerExecutionContext.from_manifest(manifest)
    outside_path = tmp_path / "outside.txt"

    with apply_execution_context(context):
        with pytest.raises(PermissionError, match="outside project root"):
            outside_path.write_text("blocked\n", encoding="utf-8")


def test_apply_execution_context_allows_write_within_project_in_safe_mode(tmp_path: Path) -> None:
    """Safe mode should permit writes under the project root."""
    manifest = _build_manifest(tmp_path, safe_mode=True)
    context = RunnerExecutionContext.from_manifest(manifest)
    inside_path = Path(context.project_root) / "allowed.txt"

    with apply_execution_context(context):
        inside_path.write_text("ok\n", encoding="utf-8")

    assert inside_path.read_text(encoding="utf-8") == "ok\n"
