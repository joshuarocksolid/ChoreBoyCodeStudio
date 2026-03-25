"""Unit tests for Global History menu wiring."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QMainWindow
import PySide2.QtGui as qt_gui
import PySide2.QtWidgets as qt_widgets

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


def test_global_history_action_is_registered_with_callback(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    calls: list[str] = []
    window = QMainWindow()

    registry = build_menu_stubs(
        window,
        callbacks=MenuCallbacks(on_open_global_history=lambda: calls.append("triggered")),
    )
    action = registry.action("shell.action.file.globalHistory")

    assert action is not None
    assert action.text() == "Open Global History..."

    action.trigger()
    assert calls == ["triggered"]


def test_global_history_action_is_only_in_file_menu(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    window = QMainWindow()
    _ = build_menu_stubs(window, callbacks=MenuCallbacks())

    file_menu = window.findChild(qt_widgets.QMenu, "shell.menu.file")
    edit_menu = window.findChild(qt_widgets.QMenu, "shell.menu.edit")
    assert file_menu is not None
    assert edit_menu is not None

    file_actions = [action for action in file_menu.actions() if action.text() == "Open Global History..."]
    edit_actions = [action for action in edit_menu.actions() if action.text() == "Open Global History..."]

    assert len(file_actions) == 1
    assert len(edit_actions) == 0
