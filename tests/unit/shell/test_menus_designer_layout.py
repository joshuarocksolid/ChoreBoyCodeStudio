"""Unit tests for Designer layout menu action wiring."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

import PySide2.QtGui as qt_gui
import PySide2.QtWidgets as qt_widgets
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


def test_designer_layout_actions_are_registered_with_shortcuts(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    calls: list[str] = []
    window = QMainWindow()
    registry = build_menu_stubs(
        window,
        callbacks=MenuCallbacks(
            on_designer_layout_horizontal=lambda: calls.append("h"),
            on_designer_layout_vertical=lambda: calls.append("v"),
            on_designer_layout_grid=lambda: calls.append("g"),
            on_designer_layout_break=lambda: calls.append("b"),
        ),
    )

    horizontal = registry.action("designer.layout.horizontal")
    vertical = registry.action("designer.layout.vertical")
    grid = registry.action("designer.layout.grid")
    brk = registry.action("designer.layout.break")
    assert horizontal is not None
    assert vertical is not None
    assert grid is not None
    assert brk is not None
    assert horizontal.shortcut().toString() == "Ctrl+1"
    assert vertical.shortcut().toString() == "Ctrl+2"
    assert grid.shortcut().toString() == "Ctrl+3"
    assert brk.shortcut().toString() == "Ctrl+0"

    horizontal.trigger()
    vertical.trigger()
    grid.trigger()
    brk.trigger()
    assert calls == ["h", "v", "g", "b"]
