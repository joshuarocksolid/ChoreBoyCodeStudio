"""Unit tests for semantic navigation, hover, and signature actions in MainWindow."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.shell.main_window import MainWindow

pytestmark = pytest.mark.unit


class _FakeSemanticWorker:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def submit(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


class _FakeSemanticFacade:
    def __init__(self) -> None:
        self.lookup_definition_calls: list[dict[str, Any]] = []
        self.lookup_definition_result: object = SimpleNamespace(
            found=False,
            symbol_name="helper_task",
            locations=[],
            metadata=SimpleNamespace(unsupported_reason="", source="semantic", confidence="exact"),
        )

    def lookup_definition(self, **kwargs: Any) -> object:
        self.lookup_definition_calls.append(kwargs)
        return self.lookup_definition_result


def _build_window() -> MainWindow:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._loaded_project = SimpleNamespace(project_root="/tmp/project")
    window_any._editor_manager = SimpleNamespace(active_tab=lambda: SimpleNamespace(file_path="/tmp/project/main.py"))
    editor_widget = SimpleNamespace(
        toPlainText=lambda: "from helper import helper_task\nvalue = helper_task()\n",
        textCursor=lambda: SimpleNamespace(position=lambda: 40),
        word_under_cursor=lambda: "helper_task",
        show_calltip=lambda _text: None,
    )
    window_any._active_editor_widget = lambda: editor_widget
    window_any._semantic_worker = _FakeSemanticWorker()
    window_any._semantic_facade = _FakeSemanticFacade()
    window_any._open_file_at_line = lambda *_args, **_kwargs: None
    return window


def test_handle_go_to_definition_action_dispatches_semantic_task() -> None:
    window = _build_window()
    window_any = cast(Any, window)

    MainWindow._handle_go_to_definition_action(window)

    assert len(window_any._semantic_worker.calls) == 1
    worker_call = window_any._semantic_worker.calls[0]
    assert worker_call["key"] == "go_to_definition"

    result = worker_call["task"]()

    assert result is window_any._semantic_facade.lookup_definition_result
    assert window_any._semantic_facade.lookup_definition_calls == [
        {
            "project_root": "/tmp/project",
            "current_file_path": "/tmp/project/main.py",
            "source_text": "from helper import helper_task\nvalue = helper_task()\n",
            "cursor_position": 40,
        }
    ]


def test_handle_go_to_definition_action_uses_target_chooser(monkeypatch: pytest.MonkeyPatch) -> None:
    window = _build_window()
    window_any = cast(Any, window)
    opened: list[tuple[str, int]] = []
    window_any._open_file_at_line = lambda file_path, line_number: opened.append((file_path, line_number))
    window_any._semantic_facade.lookup_definition_result = SimpleNamespace(
        found=True,
        symbol_name="helper_task",
        locations=[
            SimpleNamespace(file_path="/tmp/project/a.py", line_number=3, symbol_kind="function"),
            SimpleNamespace(file_path="/tmp/project/b.py", line_number=8, symbol_kind="function"),
        ],
        metadata=SimpleNamespace(unsupported_reason="", source="semantic", confidence="exact"),
    )
    monkeypatch.setattr(
        "app.shell.main_window.QInputDialog.getItem",
        lambda *_args, **_kwargs: ("b.py:8 (function)", True),
    )

    MainWindow._handle_go_to_definition_action(window)
    worker_call = window_any._semantic_worker.calls[0]

    worker_call["on_success"](window_any._semantic_facade.lookup_definition_result)

    assert opened == [("/tmp/project/b.py", 8)]


def test_signature_help_action_shows_inline_calltip(monkeypatch: pytest.MonkeyPatch) -> None:
    window = _build_window()
    window_any = cast(Any, window)
    shown: list[str] = []
    editor_widget = window_any._active_editor_widget()
    editor_widget.show_calltip = lambda text: shown.append(text)
    monkeypatch.setattr(window, "_build_inline_signature_text", lambda **_kwargs: "helper_task(value)")

    MainWindow._handle_signature_help_action(window)

    assert shown == ["helper_task(value)"]


def test_hover_info_action_shows_inline_calltip(monkeypatch: pytest.MonkeyPatch) -> None:
    window = _build_window()
    window_any = cast(Any, window)
    shown: list[str] = []
    editor_widget = window_any._active_editor_widget()
    editor_widget.show_calltip = lambda text: shown.append(text)
    monkeypatch.setattr(window, "_build_inline_hover_text", lambda **_kwargs: "Symbol: helper_task")

    MainWindow._handle_hover_info_action(window)

    assert shown == ["Symbol: helper_task"]
