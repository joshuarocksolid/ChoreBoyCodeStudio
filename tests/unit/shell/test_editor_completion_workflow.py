"""Unit tests for editor completion workflow delivery gates."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.intelligence.completion_models import CompletionItem, CompletionKind, CompletionResolveResult
from app.shell.editor_completion_workflow import EditorCompletionWorkflow

pytestmark = pytest.mark.unit


class _FakeIntelligenceController:
    def __init__(self) -> None:
        self.resolve_calls: list[dict[str, Any]] = []

    def request_completion_resolve(self, **kwargs: Any) -> None:
        self.resolve_calls.append(kwargs)


class _FakeHost:
    def __init__(self, *, editor_widget: object) -> None:
        self._editor_widget = editor_widget
        self._intelligence_controller = _FakeIntelligenceController()

    def loaded_project(self) -> object | None:
        return None

    def intelligence_controller(self) -> _FakeIntelligenceController:
        return self._intelligence_controller

    def editor_buffer_revision(self, file_path: str) -> int | None:
        return 1

    def editor_widget_for_path(self, file_path: str) -> object | None:
        return self._editor_widget

    def log_warning(self, message: str, *args: object) -> None:
        return None


def test_completion_resolve_skips_delivery_when_generation_is_stale() -> None:
    editor_widget = SimpleNamespace(
        completion_request_generation=lambda: 2,
        show_resolved_calls=[],
        show_resolved_completion_item_for_request=lambda **kwargs: editor_widget.show_resolved_calls.append(kwargs),
    )
    host = _FakeHost(editor_widget=editor_widget)
    workflow = EditorCompletionWorkflow(host)

    workflow.request_completion_item_resolve_async(
        file_path="/tmp/a.py",
        editor_widget=editor_widget,
        item=CompletionItem(label="alpha", insert_text="alpha", kind=CompletionKind.SYMBOL),
        source_text="alpha = 1\n",
        cursor_position=0,
        request_generation=1,
    )

    resolve_call = host.intelligence_controller().resolve_calls[0]
    resolve_call["on_success"](
        CompletionResolveResult(
            request_generation=1,
            item=CompletionItem(label="alpha", insert_text="alpha", kind=CompletionKind.SYMBOL, detail="resolved"),
            buffer_revision=1,
            context_fingerprint="",
        )
    )

    assert editor_widget.show_resolved_calls == []
