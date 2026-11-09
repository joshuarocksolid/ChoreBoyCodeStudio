# pyright: reportAttributeAccessIssue=false
"""K11 choices and numbers (UX_SPEC §12.3) at a real main window.

Keys only, after the tab is open. Save and reopen go through the shell.
Close and reopen start a new undo stack, so the final Undo all returns to
the bytes that were on disk after the save, which still hold Password.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QLabel, QWidget
from tests.form_builder.qtside.test_m3_keyboard_scripts import Kb, _close, _key, _mods, _session, _walk_to

pytestmark = [pytest.mark.unit, pytest.mark.timeout(180)]

_K11 = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Customer</class>
 <widget class="QWidget" name="Customer">
  <property name="geometry"><rect><x>0</x><y>0</y><width>480</width><height>420</height></rect></property>
  <layout class="QVBoxLayout" name="mainLayout">
   <item>
    <widget class="QLabel" name="nameLabel">
     <property name="text"><string>Name:</string></property>
    </widget>
   </item>
   <item><widget class="QLineEdit" name="nameEdit"/></item>
   <item><widget class="QDateEdit" name="whenEdit"/></item>
   <item><widget class="QKeySequenceEdit" name="keysEdit"/></item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _row_key(widget: QWidget) -> str:
    current = widget
    while current is not None:
        name = str(current.objectName())
        if name.startswith("formBuilder.row."):
            return name[len("formBuilder.row.") :]
        parent = current.parentWidget()
        current = parent if isinstance(parent, QWidget) else None
    return ""


def _tab_to_row(kb: Kb, key: str, limit: int = 80) -> None:
    for _ in range(limit):
        focus = kb.focus()
        if isinstance(focus, QWidget) and _row_key(focus) == key:
            return
        if kb.focus_in("formBuilder.inspector"):
            kb.press("Key_Tab")
        else:
            kb.press("Key_Backtab", "Shift")
    kb.check(False, "Tab reaches the %s row" % key)


def _tab_to_editor(kb: Kb, key: str, limit: int = 80) -> None:
    """The value control, not the reset button that shares the row."""
    for _ in range(limit):
        focus = kb.focus()
        if not isinstance(focus, QWidget):
            kb.press("Key_Tab")
            continue
        if _row_key(focus) == key and str(getattr(focus, "objectName")()) != "formBuilder.rowReset":
            return
        kb.press("Key_Tab")
    kb.check(False, "Tab reaches the %s editor" % key)


def _focus_text(kb: Kb) -> str:
    widget = kb.focus()
    text = getattr(widget, "text", None)
    if callable(text):
        return str(text())
    return ""


def _tab_to_text(kb: Kb, text: str, limit: int = 40) -> None:
    for _ in range(limit):
        if _focus_text(kb) == text:
            return
        kb.press("Key_Tab")
    kb.check(False, "Tab reaches %s" % text)


def _open_all(kb: Kb) -> None:
    header = kb.pane("formBuilder.inspector").findChild(QWidget, "formBuilder.group.all")
    kb.check(isinstance(header, QWidget), "All properties is in the inspector")
    for _ in range(200):
        if kb.focus_name() == "formBuilder.group.all":
            break
        kb.press("Key_Tab")
    kb.check(kb.focus_name() == "formBuilder.group.all", "Tab reaches All properties")
    if not bool(header.isChecked()):  # type: ignore[attr-defined]
        kb.press("Key_Space")
        kb.pump(8)


def _reopen(window: object, kb: Kb, qapp: QApplication) -> None:
    assert window._editor_tab_factory.open_file_in_editor(str(kb.path))  # type: ignore[attr-defined]  # noqa: SLF001
    stack = window._center_stack  # type: ignore[attr-defined]  # noqa: SLF001
    stack.setCurrentIndex(1)
    surface = window._tab_content_registry.surface_for_path(str(kb.path))  # type: ignore[attr-defined]  # noqa: SLF001
    assert surface is not None
    kb.surface = surface
    surface.focus_primary()
    kb.pump()


def _echo_label(kb: Kb) -> QLabel:
    row = kb.pane("formBuilder.inspector").findChild(QWidget, "formBuilder.row.echoMode")
    assert isinstance(row, QWidget)
    for label in row.findChildren(QLabel):
        if label.text() == "Echo mode":
            return label
    raise AssertionError("Echo mode label")


def test_k11_choices_and_numbers(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _session(tmp_path, qapp, _K11)
    try:
        original = kb.text()
        kb.press("Key_3", "Alt")
        _walk_to(kb, "nameEdit")
        kb.press("Key_4", "Alt")
        kb.check(kb.focus_in("formBuilder.inspector"), "Alt+4 focuses the inspector")
        kb.press("Key_F", "Control")
        kb.check(kb.focus_name() == "formBuilder.inspectorSearch", "Ctrl+F focuses the property search")
        kb.type("echo")
        _tab_to_row(kb, "echoMode")
        kb.check(kb.focus_name() == "_EnumBox", "Tab reaches Echo mode")
        kb.press("Key_Down", "Alt")
        kb.press("Key_Down")
        kb.press("Key_Down")
        kb.press("Key_Return")
        kb.check("Password" in kb.text(), "choosing Password writes it")
        kb.press("Key_Escape")
        search = kb.pane("formBuilder.inspector").findChild(QWidget, "formBuilder.inspectorSearch")
        kb.check(isinstance(search, QWidget) and search.text() == "", "Esc clears the search")  # type: ignore[attr-defined]
        kb.press("Key_S", "Control")
        kb.pump(12)
        kb.check("Password" in kb.path.read_text(encoding="utf-8"), "Ctrl+S writes Password to the file")
        # Ctrl+W disposes the session before the harness can read the selection.
        QTest.keyClick(kb.target(), _key("Key_W"), _mods("Control"))
        for _ in range(8):
            qapp.processEvents()
        _reopen(window, kb, qapp)
        kb.press("Key_3", "Alt")
        _walk_to(kb, "nameEdit")
        kb.press("Key_4", "Alt")
        _tab_to_row(kb, "echoMode")
        combo = kb.focus()
        current = getattr(combo, "currentText", None)
        kb.check(callable(current) and current() == "Password", "reopen shows Password")
        kb.check(_echo_label(kb).property("fbChanged") == "true", "Echo mode is Strong")
        saved = kb.text()

        _tab_to_row(kb, "maxLength")
        before = len(kb.session.log.entries())
        kb.press("Key_A", "Control")
        kb.type("40")
        kb.press("Key_Return")
        kb.press("Key_Up")
        kb.press("Key_Up")
        kb.press("Key_Up")
        kb.check(">43<" in kb.text() or "43" in _focus_text(kb), "Up three times makes 43")
        kb.press("Key_Z", "Control")
        kb.check(len(kb.session.log.entries()) <= before + 1, "one undo takes back the visit")
        kb.check(">43<" not in kb.text(), "undo restores the value from before the visit")
        kb.press("Key_Z", "Control", "Shift")
        kb.check(">43<" in kb.text(), "redo brings the visit back")
        kb.press("Key_Backtab", "Shift")
        _tab_to_editor(kb, "maxLength")
        kb.press("Key_Up")
        kb.check(">44<" in kb.text() or "44" in _focus_text(kb), "a second visit steps to 44")
        kb.press("Key_Z", "Control")
        kb.check(">43<" in kb.text(), "undo of the second visit stops at 43")

        kb.press("Key_3", "Alt")
        _walk_to(kb, "nameLabel", "Key_Up")
        kb.press("Key_4", "Alt")
        _open_all(kb)
        _tab_to_row(kb, "textInteractionFlags", 200)
        before_flags = kb.text()
        steps = len(kb.session.log.entries())
        kb.press("Key_Return")
        kb.check(kb.pane("formBuilder.inspector").findChild(QWidget, "formBuilder.rowPopover") is not None or kb.focus_name() != "formBuilder.summary", "Enter opens the flags popover")
        _tab_to_text(kb, "Select with mouse")
        kb.press("Key_Space")
        kb.press("Key_Escape")
        kb.pump(4)
        kb.check(kb.text() == before_flags, "Esc from the flags popover changes nothing")
        kb.check(len(kb.session.log.entries()) == steps, "Esc adds no undo step")
        _tab_to_row(kb, "textInteractionFlags", 200)
        kb.press("Key_Return")
        _tab_to_text(kb, "Select with mouse")
        kb.press("Key_Space")
        kb.press("Key_Return")
        kb.pump(4)
        kb.check(kb.text() != before_flags, "Enter keeps the flag change")
        kb.check(len(kb.session.log.entries()) == steps + 1, "the flag change is one step")

        kb.press("Key_3", "Alt")
        _walk_to(kb, "whenEdit")
        kb.press("Key_4", "Alt")
        _open_all(kb)
        _tab_to_row(kb, "date", 200)
        kb.press("Key_A", "Control")
        kb.type("12/31/2026")
        kb.press("Key_Return")
        kb.check("2026" in kb.text(), "the typed date is written")
        kb.press("Key_Down", "Alt")
        kb.press("Key_PageDown")
        kb.press("Key_Return")
        kb.pump(4)
        written = kb.text()
        kb.check("<year>2027</year>" in written and "<day>31</day>" in written, "PageDown writes January 31, 2027")

        kb.press("Key_3", "Alt")
        _walk_to(kb, "keysEdit")
        kb.press("Key_4", "Alt")
        _open_all(kb)
        _tab_to_row(kb, "keySequence", 200)
        _tab_to_text(kb, "Record")
        kb.press("Key_Return")
        kb.check("Press the keys" in _focus_text(kb), "Record asks for the keys")
        kb.press("Key_P", "Control", "Shift")
        # The chord window is 1 s from when the drain timer reads the key. Under a
        # loaded full run that timer can start late, so wait on the result.
        for _ in range(40):
            QTest.qWait(100)
            if "Ctrl+Shift+P" in kb.text():
                break
        kb.pump(8)
        kb.check("Ctrl+Shift+P" in kb.text(), "Ctrl+Shift+P is written")
        held = kb.text()
        _tab_to_text(kb, "Record")
        kb.press("Key_Return")
        kb.press("Key_Escape")
        kb.pump(4)
        kb.check(kb.text() == held, "Esc while recording leaves the shortcut")

        # A rebuild drops focus on the inspector search, and that field eats Ctrl+Z.
        kb.press("Key_3", "Alt")
        for _ in range(40):
            if not kb.session.log.can_undo():
                break
            kb.press("Key_Z", "Control")
        # The reopened tab's undo stack starts at the saved file.
        kb.check(kb.text() == saved, "undo all returns to the bytes on disk at reopen")
        kb.check(kb.text() != original and "Password" in kb.text(), "Password stays: undo does not cross the reopen")
        kb.done(guard)
    finally:
        _close(window, qapp, guard)
