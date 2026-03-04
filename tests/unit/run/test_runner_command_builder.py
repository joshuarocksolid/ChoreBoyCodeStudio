"""Unit tests for shared runner command construction."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.run.runner_command_builder import build_runner_command

pytestmark = pytest.mark.unit


def test_build_runner_command_for_apprun_bootstraps_runner_parent_path(tmp_path: Path) -> None:
    """AppRun command should inject runner parent into ``sys.path`` payload."""
    runner_boot = tmp_path / "run_runner.py"
    runner_boot.write_text("print('stub')\n", encoding="utf-8")

    command = build_runner_command(
        runtime_executable="/opt/freecad/AppRun",
        runner_boot_path=str(runner_boot),
        manifest_path="/tmp/run_manifest.json",
    )

    assert command[0] == "/opt/freecad/AppRun"
    assert command[1] == "-c"
    payload = command[2]
    assert "sys.path.insert(0" in payload
    assert str(tmp_path.resolve()) in payload
    assert "runpy.run_path" in payload


def test_build_runner_command_for_python_runtime_uses_manifest_arguments(tmp_path: Path) -> None:
    """Non-AppRun runtimes should launch run_runner.py directly."""
    runner_boot = tmp_path / "run_runner.py"
    runner_boot.write_text("print('stub')\n", encoding="utf-8")

    command = build_runner_command(
        runtime_executable="/usr/bin/python3",
        runner_boot_path=str(runner_boot),
        manifest_path="/tmp/run_manifest.json",
    )

    assert command == [
        "/usr/bin/python3",
        str(runner_boot.resolve()),
        "--manifest",
        "/tmp/run_manifest.json",
    ]
