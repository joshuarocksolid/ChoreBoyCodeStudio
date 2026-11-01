# pyright: reportAttributeAccessIssue=false
"""Set and message take the formula editor. Stop's when field stays a line."""

from __future__ import annotations

import json
from typing import cast

import pytest

from app.features.form_builder.engine.commands.base import Command
from app.features.form_builder.engine.logic.events import read_event
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.qtside.formula.editor import FormulaEditor
from app.features.form_builder.qtside.inspector.behavior_ext._rows import _add_verb
from app.features.form_builder.qtside.pickers.flow import PickContext, PickerSource, _step_page
from app.features.form_builder.qtside.pickers.popover import EventPicker
from app.features.form_builder.qtside.pickers.verb_pages import page_for
from app.features.form_builder.integration.chrome import chrome_for
from app.qt.QtCore import Qt
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QLineEdit, QListWidget, QWidget
from app.shell.theme_tokens import tokens_from_palette
from tests.form_builder.qtside.support import form, opened

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("qapp")]

FORM = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>320</width><height>160</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QLineEdit" name="nameEdit"/>
   </item>
   <item>
    <widget class="QPushButton" name="okButton">
     <property name="text"><string>OK</string></property>
    </widget>
   </item>
  </layout>
""",
)


def pump() -> None:
    app = QApplication.instance()
    assert app is not None
    for _ in range(6):
        app.processEvents()


def _picker(document: object, host: QWidget, on_commit) -> EventPicker:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    chrome = chrome_for(tokens_from_palette(app.palette()))
    ctx = PickContext(
        document,  # type: ignore[arg-type]
        QtClassTable.shared(),
        PickerSource("okButton", "clicked"),
        "",
        (),
        "forms/form.py",
        "Form",
        False,
    )
    picker = EventPicker(host, chrome, on_commit)
    picker._ctx = ctx
    return picker


def _back(picker: EventPicker):
    ctx = picker._ctx
    assert isinstance(ctx, PickContext)
    return _step_page(ctx, "clicked", False, -1, "")


def test_set_and_message_use_the_formula_editor() -> None:
    with opened(FORM) as (session, _realizer):
        host = QWidget()
        host.resize(420, 280)
        host.show()
        try:
            picker = _picker(session.document, host, lambda gesture: None)
            back = _back(picker)
            for verb in ("set", "message"):
                picker._apply(page_for(back, verb))
                picker.show()
                pump()
                editor = picker.findChild(FormulaEditor, "formBuilder.verbField.formula")
                assert isinstance(editor, FormulaEditor), verb
                assert editor.objectName() == "formBuilder.verbField.formula"
            picker._apply(page_for(back, "stop"))
            pump()
            when = picker.findChild(QLineEdit, "formBuilder.verbField.when")
            assert isinstance(when, QLineEdit)
            assert not isinstance(when, FormulaEditor)
        finally:
            host.close()
            host.deleteLater()
            pump()


def test_the_formula_field_completes_and_underlines_an_error() -> None:
    with opened(FORM) as (session, _realizer):
        host = QWidget()
        host.resize(420, 280)
        host.show()
        try:
            picker = _picker(session.document, host, lambda gesture: None)
            back = _back(picker)
            picker._apply(page_for(back, "set"))
            picker.show()
            pump()
            editor = picker.findChild(FormulaEditor, "formBuilder.verbField.formula")
            assert isinstance(editor, FormulaEditor)
            editor.setFocus()
            QTest.keyClicks(editor, "na")
            pump()
            complete = picker.findChild(QListWidget, "formBuilder.formula.complete")
            assert complete is not None and complete.isVisible()
            status = picker.findChild(QWidget, "formBuilder.verbStatus.formula")
            assert status is not None and status.isVisible() and status.text()  # type: ignore[attr-defined]
            labels = [complete.item(index).text() for index in range(complete.count())]
            assert any("nameEdit" in text for text in labels)
            editor.setPlainText("missingField")
            pump()
            assert editor.has_error()
            assert editor.extraSelections()
        finally:
            host.close()
            host.deleteLater()
            pump()


def test_committing_a_set_formula_writes_the_step() -> None:
    with opened(FORM) as (session, _realizer):
        host = QWidget()
        host.resize(420, 280)
        host.show()
        got = {}

        def take(gesture) -> None:
            got["gesture"] = gesture

        try:
            picker = _picker(session.document, host, take)
            back = _back(picker)
            picker._apply(page_for(back, "set"))
            picker.show()
            pump()
            field = picker.findChild(QLineEdit, "formBuilder.verbField.field")
            editor = picker.findChild(FormulaEditor, "formBuilder.verbField.formula")
            assert field is not None and isinstance(editor, FormulaEditor)
            field.setText("nameEdit")
            editor.setFocus()
            editor.setPlainText("1")
            pump()
            QTest.keyClick(editor, Qt.Key.Key_Return)
            pump()
            gesture = got["gesture"]
            fields = json.loads(gesture.verb_fields)
            assert fields["formula"] == "1"
            assert fields["field"] == "nameEdit"
            outcome = _add_verb(session.document, QtClassTable.shared(), "okButton", gesture)
            assert outcome is not None
            command = outcome.command
            assert command is not None
            session.log.execute(cast(Command, command))
            state = read_event(session.document, "okButton", "clicked")
            stored = state.list_steps[-1].raw
            assert stored.verb == "set"
            assert dict(stored.fields) == {"field": "nameEdit", "formula": "1"}
        finally:
            host.close()
            host.deleteLater()
            pump()


def test_shift_enter_inserts_a_line_and_does_not_commit() -> None:
    with opened(FORM) as (session, _realizer):
        host = QWidget()
        host.resize(420, 280)
        host.show()
        got = {}
        try:
            picker = _picker(session.document, host, lambda gesture: got.setdefault("gesture", gesture))
            back = _back(picker)
            picker._apply(page_for(back, "set"))
            picker.show()
            pump()
            editor = picker.findChild(FormulaEditor, "formBuilder.verbField.formula")
            assert isinstance(editor, FormulaEditor)
            editor.setFocus()
            editor.setPlainText("1")
            QTest.keyClick(editor, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
            pump()
            assert "\n" in editor.toPlainText()
            assert "gesture" not in got
        finally:
            host.close()
            host.deleteLater()
            pump()
