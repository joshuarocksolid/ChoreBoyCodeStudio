# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""The row popover shell (UX-PED-003): placement, keys, focus and what closes it."""

from __future__ import annotations

from typing import List

import pytest

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.qtside.inspector._services import Services
from app.features.form_builder.qtside.inspector.editors import default_catalog
from app.features.form_builder.qtside.inspector.editors._popover import RowPopover, SummaryButton
from app.qt.QtCore import QPoint, Qt  # type: ignore[reportAttributeAccessIssue]
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QLineEdit, QPushButton, QWidget
from tests.form_builder.qtside.support import open_session

pytestmark = [pytest.mark.usefixtures("qapp"), pytest.mark.unit]

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form"><widget class="QLineEdit" name="field"/></widget>
 <resources/>
 <connections/>
</ui>
"""


def QRectInside(inner: QWidget, outer: QWidget) -> bool:
    return outer.rect().contains(inner.geometry())


def _key(name: str):  # type: ignore[no-untyped-def]
    return getattr(getattr(Qt, "Key", Qt), name)


def _settle(qapp: QApplication) -> None:
    for _ in range(3):
        qapp.processEvents()


class _Host:
    """The popover's host: a real Services over a real session."""

    def __init__(self) -> None:
        self.session = open_session(_FORM, "/tmp/cbcs-popover-shell.ui")
        self.services = Services(self.session, default_catalog(), None)

    def close(self) -> None:
        self.session.dispose()


def _window(width: int, height: int) -> QWidget:
    window = QWidget()
    window.resize(width, height)
    window.show()
    return window


def _row(window: QWidget, x: int, y: int, width: int, height: int = 24) -> QWidget:
    row = QWidget(window)
    row.setGeometry(x, y, width, height)
    row.show()
    return row


def test_small_popover_is_the_row_width_and_does_not_cover_the_row(qapp: QApplication) -> None:
    host = _Host()
    window = _window(400, 300)
    row = _row(window, 20, 60, 236)
    popover = RowPopover(row, host.services, row_label="Test row", session_label="Change test row")
    try:
        popover.open_popover()
        _settle(qapp)
        assert popover.width() == 236
        assert popover.geometry().top() >= row.geometry().bottom()
        assert popover.geometry().left() == row.geometry().left()
        assert QRectInside(popover, window)
    finally:
        popover.done()
        _settle(qapp)
        host.close()
        window.close()


def test_popover_flips_above_the_row_near_the_bottom_and_stays_inside(qapp: QApplication) -> None:
    host = _Host()
    window = _window(400, 300)
    row = _row(window, 20, 262, 236)
    popover = RowPopover(row, host.services, row_label="Test row", session_label="Change test row")
    try:
        popover.open_popover()
        _settle(qapp)
        assert popover.geometry().bottom() <= row.geometry().top()
        assert QRectInside(popover, window)
        assert popover.width() == 236
    finally:
        popover.done()
        _settle(qapp)
        host.close()
        window.close()


def test_large_popover_is_320_to_480_wide_and_grows_to_the_left(qapp: QApplication) -> None:
    host = _Host()
    window = _window(640, 400)
    row = _row(window, 380, 60, 236)
    popover = RowPopover(row, host.services, row_label="Palette", session_label="Change palette", large=True)
    try:
        popover.open_popover()
        _settle(qapp)
        assert popover.width() == 320
        assert popover.geometry().right() == row.geometry().right()
        assert QRectInside(popover, window)
    finally:
        popover.done()
        _settle(qapp)
        host.close()
        window.close()


def _open(qapp: QApplication, host: _Host, window: QWidget, row: QWidget, fields: List[QLineEdit]):  # type: ignore[no-untyped-def]
    popover = RowPopover(row, host.services, row_label="Test row", session_label="Change test row")
    for field in fields:
        popover.body().addWidget(field)
    popover.open_popover()
    _settle(qapp)
    return popover


def test_tab_and_shift_tab_stay_inside_the_popover(qapp: QApplication) -> None:
    host = _Host()
    window = _window(400, 300)
    row = _row(window, 20, 40, 236)
    first, second = QLineEdit(), QLineEdit()
    popover = _open(qapp, host, window, row, [first, second])
    try:
        first.setFocus()
        _settle(qapp)
        QTest.keyClick(first, _key("Key_Tab"))
        _settle(qapp)
        assert QApplication.focusWidget() is second
        QTest.keyClick(second, _key("Key_Tab"))
        _settle(qapp)
        assert QApplication.focusWidget() is not None and popover.isAncestorOf(QApplication.focusWidget())
        QTest.keyClick(QApplication.focusWidget(), _key("Key_Backtab"))
        _settle(qapp)
        assert QApplication.focusWidget() is second
    finally:
        popover.done()
        _settle(qapp)
        host.close()
        window.close()


def test_escape_closes_and_focus_returns_to_the_summary(qapp: QApplication) -> None:
    host = _Host()
    window = _window(400, 300)
    row = _row(window, 20, 40, 236)
    summary = SummaryButton("Test row", row)
    summary.setGeometry(0, 0, 236, 24)
    summary.show()
    field = QLineEdit()
    popover = RowPopover(row, host.services, row_label="Test row", session_label="Change test row", anchor=summary)
    popover.body().addWidget(field)
    popover.open_popover()
    _settle(qapp)
    try:
        field.setFocus()
        _settle(qapp)
        QTest.keyClick(field, _key("Key_Escape"))
        _settle(qapp)
        assert popover.closed
        assert not popover.isVisible()
        assert QApplication.focusWidget() is summary
    finally:
        host.close()
        window.close()


def test_done_and_click_outside_keep_focus_on_the_summary(qapp: QApplication) -> None:
    host = _Host()
    window = _window(400, 300)
    row = _row(window, 20, 40, 236)
    summary = SummaryButton("Test row", row)
    summary.setGeometry(0, 0, 236, 24)
    summary.show()
    other = QPushButton("Elsewhere", window)
    other.setGeometry(20, 200, 120, 24)
    other.show()
    popover = RowPopover(row, host.services, row_label="Test row", session_label="Change test row", anchor=summary)
    popover.open_popover()
    _settle(qapp)
    try:
        done = popover.findChild(QPushButton, "formBuilder.popoverDone")
        assert done is not None
        done.setFocus()
        _settle(qapp)
        done.click()
        _settle(qapp)
        assert popover.closed and QApplication.focusWidget() is summary

        popover = RowPopover(row, host.services, row_label="Test row", session_label="Change test row", anchor=summary)
        popover.open_popover()
        _settle(qapp)
        QTest.mouseClick(other, _mouse("LeftButton"), _mods("NoModifier"), QPoint(4, 4))
        _settle(qapp)
        assert popover.closed
        assert QApplication.focusWidget() is summary
    finally:
        host.close()
        window.close()


def test_summary_opens_on_enter_and_alt_down_and_elides_with_the_full_text_in_the_tooltip(qapp: QApplication) -> None:
    window = _window(200, 80)
    summary = SummaryButton("Font", window)
    summary.setGeometry(0, 0, 90, 24)
    summary.show()
    opened: List[int] = []
    summary.set_opener(lambda: opened.append(1))
    summary.set_summary("Sans Serif, 12 pt, Bold, Italic, Underline")
    try:
        _settle(qapp)
        assert summary.toolTip() == "Sans Serif, 12 pt, Bold, Italic, Underline"
        assert summary.text().endswith("▾") and "…" in summary.text()
        assert summary.accessibleName() == "Font: Sans Serif, 12 pt, Bold, Italic, Underline"
        summary.setFocus()
        QTest.keyClick(summary, _key("Key_Return"))
        QTest.keyClick(summary, _key("Key_Down"), _mods("AltModifier"))
        assert opened == [1, 1]
    finally:
        window.close()


def _mods(name: str):  # type: ignore[no-untyped-def]
    return getattr(getattr(Qt, "KeyboardModifier", Qt), name)


def _mouse(name: str):  # type: ignore[no-untyped-def]
    return getattr(getattr(Qt, "MouseButton", Qt), name)
