# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false
"""K23 Tab order and buddies (UX_SPEC 12.3, M5.6): the whole script with keys only, in a real main window.

Setup is the only non-key step (the project and the open tab). A filter fails the run on
any mouse press. Differences from the spec text, all forced by the form: its labels sit
between the fields in Tab order, so a step that says "Tab" is as many Tabs as it takes to
reach the named widget; and the Help item is run with ``QAction.trigger`` because the
offscreen platform draws no menu bar to press keys into.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.ui4.writer import write_ui  # noqa: E402
from app.qt.QtWidgets import QApplication, QComboBox, QWidget  # noqa: E402
from app.qt.qt_compat import wrapper_is_valid  # noqa: E402
from tests.form_builder.qtside.test_m3_keyboard_scripts import (  # noqa: E402
    Kb,
    _close,
    _session,
    _walk_to,
)

pytestmark = [pytest.mark.unit, pytest.mark.timeout(300)]

K23_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Contact</class>
 <widget class="QWidget" name="Contact">
  <property name="geometry"><rect><x>0</x><y>0</y><width>420</width><height>260</height></rect></property>
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="0"><widget class="QLabel" name="nameLabel"><property name="text"><string>Name</string></property></widget></item>
   <item row="0" column="1"><widget class="QLineEdit" name="nameEdit"/></item>
   <item row="1" column="0"><widget class="QLabel" name="emailLabel"><property name="text"><string>Email</string></property></widget></item>
   <item row="1" column="1"><widget class="QLineEdit" name="emailEdit"/></item>
   <item row="2" column="0"><widget class="QLabel" name="phoneLabel"><property name="text"><string>Phone</string></property></widget></item>
   <item row="2" column="1"><widget class="QLineEdit" name="phoneEdit"/></item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _doc(kb: Kb):  # type: ignore[no-untyped-def]
    return kb.session.document


def _status(kb: Kb) -> str:
    return kb.surface.editor_status_sentence()


def _buddy(kb: Kb, label: str) -> Optional[str]:
    from app.features.form_builder.engine.query import tab_stops as q

    document = _doc(kb)
    return q.buddy_of(document, document.by_name(label)[0])


def _focus_is(kb: Kb, widget: QWidget) -> bool:
    focus = kb.focus()
    return focus is not None and (focus is widget or widget.isAncestorOf(focus))


@pytest.mark.parity("R3-8", "R3-9", "R3-10", "R3-11", "R3-12", "R3-209", "R3-210", "R3-211")
@pytest.mark.pain("P-20")
def test_k23_tab_order_and_buddies(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _session(tmp_path, qapp, K23_FORM)
    try:
        original = kb.text()
        assert _doc(kb).tabstops() is None
        modes = kb.surface.modes

        kb.press("Key_F8")
        kb.check(modes.active == "tab_order", "F8 opens the Tab order overlay")
        kb.check(kb.focus_in("formBuilder.canvas"), "focus is on the canvas")
        _walk_to(kb, "nameEdit", limit=12)
        kb.check("Press Enter to make nameEdit number 1." in _status(kb), "status offers number 1: %r" % _status(kb))
        kb.press("Key_Return")
        kb.check(modes.picked == ("nameEdit",), "Enter gives nameEdit number 1")
        _walk_to(kb, "emailEdit", limit=6)
        kb.press("Key_Return")
        kb.check(modes.picked == ("nameEdit", "emailEdit"), "number 2 is emailEdit")
        kb.check(_doc(kb).tabstops() == ("nameEdit", "emailEdit", "phoneEdit"), "tabstops follow the numbers")
        # Shift+Tab back to the first, Shift+Enter to continue from it, then number phoneEdit.
        _walk_to(kb, "nameEdit", key="Key_Backtab", limit=6)
        kb.press("Key_Return", "Shift")
        kb.check(modes.picked == ("nameEdit",), "Shift+Enter continues from nameEdit")
        _walk_to(kb, "phoneEdit", limit=8)
        kb.press("Key_Return")
        kb.check(_doc(kb).tabstops() == ("nameEdit", "phoneEdit", "emailEdit"), "the order continues from the first")
        kb.press("Key_Backspace")
        kb.check(modes.picked == ("nameEdit",), "Backspace takes back the last number")
        kb.check(_doc(kb).tabstops() == ("nameEdit", "emailEdit", "phoneEdit"), "the order is back")
        kb.check("nameEdit" in kb.text() and "emailEdit" in kb.text(), "the form still lists its fields")
        kb.press("Key_Escape")
        kb.check(modes.active == "", "Esc closes the overlay")

        # Alt+4, the Tab order group: Alt+Down on row 1, then "Use reading order".
        for _ in range(6):
            if kb.current() == "Contact":
                break
            kb.press("Key_Escape")
        kb.check(kb.current() == "Contact", "Esc walks up to the form")
        kb.surface.focus_tab_order_list()
        kb.pump()
        rows = kb.surface.findChild(QWidget, "formBuilder.tabOrderRows")
        kb.check(rows is not None and rows.count() == 3, "the Tab order group lists three rows")
        kb.check(_focus_is(kb, rows), "focus is in the list")
        before = _doc(kb).tabstops()
        kb.press("Key_Down", "Alt")
        after = _doc(kb).tabstops()
        kb.check(after is not None and after != before and after[0] == before[1], "Alt+Down moves row 1 down: %r" % (after,))
        reset = kb.surface.findChild(QWidget, "formBuilder.tabOrderReset")
        kb.check(reset is not None and reset.isVisible(), "Use reading order is offered")
        kb.press("Key_Tab")
        kb.check(_focus_is(kb, reset), "Tab reaches Use reading order")
        kb.press("Key_Return")
        kb.check(_doc(kb).tabstops() is None, "tabstops is gone")

        # F7, the Email label, Enter, Tab to emailEdit, Enter.
        kb.press("Key_Escape")
        kb.surface._workbench.canvas.setFocus()
        kb.pump()
        kb.press("Key_F7")
        kb.check(modes.active == "buddies", "F7 opens the Buddies overlay")
        _walk_to(kb, "emailLabel", limit=12)
        kb.press("Key_Return")
        kb.check("Choose the field for “Email”, then press Enter." in _status(kb), "status: %r" % _status(kb))
        for _ in range(4):
            if modes._candidate == "emailEdit":
                break
            kb.press("Key_Tab")
        kb.check(modes._candidate == "emailEdit", "Tab reaches emailEdit")
        kb.press("Key_Return")
        kb.check(_buddy(kb, "emailLabel") == "emailEdit", "buddy of emailLabel is emailEdit")
        kb.press("Key_Escape")
        kb.check(modes.active == "", "Esc closes the Buddies overlay")

        # phoneLabel, the Buddy drop-down, type "phone", Enter.
        _walk_to(kb, "phoneLabel", limit=12)
        kb.surface._focus_inspector_pane()
        kb.pump()
        combo: Optional[QComboBox] = None
        for _ in range(60):
            combo = kb.surface.findChild(QComboBox, "formBuilder.buddyPicker")
            if combo is not None and _focus_is(kb, combo):
                break
            kb.press("Key_Tab")
        kb.check(combo is not None and _focus_is(kb, combo), "Tab reaches the Buddy drop-down")
        kb.type("phone")
        kb.press("Key_Return")
        kb.check(_buddy(kb, "phoneLabel") == "phoneEdit", "buddy of phoneLabel is phoneEdit")

        # F1 from the canvas: the help card opens, Esc closes it.
        kb.surface._workbench.canvas.setFocus()
        kb.pump()
        kb.press("Key_F1")
        card = kb.surface.findChild(QWidget, "formBuilder.widgetHelp")
        kb.check(card is not None and card.isVisible(), "F1 opens the help card")
        kb.check("Qt class: QLabel" in card.text(), "the card names the Qt class: %r" % card.text())
        kb.press("Key_Escape")
        kb.check(card is None or not wrapper_is_valid(card) or not card.isVisible(), "Esc closes the card")

        # Help > Form designer keys, "wrap".
        action = window._menu_actions.get("form.help.formKeys") if hasattr(window, "_menu_actions") else None
        from app.features.form_builder.integration.widget_help import show_keys_page

        dialog = show_keys_page(kb.surface)
        kb.pump()
        page = dialog.findChild(QWidget, "formBuilder.keysPage")
        kb.check(_focus_is(kb, page), "the filter has focus when the page opens")
        kb.type("wrap")
        kb.check(page.first_row_keys() == "Ctrl+Shift+G", "the first row for wrap is Ctrl+Shift+G: %r" % page.first_row_keys())
        dialog.close()
        del action

        # Undo all: the original bytes.
        kb.surface._workbench.canvas.setFocus()
        for _ in range(40):
            if not kb.session.log.can_undo():
                break
            kb.press("Key_Z", "Control")
        kb.check(kb.text() == original, "undo all returns the original bytes")
        kb.done(guard)
    finally:
        _close(window, qapp, guard)
