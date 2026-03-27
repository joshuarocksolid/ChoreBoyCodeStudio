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
            on_designer_layout_align_left=lambda: calls.append("align_left"),
            on_designer_layout_align_hcenter=lambda: calls.append("align_hcenter"),
            on_designer_layout_align_right=lambda: calls.append("align_right"),
            on_designer_layout_align_top=lambda: calls.append("align_top"),
            on_designer_layout_align_vcenter=lambda: calls.append("align_vcenter"),
            on_designer_layout_align_bottom=lambda: calls.append("align_bottom"),
            on_designer_layout_distribute_horizontal=lambda: calls.append("dist_h"),
            on_designer_layout_distribute_vertical=lambda: calls.append("dist_v"),
            on_designer_layout_adjust_size=lambda: calls.append("adjust"),
        ),
    )

    horizontal = registry.action("designer.layout.horizontal")
    vertical = registry.action("designer.layout.vertical")
    grid = registry.action("designer.layout.grid")
    brk = registry.action("designer.layout.break")
    align_left = registry.action("designer.layout.align_left")
    align_hcenter = registry.action("designer.layout.align_hcenter")
    align_right = registry.action("designer.layout.align_right")
    align_top = registry.action("designer.layout.align_top")
    align_vcenter = registry.action("designer.layout.align_vcenter")
    align_bottom = registry.action("designer.layout.align_bottom")
    distribute_horizontal = registry.action("designer.layout.distribute_horizontal")
    distribute_vertical = registry.action("designer.layout.distribute_vertical")
    adjust_size = registry.action("designer.layout.adjust_size")
    assert horizontal is not None
    assert vertical is not None
    assert grid is not None
    assert brk is not None
    assert align_left is not None
    assert align_hcenter is not None
    assert align_right is not None
    assert align_top is not None
    assert align_vcenter is not None
    assert align_bottom is not None
    assert distribute_horizontal is not None
    assert distribute_vertical is not None
    assert adjust_size is not None
    assert horizontal.shortcut().toString() == "Ctrl+1"
    assert vertical.shortcut().toString() == "Ctrl+2"
    assert grid.shortcut().toString() == "Ctrl+3"
    assert brk.shortcut().toString() == "Ctrl+0"
    assert align_left.shortcut().toString() == ""
    assert align_hcenter.shortcut().toString() == ""
    assert align_right.shortcut().toString() == ""
    assert align_top.shortcut().toString() == ""
    assert align_vcenter.shortcut().toString() == ""
    assert align_bottom.shortcut().toString() == ""
    assert distribute_horizontal.shortcut().toString() == ""
    assert distribute_vertical.shortcut().toString() == ""
    assert adjust_size.shortcut().toString() == "Ctrl+J"

    horizontal.trigger()
    vertical.trigger()
    grid.trigger()
    brk.trigger()
    align_left.trigger()
    align_hcenter.trigger()
    align_right.trigger()
    align_top.trigger()
    align_vcenter.trigger()
    align_bottom.trigger()
    distribute_horizontal.trigger()
    distribute_vertical.trigger()
    adjust_size.trigger()
    assert calls == [
        "h",
        "v",
        "g",
        "b",
        "align_left",
        "align_hcenter",
        "align_right",
        "align_top",
        "align_vcenter",
        "align_bottom",
        "dist_h",
        "dist_v",
        "adjust",
    ]
