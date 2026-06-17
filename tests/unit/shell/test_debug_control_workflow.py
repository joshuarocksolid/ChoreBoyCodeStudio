"""Unit tests for DebugControlWorkflow with a stub shell host."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, cast

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.debug.debug_models import DebugBreakpoint, DebugExceptionPolicy  # noqa: E402
from app.debug.debug_session import DebugSession  # noqa: E402
from app.run.run_service import RunService  # noqa: E402
from app.shell.debug_control_workflow import DebugControlWorkflow  # noqa: E402
from app.shell.debug_shell_host import DebugShellHost  # noqa: E402
from app.shell.run_session_controller import RunSessionController  # noqa: E402
from app.shell.run_session_store import RunSessionStore  # noqa: E402

pytestmark = pytest.mark.unit


@dataclass
class FakeSupervisor:
    running: bool = False

    def is_running(self) -> bool:
        return self.running


@dataclass
class FakeRunService:
    _supervisor: FakeSupervisor = field(default_factory=FakeSupervisor)
    _is_debug_mode: bool = False
    commands: list[tuple[str, dict[str, object] | None]] = field(default_factory=list)

    @property
    def supervisor(self) -> FakeSupervisor:
        return self._supervisor

    @property
    def is_debug_mode(self) -> bool:
        return self._is_debug_mode

    def send_debug_command(self, command_name: str, arguments: dict[str, object] | None = None) -> str:
        self.commands.append((command_name, arguments))
        return "ok"


@dataclass
class FakeDebugPanel:
    breakpoint_updates: list[list[DebugBreakpoint]] = field(default_factory=list)

    def set_breakpoints(self, breakpoints: list[DebugBreakpoint]) -> None:
        self.breakpoint_updates.append(list(breakpoints))


@dataclass
class StubDebugShellHost:
    """Minimal DebugShellHost stub for workflow unit tests."""

    _run_service: FakeRunService = field(default_factory=FakeRunService)
    _debug_session: DebugSession = field(default_factory=DebugSession)
    _run_session_controller: RunSessionController = field(
        default_factory=lambda: RunSessionController(RunService(), RunSessionStore())
    )
    _debug_panel: FakeDebugPanel | None = field(default_factory=FakeDebugPanel)
    _editor_widgets_by_path: dict[str, Any] = field(default_factory=dict)
    _loaded_project: Any | None = None
    _debug_exception_policy: DebugExceptionPolicy = field(
        default_factory=lambda: DebugExceptionPolicy(
            stop_on_uncaught_exceptions=True,
            stop_on_raised_exceptions=False,
        )
    )
    debug_output_lines: list[str] = field(default_factory=list)
    refresh_run_action_calls: int = 0
    opened_files: list[tuple[str, int, bool]] = field(default_factory=list)
    _active_editor: Any | None = None

    def __post_init__(self) -> None:
        self._editor_tab_workflow = SimpleNamespace(
            active_editor_widget=lambda: self._active_editor,
            open_file_at_line=lambda file_path, line_number, preview=False: self.opened_files.append(
                (file_path, line_number, preview)
            ),
        )
        self._debug_inspector_workflow = SimpleNamespace(
            append_debug_output_line=self._append_debug_output_line,
        )
        self._repl_event_workflow = SimpleNamespace(
            append_python_console_line=lambda _text, _stream="stdout": None,
        )
        self._run_event_workflow = SimpleNamespace(
            refresh_run_action_states=lambda: setattr(
                self,
                "refresh_run_action_calls",
                self.refresh_run_action_calls + 1,
            ),
        )

    def _append_debug_output_line(self, text: str) -> None:
        self.debug_output_lines.append(text)


def _workflow(host: StubDebugShellHost) -> DebugControlWorkflow:
    return DebugControlWorkflow(cast(DebugShellHost, host))


def test_send_debug_command_records_transport_and_output() -> None:
    host = StubDebugShellHost()
    host._run_service._supervisor.running = True
    workflow = _workflow(host)

    workflow.send_debug_command("continue", {"thread_id": 1})

    assert host._run_service.commands == [("continue", {"thread_id": 1})]
    assert host.debug_output_lines == ["[debug] continue"]


def test_is_debug_navigation_target_allowed_respects_project_root() -> None:
    host = StubDebugShellHost()
    host._loaded_project = SimpleNamespace(project_root="/tmp/project")
    workflow = _workflow(host)

    assert workflow.is_debug_navigation_target_allowed("/tmp/project/app/main.py") is True
    assert workflow.is_debug_navigation_target_allowed("/tmp/ide/app/main.py") is False


def test_refresh_breakpoints_list_updates_debug_panel() -> None:
    host = StubDebugShellHost()
    panel = host._debug_panel
    assert panel is not None
    workflow = _workflow(host)
    workflow._store.ensure_spec("/tmp/project/main.py", 10)

    workflow.refresh_breakpoints_list()

    assert len(panel.breakpoint_updates) == 1
    assert panel.breakpoint_updates[0][0].file_path == "/tmp/project/main.py"
    assert panel.breakpoint_updates[0][0].line_number == 10


def test_clear_all_breakpoints_clears_store_editors_and_panel_once() -> None:
    host = StubDebugShellHost()
    panel = host._debug_panel
    assert panel is not None
    workflow = _workflow(host)
    workflow._store.ensure_spec("/tmp/project/main.py", 10)
    workflow._store.ensure_spec("/tmp/project/util.py", 3)
    editor_state = {"breakpoints": set()}

    def set_breakpoints(lines: set[int]) -> None:
        editor_state["breakpoints"] = set(lines)

    editor = SimpleNamespace(set_breakpoints=set_breakpoints)
    host._editor_widgets_by_path["/tmp/project/main.py"] = editor
    workflow.refresh_breakpoints_list()
    panel.breakpoint_updates.clear()

    workflow.clear_all_breakpoints()

    assert workflow.all_breakpoints() == []
    assert editor_state["breakpoints"] == set()
    assert len(panel.breakpoint_updates) == 1
    assert panel.breakpoint_updates[0] == []
    assert host.refresh_run_action_calls == 1


def test_handle_remove_all_breakpoints_action_delegates_to_clear_all_breakpoints() -> None:
    host = StubDebugShellHost()
    workflow = _workflow(host)
    workflow._store.ensure_spec("/tmp/project/main.py", 10)

    workflow.handle_remove_all_breakpoints_action()

    assert workflow.all_breakpoints() == []
