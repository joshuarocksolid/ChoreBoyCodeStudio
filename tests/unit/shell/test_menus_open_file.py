"""Unit tests for Open File menu wiring."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

import PySide2.QtWidgets as qt_widgets
import PySide2.QtGui as qt_gui
from PySide2.QtWidgets import QMainWindow

from app.shell.menus import MenuCallbacks, build_menu_stubs

pytestmark = pytest.mark.unit


@pytest.fixture
def _ensure_qapp(qapp):  # type: ignore[no-untyped-def]
    if not hasattr(qt_widgets, "QActionGroup"):
        qt_widgets.QActionGroup = qt_gui.QActionGroup  # type: ignore[attr-defined]
    return qapp


def test_open_file_action_is_registered_with_callback_and_shortcut(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    calls: list[str] = []
    window = QMainWindow()

    registry = build_menu_stubs(
        window,
        callbacks=MenuCallbacks(on_open_file=lambda: calls.append("triggered")),
    )
    open_file_action = registry.action("shell.action.file.openFile")

    assert open_file_action is not None
    assert open_file_action.text() == "Open File..."
    assert open_file_action.shortcut().toString() == "Ctrl+Shift+O"

    open_file_action.trigger()
    assert calls == ["triggered"]


def test_open_file_action_appears_in_file_menu_after_open_project(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    window = QMainWindow()
    _ = build_menu_stubs(window, callbacks=MenuCallbacks())

    file_menu = window.findChild(qt_widgets.QMenu, "shell.menu.file")
    assert file_menu is not None

    action_texts = [a.text() for a in file_menu.actions()]
    assert "Open File..." in action_texts
    assert "Open Project..." in action_texts

    open_project_idx = action_texts.index("Open Project...")
    open_file_idx = action_texts.index("Open File...")
    assert open_file_idx == open_project_idx + 1
