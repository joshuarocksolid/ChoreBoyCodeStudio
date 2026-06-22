"""Unit tests for outline async refresh and AD-018 stale delivery gates."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.intelligence.outline_service import OutlineSymbol
from app.shell.editor_tab_outline_workflow import EditorTabOutlineWorkflow

pytestmark = pytest.mark.unit


class _FakeBackgroundTasks:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def run(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


class _FakeOutlinePanel:
    def __init__(self) -> None:
        self.outline_calls: list[tuple[tuple[OutlineSymbol, ...], str]] = []

    def set_outline(self, symbols: tuple[OutlineSymbol, ...], file_path: str) -> None:
        self.outline_calls.append((symbols, file_path))

    def highlight_symbol_at_line(self, line_number: int) -> None:
        return None

    def set_unsupported_language(self, language: str) -> None:
        return None


class _FakeHost:
    def __init__(self) -> None:
        self._outline_panel = _FakeOutlinePanel()
        self._outline_symbols_by_path: dict[str, tuple[OutlineSymbol, ...]] = {}
        self._background_tasks = _FakeBackgroundTasks()
        self._outline_follow_cursor = False
        self._buffer_revision = 1

    def outline_panel(self) -> _FakeOutlinePanel:
        return self._outline_panel

    def outline_symbols_by_path(self) -> dict[str, tuple[OutlineSymbol, ...]]:
        return self._outline_symbols_by_path

    def outline_follow_cursor(self) -> bool:
        return self._outline_follow_cursor

    def background_tasks(self) -> _FakeBackgroundTasks:
        return self._background_tasks

    def start_outline_refresh_timer(self) -> None:
        return None

    def stop_outline_refresh_timer(self) -> None:
        return None


def _sample_symbols() -> tuple[OutlineSymbol, ...]:
    return (
        OutlineSymbol(
            name="alpha",
            qualified_name="alpha",
            kind="function",
            line_number=1,
            end_line_number=1,
            children=(),
        ),
    )


def test_outline_refresh_skips_panel_update_when_revision_is_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _FakeHost()
    editor_widget = SimpleNamespace(
        toPlainText=lambda: "def alpha():\n    pass\n",
        textCursor=lambda: SimpleNamespace(blockNumber=lambda: 0),
    )
    editor_manager = SimpleNamespace(
        active_tab=lambda: SimpleNamespace(
            file_path="/tmp/project/main.py",
            current_content="def alpha():\n    pass\n",
        )
    )

    workflow = EditorTabOutlineWorkflow(
        host=host,
        editor_manager=editor_manager,
        editor_widgets_by_path=lambda: {"/tmp/project/main.py": editor_widget},
        editor_tab_factory=SimpleNamespace(open_file_in_editor=lambda *_a, **_kw: True),
        buffer_revision=lambda _path: host._buffer_revision,
    )
    monkeypatch.setattr(
        "app.shell.editor_tab_outline_workflow.build_outline_from_source",
        lambda _source: _sample_symbols(),
    )

    workflow.refresh_for_active_tab()
    background_call = host.background_tasks().calls[0]
    host._buffer_revision = 2
    background_call["on_success"](_sample_symbols())

    assert host.outline_panel().outline_calls == []
    assert host.outline_symbols_by_path() == {}


def test_outline_refresh_updates_panel_when_revision_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _FakeHost()
    editor_widget = SimpleNamespace(
        toPlainText=lambda: "def alpha():\n    pass\n",
        textCursor=lambda: SimpleNamespace(blockNumber=lambda: 0),
    )
    editor_manager = SimpleNamespace(
        active_tab=lambda: SimpleNamespace(
            file_path="/tmp/project/main.py",
            current_content="def alpha():\n    pass\n",
        )
    )
    symbols = _sample_symbols()

    workflow = EditorTabOutlineWorkflow(
        host=host,
        editor_manager=editor_manager,
        editor_widgets_by_path=lambda: {"/tmp/project/main.py": editor_widget},
        editor_tab_factory=SimpleNamespace(open_file_in_editor=lambda *_a, **_kw: True),
        buffer_revision=lambda _path: host._buffer_revision,
    )
    monkeypatch.setattr(
        "app.shell.editor_tab_outline_workflow.build_outline_from_source",
        lambda _source: symbols,
    )

    workflow.refresh_for_active_tab()
    background_call = host.background_tasks().calls[0]
    background_call["on_success"](symbols)

    assert host.outline_panel().outline_calls == [(symbols, "/tmp/project/main.py")]
    assert host.outline_symbols_by_path()["/tmp/project/main.py"] == symbols
