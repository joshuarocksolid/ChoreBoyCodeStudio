# pyright: reportAttributeAccessIssue=false
"""Scalar editors: a value set in the inspector survives save, and a bad one does not."""

from __future__ import annotations

from typing import Tuple

import pytest

from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.values import DateValue
from app.features.form_builder.engine.ui4.writer import write_ui
from app.features.form_builder.qtside.inspector.api import GroupId
from app.features.form_builder.qtside.inspector.pane import InspectorPane
from app.features.form_builder.qtside.realize.api import Realizer
from app.features.form_builder.integration.canvas import FormCanvas
from app.features.form_builder.qtside.canvas.core.frame import Chip
from app.qt.QtCore import QLocale, Qt
from app.qt.QtGui import QAction, QKeySequence
from app.qt.QtTest import QTest
from app.qt.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStyle,
    QStyleOptionComboBox,
    QStyleOptionSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from tests.form_builder.qtside.support import form, opened

pytestmark = pytest.mark.usefixtures("qapp")

_FORM = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>420</width><height>320</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QLineEdit" name="email">
    <property name="echoMode"><enum>QLineEdit::Normal</enum></property>
   </widget></item>
   <item><widget class="QLineEdit" name="secret"/></item>
   <item><widget class="QLabel" name="caption"><property name="text"><string>Name</string></property></widget></item>
   <item><widget class="QDateEdit" name="when"/></item>
   <item><widget class="QTimeEdit" name="clock"/></item>
   <item><widget class="QDateTimeEdit" name="stamp"/></item>
   <item><widget class="QKeySequenceEdit" name="keys"/></item>
   <item><widget class="QDoubleSpinBox" name="amount"/></item>
   <item><widget class="QLineEdit" name="mark">
    <property name="passwordCharacter"><char><unicode>42</unicode></char></property>
   </widget></item>
  </layout>
""",
)


def _events() -> None:
    app = QApplication.instance()
    assert app is not None
    app.processEvents()


def _pane(session: FormSession, realizer: Realizer, width: int = 420) -> Tuple[QWidget, InspectorPane]:
    window = QWidget()
    pane = InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None, parent=window)
    layout = QVBoxLayout(window)
    layout.addWidget(pane)
    window.resize(width, 820)
    window.show()
    _events()
    pane.flush()
    return window, pane


def _select(session: FormSession, pane: InspectorPane, *names: str) -> None:
    ids = tuple(session.document.by_name(name)[0] for name in names)
    session.selection.set(ids, source=SelectionSource.PROGRAM)
    pane.flush()
    _events()


def _close(window: QWidget, pane: InspectorPane) -> None:
    pane.dispose()
    window.close()
    window.deleteLater()
    _events()


def _row(pane: QWidget, key: str) -> QWidget:
    for group in GroupId:
        button = pane.findChild(QWidget, "formBuilder.group.%s" % group.value)
        if isinstance(button, QWidget) and hasattr(button, "isChecked") and not button.isChecked():
            button.click()
    for _ in range(6):
        _events()
    pane.flush()
    _events()
    found = pane.findChild(QWidget, "formBuilder.row.%s" % key)
    assert isinstance(found, QWidget), key
    return found


def _xml(session: FormSession) -> str:
    return str(write_ui(session.document).text)


def _steps(session: FormSession) -> int:
    return len(session.log.entries())


def _key(name: str) -> object:
    return getattr(getattr(Qt, "Key", Qt), name)


def _mods(*names: str) -> object:
    enum = getattr(Qt, "KeyboardModifier", Qt)
    value = getattr(enum, "NoModifier")
    for name in names:
        value = value | getattr(enum, name + "Modifier")
    return value


def _flag(pop: QWidget, qt_name: str) -> QCheckBox:
    for box in pop.findChildren(QCheckBox):
        if box.toolTip() == qt_name:
            return box
    raise AssertionError(qt_name)


def _labeled(row: QWidget, text: str) -> QPushButton:
    for button in row.findChildren(QPushButton):
        if button.text() == text:
            return button
    raise AssertionError(text)


def _named(root: QWidget, object_name: str) -> QPushButton:
    for button in root.findChildren(QPushButton, object_name):
        if button.isVisible():
            return button
    raise AssertionError(object_name)


def _summary(row: QWidget) -> QPushButton:
    found = None
    for button in row.findChildren(QPushButton, "formBuilder.summary"):
        if button.isVisible():
            found = button
    assert isinstance(found, QPushButton)
    return found


def _popover() -> QWidget:
    found = None
    for candidate in QApplication.topLevelWidgets():
        for widget in candidate.findChildren(QWidget):
            if widget.objectName() != "formBuilder.rowPopover":
                continue
            if any(child.isVisible() for child in widget.findChildren(QWidget)):
                found = widget
    if isinstance(found, QWidget):
        return found
    raise AssertionError("popover")


def _caption(row: QWidget) -> str:
    label = row.findChild(QLabel, "formBuilder.rowError")
    if not isinstance(label, QLabel) or not label.isVisible():
        return ""
    return label.text()


@pytest.mark.parity("R3-153")
@pytest.mark.pain("P-18")
def test_echo_mode_password_stays_written() -> None:
    with opened(_FORM) as (session, realizer):
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "email")
            row = _row(pane, "echoMode")
            combo = row.findChild(QComboBox)
            assert isinstance(combo, QComboBox)
            assert combo.currentText() == "Normal"
            index = combo.findData("Password")
            assert index >= 0
            combo.setCurrentIndex(index)
            _events()
            pane.flush()
            text = _xml(session)
            assert "Password" in text
            saved = text
        finally:
            _close(window, pane)
    with opened(saved) as (session, realizer):
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "email")
            row = _row(pane, "echoMode")
            combo = row.findChild(QComboBox)
            assert isinstance(combo, QComboBox)
            assert combo.currentText() == "Password"
            assert "Password" in _xml(session)
        finally:
            _close(window, pane)


@pytest.mark.pain("P-18")
def test_unknown_enumerator_is_byte_identical_after_save() -> None:
    text = _FORM.replace("QLineEdit::Normal", "QLineEdit::SomeFutureMode")
    with opened(text) as (session, realizer):
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "email")
            row = _row(pane, "echoMode")
            combo = row.findChild(QComboBox)
            assert isinstance(combo, QComboBox)
            assert "kept as is" in combo.currentText()
            before = _xml(session)
            pane.flush()
            assert _xml(session) == before
            assert "SomeFutureMode" in before
        finally:
            _close(window, pane)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "M4.2: realizer.problems() is one flat list, so a row cannot show "
        "'Saved in the file. The canvas can't show this value.' for one property. "
        "M4.3d owns the caption widget."
    ),
)
def test_canvas_refusal_names_the_saved_value() -> None:
    with opened(_FORM) as (session, realizer):
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "email")
            row = _row(pane, "echoMode")
            assert "Saved in the file. The canvas can't show this value." in _caption(row)
        finally:
            _close(window, pane)


@pytest.mark.parity("R3-151")
def test_bool_space_commits_and_reset_removes_it() -> None:
    with opened(_FORM) as (session, realizer):
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "email")
            row = _row(pane, "enabled")
            box = row.findChild(QCheckBox)
            assert isinstance(box, QCheckBox)
            box.setFocus()
            QTest.keyClick(box, _key("Key_Space"))
            _events()
            pane.flush()
            assert "<bool>" in _xml(session)
            reset = row.findChild(QWidget, "formBuilder.rowReset")
            assert isinstance(reset, QWidget)
            reset.click() if hasattr(reset, "click") else None
            _events()
            pane.flush()
            assert 'name="enabled"' not in _xml(session)
        finally:
            _close(window, pane)


@pytest.mark.parity("R3-152")
def test_number_up_three_times_is_one_undo_step() -> None:
    with opened(_FORM) as (session, realizer):
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "email")
            row = _row(pane, "maxLength")
            spin = row.findChild(QSpinBox)
            assert isinstance(spin, QSpinBox)
            before = _steps(session)
            spin.setFocus()
            _events()
            for _ in range(3):
                QTest.keyClick(spin, _key("Key_Down"))
                _events()
            pane.flush()
            assert _steps(session) == before + 1
            assert "maxLength" in _xml(session)
            session.log.undo()
            pane.flush()
            _events()
            assert _steps(session) == before or "maxLength" not in _xml(session)
            spin.setFocus()
            QTest.keyClick(spin, _key("Key_Down"))
            _events()
            pane.flush()
            assert _steps(session) == before + 1
        finally:
            _close(window, pane)


def test_out_of_range_number_is_refused() -> None:
    with opened(_FORM) as (session, realizer):
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "email")
            row = _row(pane, "maxLength")
            spin = row.findChild(QSpinBox)
            assert isinstance(spin, QSpinBox)
            before = _xml(session)
            edit = spin.lineEdit()
            assert edit is not None
            edit.setFocus()
            edit.selectAll()
            QTest.keyClicks(edit, "99999")
            QTest.keyClick(edit, _key("Key_Return"))
            _events()
            pane.flush()
            assert "Use a number from 0 to 32767." in _caption(row)
            assert _xml(session) == before
        finally:
            _close(window, pane)


def test_non_number_is_refused() -> None:
    with opened(_FORM) as (session, realizer):
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "amount")
            row = _row(pane, "value")
            edit = row.findChild(QLineEdit)
            assert isinstance(edit, QLineEdit)
            before = _xml(session)
            edit.setFocus()
            edit.selectAll()
            QTest.keyClicks(edit, "nope")
            QTest.keyClick(edit, _key("Key_Return"))
            _events()
            pane.flush()
            assert _caption(row) == "Type a number, like 12."
            assert _xml(session) == before
        finally:
            _close(window, pane)


@pytest.mark.parity("R3-158")
def test_two_characters_in_a_char_field_are_refused() -> None:
    with opened(_FORM) as (session, realizer):
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "mark")
            row = _row(pane, "passwordCharacter")
            edit = row.findChild(QLineEdit)
            assert isinstance(edit, QLineEdit)
            before = _xml(session)
            edit.setFocus()
            edit.clear()
            QTest.keyClicks(edit, "ab")
            QTest.keyClick(edit, _key("Key_Return"))
            _events()
            pane.flush()
            assert _caption(row) == "Type one character."
            assert _xml(session) == before
        finally:
            _close(window, pane)


@pytest.mark.parity("R3-169")
def test_bad_date_and_time_are_refused() -> None:
    with opened(_FORM) as (session, realizer):
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "when")
            row = _row(pane, "date")
            edit = row.findChild(QLineEdit)
            assert isinstance(edit, QLineEdit)
            before = _xml(session)
            edit.setFocus()
            edit.selectAll()
            QTest.keyClicks(edit, "not-a-date")
            QTest.keyClick(edit, _key("Key_Return"))
            _events()
            pane.flush()
            assert _caption(row) == "Use a date like 10/28/2026."
            assert _xml(session) == before
            _select(session, pane, "clock")
            row = _row(pane, "time")
            edit = row.findChild(QLineEdit)
            assert isinstance(edit, QLineEdit)
            before = _xml(session)
            edit.setFocus()
            edit.selectAll()
            QTest.keyClicks(edit, "not-a-time")
            QTest.keyClick(edit, _key("Key_Return"))
            _events()
            pane.flush()
            assert _caption(row) == "Use a time like 2:30 PM."
            assert _xml(session) == before
        finally:
            _close(window, pane)


@pytest.mark.parametrize(
    "keys,written",
    (
        ((("Key_PageDown", ()),), "<year>2027</year><month>1</month><day>31</day>"),
        ((("Key_PageDown", ("Control",)),), "<year>2027</year><month>12</month><day>31</day>"),
        ((("Key_PageUp", ("Control",)),), "<year>2025</year><month>12</month><day>31</day>"),
    ),
)
def test_calendar_pages_by_month_and_by_year(keys: Tuple[Tuple[str, Tuple[str, ...]], ...], written: str) -> None:
    with opened(_FORM) as (session, realizer):
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "when")
            edit = _row(pane, "date").findChild(QLineEdit)
            assert isinstance(edit, QLineEdit)
            edit.setFocus()
            edit.selectAll()
            QTest.keyClicks(edit, "12/31/2026")
            QTest.keyClick(edit, _key("Key_Return"))
            _events()
            pane.flush()
            edit = _row(pane, "date").findChild(QLineEdit)
            assert isinstance(edit, QLineEdit)
            edit.setFocus()
            QTest.keyClick(edit, _key("Key_Down"), _mods("Alt"))
            _events()
            for name, mods in keys:
                focus = QApplication.focusWidget()
                assert isinstance(focus, QWidget)
                QTest.keyClick(focus, _key(name), _mods(*mods))
                _events()
            focus = QApplication.focusWidget()
            assert isinstance(focus, QWidget)
            QTest.keyClick(focus, _key("Key_Return"))
            _events()
            pane.flush()
            assert written in "".join(_xml(session).split())
        finally:
            _close(window, pane)


_FREE = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>320</width><height>200</height></rect></property>
  <widget class="QPushButton" name="free">
   <property name="geometry"><rect><x>8</x><y>24</y><width>80</width><height>24</height></rect></property>
   <property name="text"><string>Free</string></property>
  </widget>
""",
)


@pytest.mark.parity("R3-166")
def test_rect_fields_pair_above_300_and_stack_below() -> None:
    with opened(_FREE) as (session, realizer):
        window, pane = _pane(session, realizer, width=236)
        try:
            _select(session, pane, "free")
            pane.setFixedWidth(236)
            _events()
            row = _row(pane, "geometry")
            spins = [spin for spin in row.findChildren(QSpinBox) if spin.isVisible()]
            assert len(spins) >= 4
            narrow_y = {spin.mapTo(row, spin.rect().topLeft()).y() for spin in spins[:4]}
            assert len(narrow_y) >= 3
            pane.setFixedWidth(420)
            window.resize(420, 820)
            _events()
            pane.flush()
            spins = [spin for spin in row.findChildren(QSpinBox) if spin.isVisible()]
            points = [spin.mapTo(row, spin.rect().center()) for spin in spins[:4]]
            same_row = sum(1 for point in points[1:] if abs(point.y() - points[0].y()) < 8)
            assert same_row >= 1
        finally:
            _close(window, pane)


def test_reference_texts_fit_at_236() -> None:
    with opened(_FORM) as (session, realizer):
        window, pane = _pane(session, realizer, width=236)
        try:
            pane.setFixedWidth(236)
            for name in ("email", "when", "keys", "caption"):
                _select(session, pane, name)
                _events()
                scroll = pane.findChild(QScrollArea, "formBuilder.inspectorScroll")
                assert isinstance(scroll, QScrollArea)
                assert scroll.horizontalScrollBar().maximum() == 0, name
        finally:
            _close(window, pane)


def _text_width(widget: QWidget) -> int:
    if isinstance(widget, QComboBox):
        option = QStyleOptionComboBox()
        widget.initStyleOption(option)
        rect = widget.style().subControlRect(
            QStyle.ComplexControl.CC_ComboBox,
            option,
            QStyle.SubControl.SC_ComboBoxEditField,
            widget,
        )
        return int(rect.width())
    if isinstance(widget, QSpinBox):
        option = QStyleOptionSpinBox()
        widget.initStyleOption(option)
        rect = widget.style().subControlRect(
            QStyle.ComplexControl.CC_SpinBox,
            option,
            QStyle.SubControl.SC_SpinBoxEditField,
            widget,
        )
        return int(rect.width())
    return int(widget.contentsRect().width())


def _at_132(widget: QWidget, text: str) -> None:
    """The reference string fits this control when the control is the 132 px column."""
    host = QWidget()
    host.setFixedWidth(132)
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    widget.setParent(host)
    layout.addWidget(widget)
    host.show()
    _events()
    advance = widget.fontMetrics().horizontalAdvance(text)
    width = _text_width(widget)
    assert advance <= width, "%s needs %s px and the control shows %s" % (text, advance, width)
    host.close()
    host.deleteLater()
    _events()


def test_reference_texts_fit_in_a_132px_column() -> None:
    with opened(_FORM) as (session, realizer):
        window, pane = _pane(session, realizer, width=420)
        try:
            _select(session, pane, "email")
            length = _row(pane, "maxLength").findChild(QSpinBox)
            assert isinstance(length, QSpinBox)
            _at_132(length, "\u22122147483648")
            _select(session, pane, "stamp")
            stamp = _row(pane, "dateTime").findChild(QLineEdit)
            assert isinstance(stamp, QLineEdit)
            _at_132(stamp, "12/31/2026 11:59 PM")
            _select(session, pane, "keys")
            field = _row(pane, "keySequence").findChild(QLineEdit)
            assert isinstance(field, QLineEdit)
            _at_132(field, "Ctrl+Shift+Alt+F12")
            policy = _row(pane, "sizePolicy").findChild(QPushButton, "formBuilder.summary")
            assert isinstance(policy, QPushButton)
            policy.set_summary("Minimum expanding")  # type: ignore[attr-defined]
            host = QWidget()
            host.setFixedWidth(132)
            box = QVBoxLayout(host)
            box.setContentsMargins(0, 0, 0, 0)
            policy.setParent(host)
            box.addWidget(policy)
            host.show()
            _events()
            assert policy.toolTip() == "Minimum expanding"
            assert policy.width() <= 132
            host.close()
        finally:
            _close(window, pane)


def _row_width(window: QWidget, pane: InspectorPane, key: str, width: int) -> QWidget:
    """Resize until the row is ``width`` px wide (the pane adds margins and a scroll bar)."""
    row = _row(pane, key)
    for _ in range(4):
        delta = width - row.width()
        if delta == 0:
            break
        window.resize(window.width() + delta, window.height())
        _events()
        pane.flush()
        _events()
        row = _row(pane, key)
    assert row.width() == width
    return row


@pytest.mark.parametrize("width,stacked", ((236, True), (300, False)))
def test_echo_mode_shows_its_longest_name_unclipped(width: int, stacked: bool) -> None:
    with opened(_FORM) as (session, realizer):
        window, pane = _pane(session, realizer, width=width + 40)
        try:
            _select(session, pane, "email")
            row = _row_width(window, pane, "echoMode", width)
            combo = row.findChild(QComboBox)
            assert isinstance(combo, QComboBox)
            longest = combo.itemText(combo.findData("PasswordEchoOnEdit"))
            assert combo.fontMetrics().horizontalAdvance(longest) <= _text_width(combo)
            label = row.findChild(QLabel)
            assert isinstance(label, QLabel)
            top = combo.mapTo(row, combo.rect().topLeft()).y()
            bottom = label.mapTo(row, label.rect().bottomLeft()).y()
            assert (bottom < top) == stacked
        finally:
            _close(window, pane)


@pytest.mark.parity("R3-154")
def test_flags_escape_keeps_bytes_and_done_is_one_step() -> None:
    with opened(_FORM) as (session, realizer):
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "caption")
            row = _row(pane, "textInteractionFlags")
            button = _summary(row)
            before = _xml(session)
            steps = _steps(session)
            button.click()
            _events()
            pop = _popover()
            box = _flag(pop, "TextSelectableByMouse")
            box.setChecked(True)
            QTest.qWait(50)
            pop.setFocus()
            QTest.keyClick(pop, _key("Key_Escape"))
            QTest.qWait(50)
            pane.flush()
            assert _xml(session) == before
            assert _steps(session) == steps
            button = _summary(row)
            button.click()
            _events()
            pop = _popover()
            _flag(pop, "LinksAccessibleByMouse").setChecked(False)
            _flag(pop, "TextSelectableByMouse").setChecked(True)
            QTest.qWait(50)
            done = _named(pop, "formBuilder.popoverDone")
            done.click()
            QTest.qWait(50)
            pane.flush()
            xml = _xml(session)
            assert _steps(session) == steps + 1
            assert "TextSelectableByMouse" in xml
        finally:
            _close(window, pane)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "M4.2: Realizer._reset_property falls back to setProperty(name, fresh.property(name)), "
        "which PySide6 drops for a flags value, so a reverted textInteractionFlags stays on the "
        "canvas label and the row's unwritten default shows the cancelled flag."
    ),
)
def test_flags_escape_restores_the_canvas_widget() -> None:
    with opened(_FORM) as (session, realizer):
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "caption")
            row = _row(pane, "textInteractionFlags")
            _summary(row).click()
            _events()
            pop = _popover()
            _flag(pop, "TextSelectableByMouse").setChecked(True)
            QTest.qWait(50)
            pop.setFocus()
            QTest.keyClick(pop, _key("Key_Escape"))
            QTest.qWait(50)
            pane.flush()
            found = realizer.widget_for(session.document.by_name("caption")[0])
            assert isinstance(found, QLabel)
            canvas_label: QLabel = found
            flags = getattr(Qt, "TextInteractionFlag", Qt)
            assert canvas_label.textInteractionFlags() == getattr(flags, "LinksAccessibleByMouse")
            _summary(_row(pane, "textInteractionFlags")).click()
            _events()
            assert not _flag(_popover(), "TextSelectableByMouse").isChecked()
        finally:
            _close(window, pane)


@pytest.mark.parity("R3-168")
def test_key_sequence_records_cancels_and_clears() -> None:
    with opened(_FORM) as (session, realizer):
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "keys")
            row = _row(pane, "keySequence")
            record = _labeled(row, "Record")
            record.click()
            _events()
            field = row.findChild(QLineEdit)
            assert isinstance(field, QLineEdit)
            field.setFocus()
            QTest.qWait(50)
            QTest.keyClick(field, _key("Key_P"), _mods("Control", "Shift"))
            QTest.qWait(1200)
            _events()
            pane.flush()
            text = _xml(session)
            assert "Ctrl+Shift+P" in text or "Ctrl+P" in text
            before = _xml(session)
            record.click()
            _events()
            field = row.findChild(QLineEdit)
            assert isinstance(field, QLineEdit)
            QTest.keyClick(field, _key("Key_Escape"))
            QTest.qWait(80)
            pane.flush()
            assert _xml(session) == before
            record.click()
            _events()
            field = row.findChild(QLineEdit)
            assert isinstance(field, QLineEdit)
            QTest.keyClick(field, _key("Key_Backspace"))
            QTest.qWait(80)
            pane.flush()
            assert "Ctrl+Shift+P" not in _xml(session)
        finally:
            _close(window, pane)


@pytest.mark.parametrize(
    "key,mods,stored",
    (
        ("Key_Minus", ("Control",), "Ctrl+-"),
        ("Key_PageDown", ("Control",), "Ctrl+PgDown"),
        ("Key_Comma", ("Control",), "Ctrl+,"),
    ),
)
def test_recorded_shortcut_is_text_qt_can_read(key: str, mods: Tuple[str, ...], stored: str) -> None:
    with opened(_FORM) as (session, realizer):
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "keys")
            row = _row(pane, "keySequence")
            _labeled(row, "Record").click()
            _events()
            field = row.findChild(QLineEdit)
            assert isinstance(field, QLineEdit)
            field.setFocus()
            QTest.qWait(50)
            QTest.keyClick(field, _key(key), _mods(*mods))
            QTest.qWait(1200)
            _events()
            pane.flush()
            assert "<string>%s</string>" % stored in _xml(session)
            portable = getattr(getattr(QKeySequence, "SequenceFormat", QKeySequence), "PortableText")
            assert not QKeySequence.fromString(stored, portable).isEmpty()
        finally:
            _close(window, pane)


def test_two_echo_modes_show_mixed_and_write_both() -> None:
    with opened(_FORM) as (session, realizer):
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "email")
            row = _row(pane, "echoMode")
            combo = row.findChild(QComboBox)
            assert isinstance(combo, QComboBox)
            combo.setCurrentIndex(combo.findData("Password"))
            _events()
            pane.flush()
            _select(session, pane, "email", "secret")
            row = _row(pane, "echoMode")
            combo = row.findChild(QComboBox)
            assert isinstance(combo, QComboBox)
            assert combo.currentText() == "Mixed" or combo.currentIndex() < 0
            steps = _steps(session)
            combo.setCurrentIndex(combo.findData("NoEcho"))
            _events()
            pane.flush()
            text = _xml(session)
            assert text.count("NoEcho") >= 2
            assert _steps(session) == steps + 1
        finally:
            _close(window, pane)


_PAIR_OF_LINES = form(
    'class="QWidget" name="Form"',
    """
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QLineEdit" name="first">
    <property name="maxLength"><number>10</number></property>
    <property name="minimumSize"><size><width>10</width><height>20</height></size></property>
   </widget></item>
   <item><widget class="QLineEdit" name="second">
    <property name="maxLength"><number>20</number></property>
    <property name="minimumSize"><size><width>30</width><height>40</height></size></property>
   </widget></item>
  </layout>
""",
)


def _type_into(spin: QSpinBox, text: str) -> None:
    spin.setFocus()
    spin.lineEdit().selectAll()
    QTest.keyClicks(spin.lineEdit(), text)
    QTest.keyClick(spin.lineEdit(), _key("Key_Return"))
    _events()


def test_mixed_number_writes_the_typed_value_to_both() -> None:
    with opened(_PAIR_OF_LINES) as (session, realizer):
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "first")
            _row(pane, "maxLength")
            _select(session, pane, "first", "second")
            spin = _row(pane, "maxLength").findChild(QSpinBox)
            assert isinstance(spin, QSpinBox)
            assert spin.lineEdit().text() == ""
            _type_into(spin, "10")
            pane.flush()
            flat = "".join(_xml(session).split())
            assert flat.count('<propertyname="maxLength"><number>10</number>') == 2
        finally:
            _close(window, pane)


def test_mixed_size_keeps_both_heights_until_every_field_is_typed() -> None:
    with opened(_PAIR_OF_LINES) as (session, realizer):
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "first", "second")
            spins = _row(pane, "minimumSize").findChildren(QSpinBox)
            assert [spin.lineEdit().text() for spin in spins] == ["", ""]
            assert [spin.lineEdit().placeholderText() for spin in spins] == ["Mixed", "Mixed"]
            before = _xml(session)
            _type_into(spins[0], "50")
            pane.flush()
            assert _xml(session) == before
            spins = _row(pane, "minimumSize").findChildren(QSpinBox)
            _type_into(spins[1], "60")
            pane.flush()
            flat = "".join(_xml(session).split())
            assert flat.count("<size><width>50</width><height>60</height></size>") == 2
        finally:
            _close(window, pane)


@pytest.mark.parity("R3-167")
def test_size_policy_summary_names_the_policy() -> None:
    with opened(_FORM) as (session, realizer):
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "email")
            row = _row(pane, "sizePolicy")
            button = row.findChild(QPushButton, "formBuilder.summary")
            assert isinstance(button, QPushButton)
            assert button.toolTip()
            button.click()
            _events()
            combo = _popover().findChild(QComboBox)
            assert isinstance(combo, QComboBox)
            assert combo.findText("Minimum expanding") >= 0
            combo.setCurrentIndex(combo.findText("Minimum"))
            _events()
            done = _popover().findChild(QPushButton, "formBuilder.popoverDone")
            assert isinstance(done, QPushButton)
            done.click()
            _events()
            pane.flush()
            assert 'hsizetype="Minimum" vsizetype="Fixed"' in _xml(session)
        finally:
            _close(window, pane)


def test_unset_size_policy_shows_the_live_policy() -> None:
    with opened(_FORM) as (session, realizer):
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "caption")
            assert _summary(_row(pane, "sizePolicy")).text().startswith("Preferred × Preferred")
            _select(session, pane, "email")
            assert _summary(_row(pane, "sizePolicy")).text().startswith("Expanding × Fixed")
            before = _xml(session)
            _summary(_row(pane, "sizePolicy")).click()
            _events()
            combos = _popover().findChildren(QComboBox)
            assert [combo.currentData() for combo in combos[:2]] == ["Expanding", "Fixed"]
            done = _popover().findChild(QPushButton, "formBuilder.popoverDone")
            assert isinstance(done, QPushButton)
            done.click()
            _events()
            pane.flush()
            assert _xml(session) == before
        finally:
            _close(window, pane)


@pytest.mark.parity("R3-171")
def test_locale_choice_is_written_as_qt_names() -> None:
    with opened(_FORM) as (session, realizer):
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "email")
            row = _row(pane, "locale")
            before = _xml(session)
            _summary(row).click()
            _events()
            done = _popover().findChild(QPushButton, "formBuilder.popoverDone")
            assert isinstance(done, QPushButton)
            done.click()
            _events()
            pane.flush()
            assert _xml(session) == before
            row = _row(pane, "locale")
            _summary(row).click()
            _events()
            pop = _popover()
            field = pop.findChild(QLineEdit)
            assert isinstance(field, QLineEdit)
            QTest.keyClicks(field, "French")
            listing = pop.findChild(QListWidget)
            assert isinstance(listing, QListWidget)
            shown = [listing.item(i) for i in range(listing.count()) if not listing.item(i).isHidden()]
            listing.setCurrentItem(shown[0])
            _events()
            done = _popover().findChild(QPushButton, "formBuilder.popoverDone")
            assert isinstance(done, QPushButton)
            done.click()
            _events()
            pane.flush()
            assert '<locale language="French" country="France"/>' in _xml(session)
            assert _summary(_row(pane, "locale")).text().startswith("French (France)")
        finally:
            _close(window, pane)


_FLOATS = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>420</width><height>240</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QLineEdit" name="email">
    <property name="shopCount" stdset="0"><uint>4</uint></property>
    <property name="shopRate" stdset="0"><float>1.5</float></property>
    <property name="shopPoint" stdset="0"><pointf><x>1.25</x><y>2.5</y></pointf></property>
    <property name="shopSize" stdset="0"><sizef><width>3.5</width><height>4.5</height></sizef></property>
   </widget></item>
   <item><widget class="QGraphicsView" name="view"/></item>
  </layout>
""",
)

# No catalog widget exposes uint, float, QPointF or QSizeF. Those four ride on
# dynamic properties. QGraphicsView.sceneRect is a live QRectF.
_FLOAT_CASES = (
    ("email", "shopCount", "uint", "12"),
    ("email", "shopRate", "float", "2.5"),
    ("email", "shopPoint", "pointf", "8.5"),
    ("email", "shopSize", "sizef", "9.5"),
    ("view", "sceneRect", "rectf", "6.5"),
)


def _set_typed(row: QWidget, kind: str, text: str) -> None:
    if kind == "uint":
        field = row.findChild(QLineEdit)
        assert isinstance(field, QLineEdit)
        field.setFocus()
        field.selectAll()
        QTest.keyClicks(field, text)
        QTest.keyClick(field, _key("Key_Return"))
        return
    spin = row.findChild(QDoubleSpinBox)
    assert isinstance(spin, QDoubleSpinBox)
    spin.setFocus()
    spin.setValue(float(text))
    _events()


def _reset_row(row: QWidget) -> None:
    editor = row.findChild(QWidget)
    assert isinstance(editor, QWidget)
    editor.setFocus()
    _events()
    button = row.findChild(QToolButton, "formBuilder.rowReset")
    assert isinstance(button, QToolButton)
    assert button.isVisible()
    button.click()
    _events()


@pytest.mark.parametrize("owner,key,kind,text", _FLOAT_CASES)
def test_typed_value_round_trips(owner: str, key: str, kind: str, text: str) -> None:
    with opened(_FLOATS) as (session, realizer):
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, owner)
            row = _row(pane, key)
            _set_typed(row, kind, text)
            pane.flush()
            saved = _xml(session)
            assert text in saved
            assert key in saved
        finally:
            _close(window, pane)
    with opened(saved) as (session, realizer):
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, owner)
            row = _row(pane, key)
            assert text in _xml(session)
            _reset_row(row)
            pane.flush()
            assert key not in _xml(session)
        finally:
            _close(window, pane)


class _CanvasHost:
    def canvas_pressed(self) -> None:
        return None

    def narrate(self, sentence: str) -> None:
        return None

    def hover_changed(self, node: object) -> None:
        return None

    def zoom_changed(self, label: str) -> None:
        return None

    def open_problem(self, node: object) -> None:
        return None

    def open_layout_popover(self, node: object) -> None:
        return None

    def open_context_menu(self, node: object, at: object) -> None:
        return None


def _width_story(pane: QWidget) -> str:
    checked = ""
    for word in ("Hug", "Fill", "Fixed"):
        button = pane.findChild(QToolButton, "formBuilder.size.width.%s" % word)
        if isinstance(button, QToolButton) and button.isChecked():
            checked = word
    axis = pane.findChild(QWidget, "formBuilder.size.h")
    caption = ""
    if isinstance(axis, QWidget):
        note = axis.findChild(QLabel, "formBuilder.rowNote")
        if isinstance(note, QLabel) and note.isVisible():
            caption = note.text()
    return checked or caption


def test_size_policy_updates_the_size_group_and_the_chip_together() -> None:
    with opened(_FORM) as (session, realizer):
        host = QWidget()
        layout = QHBoxLayout(host)
        canvas = FormCanvas(session, realizer, _CanvasHost(), host)
        pane = InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None, parent=host)
        layout.addWidget(canvas, 1)
        layout.addWidget(pane)
        host.resize(1100, 640)
        host.show()
        _events()
        try:
            _select(session, pane, "email")
            before = _width_story(pane)
            row = _row(pane, "sizePolicy")
            summary = row.findChild(QPushButton, "formBuilder.summary")
            assert isinstance(summary, QPushButton)
            summary.click()
            _events()
            combo = _popover().findChild(QComboBox)
            assert isinstance(combo, QComboBox)
            combo.setCurrentIndex(combo.findText("Minimum"))
            for _ in range(8):
                _events()
            story = _width_story(pane)
            chips = [item.text for item in canvas.overlay().items if isinstance(item, Chip)]
            assert "Minimum" in story and story != before
            assert any("Minimum" in chip for chip in chips), (story, chips)
        finally:
            canvas.dispose()
            pane.dispose()
            host.close()
            host.deleteLater()
            _events()


_ACTIONS = form(
    'class="QMainWindow" name="MainWindow"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>480</width><height>240</height></rect></property>
  <widget class="QWidget" name="centralwidget">
   <layout class="QVBoxLayout" name="verticalLayout">
    <item><widget class="QKeySequenceEdit" name="keys"/></item>
   </layout>
  </widget>
  <action name="actionPrint">
   <property name="text"><string>Print</string></property>
   <property name="shortcut"><string>Ctrl+Alt+P</string></property>
  </action>
  <action name="actionCopy">
   <property name="text"><string>Save a copy</string></property>
   <property name="shortcut"><string>Ctrl+Alt+C</string></property>
  </action>
""",
)


def _record(row: QWidget, key: str, *mods: str) -> None:
    record = _labeled(row, "Record")
    record.click()
    _events()
    field = row.findChild(QLineEdit)
    assert isinstance(field, QLineEdit)
    field.setFocus()
    QTest.qWait(40)
    QTest.keyClick(field, _key(key), _mods(*mods) if mods else _mods())
    QTest.qWait(1200)


def test_key_sequence_warns_for_this_form_only() -> None:
    stray = QWidget()
    stray.setObjectName("ideWindow")
    ide = QAction("IDE Print", stray)
    ide.setObjectName("idePrint")
    ide.setShortcut(QKeySequence("Ctrl+Alt+Z"))
    stray.addAction(ide)
    same = QAction("IDE Same", stray)
    same.setObjectName("ideSame")
    same.setShortcut(QKeySequence("Ctrl+Alt+P"))
    stray.addAction(same)
    try:
        with opened(_ACTIONS) as (session, realizer):
            window, pane = _pane(session, realizer)
            try:
                _select(session, pane, "keys")
                row = _row(pane, "keySequence")
                _record(row, "Key_Z", "Control", "Alt")
                pane.flush()
                _events()
                row = _row(pane, "keySequence")
                warning = row.findChild(QLabel, "formBuilder.rowWarning")
                assert isinstance(warning, QLabel)
                assert not warning.isVisible(), warning.text()
                _record(row, "Key_P", "Control", "Alt")
                pane.flush()
                _events()
                row = _row(pane, "keySequence")
                warning = row.findChild(QLabel, "formBuilder.rowWarning")
                field = row.findChild(QLineEdit)
                shown = field.text() if isinstance(field, QLineEdit) else ""
                assert isinstance(warning, QLabel), (shown, _xml(session))
                assert warning.isVisible(), (warning.text(), shown, _xml(session))
                assert warning.text() == "Print already uses Ctrl+Alt+P."
                assert "Ctrl+Alt+P" in _xml(session)
            finally:
                _close(window, pane)
    finally:
        stray.deleteLater()
        _events()


_COMBINED_FLAGS = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>420</width><height>200</height></rect></property>
  <widget class="QLabel" name="caption">
   <property name="text"><string>Name</string></property>
   <property name="textInteractionFlags"><set>Qt::TextEditorInteraction</set></property>
  </widget>
""",
)


def test_flags_popover_hides_combined_enumerators() -> None:
    with opened(_COMBINED_FLAGS) as (session, realizer):
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "caption")
            row = _row(pane, "textInteractionFlags")
            summary = _summary(row)
            assert "Text editor" in summary.text()
            before = _xml(session)
            summary.click()
            _events()
            pop = _popover()
            labels = [box.text() for box in pop.findChildren(QCheckBox)]
            tips = [box.toolTip() for box in pop.findChildren(QCheckBox)]
            assert "No interaction" not in labels
            assert "Text editor" not in labels
            assert "Text browser" not in labels
            assert "NoTextInteraction" not in tips
            assert "TextEditorInteraction" not in tips
            assert "TextBrowserInteraction" not in tips
            assert "Select with mouse" in labels
            done = pop.findChild(QPushButton, "formBuilder.popoverDone")
            assert isinstance(done, QPushButton)
            done.click()
            _events()
            pane.flush()
            assert "TextEditorInteraction" in _xml(session)
            assert _xml(session) == before
        finally:
            _close(window, pane)


def test_size_policy_help_is_a_caption() -> None:
    with opened(_FORM) as (session, realizer):
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "email")
            _summary(_row(pane, "sizePolicy")).click()
            _events()
            pop = _popover()
            captions = pop.findChildren(QLabel, "formBuilder.policyHelp")
            combos = pop.findChildren(QComboBox)
            assert len(captions) >= 2 and len(combos) >= 2
            assert captions[0].text()
            assert captions[1].text()
            combos[0].setCurrentIndex(combos[0].findData("Fixed"))
            _events()
            assert captions[0].text() == "Exactly its size hint."
            combos[1].setCurrentIndex(combos[1].findData("Expanding"))
            _events()
            assert captions[1].text() == "Takes all the room it can."
        finally:
            _close(window, pane)


def test_unset_dates_locale_and_scene_rect_show_a_default() -> None:
    with opened(_FORM) as (session, realizer):
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "when")
            date = _row(pane, "date").findChild(QLineEdit)
            assert isinstance(date, QLineEdit)
            assert "/" in date.text() and date.text()[-4:].isdigit()
            assert date.property("fbState") == "unset"
            _select(session, pane, "clock")
            clock = _row(pane, "time").findChild(QLineEdit)
            assert isinstance(clock, QLineEdit) and ":" in clock.text()
            _select(session, pane, "stamp")
            stamp = _row(pane, "dateTime").findChild(QLineEdit)
            assert isinstance(stamp, QLineEdit)
            assert "/" in stamp.text() and ":" in stamp.text()
            _select(session, pane, "amount")
            amount = _row(pane, "value").findChild(QDoubleSpinBox)
            assert isinstance(amount, QDoubleSpinBox) and amount.text()
            _select(session, pane, "email")
            locale = _summary(_row(pane, "locale"))
            assert "(" in locale.text()
            assert locale.styleSheet()
        finally:
            _close(window, pane)
    with opened(_FLOATS) as (session, realizer):
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "view")
            row = _row(pane, "sceneRect")
            text = " ".join(box.text() for box in row.findChildren(QDoubleSpinBox))
            assert any(ch.isdigit() for ch in text), text
        finally:
            _close(window, pane)


def test_locale_down_enters_the_list_and_up_returns() -> None:
    with opened(_FORM) as (session, realizer):
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "email")
            _summary(_row(pane, "locale")).click()
            _events()
            pop = _popover()
            field = pop.findChild(QLineEdit)
            listing = pop.findChild(QListWidget)
            assert isinstance(field, QLineEdit) and isinstance(listing, QListWidget)
            field.setFocus()
            QTest.keyClick(field, _key("Key_Down"))
            _events()
            assert listing.hasFocus()
            listing.blockSignals(True)
            listing.setCurrentRow(0)
            listing.blockSignals(False)
            listing.setFocus()
            QTest.keyClick(listing, _key("Key_Up"))
            _events()
            assert field.hasFocus()
        finally:
            _close(window, pane)


def test_project_locale_ignores_a_german_system_locale() -> None:
    from app.features.form_builder.qtside.inspector.editors.dates import _format, _parse
    from app.features.form_builder.qtside.inspector.editors._number_box import format_real, parse_real

    previous = QLocale()
    QLocale.setDefault(QLocale("de_DE"))
    try:
        assert str(QLocale().decimalPoint()) == ","
        assert format_real(12.5, 1, strip=False) == "12.5"
        assert parse_real("12.5") == 12.5
        assert _format("date", DateValue(2026, 12, 31)) == "12/31/2026"
        assert _parse("date", "12/31/2026") == DateValue(2026, 12, 31)
    finally:
        QLocale.setDefault(previous)


_TWO_KEYS = form(
    'class="QWidget" name="Form"',
    """
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QKeySequenceEdit" name="keysA"><property name="keySequence"><string>Ctrl+Alt+P</string></property></widget></item>
   <item><widget class="QKeySequenceEdit" name="keysB"><property name="keySequence"><string>Ctrl+Alt+P</string></property></widget></item>
   <item><widget class="QKeySequenceEdit" name="keysC"><property name="keySequence"><string>Ctrl+Alt+Q</string></property></widget></item>
  </layout>
""",
)


def _shown_warning(pane: InspectorPane) -> str:
    warning = _row(pane, "keySequence").findChild(QLabel, "formBuilder.rowWarning")
    assert isinstance(warning, QLabel)
    return warning.text() if warning.isVisible() else ""


def test_key_clash_follows_the_selection() -> None:
    # The row keeps its editor across selections; the warning must name the other owner.
    with opened(_TWO_KEYS) as (session, realizer):
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "keysA")
            assert _shown_warning(pane) == "keysB already uses Ctrl+Alt+P."
            _select(session, pane, "keysB")
            assert _shown_warning(pane) == "keysA already uses Ctrl+Alt+P."
            _select(session, pane, "keysC")
            assert _shown_warning(pane) == ""
        finally:
            _close(window, pane)


def test_unticking_one_bit_of_a_combined_flag_writes_the_rest() -> None:
    with opened(_COMBINED_FLAGS) as (session, realizer):
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "caption")
            _summary(_row(pane, "textInteractionFlags")).click()
            _events()
            pop = _popover()
            boxes = {box.text(): box for box in pop.findChildren(QCheckBox)}
            assert boxes["Select with mouse"].isChecked() and boxes["Editable"].isChecked()
            boxes["Select with mouse"].click()
            _events()
            done = pop.findChild(QPushButton, "formBuilder.popoverDone")
            assert isinstance(done, QPushButton)
            done.click()
            _events()
            pane.flush()
            xml = _xml(session)
            assert "TextEditorInteraction" not in xml
            assert "TextSelectableByMouse" not in xml
            assert "Qt::TextSelectableByKeyboard" in xml and "Qt::TextEditable" in xml
        finally:
            _close(window, pane)
