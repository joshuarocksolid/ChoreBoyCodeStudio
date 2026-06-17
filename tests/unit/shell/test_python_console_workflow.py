"""Unit tests for Python console async completion workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.intelligence.completion_models import CompletionEnvelope, CompletionItem, CompletionKind  # noqa: E402
from app.shell.python_console_workflow import PythonConsoleWorkflow  # noqa: E402

pytestmark = pytest.mark.unit


@dataclass
class FakeConsoleWidget:
    shown_generations: list[int] = field(default_factory=list)
    shown_items: list[list[CompletionItem]] = field(default_factory=list)

    def show_completion_items_for_request(
        self,
        *,
        request_generation: int,
        prefix: str,
        items: list[CompletionItem],
    ) -> None:
        self.shown_generations.append(request_generation)
        self.shown_items.append(list(items))


@dataclass
class FakePythonConsoleHost:
    console_widget: FakeConsoleWidget | None = field(default_factory=FakeConsoleWidget)
    dispatched: list[object] = field(default_factory=list)
    status_messages: list[tuple[str, int]] = field(default_factory=list)
    focused_tab: bool = False
    repl_warnings: list[tuple[str, Exception]] = field(default_factory=list)
    clear_console_calls: int = 0

    def python_console_widget(self) -> FakeConsoleWidget | None:
        return self.console_widget

    def dispatch_to_main_thread(self, callback) -> None:  # type: ignore[no-untyped-def]
        self.dispatched.append(callback)
        callback()

    def show_status_message(self, message: str, timeout_ms: int) -> None:
        self.status_messages.append((message, timeout_ms))

    def focus_python_console_tab(self) -> None:
        self.focused_tab = True

    def log_repl_warning(self, message: str, exc: Exception) -> None:
        self.repl_warnings.append((message, exc))

    def clear_console_host(self) -> FakeClearConsoleHost:
        self.clear_console_calls += 1
        return FakeClearConsoleHost()


@dataclass
class FakeClearConsoleHost:
    cleared: bool = False

    def console_model(self) -> object:
        return SimpleNamespace(clear=lambda: setattr(self, "cleared", True))

    def run_log_panel(self) -> None:
        return None

    def python_console_widget(self) -> None:
        return None

    def debug_panel(self) -> None:
        return None

    def active_run_output_tail(self) -> object:
        return SimpleNamespace(clear=lambda: None)

    def clear_problems(self) -> None:
        return None

    def reset_debug_session(self) -> None:
        return None

    def clear_debug_execution_indicator(self) -> None:
        return None

    def run_log_begin_run(self) -> None:
        return None


@dataclass
class FakeReplSession:
    running: bool = False
    sent_inputs: list[str] = field(default_factory=list)
    restart_count: int = 0
    start_count: int = 0
    envelope: CompletionEnvelope = field(
        default_factory=lambda: CompletionEnvelope(items=[], degradation_reason="")
    )
    calls: list[dict[str, object]] = field(default_factory=list)

    @property
    def is_running(self) -> bool:
        return self.running

    def start(self) -> None:
        self.start_count += 1
        self.running = True

    def restart(self) -> None:
        self.restart_count += 1
        self.running = True

    def send_input(self, text: str) -> None:
        self.sent_inputs.append(text)

    def complete(
        self,
        *,
        line_buffer: str,
        cursor_offset: int,
        trigger_kind: str,
        trigger_character: str,
        max_results: int = 100,
    ) -> CompletionEnvelope:
        self.calls.append(
            {
                "line_buffer": line_buffer,
                "cursor_offset": cursor_offset,
                "trigger_kind": trigger_kind,
                "trigger_character": trigger_character,
                "max_results": max_results,
            }
        )
        return self.envelope


def test_request_completion_async_applies_items_on_main_thread() -> None:
    repl = FakeReplSession(
        envelope=CompletionEnvelope(
            items=[
                CompletionItem(
                    label="print",
                    insert_text="print",
                    kind=CompletionKind.BUILTIN,
                )
            ]
        )
    )
    host = FakePythonConsoleHost()
    workflow = PythonConsoleWorkflow(
        repl_manager=repl,
        host=host,
        start_background_work=lambda work: work(),
    )

    workflow.request_completion_async(
        line_buffer="pri",
        cursor_offset=3,
        request_generation=7,
        trigger_kind="manual",
        trigger_character="",
    )

    assert repl.calls == [
        {
            "line_buffer": "pri",
            "cursor_offset": 3,
            "trigger_kind": "manual",
            "trigger_character": "",
            "max_results": 100,
        }
    ]
    assert host.console_widget is not None
    assert host.console_widget.shown_generations == [7]
    assert len(host.console_widget.shown_items[0]) == 1
    assert host.status_messages == []


def test_request_completion_async_shows_degradation_status() -> None:
    repl = FakeReplSession(
        envelope=CompletionEnvelope(items=[], degradation_reason="repl_unavailable")
    )
    host = FakePythonConsoleHost()
    workflow = PythonConsoleWorkflow(
        repl_manager=repl,
        host=host,
        start_background_work=lambda work: work(),
    )

    workflow.request_completion_async(
        line_buffer="x",
        cursor_offset=1,
        request_generation=1,
        trigger_kind="automatic",
        trigger_character=".",
    )

    assert host.status_messages == [
        ("Python Console completion unavailable: repl_unavailable", 4000)
    ]


def test_request_completion_async_shows_jedi_unavailable_status() -> None:
    repl = FakeReplSession(
        envelope=CompletionEnvelope(items=[], degradation_reason="repl_jedi_unavailable")
    )
    host = FakePythonConsoleHost()
    workflow = PythonConsoleWorkflow(
        repl_manager=repl,
        host=host,
        start_background_work=lambda work: work(),
    )

    workflow.request_completion_async(
        line_buffer="from FreeCAD",
        cursor_offset=len("from FreeCAD"),
        request_generation=1,
        trigger_kind="manual",
        trigger_character="",
    )

    assert host.status_messages == [
        (
            "Python Console semantic completion is unavailable (Jedi not loaded).",
            4000,
        )
    ]


def test_request_completion_async_shows_no_completions_status() -> None:
    repl = FakeReplSession(
        envelope=CompletionEnvelope(items=[], degradation_reason="repl_no_completions")
    )
    host = FakePythonConsoleHost()
    workflow = PythonConsoleWorkflow(
        repl_manager=repl,
        host=host,
        start_background_work=lambda work: work(),
    )

    workflow.request_completion_async(
        line_buffer="from FreeCAD",
        cursor_offset=len("from FreeCAD"),
        request_generation=1,
        trigger_kind="manual",
        trigger_character="",
    )

    assert host.status_messages == [
        ("Python Console completion returned no results.", 4000)
    ]


def test_request_completion_async_skips_apply_when_widget_missing() -> None:
    repl = FakeReplSession(
        envelope=CompletionEnvelope(
            items=[
                CompletionItem(
                    label="value",
                    insert_text="value",
                    kind=CompletionKind.TEXT,
                )
            ],
            degradation_reason="repl_control_unavailable",
        )
    )
    host = FakePythonConsoleHost(console_widget=None)
    workflow = PythonConsoleWorkflow(
        repl_manager=repl,
        host=host,
        start_background_work=lambda work: work(),
    )

    workflow.request_completion_async(
        line_buffer="val",
        cursor_offset=3,
        request_generation=2,
        trigger_kind="manual",
        trigger_character="",
    )

    assert host.status_messages == []


def test_handle_submit_auto_starts_repl_and_sends_input() -> None:
    repl = FakeReplSession(running=False)
    host = FakePythonConsoleHost()
    workflow = PythonConsoleWorkflow(repl_manager=repl, host=host)

    workflow.handle_submit("print(1)")

    assert repl.start_count == 1
    assert repl.sent_inputs == ["print(1)"]


def test_handle_submit_ignores_blank_input() -> None:
    repl = FakeReplSession(running=False)
    host = FakePythonConsoleHost()
    workflow = PythonConsoleWorkflow(repl_manager=repl, host=host)

    workflow.handle_submit("   ")

    assert repl.start_count == 0
    assert repl.sent_inputs == []


def test_handle_interrupt_sends_ctrl_c_when_running() -> None:
    repl = FakeReplSession(running=True)
    host = FakePythonConsoleHost()
    workflow = PythonConsoleWorkflow(repl_manager=repl, host=host)

    workflow.handle_interrupt()

    assert repl.sent_inputs == ["\x03"]


def test_handle_interrupt_noop_when_not_running() -> None:
    repl = FakeReplSession(running=False)
    host = FakePythonConsoleHost()
    workflow = PythonConsoleWorkflow(repl_manager=repl, host=host)

    workflow.handle_interrupt()

    assert repl.sent_inputs == []


def test_handle_start_python_console_action_restarts_and_focuses_tab() -> None:
    repl = FakeReplSession(running=True)
    host = FakePythonConsoleHost()
    workflow = PythonConsoleWorkflow(repl_manager=repl, host=host)

    result = workflow.handle_start_python_console_action()

    assert result is True
    assert repl.restart_count == 1
    assert host.focused_tab is True


def test_handle_submit_logs_warning_on_send_failure() -> None:
    repl = FakeReplSession(running=True)

    def _fail_send(_text: str) -> None:
        raise RuntimeError("broken pipe")

    repl.send_input = _fail_send  # type: ignore[method-assign]
    host = FakePythonConsoleHost()
    workflow = PythonConsoleWorkflow(repl_manager=repl, host=host)

    workflow.handle_submit("x = 1")

    assert len(host.repl_warnings) == 1
    assert "REPL send_input failed" in host.repl_warnings[0][0]


def test_handle_clear_console_action_uses_clear_policy_host() -> None:
    repl = FakeReplSession(running=True)
    host = FakePythonConsoleHost()
    workflow = PythonConsoleWorkflow(repl_manager=repl, host=host)

    workflow.handle_clear_console_action()

    assert host.clear_console_calls == 1
