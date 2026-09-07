"""Unit tests for ProcessSupervisor stale-exit hardening."""

from __future__ import annotations

import time
from typing import cast

import pytest

import app.run.process_supervisor as process_supervisor_module
from app.run.process_supervisor import ProcessEvent, ProcessSupervisor, _ProcessResources

pytestmark = pytest.mark.unit


class _FakeProcess:
    def __init__(self, *, pid: int, return_code: int = 0) -> None:
        self.pid = pid
        self.returncode = return_code
        self.stdout = None
        self.stderr = None
        self.stdin = None

    def wait(self) -> int:
        return self.returncode

    def poll(self) -> int:
        return self.returncode


class _FakeRunningProcess:
    pid = 4004
    returncode = None
    stdout = None
    stderr = None
    stdin = None

    def wait(self) -> int:
        return 0

    def poll(self) -> None:
        return None


def test_start_sanitizes_virtualenv_for_apprun_command(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    def fake_popen(command: list[str], **kwargs: object) -> _FakeRunningProcess:
        calls["command"] = command
        calls["kwargs"] = kwargs
        return _FakeRunningProcess()

    monkeypatch.setattr(process_supervisor_module.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(ProcessSupervisor, "_start_waiter_thread", lambda self, process: None)

    supervisor = ProcessSupervisor()
    supervisor.start(
        ["/opt/freecad/AppRun", "-c", "print('ok')"],
        cwd="/tmp",
        env={
            "PATH": "/usr/bin",
            "VIRTUAL_ENV": "/tmp/stale-venv",
            "VIRTUAL_ENV_PROMPT": "(.venv-editor) ",
        },
    )

    kwargs = cast(dict[str, object], calls["kwargs"])
    assert kwargs["env"] == {"PATH": "/usr/bin"}


def test_start_wraps_eacces_popen_as_run_lifecycle_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_popen(command: list[str], **kwargs: object) -> _FakeRunningProcess:
        raise PermissionError(13, "Permission denied", "/opt/freecad/AppRun")

    monkeypatch.setattr(process_supervisor_module.subprocess, "Popen", fake_popen)

    supervisor = ProcessSupervisor()
    with pytest.raises(process_supervisor_module.RunLifecycleError, match="Permission denied") as caught:
        supervisor.start(["/opt/freecad/AppRun", "-c", "print('ok')"], cwd="/tmp")

    assert isinstance(caught.value.__cause__, PermissionError)
    assert caught.value.__cause__.errno == 13


def test_start_preserves_default_env_for_plain_python_command(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    def fake_popen(command: list[str], **kwargs: object) -> _FakeRunningProcess:
        calls["command"] = command
        calls["kwargs"] = kwargs
        return _FakeRunningProcess()

    monkeypatch.setattr(process_supervisor_module.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(ProcessSupervisor, "_start_waiter_thread", lambda self, process: None)

    supervisor = ProcessSupervisor()
    supervisor.start(["/usr/bin/python3", "script.py"], cwd="/tmp")

    kwargs = cast(dict[str, object], calls["kwargs"])
    assert kwargs["env"] is None


def test_start_forked_script_runs_script_without_execve(tmp_path) -> None:
    script = tmp_path / "child.py"
    script.write_text("import sys\nprint('fork-ok')\nsys.exit(0)\n", encoding="utf-8")
    events: list[ProcessEvent] = []
    supervisor = ProcessSupervisor(on_event=events.append)

    supervisor.start_forked_script(
        script_path=str(script),
        argv=[str(script)],
        cwd=str(tmp_path),
    )
    deadline = time.monotonic() + 2.0
    while supervisor.is_running() and time.monotonic() < deadline:
        time.sleep(0.01)

    output_text = "".join(event.text or "" for event in events if event.event_type == "output")
    assert "fork-ok" in output_text
    assert supervisor.is_running() is False


def test_wait_for_exit_ignores_stale_process_when_new_process_is_active() -> None:
    events: list[ProcessEvent] = []
    supervisor = ProcessSupervisor(on_event=events.append)
    stale_process = _FakeProcess(pid=1001, return_code=0)
    active_process = _FakeProcess(pid=2002, return_code=0)

    with supervisor._lock:
        supervisor._process = active_process  # type: ignore[assignment]
        supervisor._state = "running"
        supervisor._terminated_by_user = False
        supervisor._process_resources[stale_process.pid] = _ProcessResources(reader_threads=[], reader_streams=[])
        supervisor._process_resources[active_process.pid] = _ProcessResources(reader_threads=[], reader_streams=[])

    supervisor._wait_for_exit(stale_process)  # type: ignore[arg-type]

    assert supervisor.process_id == active_process.pid
    assert supervisor.state == "running"
    assert stale_process.pid not in supervisor._process_resources
    assert active_process.pid in supervisor._process_resources
    assert events == []


def test_wait_for_exit_emits_exit_events_for_active_process() -> None:
    events: list[ProcessEvent] = []
    supervisor = ProcessSupervisor(on_event=events.append)
    active_process = _FakeProcess(pid=3003, return_code=7)

    with supervisor._lock:
        supervisor._process = active_process  # type: ignore[assignment]
        supervisor._state = "running"
        supervisor._terminated_by_user = False
        supervisor._process_resources[active_process.pid] = _ProcessResources(reader_threads=[], reader_streams=[])

    supervisor._wait_for_exit(active_process)  # type: ignore[arg-type]

    assert supervisor.process_id is None
    assert supervisor.state == "exited"
    assert [event.event_type for event in events] == ["state", "exit"]
    assert events[0].state == "exited"
    assert events[1].return_code == 7

