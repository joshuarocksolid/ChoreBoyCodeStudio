# pyright: reportAttributeAccessIssue=false
"""Formula › and ‹ Builder keep the same text, and commit is one undo step."""

from __future__ import annotations

import pytest

from app.features.form_builder.qtside.inspector.behavior_ext.state import open_state_row
from app.qt.QtCore import Qt
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QLabel, QLineEdit, QPushButton, QWidget
from tests.form_builder.qtside.test_m7_2b1_fx import _editor
from tests.form_builder.qtside.test_m7_2b1_state import _select, _stored, desk, pump

pytestmark = [pytest.mark.unit]


def _key(name: str) -> object:
    return getattr(getattr(Qt, "Key", Qt), name)


def _switch(root: QWidget) -> QPushButton:
    found = root.findChild(QPushButton, "formBuilder.formula.switch")
    assert isinstance(found, QPushButton)
    return found


def _field(root: QWidget) -> QLineEdit:
    found = root.findChild(QLineEdit, "formBuilder.builder.cond.row.0.field")
    assert isinstance(found, QLineEdit)
    return found


def test_empty_condition_opens_in_the_builder_and_switches_without_loss(qapp: QApplication) -> None:
    del qapp
    with desk() as (session, pane):
        _select(session, pane, "discountEdit")
        open_state_row(pane, "cbcsEnabledWhen")
        pump()
        editor = _editor(pane)
        switch = _switch(pane)
        assert not editor.isVisible()
        assert switch.text() == "Formula ›"
        assert _field(pane).isVisible()
        QTest.keyClick(switch, _key("Key_Space"))  # type: ignore[arg-type]
        pump()
        assert editor.isVisible()
        assert editor.toPlainText() == ""
        assert switch.text() == "‹ Builder"
        assert switch.isEnabled()
        QTest.keyClick(switch, _key("Key_Space"))  # type: ignore[arg-type]
        pump()
        assert not editor.isVisible()
        assert editor.toPlainText() == ""
        assert switch.text() == "Formula ›"


def test_builder_status_reads_the_condition_in_words(qapp: QApplication) -> None:
    del qapp
    with desk() as (session, pane):
        _select(session, pane, "discountEdit")
        open_state_row(pane, "cbcsEnabledWhen")
        pump()
        editor = _editor(pane)
        editor.setFocus()
        pump()
        editor.setPlainText("discountCheck and discountCheck")
        pump()
        QTest.keyClick(_switch(pane), _key("Key_Space"))  # type: ignore[arg-type]
        pump()
        status = pane.findChild(QLabel, "formBuilder.state.status")
        assert status is not None
        assert status.text().splitlines()[-1] == "Discount is checked and Discount is checked"


def test_a_complex_formula_disables_builder(qapp: QApplication) -> None:
    del qapp
    with desk() as (session, pane):
        _select(session, pane, "discountEdit")
        open_state_row(pane, "cbcsEnabledWhen")
        pump()
        editor = _editor(pane)
        editor.setFocus()
        pump()
        editor.setPlainText("round(qtySpin)")
        pump()
        switch = _switch(pane)
        note = pane.findChild(QWidget, "formBuilder.builder.blocked")
        assert editor.isVisible()
        assert switch.text() == "‹ Builder"
        assert not switch.isEnabled()
        assert switch.toolTip() == "This is too complex for the builder. Edit it as a formula."
        assert note is not None and note.isVisible()
        assert note.text() == "This is too complex for the builder. Edit it as a formula."  # type: ignore[attr-defined]


def test_a_value_formula_switches_both_ways_without_loss(qapp: QApplication) -> None:
    del qapp
    with desk() as (session, pane):
        _select(session, pane, "discountEdit")
        depth = len(session.log.entries())
        open_state_row(pane, "cbcsValue")
        pump()
        editor = _editor(pane)
        editor.setFocus()
        pump()
        editor.setPlainText("qtySpin * priceSpin")
        pump()
        switch = _switch(pane)
        QTest.keyClick(switch, _key("Key_Space"))  # type: ignore[arg-type]
        pump()
        assert not editor.isVisible()
        assert editor.toPlainText() == "qtySpin * priceSpin"
        assert switch.text() == "Formula ›"
        QTest.keyClick(switch, _key("Key_Space"))  # type: ignore[arg-type]
        pump()
        assert editor.isVisible()
        assert editor.toPlainText() == "qtySpin * priceSpin"
        assert switch.text() == "‹ Builder"
        assert len(session.log.entries()) == depth


def test_builder_commit_is_one_undo_step(qapp: QApplication) -> None:
    del qapp
    with desk() as (session, pane):
        _select(session, pane, "discountEdit")
        depth = len(session.log.entries())
        open_state_row(pane, "cbcsEnabledWhen")
        pump()
        field = _field(pane)
        assert QApplication.focusWidget() is field
        QTest.keyClicks(field, "disc")
        pump()
        QTest.keyClick(field, _key("Key_Tab"))  # type: ignore[arg-type]
        pump()
        QTest.keyClick(field, _key("Key_Return"), Qt.KeyboardModifier.ControlModifier)  # type: ignore[arg-type]
        pump()
        assert _stored(session, "discountEdit", "cbcsEnabledWhen") == "discountCheck"
        assert session.log.undo_label() == "Set Enabled when for Discount rate"
        assert len(session.log.entries()) == depth + 1
        session.log.undo()
        pump()
        assert _stored(session, "discountEdit", "cbcsEnabledWhen") == ""
