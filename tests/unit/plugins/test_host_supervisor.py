"""Unit tests for plugin host launch path selection."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.plugins.host_supervisor import PluginHostSupervisor
import app.plugins.host_supervisor as host_supervisor_module

pytestmark = pytest.mark.unit


def test_build_command_reexecs_apprun_when_outside_freecad(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host_boot = tmp_path / "run_plugin_host.py"
    host_boot.write_text("", encoding="utf-8")
    app_run = tmp_path / "AppRun"
    app_run.write_text("", encoding="utf-8")
    monkeypatch.setattr(host_supervisor_module, "is_running_inside_freecad_runtime", lambda: False)

    supervisor = PluginHostSupervisor(
        runtime_executable=str(app_run),
        host_boot_path=str(host_boot),
    )

    command = supervisor._build_command()

    assert command[0] == str(app_run.resolve())
    assert command[1] == "-c"


def test_build_command_does_not_reexec_apprun_when_inside_freecad(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host_boot = tmp_path / "run_plugin_host.py"
    host_boot.write_text("", encoding="utf-8")
    app_run = tmp_path / "AppRun"
    app_run.write_text("", encoding="utf-8")
    monkeypatch.setattr(host_supervisor_module, "is_running_inside_freecad_runtime", lambda: True)

    supervisor = PluginHostSupervisor(
        runtime_executable=str(app_run),
        host_boot_path=str(host_boot),
    )

    command = supervisor._build_command()

    assert command[0] != str(app_run.resolve())
    assert "AppRun" not in Path(command[0]).name
    assert "-c" not in command
    assert str(host_boot.resolve()) in command


def test_start_uses_forked_script_when_inside_freecad(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host_boot = tmp_path / "run_plugin_host.py"
    host_boot.write_text("", encoding="utf-8")
    app_run = tmp_path / "AppRun"
    app_run.write_text("", encoding="utf-8")
    monkeypatch.setattr(host_supervisor_module, "is_running_inside_freecad_runtime", lambda: True)
    calls: dict[str, object] = {}

    def fake_start_forked(self, **kwargs: object) -> int:  # type: ignore[no-untyped-def]
        calls["kwargs"] = kwargs
        return 4242

    def fake_popen_start(self, command: list[str], **kwargs: object) -> int:  # type: ignore[no-untyped-def]
        raise AssertionError(f"Popen start must not run inside FreeCAD: {command}")

    monkeypatch.setattr(
        host_supervisor_module.ProcessSupervisor,
        "start_forked_script",
        fake_start_forked,
    )
    monkeypatch.setattr(host_supervisor_module.ProcessSupervisor, "start", fake_popen_start)

    supervisor = PluginHostSupervisor(
        runtime_executable=str(app_run),
        host_boot_path=str(host_boot),
    )

    process_id = supervisor.start()

    assert process_id == 4242
    kwargs = calls["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["script_path"] == str(host_boot.resolve())
    assert str(host_boot.resolve()) in kwargs["argv"]
