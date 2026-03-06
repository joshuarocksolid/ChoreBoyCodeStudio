"""Unit tests for shared runtime launch helper functions."""

from __future__ import annotations

from pathlib import Path

import pytest

import app.run.runtime_launch as runtime_launch_module
from app.run.runtime_launch import (
    build_runpy_bootstrap_payload,
    is_freecad_runtime_executable,
    resolve_runtime_executable,
)

pytestmark = pytest.mark.unit


def test_is_freecad_runtime_executable_supports_apprun_and_appimage_names() -> None:
    assert is_freecad_runtime_executable("/opt/freecad/AppRun") is True
    assert is_freecad_runtime_executable("/opt/freecad/usr/bin/freecad") is True
    assert is_freecad_runtime_executable("/tmp/FreeCAD.AppImage") is True
    assert is_freecad_runtime_executable("/usr/bin/python3") is False


def test_build_runpy_bootstrap_payload_includes_path_and_argv() -> None:
    payload = build_runpy_bootstrap_payload(
        script_path="/workspace/run_runner.py",
        path_entry="/workspace",
        argv=["run_runner.py", "--manifest", "/tmp/manifest.json"],
    )

    assert "import runpy, sys;" in payload
    assert "sys.path.insert(0" in payload
    assert "sys.argv=['run_runner.py', '--manifest', '/tmp/manifest.json']" in payload
    assert "runpy.run_path('/workspace/run_runner.py'" in payload


def test_resolve_runtime_executable_prefers_explicit_override(tmp_path: Path) -> None:
    runtime_path = tmp_path / "custom_runtime"
    runtime_path.write_text("", encoding="utf-8")

    resolved = resolve_runtime_executable(str(runtime_path))

    assert resolved == str(runtime_path.resolve())


def test_resolve_runtime_executable_falls_back_to_sys_executable_when_default_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runtime_launch_module.constants, "APP_RUN_PATH", "/tmp/does-not-exist-apprun")
    monkeypatch.setattr(runtime_launch_module.sys, "executable", "/usr/bin/custom-python")

    resolved = resolve_runtime_executable(None)

    assert resolved == "/usr/bin/custom-python"
