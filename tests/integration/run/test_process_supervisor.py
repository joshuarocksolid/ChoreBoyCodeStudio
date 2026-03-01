"""Integration tests for process supervisor lifecycle behavior."""

from __future__ import annotations

import gc
import sys
import time

import pytest

from app.run.process_supervisor import ProcessEvent, ProcessSupervisor

pytestmark = pytest.mark.integration


def _wait_until(predicate, timeout_seconds: float = 3.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_process_supervisor_streams_output_and_emits_exit_event(tmp_path) -> None:
    """Supervisor should stream stdout/stderr and produce exit events."""
    events: list[ProcessEvent] = []
    supervisor = ProcessSupervisor(on_event=events.append)
    command = [
        sys.executable,
        "-c",
        "import sys,time;print('hello-out');print('hello-err', file=sys.stderr);time.sleep(0.1)",
    ]

    supervisor.start(command, cwd=str(tmp_path))

    assert _wait_until(lambda: any(event.event_type == "exit" for event in events))
    assert any(event.event_type == "output" and event.stream == "stdout" and "hello-out" in (event.text or "") for event in events)
    assert any(event.event_type == "output" and event.stream == "stderr" and "hello-err" in (event.text or "") for event in events)
    assert any(event.event_type == "exit" and event.return_code == 0 for event in events)


def test_process_supervisor_stop_terminates_long_running_process(tmp_path) -> None:
    """Stop should terminate active long-running process and emit exit event."""
    events: list[ProcessEvent] = []
    supervisor = ProcessSupervisor(on_event=events.append)
    command = [sys.executable, "-c", "import time; print('tick'); time.sleep(30)"]

    supervisor.start(command, cwd=str(tmp_path))
    assert _wait_until(lambda: supervisor.is_running())

    supervisor.stop(terminate_timeout_seconds=0.2)
    assert _wait_until(lambda: any(event.event_type == 'exit' for event in events))
    assert any(event.event_type == "exit" and event.terminated_by_user for event in events)


def test_process_supervisor_send_input_writes_to_child_stdin(tmp_path) -> None:
    """Supervisor should support interactive stdin writes."""
    events: list[ProcessEvent] = []
    supervisor = ProcessSupervisor(on_event=events.append)
    command = [
        sys.executable,
        "-c",
        "import sys; line = sys.stdin.readline().strip(); print(f'ECHO:{line}')",
    ]

    supervisor.start(command, cwd=str(tmp_path))
    supervisor.send_input("hello\n")

    assert _wait_until(lambda: any(event.event_type == "exit" for event in events))
    assert any(event.event_type == "output" and "ECHO:hello" in (event.text or "") for event in events)


def test_process_supervisor_pause_interrupts_active_process(tmp_path) -> None:
    """Pause should send interrupt signal to active process."""
    events: list[ProcessEvent] = []
    supervisor = ProcessSupervisor(on_event=events.append)
    command = [
        sys.executable,
        "-c",
        "import time; print('READY', flush=True); time.sleep(30)",
    ]
    supervisor.start(command, cwd=str(tmp_path))
    assert _wait_until(lambda: supervisor.is_running())

    assert supervisor.pause() is True
    assert _wait_until(
        lambda: any(event.event_type == "exit" and (event.return_code or 0) != 0 for event in events),
        timeout_seconds=5.0,
    )


@pytest.mark.filterwarnings("error::pytest.PytestUnraisableExceptionWarning")
@pytest.mark.filterwarnings("error::ResourceWarning")
def test_process_supervisor_stop_cleans_up_stream_handles(tmp_path) -> None:
    """Stop path should not leave unclosed stdout/stderr stream wrappers."""
    events: list[ProcessEvent] = []
    supervisor = ProcessSupervisor(on_event=events.append)
    command = [sys.executable, "-c", "import time; print('tick'); time.sleep(30)"]

    supervisor.start(command, cwd=str(tmp_path))
    assert _wait_until(lambda: supervisor.is_running())

    supervisor.stop(terminate_timeout_seconds=0.2)
    assert _wait_until(lambda: any(event.event_type == "exit" for event in events))

    del supervisor
    gc.collect()


@pytest.mark.filterwarnings("error::pytest.PytestUnraisableExceptionWarning")
@pytest.mark.filterwarnings("error::ResourceWarning")
def test_process_supervisor_exit_cleans_up_stream_handles(tmp_path) -> None:
    """Natural process exit should not leave unclosed stdout/stderr streams."""
    events: list[ProcessEvent] = []
    supervisor = ProcessSupervisor(on_event=events.append)
    command = [sys.executable, "-c", "print('done')"]

    supervisor.start(command, cwd=str(tmp_path))
    assert _wait_until(lambda: any(event.event_type == "exit" for event in events))

    del supervisor
    gc.collect()
