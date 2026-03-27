"""Unit tests for Edit menu action wiring."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

import PySide2.QtGui as qt_gui
import PySide2.QtWidgets as qt_widgets
from PySide2.QtWidgets import QMainWindow

from app.shell.menus import MenuCallbacks, build_menu_stubs
from app.shell.shortcut_preferences import default_shortcut_map

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


def test_edit_actions_registered_with_shortcuts_and_callbacks(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    calls: list[str] = []
    window = QMainWindow()
    registry = build_menu_stubs(
        window,
        callbacks=MenuCallbacks(
            on_cut=lambda: calls.append("cut"),
            on_copy=lambda: calls.append("copy"),
            on_paste=lambda: calls.append("paste"),
        ),
    )
    cut_action = registry.action("shell.action.edit.cut")
    copy_action = registry.action("shell.action.edit.copy")
    paste_action = registry.action("shell.action.edit.paste")

    assert cut_action is not None
    assert copy_action is not None
    assert paste_action is not None
    assert cut_action.shortcut().toString() == "Ctrl+X"
    assert copy_action.shortcut().toString() == "Ctrl+C"
    assert paste_action.shortcut().toString() == "Ctrl+V"

    cut_action.trigger()
    copy_action.trigger()
    paste_action.trigger()

    assert calls == ["cut", "copy", "paste"]


def test_default_shortcut_map_includes_edit_clipboard_actions() -> None:
    defaults = default_shortcut_map()
    assert defaults["shell.action.edit.cut"] == "Ctrl+X"
    assert defaults["shell.action.edit.copy"] == "Ctrl+C"
    assert defaults["shell.action.edit.paste"] == "Ctrl+V"
