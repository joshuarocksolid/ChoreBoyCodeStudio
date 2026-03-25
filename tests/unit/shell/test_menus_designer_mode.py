"""Unit tests for Designer mode menu action wiring."""

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


def test_designer_mode_actions_registered_with_expected_shortcuts(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    calls: list[str] = []
    window = QMainWindow()
    registry = build_menu_stubs(
        window,
        callbacks=MenuCallbacks(
            on_designer_mode_widget=lambda: calls.append("widget"),
            on_designer_mode_signals_slots=lambda: calls.append("signals"),
            on_designer_mode_buddy=lambda: calls.append("buddy"),
            on_designer_mode_tab_order=lambda: calls.append("tab"),
        ),
    )

    widget_mode = registry.action("designer.mode.widget")
    signals_mode = registry.action("designer.mode.signals_slots")
    buddy_mode = registry.action("designer.mode.buddy")
    tab_mode = registry.action("designer.mode.tab_order")

    assert widget_mode is not None and widget_mode.shortcut().toString() == "F3"
    assert signals_mode is not None and signals_mode.shortcut().toString() == "F4"
    assert buddy_mode is not None and buddy_mode.shortcut().toString() == "F5"
    assert tab_mode is not None and tab_mode.shortcut().toString() == "F6"

    widget_mode.trigger()
    signals_mode.trigger()
    buddy_mode.trigger()
    tab_mode.trigger()
    assert calls == ["widget", "signals", "buddy", "tab"]
