"""Unit tests for shell menu registry IDs."""

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


def test_menu_registry_includes_top_level_shell_menu_ids(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    window = QMainWindow()
    registry = build_menu_stubs(window, callbacks=MenuCallbacks())

    assert registry.menu("shell.menu.file") is not None
    assert registry.menu("shell.menu.edit") is not None
    assert registry.menu("shell.menu.run") is not None
    assert registry.menu("shell.menu.view") is not None
    assert registry.menu("shell.menu.tools") is not None
    assert registry.menu("shell.menu.help") is not None
    assert registry.menu("shell.menu.file.openRecent") is not None
    assert registry.menu("shell.menu.view.theme") is not None


def test_tools_menu_registers_highlighting_actions(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    window = QMainWindow()
    registry = build_menu_stubs(window, callbacks=MenuCallbacks())

    assert registry.action("shell.action.tools.setLanguageMode") is not None
    assert registry.action("shell.action.tools.clearLanguageOverride") is not None
    assert registry.action("shell.action.tools.inspectToken") is not None
    assert registry.action("shell.action.tools.dependencyInspector") is not None
    assert registry.action("shell.action.tools.addDependency") is not None


def test_view_menu_registers_test_explorer_action(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    window = QMainWindow()
    registry = build_menu_stubs(window, callbacks=MenuCallbacks())

    action = registry.action("shell.action.view.showTestExplorer")
    assert action is not None
    assert action.text() == "Show Test Explorer"

