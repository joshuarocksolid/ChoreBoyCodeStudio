# pyright: reportAttributeAccessIssue=false
"""Esc in the event picker writes nothing. A finished choice is one undo step."""

from __future__ import annotations

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.qtside.inspector.pane import TabId  # noqa: E402
from app.qt.QtCore import Qt  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtWidgets import QApplication, QLineEdit, QPushButton, QWidget  # noqa: E402
from tests.form_builder.inspector.test_inspector_round2 import _close, _pane, _select  # noqa: E402

pytestmark = pytest.mark.unit

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QWidget" name="Invoice">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QPushButton" name="okButton"><property name="text"><string>OK</string></property></widget></item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def test_escape_in_the_event_picker_writes_nothing(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp, _FORM)
    try:
        _select(session, "okButton")
        pane.focus_tab(TabId.BEHAVIOR)
        pane.flush()
        qapp.processEvents()
        before = session.text()
        depth = len(session.log.entries())
        add = next(button for button in pane.findChildren(QPushButton) if button.text().startswith("+ When"))
        add.click()
        qapp.processEvents()
        search = window.findChild(QLineEdit, "formBuilder.eventPickerSearch")
        assert search is not None and search.isVisible()
        QTest.keyClick(search, Qt.Key_Escape)
        qapp.processEvents()
        picker = window.findChild(QWidget, "formBuilder.eventPicker")
        assert picker is None or not picker.isVisible()
        assert session.text() == before
        assert len(session.log.entries()) == depth
    finally:
        _close(window, pane, realizer, session, qapp)


def test_close_this_form_is_one_undo_step_and_shows_the_row(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp, _FORM)
    try:
        _select(session, "okButton")
        pane.focus_tab(TabId.BEHAVIOR)
        pane.flush()
        qapp.processEvents()
        depth = len(session.log.entries())
        add = next(button for button in pane.findChildren(QPushButton) if button.text().startswith("+ When"))
        add.click()
        qapp.processEvents()
        search = window.findChild(QLineEdit, "formBuilder.eventPickerSearch")
        assert search is not None
        QTest.keyClick(search, Qt.Key_Return)
        qapp.processEvents()
        QTest.keyClicks(search, "close")
        qapp.processEvents()
        QTest.keyClick(search, Qt.Key_Return)
        pane.flush()
        qapp.processEvents()
        assert len(session.log.entries()) == depth + 1
        assert session.log.undo_label() == "Add Close this form to OK clicked"
        assert any("Close this form" in widget.accessibleName() for widget in pane.findChildren(QWidget))
    finally:
        _close(window, pane, realizer, session, qapp)
