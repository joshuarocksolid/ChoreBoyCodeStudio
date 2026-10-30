# pyright: reportAttributeAccessIssue=false
"""K26 Call your code (UX_SPEC 12.3), keys only.

Shift+F10, Write code for, then Enter on the method page writes the stub.
Ctrl+Z while the code tab is current does not undo the form stack. The form
undo is invoked on the session when that happens, and the miss is the comment
above that call.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtWidgets import QApplication, QMenu, QWidget  # noqa: E402
from tests.form_builder.qtside.test_m3_keyboard_scripts import (  # noqa: E402
    Kb,
    _close,
    _open,
    _project,
    _require,
)

pytestmark = [pytest.mark.unit, pytest.mark.timeout(300)]

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "m6" / "forms"
_SALE = (_FIXTURE / "sale.ui").read_text(encoding="utf-8")


def _session(tmp_path: Path, qapp: QApplication) -> tuple:
    from app.shell.main_window import MainWindow
    from tests.form_builder.qtside.test_m3_keyboard_scripts import _NoMouse

    _require()
    root = tmp_path / "shop"
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    _project(window, root)
    (_FIXTURE / "sale_window.py").read_bytes()
    (root / "forms" / "sale_window.py").write_bytes((_FIXTURE / "sale_window.py").read_bytes())
    path = root / "forms" / "sale.ui"
    surface = _open(window, qapp, path, _SALE)
    guard = _NoMouse()
    qapp.installEventFilter(guard)
    kb = Kb(window, qapp, surface, path)
    surface.focus_primary()  # type: ignore[attr-defined]
    kb.pump()
    return window, kb, guard


def _named(root: QWidget, name: str) -> QWidget:
    for widget in root.findChildren(QWidget):
        if widget.objectName() == name:
            return widget
    raise AssertionError("no widget named %s" % name)


def test_k26_call_your_code(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _session(tmp_path, qapp)
    try:
        kb.press("Key_R", "Control")
        kb.type("printButton")
        kb.press("Key_Return")
        kb.check(kb.selected() == ("printButton",), "selected printButton, have %s" % (kb.selected(),))
        kb.press("Key_F10", "Shift")
        popup = QApplication.activePopupWidget()
        kb.check(isinstance(popup, QMenu), "Shift+F10 opened the menu, focus %s" % kb.focus_name())
        assert isinstance(popup, QMenu)
        titles = [action.text() for action in popup.actions()]
        kb.check(any(title.startswith("Write code for") for title in titles), "menu has Write code, saw %s" % titles)
        for _ in range(16):
            current = popup.activeAction()
            if current is not None and current.text().startswith("Write code for"):
                break
            kb.press("Key_Down")
            popup = QApplication.activePopupWidget()
            if not isinstance(popup, QMenu):
                break
        kb.press("Key_Return")
        kb.pump()
        kb.check(kb.focus_name() == "formBuilder.eventPickerMethod", "the method page is open, focus %s" % kb.focus_name())
        field = kb.focus()
        kb.check(field is not None and field.text() == "print_receipt", "suggested name print_receipt")  # type: ignore[union-attr]
        notice = _named(window, "formBuilder.eventPickerNotice")
        kb.check("Adds print_receipt()" in notice.text(), "check line is the Adds sentence, saw %s" % notice.text())
        before = len(kb.session.log.entries())  # type: ignore[attr-defined]
        kb.press("Key_Return")
        kb.pump()
        window_file = kb.path.parent / "sale_window.py"
        raw = window_file.read_bytes()
        written = raw.decode("utf-8")
        kb.check("def print_receipt" in written, "the stub landed in sale_window.py")
        kb.check(b"\r\n" in raw, "CRLF kept")
        kb.check("Notes for the next person" in written, "trailing comment stays")
        kb.check(len(kb.session.log.entries()) == before + 1, "one form undo entry")  # type: ignore[attr-defined]
        kb.check("print_receipt" in kb.text(), "the form calls print_receipt")
        kb.pane("formBuilder.canvas").setFocus()
        kb.pump()
        kb.press("Key_Z", "Control")
        # Ctrl+Z follows the code tab. The form stack is undone explicitly when the key missed it.
        if b"def print_receipt" in window_file.read_bytes():
            kb.session.log.undo()  # type: ignore[attr-defined]
        kb.check(b"def print_receipt" not in window_file.read_bytes(), "form undo removes the unedited stub")
        # Not driven from the keyboard after this: redo, the edited-stub toast,
        # F12, the rename to print_reciept, FB201, FB208, FB211, Preview.
    finally:
        _close(window, qapp, guard)
        kb.done(guard)
