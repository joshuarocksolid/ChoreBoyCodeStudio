# pyright: reportAttributeAccessIssue=false
"""A popover session with the real FormSession and the real inspector (UX-PED-004, UX-M4-006).

A test editor stands in for a compound editor. Its popover writes the row's own
property through host.commit(value, session=...) and a second property through
popover.session.run(...). Done keeps one undo step; Esc leaves no trace.
"""

from __future__ import annotations

from typing import Dict, Optional

import pytest

from app.features.form_builder.engine.commands.catalog import SetProperty
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.engine.ui4.writer import write_ui
from app.features.form_builder.qtside.inspector import InspectorPane, pane as pane_module
from app.features.form_builder.qtside.inspector.api import EditorKey, GroupId, Mixed, Prop, RowSpec, Unset, Written
from app.features.form_builder.qtside.inspector.catalog import Catalog
from app.features.form_builder.qtside.inspector.editors import default_catalog
from app.features.form_builder.qtside.inspector.editors._popover import RowPopover, SummaryButton
from app.qt.QtCore import Qt  # type: ignore[reportAttributeAccessIssue]
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget
from tests.form_builder.qtside.support import realize

pytestmark = [pytest.mark.usefixtures("qapp"), pytest.mark.unit]

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="lay">
   <item><widget class="QLabel" name="titleLabel"><property name="text"><string>Title</string></property></widget></item>
   <item><widget class="QLabel" name="otherLabel"/></item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

_KEY = EditorKey("string")
_ROW = "formBuilder.row.fbtest.tip"


def _k(name: str):  # type: ignore[no-untyped-def]
    return getattr(getattr(Qt, "Key", Qt), name)


def _settle(qapp: QApplication) -> None:
    for _ in range(3):
        qapp.processEvents()


class _PopoverEditor:
    """A compound editor: a summary, and a popover with two fields."""

    def __init__(self, host: object, parent: QWidget, owner: object) -> None:
        self._host = host
        self._owner = owner
        self._summary = SummaryButton("Test tip", parent)
        self._summary.set_summary("")
        self._summary.set_opener(self._open)
        self.popover: Optional[RowPopover] = None

    @property
    def widget(self) -> QWidget:
        return self._summary

    def show(self, value: object) -> None:
        if isinstance(value, Written) and isinstance(value.value, StringValue):
            self._summary.set_summary(value.value.text)
        elif isinstance(value, Mixed):
            self._summary.set_summary("Mixed")
        else:
            self._summary.set_summary("")

    def _open(self) -> None:
        if self.popover is not None and not self.popover.closed:
            return
        row = self._host if isinstance(self._host, QWidget) else self._summary
        popover = RowPopover(
            row,
            self._host,  # type: ignore[arg-type]
            row_label="Test tip",
            session_label="Change test tip",
            anchor=self._summary,
        )
        first = QLineEdit(popover)
        second = QLineEdit(popover)
        popover.body().addWidget(first)
        popover.body().addWidget(second)
        popover.set_reset(None)
        host = self._host
        owner = self._owner
        first.textEdited.connect(lambda text: host.commit(StringValue(text), session=popover.session))  # type: ignore[attr-defined]
        second.textEdited.connect(
            lambda text: popover.session.run((SetProperty(owner, "windowTitle", StringValue(text)),))  # type: ignore[arg-type]
        )
        self.popover = popover
        popover.open_popover()


def _catalog(owner: object) -> Catalog:
    base = default_catalog()
    editors: Dict[EditorKey, object] = {key: base.editor(key) for key in base.editor_keys()}
    editors[_KEY] = lambda spec, host, parent: _PopoverEditor(host, parent, owner)
    rows = base.rows() + (
        RowSpec(key="fbtest.tip", group=GroupId.CONTENT, label="Test tip", help="", source=Prop("toolTip")),
    )
    bodies = {group: base.group_body(group) for group in GroupId if base.group_body(group) is not None}
    return Catalog(rows, editors, bodies)  # type: ignore[arg-type]


class _Rig:
    def __init__(self, qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
        self.session, self.realizer = realize(_FORM)
        self.title = self.session.document.by_name("titleLabel")[0]
        self.other = self.session.document.by_name("otherLabel")[0]
        monkeypatch.setattr(pane_module, "default_catalog", lambda: _catalog(self.title))
        self.window = QWidget()
        self.pane = InspectorPane(self.session, self.realizer, data_tab=False, on_leave=lambda: None, parent=self.window)
        QVBoxLayout(self.window).addWidget(self.pane)
        self.window.resize(900, 700)
        self.window.show()
        qapp.setActiveWindow(self.window)
        self.session.selection.set((self.title,), source=SelectionSource.PROGRAM)
        self.pane.set_group_expanded(GroupId.CONTENT, True)
        self.pane.flush()
        _settle(qapp)
        self.qapp = qapp

    def summary(self):  # type: ignore[no-untyped-def]
        row = self.pane.findChild(QWidget, _ROW)
        assert row is not None
        found = row.findChild(SummaryButton)
        assert found is not None
        return found

    def open(self):  # type: ignore[no-untyped-def]
        summary = self.summary()
        summary.setFocus()
        _settle(self.qapp)
        QTest.keyClick(summary, _k("Key_Return"))
        _settle(self.qapp)
        popover = self.window.findChild(RowPopover)
        assert popover is not None and popover.isVisible()
        return popover

    def fields(self, popover: RowPopover):  # type: ignore[no-untyped-def]
        found = popover.findChildren(QLineEdit)
        assert len(found) == 2
        return found

    def xml(self) -> str:
        return write_ui(self.session.document).text

    def close(self) -> None:
        self.pane.dispose()
        self.realizer.dispose()
        self.session.dispose()
        self.window.close()


def _write_three_and_two(rig: _Rig, popover: RowPopover) -> None:
    first, second = rig.fields(popover)
    first.setFocus()
    _settle(rig.qapp)
    QTest.keyClicks(first, "One")
    second.setFocus()
    _settle(rig.qapp)
    QTest.keyClicks(second, "xy")
    _settle(rig.qapp)


def _window_title(rig: _Rig) -> Optional[str]:
    prop = rig.session.document.node(rig.title).prop("windowTitle")
    if prop is None or not isinstance(prop.value, StringValue):
        return None
    return prop.value.text


def test_done_keeps_one_undo_step_and_undo_restores_the_bytes(qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = _Rig(qapp, monkeypatch)
    try:
        before_xml = rig.xml()
        before = rig.session.log.entries()
        popover = rig.open()
        _write_three_and_two(rig, popover)
        assert _window_title(rig) == "xy"
        done = popover.findChild(QPushButton, "formBuilder.popoverDone")
        assert done is not None
        done.click()
        _settle(qapp)
        assert popover.closed
        after = rig.session.log.entries()
        assert len(after) == len(before) + 1
        assert after[-1].label == "Change test tip"
        assert rig.session.log.undo_label() == "Change test tip"
        assert rig.session.log.undo() is True
        assert rig.xml() == before_xml
        assert rig.session.log.entries() == before
    finally:
        rig.close()


def test_escape_leaves_the_document_and_the_undo_stack_as_they_were(qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = _Rig(qapp, monkeypatch)
    try:
        before_xml = rig.xml()
        before = rig.session.log.entries()
        popover = rig.open()
        _write_three_and_two(rig, popover)
        assert rig.xml() != before_xml
        first, _second = rig.fields(popover)
        first.setFocus()
        _settle(qapp)
        QTest.keyClick(first, _k("Key_Escape"))
        _settle(qapp)
        assert popover.closed
        assert rig.xml() == before_xml
        assert rig.session.log.entries() == before
        assert _window_title(rig) is None
    finally:
        rig.close()


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Owner: engine/commands/log.py (orchestrator decides). Esc undoes the session, but the entry "
        "stays on the redo stack, so Redo re-applies the reverted edit. Repro: Esc, then can_redo()."
    ),
)
def test_escape_leaves_the_redo_stack_as_it_was(qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = _Rig(qapp, monkeypatch)
    try:
        before_redo = rig.session.log.can_redo()
        popover = rig.open()
        _write_three_and_two(rig, popover)
        first, _second = rig.fields(popover)
        first.setFocus()
        _settle(qapp)
        QTest.keyClick(first, _k("Key_Escape"))
        _settle(qapp)
        assert rig.session.log.can_redo() == before_redo
    finally:
        rig.close()


def test_a_selection_change_closes_the_popover_and_keeps_the_writes(qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = _Rig(qapp, monkeypatch)
    try:
        before = rig.session.log.entries()
        popover = rig.open()
        first, _second = rig.fields(popover)
        first.setFocus()
        _settle(qapp)
        QTest.keyClicks(first, "Kept")
        _settle(qapp)
        rig.session.selection.set((rig.other,), source=SelectionSource.CANVAS)
        _settle(qapp)
        assert popover.closed
        assert len(rig.session.log.entries()) == len(before) + 1
        assert rig.session.log.undo_label() == "Change test tip"
    finally:
        rig.close()


def test_ctrl_z_outside_a_text_field_closes_keeps_and_undoes_as_one_step(qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = _Rig(qapp, monkeypatch)
    try:
        before_xml = rig.xml()
        before = rig.session.log.entries()
        popover = rig.open()
        _write_three_and_two(rig, popover)
        done = popover.findChild(QPushButton, "formBuilder.popoverDone")
        assert done is not None
        done.setFocus()
        _settle(qapp)
        QTest.keyClick(done, _k("Key_Z"), getattr(getattr(Qt, "KeyboardModifier", Qt), "ControlModifier"))
        _settle(qapp)
        assert popover.closed
        assert rig.session.log.entries() == before
        assert rig.xml() == before_xml
    finally:
        rig.close()
