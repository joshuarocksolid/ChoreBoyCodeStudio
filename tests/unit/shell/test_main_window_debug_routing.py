"""Unit tests for debug-output routing and run/debug shell integration."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.core import constants  # noqa: E402
from app.shell.debug_control_workflow import DebugControlWorkflow  # noqa: E402
from app.shell.project_tree_ui_workflow import ProjectTreeUiWorkflow  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402
from app.shell.run_debug_presenter import RunDebugPresenter  # noqa: E402
from app.shell.run_launch_workflow import ProjectTarget, RunLaunchWorkflow  # noqa: E402
from app.shell.run_session_controller import RunSessionStartFailureReason, RunSessionStartResult  # noqa: E402
from app.shell.run_session_store import RunSessionStore  # noqa: E402
from app.shell.shell_composition import MainWindowRunLaunchHost  # noqa: E402
from app.run.run_service import RunSession  # noqa: E402

pytestmark = pytest.mark.unit


def _attach_run_launch_workflow(window: MainWindow) -> RunLaunchWorkflow:
    window_any = cast(Any, window)
    window_any._run_debug_presenter = RunDebugPresenter(window)
    workflow = RunLaunchWorkflow(MainWindowRunLaunchHost(window))
    window_any._run_launch_workflow = workflow
    return workflow


def _stub_presenter_dependencies(window_any: Any) -> None:
    window_any._prepare_for_session_start = lambda: None
    window_any._run_event_workflow = SimpleNamespace(
        append_console_line=lambda _text, _stream="stdout": None,
        set_run_status=lambda _status, return_code=None: None,
        refresh_run_action_states=lambda: None,
    )
    window_any._repl_event_workflow = SimpleNamespace(
        append_python_console_line=lambda _text, _stream="stdout": None,
    )
    window_any._auto_open_console_on_run_output = False


class _FakeDebugPanel:
    def __init__(self) -> None:
        self.enabled_calls: list[bool] = []

    def set_command_input_enabled(self, enabled: bool) -> None:
        self.enabled_calls.append(enabled)


class _FakeRunSessionController:
    def __init__(self, active_mode: str) -> None:
        self.session_store = RunSessionStore()
        self.active_session_mode = active_mode

    def start_session(self, **_kwargs):  # type: ignore[no-untyped-def]
        session = RunSession(
            run_id="run123",
            manifest_path="/tmp/run.json",
            log_file_path="/tmp/project/logs/run_run123.log",
            project_root="/tmp/project",
            entry_file="run.py",
            mode=self.active_session_mode or constants.RUN_MODE_PYTHON_SCRIPT,
        )
        self.session_store.start_from_session(session)
        from app.shell.run_session_controller import RunSessionStartResult

        return RunSessionStartResult(started=True, session=session)


class _FailingRunSessionController:
    def __init__(self, result: RunSessionStartResult) -> None:
        self._result = result
        self.session_store = RunSessionStore()
        self.active_session_mode: str | None = None

    def start_session(self, **_kwargs):  # type: ignore[no-untyped-def]
        return self._result


class _FakeEditorWidget:
    def __init__(self) -> None:
        self.clear_calls = 0
        self.delete_calls = 0

    def clear_debug_execution_line(self) -> None:
        self.clear_calls += 1

    def deleteLater(self) -> None:  # noqa: N802 - Qt signature
        self.delete_calls += 1


def test_start_session_in_debug_enables_debug_input() -> None:
    """REPL is managed independently; starting a debug session should only enable the debug panel."""
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._loaded_project = object()
    window_any._run_session_controller = _FakeRunSessionController(constants.RUN_MODE_PYTHON_DEBUG)
    window_any._debug_panel = _FakeDebugPanel()
    window_any._save_workflow = SimpleNamespace(handle_save_all_action=lambda: True)
    _stub_presenter_dependencies(window_any)
    window_any._is_shutting_down = False
    window_any._event_bus = SimpleNamespace(publish=lambda _event: None)
    workflow = _attach_run_launch_workflow(window)

    started = workflow.start_session(mode=constants.RUN_MODE_PYTHON_DEBUG, skip_save=True)
    debug_panel = cast(_FakeDebugPanel, window_any._debug_panel)

    assert started is True
    assert debug_panel.enabled_calls == [True]


def test_handle_rerun_last_debug_target_replays_project_debug() -> None:
    window = MainWindow.__new__(MainWindow)
    workflow = _attach_run_launch_workflow(window)
    calls: list[str] = []
    workflow.record_debug_target(ProjectTarget())
    workflow.handle_debug_project_action = lambda: calls.append("project")  # type: ignore[method-assign]

    workflow.handle_rerun_last_debug_target_action()

    assert calls == ["project"]


def test_handle_rerun_last_debug_target_replays_current_test_debug() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    calls: list[tuple[str, object]] = []
    workflow = _attach_run_launch_workflow(window)
    workflow.record_debug_target_from_dict(
        {"kind": "current_test", "target_path": "/tmp/project/test_sample.py"}
    )
    window_any._editor_tab_factory = SimpleNamespace(
        open_file_in_editor=lambda file_path, preview=False: calls.append(("open", file_path)) or True
    )
    window_any._editor_tabs_widget = SimpleNamespace(setCurrentIndex=lambda index: calls.append(("tab", index)))
    window_any._editor_tab_workflow = SimpleNamespace(tab_index_for_path=lambda _file_path: 2)
    window_any._test_runner_workflow = SimpleNamespace(
        debug_current_file_tests=lambda: calls.append(("debug", "current_test"))
    )

    workflow.handle_rerun_last_debug_target_action()

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
    window_any._save_workflow = SimpleNamespace(handle_save_all_action=lambda: True)
    _stub_presenter_dependencies(window_any)
    workflow = _attach_run_launch_workflow(window)

    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.shell.run_debug_presenter.QMessageBox.warning",
        lambda _parent, title, text: warnings.append((title, text)),
    )

    started = workflow.start_session(mode=constants.RUN_MODE_PYTHON_SCRIPT, skip_save=True)

    assert started is False
    assert warnings == [("Run unavailable", "Open something first (legacy wording changed).")]


def test_start_session_already_running_reason_shows_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._loaded_project = object()
    window_any._run_session_controller = _FailingRunSessionController(
        RunSessionStartResult(
            started=False,
            failure_reason=RunSessionStartFailureReason.ALREADY_RUNNING,
            error_message="A run is already in progress. Stop it before starting a new one.",
        )
    )
    window_any._debug_panel = None
    window_any._save_workflow = SimpleNamespace(handle_save_all_action=lambda: True)
    _stub_presenter_dependencies(window_any)
    workflow = _attach_run_launch_workflow(window)

    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.shell.run_debug_presenter.QMessageBox.warning",
        lambda _parent, title, text: warnings.append((title, text)),
    )

    started = workflow.start_session(mode=constants.RUN_MODE_PYTHON_SCRIPT, skip_save=True)

    assert started is False
    assert warnings == [
        (
            "Run already in progress",
            "A run is already in progress. Stop it before starting a new one.",
        )
    ]


def test_handle_debug_navigate_preview_ignores_non_project_file() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._loaded_project = SimpleNamespace(project_root="/tmp/project")
    open_calls: list[tuple[str, int | None]] = []
    window_any._editor_tab_workflow = SimpleNamespace(
        open_file_at_line=lambda file_path, line_number, preview=False: open_calls.append((file_path, line_number))
    )

    DebugControlWorkflow(window).handle_debug_navigate_preview("/tmp/ide/app/shell/main_window.py", 99)

    assert open_calls == []


def test_handle_debug_navigate_preview_opens_project_file_as_preview() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._loaded_project = SimpleNamespace(project_root="/tmp/project")
    open_calls: list[tuple[str, int | None, bool]] = []
    window_any._editor_tab_workflow = SimpleNamespace(
        open_file_at_line=lambda file_path, line_number, preview=False: open_calls.append(
            (file_path, line_number, preview)
        )
    )

    DebugControlWorkflow(window).handle_debug_navigate_preview("/tmp/project/app/main.py", 17)

    assert open_calls == [("/tmp/project/app/main.py", 17, True)]


def test_handle_debug_navigate_permanent_opens_project_file_as_permanent() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._loaded_project = SimpleNamespace(project_root="/tmp/project")
    open_calls: list[tuple[str, int | None, bool]] = []
    window_any._editor_tab_workflow = SimpleNamespace(
        open_file_at_line=lambda file_path, line_number, preview=False: open_calls.append(
            (file_path, line_number, preview)
        )
    )

    DebugControlWorkflow(window).handle_debug_navigate_permanent("/tmp/project/app/main.py", 18)

    assert open_calls == [("/tmp/project/app/main.py", 18, False)]


def test_release_editor_widget_clears_active_debug_editor_pointer() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    editor = _FakeEditorWidget()
    window_any._debug_execution_editor = editor
    cleared: list[bool] = []

    host = SimpleNamespace(
        debug_execution_editor=lambda: window_any._debug_execution_editor,
        clear_debug_execution_indicator=lambda: (
            setattr(window_any, "_debug_execution_editor", None),
            editor.clear_debug_execution_line(),
            cleared.append(True),
        ),
        markdown_panes_by_path=lambda: {},
    )
    workflow = ProjectTreeUiWorkflow(host)

    workflow.release_editor_widget(editor)

    assert window_any._debug_execution_editor is None
    assert editor.clear_calls == 1
    assert editor.delete_calls == 1
    assert cleared == [True]
