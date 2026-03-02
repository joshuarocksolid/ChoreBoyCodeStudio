"""Unit tests for debug-output routing behavior in MainWindow."""

from __future__ import annotations

from typing import Any, cast

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.core import constants  # noqa: E402
from app.debug.debug_session import DebugSession  # noqa: E402
from app.run.process_supervisor import ProcessEvent  # noqa: E402
from app.run.run_service import RunSession  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402
from app.shell.run_session_controller import RunSessionStartResult  # noqa: E402

pytestmark = pytest.mark.unit


class _TailBuffer:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def append(self, text: str) -> None:
        self.lines.append(text)


class _FakePythonConsole:
    def __init__(self) -> None:
        self.locked_calls: list[bool] = []
        self.active_calls: list[bool] = []

    def set_debug_session_locked(self, locked: bool) -> None:
        self.locked_calls.append(locked)

    def set_session_active(self, active: bool) -> None:
        self.active_calls.append(active)


class _FakeDebugPanel:
    def __init__(self) -> None:
        self.enabled_calls: list[bool] = []

    def set_command_input_enabled(self, enabled: bool) -> None:
        self.enabled_calls.append(enabled)


class _FakeRunSessionController:
    def __init__(self, active_mode: str) -> None:
        self.active_session_mode = active_mode

    def start_session(self, **_kwargs):  # type: ignore[no-untyped-def]
        return RunSessionStartResult(
            started=True,
            session=RunSession(
                run_id="run123",
                manifest_path="/tmp/run.json",
                log_file_path="/tmp/run.log",
                project_root="/tmp/project",
                entry_file="run.py",
                mode=self.active_session_mode,
            ),
        )


def test_apply_run_event_routes_debug_output_to_debug_panel_only() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._active_session_mode = constants.RUN_MODE_PYTHON_DEBUG
    window_any._debug_session = DebugSession()
    window_any._active_run_output_tail = _TailBuffer()

    python_console_lines: list[tuple[str, str]] = []
    debug_lines: list[str] = []
    console_lines: list[tuple[str, str]] = []

    window_any._append_python_console_line = (
        lambda text, stream="stdout": python_console_lines.append((text, stream))
    )
    window_any._append_debug_output_line = debug_lines.append
    window_any._append_console_line = (
        lambda text, stream="stdout": console_lines.append((text, stream))
    )

    event = ProcessEvent(event_type="output", stream="stdout", text="hello-debug\n")
    MainWindow._apply_run_event(window, event)

    assert python_console_lines == []
    assert debug_lines == ["hello-debug"]
    assert console_lines == [("hello-debug\n", "stdout")]


def test_start_session_in_debug_locks_python_console_and_enables_debug_input() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._loaded_project = object()
    window_any._run_session_controller = _FakeRunSessionController(constants.RUN_MODE_PYTHON_DEBUG)
    window_any._python_console_widget = _FakePythonConsole()
    window_any._debug_panel = _FakeDebugPanel()
    window_any._handle_save_all_action = lambda: True
    window_any._prepare_for_session_start = lambda: None
    window_any._append_console_line = lambda _text, _stream="stdout": None
    window_any._append_python_console_line = lambda _text, _stream="stdout": None
    window_any._refresh_run_action_states = lambda: None
    window_any._active_run_session_log_path = None

    started = MainWindow._start_session(window, mode=constants.RUN_MODE_PYTHON_DEBUG, skip_save=True)
    python_console = cast(_FakePythonConsole, window_any._python_console_widget)
    debug_panel = cast(_FakeDebugPanel, window_any._debug_panel)

    assert started is True
    assert python_console.locked_calls == [True]
    assert python_console.active_calls == []
    assert debug_panel.enabled_calls == [True]
