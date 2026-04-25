"""Unit tests for menu shortcut override wiring."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

import PySide2.QtGui as qt_gui
import PySide2.QtWidgets as qt_widgets
from PySide2.QtWidgets import QMainWindow

from app.shell.menus import MenuCallbacks, build_menu_stubs

pytestmark = pytest.mark.unit


@pytest.fixture
def _ensure_qapp(qapp):  # type: ignore[no-untyped-def]
    if not hasattr(qt_widgets, "QActionGroup"):
        qt_widgets.QActionGroup = qt_gui.QActionGroup  # type: ignore[attr-defined]
    return qapp


def test_build_menu_stubs_applies_shortcut_overrides(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    window = QMainWindow()
    registry = build_menu_stubs(
        window.menuBar(),
        callbacks=MenuCallbacks(),
        shortcut_overrides={
            "shell.action.run.run": "Ctrl+R",
            "shell.action.file.save": "",
        },
    )

    run_action = registry.action("shell.action.run.run")
    save_action = registry.action("shell.action.file.save")
    assert run_action is not None
    assert save_action is not None
    assert run_action.shortcut().toString() == "Ctrl+R"
    assert save_action.shortcut().toString() == ""
