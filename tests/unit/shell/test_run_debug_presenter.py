"""Unit tests for run/debug presenter failure mapping."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.core import constants  # noqa: E402
from app.core.models import LoadedProject, ProjectMetadata  # noqa: E402
from app.shell.run_debug_presenter import RunDebugPresenter  # noqa: E402
from app.shell.run_session_controller import (  # noqa: E402
    RunSessionController,
    RunSessionStartFailureReason,
    RunSessionStartResult,
)

pytestmark = pytest.mark.unit


class _KeywordOnlyConsoleCapture:
    """Mirrors RunEventWorkflow.append_console_line keyword-only stream semantics."""

    def __init__(self) -> None:
        self.lines: list[tuple[str, str]] = []

    def append_console_line(self, text: str, *, stream: str = "stdout") -> None:
        self.lines.append((text, stream))

    def bind_append_console_line(self):
        return lambda text, stream: self.append_console_line(text, stream=stream)


class _FailingRunSessionController:
    def __init__(self, result: RunSessionStartResult) -> None:
        self._result = result

    def start_session(self, **_kwargs: object) -> RunSessionStartResult:
        return self._result


class _PresenterHostStub:
    def __init__(
        self,
        *,
        start_result: RunSessionStartResult | None = None,
        is_running: bool = False,
        active_mode: str | None = None,
        is_shutting_down: bool = False,
    ) -> None:
        self.calls: dict[str, list[str]] = {"stop": [], "run": [], "debug_target": []}
        self._start_result = start_result
        self._is_running = is_running
        self._active_mode = active_mode
        self._is_shutting_down = is_shutting_down

        if start_result is not None:
            self._run_session_controller: Any = _FailingRunSessionController(start_result)
        else:
            calls = self.calls

            class _RunSessionControllerStub:
                active_session_mode = active_mode

                def stop_session(self, append_console_line) -> None:  # type: ignore[no-untyped-def]
                    calls["stop"].append("stop")
                    append_console_line("Stop requested.\n", "system")

            self._run_session_controller = _RunSessionControllerStub()

        console = _KeywordOnlyConsoleCapture()
        self._console = console
        self._run_event_workflow = SimpleNamespace(
            append_console_line=console.append_console_line,
            bind_append_console_line=console.bind_append_console_line,
            set_run_status=lambda _status, return_code=None: self.calls["stop"].append(f"status:{_status}"),
            refresh_run_action_states=lambda: self.calls["stop"].append("refresh"),
        )
        self._repl_event_workflow = SimpleNamespace(
            append_python_console_line=lambda _text, _stream="stdout": None,
        )
        self._save_workflow = SimpleNamespace(handle_save_all_action=lambda: True)
        self._run_service = SimpleNamespace(supervisor=SimpleNamespace(is_running=lambda: self._is_running))
        self._run_launch_workflow = SimpleNamespace(
            handle_run_action=lambda: self.calls["run"].append("run"),
            handle_rerun_last_debug_target_action=lambda: self.calls["debug_target"].append("debug_target"),
        )

    def dialog_parent(self) -> object:
        return None

    def loaded_project(self) -> object:
        return object()

    def run_session_controller(self) -> Any:
        return self._run_session_controller

    def save_workflow(self) -> Any:
        return self._save_workflow

    def prepare_for_session_start(self) -> None:
        return None

    def run_event_workflow(self) -> Any:
        return self._run_event_workflow

    def repl_event_workflow(self) -> Any:
        return self._repl_event_workflow

    def event_bus(self) -> Any:
        return SimpleNamespace(publish=lambda _event: None)

    def debug_panel(self) -> None:
        return None

    def auto_open_console_on_run_output(self) -> bool:
        return False

    def bottom_tabs_widget(self) -> None:
        return None

    def run_log_panel(self) -> None:
        return None

    def run_service(self) -> Any:
        return self._run_service

    def run_launch_workflow(self) -> Any:
        return self._run_launch_workflow

    def is_shutting_down(self) -> bool:
        return self._is_shutting_down


def test_start_session_already_running_shows_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    host = _PresenterHostStub(
        start_result=RunSessionStartResult(
            started=False,
            failure_reason=RunSessionStartFailureReason.ALREADY_RUNNING,
            error_message="Stop the current run first.",
        )
    )
    presenter = RunDebugPresenter(host)

    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.shell.run_debug_presenter.QMessageBox.warning",
        lambda _parent, title, text: warnings.append((title, text)),
    )

    started = presenter.start_session(mode=constants.RUN_MODE_PYTHON_SCRIPT, skip_save=True)

    assert started is False
    assert warnings == [("Run already in progress", "Stop the current run first.")]


def test_restart_while_running_defers_relaunch_until_exit() -> None:
    """CC-17 / RUN-R-17: restart while supervisor running stops first; relaunch waits for exit."""
    host = _PresenterHostStub(is_running=True, active_mode=constants.RUN_MODE_PYTHON_SCRIPT)
    presenter = RunDebugPresenter(host)

    presenter.restart_session()

    assert host.calls["run"] == []
    assert host.calls["debug_target"] == []
    assert "stop" in host.calls["stop"]
    assert "status:stopping" in host.calls["stop"]
    assert host._console.lines == [("Stop requested.\n", "system")]

    presenter.execute_pending_restart_if_any()

    assert host.calls["run"] == ["run"]
    assert host.calls["debug_target"] == []


class _FakeSupervisor:
    def __init__(self) -> None:
        self._running = False

    def is_running(self) -> bool:
        return self._running


class _FakeRunService:
    def __init__(self) -> None:
        self.supervisor = _FakeSupervisor()

    def start_run(self, loaded_project, **kwargs):  # type: ignore[no-untyped-def]
        from app.run.run_service import RunSession

        self.supervisor._running = True
        project_root = loaded_project.project_root if loaded_project is not None else "/tmp/repl"
        return RunSession(
            run_id="run123",
            manifest_path=f"{project_root}/cbcs/runs/run.json",
            log_file_path=f"{project_root}/logs/run_run123.log",
            project_root=project_root,
            entry_file=kwargs.get("entry_file") or "main.py",
            mode=kwargs["mode"],
        )


class _SuccessfulStartHost:
    def __init__(self) -> None:
        self._console = _KeywordOnlyConsoleCapture()
        self._run_event_workflow = SimpleNamespace(
            append_console_line=self._console.append_console_line,
            bind_append_console_line=self._console.bind_append_console_line,
            set_run_status=lambda _status, return_code=None: None,
            refresh_run_action_states=lambda: None,
        )
        self._run_session_controller = RunSessionController(_FakeRunService())  # type: ignore[arg-type]
        self._loaded_project = LoadedProject(
            project_root="/tmp/project",
            manifest_path="/tmp/project/cbcs/project.json",
            metadata=ProjectMetadata(schema_version=1, name="proj"),
            entries=[],
        )

    def dialog_parent(self) -> object:
        return None

    def loaded_project(self) -> LoadedProject:
        return self._loaded_project

    def run_session_controller(self) -> RunSessionController:
        return self._run_session_controller

    def save_workflow(self) -> Any:
        return SimpleNamespace(handle_save_all_action=lambda: True)

    def prepare_for_session_start(self) -> None:
        return None

    def run_event_workflow(self) -> Any:
        return self._run_event_workflow

    def repl_event_workflow(self) -> Any:
        return SimpleNamespace(append_python_console_line=lambda _text: None)

    def event_bus(self) -> Any:
        return SimpleNamespace(publish=lambda _event: None)

    def debug_panel(self) -> None:
        return None

    def auto_open_console_on_run_output(self) -> bool:
        return False

    def bottom_tabs_widget(self) -> None:
        return None

    def run_log_panel(self) -> None:
        return None

    def run_service(self) -> Any:
        return SimpleNamespace(supervisor=SimpleNamespace(is_running=lambda: False))

    def run_launch_workflow(self) -> Any:
        return SimpleNamespace(
            handle_run_action=lambda: None,
            handle_rerun_last_debug_target_action=lambda: None,
        )

    def is_shutting_down(self) -> bool:
        return False


def test_start_session_forwards_positional_console_lines_through_bind_adapter() -> None:
    host = _SuccessfulStartHost()
    presenter = RunDebugPresenter(host)

    started = presenter.start_session(mode=constants.RUN_MODE_PYTHON_SCRIPT, skip_save=True)

    assert started is True
    assert host._console.lines == [
        ("────────────────────\n", "system"),
        ("Starting run...\n", "system"),
        ("Run started (run123)\n", "system"),
    ]


def test_stop_session_forwards_positional_console_lines_through_bind_adapter() -> None:
    host = _PresenterHostStub(is_running=False, active_mode=None)
    presenter = RunDebugPresenter(host)

    presenter.stop_session()

    assert host._console.lines == [("Stop requested.\n", "system")]
    assert "status:stopping" in host.calls["stop"]
    assert "refresh" in host.calls["stop"]


def test_restart_while_idle_relaunches_immediately() -> None:
    host = _PresenterHostStub(is_running=False, active_mode=None)
    presenter = RunDebugPresenter(host)

    presenter.restart_session()

    assert host.calls["run"] == ["run"]
    assert host.calls["stop"] == []


def test_pending_restart_prefers_last_debug_target_mode() -> None:
    host = _PresenterHostStub(is_running=True, active_mode=constants.RUN_MODE_PYTHON_DEBUG)
    presenter = RunDebugPresenter(host)

    presenter.restart_session()
    presenter.execute_pending_restart_if_any()

    assert host.calls["debug_target"] == ["debug_target"]
    assert host.calls["run"] == []


def test_pending_restart_skipped_during_shutdown() -> None:
    host = _PresenterHostStub(
        is_running=True,
        active_mode=constants.RUN_MODE_PYTHON_SCRIPT,
        is_shutting_down=True,
    )
    presenter = RunDebugPresenter(host)

    presenter.restart_session()
    presenter.execute_pending_restart_if_any()

    assert host.calls["run"] == []
