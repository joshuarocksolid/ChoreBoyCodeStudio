"""Unit tests for Quick Open menu wiring."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtCore import Qt
import PySide2.QtWidgets as qt_widgets
import PySide2.QtGui as qt_gui
from PySide2.QtWidgets import QMainWindow

from app.shell.menus import MenuCallbacks, build_menu_stubs

pytestmark = pytest.mark.unit


@pytest.fixture
def _ensure_qapp(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    if not hasattr(qt_widgets, "QActionGroup"):
        qt_widgets.QActionGroup = qt_gui.QActionGroup  # type: ignore[attr-defined]
    app = qt_widgets.QApplication.instance()
    if app is None:
        app = qt_widgets.QApplication([])
    return app


def test_quick_open_action_is_registered_with_callback_and_shortcut(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    calls: list[str] = []
    window = QMainWindow()

    registry = build_menu_stubs(
        window,
        callbacks=MenuCallbacks(on_quick_open=lambda: calls.append("triggered")),
    )
    quick_open_action = registry.action("shell.action.file.quickOpen")

    assert quick_open_action is not None
    assert quick_open_action.text() == "Quick Open..."
    assert quick_open_action.shortcut().toString() == "Ctrl+P"
    assert quick_open_action.shortcutContext() == Qt.ApplicationShortcut

    quick_open_action.trigger()
    assert calls == ["triggered"]


def test_quick_open_action_is_only_in_file_menu(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    window = QMainWindow()
    _ = build_menu_stubs(window, callbacks=MenuCallbacks())

    file_menu = window.findChild(qt_widgets.QMenu, "shell.menu.file")
    edit_menu = window.findChild(qt_widgets.QMenu, "shell.menu.edit")
    assert file_menu is not None
    assert edit_menu is not None

    file_actions = [action for action in file_menu.actions() if action.text() == "Quick Open..."]
    edit_actions = [action for action in edit_menu.actions() if action.text() == "Quick Open..."]

    assert len(file_actions) == 1
    assert len(edit_actions) == 0
