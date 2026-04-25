"""Unit tests for runner debug helper module."""

from __future__ import annotations

import io
from pathlib import Path
import runpy
import sys
from typing import Mapping

import pytest

from app.core import constants
from app.debug.debug_breakpoints import build_breakpoint
from app.debug.debug_models import DebugExceptionPolicy, DebugTransportConfig
from app.run.run_manifest import RunManifest
from app.runner.debug_runner import run_debug_session
from app.runner import output_bridge
from app.runner.output_bridge import redirect_output_to_log

pytestmark = pytest.mark.unit


class _FakeTransport:
    instances: list["_FakeTransport"] = []
    commands_on_stop: list[dict[str, object]] = []

    def __init__(self, _config, *, engine_name: str, on_message, on_error) -> None:  # type: ignore[no-untyped-def]
        self.engine_name = engine_name
        self._on_message = on_message
        self._on_error = on_error
        self.sent_messages: list[dict[str, object]] = []
        type(self).instances.append(self)

    def connect(self) -> None:
        return None

    def send_message(self, message: dict[str, object]) -> None:
        self.sent_messages.append(message)
        if message.get("kind") == "event" and message.get("event") == "stopped":
            commands = type(self).commands_on_stop or [
                {
                    "kind": "command",
                    "command": "continue",
                    "command_id": "cmd_continue",
                    "arguments": {},
                }
            ]
            for command in commands:
                self._on_message(command)

    def close(self) -> None:
        return None


def _build_manifest(tmp_path: Path, *, breakpoints=None, exception_policy: DebugExceptionPolicy | None = None) -> RunManifest:
    return RunManifest(
        manifest_version=constants.RUN_MANIFEST_VERSION,
        run_id="run_debug_test",
        project_root=str(tmp_path.resolve()),
        entry_file="run.py",
        working_directory=str(tmp_path.resolve()),
        log_file=str((tmp_path / "logs" / "run_debug_test.log").resolve()),
        mode=constants.RUN_MODE_PYTHON_DEBUG,
        argv=[],
        env={},
        timestamp="2026-03-01T00:00:00",
        breakpoints=[] if breakpoints is None else list(breakpoints),
        debug_transport=DebugTransportConfig(
            protocol="cb-debug-v1",
            host="127.0.0.1",
            port=9000,
            session_token="token",
        ),
        debug_exception_policy=exception_policy or DebugExceptionPolicy(),
    )


def _event_messages(transport: _FakeTransport, event_name: str) -> list[Mapping[str, object]]:
    events: list[Mapping[str, object]] = []
    for message in transport.sent_messages:
        if message.get("kind") == "event" and message.get("event") == event_name:
            body = message.get("body")
            if isinstance(body, Mapping):
                events.append(body)
    return events


def test_run_debug_session_returns_success_for_clean_script(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script_path = tmp_path / "run.py"
    script_path.write_text("value = 1\n", encoding="utf-8")
    manifest = _build_manifest(tmp_path)
    _FakeTransport.instances.clear()
    monkeypatch.setattr("app.runner.debug_runner.RunnerDebugTransportClient", _FakeTransport)

    def _entry_callable(_path: str) -> None:
        return None

    exit_code = run_debug_session(manifest, _entry_callable, str(script_path.resolve()))

    transport = _FakeTransport.instances[-1]
    assert exit_code == constants.RUN_EXIT_SUCCESS
    assert all(body.get("reason") != "breakpoint" for body in _event_messages(transport, "stopped"))
    assert len(_event_messages(transport, "session_ready")) == 1
    assert len(_event_messages(transport, "session_ended")) == 1


def test_run_debug_session_first_pause_targets_user_breakpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script_path = tmp_path / "run.py"
    script_path.write_text("value = 41\nvalue = value + 1\nprint(value)\n", encoding="utf-8")
    manifest = _build_manifest(
        tmp_path,
        breakpoints=[build_breakpoint(str(script_path.resolve()), 2)],
    )
    _FakeTransport.instances.clear()
    monkeypatch.setattr("app.runner.debug_runner.RunnerDebugTransportClient", _FakeTransport)

    def _entry_callable(path: str) -> None:
        runpy.run_path(path, run_name="__main__")

    exit_code = run_debug_session(manifest, _entry_callable, str(script_path.resolve()))

    transport = _FakeTransport.instances[-1]
    stopped_events = _event_messages(transport, "stopped")
    breakpoint_updates = _event_messages(transport, "breakpoints_updated")

    assert exit_code == constants.RUN_EXIT_SUCCESS
    assert stopped_events
    matching_pause = None
    for stopped_event in stopped_events:
        frames = stopped_event.get("frames", [])
        if not isinstance(frames, list):
            continue
        for frame in frames:
            if not isinstance(frame, Mapping):
                continue
            file_path = frame.get("file_path")
            line_number = frame.get("line_number")
            if (
                isinstance(file_path, str)
                and isinstance(line_number, int)
                and Path(file_path).resolve() == script_path.resolve()
                and line_number == 2
            ):
                matching_pause = stopped_event
                break
        if matching_pause is not None:
            break

    assert matching_pause is not None
    assert breakpoint_updates
    assert breakpoint_updates[0]["breakpoints"][0]["verified"] is True  # type: ignore[index]


def test_run_debug_session_invalid_breakpoint_is_reported_in_breakpoint_update(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script_path = tmp_path / "run.py"
    script_path.write_text("x = 1\nx = x + 1\nprint(x)\n", encoding="utf-8")
    manifest = _build_manifest(
        tmp_path,
        breakpoints=[build_breakpoint(str(script_path.resolve()), 999)],
    )
    _FakeTransport.instances.clear()
    monkeypatch.setattr("app.runner.debug_runner.RunnerDebugTransportClient", _FakeTransport)

    def _entry_callable(path: str) -> None:
        runpy.run_path(path, run_name="__main__")

    exit_code = run_debug_session(manifest, _entry_callable, str(script_path.resolve()))

    transport = _FakeTransport.instances[-1]
    breakpoint_updates = _event_messages(transport, "breakpoints_updated")

    assert exit_code == constants.RUN_EXIT_SUCCESS
    assert breakpoint_updates
    updated_breakpoint = breakpoint_updates[0]["breakpoints"][0]  # type: ignore[index]
    assert updated_breakpoint["verified"] is False
    assert str(updated_breakpoint["verification_message"]).strip()


def test_run_debug_session_updates_breakpoints_without_mutating_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script_path = tmp_path / "run.py"
    script_path.write_text("value = 1\nvalue = value + 1\nprint(value)\n", encoding="utf-8")
    original_breakpoint = build_breakpoint(str(script_path.resolve()), 1)
    replacement_breakpoint = build_breakpoint(str(script_path.resolve()), 2)
    manifest = _build_manifest(tmp_path, breakpoints=[original_breakpoint])
    original_manifest_breakpoints = list(manifest.breakpoints)
    replacement_payload = {
        "breakpoint_id": replacement_breakpoint.breakpoint_id,
        "file_path": replacement_breakpoint.file_path,
        "line_number": replacement_breakpoint.line_number,
        "enabled": replacement_breakpoint.enabled,
        "condition": replacement_breakpoint.condition,
        "hit_condition": replacement_breakpoint.hit_condition,
    }
    _FakeTransport.instances.clear()
    monkeypatch.setattr(
        _FakeTransport,
        "commands_on_stop",
        [
            {
                "kind": "command",
                "command": "update_breakpoints",
                "command_id": "cmd_update_breakpoints",
                "arguments": {"breakpoints": [replacement_payload]},
            },
            {
                "kind": "command",
                "command": "continue",
                "command_id": "cmd_continue",
                "arguments": {},
            },
        ],
    )
    monkeypatch.setattr("app.runner.debug_runner.RunnerDebugTransportClient", _FakeTransport)

    def _entry_callable(path: str) -> None:
        runpy.run_path(path, run_name="__main__")

    exit_code = run_debug_session(manifest, _entry_callable, str(script_path.resolve()))

    transport = _FakeTransport.instances[-1]
    breakpoint_updates = _event_messages(transport, "breakpoints_updated")
    updated_breakpoints = breakpoint_updates[-1].get("breakpoints")
    assert isinstance(updated_breakpoints, list)
    updated_breakpoint = updated_breakpoints[0]
    assert isinstance(updated_breakpoint, Mapping)
    assert exit_code == constants.RUN_EXIT_SUCCESS
    assert updated_breakpoint["breakpoint_id"] == replacement_breakpoint.breakpoint_id
    assert updated_breakpoint["line_number"] == replacement_breakpoint.line_number
    assert manifest.breakpoints == original_manifest_breakpoints


def test_run_debug_session_pauses_on_uncaught_exception_when_enabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script_path = tmp_path / "run.py"
    script_path.write_text("raise ValueError('boom')\n", encoding="utf-8")
    manifest = _build_manifest(
        tmp_path,
        exception_policy=DebugExceptionPolicy(stop_on_uncaught_exceptions=True),
    )
    _FakeTransport.instances.clear()
    monkeypatch.setattr("app.runner.debug_runner.RunnerDebugTransportClient", _FakeTransport)

    def _entry_callable(path: str) -> None:
        runpy.run_path(path, run_name="__main__")

    with pytest.raises(ValueError, match="boom"):
        run_debug_session(manifest, _entry_callable, str(script_path.resolve()))

    transport = _FakeTransport.instances[-1]
    stopped_events = _event_messages(transport, "stopped")

    assert stopped_events
    exception_stop = next((event for event in stopped_events if event.get("reason") == "exception"), None)
    assert exception_stop is not None
    exception_payload = exception_stop.get("exception")
    assert isinstance(exception_payload, Mapping)
    assert exception_payload["type_name"] == "ValueError"


def test_redirect_output_to_log_mirrors_stdout_and_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout_capture)
    monkeypatch.setattr(sys, "stderr", stderr_capture)
    log_path = tmp_path / "logs" / "run.log"

    with redirect_output_to_log(str(log_path)):
        print("STDOUT_MARKER")
        print("STDERR_MARKER", file=sys.stderr)

    log_text = log_path.read_text(encoding="utf-8")
    assert "STDOUT_MARKER" in stdout_capture.getvalue()
    assert "STDERR_MARKER" in stderr_capture.getvalue()
    assert "STDOUT_MARKER" in log_text
    assert "STDERR_MARKER" in log_text


def test_redirect_output_to_log_falls_back_when_log_file_open_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout_capture)
    monkeypatch.setattr(sys, "stderr", stderr_capture)

    def _raise_open_error(_self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise OSError("open denied")

    monkeypatch.setattr(output_bridge.Path, "open", _raise_open_error)

    with redirect_output_to_log(str(tmp_path / "logs" / "run.log")):
        print("FALLBACK_STDOUT")

    assert "FALLBACK_STDOUT" in stdout_capture.getvalue()
    assert "unable to open run log" in stderr_capture.getvalue()
