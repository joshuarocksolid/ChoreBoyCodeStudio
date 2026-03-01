"""Unit tests for runner execution-context helpers."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import types

import pytest

from app.core import constants
from app.core.errors import RunLifecycleError
from app.run.run_manifest import RunManifest
from app.runner.execution_context import RunnerExecutionContext, apply_execution_context

pytestmark = pytest.mark.unit


def _build_manifest(tmp_path: Path, *, entry_file: str = "run.py") -> RunManifest:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / entry_file).write_text("print('ok')\n", encoding="utf-8")
    return RunManifest(
        manifest_version=constants.RUN_MANIFEST_VERSION,
        run_id="run_1",
        project_root=str(project_root.resolve()),
        entry_file=entry_file,
        working_directory=str(project_root.resolve()),
        mode="python_script",
        argv=["--arg"],
        env={"CUSTOM_ENV": "value"},
        safe_mode=True,
        log_file=str((project_root / "logs" / "run.log").resolve()),
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
        mode="python_script",
        argv=[],
        env={},
        safe_mode=True,
        log_file=str((project_root / "logs" / "run.log").resolve()),
        timestamp="2026-03-01T01:01:01",
    )

    with pytest.raises(RunLifecycleError, match="Entry file not found"):
        RunnerExecutionContext.from_manifest(manifest)


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
