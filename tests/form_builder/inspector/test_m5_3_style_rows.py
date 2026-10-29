# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOptionalMemberAccess=false
"""Text colour, Background, Style sheet and the form's Look group in the inspector (UX-STYLE-001, 010 .. 013)."""

from __future__ import annotations

from typing import List

import pytest

from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.ui4.values import BoolValue, ColorValue, FontValue, PaletteValue, StringValue
from app.features.form_builder.qtside.inspector.editors._popover import RowPopover
from app.features.form_builder.qtside.visual.common import RowSummary
from app.qt.QtCore import Qt
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QLabel, QLineEdit, QPushButton, QSpinBox, QWidget
from tests.form_builder.inspector.test_inspector_round2 import _close, _pane, _select

pytestmark = [pytest.mark.usefixtures("qapp"), pytest.mark.unit]

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="mainLayout">
   <item><widget class="QLabel" name="nameLabel"><property name="text"><string>Name</string></property></widget></item>
   <item><widget class="QPushButton" name="okButton"><property name="text"><string>OK</string></property></widget></item>
   <item><widget class="QProgressBar" name="bar"/></item>
  </layout>
 </widget>
</ui>
"""


def _keys(pane, group: str) -> List[str]:  # type: ignore[no-untyped-def]
    names = []
    for widget in pane.findChildren(QWidget):
        name = widget.objectName()
        if name.startswith("formBuilder.row.") and widget.isVisibleTo(pane):
            names.append((widget.mapTo(pane, widget.rect().topLeft()).y(), name.split(".")[-1]))
    found: List[str] = []
    for _y, name in sorted(names):
        if name not in found:
            found.append(name)
    return found


def _stored(session, name: str, prop: str):  # type: ignore[no-untyped-def]
    entry = session.document.node(session.document.by_name(name)[0]).prop(prop)
    return None if entry is None else entry.value


def _open_popover(window):  # type: ignore[no-untyped-def]
    return [found for found in window.findChildren(RowPopover) if found.isVisible()][-1]


def _pick(pane, window, row_key: str, hex_text: str) -> None:  # type: ignore[no-untyped-def]
    row = pane.findChild(QWidget, "formBuilder.row.%s" % row_key)
    summary = row.findChild(RowSummary)
    summary.click()
    QApplication.processEvents()
    popover = _open_popover(window)
    field = popover.findChild(QLineEdit, "formBuilder.colorHex")
    field.setText(hex_text)
    QTest.keyClick(field, Qt.Key.Key_Return)
    QApplication.processEvents()
    popover.done()
    QApplication.processEvents()
    pane.flush()


def test_appearance_reads_font_text_colour_background_style_sheet_then_the_m4_rows(qapp) -> None:  # type: ignore[no-untyped-def]
    window, pane, session, realizer = _pane(qapp, _FORM)
    try:
        _select(session, "nameLabel")
        pane.flush()
        order = _keys(pane, "appearance")
        picked = [key for key in order if key in ("font", "textColour", "backgroundColour", "styleSheet", "alignment", "wordWrap")]
        assert picked == ["font", "textColour", "backgroundColour", "styleSheet", "alignment", "wordWrap"]
        _select(session, "bar")
        pane.flush()
        # A progress bar has no text colour or background row, and keeps its style sheet row.
        assert pane.findChild(QWidget, "formBuilder.row.textColour") is None or not pane.findChild(
            QWidget, "formBuilder.row.textColour"
        ).isVisibleTo(pane)
        assert pane.findChild(QWidget, "formBuilder.row.styleSheet") is not None
    finally:
        _close(window, pane, realizer, session, qapp)


def test_text_colour_writes_a_style_sheet_declaration_and_background_a_palette_role(qapp) -> None:  # type: ignore[no-untyped-def]
    window, pane, session, realizer = _pane(qapp, _FORM)
    try:
        before = session.text()
        _select(session, "nameLabel")
        pane.flush()
        _pick(pane, window, "textColour", "#FFFFFF")
        sheet = _stored(session, "nameLabel", "styleSheet")
        assert isinstance(sheet, StringValue) and sheet.text == "color: #FFFFFF;"
        _pick(pane, window, "backgroundColour", "#1A7F37")
        palette = _stored(session, "nameLabel", "palette")
        assert isinstance(palette, PaletteValue)
        for group in (palette.active, palette.inactive, palette.disabled):
            assert [item.role for item in group] == ["Window"]
            assert group[0].brush.color == ColorValue(26, 127, 55)
        fill = _stored(session, "nameLabel", "autoFillBackground")
        assert isinstance(fill, BoolValue) and fill.value
        label = realizer.widget_for(session.document.by_name("nameLabel")[0])
        assert label.styleSheet() == "color: #FFFFFF;" and label.autoFillBackground()
        summary = pane.findChild(QWidget, "formBuilder.row.textColour").findChild(RowSummary)
        assert "#FFFFFF" in summary.summary
        # Undo twice: the original bytes.
        assert session.log.undo() and session.log.undo()
        assert session.text() == before
    finally:
        _close(window, pane, realizer, session, qapp)


def test_a_colour_read_from_the_palette_is_shown_with_its_caption_and_reset_takes_back_only_what_the_row_wrote(qapp) -> None:  # type: ignore[no-untyped-def]
    form = _FORM.replace(
        '<property name="text"><string>Name</string></property>',
        '<property name="text"><string>Name</string></property>'
        '<property name="palette"><palette><active><colorrole role="WindowText"><brush brushstyle="SolidPattern">'
        '<color alpha="255"><red>255</red><green>0</green><blue>0</blue></color></brush></colorrole></active>'
        "<inactive/><disabled/></palette></property>",
    )
    window, pane, session, realizer = _pane(qapp, form)
    try:
        _select(session, "nameLabel")
        pane.flush()
        row = pane.findChild(QWidget, "formBuilder.row.textColour")
        assert "#FF0000" in row.findChild(RowSummary).summary
        captions = [label.text() for label in row.findChildren(QLabel) if label.isVisibleTo(pane)]
        assert "Set by the palette. ChoreBoy shows its own text colour; pick a colour here to override it." in captions
        _pick(pane, window, "textColour", "#00FF00")
        _pick(pane, window, "backgroundColour", "#0000FF")
        row = pane.findChild(QWidget, "formBuilder.row.textColour")
        row.findChild(RowSummary).click()
        QApplication.processEvents()
        _open_popover(window).findChild(QPushButton, "formBuilder.popoverReset").click()
        QApplication.processEvents()
        pane.flush()
        assert _stored(session, "nameLabel", "styleSheet") is None
        palette = _stored(session, "nameLabel", "palette")
        assert {item.role for item in palette.active} == {"WindowText", "Window"}
    finally:
        _close(window, pane, realizer, session, qapp)


def test_a_sheet_that_already_sets_the_colour_is_named_and_the_style_sheet_row_summarises(qapp) -> None:  # type: ignore[no-untyped-def]
    form = _FORM.replace(
        '<widget class="QWidget" name="Form">',
        '<widget class="QWidget" name="Form"><property name="styleSheet"><string notr="true">QPushButton { background: #123456; }</string></property>',
    )
    window, pane, session, realizer = _pane(qapp, form)
    try:
        _select(session, "okButton")
        pane.flush()
        row = pane.findChild(QWidget, "formBuilder.row.backgroundColour")
        warnings = [label.text() for label in row.findChildren(QLabel) if label.isVisibleTo(pane)]
        assert any("The style sheet sets this colour, so this one has no effect." in text for text in warnings)
        assert not any(
            "no effect" in label.text()
            for label in pane.findChild(QWidget, "formBuilder.row.textColour").findChildren(QLabel)
            if label.isVisibleTo(pane)
        )
        _select(session, "Form")
        pane.flush()
        sheet_row = pane.findChild(QWidget, "formBuilder.row.styleSheet")
        assert "1 rule" in [label.text() for label in sheet_row.findChildren(QLabel)]
    finally:
        _close(window, pane, realizer, session, qapp)


def test_the_form_has_a_look_group_for_accent_colour_and_text_size(qapp) -> None:  # type: ignore[no-untyped-def]
    window, pane, session, realizer = _pane(qapp, _FORM)
    try:
        session.selection.clear(source=SelectionSource.PROGRAM)
        pane.flush()
        look = pane.findChild(QWidget, "formBuilder.formGroup.look")
        assert look is not None and look.isVisibleTo(pane)
        before = session.text()
        size = look.findChild(QSpinBox, "formBuilder.textSize")
        size.setValue(12)
        QApplication.processEvents()
        pane.flush()
        font = _stored(session, "Form", "font")
        assert isinstance(font, FontValue) and font.pointsize == 12
        assert realizer.root_widget.font().pointSize() == 12
        assert "Every widget that doesn't set its own size follows this." in [label.text() for label in look.findChildren(QLabel)]
        assert session.log.undo()
        assert session.text() == before
    finally:
        _close(window, pane, realizer, session, qapp)


_PALETTE_LABEL = _FORM.replace(
    '<property name="text"><string>Name</string></property>',
    '<property name="text"><string>Name</string></property>'
    '<property name="palette"><palette><active><colorrole role="WindowText"><brush brushstyle="SolidPattern">'
    '<color alpha="255"><red>255</red><green>0</green><blue>0</blue></color></brush></colorrole></active>'
    "<inactive/><disabled/></palette></property>",
)


def test_the_palette_editor_warns_under_a_text_role_that_is_set_and_only_there(qapp) -> None:  # type: ignore[no-untyped-def]
    from app.features.form_builder.qtside.inspector.api import GroupId

    window, pane, session, realizer = _pane(qapp, _PALETTE_LABEL)
    try:
        _select(session, "nameLabel")
        pane.set_group_expanded(GroupId.ALL, True)
        pane.flush()
        pane.findChild(QWidget, "formBuilder.row.palette").findChild(RowSummary).click()
        QApplication.processEvents()
        popover = _open_popover(window)
        notes = [label for label in popover.findChildren(QLabel, "formBuilder.paletteTextNote") if label.isVisibleTo(popover)]
        assert [label.text() for label in notes] == [
            "ChoreBoy's theme sets text colours, so this has no effect when the app runs. Use Text colour in Appearance."
        ]
        # The value is still written for Designer and other runtimes.
        assert isinstance(_stored(session, "nameLabel", "palette"), PaletteValue)
    finally:
        _close(window, pane, realizer, session, qapp)


def test_the_accent_colour_writes_highlight_and_link_on_the_root_palette(qapp) -> None:  # type: ignore[no-untyped-def]
    window, pane, session, realizer = _pane(qapp, _FORM)
    try:
        session.selection.clear(source=SelectionSource.PROGRAM)
        pane.flush()
        before = session.text()
        look = pane.findChild(QWidget, "formBuilder.formGroup.look")
        look.findChild(RowSummary).click()
        QApplication.processEvents()
        popover = _open_popover(window)
        field = popover.findChild(QLineEdit, "formBuilder.colorHex")
        field.setText("#1A7F37")
        QTest.keyClick(field, Qt.Key.Key_Return)
        QApplication.processEvents()
        popover.done()
        pane.flush()
        palette = _stored(session, "Form", "palette")
        assert isinstance(palette, PaletteValue)
        for group in (palette.active, palette.inactive, palette.disabled):
            assert sorted(item.role for item in group) == ["Highlight", "Link"]
        assert session.log.undo()
        assert session.text() == before
    finally:
        _close(window, pane, realizer, session, qapp)


def test_selecting_the_form_shows_the_look_group_and_widgets_do_not_have_it(qapp) -> None:  # type: ignore[no-untyped-def]
    window, pane, session, realizer = _pane(qapp, _FORM)
    try:
        _select(session, "Form")
        pane.flush()
        order = _keys(pane, "appearance")
        picked = [key for key in order if key in ("font", "textColour", "backgroundColour", "styleSheet")]
        assert picked == ["font", "textColour", "backgroundColour", "styleSheet"]
        look = pane.findChild(QWidget, "formBuilder.formGroup.look")
        assert look is not None and look.isVisibleTo(pane)
        before = session.text()
        box = look.findChild(QSpinBox, "formBuilder.textSize")
        assert box.isVisibleTo(pane)
        box.setValue(14)
        QApplication.processEvents()
        assert session.log.undo_label() == "Change text size"
        assert realizer.root_widget.font().pointSize() == 14
        _select(session, "okButton")
        pane.flush()
        assert not look.isVisibleTo(pane)
        assert session.log.undo()
        assert session.text() == before
    finally:
        _close(window, pane, realizer, session, qapp)
