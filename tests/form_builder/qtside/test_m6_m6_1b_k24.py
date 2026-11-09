# pyright: reportAttributeAccessIssue=false
"""K24 Events list (UX_SPEC 12.3): keys only, on sale.ui."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtCore import QPoint  # noqa: E402
from app.qt.QtWidgets import QApplication, QLabel, QScrollArea, QWidget  # noqa: E402
from tests.form_builder.qtside.test_m3_keyboard_scripts import Kb, _close, _session  # noqa: E402

pytestmark = [pytest.mark.unit, pytest.mark.timeout(300)]

_SALE = (Path(__file__).resolve().parents[1] / "fixtures" / "m6" / "forms" / "sale.ui").read_text(encoding="utf-8")


def _label(kb: Kb) -> str:
    return str(kb.session.log.undo_label())  # type: ignore[attr-defined]


def _depth(kb: Kb) -> int:
    return len(kb.session.log.entries())  # type: ignore[attr-defined]


def _inside(widget: QWidget, name: str) -> bool:
    current = widget
    while current is not None:
        if current.objectName() == name:
            return True
        current = current.parentWidget()
    return False


def _row_in_viewport(widget: QWidget) -> bool:
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, QScrollArea):
            view = parent.viewport()
            point = widget.mapTo(view, QPoint(1, 1))
            return view.rect().contains(point)
        parent = parent.parentWidget()
    return widget.isVisible()


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


def script_k24(kb: Kb) -> None:
    """K24 on an open sale form. Keys only. Restores the form bytes."""
    original = kb.text()
    _go(kb, "cancelButton")
    kb.press("Key_B", "Alt")
    kb.check(
        any("Nothing happens yet when Cancel is clicked." in widget.text() for widget in kb.surface.findChildren(QLabel)),  # type: ignore[attr-defined]
        "empty Cancel sentence",
    )
    kb.press("Key_Down")
    stayed = kb.focus()
    kb.check(
        stayed is not None and _inside(stayed, "formBuilder.events"),
        "Down on + When… stays in Events",
    )
    kb.press("Key_Escape")
    kb.check(kb.focus_name() == "formBuilder.canvas", "Esc returns to the canvas, have %s" % kb.focus_name())
    _add_close(kb)
    kb.press("Key_B", "Alt")
    row = kb.focus()
    kb.check(row is not None and "clicked" in (row.accessibleName() or "").lower(), "Alt+B focuses the clicked row")
    kb.check(_row_in_viewport(row), "the focused row is inside the viewport")

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
    kb.check(_focus_shows(kb, "Clear Name"), "Clear Name is focused")

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
    spoken = "" if focus is None else focus.accessibleName()
    kb.check(focus is not None and "(off)" not in spoken and spoken.endswith(", turned off"), "turned off, have %s" % spoken)

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


@pytest.mark.parity("R3-3", "R3-4", "R3-5")
@pytest.mark.pain("P-16")
@pytest.mark.logic("L-events-list", "L-signal-slot-picker")
def test_k24_events_list(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _session(tmp_path, qapp, _SALE)
    try:
        script_k24(kb)
        kb.done(guard)
    finally:
        _close(window, qapp, guard)
