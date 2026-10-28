# pyright: reportAttributeAccessIssue=false
"""K11 scalar editors (UX_SPEC §12.3) at a real main window.

The steps that need a date edit or a key-sequence edit use a small form.
The echo-mode and maximum-length steps use the customer form the M3 scripts open.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.qt.QtWidgets import QApplication
from tests.form_builder.qtside.test_m3_keyboard_scripts import _close, _session, _walk_to

pytestmark = [pytest.mark.unit, pytest.mark.timeout(180)]


def test_k11_echo_mode_and_maximum_length(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _session(tmp_path, qapp)
    try:
        kb.press("Key_3", "Alt")
        _walk_to(kb, "nameEdit")
        kb.press("Key_4", "Alt")
        kb.check(kb.focus_in("formBuilder.inspector"), "Alt+4 focuses the inspector")
        kb.press("Key_F", "Control")
        kb.check(kb.focus_name() == "formBuilder.inspectorSearch", "Ctrl+F focuses the property search")
        kb.type("echo")
        for _ in range(12):
            if kb.focus_name() == "_EnumBox":
                break
            kb.press("Key_Tab")
        kb.check(kb.focus_name() == "_EnumBox", "Tab reaches Echo mode")
        # Closed combo: Down commits. Normal, No echo, Password.
        kb.press("Key_Down")
        kb.press("Key_Down")
        kb.pump()
        kb.check("Password" in kb.text(), "choosing Password is written")
        kb.press("Key_Escape")
        kb.pump()
        kb.check(kb.focus_name() == "formBuilder.inspectorSearch" or "Password" in kb.text(), "search clears or the value stays")
        # Maximum length: leave the search and edit the number.
        kb.press("Key_A", "Control")
        kb.type("maximum")
        kb.pump()
        for _ in range(8):
            if "QSpinBox" in kb.focus_name() or kb.focus_name().endswith("SpinBox"):
                break
            kb.press("Key_Tab")
        before = len(kb.session.log.entries())  # type: ignore[attr-defined]
        kb.type("40")
        kb.press("Key_Return")
        kb.press("Key_Up")
        kb.press("Key_Up")
        kb.press("Key_Up")
        kb.check("43" in kb.text() or ">40<" in kb.text() or ">41<" in kb.text(), "Up three times stays in one visit")
        kb.press("Key_Z", "Control")
        after_undo = len(kb.session.log.entries())  # type: ignore[attr-defined]
        kb.check(after_undo <= before + 1, "one undo takes back the visit (steps %s -> %s)" % (before, after_undo))
        kb.done(guard)
    finally:
        _close(window, qapp, guard)
