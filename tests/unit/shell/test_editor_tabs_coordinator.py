"""Unit tests for EditorTabsCoordinator editor text action routing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

from app.shell.editor_tabs_coordinator import EditorTabsCoordinator


@dataclass
class _FakeTabState:
    file_path: str
    display_name: str = "main.py"
    is_dirty: bool = False
    is_preview: bool = False


@dataclass
class _FakeEditorManager:
    active_tab_state: _FakeTabState | None = None

    def active_tab(self) -> _FakeTabState | None:
        return self.active_tab_state


@dataclass
class _FakeEditorWidget:
    calls: list[str] = field(default_factory=list)

    def toggle_comment_selection(self) -> None:
        self.calls.append("toggle_comment")

    def indent_selection(self) -> None:
        self.calls.append("indent")

    def outdent_selection(self) -> None:
        self.calls.append("outdent")


@dataclass
class _FakeWindow:
    _editor_manager: _FakeEditorManager
    _editor_widgets_by_path: dict[str, _FakeEditorWidget]


def test_handle_toggle_comment_delegates_to_active_editor() -> None:
    tab = _FakeTabState(file_path="/tmp/main.py")
    editor = _FakeEditorWidget()
    window = _FakeWindow(
        _editor_manager=_FakeEditorManager(active_tab_state=tab),
        _editor_widgets_by_path={tab.file_path: editor},
    )
    coordinator = EditorTabsCoordinator(window)

    coordinator.handle_toggle_comment_action()

    assert editor.calls == ["toggle_comment"]


def test_handle_indent_noops_when_no_active_editor() -> None:
    window = _FakeWindow(
        _editor_manager=_FakeEditorManager(active_tab_state=None),
        _editor_widgets_by_path={},
    )
    coordinator = EditorTabsCoordinator(window)

    coordinator.handle_indent_action()

    assert window._editor_widgets_by_path == {}


def test_handle_outdent_delegates_to_active_editor() -> None:
    tab = _FakeTabState(file_path="/tmp/other.py")
    editor = _FakeEditorWidget()
    window = _FakeWindow(
        _editor_manager=_FakeEditorManager(active_tab_state=tab),
        _editor_widgets_by_path={tab.file_path: editor},
    )
    coordinator = EditorTabsCoordinator(window)

    coordinator.handle_outdent_action()

    assert editor.calls == ["outdent"]
