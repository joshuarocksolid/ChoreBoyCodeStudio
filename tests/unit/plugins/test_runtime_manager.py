"""Unit tests for plugin runtime manager request/response behavior."""

from __future__ import annotations

import threading

import pytest

from app.core.errors import RunLifecycleError
from app.plugins.rpc_protocol import (
    build_job_event,
    build_job_terminal_message,
    build_response,
    decode_message,
    encode_message,
)
from app.plugins.runtime_manager import PluginRuntimeManager
from app.run.process_supervisor import ProcessEvent

pytestmark = pytest.mark.unit


class _ResponsiveHostSupervisor:
    def __init__(self, *, on_event, **_kwargs) -> None:  # type: ignore[no-untyped-def]
        self._on_event = on_event
        self._running = False
        self.sent_input: list[str] = []

    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def send_input(self, text: str) -> None:
        self.sent_input.append(text)
        payload = decode_message(text)
        payload_type = payload.get("type")
        if payload_type == "command":
            response = build_response(
                request_id=payload["request_id"],
                ok=True,
                result={"echo": payload.get("payload", {})},
            )
            self._on_event(
                ProcessEvent(
                    event_type="output",
                    stream="stdout",
                    text=encode_message(response),
                )
            )
            return
        if payload_type == "provider_query":
            response = build_response(
                request_id=payload["request_id"],
                ok=True,
                result={"provider_key": payload["provider_key"], "request": payload.get("request", {})},
            )
            self._on_event(
                ProcessEvent(
                    event_type="output",
                    stream="stdout",
                    text=encode_message(response),
                )
            )
            return
        if payload_type == "provider_job_start":
            messages = [
                build_response(
                    request_id=payload["request_id"],
                    ok=True,
                    result={"job_id": payload["job_id"], "provider_key": payload["provider_key"]},
                ),
                build_job_event(
                    job_id=payload["job_id"],
                    provider_key=payload["provider_key"],
                    event_type="job_progress",
                    payload={"completed": 1},
                ),
                build_job_terminal_message(
                    job_id=payload["job_id"],
                    provider_key=payload["provider_key"],
                    message_type="job_result",
                    result={"job": "done"},
                ),
            ]
            for message in messages:
                self._on_event(
                    ProcessEvent(
                        event_type="output",
                        stream="stdout",
                        text=encode_message(message),
                    )
                )
            return
        if payload_type == "provider_job_cancel":
            response = build_response(
                request_id=payload["request_id"],
                ok=True,
                result={"job_id": payload["job_id"], "cancel_requested": True},
            )
            self._on_event(
                ProcessEvent(
                    event_type="output",
                    stream="stdout",
                    text=encode_message(response),
                )
            )


class _SilentHostSupervisor(_ResponsiveHostSupervisor):
    def send_input(self, text: str) -> None:
        self.sent_input.append(text)


def test_invoke_command_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.plugins.runtime_manager.PluginHostSupervisor", _ResponsiveHostSupervisor)
    manager = PluginRuntimeManager()

    result = manager.invoke_command("plugin.demo.echo", {"value": 42})

    assert result == {"echo": {"value": 42}}
    assert manager.is_running() is True


def test_invoke_command_times_out_when_host_is_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.plugins.runtime_manager.PluginHostSupervisor", _SilentHostSupervisor)
    manager = PluginRuntimeManager()

    with pytest.raises(RunLifecycleError, match="timed out"):
        manager.invoke_command("plugin.demo.echo", {"value": 1}, timeout_seconds=0.01)


def test_host_exit_unblocks_pending_request_with_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.plugins.runtime_manager.PluginHostSupervisor", _SilentHostSupervisor)
    manager = PluginRuntimeManager()
    error_text: list[str] = []

    def worker() -> None:
        try:
            manager.invoke_command("plugin.demo.echo", {"value": 1}, timeout_seconds=1.0)
        except RunLifecycleError as exc:
            error_text.append(str(exc))

    thread = threading.Thread(target=worker)
    thread.start()
    deadline = threading.Event()
    for _attempt in range(100):
        with manager._pending_lock:
            if manager._pending_requests:
                break
        deadline.wait(0.01)
    manager._handle_event(ProcessEvent(event_type="exit", return_code=1))
    thread.join(timeout=1.0)

    assert error_text
    assert "exited before response" in error_text[0]


def test_stderr_output_is_recorded_as_last_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.plugins.runtime_manager.PluginHostSupervisor", _ResponsiveHostSupervisor)
    manager = PluginRuntimeManager()

    manager._handle_event(ProcessEvent(event_type="output", stream="stderr", text="boom"))

    assert manager.last_error == "boom"


def test_stderr_output_is_persisted_to_plugin_host_log(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.plugins.runtime_manager.PluginHostSupervisor", _ResponsiveHostSupervisor)
    manager = PluginRuntimeManager(state_root=str((tmp_path / "state").resolve()))

    manager._handle_event(ProcessEvent(event_type="output", stream="stderr", text="boom\n"))

    log_path = manager.log_file_path
    assert "plugin_host.log" in log_path
    assert "stderr: boom" in open(log_path, encoding="utf-8").read()


def test_host_exit_is_persisted_to_plugin_host_log(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.plugins.runtime_manager.PluginHostSupervisor", _ResponsiveHostSupervisor)
    manager = PluginRuntimeManager(state_root=str((tmp_path / "state").resolve()))

    manager._handle_event(ProcessEvent(event_type="exit", return_code=3, terminated_by_user=False))

    assert "host exited return_code=3 terminated_by_user=False" in open(
        manager.log_file_path,
        encoding="utf-8",
    ).read()


def test_invoke_workflow_query_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.plugins.runtime_manager.PluginHostSupervisor", _ResponsiveHostSupervisor)
    manager = PluginRuntimeManager()

    result = manager.invoke_workflow_query("cbcs.python_tools:formatter", {"source_text": "x=1\n"})

    assert result["provider_key"] == "cbcs.python_tools:formatter"
    assert result["request"] == {"source_text": "x=1\n"}


def test_start_workflow_job_receives_events_and_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.plugins.runtime_manager.PluginHostSupervisor", _ResponsiveHostSupervisor)
    manager = PluginRuntimeManager()
    events: list[tuple[str, dict[str, object]]] = []

    job = manager.start_workflow_job(
        "cbcs.pytest:pytest",
        {"project_root": "/tmp/project"},
        on_event=lambda event_type, payload: events.append((event_type, dict(payload))),
    )
    result = manager.wait_for_workflow_job(job)

    assert result == {"job": "done"}
    assert events == [("job_progress", {"completed": 1})]


def test_start_workflow_job_surfaces_event_handler_failure_as_job_error(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.plugins.runtime_manager.PluginHostSupervisor", _ResponsiveHostSupervisor)
    manager = PluginRuntimeManager(state_root=str((tmp_path / "state").resolve()))
    observed_events: list[tuple[str, dict[str, object]]] = []

    def _on_event(event_type: str, payload):  # type: ignore[no-untyped-def]
        observed_events.append((event_type, dict(payload)))
        raise RuntimeError("event callback failure")

    job = manager.start_workflow_job(
        "cbcs.pytest:pytest",
        {"project_root": "/tmp/project"},
        on_event=_on_event,
    )

    with pytest.raises(RunLifecycleError, match="Workflow job event handler failed"):
        manager.wait_for_workflow_job(job)

    assert observed_events == [("job_progress", {"completed": 1})]
    log_text = open(manager.log_file_path, encoding="utf-8").read()
    assert "Workflow job event handler failed" in log_text
    assert "provider=cbcs.pytest:pytest" in log_text


def test_cancel_workflow_job_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.plugins.runtime_manager.PluginHostSupervisor", _ResponsiveHostSupervisor)
    manager = PluginRuntimeManager()

    result = manager.cancel_workflow_job("job-1")

    assert result == {"job_id": "job-1", "cancel_requested": True}
