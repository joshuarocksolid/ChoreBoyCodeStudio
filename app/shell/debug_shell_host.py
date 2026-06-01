"""Typed host ports for :class:`DebugControlWorkflow`."""

from __future__ import annotations

from typing import Mapping, Protocol

from app.core.models import LoadedProject
from app.debug.debug_models import DebugBreakpoint, DebugExceptionPolicy
from app.debug.debug_session import DebugSession
from app.shell.run_session_controller import RunSessionController


class DebugProcessSupervisorPort(Protocol):
    """Minimal process supervisor surface for debug transport gating."""

    def is_running(self) -> bool:
        ...


class DebugRunServicePort(Protocol):
    """Minimal run-service surface used by debug control."""

    @property
    def supervisor(self) -> DebugProcessSupervisorPort:
        ...

    @property
    def is_debug_mode(self) -> bool:
        ...

    def send_debug_command(self, command_name: str, arguments: dict[str, object] | None = None) -> str:
        ...


class DebugTextCursorPort(Protocol):
    """Minimal text cursor surface for breakpoint line resolution."""

    def blockNumber(self) -> int:
        ...


class DebugEditorWidgetPort(Protocol):
    """Minimal editor surface for gutter breakpoint actions."""

    def textCursor(self) -> DebugTextCursorPort:
        ...

    def toggle_breakpoint(self, line_number: int) -> None:
        ...

    def set_breakpoints(self, breakpoints: set[int]) -> None:
        ...


class DebugPanelPort(Protocol):
    """Minimal debug panel surface for breakpoint list refresh."""

    def set_breakpoints(self, breakpoints: list[DebugBreakpoint]) -> None:
        ...


class DebugShellHost(Protocol):
    """Host ports for :class:`DebugControlWorkflow` (not ``window: Any``).

    Production hosts (``MainWindow``) are ``QWidget`` subclasses used as dialog
    parents; unit tests may use lightweight stubs without Qt widgets.
    """

    @property
    def _run_service(self) -> DebugRunServicePort:
        ...

    @property
    def _debug_session(self) -> DebugSession:
        ...

    @property
    def _run_session_controller(self) -> RunSessionController:
        ...

    @property
    def _debug_panel(self) -> DebugPanelPort | None:
        ...

    @property
    def _editor_widgets_by_path(self) -> Mapping[str, DebugEditorWidgetPort]:
        ...

    @property
    def _loaded_project(self) -> LoadedProject | None:
        ...

    @property
    def _debug_exception_policy(self) -> DebugExceptionPolicy:
        ...

    @_debug_exception_policy.setter
    def _debug_exception_policy(self, value: DebugExceptionPolicy) -> None:
        ...

    def _append_python_console_line(self, text: str) -> None:
        return None

    def _refresh_run_action_states(self) -> None:
        ...

    def _open_file_at_line(self, file_path: str, line_number: int, *, preview: bool = False) -> None:
        ...

    @property
    def _editor_tab_workflow(self) -> object:
        ...

    @property
    def _debug_inspector_workflow(self) -> object:
        ...

    @property
    def _repl_event_workflow(self) -> object:
        ...

    @property
    def _run_event_workflow(self) -> object:
        ...
