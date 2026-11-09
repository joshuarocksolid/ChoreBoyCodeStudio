# pyright: reportAttributeAccessIssue=false
"""K12. Text, translations and custom properties (UX_SPEC §12.3).

Alt+4 is the shell shortcut that focuses the inspector (integration/surface.py).
These steps start once that focus has landed, and every edit is a key.
"""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.ui4.writer import write_ui
from app.qt.QtCore import Qt
from app.qt.QtGui import QTextCursor
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QCheckBox, QLineEdit, QToolButton, QWidget
from tests.form_builder.qtside.test_m43d_text import (
    _LABEL,
    _close,
    _expand_all,
    _pane,
    _select,
    _settle,
)

pytestmark = pytest.mark.unit


def test_k12_text_translations_and_custom_properties(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp, _LABEL)
    try:
        _select(session, "titleLabel")
        _settle(qapp, pane)
        original = write_ui(session.document).text
        row = pane.findChild(QWidget, "formBuilder.row.text")
        assert row is not None
        edit = row.findChild(QLineEdit)
        assert isinstance(edit, QLineEdit)
        edit.setFocus()
        edit.selectAll()
        QTest.keyClicks(edit, "Total:")
        QTest.keyClick(edit, Qt.Key_Return)
        qapp.processEvents()
        node = session.document.node(session.document.by_name("titleLabel")[0])
        text = node.prop("text")
        assert text is not None
        assert text.value.text == "Total:"
        toggle = row.findChild(QToolButton, "formBuilder.translationToggle")
        assert toggle is not None
        toggle.setFocus()
        QTest.keyClick(toggle, Qt.Key_Space)
        qapp.processEvents()
        box = row.findChild(QCheckBox)
        assert box is not None
        box.setFocus()
        QTest.keyClick(box, Qt.Key_Space)
        qapp.processEvents()
        written = write_ui(session.document).text
        assert 'notr="true"' in written
        note = next(
            item
            for item in row.findChildren(QLineEdit)
            if item.accessibleName() == "Translation: note for the translator"
        )
        note.setFocus()
        QTest.keyClicks(note, "Shown on receipts")
        QTest.keyClick(note, Qt.Key_Return)
        qapp.processEvents()
        assert 'extracomment="Shown on receipts"' in write_ui(session.document).text
        _expand_all(qapp, pane)
        add = pane.findChild(QWidget, "formBuilder.addCustomProperty")
        assert add is not None and add.isVisible()
        add.setFocus()
        QTest.keyClick(add, Qt.Key_Return)
        qapp.processEvents()
        name = next(
            item for item in pane.findChildren(QLineEdit) if item.accessibleName() == "Custom property name"
        )
        assert name.hasFocus()
        QTest.keyClicks(name, "requiredRole")
        QTest.keyClick(name, Qt.Key_Tab)
        kind = qapp.focusWidget()
        assert kind is not None and kind.accessibleName() == "Custom property type"
        assert kind.currentText() == "Text"
        QTest.keyClick(kind, Qt.Key_Return)
        qapp.processEvents()
        _settle(qapp, pane)
        qapp.processEvents()
        written = write_ui(session.document).text
        assert '<property name="requiredRole" stdset="0">' in written, written
        value = qapp.focusWidget()
        assert isinstance(value, QLineEdit)
        assert value.accessibleName() != "Custom property name"
        QTest.keyClicks(value, "manager")
        QTest.keyClick(value, Qt.Key_Return)
        qapp.processEvents()
        role = session.document.node(session.document.by_name("titleLabel")[0]).prop("requiredRole")
        assert role is not None and role.is_dynamic and role.value.text == "manager"
        _expand_all(qapp, pane)
        add = pane.findChild(QWidget, "formBuilder.addCustomProperty")
        assert add is not None
        add.setFocus()
        QTest.keyClick(add, Qt.Key_Return)
        qapp.processEvents()
        name = next(
            item for item in pane.findChildren(QLineEdit) if item.accessibleName() == "Custom property name"
        )
        QTest.keyClicks(name, "2nd")
        QTest.keyClick(name, Qt.Key_Return)
        qapp.processEvents()
        error = pane.findChild(QWidget, "formBuilder.rowError")
        assert error is not None and error.isVisible()
        assert "digit" in error.text()
        refused = write_ui(session.document).text
        QTest.keyClick(name, Qt.Key_Return)
        assert write_ui(session.document).text == refused
        QTest.keyClick(name, Qt.Key_Escape)
        qapp.processEvents()
        assert not name.isVisible()
        _select(session, "richLabel")
        _settle(qapp, pane)
        rich = pane.findChild(QWidget, "formBuilder.row.text")
        assert rich is not None
        summary = rich.findChild(QWidget, "formBuilder.summary")
        assert summary is not None
        summary.setFocus()
        QTest.keyClick(summary, Qt.Key_Space)
        qapp.processEvents()
        popover = window.findChild(QWidget, "formBuilder.rowPopover")
        assert popover is not None
        formatted = next(
            item for item in popover.findChildren(QWidget) if item.accessibleName() == "Text: formatted text"
        )
        formatted.setFocus()
        cursor = formatted.textCursor()
        cursor.select(QTextCursor.Document)
        formatted.setTextCursor(cursor)
        QTest.keyClick(formatted, Qt.Key_B, Qt.ControlModifier)
        done = popover.findChild(QWidget, "formBuilder.popoverDone")
        assert done is not None
        done.setFocus()
        QTest.keyClick(done, Qt.Key_Space)
        qapp.processEvents()
        bold = write_ui(session.document).text
        assert "font-weight:600" in bold
        # Same steps again on the same start: the same bytes (CONTRACTS §8.3).
        session.log.undo()
        summary.setFocus()
        QTest.keyClick(summary, Qt.Key_Space)
        qapp.processEvents()
        popover = [item for item in window.findChildren(QWidget, "formBuilder.rowPopover") if item.isVisible()][-1]
        formatted = next(
            item for item in popover.findChildren(QWidget) if item.accessibleName() == "Text: formatted text"
        )
        formatted.setFocus()
        cursor = formatted.textCursor()
        cursor.select(QTextCursor.Document)
        formatted.setTextCursor(cursor)
        QTest.keyClick(formatted, Qt.Key_B, Qt.ControlModifier)
        done = popover.findChild(QWidget, "formBuilder.popoverDone")
        assert done is not None
        done.setFocus()
        QTest.keyClick(done, Qt.Key_Space)
        qapp.processEvents()
        assert write_ui(session.document).text == bold
        while session.log.undo():
            pass
        assert write_ui(session.document).text == original
    finally:
        _close(window, pane, realizer, session, qapp)
