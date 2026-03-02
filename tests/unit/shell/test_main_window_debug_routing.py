"""Unit tests for debug-output routing behavior in MainWindow."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.core import constants  # noqa: E402
from app.debug.debug_models import DebugExecutionState, DebugFrame, DebugSessionState  # noqa: E402
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
        self.active_calls: list[bool] = []

    def set_session_active(self, active: bool) -> None:
        self.active_calls.append(active)


class _FakeDebugPanel:
    def __init__(self) -> None:
        self.enabled_calls: list[bool] = []
        self.state_updates: list[DebugSessionState] = []

    def set_command_input_enabled(self, enabled: bool) -> None:
        self.enabled_calls.append(enabled)

    def update_from_state(self, state: DebugSessionState) -> None:
        self.state_updates.append(state)


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


def test_start_session_in_debug_disables_python_console_session_and_enables_debug_input() -> None:
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
    assert python_console.active_calls == [False]
    assert debug_panel.enabled_calls == [True]


def test_apply_debug_inspector_event_ignores_non_project_paused_frame_navigation() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._debug_panel = _FakeDebugPanel()
    window_any._loaded_project = SimpleNamespace(project_root="/tmp/project")
    window_any._debug_execution_editor = None
    window_any._editor_widgets_by_path = {}
    window_any._clear_debug_execution_indicator = lambda: None

    state = DebugSessionState(
        execution_state=DebugExecutionState.PAUSED,
        frames=[
            DebugFrame(
                file_path="/tmp/ide/app/runner/runner_main.py",
                line_number=58,
                function_name="_run_entry_script",
            )
        ],
    )
    window_any._debug_session = SimpleNamespace(state=state)
    open_calls: list[tuple[str, int | None]] = []
    window_any._open_file_at_line = lambda file_path, line_number: open_calls.append((file_path, line_number))

    MainWindow._apply_debug_inspector_event(window)

    assert open_calls == []


def test_handle_debug_navigate_ignores_non_project_file() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._loaded_project = SimpleNamespace(project_root="/tmp/project")
    open_calls: list[tuple[str, int | None]] = []
    window_any._open_file_at_line = lambda file_path, line_number: open_calls.append((file_path, line_number))

    MainWindow._handle_debug_navigate(window, "/tmp/ide/app/shell/main_window.py", 99)

    assert open_calls == []
