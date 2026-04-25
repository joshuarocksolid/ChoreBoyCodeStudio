"""Unit tests for debug-output routing behavior in MainWindow."""

from __future__ import annotations

from pathlib import Path
import queue
from types import SimpleNamespace
from typing import Any, cast

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.core import constants  # noqa: E402
from app.debug.debug_models import DebugExecutionState, DebugFrame, DebugSessionState  # noqa: E402
from app.debug.debug_session import DebugSession  # noqa: E402
from app.run.problem_parser import ProblemEntry  # noqa: E402
from app.run.process_supervisor import ProcessEvent  # noqa: E402
from app.run.run_service import RunSession  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402
from app.shell.run_session_controller import RunSessionStartFailureReason, RunSessionStartResult  # noqa: E402

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


class _FakeBottomTabs:
    def __init__(self, mapping: dict[object, int]) -> None:
        self._mapping = mapping
        self.current_index: int | None = None

    def indexOf(self, widget: object) -> int:  # noqa: N802 - Qt signature
        return self._mapping.get(widget, -1)

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802 - Qt signature
        self.current_index = index


class _FakeRunSessionController:
    def __init__(self, active_mode: str) -> None:
        self.active_session_mode = active_mode

    def set_active_session_mode(self, mode: str | None) -> None:
        self.active_session_mode = mode

    def clear_active_session_mode(self) -> None:
        self.active_session_mode = None

    def start_session(self, **_kwargs):  # type: ignore[no-untyped-def]
        return RunSessionStartResult(
            started=True,
            session=RunSession(
                run_id="run123",
                manifest_path="/tmp/run.json",
                log_file_path="/tmp/project/logs/run_run123.log",
                project_root="/tmp/project",
                entry_file="run.py",
                mode=self.active_session_mode,
            ),
        )


class _FailingRunSessionController:
    def __init__(self, result: RunSessionStartResult) -> None:
        self._result = result
        self.active_session_mode: str | None = None

    def start_session(self, **_kwargs):  # type: ignore[no-untyped-def]
        return self._result


class _FakeEditorWidget:
    def __init__(self, *, clear_raises: bool = False) -> None:
        self.clear_calls = 0
        self.delete_calls = 0
        self._clear_raises = clear_raises

    def clear_debug_execution_line(self) -> None:
        self.clear_calls += 1
        if self._clear_raises:
            raise RuntimeError("widget already deleted")

    def deleteLater(self) -> None:  # noqa: N802 - Qt signature
        self.delete_calls += 1


def test_apply_run_event_routes_debug_output_to_debug_panel_only() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._run_session_controller = _FakeRunSessionController(constants.RUN_MODE_PYTHON_DEBUG)
    window_any._debug_session = DebugSession()
    window_any._active_run_output_tail = _TailBuffer()
    window_any._is_shutting_down = False

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
    window_any._active_run_session_info = None
    window_any._event_bus = SimpleNamespace(publish=lambda _event: None)
    window_any._get_run_output_coordinator = lambda: SimpleNamespace(
        apply=lambda process_event: (
            window_any._append_console_line(process_event.text or "", stream=process_event.stream or "stdout"),
            window_any._append_debug_output_line((process_event.text or "").rstrip()),
        )
    )

    event = ProcessEvent(event_type="output", stream="stdout", text="hello-debug\n")
    MainWindow._apply_run_event(window, event)

    assert python_console_lines == []
    assert debug_lines == ["hello-debug"]
    assert console_lines == [("hello-debug\n", "stdout")]


def test_apply_run_event_auto_focuses_run_log_tab_when_enabled() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._run_session_controller = _FakeRunSessionController(constants.RUN_MODE_PYTHON_SCRIPT)
    window_any._debug_session = DebugSession()
    window_any._active_run_output_tail = _TailBuffer()
    window_any._is_shutting_down = False
    window_any._auto_open_console_on_run_output = True
    window_any._refresh_run_action_states = lambda: None

    console_lines: list[tuple[str, str]] = []
    window_any._append_console_line = (
        lambda text, stream="stdout": console_lines.append((text, stream))
    )
    window_any._append_debug_output_line = lambda _text: None

    run_log_widget = object()
    window_any._run_log_panel = run_log_widget
    window_any._bottom_tabs_widget = _FakeBottomTabs({run_log_widget: 2})
    window_any._active_run_session_info = None
    window_any._event_bus = SimpleNamespace(publish=lambda _event: None)
    window_any._get_run_output_coordinator = lambda: SimpleNamespace(
        apply=lambda process_event: (
            window_any._append_console_line(process_event.text or "", stream=process_event.stream or "stdout"),
            window_any._bottom_tabs_widget.setCurrentIndex(2),
        )
    )

    event = ProcessEvent(event_type="output", stream="stdout", text="hello\n")
    MainWindow._apply_run_event(window, event)

    assert console_lines == [("hello\n", "stdout")]
    assert window_any._bottom_tabs_widget.current_index == 2


def test_apply_run_event_focuses_problems_tab_on_failed_exit_when_enabled() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._run_session_controller = _FakeRunSessionController(constants.RUN_MODE_PYTHON_SCRIPT)
    window_any._debug_session = DebugSession()
    window_any._is_shutting_down = False
    window_any._auto_open_problems_on_run_failure = True
    window_any._debug_panel = None
    window_any._append_console_line = lambda _text, stream="stdout": None
    window_any._append_debug_output_line = lambda _text: None
    window_any._refresh_run_action_states = lambda: None
    window_any._finalize_run_log = lambda return_code=None: None
    window_any._update_problems_from_output = lambda: [
        ProblemEntry(
            file_path="/tmp/project/main.py",
            line_number=5,
            context="<module>",
            message="RuntimeError: boom",
        )
    ]
    problems_widget = object()
    window_any._problems_panel = problems_widget
    window_any._bottom_tabs_widget = _FakeBottomTabs({problems_widget: 3})
    window_any._active_run_session_info = None
    window_any._event_bus = SimpleNamespace(publish=lambda _event: None)
    window_any._get_run_output_coordinator = lambda: SimpleNamespace(
        apply=lambda process_event: (
            window_any._finalize_run_log(process_event.return_code),
            window_any._update_problems_from_output(),
            window_any._bottom_tabs_widget.setCurrentIndex(3),
        )
    )

    event = ProcessEvent(event_type="exit", return_code=1, terminated_by_user=False)
    MainWindow._apply_run_event(window, event)

    assert window_any._bottom_tabs_widget.current_index == 3


def test_apply_run_event_exit_cleans_transient_entry_file() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._active_run_session_info = None
    window_any._active_transient_entry_file_path = "/tmp/transient.py"
    deleted: list[str] = []
    window_any._delete_transient_entry_file = deleted.append
    window_any._event_bus = SimpleNamespace(publish=lambda _event: None)
    window_any._get_run_output_coordinator = lambda: SimpleNamespace(apply=lambda _event: None)

    MainWindow._apply_run_event(window, ProcessEvent(event_type="exit", return_code=0, terminated_by_user=False))

    assert deleted == ["/tmp/transient.py"]
    assert window_any._active_transient_entry_file_path is None


def test_start_session_in_debug_enables_debug_input() -> None:
    """REPL is managed independently; starting a debug session should only enable the debug panel."""
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._loaded_project = object()
    window_any._run_session_controller = _FakeRunSessionController(constants.RUN_MODE_PYTHON_DEBUG)
    window_any._debug_panel = _FakeDebugPanel()
    window_any._handle_save_all_action = lambda: True
    window_any._prepare_for_session_start = lambda: None
    window_any._append_console_line = lambda _text, _stream="stdout": None
    window_any._append_python_console_line = lambda _text, _stream="stdout": None
    window_any._refresh_run_action_states = lambda: None
    window_any._auto_open_console_on_run_output = False
    window_any._set_run_status = lambda _status: None
    window_any._is_shutting_down = False
    window_any._event_bus = SimpleNamespace(publish=lambda _event: None)

    started = MainWindow._start_session(window, mode=constants.RUN_MODE_PYTHON_DEBUG, skip_save=True)
    debug_panel = cast(_FakeDebugPanel, window_any._debug_panel)

    assert started is True
    assert debug_panel.enabled_calls == [True]


def test_handle_rerun_last_debug_target_replays_project_debug() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    calls: list[str] = []
    window_any._last_debug_target = {"kind": "project"}
    window_any._handle_debug_project_action = lambda: calls.append("project")

    MainWindow._handle_rerun_last_debug_target_action(window)

    assert calls == ["project"]


def test_handle_rerun_last_debug_target_replays_current_test_debug() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    calls: list[tuple[str, object]] = []
    window_any._last_debug_target = {"kind": "current_test", "target_path": "/tmp/project/test_sample.py"}
    window_any._open_file_in_editor = lambda file_path, preview=False: calls.append(("open", file_path)) or True
    window_any._editor_tabs_widget = SimpleNamespace(setCurrentIndex=lambda index: calls.append(("tab", index)))
    window_any._tab_index_for_path = lambda _file_path: 2
    window_any._test_runner_workflow = SimpleNamespace(
        debug_current_file_tests=lambda: calls.append(("debug", "current_test"))
    )

    MainWindow._handle_rerun_last_debug_target_action(window)

    assert calls == [
        ("open", "/tmp/project/test_sample.py"),
        ("tab", 2),
        ("debug", "current_test"),
    ]


def test_start_session_failure_uses_reason_code_for_warning_title(monkeypatch: pytest.MonkeyPatch) -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._loaded_project = object()
    window_any._run_session_controller = _FailingRunSessionController(
        RunSessionStartResult(
            started=False,
            failure_reason=RunSessionStartFailureReason.NO_PROJECT,
            error_message="Open something first (legacy wording changed).",
        )
    )
    window_any._debug_panel = None
    window_any._handle_save_all_action = lambda: True
    window_any._prepare_for_session_start = lambda: None
    window_any._append_console_line = lambda _text, _stream="stdout": None
    window_any._append_python_console_line = lambda _text, _stream="stdout": None
    window_any._refresh_run_action_states = lambda: None
    window_any._auto_open_console_on_run_output = False
    window_any._set_run_status = lambda _status: None

    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.shell.run_debug_presenter.QMessageBox.warning",
        lambda _parent, title, text: warnings.append((title, text)),
    )

    started = MainWindow._start_session(window, mode=constants.RUN_MODE_PYTHON_SCRIPT, skip_save=True)

    assert started is False
    assert warnings == [("Run unavailable", "Open something first (legacy wording changed).")]


def test_start_session_already_running_reason_shows_no_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._loaded_project = object()
    window_any._run_session_controller = _FailingRunSessionController(
        RunSessionStartResult(
            started=False,
            failure_reason=RunSessionStartFailureReason.ALREADY_RUNNING,
        )
    )
    window_any._debug_panel = None
    window_any._handle_save_all_action = lambda: True
    window_any._prepare_for_session_start = lambda: None
    window_any._append_console_line = lambda _text, _stream="stdout": None
    window_any._append_python_console_line = lambda _text, _stream="stdout": None
    window_any._refresh_run_action_states = lambda: None
    window_any._auto_open_console_on_run_output = False
    window_any._set_run_status = lambda _status: None

    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.shell.run_debug_presenter.QMessageBox.warning",
        lambda _parent, title, text: warnings.append((title, text)),
    )

    started = MainWindow._start_session(window, mode=constants.RUN_MODE_PYTHON_SCRIPT, skip_save=True)

    assert started is False
    assert warnings == []


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


def test_handle_debug_navigate_preview_ignores_non_project_file() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._loaded_project = SimpleNamespace(project_root="/tmp/project")
    open_calls: list[tuple[str, int | None]] = []
    window_any._open_file_at_line = lambda file_path, line_number: open_calls.append((file_path, line_number))

    MainWindow._handle_debug_navigate_preview(window, "/tmp/ide/app/shell/main_window.py", 99)

    assert open_calls == []


def test_handle_debug_navigate_preview_opens_project_file_as_preview() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._loaded_project = SimpleNamespace(project_root="/tmp/project")
    open_calls: list[tuple[str, int | None, bool]] = []
    window_any._open_file_at_line = (
        lambda file_path, line_number, preview=False: open_calls.append((file_path, line_number, preview))
    )

    MainWindow._handle_debug_navigate_preview(window, "/tmp/project/app/main.py", 17)

    assert open_calls == [("/tmp/project/app/main.py", 17, True)]


def test_handle_debug_navigate_permanent_opens_project_file_as_permanent() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._loaded_project = SimpleNamespace(project_root="/tmp/project")
    open_calls: list[tuple[str, int | None, bool]] = []
    window_any._open_file_at_line = (
        lambda file_path, line_number, preview=False: open_calls.append((file_path, line_number, preview))
    )

    MainWindow._handle_debug_navigate_permanent(window, "/tmp/project/app/main.py", 18)

    assert open_calls == [("/tmp/project/app/main.py", 18, False)]


def test_enqueue_run_event_ignored_while_shutting_down() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._is_shutting_down = True
    window_any._run_event_queue = queue.Queue()

    MainWindow._enqueue_run_event(window, ProcessEvent(event_type="state", state="running"))

    assert window_any._run_event_queue.empty() is True


def test_process_queued_run_events_drains_without_applying_while_shutting_down() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._is_shutting_down = True
    window_any._run_event_queue = queue.Queue()
    window_any._run_event_queue.put(ProcessEvent(event_type="state", state="running"))
    window_any._run_event_queue.put(ProcessEvent(event_type="state", state="exited"))

    applied_events: list[ProcessEvent] = []
    window_any._apply_run_event = lambda event: applied_events.append(event)

    MainWindow._process_queued_run_events(window)

    assert window_any._run_event_queue.empty() is True
    assert applied_events == []


def test_release_editor_widget_clears_active_debug_editor_pointer() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    editor = _FakeEditorWidget()
    window_any._debug_execution_editor = editor

    MainWindow._release_editor_widget(window, editor)

    assert window_any._debug_execution_editor is None
    assert editor.clear_calls == 1
    assert editor.delete_calls == 1


def test_clear_debug_execution_indicator_handles_deleted_editor_wrapper() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._debug_execution_editor = _FakeEditorWidget(clear_raises=True)

    MainWindow._clear_debug_execution_indicator(window)

    assert window_any._debug_execution_editor is None
