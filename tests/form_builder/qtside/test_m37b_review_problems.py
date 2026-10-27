# pyright: reportAttributeAccessIssue=false
"""Opus gate repros for M3.7b: Problems double click on a form row with a widget."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.qt.QtWidgets import QApplication, QWidget
from testing.main_window_shutdown import shutdown_main_window_for_test
from tests.form_builder.qtside.test_problem_click_and_insert import (
    _DUPLICATE,
    _button,
    _mod,
    _open,
    _problems_focus,
    _require,
    _row,
    _selected_name,
    _show_problems,
    _window,
    _xml_checked,
)
from app.qt.QtTest import QTest

pytestmark = pytest.mark.unit


def test_double_click_on_a_form_problem_with_a_widget_activates_it(tmp_path: Path, qapp: QApplication) -> None:
    # Drive the double click through the QWindow so Qt makes the double click
    # itself. QTest.mouseDClick on the viewport after a click is not reliable on
    # Qt 6; that, not a deleted row, is why the M3.7b test needed a retry loop.
    _require()
    window = _window(tmp_path)
    try:
        surface = _open(window, qapp, tmp_path / "invoice.ui", _DUPLICATE)
        tree = _show_problems(window, qapp)
        tree.scrollToItem(_row(tree, "okButton"))
        qapp.processEvents()
        item = _row(tree, "okButton")
        panel = window._problems_panel
        assert panel is not None
        fired = []
        panel.item_activated.connect(lambda path, line: fired.append(line))
        pos = tree.viewport().mapTo(window, tree.visualItemRect(item).center())
        handle = window.windowHandle()
        QTest.mouseClick(handle, _button(), _mod("NoModifier"), pos)
        assert not _xml_checked(surface)
        QTest.mouseDClick(handle, _button(), _mod("NoModifier"), pos)
        qapp.processEvents()
        qapp.processEvents()
        assert fired, "double click did not activate the row"
        assert not _xml_checked(surface)
        assert _selected_name(surface) == "okButton"
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_single_click_in_xml_view_keeps_focus_in_problems(tmp_path: Path, qapp: QApplication) -> None:
    _require()
    window = _window(tmp_path)
    try:
        surface = _open(window, qapp, tmp_path / "invoice.ui", _DUPLICATE)
        toggle = surface.findChild(QWidget, "formBuilder.viewXml")
        toggle.click()
        qapp.processEvents()
        assert _xml_checked(surface)
        tree = _show_problems(window, qapp)
        tree.setFocus()
        tree.scrollToItem(_row(tree, "okButton"))
        qapp.processEvents()
        item = _row(tree, "okButton")
        QTest.mouseClick(tree.viewport(), _button(), _mod("NoModifier"), tree.visualItemRect(item).center())
        qapp.processEvents()
        # M5: a single click previews; it must not change the view or take focus.
        assert _xml_checked(surface)
        assert _problems_focus(window), QApplication.focusWidget()
    finally:
        shutdown_main_window_for_test(window, qapp)

