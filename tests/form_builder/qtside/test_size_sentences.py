# pyright: reportAttributeAccessIssue=false
"""Why-text and size segments that follow the live widget."""

from __future__ import annotations

import re
from typing import Tuple

import pytest

from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.writer import write_ui
from app.features.form_builder.qtside.inspector.api import GroupId
from app.features.form_builder.qtside.inspector.pane import InspectorPane
from app.features.form_builder.qtside.realize.api import Realizer
from app.qt.QtCore import Qt
from app.qt.QtTest import QTest
from app.qt.QtWidgets import (
    QApplication,
    QFormLayout,
    QLabel,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from tests.form_builder.qtside.support import form, opened

pytestmark = pytest.mark.usefixtures("qapp")

_LABELS = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>480</width><height>160</height></rect></property>
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="0">
    <widget class="QLabel" name="shortLabel"><property name="text"><string>No</string></property></widget>
   </item>
   <item row="0" column="1"><widget class="QLineEdit" name="short"/></item>
   <item row="1" column="0">
    <widget class="QLabel" name="longLabel"><property name="text"><string>Street address line</string></property></widget>
   </item>
   <item row="1" column="1"><widget class="QLineEdit" name="long"/></item>
  </layout>
""",
)

_LINE = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>320</width><height>120</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QLineEdit" name="email"/></item>
  </layout>
""",
)

_FREE = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>320</width><height>200</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QGroupBox" name="box">
     <property name="title"><string>Box</string></property>
     <widget class="QPushButton" name="free">
      <property name="geometry"><rect><x>8</x><y>24</y><width>80</width><height>24</height></rect></property>
      <property name="text"><string>Free</string></property>
     </widget>
    </widget>
   </item>
  </layout>
""",
)

_SHARE = (
    '<property name="sizePolicy"><sizepolicy hsizetype="Expanding" vsizetype="Preferred">'
    "<horstretch>%d</horstretch><verstretch>0</verstretch></sizepolicy></property>"
)


def _splitter(left: int, right: int) -> str:
    return form(
        'class="QSplitter" name="Form"',
        """
  <property name="orientation"><enum>Qt::Horizontal</enum></property>
  <property name="geometry"><rect><x>0</x><y>0</y><width>640</width><height>240</height></rect></property>
  <widget class="QTextEdit" name="left">%s</widget>
  <widget class="QTextEdit" name="right">%s</widget>
"""
        % (_SHARE % left, _SHARE % right),
    )


def _events() -> None:
    app = QApplication.instance()
    assert app is not None
    app.processEvents()


def _id(session: FormSession, name: str) -> object:
    found = session.document.by_name(name)
    assert found, name
    return found[0]


def _show_root(realizer: Realizer) -> QWidget:
    root = realizer.root_widget
    assert root is not None
    root.resize(640, 240)
    root.show()
    _events()
    return root


def _pane(session: FormSession, realizer: Realizer) -> Tuple[QWidget, InspectorPane]:
    window = QWidget()
    pane = InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None, parent=window)
    layout = QVBoxLayout(window)
    layout.addWidget(pane)
    window.resize(420, 720)
    window.show()
    _events()
    pane.set_group_expanded(GroupId.SIZE, True)
    pane.flush()
    _events()
    return window, pane


def _select(session: FormSession, pane: InspectorPane, name: str) -> None:
    session.selection.set((_id(session, name),), source=SelectionSource.PROGRAM)  # type: ignore[arg-type]
    pane.flush()
    _events()


def _close(window: QWidget, pane: InspectorPane) -> None:
    pane.dispose()
    window.close()
    window.deleteLater()
    _events()


def _why(pane: QWidget) -> QLabel:
    found = pane.findChild(QLabel, "formBuilder.sizeWhy")
    assert isinstance(found, QLabel) and found.isVisible()
    return found


def _column_width(layout: QFormLayout) -> int:
    role = getattr(getattr(QFormLayout, "ItemRole", QFormLayout), "LabelRole")
    widths = []
    for row in range(layout.rowCount()):
        item = layout.itemAt(row, role)
        if item is None:
            continue
        child = item.widget()
        if child is not None:
            widths.append(int(child.width()))
    assert len(widths) >= 2
    return max(widths)


def _label_sentence(text: str) -> str:
    start = text.find("This label is ")
    assert start >= 0, text
    end = text.find("longest label.")
    assert end > start, text
    return text[start : end + len("longest label.")]


def _growth_sentence(text: str) -> str:
    start = text.find("When the splitter grows")
    assert start >= 0, text
    end = text.find(".", start)
    assert end > start, text
    return text[start : end + 1]


def test_a_form_label_sentence_uses_the_live_label_and_column_widths() -> None:
    with opened(_LABELS) as (session, realizer):
        _show_root(realizer)
        window, pane = _pane(session, realizer)
        try:
            for name in ("shortLabel", "longLabel"):
                label = realizer.widget_for(_id(session, name))  # type: ignore[arg-type]
                assert label is not None
                assert isinstance(label, QLabel)
                parent = label.parentWidget()
                assert parent is not None
                form_layout = parent.layout()
                assert isinstance(form_layout, QFormLayout)
                column = _column_width(form_layout)
                _select(session, pane, name)
                sentence = _label_sentence(_why(pane).text())
                expected = (
                    "This label is %d px wide. The label column is %d px, the width of the longest label."
                    % (int(label.width()), column)
                )
                assert sentence == expected
                numbers = [int(item) for item in re.findall(r"\d+", sentence)]
                assert numbers
                assert all(number == int(label.width()) or number == column for number in numbers)
                assert "Labels are as wide as the longest label" not in _why(pane).text()
        finally:
            _close(window, pane)


def test_clicking_outlined_fill_on_a_line_edit_stays_outlined() -> None:
    with opened(_LINE) as (session, realizer):
        _show_root(realizer)
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "email")
            button = pane.findChild(QToolButton, "formBuilder.size.width.Fill")
            assert isinstance(button, QToolButton)
            assert button.isVisible()
            assert not button.isChecked()
            assert button.property("fbOutline") == "true"
            before_xml = write_ui(session.document).text
            before_log = len(session.log.entries())
            QTest.mouseClick(button, getattr(getattr(Qt, "MouseButton", Qt), "LeftButton"))
            _events()
            assert not button.isChecked()
            assert button.property("fbOutline") == "true"
            assert write_ui(session.document).text == before_xml
            assert len(session.log.entries()) == before_log
        finally:
            _close(window, pane)


def test_a_free_button_reports_its_stored_rectangle() -> None:
    with opened(_FREE) as (session, realizer):
        _show_root(realizer)
        window, pane = _pane(session, realizer)
        try:
            button = realizer.widget_for(_id(session, "free"))  # type: ignore[arg-type]
            assert button is not None
            _select(session, pane, "free")
            text = _why(pane).text()
            assert text == "%d × %d px, as stored. A layout would size it." % (
                int(button.width()),
                int(button.height()),
            )
            numbers = [int(item) for item in re.findall(r"\d+", text)]
            assert numbers == [int(button.width()), int(button.height())]
            body = pane.findChild(QWidget, "formBuilder.sizeBody")
            assert body is not None
            notes = [
                label.text()
                for label in body.findChildren(QLabel, "formBuilder.rowNote")
                if label.isVisible()
            ]
            assert notes.count("Not in a layout: its size is the rectangle in Placement.") == 1
            for axis in ("width", "height"):
                for word in ("Hug", "Fill", "Fixed"):
                    segment = pane.findChild(QToolButton, "formBuilder.size.%s.%s" % (axis, word))
                    assert isinstance(segment, QToolButton)
                    assert not segment.isEnabled()
                    assert segment.property("fbOutline") != "true"
        finally:
            _close(window, pane)


def test_a_grip_drag_and_a_shrink_leave_the_growth_sentence_alone() -> None:
    with opened(_splitter(1, 3)) as (session, realizer):
        root = _show_root(realizer)
        assert isinstance(root, QSplitter)
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "right")
            first = _growth_sentence(_why(pane).text())
            assert "of every" in first
            sizes = [int(size) for size in root.sizes()]
            root.setSizes([sizes[0] + 40, max(0, sizes[1] - 40)])
            _events()
            _events()
            assert _growth_sentence(_why(pane).text()) == first
            root.resize(max(80, int(root.width()) - 120), int(root.height()))
            _events()
            _events()
            assert _growth_sentence(_why(pane).text()) == first
            assert "spare room" not in first
        finally:
            _close(window, pane)


def test_a_splitter_pane_with_no_share_states_no_ratio() -> None:
    with opened(_splitter(0, 3)) as (session, realizer):
        root = _show_root(realizer)
        assert isinstance(root, QSplitter)
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "left")
            first = _growth_sentence(_why(pane).text())
            assert "of every" not in first
            assert re.search(r"\d+\s+of\s+\d+", first) is None
            sizes = [int(size) for size in root.sizes()]
            root.setSizes([sizes[0] + 40, max(0, sizes[1] - 40)])
            _events()
            _events()
            root.resize(max(80, int(root.width()) - 80), int(root.height()))
            _events()
            _events()
            assert _growth_sentence(_why(pane).text()) == first
            assert "spare room" not in _why(pane).text()
        finally:
            _close(window, pane)


def test_placement_spins_show_four_digits_at_236_px() -> None:
    with opened(_FREE) as (session, realizer):
        _show_root(realizer)
        window, pane = _pane(session, realizer)
        try:
            pane.setFixedWidth(236)
            window.resize(236, 800)
            pane.set_group_expanded(GroupId.PLACEMENT, True)
            _events()
            _select(session, pane, "free")
            row = pane.findChild(QWidget, "formBuilder.row.geometry")
            assert isinstance(row, QWidget)
            spins = [spin for spin in row.findChildren(QSpinBox) if spin.isVisible()]
            assert len(spins) >= 4
            for spin in spins:
                spin.setValue(1280)
            _events()
            for spin in spins:
                edit = spin.lineEdit()
                assert edit is not None
                text = edit.text()
                digits = text.replace(",", "").replace(" ", "").replace("\u202f", "")
                assert digits == "1280", text
                advance = int(edit.fontMetrics().horizontalAdvance(text))
                assert advance <= int(edit.contentsRect().width()), (text, advance, edit.contentsRect())
            scroll = pane.findChild(QScrollArea, "formBuilder.inspectorScroll")
            assert isinstance(scroll, QScrollArea)
            assert scroll.horizontalScrollBar().maximum() == 0
            _no_sideways_overlap(pane)
        finally:
            _close(window, pane)


def _no_sideways_overlap(pane: QWidget) -> None:
    for parent in [pane] + pane.findChildren(QWidget):
        shown = [item for item in parent.children() if isinstance(item, QWidget) and item.isVisible()]
        for index, first in enumerate(shown):
            for second in shown[index + 1 :]:
                both = first.geometry().intersected(second.geometry())
                assert both.isEmpty(), (first.objectName(), second.objectName(), both)
