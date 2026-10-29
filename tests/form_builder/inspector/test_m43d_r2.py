# pyright: reportAttributeAccessIssue=false
"""Round-2 seams and the review fixes that need a sample row or a measured row."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.ui4.values import StringListValue, StringValue
from app.features.form_builder.qtside.inspector import InspectorPane
from app.features.form_builder.qtside.inspector.api import (
    Choice,
    EditorKey,
    FlagBit,
    GroupId,
    Prop,
    RowSpec,
)
from app.features.form_builder.qtside.inspector.catalog import Registrations
from app.features.form_builder.qtside.inspector.editors import default_catalog
from app.features.form_builder.qtside.inspector.rich_html import unsupported_formatting
from app.qt.QtCore import Qt
from app.qt.QtGui import QTextCursor
from app.qt.QtTest import QTest
from app.qt.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QLabel,
    QPushButton,
    QLineEdit,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from app.qt.qt_compat import enum_value
from tests.form_builder.qtside.support import realize
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

_FLAGS = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <widget class="QWidget" name="dockA">
   <property name="features">
    <set>QDockWidget::DockWidgetClosable|QDockWidget::DockWidgetMovable</set>
   </property>
  </widget>
  <widget class="QWidget" name="dockB">
   <property name="features">
    <set>QDockWidget::DockWidgetMovable</set>
   </property>
  </widget>
  <widget class="QWidget" name="dockOnly">
   <property name="features">
    <set>QDockWidget::DockWidgetClosable</set>
   </property>
  </widget>
 </widget>
</ui>
"""

_RICH_LIMIT = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <widget class="QLabel" name="richLabel">
   <property name="text">
    <string>&lt;p style=" color:#ff0000;"&gt;Hello&lt;/p&gt;</string>
   </property>
   <property name="textFormat"><enum>Qt::RichText</enum></property>
  </widget>
 </widget>
</ui>
"""


def _sample_catalog():
    base = default_catalog()
    regs = Registrations()
    scope = regs.scope("sample")
    for key in ("bool", "enum", "string"):
        factory = base.editor(EditorKey(key))
        assert factory is not None
        scope.editor(EditorKey(key), factory)

    def swatches(_document, _owners):
        return (
            Choice("Red", StringValue("red")),
            Choice("Blue", StringValue("blue")),
        )

    scope.row(RowSpec("closable", GroupId.CONTENT, "Closable", "", FlagBit("features", "QDockWidget::DockWidgetClosable")))
    scope.row(RowSpec("swatch", GroupId.CONTENT, "Swatch", "", Prop("toolTip"), choices=swatches))
    scope.row(RowSpec("keptSample", GroupId.CONTENT, "Kept sample", "", Prop("statusTip"), editor="not-registered"))
    scope.row(RowSpec("forced", GroupId.CONTENT, "Forced", "", Prop("accessibleName"), editor="bool"))
    return regs.freeze()


def _open(qapp: QApplication, text: str, catalog=None):
    session, realizer = realize(text)
    window = QWidget()
    pane = InspectorPane(
        session,
        realizer,
        data_tab=False,
        on_leave=lambda: None,
        catalog=catalog,
        parent=window,
    )
    pane.apply_chrome(_CHROME)
    layout = QVBoxLayout(window)
    layout.addWidget(pane)
    window.resize(420, 760)
    window.show()
    qapp.setActiveWindow(window)
    qapp.processEvents()
    pane.flush()
    return window, pane, session, realizer


def _fit(qapp: QApplication, window: QWidget, pane: InspectorPane, row_target: int) -> None:
    scroll = pane.findChild(QScrollArea, "formBuilder.inspectorScroll")
    assert scroll is not None
    width = row_target + 60
    for _ in range(30):
        window.resize(width, 900)
        _settle(qapp, pane)
        row = scroll.viewport().width() - 16
        if row == row_target:
            return
        width += row_target - row


def _prop_text(session, name: str, prop: str) -> str:
    node = session.document.node(session.document.by_name(name)[0])
    entry = node.prop(prop)
    if entry is None:
        return ""
    return entry.value.text


def test_row_editor_key_and_unregistered_key(qapp: QApplication) -> None:
    window, pane, session, realizer = _open(qapp, _FLAGS, _sample_catalog())
    try:
        _select(session, "dockA")
        _settle(qapp, pane)
        forced = pane.findChild(QWidget, "formBuilder.row.forced")
        assert forced is not None
        assert forced.findChild(QCheckBox) is not None
        assert forced.findChild(QLineEdit) is None
        kept = pane.findChild(QWidget, "formBuilder.row.keptSample")
        assert kept is not None
        assert any("Kept as is" in label.text() for label in kept.findChildren(QLabel))
    finally:
        _close(window, pane, realizer, session, qapp)


def test_choice_dropdown_writes_the_choice_value(qapp: QApplication) -> None:
    window, pane, session, realizer = _open(qapp, _FLAGS, _sample_catalog())
    try:
        _select(session, "dockA")
        _settle(qapp, pane)
        row = pane.findChild(QWidget, "formBuilder.row.swatch")
        assert row is not None
        combo = row.findChild(QComboBox)
        assert combo is not None
        assert combo.itemText(0) == "Red"
        assert combo.itemText(1) == "Blue"
        combo.setCurrentIndex(1)
        _settle(qapp, pane)
        assert _prop_text(session, "dockA", "toolTip") == "blue"
    finally:
        _close(window, pane, realizer, session, qapp)


def test_flag_bit_edits_one_bit_and_resets_to_the_default(qapp: QApplication) -> None:
    window, pane, session, realizer = _open(qapp, _FLAGS, _sample_catalog())
    try:
        _select(session, "dockA")
        _settle(qapp, pane)
        row = pane.findChild(QWidget, "formBuilder.row.closable")
        assert row is not None
        box = row.findChild(QCheckBox)
        assert box is not None and box.isChecked()

        _select(session, "dockA", "dockB")
        _settle(qapp, pane)
        row = pane.findChild(QWidget, "formBuilder.row.closable")
        assert row is not None
        box = row.findChild(QCheckBox)
        assert box is not None
        assert enum_value(box.checkState()) == enum_value(Qt.PartiallyChecked)

        _select(session, "dockA")
        _settle(qapp, pane)
        row = pane.findChild(QWidget, "formBuilder.row.closable")
        assert row is not None
        box = row.findChild(QCheckBox)
        assert box is not None and box.isChecked()
        steps = len(session.log.entries())
        box.click()
        _settle(qapp, pane)
        assert len(session.log.entries()) == steps + 1
        assert session.log.undo_label() == "Change closable"
        written = _prop_text(session, "dockA", "features")
        assert "DockWidgetMovable" in written
        assert "DockWidgetClosable" not in written

        _select(session, "dockOnly")
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
        assert _prop_text(session, "dockOnly", "features") == ""
    finally:
        _close(window, pane, realizer, session, qapp)


def test_reset_overlay_keeps_the_editor_width(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp, _LABEL)
    try:
        _select(session, "titleLabel")
        _fit(qapp, window, pane, 236)
        row = pane.findChild(QWidget, "formBuilder.row.text")
        assert row is not None
        edit = row.findChild(QLineEdit)
        assert edit is not None
        before = edit.width()
        assert before >= 120
        edit.setText("Hello there")
        edit.editingFinished.emit()
        _settle(qapp, pane)
        edit.setFocus()
        qapp.processEvents()
        reset = row.findChild(QToolButton, "formBuilder.rowReset")
        assert reset is not None and reset.isVisible()
        assert edit.width() == before
        label = next(item for item in row.findChildren(QLabel) if item.text() == "Text")
        column = label.parentWidget()
        assert column is not None
        assert reset.x() + reset.width() <= column.x() + column.width() + 1
    finally:
        _close(window, pane, realizer, session, qapp)


def test_translation_caption_uses_the_row_width(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp, _LABEL)
    try:
        _select(session, "titleLabel")
        _fit(qapp, window, pane, 236)
        row = pane.findChild(QWidget, "formBuilder.row.text")
        assert row is not None
        disclosure = row.findChild(QWidget, "formBuilder.translation")
        assert disclosure is not None
        assert disclosure.width() > 132
        toggle = row.findChild(QToolButton, "formBuilder.translationToggle")
        assert toggle is not None
        toggle.click()
        qapp.processEvents()
        note = next(item for item in disclosure.findChildren(QLabel) if item.text() == "Note for the translator")
        assert note.fontMetrics().horizontalAdvance(note.text()) <= note.width() + 1
        box = disclosure.findChild(QCheckBox)
        assert box is not None
        box.click()
        qapp.processEvents()
        tag = disclosure.findChild(QLabel, "formBuilder.translationTag")
        assert tag is not None and tag.isVisible()
        assert tag.text() == "Not translated"
        assert tag.fontMetrics().horizontalAdvance(tag.text()) <= tag.width() + 1
    finally:
        _close(window, pane, realizer, session, qapp)


def test_long_property_names_elide_and_the_menu_hides_its_arrow(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp, _LABEL)
    try:
        _select(session, "nameEdit")
        _expand_all(qapp, pane)
        row = pane.findChild(QWidget, "formBuilder.row.inputMethodHints")
        assert row is not None
        label = next(item for item in row.findChildren(QLabel) if "inputMethodHints" in (item.toolTip() or item.text()))
        assert "inputMethodHints" in label.toolTip()
        assert "\u2026" in label.text()
        summary = row.findChild(QPushButton, "formBuilder.summary")
        assert summary is not None and "Imh" not in summary.accessibleName()
        add = pane.findChild(QWidget, "formBuilder.addCustomProperty")
        assert add is not None
        add.click()
        qapp.processEvents()
        name = next(item for item in pane.findChildren(QLineEdit) if item.accessibleName() == "Custom property name")
        name.setText("roleText")
        name.returnPressed.emit()
        _settle(qapp, pane)
        _expand_all(qapp, pane)
        custom = pane.findChild(QWidget, "formBuilder.row.roleText")
        assert custom is not None
        menu = custom.findChild(QToolButton, "formBuilder.customMenu")
        assert menu is not None
        assert "menu-indicator" in menu.styleSheet()
        assert "image: none" in menu.styleSheet()
    finally:
        _close(window, pane, realizer, session, qapp)


def test_unsupported_rich_text_opens_in_source(qapp: QApplication) -> None:
    assert unsupported_formatting('<p style=" color:#ff0000;">Hello</p>')
    assert not unsupported_formatting("<p>Hello</p>")
    window, pane, session, realizer = _pane(qapp, _RICH_LIMIT)
    try:
        _select(session, "richLabel")
        _settle(qapp, pane)
        row = pane.findChild(QWidget, "formBuilder.row.text")
        assert row is not None
        summary = row.findChild(QWidget, "formBuilder.summary")
        assert summary is not None
        summary.click()
        qapp.processEvents()
        popover = window.findChild(QWidget, "formBuilder.rowPopover")
        assert popover is not None
        limit = popover.findChild(QLabel, "formBuilder.richLimit")
        assert limit is not None and limit.isVisible()
        assert limit.text() == "This text has formatting the editor can't keep."
        source = next(item for item in popover.findChildren(QWidget) if item.accessibleName() == "Text: HTML source")
        assert source.isVisible()
        assert "color:" in _prop_text(session, "richLabel", "text")
    finally:
        _close(window, pane, realizer, session, qapp)


def test_ctrl_b_toggles_bold_off(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp, _LABEL)
    try:
        _select(session, "richLabel")
        _settle(qapp, pane)
        row = pane.findChild(QWidget, "formBuilder.row.text")
        assert row is not None
        summary = row.findChild(QWidget, "formBuilder.summary")
        assert summary is not None
        summary.click()
        qapp.processEvents()
        popover = window.findChild(QWidget, "formBuilder.rowPopover")
        assert popover is not None
        formatted = next(item for item in popover.findChildren(QWidget) if item.accessibleName() == "Text: formatted text")
        cursor = formatted.textCursor()
        cursor.select(QTextCursor.Document)
        formatted.setTextCursor(cursor)
        QTest.keyClick(formatted, Qt.Key_B, Qt.ControlModifier)
        QTest.keyClick(formatted, Qt.Key_B, Qt.ControlModifier)
        qapp.processEvents()
        done = popover.findChild(QWidget, "formBuilder.popoverDone")
        assert done is not None
        done.click()
        qapp.processEvents()
        assert "font-weight:600" not in _prop_text(session, "richLabel", "text")
    finally:
        _close(window, pane, realizer, session, qapp)


def test_string_list_close_drops_the_trailing_empty_row(qapp: QApplication) -> None:
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
        popover = window.findChild(QWidget, "formBuilder.rowPopover")
        assert popover is not None
        edit = popover.findChild(QLineEdit)
        assert edit is not None
        edit.setFocus()
        QTest.keyClick(edit, Qt.Key_Down)
        QTest.keyClick(edit, Qt.Key_Down)
        QTest.keyClick(edit, Qt.Key_Return)
        qapp.processEvents()
        done = popover.findChild(QWidget, "formBuilder.popoverDone")
        assert done is not None
        done.click()
        qapp.processEvents()
        tags = session.document.node(session.document.by_name("Form")[0]).value("tags")
        assert isinstance(tags, StringListValue)
        assert tags.items == ("Red", "Green", "Blue")
    finally:
        _close(window, pane, realizer, session, qapp)


_GROUP = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <widget class="QGroupBox" name="box">
   <property name="title"><string>Box</string></property>
  </widget>
 </widget>
</ui>
"""


def test_an_unset_group_box_title_alignment_shows_left(qapp: QApplication) -> None:
    """UX-CONT-014: Title alignment."""
    # The live default is ``AlignLeft|AlignLeading`` without a scope.
    window, pane, session, realizer = _open(qapp, _GROUP)
    try:
        _select(session, "box")
        _expand_all(qapp, pane)
        _settle(qapp, pane)
        row = pane.findChild(QWidget, "formBuilder.row.titleAlignment")
        assert row is not None
        combo = row.findChild(QComboBox)
        assert combo is not None
        assert combo.currentText() == "Left"
    finally:
        _close(window, pane, realizer, session, qapp)
