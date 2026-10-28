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
        toggle_all = pane.findChild(QToolButton, "formBuilder.group.all")
        assert toggle_all is not None
        if toggle_all.isChecked():
            toggle_all.click()
            _settle(qapp, pane)
        toggle_all.click()
        _settle(qapp, pane)
        _select(session, "titleLabel")
        _settle(qapp, pane)
        add = pane.findChild(QWidget, "formBuilder.addCustomProperty")
        assert add is not None
        add.setFocus()
        QTest.keyClick(add, Qt.Key_Space)
        qapp.processEvents()
        name = next(
            item for item in pane.findChildren(QLineEdit) if item.accessibleName() == "Custom property name"
        )
        name.setFocus()
        QTest.keyClicks(name, "requiredRole")
        QTest.keyClick(name, Qt.Key_Return)
        qapp.processEvents()
        if 'name="requiredRole"' not in write_ui(session.document).text:
            confirm = next(item for item in pane.findChildren(QWidget) if getattr(item, "text", lambda: "")() == "Add")
            confirm.click()
            qapp.processEvents()
        written = write_ui(session.document).text
        assert 'name="requiredRole"' in written, written
        assert 'stdset="0"' in written
        _expand_all(qapp, pane)
        add = pane.findChild(QWidget, "formBuilder.addCustomProperty")
        assert add is not None
        add.setFocus()
        QTest.keyClick(add, Qt.Key_Space)
        qapp.processEvents()
        name = next(
            item for item in pane.findChildren(QLineEdit) if item.accessibleName() == "Custom property name"
        )
        name.setFocus()
        QTest.keyClicks(name, "2nd")
        QTest.keyClick(name, Qt.Key_Return)
        qapp.processEvents()
        error = pane.findChild(QWidget, "formBuilder.rowError")
        assert error is not None and error.isVisible()
        assert "digit" in error.text()
        QTest.keyClick(name, Qt.Key_Escape)
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
        while session.log.undo():
            pass
        assert write_ui(session.document).text == original
    finally:
        _close(window, pane, realizer, session, qapp)
