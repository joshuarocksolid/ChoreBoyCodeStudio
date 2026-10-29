# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false, reportArgumentType=false
"""K18 Style (UX_SPEC 12.3), keys only: the style sheet drawer, Text colour, Background and Text size."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QWidget
from tests.form_builder.qtside.test_m3_keyboard_scripts import Kb, _close, _session

pytestmark = [pytest.mark.unit, pytest.mark.timeout(300), pytest.mark.parity("R3-176"), pytest.mark.pain("P-8")]

_SHOP = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Shop</class>
 <widget class="QWidget" name="Shop">
  <property name="geometry"><rect><x>0</x><y>0</y><width>420</width><height>300</height></rect></property>
  <layout class="QVBoxLayout" name="mainLayout">
   <item><widget class="QLabel" name="titleLabel"><property name="text"><string>Shop</string></property></widget></item>
   <item><widget class="QPushButton" name="okButton"><property name="text"><string>OK</string></property></widget></item>
   <item><widget class="QPushButton" name="cancelButton"><property name="text"><string>Cancel</string></property></widget></item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _wait(kb: Kb, ms: int) -> None:
    QTest.qWait(ms)
    kb.pump()


def _green(surface: object, name: str) -> bool:
    session = surface.session
    widget = surface.realized_object(session.document.by_name(name)[0])
    image = widget.grab().toImage()
    color = image.pixelColor(image.width() // 2, 3)
    return color.green() > color.red() + 40 and color.green() > color.blue() + 40


def _walk_to(kb: Kb, name: str) -> None:
    kb.press("Key_3", "Alt")
    for _ in range(14):
        if kb.current() == name:
            _wait(kb, 80)
            return
        kb.press("Key_Tab")
    kb.check(kb.current() == name, "Tab reaches %s" % name)


def _find_row(kb: Kb, words: str, row: str) -> None:
    """Alt+4, Ctrl+F, the words, then Tab until focus is inside the row that was found."""
    kb.press("Key_4", "Alt")
    kb.press("Key_F", "Control")
    kb.type(words)
    for _ in range(6):
        kb.press("Key_Tab")
        focus = QApplication.focusWidget()
        holder = kb.pane("formBuilder.row.%s" % row) if kb.surface.findChild(QWidget, "formBuilder.row.%s" % row) else None
        if focus is not None and holder is not None and (focus is holder or holder.isAncestorOf(focus)):
            return
    kb.check(False, "Tab reaches the %s row" % row)


def test_k18_style(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _session(tmp_path, qapp, _SHOP)
    try:
        surface = kb.surface
        original = kb.text()
        session = kb.session
        # The button, then the Style sheet row: Enter opens the drawer with focus in its editor.
        _walk_to(kb, "okButton")
        _find_row(kb, "style", "styleSheet")
        kb.check(kb.focus_name() == "formBuilder.styleEdit", "Tab reaches the Style sheet row's Edit button")
        kb.press("Key_Return")
        drawer = surface.workbench._under_widget
        kb.check(surface.workbench.under_canvas_key() == "style", "Enter opens the style sheet drawer")
        kb.check(QApplication.focusWidget() is drawer.editor, "focus is in the drawer's editor")
        kb.type("QPushButton#okButton { background: #1A7F37; }")
        _wait(kb, 400)
        kb.check(_green(surface, "okButton"), "after 300 ms the canvas button is green")
        kb.check(drawer.status_text().endswith("Looks right"), "the status reads Looks right")
        kb.check([chip[1] for chip in drawer.chips()] == ["1 widget"], "the chip reads 1 widget")
        kb.press("Key_Backspace")
        _wait(kb, 400)
        kb.check(drawer.status_text().endswith("Line 1: a } is missing."), "the status names the line")
        kb.check(_green(surface, "okButton"), "the button stays green")
        kb.type("}")
        _wait(kb, 400)
        kb.press("Key_Escape")
        kb.check(surface.workbench.under_canvas_key() == "", "Esc closes the drawer")
        kb.check(kb.focus_name() == "formBuilder.styleEdit", "focus is on the Style sheet row")
        kb.check(session.log.undo_label() == "Change style sheet of okButton", "one step: Change style sheet of okButton")
        # Text colour and Background of a label.
        _walk_to(kb, "titleLabel")
        for words, row, color in (
            ("text colour", "textColour", "#FFFFFF"),
            ("background", "backgroundColour", "#1A7F37"),
        ):
            _find_row(kb, words, row)
            kb.press("Key_Return")
            for _ in range(12):
                if kb.focus_name() == "formBuilder.colorHex":
                    break
                kb.press("Key_Tab")
            kb.check(kb.focus_name() == "formBuilder.colorHex", "Tab reaches Hex in the %s popover" % words)
            kb.press("Key_A", "Control")
            kb.type(color)
            kb.press("Key_Return")
            popover = [w for w in surface.findChildren(QWidget, "formBuilder.rowPopover") if w.isVisible()]
            if popover:
                kb.press("Key_Escape")
            kb.check(
                not [w for w in surface.findChildren(QWidget, "formBuilder.rowPopover") if w.isVisible()],
                "the %s popover is closed" % words,
            )
        text = kb.text()
        kb.check("color: #FFFFFF;" in text, "the label's style sheet has the text colour")
        kb.check(text.count('<colorrole role="Window">') == 3 and "autoFillBackground" in text, "the XML has the Window role and the fill")
        # The form's Look group.
        kb.press("Key_3", "Alt")
        for _ in range(8):
            if kb.selected() == ("Shop",):
                break
            kb.press("Key_Escape")
        kb.check(kb.selected() == ("Shop",), "Esc selects the form")
        _wait(kb, 80)
        kb.press("Key_4", "Alt")
        kb.press("Key_F", "Control")
        kb.press("Key_Backspace")
        for _ in range(30):
            kb.press("Key_Tab")
            if kb.focus_name() == "formBuilder.textSize":
                break
        kb.check(kb.focus_name() == "formBuilder.textSize", "Tab reaches Text size")
        kb.press("Key_A", "Control")
        kb.type("12")
        kb.press("Key_Return")
        _wait(kb, 100)
        kb.check("<pointsize>12</pointsize>" in kb.text(), "Text size 12 is on the form's font")
        # Undo all: the original bytes.
        kb.press("Key_3", "Alt")
        for _ in range(20):
            if not session.log.can_undo():
                break
            kb.press("Key_Z", "Control")
        kb.check(kb.text() == original, "undo all returns the original bytes")
        kb.done(guard)
    finally:
        _close(window, qapp, guard)
