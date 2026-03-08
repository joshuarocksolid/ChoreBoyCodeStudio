"""Unit tests for MainWindow Python Console REPL event routing."""

from __future__ import annotations

import queue
from types import SimpleNamespace
from typing import Any, cast

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.shell.main_window import MainWindow

pytestmark = pytest.mark.unit


class _FakePythonConsole:
    def __init__(self) -> None:
        self.active_calls: list[bool] = []

    def set_session_active(self, active: bool) -> None:
        self.active_calls.append(active)


def _build_window_for_repl_events() -> tuple[MainWindow, list[tuple[str, str]], _FakePythonConsole]:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    output_lines: list[tuple[str, str]] = []
    fake_console = _FakePythonConsole()

    window_any._is_shutting_down = False
    window_any._repl_event_queue = queue.Queue()
    window_any._python_console_widget = fake_console
    window_any._append_python_console_line = (
        lambda text, stream="stdout": output_lines.append((text, stream))
    )
    window_any._logger = SimpleNamespace(exception=lambda *_args, **_kwargs: None)
    return window, output_lines, fake_console


def test_process_queued_repl_events_preserves_output_chunks() -> None:
    window, output_lines, _fake_console = _build_window_for_repl_events()
    cast(Any, window)._repl_event_queue.put(("output", "line one\nline two\n", "stdout"))

    MainWindow._process_queued_repl_events(window)

    assert output_lines == [("line one\nline two\n", "stdout")]


def test_process_queued_repl_events_marks_console_inactive_on_end() -> None:
    window, output_lines, fake_console = _build_window_for_repl_events()
    cast(Any, window)._repl_event_queue.put(("ended", 0, False))

    MainWindow._process_queued_repl_events(window)

    assert fake_console.active_calls == [False]
    assert len(output_lines) == 1
    assert output_lines[0][1] == "system"
    assert "Python console session ended" in output_lines[0][0]

