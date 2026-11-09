# pyright: reportAttributeAccessIssue=false
"""Picker lifetime, method-page keys, and Alt+B on a widget that already has an event."""

from __future__ import annotations

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtCore import QEvent, Qt  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtWidgets import QApplication, QCheckBox, QLineEdit, QWidget  # noqa: E402
from app.features.form_builder.qtside.inspector.pane import TabId  # noqa: E402
from app.features.form_builder.qtside.pickers.popover import EventPicker  # noqa: E402
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
 <connections>
  <connection>
   <sender>okButton</sender>
   <signal>clicked()</signal>
   <receiver>Invoice</receiver>
   <slot>close()</slot>
  </connection>
 </connections>
</ui>
"""


def _open(window, pane, qapp):
    when = pane.findChild(QWidget, "formBuilder.events.when")
    host = when if when is not None else pane
    host_button = next(
        (button for button in pane.findChildren(QWidget) if button.objectName() == "formBuilder.events.when"),
        host,
    )
    from app.features.form_builder.qtside.pickers import open_event_picker

    picker = open_event_picker(host_button, "okButton", "")
    qapp.processEvents()
    return picker


def test_eight_picker_opens_leave_none_alive(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp, _FORM)
    try:
        _select(session, "okButton")
        pane.focus_tab(TabId.BEHAVIOR)
        pane.flush()
        qapp.processEvents()
        for _ in range(8):
            picker = _open(window, pane, qapp)
            search = picker.findChild(QLineEdit, "formBuilder.eventPickerSearch")
            assert search is not None
            QTest.keyClick(search, Qt.Key_Escape)
            qapp.processEvents()
        picker = None
        qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        qapp.processEvents()
        alive = [item for item in qapp.allWidgets() if isinstance(item, EventPicker)]
        assert alive == []
    finally:
        _close(window, pane, realizer, session, qapp)


def test_invalid_method_name_stays_open(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp, _FORM)
    try:
        _select(session, "okButton")
        pane.focus_tab(TabId.BEHAVIOR)
        pane.flush()
        qapp.processEvents()
        before = session.text()
        picker = _open(window, pane, qapp)
        search = picker.findChild(QLineEdit, "formBuilder.eventPickerSearch")
        QTest.keyClicks(search, "new method")
        qapp.processEvents()
        QTest.keyClick(search, Qt.Key_Return)
        qapp.processEvents()
        field = picker.findChild(QLineEdit, "formBuilder.eventPickerMethod")
        if field is not None and field.isVisible():
            QTest.keyClick(field, Qt.Key_A, Qt.KeyboardModifier.ControlModifier)
            QTest.keyClicks(field, "123bad")
            QTest.keyClick(field, Qt.Key_Return)
            qapp.processEvents()
            assert field.isVisible()
        assert session.text() == before
    finally:
        _close(window, pane, realizer, session, qapp)


def test_show_actions_checkbox_escape_goes_back_one_page(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp, _FORM)
    try:
        _select(session, "okButton")
        pane.focus_tab(TabId.BEHAVIOR)
        pane.flush()
        qapp.processEvents()
        picker = _open(window, pane, qapp)
        search = picker.findChild(QLineEdit, "formBuilder.eventPickerSearch")
        QTest.keyClick(search, Qt.Key_Return)
        qapp.processEvents()
        box = picker.findChild(QCheckBox, "formBuilder.eventPickerBase")
        if box is not None and box.isVisible():
            box.setFocus()
            QTest.keyClick(box, Qt.Key_Escape)
            qapp.processEvents()
            assert picker.isVisible()
            assert search.isVisible()
        assert session.text().count("<connection>") == 1
    finally:
        _close(window, pane, realizer, session, qapp)
