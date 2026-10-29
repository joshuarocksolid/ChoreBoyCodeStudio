from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.query.selection import SelectionSource  # noqa: E402
from app.features.form_builder.install import form_builder_enabled  # noqa: E402
from app.features.form_builder.integration.surface import FormSurface  # noqa: E402
from app.features.form_builder.qtside.inspector.api import GroupId  # noqa: E402
import re  # noqa: E402

from app.qt.QtCore import Qt  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtGui import QFont  # noqa: E402
from app.qt.QtWidgets import (  # noqa: E402
    QApplication,
    QCheckBox,
    QComboBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QToolButton,
    QSpinBox,
    QWidget,
)
from app.qt.qt_compat import enum_value  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402
from testing.main_window_shutdown import shutdown_main_window_for_test  # noqa: E402

pytestmark = pytest.mark.unit

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QWidget" name="Invoice">
  <layout class="QVBoxLayout" name="mainLayout">
   <item>
    <widget class="QLineEdit" name="email">
     <property name="text"><string>Pay</string></property>
     <property name="placeholderText"><string>name@example.com and a long tail</string></property>
    </widget>
   </item>
   <item>
    <widget class="QPushButton" name="okButtonWithAVeryLongObjectName"/>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _require() -> None:
    if not form_builder_enabled():
        pytest.skip("form builder is registered on PySide6")


def _open(tmp_path: Path, qapp: QApplication) -> tuple[MainWindow, FormSurface]:
    path = tmp_path / "invoice.ui"
    path.write_text(_FORM, encoding="utf-8")
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    assert window._editor_tab_factory.open_file_in_editor(str(path))  # noqa: SLF001
    window._center_stack.setCurrentIndex(1)  # noqa: SLF001
    window.resize(1400, 900)
    window.show()
    qapp.processEvents()
    surface = window._tab_content_registry.surface_for_path(str(path))  # noqa: SLF001
    assert isinstance(surface, FormSurface)
    return window, surface


def test_editor_page_inspector_does_not_scroll_sideways(tmp_path: Path, qapp: QApplication) -> None:
    _require()
    window, surface = _open(tmp_path, qapp)
    try:
        scroll = surface.findChild(QScrollArea, "formBuilder.inspectorScroll")
        assert scroll is not None
        off = getattr(getattr(Qt, "ScrollBarPolicy", Qt), "ScrollBarAlwaysOff")
        assert enum_value(scroll.horizontalScrollBarPolicy()) == enum_value(off)
        assert scroll.horizontalScrollBar().isVisible() is False
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_editor_page_shows_live_defaults_and_the_form_size(tmp_path: Path, qapp: QApplication) -> None:
    _require()
    window, surface = _open(tmp_path, qapp)
    try:
        session = surface._session  # noqa: SLF001
        pane = surface._workbench.inspector  # noqa: SLF001
        session.selection.clear(source=SelectionSource.PROGRAM)
        pane.flush()
        qapp.processEvents()
        size = surface.findChild(QLabel, "formBuilder.formDesignSize")
        caption = surface.findChild(QLabel, "formBuilder.formCaption.window")
        assert size is not None and size.text().endswith(" px")
        assert caption is not None and caption.text() == "Window"
        email = session.document.by_name("email")[0]
        session.selection.set((email,), source=SelectionSource.PROGRAM)
        pane.set_group_expanded(GroupId.ALL, True)
        pane.flush()
        qapp.processEvents()
        widget = surface._realizer.widget_for(email)  # noqa: SLF001
        length = surface.findChild(QWidget, "formBuilder.row.maxLength")
        assert widget is not None and length is not None
        spin = length.findChild(QSpinBox)
        assert spin is not None
        assert spin.value() == int(widget.property("maxLength"))
        assert spin.value() != 0
        echo = surface.findChild(QWidget, "formBuilder.row.echoMode")
        assert echo is not None
        combo = echo.findChild(QComboBox)
        assert combo is not None and combo.currentText()
        enabled = surface.findChild(QWidget, "formBuilder.row.enabled")
        assert enabled is not None
        box = enabled.findChild(QCheckBox)
        assert box is not None and box.isChecked() == bool(widget.isEnabled())
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_all_properties_show_the_class_value_not_the_canvas_override(tmp_path: Path, qapp: QApplication) -> None:
    """UX-INSP-008: the canvas turns focus off on every widget; the inspector must not show that."""
    _require()
    window, surface = _open(tmp_path, qapp)
    try:
        session = surface._session  # noqa: SLF001
        pane = surface._workbench.inspector  # noqa: SLF001
        email = session.document.by_name("email")[0]
        session.selection.set((email,), source=SelectionSource.PROGRAM)
        pane.set_group_expanded(GroupId.ALL, True)
        pane.flush()
        qapp.processEvents()
        widget = surface._realizer.widget_for(email)  # noqa: SLF001
        assert widget is not None
        no_focus = getattr(getattr(Qt, "FocusPolicy", Qt), "NoFocus")
        assert enum_value(widget.focusPolicy()) == enum_value(no_focus)
        policy = surface.findChild(QWidget, "formBuilder.row.focusPolicy")
        tracking = surface.findChild(QWidget, "formBuilder.row.mouseTracking")
        assert policy is not None and tracking is not None
        combo = policy.findChild(QComboBox)
        box = tracking.findChild(QCheckBox)
        assert combo is not None and box is not None
        assert combo.currentText() == "Strong focus"
        # Qt's own QLineEdit constructor turns tracking on, so the class value
        # comes from a fresh line edit rather than a constant.
        fresh = QLineEdit()
        try:
            assert box.isChecked() == fresh.hasMouseTracking()
        finally:
            fresh.deleteLater()
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_changed_labels_and_the_name_are_strong_under_the_shell_style(tmp_path: Path, qapp: QApplication) -> None:
    """UX-INSP-001 and UX-INSP-006 under the shell's chrome font-weight rule."""
    _require()
    window, surface = _open(tmp_path, qapp)
    try:
        session = surface._session  # noqa: SLF001
        pane = surface._workbench.inspector  # noqa: SLF001
        email = session.document.by_name("email")[0]
        session.selection.set((email,), source=SelectionSource.PROGRAM)
        pane.flush()
        qapp.processEvents()
        strong = enum_value(getattr(getattr(QFont, "Weight", QFont), "DemiBold"))
        changed = surface.findChild(QWidget, "formBuilder.row.text")
        plain = surface.findChild(QWidget, "formBuilder.row.maxLength")
        assert changed is not None
        label = next(item for item in changed.findChildren(QLabel) if item.text() == "Text")
        assert label.fontInfo().weight() >= strong
        if plain is not None:
            other = next(item for item in plain.findChildren(QLabel) if item.text())
            assert other.fontInfo().weight() < strong
        name = surface.findChild(QLineEdit, "formBuilder.inspectorName")
        assert name is not None and name.text() == "email"
        assert name.fontInfo().weight() >= strong
    finally:
        shutdown_main_window_for_test(window, qapp)


def _show(surface: FormSurface, qapp: QApplication, name: str, *, expand_all: bool = False) -> None:
    session = surface._session  # noqa: SLF001
    pane = surface._workbench.inspector  # noqa: SLF001
    node = session.document.by_name(name)[0]
    session.selection.set((node,), source=SelectionSource.PROGRAM)
    pane.set_group_expanded(GroupId.ALL, expand_all)
    pane.flush()
    qapp.processEvents()


def _row(surface: FormSurface, key: str) -> QWidget:
    row = surface.findChild(QWidget, "formBuilder.row.%s" % key)
    assert row is not None, key
    return row


def _label_of(row: QWidget) -> QLabel:
    labels = [item for item in row.findChildren(QLabel) if item.text()]
    assert labels
    return labels[0]


def _key_into(widget: QWidget, text: str) -> None:
    widget.setFocus()
    QTest.keyClicks(widget, text)


def test_changed_bar_paints_the_accent_and_rows_stay_aligned(tmp_path: Path, qapp: QApplication) -> None:
    """UX-INSP-006: the 2 px bar is accent coloured and does not shift its row."""
    _require()
    window, surface = _open(tmp_path, qapp)
    try:
        _show(surface, qapp, "email")
        pane = surface._workbench.inspector  # noqa: SLF001
        found = re.search(r'rowChanged\[fbChanged="true"\] \{ background: (#[0-9A-Fa-f]{6})', pane.styleSheet())
        assert found is not None
        accent = found.group(1).lower()
        changed = _row(surface, "text")
        plain = _row(surface, "maxLength")
        bar = changed.findChild(QWidget, "formBuilder.rowChanged")
        assert bar is not None and bar.isVisible() and bar.width() == 2
        image = changed.grab().toImage()
        assert image.pixelColor(bar.x(), bar.y() + bar.height() // 2).name() == accent
        changed_label = _label_of(changed)
        plain_label = _label_of(plain)
        assert changed_label.mapTo(pane, changed_label.rect().topLeft()).x() == plain_label.mapTo(
            pane, plain_label.rect().topLeft()
        ).x()
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_alignment_segments_show_the_value(tmp_path: Path, qapp: QApplication) -> None:
    """An unset line edit reads Left; clicking Right checks Right and writes it."""
    _require()
    window, surface = _open(tmp_path, qapp)
    try:
        _show(surface, qapp, "email")
        row = _row(surface, "alignment")
        buttons = {button.toolTip(): button for button in row.findChildren(QToolButton) if button.toolTip()}
        left, right = buttons["AlignLeft"], buttons["AlignRight"]
        assert left.isChecked() and not right.isChecked()
        # The checked segment looks different from the unchecked one under the shell style.
        on = left.grab().toImage()
        off = right.grab().toImage()
        assert on.pixelColor(on.width() // 2, 2).name() != off.pixelColor(off.width() // 2, 2).name()
        right.click()
        surface._workbench.inspector.flush()  # noqa: SLF001
        qapp.processEvents()
        row = _row(surface, "alignment")
        buttons = {button.toolTip(): button for button in row.findChildren(QToolButton) if button.toolTip()}
        assert buttons["AlignRight"].isChecked() and not buttons["AlignLeft"].isChecked()
        session = surface._session  # noqa: SLF001
        written = session.document.node(session.document.by_name("email")[0]).prop("alignment")
        assert written is not None and "AlignRight" in str(written)
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_escape_cancels_a_rename_and_a_text_edit(tmp_path: Path, qapp: QApplication) -> None:
    """UX-TEXT-003 / UX-SEL-004: Esc cancels the edit in progress, a second Esc leaves."""
    _require()
    window, surface = _open(tmp_path, qapp)
    try:
        session = surface._session  # noqa: SLF001
        pane = surface._workbench.inspector  # noqa: SLF001
        email = session.document.by_name("email")[0]
        _show(surface, qapp, "email")
        name = surface.findChild(QLineEdit, "formBuilder.inspectorName")
        assert name is not None
        name.setFocus()
        name.selectAll()
        QTest.keyClicks(name, "fooName")
        QTest.keyClick(name, Qt.Key_Escape)
        qapp.processEvents()
        assert name.text() == "email"
        assert qapp.focusWidget() is name
        QTest.keyClick(name, Qt.Key_Escape)
        qapp.processEvents()
        assert session.document.node(email).object_name == "email"
        assert not pane.isAncestorOf(qapp.focusWidget())

        for searching in (False, True):
            _show(surface, qapp, "email")
            search = surface.findChild(QLineEdit, "formBuilder.inspectorSearch")
            assert search is not None
            search.setText("mask" if searching else "")
            pane.flush()
            qapp.processEvents()
            # Tooltip opens a popover since M4.3d; Input mask is still an inline field.
            editor = _row(surface, "inputMask").findChild(QLineEdit)
            assert editor is not None
            _key_into(editor, "typed")
            QTest.keyClick(editor, Qt.Key_Escape)
            qapp.processEvents()
            assert editor.text() == ""
            assert qapp.focusWidget() is editor
            if searching:
                assert search.text() == "mask"
            QTest.keyClick(editor, Qt.Key_Escape)
            qapp.processEvents()
            assert session.document.node(email).prop("inputMask") is None
            search.setText("")

        # A spin box: typed digits are not committed until Enter, and Esc drops them.
        _show(surface, qapp, "email", expand_all=True)
        spin = _row(surface, "maxLength").findChild(QSpinBox)
        assert spin is not None
        shown = spin.text()
        spin.setFocus()
        spin.selectAll()
        QTest.keyClicks(spin, "12")
        assert spin.text() != shown
        QTest.keyClick(spin, Qt.Key_Escape)
        qapp.processEvents()
        assert spin.text() == shown
        assert qapp.focusWidget() is spin
        QTest.keyClick(spin, Qt.Key_Escape)
        qapp.processEvents()
        assert session.document.node(email).prop("maxLength") is None
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_adding_a_connection_keeps_the_sender_selected(tmp_path: Path, qapp: QApplication) -> None:
    """UX-INSP-013: after a slot is picked the Behavior list shows the new row."""
    _require()
    window, surface = _open(tmp_path, qapp)
    try:
        session = surface._session  # noqa: SLF001
        pane = surface._workbench.inspector  # noqa: SLF001
        sender = session.document.by_name("okButtonWithAVeryLongObjectName")[0]
        _show(surface, qapp, "okButtonWithAVeryLongObjectName")
        tabs = pane.findChild(QTabWidget)
        assert tabs is not None
        behavior = next(index for index in range(tabs.count()) if tabs.tabText(index).startswith("Behavior"))
        tabs.setCurrentIndex(behavior)
        pane.flush()
        qapp.processEvents()
        add = next(button for button in pane.findChildren(QPushButton) if "Add connection" in button.text())
        add.click()
        qapp.processEvents()
        signal = pane.findChild(QComboBox, "formBuilder.draftSignal")
        slot = pane.findChild(QComboBox, "formBuilder.draftSlot")
        assert signal is not None and slot is not None
        signal.hidePopup()
        slot.setCurrentIndex(0)
        slot.activated.emit(0)
        pane.flush()
        qapp.processEvents()
        # The committed row takes focus but does not reopen its "When" popup.
        assert not any(combo.view().isVisible() for combo in pane.findChildren(QComboBox))
        assert len(session.document.connections()) == 1
        assert session.selection.state.ids == (sender,)
        assert tabs.tabText(behavior) == "Behavior (1)"
        name = surface.findChild(QLineEdit, "formBuilder.inspectorName")
        assert name is not None and name.text() == "okButtonWithAVeryLongObjectName"
        assert add.isEnabled()
        assert pane.findChild(QWidget, "formBuilder.connectionDraft") is None
        session.log.undo()
        pane.flush()
        qapp.processEvents()
        assert session.document.connections() == ()
        assert session.selection.state.ids == (sender,)
        # Redo selects the ConnectionNode again; the inspector shows its sender.
        session.log.redo()
        pane.flush()
        qapp.processEvents()
        assert len(session.document.connections()) == 1
        assert name.text() == "okButtonWithAVeryLongObjectName" and not name.isReadOnly()
        assert tabs.tabText(behavior) == "Behavior (1)"
        assert add.isEnabled()
        # Remove keeps the sender too, not the <ui> node.
        remove = next(button for button in pane.findChildren(QToolButton) if button.text() == "Remove")
        remove.click()
        pane.flush()
        qapp.processEvents()
        assert session.document.connections() == ()
        assert session.selection.state.ids == (sender,)
        assert name.text() == "okButtonWithAVeryLongObjectName"
        assert tabs.tabText(behavior) == "Behavior"
        assert add.isEnabled()
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_line_edits_show_the_start_of_their_text(tmp_path: Path, qapp: QApplication) -> None:
    """UX-INSP-003: a long value shows its head, not its tail."""
    _require()
    window, surface = _open(tmp_path, qapp)
    try:
        _show(surface, qapp, "email")
        placeholder = _row(surface, "placeholderText").findChild(QLineEdit)
        assert placeholder is not None and placeholder.text().startswith("name@")
        assert placeholder.cursorPosition() == 0
        _show(surface, qapp, "okButtonWithAVeryLongObjectName")
        name = surface.findChild(QLineEdit, "formBuilder.inspectorName")
        assert name is not None and name.text() == "okButtonWithAVeryLongObjectName"
        assert name.cursorPosition() == 0
    finally:
        shutdown_main_window_for_test(window, qapp)
