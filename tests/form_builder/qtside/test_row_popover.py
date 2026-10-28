# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""The row popover shell (UX-PED-003): placement, keys, focus and what closes it."""

from __future__ import annotations

from typing import List

import pytest

from app.features.form_builder.engine.commands.catalog import SetProperty
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.qtside.inspector._services import Services
from app.features.form_builder.qtside.inspector.api import EditorKey, OpenRow, Unset, ValueSpec
from app.features.form_builder.qtside.inspector.catalog import Catalog
from app.features.form_builder.qtside.inspector.editors import default_catalog
from app.features.form_builder.qtside.inspector.editors._popover import RowPopover, SummaryButton
from app.features.form_builder.qtside.inspector._properties import _Row
from app.qt.QtCore import QPoint, QPointF, Qt  # type: ignore[reportAttributeAccessIssue]
from app.qt.QtGui import QKeySequence, QShortcut, QWheelEvent  # type: ignore[reportAttributeAccessIssue]
from app.qt.QtTest import QTest
from app.qt.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QWidget,
)
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


def _enum(kind: str, name: str):  # type: ignore[no-untyped-def]
    return getattr(getattr(Qt, kind, Qt), name)


def test_the_title_is_title_size_and_the_qt_name_is_faint_caption(qapp: QApplication) -> None:
    host = _Host()
    window = _window(400, 300)
    row = _row(window, 20, 40, 236)
    popover = RowPopover(
        row,
        host.services,
        row_label="Tool tip",
        session_label="Change tool tip",
        qt_name="toolTip",
    )
    popover.open_popover()
    _settle(qapp)
    try:
        sheet = popover.styleSheet()
        title = popover.findChild(QLabel, "formBuilder.popoverTitle")
        qt_name = popover.findChild(QLabel, "formBuilder.popoverQtName")
        reset = popover.findChild(QPushButton, "formBuilder.popoverReset")
        assert title is not None and qt_name is not None and reset is not None
        assert "QLabel#formBuilder\\.popoverTitle" in sheet and "font-size: 13px" in sheet
        assert "QLabel#formBuilder\\.popoverQtName" in sheet and "font-size: 11px" in sheet
        assert host.services.chrome.faint in sheet
        assert ("border: 1px solid %s" % host.services.chrome.border) in sheet
        title.ensurePolished()
        qt_name.ensurePolished()
        assert title.font().pixelSize() == 13
        assert qt_name.font().pixelSize() == 11
    finally:
        popover.done()
        host.close()
        window.close()


def test_click_outside_keeps_a_commit_that_waits_for_focus_out(qapp: QApplication) -> None:
    host = _Host()
    window = _window(400, 300)
    row = _row(window, 20, 40, 236)
    summary = SummaryButton("Test row", row)
    summary.setGeometry(0, 0, 236, 24)
    summary.show()
    other = QPushButton("Elsewhere", window)
    other.setFocusPolicy(_enum("FocusPolicy", "NoFocus"))
    other.setGeometry(20, 200, 120, 24)
    other.show()
    popover = RowPopover(row, host.services, row_label="Test row", session_label="Change test row", anchor=summary)
    field = QLineEdit(popover)
    popover.body().addWidget(field)
    node = host.session.document.by_name("field")[0]
    field.editingFinished.connect(
        lambda: popover.session.run((SetProperty(node, "text", StringValue(field.text())),))
    )
    popover.open_popover()
    _settle(qapp)
    try:
        field.setFocus()
        _settle(qapp)
        QTest.keyClicks(field, "Kept")
        _settle(qapp)
        assert host.session.document.node(node).prop("text") is None
        QTest.mouseClick(other, _enum("MouseButton", "LeftButton"), _enum("KeyboardModifier", "NoModifier"), QPoint(4, 4))
        _settle(qapp)
        assert popover.closed
        stored = host.session.document.node(node).prop("text")
        assert stored is not None and isinstance(stored.value, StringValue)
        assert stored.value.text == "Kept"
    finally:
        host.close()
        window.close()


def test_a_combo_popup_and_a_child_dialog_count_as_inside(qapp: QApplication) -> None:
    host = _Host()
    window = _window(400, 320)
    row = _row(window, 20, 40, 236)
    popover = RowPopover(row, host.services, row_label="Test row", session_label="Change test row")
    combo = QComboBox(popover)
    combo.addItems(["Red", "Blue"])
    popover.body().addWidget(combo)
    dialog = QDialog(popover)
    dialog.setWindowTitle("Pick a file")
    choice = QPushButton("Choose", dialog)
    choice.setGeometry(8, 8, 80, 24)
    popover.open_popover()
    _settle(qapp)
    try:
        dialog.show()
        _settle(qapp)
        QTest.mouseClick(choice, _enum("MouseButton", "LeftButton"), _enum("KeyboardModifier", "NoModifier"), QPoint(4, 4))
        _settle(qapp)
        assert not popover.closed
        dialog.close()
        combo.showPopup()
        _settle(qapp)
        view = combo.view()
        assert view is not None
        QTest.mouseClick(
            view.viewport(),
            _enum("MouseButton", "LeftButton"),
            _enum("KeyboardModifier", "NoModifier"),
            QPoint(8, 8),
        )
        _settle(qapp)
        assert not popover.closed
    finally:
        popover.done()
        host.close()
        window.close()


def test_ctrl_shift_z_does_not_undo_the_session(qapp: QApplication) -> None:
    host = _Host()
    window = _window(400, 300)
    row = _row(window, 20, 40, 236)
    popover = RowPopover(row, host.services, row_label="Test row", session_label="Change test row")
    done = None
    popover.open_popover()
    _settle(qapp)
    try:
        done = popover.findChild(QPushButton, "formBuilder.popoverDone")
        assert done is not None
        done.setFocus()
        _settle(qapp)
        QTest.keyClick(done, _key("Key_Z"), _mods("ControlModifier") | _mods("ShiftModifier"))
        _settle(qapp)
        assert not popover.closed
    finally:
        if done is not None and not popover.closed:
            popover.done()
        host.close()
        window.close()


def test_ctrl_z_with_nothing_written_is_the_forms_undo(qapp: QApplication) -> None:
    host = _Host()
    window = _window(400, 300)
    row = _row(window, 20, 40, 236)
    log = host.session.log
    node = host.session.document.by_name("field")[0]
    log.execute(SetProperty(node, "text", StringValue("before")))
    undo = QShortcut(QKeySequence(QKeySequence.StandardKey.Undo), window)
    undo.activated.connect(log.undo)
    popover = RowPopover(row, host.services, row_label="Test row", session_label="Change test row")
    popover.open_popover()
    _settle(qapp)
    try:
        done = popover.findChild(QPushButton, "formBuilder.popoverDone")
        assert done is not None
        done.setFocus()
        _settle(qapp)
        QTest.keyClick(done, _key("Key_Z"), _mods("ControlModifier"))
        _settle(qapp)
        assert not log.entries()
        assert popover.closed
    finally:
        if not popover.closed:
            popover.done()
        host.close()
        window.close()


def test_enter_closes_a_spin_box_and_not_a_list(qapp: QApplication) -> None:
    host = _Host()
    window = _window(400, 300)
    row = _row(window, 20, 40, 236)
    popover = RowPopover(row, host.services, row_label="Test row", session_label="Change test row")
    spin = QSpinBox(popover)
    listing = QListWidget(popover)
    listing.addItem("Page 1")
    popover.body().addWidget(spin)
    popover.body().addWidget(listing)
    popover.open_popover()
    _settle(qapp)
    try:
        listing.setFocus()
        _settle(qapp)
        QTest.keyClick(listing, _key("Key_Return"))
        _settle(qapp)
        assert not popover.closed
        spin.setFocus()
        _settle(qapp)
        QTest.keyClick(spin, _key("Key_Return"))
        _settle(qapp)
        assert popover.closed
    finally:
        if not popover.closed:
            popover.done()
        host.close()
        window.close()


def test_tab_inside_a_text_edit_and_ctrl_tab_are_not_stolen(qapp: QApplication) -> None:
    host = _Host()
    window = _window(400, 300)
    row = _row(window, 20, 40, 236)
    popover = RowPopover(row, host.services, row_label="Test row", session_label="Change test row")
    plain = QPlainTextEdit(popover)
    popover.body().addWidget(plain)
    popover.open_popover()
    _settle(qapp)
    try:
        plain.setFocus()
        _settle(qapp)
        QTest.keyClick(plain, _key("Key_Tab"))
        _settle(qapp)
        assert QApplication.focusWidget() is plain or (
            QApplication.focusWidget() is not None and plain.isAncestorOf(QApplication.focusWidget())
        )
        QTest.keyClick(plain, _key("Key_Tab"), _mods("ControlModifier"))
        _settle(qapp)
        assert not popover.closed
        focus = QApplication.focusWidget()
        assert focus is plain or (focus is not None and plain.isAncestorOf(focus))
    finally:
        popover.done()
        host.close()
        window.close()


def test_escape_is_not_taken_by_a_window_shortcut(qapp: QApplication) -> None:
    host = _Host()
    window = _window(400, 300)
    row = _row(window, 20, 40, 236)
    summary = SummaryButton("Test row", row)
    summary.show()
    popover = RowPopover(row, host.services, row_label="Test row", session_label="Change test row", anchor=summary)
    field = QLineEdit(popover)
    popover.body().addWidget(field)
    fired: List[int] = []
    shortcut = QShortcut(QKeySequence(_key("Key_Escape")), window)
    shortcut.activated.connect(lambda: fired.append(1))
    popover.open_popover()
    _settle(qapp)
    try:
        field.setFocus()
        _settle(qapp)
        QTest.keyClick(field, _key("Key_Escape"))
        _settle(qapp)
        assert popover.closed
        assert fired == []
    finally:
        host.close()
        window.close()


def test_hiding_the_row_or_resizing_the_window_closes_and_keeps(qapp: QApplication) -> None:
    host = _Host()
    window = _window(400, 300)
    row = _row(window, 20, 40, 236)
    popover = RowPopover(row, host.services, row_label="Test row", session_label="Change test row")
    popover.open_popover()
    _settle(qapp)
    try:
        row.hide()
        _settle(qapp)
        assert popover.closed
        row.show()
        second = RowPopover(row, host.services, row_label="Test row", session_label="Change test row")
        second.open_popover()
        _settle(qapp)
        window.resize(480, 360)
        _settle(qapp)
        assert second.closed
    finally:
        host.close()
        window.close()


def test_a_wheel_outside_the_popover_closes_it(qapp: QApplication) -> None:
    host = _Host()
    window = _window(400, 300)
    row = _row(window, 20, 40, 236)
    popover = RowPopover(row, host.services, row_label="Test row", session_label="Change test row")
    popover.open_popover()
    _settle(qapp)
    try:
        local = QPointF(row.rect().center())
        globe = QPointF(row.mapToGlobal(row.rect().center()))
        event = QWheelEvent(
            local,
            globe,
            QPoint(0, 0),
            QPoint(0, -120),
            _enum("MouseButton", "NoButton"),
            _enum("KeyboardModifier", "NoModifier"),
            _enum("ScrollPhase", "NoScrollPhase"),
            False,
        )
        QApplication.sendEvent(row, event)
        _settle(qapp)
        assert popover.closed
    finally:
        host.close()
        window.close()


def test_a_wheel_over_the_popover_that_reaches_the_window_keeps_it_open(qapp: QApplication) -> None:
    # An unused wheel over the popover propagates to its parent, the window.
    host = _Host()
    window = _window(400, 300)
    row = _row(window, 20, 40, 236)
    popover = RowPopover(row, host.services, row_label="Test row", session_label="Change test row")
    popover.open_popover()
    _settle(qapp)
    try:
        inside = popover.geometry().center()
        event = QWheelEvent(
            QPointF(inside),
            QPointF(window.mapToGlobal(inside)),
            QPoint(0, 0),
            QPoint(0, -120),
            _enum("MouseButton", "NoButton"),
            _enum("KeyboardModifier", "NoModifier"),
            _enum("ScrollPhase", "NoScrollPhase"),
            False,
        )
        QApplication.sendEvent(window, event)
        _settle(qapp)
        assert not popover.closed
    finally:
        popover.done()
        host.close()
        window.close()


def test_disposing_the_services_closes_an_open_popover(qapp: QApplication) -> None:
    host = _Host()
    window = _window(400, 300)
    row = _row(window, 20, 40, 236)
    popover = RowPopover(row, host.services, row_label="Test row", session_label="Change test row")
    popover.open_popover()
    _settle(qapp)
    try:
        host.services.dispose()
        assert popover.closed
    finally:
        host.close()
        window.close()


class _Write:
    def edit(self, value: object, token: object) -> object:
        del value, token
        return None

    def reset(self) -> object:
        return None


class _SummaryEditor:
    def __init__(self, host: object, parent: QWidget) -> None:
        self.host = host
        self.widget = SummaryButton(str(getattr(host, "label", "")), parent)
        self.widget.set_summary("One")

    def show(self, value: object) -> None:
        del value
        self.widget.set_row_label(str(getattr(self.host, "label", "")))


def test_a_rebound_summary_keeps_label_and_summary_and_reads_the_current_label(qapp: QApplication) -> None:
    del qapp
    host = _Host()
    window = _window(400, 200)
    built: List[str] = []

    def factory(spec: object, editor_host: object, parent: QWidget) -> _SummaryEditor:
        del spec
        built.append(str(getattr(editor_host, "label", "")))
        return _SummaryEditor(editor_host, parent)

    key = EditorKey("rebind")
    catalog = Catalog((), {key: factory}, {})
    services = Services(host.session, catalog, None)
    row = _Row(services, window)
    spec = ValueSpec("string")
    try:
        row.paint(OpenRow("k", "Font", "font", "", Unset(), spec, key, _Write()), "", False)
        button = row.findChild(SummaryButton)
        assert button is not None
        assert button.accessibleName() == "Font: One"
        assert row.label == "Font"
        assert row.qt_name == "font"
        assert row.row_widget is row
        row.paint(OpenRow("k", "Family", "family", "", Unset(), spec, key, _Write()), "", False)
        assert built == ["Font"]
        assert button.accessibleName() == "Family: One"
        assert row.label == "Family"
    finally:
        services.dispose()
        host.close()
        window.close()


def _mouse(name: str):  # type: ignore[no-untyped-def]
    return getattr(getattr(Qt, "MouseButton", Qt), name)
