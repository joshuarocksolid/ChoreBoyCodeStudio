# pyright: reportAttributeAccessIssue=false
"""Scalar editors: a value set in the inspector survives save, and a bad one does not."""

from __future__ import annotations

from typing import Tuple

import pytest

from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.writer import write_ui
from app.features.form_builder.qtside.inspector.api import GroupId
from app.features.form_builder.qtside.inspector.pane import InspectorPane
from app.features.form_builder.qtside.realize.api import Realizer
from app.qt.QtCore import Qt
from app.qt.QtGui import QKeySequence
from app.qt.QtTest import QTest
from app.qt.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
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
            _select(session, pane, "email")
            _events()
            scroll = pane.findChild(QScrollArea, "formBuilder.inspectorScroll")
            assert isinstance(scroll, QScrollArea)
            assert scroll.horizontalScrollBar().maximum() == 0
            row = _row(pane, "echoMode")
            combo = row.findChild(QComboBox)
            assert isinstance(combo, QComboBox)
            metrics = combo.fontMetrics()
            assert metrics.horizontalAdvance(combo.currentText() or "Normal") <= combo.width()
            # The row layout gives this column about 80 px. The reference
            # strings are wider than that, and forcing the column wider scrolls.
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
            combo.setCurrentIndex(combo.findText("Expanding"))
            _events()
            done = _popover().findChild(QPushButton, "formBuilder.popoverDone")
            assert isinstance(done, QPushButton)
            done.click()
            _events()
            pane.flush()
            assert "Expanding" in _xml(session)
        finally:
            _close(window, pane)


@pytest.mark.parity("R3-171")
def test_locale_choice_is_written_as_qt_names() -> None:
    with opened(_FORM) as (session, realizer):
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "email")
            row = _row(pane, "locale")
            button = row.findChild(QPushButton, "formBuilder.summary")
            assert isinstance(button, QPushButton)
            button.click()
            _events()
            done = _popover().findChild(QPushButton, "formBuilder.popoverDone")
            assert isinstance(done, QPushButton)
            done.click()
            _events()
            pane.flush()
            text = _xml(session)
            assert 'language="' in text
        finally:
            _close(window, pane)
