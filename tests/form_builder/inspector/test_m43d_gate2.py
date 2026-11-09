# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false
"""Round-2 gate: Mixed in the text popover, popover titles, rich-text sizes
under a large app font, and the flag-bit seam with several owners."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.commands.catalog import SetProperty
from app.features.form_builder.engine.ui4.values import SetValue, StringValue
from app.features.form_builder.qtside.inspector.rich_html import Paragraph, Span, stable_html
from app.qt.QtGui import QFont, QTextCursor
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QCheckBox, QComboBox, QLabel, QLineEdit, QPlainTextEdit, QToolButton, QWidget
from app.qt.QtCore import Qt
from tests.form_builder.inspector.test_m43d_r2 import _FLAGS, _open, _sample_catalog
from tests.form_builder.qtside.test_m43d_text import (
    _CHROME,
    _LABEL,
    _LIST,
    _close,
    _expand_all,
    _pane,
    _select,
    _settle,
)

pytestmark = pytest.mark.unit

_TIPS = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <widget class="QLabel" name="one">
   <property name="toolTip"><string>First
line</string></property>
  </widget>
  <widget class="QLabel" name="two">
   <property name="toolTip"><string>Other
text</string></property>
  </widget>
 </widget>
</ui>
"""


def _rich_form(html: str) -> str:
    escaped = html.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <widget class="QLabel" name="richLabel">
   <property name="text"><string>%s</string></property>
   <property name="textFormat"><enum>Qt::RichText</enum></property>
  </widget>
 </widget>
</ui>
""" % escaped


def _popover(window: QWidget) -> QWidget:
    shown = [item for item in window.findChildren(QWidget, "formBuilder.rowPopover") if item.isVisible()]
    assert shown
    return shown[-1]


def _value(session, name: str, prop: str):
    node = session.document.node(session.document.by_name(name)[0])
    entry = node.prop(prop)
    return None if entry is None else entry.value


def test_mixed_text_popover_shows_mixed(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp, _TIPS)
    try:
        _select(session, "one", "two")
        _settle(qapp, pane)
        row = pane.findChild(QWidget, "formBuilder.row.toolTip")
        assert row is not None
        summary = row.findChild(QWidget, "formBuilder.summary")
        assert summary is not None
        assert summary.property("fbState") == "mixed"
        summary.click()
        qapp.processEvents()
        edit = _popover(window).findChild(QPlainTextEdit)
        assert edit is not None
        assert edit.toPlainText() == ""
        assert edit.placeholderText() == "Mixed"
        assert edit.property("fbState") == "mixed"
    finally:
        _close(window, pane, realizer, session, qapp)


def test_popover_titles_for_all_properties_and_custom_rows(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp, _LIST)
    try:
        _select(session, "Form")
        _expand_all(qapp, pane)
        row = pane.findChild(QWidget, "formBuilder.row.tags")
        assert row is not None
        button = row.findChild(QWidget, "formBuilder.summary")
        assert button is not None
        button.click()
        qapp.processEvents()
        popover = _popover(window)
        title = popover.findChild(QLabel, "formBuilder.popoverTitle")
        caption = popover.findChild(QLabel, "formBuilder.popoverQtName")
        assert title is not None and caption is None
        assert title.text() == "tags"
        box = QCheckBox("Probe", popover)
        box.ensurePolished()
        assert box.palette().color(box.foregroundRole()).name().lower() == _CHROME.text.lower()
        done = popover.findChild(QWidget, "formBuilder.popoverDone")
        assert done is not None
        done.click()
        qapp.processEvents()

        rows = [
            row for row in pane.findChildren(QWidget, "formBuilder.row.font")
            if any(label.text() == "font" for label in row.findChildren(QLabel))
        ]
        assert rows
        button = rows[-1].findChild(QWidget, "formBuilder.summary")
        assert button is not None
        button.click()
        qapp.processEvents()
        popover = _popover(window)
        title = popover.findChild(QLabel, "formBuilder.popoverTitle")
        caption = popover.findChild(QLabel, "formBuilder.popoverQtName")
        assert title is not None and caption is not None
        assert (title.text(), caption.text()) == ("Font", "font")
    finally:
        _close(window, pane, realizer, session, qapp)


def test_rich_text_keeps_sizes_under_a_large_app_font(qapp: QApplication) -> None:
    original = Paragraph((Span("Plain "), Span("Big", size="large"), Span(" tiny", size="small")))
    html = stable_html((original,))
    window, pane, session, realizer = _pane(qapp, _rich_form(html))
    saved = QFont(qapp.font())
    try:
        font = QFont(saved)
        font.setPointSize(13)
        qapp.setFont(font)
        _select(session, "richLabel")
        _settle(qapp, pane)
        row = pane.findChild(QWidget, "formBuilder.row.text")
        assert row is not None
        summary = row.findChild(QWidget, "formBuilder.summary")
        assert summary is not None
        summary.click()
        qapp.processEvents()
        popover = _popover(window)
        formatted = next(
            item for item in popover.findChildren(QWidget) if item.accessibleName() == "Text: formatted text"
        )
        cursor = formatted.textCursor()
        cursor.movePosition(QTextCursor.Start)
        formatted.setTextCursor(cursor)
        QTest.keyClicks(formatted, "A")
        QTest.keyClick(formatted, Qt.Key_Backspace)
        qapp.processEvents()
        assert _value(session, "richLabel", "text").text == html
    finally:
        qapp.setFont(saved)
        _close(window, pane, realizer, session, qapp)


def test_flag_bit_several_owners_is_one_step_and_reset_keeps_other_bits(qapp: QApplication) -> None:
    window, pane, session, realizer = _open(qapp, _FLAGS, _sample_catalog())
    try:
        _select(session, "dockA", "dockB")
        _settle(qapp, pane)
        row = pane.findChild(QWidget, "formBuilder.row.closable")
        assert row is not None
        box = row.findChild(QCheckBox)
        assert box is not None
        steps = len(session.log.entries())
        box.click()
        _settle(qapp, pane)
        assert len(session.log.entries()) == steps + 1
        for name in ("dockA", "dockB"):
            keys = _value(session, name, "features").keys()
            assert ("QDockWidget", "DockWidgetClosable") in keys
            assert ("QDockWidget", "DockWidgetMovable") in keys
        session.log.undo()
        assert _value(session, "dockB", "features") == SetValue("QDockWidget::DockWidgetMovable")

        _select(session, "dockA")
        _settle(qapp, pane)
        row = pane.findChild(QWidget, "formBuilder.row.closable")
        assert row is not None
        box = row.findChild(QCheckBox)
        assert box is not None
        box.setFocus()
        qapp.processEvents()
        reset = row.findChild(QToolButton, "formBuilder.rowReset")
        assert reset is not None and reset.isVisible()
        reset.click()
        _settle(qapp, pane)
        assert _value(session, "dockA", "features").keys() == (("QDockWidget", "DockWidgetMovable"),)
    finally:
        _close(window, pane, realizer, session, qapp)



def test_choice_dropdown_says_mixed_when_owners_differ(qapp: QApplication) -> None:
    window, pane, session, realizer = _open(qapp, _FLAGS, _sample_catalog())
    try:
        _select(session, "dockA")
        _settle(qapp, pane)
        row = pane.findChild(QWidget, "formBuilder.row.swatch")
        assert row is not None
        combo = row.findChild(QComboBox)
        assert combo is not None
        combo.setCurrentIndex(0)
        _settle(qapp, pane)
        _select(session, "dockA", "dockB")
        _settle(qapp, pane)
        row = pane.findChild(QWidget, "formBuilder.row.swatch")
        assert row is not None
        combo = row.findChild(QComboBox)
        assert combo is not None
        assert combo.currentIndex() == -1
        assert combo.placeholderText() == "Mixed"
        assert combo.property("fbState") == "mixed"
    finally:
        _close(window, pane, realizer, session, qapp)


def test_rich_text_bar_lights_only_the_state_of_the_cursor(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp, _rich_form(stable_html((Paragraph((Span("Hello"),)),))))
    try:
        _select(session, "richLabel")
        _settle(qapp, pane)
        row = pane.findChild(QWidget, "formBuilder.row.text")
        assert row is not None
        summary = row.findChild(QWidget, "formBuilder.summary")
        assert summary is not None
        summary.click()
        qapp.processEvents()
        popover = _popover(window)

        def button(name: str):
            return next(item for item in popover.findChildren(QWidget) if item.accessibleName() == name)

        button("Larger").click()
        button("Link").click()
        qapp.processEvents()
        assert not button("Larger").isChecked()
        assert not button("Link").isChecked()
        button("Bulleted list").click()
        qapp.processEvents()
        assert button("Bulleted list").isChecked()
        assert not button("Numbered list").isChecked()
    finally:
        _close(window, pane, realizer, session, qapp)


def _foreground(label: QLabel) -> str:
    label.ensurePolished()
    return label.palette().color(label.foregroundRole()).name().lower()


def test_refusal_captions_take_the_error_colour(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp, _LABEL)
    try:
        _select(session, "titleLabel")
        _expand_all(qapp, pane)
        add = pane.findChild(QWidget, "formBuilder.addCustomProperty")
        assert add is not None
        add.click()
        qapp.processEvents()
        form = pane.findChild(QWidget, "formBuilder.customProperties")
        assert form is not None
        name = form.findChild(QLineEdit)
        assert name is not None
        name.setText("2nd")
        QTest.keyClick(name, Qt.Key_Return)
        qapp.processEvents()
        error = form.findChild(QLabel, "formBuilder.rowError")
        assert error is not None and error.isVisible()
        assert _foreground(error) == _CHROME.error.lower()

        row = pane.findChild(QWidget, "formBuilder.row.buddy")
        assert row is not None
        edit = row.findChild(QLineEdit)
        assert edit is not None
        edit.setText("missing")
        edit.editingFinished.emit()
        qapp.processEvents()
        refusals = [label for label in row.findChildren(QLabel, "formBuilder.rowError") if label.isVisible()]
        assert refusals
        assert all(_foreground(label) == _CHROME.error.lower() for label in refusals)
    finally:
        _close(window, pane, realizer, session, qapp)


_SHORTCUTS = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QMainWindow" name="Form">
  <widget class="QWidget" name="central">
   <layout class="QVBoxLayout" name="v">
    <item>
     <widget class="QPushButton" name="okButton">
      <property name="shortcut"><string>Ctrl+Return</string></property>
     </widget>
    </item>
    <item>
     <widget class="QKeySequenceEdit" name="keys">
      <property name="keySequence"><string>Alt+K</string></property>
     </widget>
    </item>
   </layout>
  </widget>
  <action name="actionSave">
   <property name="shortcut"><string>Ctrl+S</string></property>
  </action>
  <action name="actionNone"/>
 </widget>
</ui>
"""


def test_form_shortcuts_come_from_the_document(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp, _SHORTCUTS)
    try:
        _select(session, "okButton")
        _expand_all(qapp, pane)
        row = pane.findChild(QWidget, "formBuilder.row.shortcut")
        assert row is not None
        found = row.form_shortcuts()
        assert dict(found) == {"Ctrl+Return": "okButton", "Alt+K": "keys", "Ctrl+S": "actionSave"}
        with pytest.raises(TypeError):
            found["Ctrl+Q"] = "x"  # type: ignore[index]
        button = session.document.by_name("okButton")[0]
        session.log.execute(SetProperty(button, "shortcut", StringValue("Ctrl+O")))
        assert dict(row.form_shortcuts())["Ctrl+O"] == "okButton"
        assert "Ctrl+Return" not in row.form_shortcuts()
    finally:
        _close(window, pane, realizer, session, qapp)
