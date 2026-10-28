# pyright: reportAttributeAccessIssue=false
"""Edit sessions and undo (UX-PED-004): one focus visit is one step, revert leaves no step."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.commands.catalog import SetProperty
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.engine.ui4.writer import write_ui
from app.features.form_builder.qtside.inspector import InspectorPane
from app.features.form_builder.qtside.inspector._services import Dropped, Services
from app.features.form_builder.qtside.inspector.editors import default_catalog
from app.qt.QtCore import Qt  # type: ignore[reportAttributeAccessIssue]
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QLineEdit, QVBoxLayout, QWidget
from tests.form_builder.qtside.support import realize

pytestmark = [pytest.mark.usefixtures("qapp"), pytest.mark.unit]

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QWidget" name="Invoice">
  <layout class="QVBoxLayout" name="mainLayout">
   <item>
    <widget class="QLineEdit" name="email">
     <property name="text"><string>Pay</string></property>
    </widget>
   </item>
   <item>
    <widget class="QLineEdit" name="phone"/>
   </item>
   <item>
    <widget class="QPushButton" name="okButton"/>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _settle(qapp: QApplication) -> None:
    for _ in range(3):
        qapp.processEvents()


def _pane(qapp: QApplication):  # type: ignore[no-untyped-def]
    session, realizer = realize(_FORM)
    window = QWidget()
    pane = InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None, parent=window)
    QVBoxLayout(window).addWidget(pane)
    window.resize(900, 700)
    window.show()
    qapp.setActiveWindow(window)
    email = session.document.by_name("email")[0]
    session.selection.set((email,), source=SelectionSource.PROGRAM)
    pane.flush()
    _settle(qapp)
    return window, pane, session, realizer


def _close(window, pane, realizer, session) -> None:  # type: ignore[no-untyped-def]
    pane.dispose()
    realizer.dispose()
    session.dispose()
    window.close()


def _text_editor(pane: InspectorPane) -> QLineEdit:
    row = pane.findChild(QWidget, "formBuilder.row.text")
    assert row is not None
    editor = row.findChild(QLineEdit)
    assert editor is not None
    return editor


def _type_and_commit(qapp: QApplication, editor: QLineEdit, text: str) -> None:
    editor.setFocus()
    _settle(qapp)
    editor.selectAll()
    QTest.keyClicks(editor, text)
    QTest.keyClick(editor, getattr(getattr(Qt, "Key", Qt), "Key_Return"))
    _settle(qapp)


def _text_of(session, name: str) -> str:  # type: ignore[no-untyped-def]
    value = session.document.node(session.document.by_name(name)[0]).prop("text")
    assert value is not None and isinstance(value.value, StringValue)
    return value.value.text


def test_two_focus_visits_to_one_row_are_two_undo_steps(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp)
    try:
        editor = _text_editor(pane)
        _type_and_commit(qapp, editor, "One")
        assert len(session.log.entries()) == 1
        other = pane.findChild(QWidget, "formBuilder.inspectorSearch")
        assert other is not None
        other.setFocus()
        _settle(qapp)
        _type_and_commit(qapp, editor, "Two")
        assert len(session.log.entries()) == 2
        assert session.log.undo() is True
        assert _text_of(session, "email") == "One"
        assert session.log.undo() is True
        assert _text_of(session, "email") == "Pay"
    finally:
        _close(window, pane, realizer, session)


def test_one_focus_visit_with_several_commits_is_one_undo_step(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp)
    try:
        editor = _text_editor(pane)
        _type_and_commit(qapp, editor, "One")
        QTest.keyClicks(editor, "x")
        QTest.keyClick(editor, getattr(getattr(Qt, "Key", Qt), "Key_Return"))
        _settle(qapp)
        assert len(session.log.entries()) == 1
        assert session.log.undo_label() == "Change text"
        assert session.log.undo() is True
        assert _text_of(session, "email") == "Pay"
    finally:
        _close(window, pane, realizer, session)


def _services(session, realizer) -> Services:  # type: ignore[no-untyped-def]
    return Services(session, default_catalog(), realizer)


def test_session_writes_are_one_step_and_revert_restores_the_bytes(qapp: QApplication) -> None:
    del qapp
    session, realizer = realize(_FORM)
    try:
        services = _services(session, realizer)
        email = session.document.by_name("email")[0]
        phone = session.document.by_name("phone")[0]
        before_xml = write_ui(session.document).text
        before = session.log.entries()
        popover = services.begin_session("Change text")
        popover.run((SetProperty(email, "text", StringValue("A")),))
        popover.run((SetProperty(email, "text", StringValue("B")),))
        popover.run((SetProperty(phone, "text", StringValue("C")),))
        after_writes = session.log.entries()
        assert len(after_writes) == len(before) + 1
        assert after_writes[-1].label == "Change text"
        assert popover.revert() is True
        assert write_ui(session.document).text == before_xml
        assert session.log.entries() == before
        assert popover.closed
    finally:
        realizer.dispose()
        session.dispose()


def test_revert_of_a_session_that_wrote_nothing_changes_nothing(qapp: QApplication) -> None:
    del qapp
    session, realizer = realize(_FORM)
    try:
        services = _services(session, realizer)
        before = session.log.entries()
        popover = services.begin_session("Change text")
        assert popover.revert() is False
        assert session.log.entries() == before
    finally:
        realizer.dispose()
        session.dispose()


def test_a_closed_session_drops_later_writes(qapp: QApplication) -> None:
    del qapp
    session, realizer = realize(_FORM)
    try:
        services = _services(session, realizer)
        email = session.document.by_name("email")[0]
        popover = services.begin_session("Change text")
        popover.close()
        assert isinstance(popover.run((SetProperty(email, "text", StringValue("A")),)), Dropped)
        assert _text_of(session, "email") == "Pay"
    finally:
        realizer.dispose()
        session.dispose()


def test_set_label_names_the_step_from_its_first_write(qapp: QApplication) -> None:
    del qapp
    session, realizer = realize(_FORM)
    try:
        services = _services(session, realizer)
        email = session.document.by_name("email")[0]
        popover = services.begin_session("Change font of titleLabel")
        popover.set_label("Change font of email")
        popover.run((SetProperty(email, "text", StringValue("A")),))
        assert session.log.undo_label() == "Change font of email"
    finally:
        realizer.dispose()
        session.dispose()


def test_revert_leaves_no_redo_entry(qapp: QApplication) -> None:
    del qapp
    session, realizer = realize(_FORM)
    try:
        services = _services(session, realizer)
        email = session.document.by_name("email")[0]
        popover = services.begin_session("Change text")
        popover.run((SetProperty(email, "text", StringValue("A")),))
        assert popover.revert() is True
        assert session.log.can_redo() is False
    finally:
        realizer.dispose()
        session.dispose()
