"""Unit tests for run process event routing workflow."""

from __future__ import annotations

import queue
from types import SimpleNamespace
from typing import Any, cast

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.core import constants  # noqa: E402
from app.debug.debug_session import DebugSession  # noqa: E402
from app.run.problem_parser import ProblemEntry  # noqa: E402
from app.run.process_supervisor import ProcessEvent  # noqa: E402
from app.shell.run_event_workflow import RunEventWorkflow  # noqa: E402
from app.shell.run_launch_workflow import RunLaunchWorkflow  # noqa: E402
from app.shell.run_session_store import ActiveRunSession, RunSessionStore  # noqa: E402

pytestmark = pytest.mark.unit


class _TailBuffer:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def append(self, text: str) -> None:
        self.lines.append(text)

    def text(self) -> str:
        return "".join(self.lines)


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
        self.session_store = RunSessionStore()
        if active_mode:
            self.session_store._active = ActiveRunSession(  # noqa: SLF001 - test fake
                mode=active_mode,
                run_id="run123",
                log_path="/tmp/project/logs/run_run123.log",
                entry_file="run.py",
            )

    @property
    def active_session_mode(self) -> str | None:
        return self.session_store.active_session_mode

    def clear_active_session(self) -> None:
        self.session_store.clear()

    def refresh_action_states(self, *_args, **_kwargs) -> None:
        return None


class _FakeRunEventHost:
    def __init__(self) -> None:
        self.is_shutting_down = False
        self.run_event_queue: queue.Queue[ProcessEvent] = queue.Queue()
        self.run_session_controller = _FakeRunSessionController(constants.RUN_MODE_PYTHON_SCRIPT)
        self.debug_session = DebugSession()
        self.active_run_output_tail = _TailBuffer()
        self.event_bus = SimpleNamespace(publish=lambda _event: None)
        self.active_transient_entry_file_path: str | None = None
        self.run_launch_workflow = cast(RunLaunchWorkflow, SimpleNamespace(delete_transient_entry_file=lambda _path: None))
        self.console_model = SimpleNamespace(append=lambda _stream, _text: None)
        self.run_log_panel = None
        self.latest_run_issue_ids: tuple[str, ...] = ()
        self.latest_run_issue_report = SimpleNamespace(issues=[])
        self.stored_runtime_problems: list[ProblemEntry] = []
        self.auto_open_console_on_run_output = False
        self.auto_open_problems_on_run_failure = False
        self.menu_registry = None
        self.loaded_project = None
        self.debug_control_workflow = SimpleNamespace(breakpoint_store=SimpleNamespace(has_any_breakpoints=lambda: False))
        self.run_service = SimpleNamespace(supervisor=SimpleNamespace(is_running=lambda: False))
        self.run_debug_presenter = SimpleNamespace(execute_pending_restart_if_any=lambda: None)
        self.test_runner_workflow = None
        self.editor_manager = SimpleNamespace(active_tab=lambda: None)
        self.status_controller = None
        self.debug_panel = None
        self.focus_calls: list[str] = []

    def has_active_python_file(self) -> bool:
        return False

    def render_merged_problems_panel(self) -> None:
        return None

    def build_runtime_issue_report(self) -> object:
        return SimpleNamespace(issues=[])

    def open_runtime_center_dialog(self, *, title: str, report: object) -> None:
        return None

    def focus_run_log_tab(self) -> None:
        self.focus_calls.append("run_log")

    def focus_problems_tab(self) -> None:
        self.focus_calls.append("problems")

    def append_debug_output_line(self, text: str) -> None:
        return None

    def apply_debug_inspector_event(self) -> None:
        return None

    def log_exception(self, message: str) -> None:
        return None


def _build_workflow(host: _FakeRunEventHost | None = None) -> tuple[RunEventWorkflow, _FakeRunEventHost]:
    resolved_host = host or _FakeRunEventHost()
    return RunEventWorkflow(cast(Any, resolved_host)), resolved_host


def test_exit_event_clears_session_store() -> None:
    """CC-09: process exit clears RunSessionStore via output coordinator."""
    host = _FakeRunEventHost()
    workflow, host = _build_workflow(host)
    assert host.run_session_controller.session_store.active_session is not None

    workflow.apply_run_event(ProcessEvent(event_type="exit", return_code=0, terminated_by_user=False))

    assert host.run_session_controller.session_store.active_session is None
    assert host.run_session_controller.active_session_mode is None


def test_apply_run_event_routes_debug_output_to_debug_panel_only() -> None:
    host = _FakeRunEventHost()
    host.run_session_controller = _FakeRunSessionController(constants.RUN_MODE_PYTHON_DEBUG)
    workflow, host = _build_workflow(host)

    debug_lines: list[str] = []
    console_lines: list[tuple[str, str]] = []

    host.append_debug_output_line = debug_lines.append  # type: ignore[method-assign]
    workflow.append_console_line = lambda text, stream="stdout": console_lines.append((text, stream))  # type: ignore[method-assign]
    workflow.get_run_output_coordinator = lambda: SimpleNamespace(  # type: ignore[method-assign]
        apply=lambda process_event: (
            workflow.append_console_line(process_event.text or "", stream=process_event.stream or "stdout"),
            host.append_debug_output_line((process_event.text or "").rstrip()),
        )
    )

    workflow.apply_run_event(ProcessEvent(event_type="output", stream="stdout", text="hello-debug\n"))

    assert debug_lines == ["hello-debug"]
    assert console_lines == [("hello-debug\n", "stdout")]


def test_apply_run_event_auto_focuses_run_log_tab_when_enabled() -> None:
    host = _FakeRunEventHost()
    host.auto_open_console_on_run_output = True
    workflow, host = _build_workflow(host)

    console_lines: list[tuple[str, str]] = []
    workflow.append_console_line = lambda text, stream="stdout": console_lines.append((text, stream))  # type: ignore[method-assign]
    run_log_widget = object()
    bottom_tabs = _FakeBottomTabs({run_log_widget: 2})

    workflow.get_run_output_coordinator = lambda: SimpleNamespace(  # type: ignore[method-assign]
        apply=lambda process_event: (
            workflow.append_console_line(process_event.text or "", stream=process_event.stream or "stdout"),
            bottom_tabs.setCurrentIndex(2),
        )
    )

    workflow.apply_run_event(ProcessEvent(event_type="output", stream="stdout", text="hello\n"))

    assert console_lines == [("hello\n", "stdout")]
    assert bottom_tabs.current_index == 2


def test_apply_run_event_focuses_problems_tab_on_failed_exit_when_enabled() -> None:
    host = _FakeRunEventHost()
    host.auto_open_problems_on_run_failure = True
    workflow, host = _build_workflow(host)

    problems_widget = object()
    bottom_tabs = _FakeBottomTabs({problems_widget: 3})
    host.focus_problems_tab = lambda: bottom_tabs.setCurrentIndex(3)  # type: ignore[method-assign]
    workflow.finalize_run_log = lambda return_code=None: None  # type: ignore[method-assign]
    workflow.update_problems_from_output = lambda: [  # type: ignore[method-assign]
        ProblemEntry(
            file_path="/tmp/project/main.py",
            line_number=5,
            context="<module>",
            message="RuntimeError: boom",
        )
    ]

    event = ProcessEvent(event_type="exit", return_code=1, terminated_by_user=False)
    workflow.apply_run_event(event)

    assert bottom_tabs.current_index == 3


def test_apply_run_event_exit_cleans_transient_entry_file() -> None:
    host = _FakeRunEventHost()
    host.active_transient_entry_file_path = "/tmp/transient.py"
    deleted: list[str] = []
    host.run_launch_workflow = cast(  # type: ignore[assignment]
        RunLaunchWorkflow,
        SimpleNamespace(delete_transient_entry_file=deleted.append),
    )
    workflow, host = _build_workflow(host)

    workflow.apply_run_event(ProcessEvent(event_type="exit", return_code=0, terminated_by_user=False))

    assert deleted == ["/tmp/transient.py"]
    assert host.active_transient_entry_file_path is None


def test_apply_run_event_exit_executes_pending_restart() -> None:
    """CC-17 / RUN-R-17: process exit event triggers execute_pending_restart_if_any()."""
    host = _FakeRunEventHost()
    restart_calls: list[str] = []
    host.run_debug_presenter = SimpleNamespace(
        execute_pending_restart_if_any=lambda: restart_calls.append("restart"),
    )
    workflow, _host = _build_workflow(host)

    workflow.apply_run_event(ProcessEvent(event_type="exit", return_code=0, terminated_by_user=False))

    assert restart_calls == ["restart"]


def test_enqueue_run_event_ignored_while_shutting_down() -> None:
    workflow, host = _build_workflow()
    host.is_shutting_down = True

    workflow.enqueue_run_event(ProcessEvent(event_type="state", state="running"))

    assert host.run_event_queue.empty() is True


def test_process_queued_run_events_drains_without_applying_while_shutting_down() -> None:
    workflow, host = _build_workflow()
    host.is_shutting_down = True
    host.run_event_queue.put(ProcessEvent(event_type="state", state="running"))
    host.run_event_queue.put(ProcessEvent(event_type="state", state="exited"))

    applied_events: list[ProcessEvent] = []
    workflow.apply_run_event = lambda event: applied_events.append(event)  # type: ignore[method-assign]

    workflow.process_queued_run_events()

    assert host.run_event_queue.empty() is True
    assert applied_events == []
