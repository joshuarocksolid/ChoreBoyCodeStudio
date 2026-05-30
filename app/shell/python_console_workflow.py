"""Python console REPL completion and async UI orchestration."""

from __future__ import annotations

import threading
from typing import Callable, Protocol

from app.intelligence.completion_models import CompletionEnvelope, CompletionItem


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


class PythonConsoleWidgetPort(Protocol):
    """Minimal Python console widget surface for completion results."""

    def show_completion_items_for_request(
        self,
        *,
        request_generation: int,
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
    """Owns off-thread Python console completion requests and UI apply."""

    def __init__(
        self,
        *,
        repl_manager: ReplCompletionPort,
        host: PythonConsoleWorkflowHost,
        start_background_work: BackgroundWorkStarter | None = None,
    ) -> None:
        self._repl_manager = repl_manager
        self._host = host
        self._start_background_work = start_background_work or self._default_start_background_work

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

            def apply() -> None:
                console_widget = self._host.python_console_widget()
                if console_widget is None:
                    return
                console_widget.show_completion_items_for_request(
                    request_generation=request_generation,
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
