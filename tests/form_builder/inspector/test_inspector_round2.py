# pyright: reportAttributeAccessIssue=false
"""Inspector round 2: live defaults, font commits, drafts, and the property page."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.ui4.nodes import ConnectionNode
from app.features.form_builder.engine.ui4.values import (
    BoolValue,
    EnumValue,
    FontValue,
    NumberValue,
    StringValue,
    UIntValue,
    ULongLongValue,
)
from app.features.form_builder.integration.memory import WorkbenchMemoryStore
from app.features.form_builder.qtside.inspector import InspectorPane
from app.features.form_builder.qtside.inspector._live import live_classes
from app.features.form_builder.qtside.inspector.api import GroupId, Unset, Written
from app.features.form_builder.qtside.inspector.editors import default_catalog
from app.features.form_builder.qtside.inspector.model import NodeBody, project
from app.features.form_builder.qtside.inspector.pane import TabId
from app.features.form_builder.qtside.theme.chrome import chrome_from_values
from app.qt.QtCore import QPointF, Qt
from app.qt.QtGui import QEnterEvent, QFont
from app.qt.QtTest import QTest
from app.qt.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from app.qt.qt_compat import enum_value
from tests.form_builder.qtside.support import realize

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QWidget" name="Invoice">
  <layout class="QVBoxLayout" name="mainLayout">
   <item>
    <widget class="QLineEdit" name="email">
     <property name="text"><string>Pay</string></property>
    </widget>
   </item>
   <item>
    <widget class="QLineEdit" name="phone"/>
   </item>
   <item>
    <widget class="QPushButton" name="okButton"/>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


_CHROME = chrome_from_values(
    window="#f3f3f3",
    panel="#ffffff",
    text="#1f1f1f",
    muted="#5c5c5c",
    faint="#6b6b6b",
    border="#c8c8c8",
    accent="#0060c0",
    row_hover="#eef3fb",
    input_bg="#ffffff",
    error="#b00020",
    focus_width=1,
)


def _pane(qapp: QApplication):
    session, realizer = realize(_FORM)
    window = QWidget()
    pane = InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None, parent=window)
    # The workbench always applies chrome. Its style sheet owns the mixed
    # italic and the changed weight, as it does in the shell.
    pane.apply_chrome(_CHROME)
    layout = QVBoxLayout(window)
    layout.addWidget(pane)
    window.resize(1400, 900)
    window.show()
    qapp.setActiveWindow(window)
    qapp.processEvents()
    pane.flush()
    return window, pane, session, realizer


def _close(window, pane, realizer, session, qapp: QApplication) -> None:
    pane.dispose()
    realizer.dispose()
    session.dispose()
    window.close()
    qapp.processEvents()


def _select(session, *names: str) -> None:
    ids = tuple(session.document.by_name(name)[0] for name in names)
    session.selection.set(ids, source=SelectionSource.PROGRAM)


def test_all_properties_show_the_live_widget_value(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp)
    try:
        _select(session, "email")
        pane.set_group_expanded(GroupId.ALL, True)
        pane.flush()
        email = session.document.by_name("email")[0]
        widget = realizer.widget_for(email)
        assert widget is not None
        length = pane.findChild(QWidget, "formBuilder.row.maxLength")
        echo = pane.findChild(QWidget, "formBuilder.row.echoMode")
        enabled = pane.findChild(QWidget, "formBuilder.row.enabled")
        policy = pane.findChild(QWidget, "formBuilder.row.focusPolicy")
        assert length is not None and echo is not None and enabled is not None and policy is not None
        spin = length.findChild(QSpinBox)
        combo = echo.findChild(QComboBox)
        box = enabled.findChild(QCheckBox)
        focus = policy.findChild(QComboBox)
        assert spin is not None and combo is not None and box is not None and focus is not None
        assert spin.value() == int(widget.property("maxLength"))
        assert spin.value() != 0
        assert spin.property("fbState") == "unset"
        assert combo.currentText()
        assert combo.property("fbState") == "unset"
        assert box.isChecked() == bool(widget.property("enabled"))
        assert focus.currentText()
        live = live_classes(realizer, session.document, (email,), with_values=True)
        body = project(session, default_catalog(), live=live, include_all=True).body
        assert isinstance(body, NodeBody)
        matched = 0
        for view in body.groups:
            if view.group is not GroupId.ALL:
                continue
            for row in view.rows():
                shown = row.value.default if isinstance(row.value, Unset) else None
                if isinstance(row.value, Written):
                    shown = row.value.value
                raw = widget.property(row.qt_name)
                if _matches(shown, raw):
                    matched += 1
        assert matched >= 4
    finally:
        _close(window, pane, realizer, session, qapp)


def test_unset_number_shows_an_em_dash_only_without_a_default(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp)
    try:
        _select(session, "email")
        pane.flush()
        length = pane.findChild(QWidget, "formBuilder.row.maxLength")
        assert length is not None
        spin = length.findChild(QSpinBox)
        assert spin is not None
        assert spin.specialValueText() == ""
        assert spin.property("fbState") == "unset"
    finally:
        _close(window, pane, realizer, session, qapp)


def test_unset_font_bold_writes_only_bold(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp)
    try:
        _select(session, "email")
        pane.flush()
        row = pane.findChild(QWidget, "formBuilder.row.font")
        assert row is not None
        family = row.findChild(QComboBox)
        size = row.findChild(QSpinBox)
        bold = next(box for box in row.findChildren(QCheckBox) if box.text() == "Bold")
        assert family is not None and size is not None
        line = family.lineEdit()
        assert line is not None
        assert line.text() == ""
        assert line.placeholderText() == "Default"
        assert size.specialValueText() == "\u2014"
        bold.click()
        pane.flush()
        stored = session.document.node(session.document.by_name("email")[0]).prop("font")
        assert stored is not None
        assert isinstance(stored.value, FontValue)
        assert stored.value.family is None
        assert stored.value.bold is True
        assert stored.value.pointsize is None
    finally:
        _close(window, pane, realizer, session, qapp)


def test_add_connection_stays_a_draft_until_a_slot_is_picked(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp)
    try:
        _select(session, "okButton")
        pane.focus_tab(TabId.BEHAVIOR)
        pane.flush()
        qapp.processEvents()
        add = next(button for button in pane.findChildren(QPushButton) if "Add connection" in button.text())
        before = len(session.document.connections())
        add.click()
        qapp.processEvents()
        assert len(session.document.connections()) == before
        draft = pane.findChild(QWidget, "formBuilder.connectionDraft")
        slot = pane.findChild(QComboBox, "formBuilder.draftSlot")
        signal = pane.findChild(QComboBox, "formBuilder.draftSignal")
        assert draft is not None and slot is not None and signal is not None
        assert draft.parentWidget() is not None
        layout = draft.parentWidget().layout()
        assert layout is not None and layout.indexOf(draft) == 0
        assert slot.currentIndex() == -1
        signal.hidePopup()
        assert slot.count() > 0
        slot.setCurrentIndex(0)
        chosen = slot.currentText()
        slot.activated.emit(0)
        pane.flush()
        connections = [node for node in session.document.connections() if isinstance(node, ConnectionNode)]
        assert len(connections) == before + 1
        assert connections[0].slot == chosen
        assert pane.findChild(QWidget, "formBuilder.connectionDraft") is None
    finally:
        _close(window, pane, realizer, session, qapp)


def test_escape_discards_a_connection_draft(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp)
    try:
        _select(session, "okButton")
        pane.focus_tab(TabId.BEHAVIOR)
        pane.flush()
        add = next(button for button in pane.findChildren(QPushButton) if "Add connection" in button.text())
        add.click()
        qapp.processEvents()
        signal = pane.findChild(QComboBox, "formBuilder.draftSignal")
        assert signal is not None
        signal.hidePopup()
        signal.setFocus()
        QTest.keyClick(signal, Qt.Key_Escape)
        qapp.processEvents()
        assert pane.findChild(QWidget, "formBuilder.connectionDraft") is None
        assert session.document.connections() == ()
    finally:
        _close(window, pane, realizer, session, qapp)


def test_leaving_the_page_discards_a_connection_draft(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp)
    try:
        _select(session, "okButton")
        pane.focus_tab(TabId.BEHAVIOR)
        pane.flush()
        add = next(button for button in pane.findChildren(QPushButton) if "Add connection" in button.text())
        add.click()
        qapp.processEvents()
        signal = pane.findChild(QComboBox, "formBuilder.draftSignal")
        assert signal is not None
        signal.hidePopup()
        # Offscreen leaves no active window after a popup closes; xcb restores it.
        qapp.setActiveWindow(window)
        qapp.processEvents()
        outside = QLineEdit(window)
        outside.setGeometry(0, 0, 80, 24)
        outside.show()
        outside.setFocus()
        qapp.processEvents()
        assert qapp.focusWidget() is outside
        assert pane.findChild(QWidget, "formBuilder.connectionDraft") is None
        assert session.document.connections() == ()
    finally:
        _close(window, pane, realizer, session, qapp)


def test_the_property_page_does_not_scroll_sideways(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp)
    try:
        _select(session, "email")
        pane.flush()
        scroll = pane.findChild(QScrollArea, "formBuilder.inspectorScroll")
        assert scroll is not None
        assert enum_value(scroll.horizontalScrollBarPolicy()) == enum_value(
            getattr(getattr(Qt, "ScrollBarPolicy", Qt), "ScrollBarAlwaysOff")
        )
        row = pane.findChild(QWidget, "formBuilder.row.text")
        assert row is not None
        editor = row.findChild(QLineEdit)
        assert editor is not None
        assert editor.minimumWidth() == 0
        ignored = getattr(getattr(QSizePolicy, "Policy", QSizePolicy), "Ignored")
        assert enum_value(editor.sizePolicy().horizontalPolicy()) == enum_value(ignored)
        label = next(item for item in row.findChildren(QLabel) if item.text() == "Text")
        assert label.parentWidget() is not None
        assert label.parentWidget().width() == 104
        pane.set_compact(True)
        assert label.parentWidget().width() == 96
    finally:
        _close(window, pane, realizer, session, qapp)


def test_reset_is_a_hover_icon_and_the_label_is_strong(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp)
    try:
        _select(session, "phone")
        pane.flush()
        row = pane.findChild(QWidget, "formBuilder.row.text")
        assert row is not None
        editor = row.findChild(QLineEdit)
        unchanged = row.findChild(QToolButton, "formBuilder.rowReset")
        label = next(item for item in row.findChildren(QLabel) if item.text() == "Text")
        assert editor is not None
        assert unchanged is None or not unchanged.isVisible()
        editor.setFocus()
        QTest.keyClicks(editor, "Hi")
        QTest.keyClick(editor, Qt.Key_Return)
        pane.flush()
        reset = row.findChild(QToolButton, "formBuilder.rowReset")
        assert reset is not None
        assert reset.text() == "\u21ba"
        assert reset.accessibleName() == "Reset"
        assert reset.width() == 16 and reset.height() == 16
        assert reset.isVisible()
        assert enum_value(label.font().weight()) == enum_value(
            getattr(getattr(QFont, "Weight", QFont), "DemiBold")
        )
        outside = QLineEdit(window)
        outside.show()
        outside.setFocus()
        qapp.processEvents()
        assert not reset.isVisible()
        kind = QPointF(4, 4)
        row.enterEvent(QEnterEvent(kind, kind, kind))
        assert reset.isVisible()
    finally:
        _close(window, pane, realizer, session, qapp)


def test_mixed_text_is_italic(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp)
    try:
        _select(session, "email", "phone")
        pane.flush()
        row = pane.findChild(QWidget, "formBuilder.row.text")
        assert row is not None
        editor = row.findChild(QLineEdit)
        assert editor is not None
        assert editor.placeholderText() == "Mixed"
        assert editor.property("fbState") == "mixed"
        assert editor.font().italic()
    finally:
        _close(window, pane, realizer, session, qapp)


def test_qt_names_toggle_is_remembered(tmp_path, qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp)
    try:
        store = WorkbenchMemoryStore(str(tmp_path))
        pane.bind_settings(store)
        _select(session, "email")
        pane.flush()
        menu = pane.findChild(QToolButton, "formBuilder.inspectorMenu")
        assert menu is not None and menu.menu() is not None
        action = menu.menu().actions()[0]
        assert action.text() == "Qt names"
        action.setChecked(True)
        qapp.processEvents()
        row = pane.findChild(QWidget, "formBuilder.row.text")
        assert row is not None
        qt_name = row.findChild(QLabel, "formBuilder.rowQtName")
        label = next(item for item in row.findChildren(QLabel) if item.text() == "Text")
        assert qt_name is not None and qt_name.isVisible()
        assert qt_name.text() == "text"
        assert label.toolTip().startswith("text \u2014")
        assert store.qt_names() is True
        assert WorkbenchMemoryStore(str(tmp_path)).qt_names() is True
    finally:
        _close(window, pane, realizer, session, qapp)


def test_headers_use_a_chevron_and_a_painted_glyph(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp)
    try:
        _select(session, "okButton")
        pane.flush()
        toggle = pane.findChild(QToolButton, "formBuilder.group.content")
        assert toggle is not None
        assert toggle.text() == "CONTENT"
        assert toggle.font().pixelSize() == 10
        arrows = getattr(Qt, "ArrowType", Qt)
        down = getattr(arrows, "DownArrow", getattr(Qt, "DownArrow"))
        assert enum_value(toggle.arrowType()) == enum_value(down)
        glyph = pane.findChild(QWidget, "formBuilder.inspectorGlyph")
        name = pane.findChild(QLineEdit, "formBuilder.inspectorName")
        assert glyph is not None and not isinstance(glyph, QLabel)
        assert glyph.width() == 16 and glyph.height() == 16
        assert name is not None and name.font().pixelSize() == 13
    finally:
        _close(window, pane, realizer, session, qapp)


def test_link_color_reaches_crumbs_and_the_filter(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp)
    try:
        _select(session, "okButton")
        pane.set_link_color("#123456")
        pane.flush()
        crumbs = pane.findChild(QLabel, "formBuilder.inspectorCrumbs")
        assert crumbs is not None and crumbs.isVisible()
        assert "color:#123456" in crumbs.text()
        search = pane.findChild(QLineEdit, "formBuilder.inspectorSearch")
        assert search is not None
        search.setText("text")
        pane.flush()
        pill = pane.findChild(QLabel, "formBuilder.inspectorFilter")
        assert pill is not None and pill.isVisible()
        assert "color:#123456" in pill.text()
    finally:
        _close(window, pane, realizer, session, qapp)


def test_form_view_lists_captions_and_a_sized_page(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp)
    try:
        session.selection.clear(source=SelectionSource.PROGRAM)
        pane.flush()
        expected = (
            ("window", "Window"),
            ("layout", "Layout"),
            ("tabOrder", "Tab order"),
            ("problems", "Problems"),
            ("files", "Files"),
        )
        for name, text in expected:
            caption = pane.findChild(QLabel, "formBuilder.formCaption.%s" % name)
            assert caption is not None and caption.text() == text
        size = pane.findChild(QLabel, "formBuilder.formDesignSize")
        root = realizer.root_widget
        assert size is not None and root is not None
        assert size.text() == "%d \u00d7 %d px" % (root.width(), root.height())
        title = pane.findChild(QWidget, "formBuilder.row.windowTitle")
        assert title is not None
        edit = title.findChild(QLineEdit)
        problems = pane.findChild(QLabel, "formBuilder.inspectorProblems")
        assert edit is not None and problems is not None
        assert edit.nextInFocusChain() is problems or problems in _chain(edit, 8)
    finally:
        _close(window, pane, realizer, session, qapp)


def test_the_key_filter_follows_focus_and_dispose(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp)
    outside = QLineEdit(window)
    outside.show()
    outside.setFocus()
    qapp.processEvents()
    name = pane.findChild(QLineEdit, "formBuilder.inspectorName")
    assert name is not None
    QTest.keyClick(outside, Qt.Key_F2)
    qapp.processEvents()
    assert qapp.focusWidget() is outside
    search = pane.findChild(QLineEdit, "formBuilder.inspectorSearch")
    assert search is not None
    search.setFocus()
    qapp.processEvents()
    QTest.keyClick(search, Qt.Key_F2)
    qapp.processEvents()
    assert qapp.focusWidget() is name
    pane.dispose()
    pane.deleteLater()
    qapp.processEvents()
    QTest.keyClick(outside, Qt.Key_A)
    qapp.processEvents()
    assert outside.text() == "a" or outside.text() == "A"
    realizer.dispose()
    session.dispose()
    window.close()


def _matches(shown: object, raw: object) -> bool:
    if isinstance(shown, BoolValue):
        return bool(shown.value) == bool(raw)
    if isinstance(shown, (NumberValue, UIntValue, ULongLongValue)):
        left = shown.value
        if isinstance(left, bool) or isinstance(raw, bool):
            return False
        if not isinstance(left, (int, float)) or not isinstance(raw, (int, float)):
            return False
        return int(left) == int(raw)
    if isinstance(shown, StringValue):
        return isinstance(raw, str) and shown.text == raw
    if isinstance(shown, EnumValue):
        return bool(shown.text) and raw is not None
    return False


def _chain(start: QWidget, limit: int) -> list:
    found = []
    widget = start
    for _ in range(limit):
        widget = widget.nextInFocusChain()
        found.append(widget)
    return found
