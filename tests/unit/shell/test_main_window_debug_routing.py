"""Unit tests for debug-output routing and run/debug shell integration."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.core import constants  # noqa: E402
from app.shell.run_launch.debug_targets import ProjectTarget  # noqa: E402
from app.shell.run_session_controller import RunSessionStartFailureReason, RunSessionStartResult  # noqa: E402
from app.shell.run_session_store import RunSessionStore  # noqa: E402
from app.run.run_service import RunSession  # noqa: E402
from tests.support.shell_host_stubs import (  # noqa: E402
    StubDebugShellHost,
    debug_control_workflow,
    run_launch_workflow_stub,
)

pytestmark = pytest.mark.unit


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
    debug_panel = _FakeDebugPanel()
    workflow, _host = run_launch_workflow_stub(
        _loaded_project=object(),
        _run_session_controller=_FakeRunSessionController(constants.RUN_MODE_PYTHON_DEBUG),
        _debug_panel=debug_panel,
    )

    started = workflow.start_session(mode=constants.RUN_MODE_PYTHON_DEBUG, skip_save=True)

    assert started is True
    assert debug_panel.enabled_calls == [True]


def test_handle_rerun_last_debug_target_replays_project_debug() -> None:
    workflow, _host = run_launch_workflow_stub()
    calls: list[str] = []
    workflow.record_debug_target(ProjectTarget())
    workflow.handle_debug_project_action = lambda: calls.append("project")  # type: ignore[method-assign]

    workflow.handle_rerun_last_debug_target_action()

    assert calls == ["project"]


def test_handle_rerun_last_debug_target_replays_current_test_debug() -> None:
    workflow, host = run_launch_workflow_stub()
    workflow.record_debug_target_from_dict(
        {"kind": "current_test", "target_path": "/tmp/project/test_sample.py"}
    )

    workflow.handle_rerun_last_debug_target_action()

    assert host.open_calls == [("open", "/tmp/project/test_sample.py")]
    assert host.tab_calls == [("tab", 2)]
    assert host.debug_calls == ["current_test"]


def test_start_session_failure_uses_reason_code_for_warning_title(monkeypatch: pytest.MonkeyPatch) -> None:
    workflow, _host = run_launch_workflow_stub(
        _loaded_project=object(),
        _run_session_controller=_FailingRunSessionController(
            RunSessionStartResult(
                started=False,
                failure_reason=RunSessionStartFailureReason.NO_PROJECT,
                error_message="Open something first (legacy wording changed).",
            )
        ),
    )

    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.shell.run_debug_presenter.QMessageBox.warning",
        lambda _parent, title, text: warnings.append((title, text)),
    )

    started = workflow.start_session(mode=constants.RUN_MODE_PYTHON_SCRIPT, skip_save=True)

    assert started is False
    assert warnings == [("Run unavailable", "Open something first (legacy wording changed).")]


def test_start_session_already_running_reason_shows_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    workflow, _host = run_launch_workflow_stub(
        _loaded_project=object(),
        _run_session_controller=_FailingRunSessionController(
            RunSessionStartResult(
                started=False,
                failure_reason=RunSessionStartFailureReason.ALREADY_RUNNING,
                error_message="A run is already in progress. Stop it before starting a new one.",
            )
        ),
    )

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
    host = StubDebugShellHost(_loaded_project=SimpleNamespace(project_root="/tmp/project"))
    workflow = debug_control_workflow(host)

    workflow.handle_debug_navigate_preview("/tmp/ide/app/shell/main_window.py", 99)

    assert host.opened_files == []


def test_handle_debug_navigate_preview_opens_project_file_as_preview() -> None:
    host = StubDebugShellHost(_loaded_project=SimpleNamespace(project_root="/tmp/project"))
    workflow = debug_control_workflow(host)

    workflow.handle_debug_navigate_preview("/tmp/project/app/main.py", 17)

    assert host.opened_files == [("/tmp/project/app/main.py", 17, True)]


def test_handle_debug_navigate_permanent_opens_project_file_as_permanent() -> None:
    host = StubDebugShellHost(_loaded_project=SimpleNamespace(project_root="/tmp/project"))
    workflow = debug_control_workflow(host)

    workflow.handle_debug_navigate_permanent("/tmp/project/app/main.py", 18)

    assert host.opened_files == [("/tmp/project/app/main.py", 18, False)]


def test_release_editor_widget_clears_active_debug_editor_pointer() -> None:
    from app.shell.project_tree_ui_workflow import ProjectTreeUiWorkflow

    editor = _FakeEditorWidget()
    cleared: list[bool] = []

    class _ReleaseEditorHost:
        def __init__(self) -> None:
            self._debug_execution_editor: _FakeEditorWidget | None = editor

        def debug_execution_editor(self) -> _FakeEditorWidget | None:
            return self._debug_execution_editor

        def clear_debug_execution_indicator(self) -> None:
            self._debug_execution_editor = None
            editor.clear_debug_execution_line()
            cleared.append(True)

        def tab_content_registry(self) -> object:
            return SimpleNamespace(
                markdown_registry=lambda: SimpleNamespace(release_widget=lambda _widget: False)
            )

    host = _ReleaseEditorHost()
    workflow = ProjectTreeUiWorkflow(host)  # type: ignore[arg-type]

    workflow.release_editor_widget(editor)

    assert host._debug_execution_editor is None
    assert editor.clear_calls == 1
    assert editor.delete_calls == 1
    assert cleared == [True]
