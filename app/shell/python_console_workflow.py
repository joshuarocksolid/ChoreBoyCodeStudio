"""Python console REPL completion, session control, and async UI orchestration."""

from __future__ import annotations

import threading
from typing import Any, Callable, Protocol

from app.intelligence.completion_context import resolve_completion_prefix
from app.intelligence.completion_models import CompletionEnvelope, CompletionItem
from app.shell.clear_console_policy import (
    ClearConsoleHost,
    MainWindowClearConsoleHost,
    clear_run_output_sinks,
    prepare_new_run,
)

_PYTHON_CONSOLE_FILE_PATH = "<python_console>"


class ReplSessionPort(Protocol):
    """Minimal REPL session surface for submit, interrupt, and restart."""

    @property
    def is_running(self) -> bool:
        ...

    def start(self) -> None:
        ...

    def restart(self) -> None:
        ...

    def send_input(self, text: str) -> None:
        ...


class PythonConsoleBindingPort(Protocol):
    """Minimal Python console widget surface for workflow signal binding."""

    input_submitted: Any
    interrupt_requested: Any
    restart_requested: Any

    def set_completion_requester(self, requester: Callable[..., None]) -> None:
        ...


class ReplCompletionPort(Protocol):
    """Minimal REPL completion surface used by the Python console."""

    def complete(
        self,
        *,
        line_buffer: str,
        cursor_offset: int,
        trigger_kind: str,
        trigger_character: str,
        max_results: int = 100,
    ) -> CompletionEnvelope:
        ...


class ReplManagerPort(ReplSessionPort, ReplCompletionPort, Protocol):
    """Combined REPL session and completion surface for the Python console workflow."""


class PythonConsoleWidgetPort(Protocol):
    """Minimal Python console widget surface for completion results."""

    def show_completion_items_for_request(
        self,
        *,
        request_generation: int,
        prefix: str,
        items: list[CompletionItem],
    ) -> None:
        ...


class PythonConsoleWorkflowHost(Protocol):
    """Typed host surface for Python console async work (not ``window: Any``)."""

    def python_console_widget(self) -> PythonConsoleWidgetPort | None:
        ...

    def dispatch_to_main_thread(self, callback: Callable[[], None]) -> None:
        ...

    def show_status_message(self, message: str, timeout_ms: int) -> None:
        ...

    def focus_python_console_tab(self) -> None:
        ...

    def log_repl_warning(self, message: str, exc: Exception) -> None:
        ...

    def clear_console_host(self) -> ClearConsoleHost:
        ...


class MainWindowPythonConsoleHost:
    """Host ports for ``PythonConsoleWorkflow`` backed by a MainWindow instance."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def python_console_widget(self) -> object | None:
        return self._window._python_console_widget

    def dispatch_to_main_thread(self, callback: Callable[[], None]) -> None:
        self._window._dispatch_to_main_thread(callback)

    def show_status_message(self, message: str, timeout_ms: int) -> None:
        self._window.statusBar().showMessage(message, timeout_ms)

    def focus_python_console_tab(self) -> None:
        bottom_tabs = self._window._bottom_tabs_widget
        container = self._window._python_console_container
        if bottom_tabs is not None and container is not None:
            index = bottom_tabs.indexOf(container)
            if index >= 0:
                bottom_tabs.setCurrentIndex(index)

    def log_repl_warning(self, message: str, exc: Exception) -> None:
        self._window._logger.warning(message, exc)

    def clear_console_host(self) -> MainWindowClearConsoleHost:
        return MainWindowClearConsoleHost(self._window)


BackgroundWorkStarter = Callable[[Callable[[], None]], None]


def _completion_degradation_message(reason: str) -> str:
    if reason == "repl_runtime_inspection":
        return "Python Console completion is using live runtime inspection."
    if reason == "repl_jedi_unavailable":
        return "Python Console semantic completion is unavailable (Jedi not loaded)."
    if reason in {"repl_no_completions", "repl_jedi_fallback"}:
        return "Python Console completion returned no results."
    return f"Python Console completion unavailable: {reason}"


class PythonConsoleWorkflow:
    """Owns Python console REPL session control, completion, and widget binding."""

    def __init__(
        self,
        *,
        repl_manager: ReplManagerPort,
        host: PythonConsoleWorkflowHost,
        start_background_work: BackgroundWorkStarter | None = None,
    ) -> None:
        self._repl_manager = repl_manager
        self._host = host
        self._start_background_work = start_background_work or self._default_start_background_work

    def bind_widget(self, widget: PythonConsoleBindingPort) -> None:
        """Wire console widget signals to workflow-owned handlers."""
        widget.input_submitted.connect(self.handle_submit)
        widget.interrupt_requested.connect(self.handle_interrupt)
        widget.restart_requested.connect(self.handle_start_python_console_action)
        widget.set_completion_requester(self.request_completion_async)

    def handle_start_python_console_action(self) -> bool:
        """Restart the REPL session and focus the Python Console tab."""
        self._repl_manager.restart()
        self._host.focus_python_console_tab()
        return True

    def handle_submit(self, command_text: str) -> None:
        """Send user input to the active REPL session, auto-starting if needed."""
        if not command_text.strip():
            return
        if not self._repl_manager.is_running:
            self._repl_manager.start()
        try:
            self._repl_manager.send_input(command_text)
        except Exception as exc:
            self._host.log_repl_warning("REPL send_input failed: %s", exc)

    def handle_interrupt(self) -> None:
        """Send Ctrl+C to the active REPL session."""
        if not self._repl_manager.is_running:
            return
        try:
            self._repl_manager.send_input("\x03")
        except Exception as exc:
            self._host.log_repl_warning("REPL interrupt failed: %s", exc)

    def handle_clear_console_action(self) -> None:
        """Clear all run-related output sinks (Run menu → Clear Console)."""
        clear_run_output_sinks(self._host.clear_console_host())

    def prepare_for_session_start(self) -> None:
        """Reset output and debug state before starting a new run session."""
        prepare_new_run(self._host.clear_console_host())

    def request_completion_async(
        self,
        line_buffer: str,
        cursor_offset: int,
        request_generation: int,
        trigger_kind: str,
        trigger_character: str,
    ) -> None:
        """Request live Python Console completions off the UI thread."""

        def work() -> None:
            envelope = self._repl_manager.complete(
                line_buffer=line_buffer,
                cursor_offset=cursor_offset,
                trigger_kind=trigger_kind,
                trigger_character=trigger_character,
                max_results=100,
            )
            completion_prefix = resolve_completion_prefix(
                source_text=line_buffer,
                cursor_position=cursor_offset,
                current_file_path=_PYTHON_CONSOLE_FILE_PATH,
                project_root=None,
                trigger_is_manual=trigger_kind == "manual",
                min_prefix_chars=1,
                max_results=100,
                trigger_kind=trigger_kind,
                trigger_character=trigger_character,
            )

            def apply() -> None:
                console_widget = self._host.python_console_widget()
                if console_widget is None:
                    return
                console_widget.show_completion_items_for_request(
                    request_generation=request_generation,
                    prefix=completion_prefix,
                    items=envelope.items,
                )
                if envelope.degradation_reason:
                    message = _completion_degradation_message(envelope.degradation_reason)
                    self._host.show_status_message(message, 4000)

            self._host.dispatch_to_main_thread(apply)

        self._start_background_work(work)

    @staticmethod
    def _default_start_background_work(work: Callable[[], None]) -> None:
        thread = threading.Thread(target=work, daemon=True)
        thread.start()
