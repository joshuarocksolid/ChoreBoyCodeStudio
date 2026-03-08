"""Unit tests for ProcessSupervisor stale-exit hardening."""

from __future__ import annotations

import pytest

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

