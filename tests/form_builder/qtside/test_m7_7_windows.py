# pyright: reportAttributeAccessIssue=false
"""Opening a form does not leave a second window beside the shell."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtCore import Qt  # noqa: E402
from app.qt.QtWidgets import QApplication, QWidget  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402
from tests.form_builder.qtside.test_m3_keyboard_scripts import (  # noqa: E402
    Kb,
    _NoMouse,
    _close,
    _open,
    _project,
    _require,
)

pytestmark = [pytest.mark.unit, pytest.mark.timeout(120)]

_FIX = Path(__file__).resolve().parents[1] / "fixtures" / "m7"


def _mapped(window: QWidget, known: list) -> list:
    """New top-levels a window manager would map.

    ``QGraphicsProxyWidget.setWidget`` leaves the form root parentless and sets
    ``WA_DontShowOnScreen``. Offscreen Qt still reports that root visible.
    Parenting or hiding it drops canvas mouse hits and clips the page, so the
    attribute is the contract. A widget with it is not a second window.
    ``known`` is the process's top-levels from earlier tests. Identity is the
    wrapper, not ``id()``, because a deleted wrapper's id gets reused.
    """
    found = []
    for widget in QApplication.topLevelWidgets():
        if widget is window or widget in known:
            continue
        if not widget.isVisible() or widget.width() < 30:
            continue
        if widget.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen):
            continue
        found.append("%s %s" % (type(widget).__name__, widget.objectName()))
    return found


def test_form_logic_and_read_as_text_stay_inside_the_main_window(tmp_path: Path, qapp: QApplication) -> None:
    _require()
    if sys.platform == "darwin":
        from app.qt.QtGui import qt_set_sequence_auto_mnemonic

        qt_set_sequence_auto_mnemonic(True)
    known = list(QApplication.topLevelWidgets())
    root = tmp_path / "shop"
    shutil.copytree(_FIX, root)
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    guard = _NoMouse()
    qapp.installEventFilter(guard)
    try:
        _project(window, root)
        path = root / "forms" / "invoice.ui"
        text = path.read_text(encoding="utf-8")
        surface = _open(window, qapp, path, text)
        surface.focus_primary()
        kb = Kb(window, qapp, surface, path)
        kb.pump()
        page = surface.findChild(QWidget, "formBuilder.canvas").page_widget()  # type: ignore[union-attr]
        assert page is not None
        assert page.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        assert window.isVisible()
        assert _mapped(window, known) == []
        kb.press("Key_1", "Alt")
        kb.pump()
        kb.press("Key_L", "Alt")
        kb.pump()
        read = window.findChild(QWidget, "formBuilder.logic.readAsText")
        if read is not None:
            read.setFocus()
            kb.press("Key_Space")
            kb.pump(8)
        text_page = window.findChild(QWidget, "formBuilder.readAsText")
        assert text_page is not None and not text_page.isWindow()
        logic = window.findChild(QWidget, "formBuilder.logic")
        assert logic is not None and not logic.isWindow()
        assert window.isVisible()
        assert _mapped(window, known) == []
    finally:
        _close(window, qapp, guard)
