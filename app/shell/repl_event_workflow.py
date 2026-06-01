"""Python Console REPL event queue processing."""

from __future__ import annotations

import queue
from typing import Any, Callable, Protocol

from app.shell.exit_status import describe_exit_code

EVENT_QUEUE_BATCH_LIMIT = 200

ReplEvent = tuple[str, object, object]


class ReplPythonConsolePort(Protocol):
    """Minimal Python console widget surface for session lifecycle."""

    def set_session_active(self, active: bool) -> None:
        ...


class ReplRuntimeIntrospectionPort(Protocol):
    """Minimal runtime introspection surface cleared on REPL start."""

    def clear_cache(self) -> None:
        ...


class ReplEventWorkflowHost(Protocol):
    """Host ports for :class:`ReplEventWorkflow`."""

    @property
    def is_shutting_down(self) -> bool:
        ...

    @property
    def repl_event_queue(self) -> queue.Queue[ReplEvent]:
        ...

    @property
    def python_console_widget(self) -> ReplPythonConsolePort | None:
        ...

    @property
    def runtime_introspection_coordinator(self) -> ReplRuntimeIntrospectionPort:
        ...

    def append_python_console_line(self, text: str, stream: str = "stdout") -> None:
        ...

    def log_exception(self, message: str) -> None:
        ...


class ReplEventWorkflow:
    """Owns REPL output/session event queue draining (separate from script/debug runs)."""

    def __init__(self, host: ReplEventWorkflowHost) -> None:
        self._host = host

    def enqueue_output(self, text: str, stream: str) -> None:
        if self._host.is_shutting_down:
            return
        self._host.repl_event_queue.put(("output", text, stream))

    def enqueue_ended(self, return_code: int | None, terminated_by_user: bool) -> None:
        if self._host.is_shutting_down:
            return
        self._host.repl_event_queue.put(("ended", return_code, terminated_by_user))

    def enqueue_started(self) -> None:
        if self._host.is_shutting_down:
            return
        self._host.repl_event_queue.put(("started", None, False))

    def process_queued_events(self) -> None:
        if self._host.is_shutting_down:
            return
        processed = 0
        while processed < EVENT_QUEUE_BATCH_LIMIT:
            try:
                item = self._host.repl_event_queue.get_nowait()
            except queue.Empty:
                break
            try:
                kind, arg1, arg2 = item
                if kind == "output":
                    text: str = arg1  # type: ignore[assignment]
                    stream: str = arg2  # type: ignore[assignment]
                    if text:
                        self._host.append_python_console_line(text, stream=stream)
                elif kind == "started":
                    self._host.runtime_introspection_coordinator.clear_cache()
                    console = self._host.python_console_widget
                    if console is not None:
                        console.set_session_active(True)
                elif kind == "ended":
                    return_code: int | None = arg1  # type: ignore[assignment]
                    terminated_by_user: bool = arg2  # type: ignore[assignment]
                    console = self._host.python_console_widget
                    if console is not None:
                        console.set_session_active(False)
                    if not terminated_by_user:
                        exit_detail = describe_exit_code(return_code)
                        if return_code is not None and return_code < 0:
                            self._host.append_python_console_line(
                                f"[system] Python console process was terminated by {exit_detail}. "
                                "The script may have crashed in native code.",
                                stream="system",
                            )
                        else:
                            self._host.append_python_console_line(
                                f"[system] Python console session ended ({exit_detail}).",
                                stream="system",
                            )
            except Exception:
                self._host.log_exception("Failed to process Python Console event")
            processed += 1

    def append_python_console_line(self, text: str, stream: str = "stdout") -> None:
        self._host.append_python_console_line(text, stream)


class MainWindowReplEventHost:
    """Adapts :class:`MainWindow` to :class:`ReplEventWorkflowHost`."""

    def __init__(self, window: Any) -> None:
        self._window = window

    @property
    def is_shutting_down(self) -> bool:
        return self._window._is_shutting_down

    @property
    def repl_event_queue(self) -> queue.Queue[ReplEvent]:
        return self._window._repl_event_queue

    @property
    def python_console_widget(self) -> ReplPythonConsolePort | None:
        return self._window._python_console_widget

    @property
    def runtime_introspection_coordinator(self) -> ReplRuntimeIntrospectionPort:
        return self._window._runtime_introspection_coordinator

    def append_python_console_line(self, text: str, stream: str = "stdout") -> None:
        widget = self._window._python_console_widget
        if widget is not None:
            widget.append_output(text, stream)

    def log_exception(self, message: str) -> None:
        self._window._logger.exception(message)
