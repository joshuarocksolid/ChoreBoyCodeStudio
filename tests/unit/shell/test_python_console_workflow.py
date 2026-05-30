"""Unit tests for Python console async completion workflow."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.intelligence.completion_models import CompletionEnvelope, CompletionItem, CompletionKind  # noqa: E402
from app.shell.python_console_workflow import PythonConsoleWorkflow  # noqa: E402

pytestmark = pytest.mark.unit


@dataclass
class FakeReplManager:
    envelope: CompletionEnvelope = field(
        default_factory=lambda: CompletionEnvelope(items=[], degradation_reason="")
    )
    calls: list[dict[str, object]] = field(default_factory=list)

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


@dataclass
class FakeConsoleWidget:
    shown_generations: list[int] = field(default_factory=list)
    shown_items: list[list[CompletionItem]] = field(default_factory=list)

    def show_completion_items_for_request(
        self,
        *,
        request_generation: int,
        items: list[CompletionItem],
    ) -> None:
        self.shown_generations.append(request_generation)
        self.shown_items.append(list(items))


@dataclass
class FakePythonConsoleHost:
    console_widget: FakeConsoleWidget | None = field(default_factory=FakeConsoleWidget)
    dispatched: list[object] = field(default_factory=list)
    status_messages: list[tuple[str, int]] = field(default_factory=list)

    def python_console_widget(self) -> FakeConsoleWidget | None:
        return self.console_widget

    def dispatch_to_main_thread(self, callback) -> None:  # type: ignore[no-untyped-def]
        self.dispatched.append(callback)
        callback()

    def show_status_message(self, message: str, timeout_ms: int) -> None:
        self.status_messages.append((message, timeout_ms))


def test_request_completion_async_applies_items_on_main_thread() -> None:
    repl = FakeReplManager(
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
    repl = FakeReplManager(
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
    repl = FakeReplManager(
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
    repl = FakeReplManager(
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
    repl = FakeReplManager(
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
