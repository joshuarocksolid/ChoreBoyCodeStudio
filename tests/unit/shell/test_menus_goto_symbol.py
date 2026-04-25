"""Unit tests for the Go-to-Symbol-in-File menu wiring."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtCore import Qt  # noqa: E402
import PySide2.QtWidgets as qt_widgets  # noqa: E402
import PySide2.QtGui as qt_gui  # noqa: E402
from PySide2.QtWidgets import QMainWindow  # noqa: E402

from app.shell.menus import MenuCallbacks, build_menu_stubs  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture
def _ensure_qapp(qapp):  # type: ignore[no-untyped-def]
    if not hasattr(qt_widgets, "QActionGroup"):
        qt_widgets.QActionGroup = qt_gui.QActionGroup  # type: ignore[attr-defined]
    return qapp


def test_goto_symbol_in_file_action_is_registered(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    calls: list[str] = []
    window = QMainWindow()

    registry = build_menu_stubs(
        window.menuBar(),
        callbacks=MenuCallbacks(on_goto_symbol_in_file=lambda: calls.append("triggered")),
    )
    action = registry.action("shell.action.tools.gotoSymbolInFile")

    assert action is not None
    assert action.text() == "Go to Symbol in File"
    assert action.shortcut().toString() == "Ctrl+R"
    assert action.shortcutContext() == Qt.ApplicationShortcut

    action.trigger()
    assert calls == ["triggered"]


def test_legacy_show_outline_action_no_longer_registered(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    window = QMainWindow()
    registry = build_menu_stubs(window.menuBar(), callbacks=MenuCallbacks())
    assert registry.action("shell.action.tools.showOutline") is None
