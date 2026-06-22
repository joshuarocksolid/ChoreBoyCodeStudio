"""Named clear-console policies for run output vs Python Console display.

UX copy SSOT: ``app.core.clear_console_contract``.
"""

from __future__ import annotations

from typing import Any, Protocol

from app.debug.debug_session import DebugSession


class ClearConsoleHost(Protocol):
    """Host ports for clear-console policy helpers."""

    def console_model(self) -> Any:
        ...

    def run_log_panel(self) -> Any | None:
        ...

    def python_console_widget(self) -> Any | None:
        ...

    def debug_panel(self) -> Any | None:
        ...

    def active_run_output_tail(self) -> Any:
        ...

    def clear_problems(self) -> None:
        ...

    def reset_debug_session(self) -> None:
        ...

    def clear_debug_execution_indicator(self) -> None:
        ...

    def run_log_begin_run(self) -> None:
        ...


def clear_run_output_sinks(host: ClearConsoleHost) -> None:
    """Clear all run-related output sinks (menu Run → Clear Console)."""
    host.console_model().clear()
    run_log_panel = host.run_log_panel()
    if run_log_panel is not None:
        run_log_panel.clear()
    python_console = host.python_console_widget()
    if python_console is not None:
        python_console.clear_console()
    debug_panel = host.debug_panel()
    if debug_panel is not None:
        debug_panel.clear_output()


def clear_python_console_display(host: ClearConsoleHost) -> None:
    """Clear only the in-tab Python Console widget display."""
    python_console = host.python_console_widget()
    if python_console is not None:
        python_console.clear_console()


def prepare_new_run(host: ClearConsoleHost) -> None:
    """Reset output and debug state before starting a new run session."""
    host.active_run_output_tail().clear()
    host.clear_problems()
    host.reset_debug_session()
    host.clear_debug_execution_indicator()
    run_log_panel = host.run_log_panel()
    if run_log_panel is not None:
        host.run_log_begin_run()


class MainWindowClearConsoleHost:
    """Adapts MainWindow private state to :class:`ClearConsoleHost`."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def console_model(self) -> Any:
        return self._window._console_model

    def run_log_panel(self) -> Any | None:
        return self._window._run_log_panel

    def python_console_widget(self) -> Any | None:
        return self._window._python_console_widget

    def debug_panel(self) -> Any | None:
        return self._window._debug_panel

    def active_run_output_tail(self) -> Any:
        return self._window._active_run_output_tail

    def clear_problems(self) -> None:
        self._window._clear_problems()

    def reset_debug_session(self) -> None:
        self._window._debug_session = DebugSession()

    def clear_debug_execution_indicator(self) -> None:
        self._window._debug_inspector_workflow.clear_debug_execution_indicator()

    def run_log_begin_run(self) -> None:
        run_log_panel = self._window._run_log_panel
        if run_log_panel is not None:
            run_log_panel.begin_run()
