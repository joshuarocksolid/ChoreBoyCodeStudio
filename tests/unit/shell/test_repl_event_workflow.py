"""Unit tests for Python Console REPL event routing workflow."""

from __future__ import annotations

import queue
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.shell.repl_event_workflow import ReplEndedEvent, ReplEventWorkflow, ReplOutputEvent  # noqa: E402

pytestmark = pytest.mark.unit


class _FakePythonConsole:
    def __init__(self) -> None:
        self.active_calls: list[bool] = []

    def set_session_active(self, active: bool) -> None:
        self.active_calls.append(active)


class _FakeReplEventHost:
    def __init__(self) -> None:
        self.is_shutting_down = False
        self.repl_event_queue: queue.Queue[ReplOutputEvent | ReplEndedEvent] = queue.Queue()
        self.python_console_widget: _FakePythonConsole | None = _FakePythonConsole()
        self.runtime_introspection_coordinator = SimpleNamespace(clear_cache=lambda: None)
        self.output_lines: list[tuple[str, str]] = []

    def append_python_console_line(self, text: str, stream: str = "stdout") -> None:
        self.output_lines.append((text, stream))

    def log_exception(self, message: str) -> None:
        return None


def _build_workflow() -> tuple[ReplEventWorkflow, _FakeReplEventHost]:
    host = _FakeReplEventHost()
    return ReplEventWorkflow(host), host


def test_process_queued_repl_events_preserves_output_chunks() -> None:
    workflow, host = _build_workflow()
    host.repl_event_queue.put(ReplOutputEvent(text="line one\nline two\n", stream="stdout"))

    workflow.process_queued_events()

    assert host.output_lines == [("line one\nline two\n", "stdout")]


def test_process_queued_repl_events_marks_console_inactive_on_end() -> None:
    workflow, host = _build_workflow()
    fake_console = host.python_console_widget
    assert fake_console is not None
    host.repl_event_queue.put(ReplEndedEvent(return_code=0, terminated_by_user=False))

    workflow.process_queued_events()

    assert fake_console.active_calls == [False]
    assert len(host.output_lines) == 1
    assert host.output_lines[0][1] == "system"
    assert "Python console session ended" in host.output_lines[0][0]
