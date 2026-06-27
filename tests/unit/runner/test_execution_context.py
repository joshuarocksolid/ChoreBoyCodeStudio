"""Unit tests for runner execution-context helpers."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import types

import pytest

from app.bootstrap.vendor_paths import resolve_vendor_root
from app.core import constants
from app.core.errors import RunLifecycleError
from app.debug.debug_models import DebugTransportConfig
from app.run.run_manifest import ReplControlConfig, RunManifest
from app.runner.debug.command_loop import RunnerDebugHost
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
        log_file=str((project_root / "logs" / "run_run_1.log").resolve()),
        mode="python_script",
        argv=("--arg",),
        env=(("CUSTOM_ENV", "value"),),
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
        argv=(),
        env=(),
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
        argv=(),
        env=(),
        timestamp="2026-03-01T01:01:01",
        repl_control=ReplControlConfig(
            protocol="cbcs_repl_control_v1",
            host="127.0.0.1",
            port=49123,
            session_token="token",
        ),
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

    vendor_root = str(resolve_vendor_root())

    with apply_execution_context(context):
        assert Path.cwd() == Path(context.working_directory)
        assert sys.argv[0] == context.entry_script_path
        assert sys.argv[1:] == ["--arg"]
        assert sys.path[0] == context.project_root
        assert vendor_root in sys.path
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


class _NoOpDebugTransport:
    instances: list["_NoOpDebugTransport"] = []

    def __init__(self, _config, *, engine_name: str, on_message, on_error) -> None:  # type: ignore[no-untyped-def]
        self.engine_name = engine_name
        type(self).instances.append(self)

    def connect(self) -> None:
        return None

    def send_message(self, message: dict[str, object]) -> None:
        return None

    def close(self) -> None:
        return None


def _build_qt_app_style_debug_manifest(tmp_path: Path) -> tuple[RunManifest, RunnerExecutionContext]:
    project_root = tmp_path / "project"
    app_dir = project_root / "app"
    app_dir.mkdir(parents=True)
    (app_dir / "__init__.py").write_text("", encoding="utf-8")
    (app_dir / "main_window.py").write_text("class MainWindow:\n    pass\n", encoding="utf-8")
    (project_root / "main.py").write_text("from app.main_window import MainWindow\n", encoding="utf-8")
    (project_root / "logs").mkdir(parents=True, exist_ok=True)

    manifest = RunManifest(
        manifest_version=constants.RUN_MANIFEST_VERSION,
        run_id="run_debug_qt_app",
        project_root=str(project_root.resolve()),
        entry_file="main.py",
        working_directory=str(project_root.resolve()),
        log_file=str((project_root / "logs" / "run_debug_qt_app.log").resolve()),
        mode=constants.RUN_MODE_PYTHON_DEBUG,
        argv=(),
        env=(),
        timestamp="2026-03-01T01:01:01",
        debug_transport=DebugTransportConfig(
            protocol="cb-debug-v1",
            host="127.0.0.1",
            port=9000,
            session_token="token",
        ),
    )
    return manifest, RunnerExecutionContext.from_manifest(manifest)


def test_debug_host_constructible_inside_execution_context_with_user_app_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Debug host must not re-import app.runner after apply_execution_context strips app.*."""
    manifest, context = _build_qt_app_style_debug_manifest(tmp_path)
    _NoOpDebugTransport.instances.clear()
    monkeypatch.setattr(
        "app.runner.debug.command_loop.RunnerDebugTransportClient",
        _NoOpDebugTransport,
    )

    with apply_execution_context(context):
        assert "app.runner" not in sys.modules
        host = RunnerDebugHost(manifest)

    assert _NoOpDebugTransport.instances
    assert host._transport is _NoOpDebugTransport.instances[-1]
