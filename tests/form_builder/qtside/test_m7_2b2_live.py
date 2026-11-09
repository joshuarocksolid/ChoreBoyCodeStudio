# pyright: reportAttributeAccessIssue=false
"""A State formula shows on the canvas and leaves the file alone."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Tuple, cast

from app.features.form_builder.engine.ids import NodeId

import pytest

from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.qtside.formula.editor import FormulaEditor
from app.features.form_builder.qtside.inspector import TabId
from app.features.form_builder.qtside.inspector.pane import InspectorPane
from app.qt.QtCore import Qt
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QLabel, QLineEdit, QSpinBox, QVBoxLayout, QWidget
from tests.form_builder.qtside.support import form, opened

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("qapp")]

FORM = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>420</width><height>320</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QLabel" name="totalLabel">
     <property name="text"><string>Qty</string></property>
    </widget>
   </item>
   <item>
    <widget class="QSpinBox" name="qtySpin"/>
   </item>
   <item>
    <widget class="QSpinBox" name="priceSpin"/>
   </item>
   <item>
    <widget class="QLineEdit" name="discountEdit"/>
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


def _id(session: FormSession, name: str) -> object:
    found = session.document.by_name(name)
    assert found, name
    return found[0]


@contextmanager
def desk() -> Iterator[Tuple[FormSession, InspectorPane, object]]:
    with opened(FORM) as (session, realizer):
        window = QWidget()
        pane = InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None, parent=window)
        layout = QVBoxLayout(window)
        layout.addWidget(pane)
        window.resize(480, 720)
        window.show()
        pump()
        try:
            yield session, pane, realizer
        finally:
            pane.dispose()
            window.close()
            window.deleteLater()
            pump()


def _select(session: FormSession, pane: InspectorPane, name: str) -> None:
    session.selection.set((_id(session, name),), source=SelectionSource.PROGRAM)  # type: ignore[arg-type]
    pane.focus_tab(TabId.BEHAVIOR)
    pane.flush()
    pump()


def _open(pane: InspectorPane, key: str) -> FormulaEditor:
    state = pane.findChild(QWidget, "formBuilder.state")
    assert state is not None
    state.open_row(key)  # type: ignore[attr-defined]
    pump()
    editor = pane.findChild(FormulaEditor, "formBuilder.formula")
    assert editor is not None
    if not editor.isVisible():
        editor.setFocus()
        pump()
    assert editor.isVisible()
    return editor


def _depth(session: FormSession) -> int:
    return len(session.log.entries())


def test_enabled_when_false_greys_the_widget_until_the_editor_closes() -> None:
    with desk() as (session, pane, realizer):
        edit = realizer.widget_named("discountEdit")
        assert isinstance(edit, QLineEdit)
        assert edit.isEnabled()
        depth = _depth(session)
        assert not session.log.is_dirty()
        _select(session, pane, "discountEdit")
        editor = _open(pane, "cbcsEnabledWhen")
        editor.setPlainText("False")
        pump()
        assert not edit.isEnabled()
        assert _depth(session) == depth
        assert not session.log.is_dirty()
        QTest.keyClick(editor, Qt.Key.Key_Escape)
        pump()
        assert edit.isEnabled()
        assert _depth(session) == depth
        assert not session.log.is_dirty()


def test_a_value_rule_shows_the_computed_label_while_the_editor_is_open() -> None:
    with desk() as (session, pane, realizer):
        label = realizer.widget_named("totalLabel")
        assert isinstance(label, QLabel)
        assert label.text() == "Qty"
        depth = _depth(session)
        _select(session, pane, "totalLabel")
        editor = _open(pane, "cbcsValue")
        editor.setPlainText('"Shown"')
        pump()
        assert label.text() == "Shown"
        assert _depth(session) == depth
        assert not session.log.is_dirty()
        QTest.keyClick(editor, Qt.Key.Key_Escape)
        pump()
        assert label.text() == "Qty"
        assert _depth(session) == depth
        assert not session.log.is_dirty()


def test_a_spin_box_value_rule_shows_the_number_while_the_editor_is_open() -> None:
    with desk() as (session, pane, realizer):
        spin = realizer.widget_named("qtySpin")
        assert isinstance(spin, QSpinBox)
        assert spin.value() == 0
        depth = _depth(session)
        _select(session, pane, "qtySpin")
        editor = _open(pane, "cbcsValue")
        editor.setPlainText("7")
        pump()
        assert spin.value() == 7
        assert _depth(session) == depth
        assert not session.log.is_dirty()
        QTest.keyClick(editor, Qt.Key.Key_Escape)
        pump()
        assert spin.value() == 0


def test_qty_times_price_shows_zero_while_the_editor_is_open() -> None:
    with desk() as (session, pane, realizer):
        label = realizer.widget_named("totalLabel")
        assert isinstance(label, QLabel)
        depth = _depth(session)
        _select(session, pane, "totalLabel")
        editor = _open(pane, "cbcsValue")
        editor.setPlainText("qtySpin * priceSpin")
        pump()
        assert label.text() == "0"
        assert _depth(session) == depth
        assert not session.log.is_dirty()
        QTest.keyClick(editor, Qt.Key.Key_Escape)
        pump()
        assert label.text() == "Qty"
        assert _depth(session) == depth


def test_a_money_format_shows_the_formatted_zero_while_the_editor_is_open() -> None:
    from app.features.form_builder.engine.commands.catalog import SetLogic

    with desk() as (session, pane, realizer):
        label = realizer.widget_named("totalLabel")
        assert isinstance(label, QLabel)
        session.log.execute(SetLogic(cast(NodeId, _id(session, "totalLabel")), "cbcsFormat", "money"))
        _select(session, pane, "totalLabel")
        editor = _open(pane, "cbcsValue")
        editor.setPlainText("qtySpin * priceSpin")
        pump()
        assert label.text() == "$0.00"
        QTest.keyClick(editor, Qt.Key.Key_Escape)
        pump()
        assert label.text() == "Qty"


def test_selection_change_restores_design_values() -> None:
    with desk() as (session, pane, realizer):
        label = realizer.widget_named("totalLabel")
        assert isinstance(label, QLabel)
        _select(session, pane, "totalLabel")
        editor = _open(pane, "cbcsValue")
        editor.setPlainText('"Shown"')
        pump()
        assert label.text() == "Shown"
        _select(session, pane, "okButton")
        assert label.text() == "Qty"
        assert not editor.isVisible()
