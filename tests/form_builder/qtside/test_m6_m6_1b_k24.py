# pyright: reportAttributeAccessIssue=false
"""K24 Events list (UX_SPEC 12.3): keys only, on sale.ui."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtWidgets import QApplication, QLabel  # noqa: E402
from tests.form_builder.qtside.test_m3_keyboard_scripts import Kb, _close, _session  # noqa: E402

pytestmark = [pytest.mark.unit, pytest.mark.timeout(300)]

_SALE = (Path(__file__).resolve().parents[1] / "fixtures" / "m6" / "forms" / "sale.ui").read_text(encoding="utf-8")


def _label(kb: Kb) -> str:
    return str(kb.session.log.undo_label())  # type: ignore[attr-defined]


def _depth(kb: Kb) -> int:
    return len(kb.session.log.entries())  # type: ignore[attr-defined]


def _focus_shows(kb: Kb, words: str) -> bool:
    widget = kb.focus()
    while widget is not None:
        if words in (widget.accessibleName() or "") and widget.isVisible():
            return True
        widget = widget.parentWidget()
    return False


def _go(kb: Kb, name: str) -> None:
    kb.press("Key_R", "Control")
    kb.type(name)
    kb.press("Key_Return")
    kb.check(kb.selected() == (name,), "selected %s, have %s" % (name, kb.selected()))


def _add_close(kb: Kb) -> None:
    before = _depth(kb)
    kb.press("Key_E", "Control", "Shift")
    kb.press("Key_Return")
    kb.type("close")
    kb.press("Key_Return")
    kb.check(_depth(kb) == before + 1, "one undo step for Close this form")
    kb.check(_label(kb) == "Add Close this form to Cancel clicked", _label(kb))
    kb.check(_focus_shows(kb, "Close this form"), "Close this form is focused")
    text = kb.text()
    kb.check("<sender>cancelButton</sender>" in text and "<slot>close()</slot>" in text, "cancel closes the form")


def test_k24_events_list(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _session(tmp_path, qapp, _SALE)
    try:
        original = kb.text()
        _go(kb, "cancelButton")
        kb.press("Key_B", "Alt")
        kb.check(
            any("Nothing happens yet when Cancel is clicked." in widget.text() for widget in kb.surface.findChildren(QLabel)),  # type: ignore[attr-defined]
            "empty Cancel sentence",
        )
        _add_close(kb)

        _go(kb, "clearButton")
        kb.press("Key_B", "Alt")
        before = _depth(kb)
        kb.press("Key_E", "Control", "Shift")
        kb.press("Key_Return")
        kb.type("clear")
        kb.press("Key_Return")
        kb.type("name")
        kb.press("Key_Return")
        kb.check(_depth(kb) == before + 1, "one undo step for Clear Name")
        kb.check(_label(kb) == "Add Clear Name to Clear clicked", _label(kb))
        kb.check(_focus_shows(kb, "Clear Name (nameEdit)"), "Clear Name is focused")

        before = _depth(kb)
        kb.press("Key_Down")
        kb.press("Key_Return")
        kb.type("focus")
        kb.press("Key_Return")
        kb.type("name")
        kb.press("Key_Return")
        kb.check(_depth(kb) == before + 1, "one undo step for Move focus")
        kb.check(_label(kb) == "Add Move focus to Name to Clear clicked", _label(kb))
        kb.check(_focus_shows(kb, "Move focus to Name"), "Move focus is focused")

        before = _depth(kb)
        kb.press("Key_Up", "Alt")
        kb.check(_depth(kb) == before + 1, "one undo step for the move")
        kb.check(_label(kb) == "Move Move focus to Name", _label(kb))
        text = kb.text()
        clear_block = text[text.find("<sender>clearButton</sender>") :]
        kb.check(clear_block.find("setFocus") < clear_block.find("clear()"), "the two clear steps swapped")

        before = _depth(kb)
        kb.press("Key_Space")
        kb.check(_depth(kb) == before + 1 and _label(kb) == "Turn off Move focus to Name", _label(kb))
        text = kb.text()
        kb.check("<sender>clearButton</sender>" not in text, "no clearButton connection")
        kb.check("cbcsOnClicked" in text and "cbcsLogic" in text, "step list and marker")
        focus = kb.focus()
        kb.check(focus is not None and "(off)" in focus.accessibleName(), "turned off, have %s" % ("" if focus is None else focus.accessibleName()))

        before = _depth(kb)
        kb.press("Key_Space")
        kb.check(_depth(kb) == before + 1 and _label(kb) == "Turn on Move focus to Name", _label(kb))
        text = kb.text()
        kb.check("cbcsOnClicked" not in text and "cbcsLogic" not in text, "back to native connections")
        clear_bits = text.split("<sender>clearButton</sender>")
        kb.check(len(clear_bits) == 3, "two clearButton connections")
        kb.check(clear_bits[1].find("setFocus") != -1 and clear_bits[2].find("clear()") != -1, "focus then clear")

        before = _depth(kb)
        kb.press("Key_Down")
        kb.press("Key_D", "Control")
        kb.check(_depth(kb) == before + 1 and _label(kb) == "Duplicate Clear Name", _label(kb))
        before = _depth(kb)
        kb.press("Key_Delete")
        kb.check(_depth(kb) == before + 1 and _label(kb) == "Delete Clear Name", _label(kb))

        for _ in range(8):
            if kb.selected() == ("Sale",):
                break
            kb.press("Key_Escape")
        kb.check(kb.selected() == ("Sale",), "the form is selected, have %s" % (kb.selected(),))
        kb.press("Key_B", "Alt")
        form = kb.pane("formBuilder.events.form")
        rows = [label for label in form.findChildren(QLabel) if "\u00b7" in label.text() and label.isVisible()]
        kb.check(len(rows) == 5, "five event rows, have %d" % len(rows))
        for _ in range(15):
            if kb.focus_name() == "formBuilder.events.formFilter":
                break
            kb.press("Key_Tab")
        kb.check(kb.focus_name() == "formBuilder.events.formFilter", "the filter has focus")
        kb.type("clear")
        kb.pump()
        left = [label for label in form.findChildren(QLabel) if "\u00b7" in label.text() and label.isVisible()]
        kb.check(len(left) == 2, "Clear's two rows, have %d: %s" % (len(left), [label.text() for label in left]))

        _go(kb, "nameEdit")
        kb.press("Key_B", "Alt")
        incoming = kb.pane("formBuilder.events.incoming")
        kb.check(
            any(label.text() == "When Clear is clicked: Clear Name" for label in incoming.findChildren(QLabel)),
            "incoming Clear Name",
        )

        while kb.session.log.can_undo():  # type: ignore[attr-defined]
            kb.press("Key_Z", "Control")
        kb.check(kb.text() == original, "undo restored the form")
        kb.done(guard)
    finally:
        _close(window, qapp, guard)
