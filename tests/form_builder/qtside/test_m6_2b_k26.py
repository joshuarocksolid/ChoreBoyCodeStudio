# pyright: reportAttributeAccessIssue=false
"""K26 Call your code. Every step is a key on the focused widget."""

from __future__ import annotations

import sys
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
_KEPT = "has your code in it, so it stays"


def _session(tmp_path: Path, qapp: QApplication) -> tuple:
    from app.shell.main_window import MainWindow
    from tests.form_builder.qtside.test_m3_keyboard_scripts import _NoMouse

    _require()
    if sys.platform == "darwin":
        from app.qt.QtGui import qt_set_sequence_auto_mnemonic

        qt_set_sequence_auto_mnemonic(True)
    root = tmp_path / "shop"
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    _project(window, root)
    (root / "forms" / "sale_window.py").write_bytes((_FIXTURE / "sale_window.py").read_bytes())
    path = root / "forms" / "sale.ui"
    surface = _open(window, qapp, path, _SALE)
    guard = _NoMouse()
    qapp.installEventFilter(guard)
    from app.core.models import LoadedProject, ProjectFileEntry

    project = window._loaded_project  # noqa: SLF001
    window._loaded_project = LoadedProject(  # noqa: SLF001
        project_root=project.project_root,
        manifest_path=project.manifest_path,
        metadata=project.metadata,
        entries=[
            ProjectFileEntry("forms/sale.ui", str(path.resolve()), False),
            ProjectFileEntry("forms/sale_window.py", str((root / "forms" / "sale_window.py").resolve()), False),
            ProjectFileEntry("main.py", str((root / "main.py").resolve()), False),
        ],
    )
    kb = Kb(window, qapp, surface, path)
    surface.focus_primary()  # type: ignore[attr-defined]
    kb.pump()
    return window, kb, guard, path


def _named(root: QWidget, name: str) -> QWidget:
    for widget in root.findChildren(QWidget):
        if widget.objectName() == name and widget.isVisible():
            return widget
    for widget in root.findChildren(QWidget):
        if widget.objectName() == name:
            return widget
    raise AssertionError("no widget named %s" % name)


def _editor(qapp: QApplication) -> QWidget:
    widget = qapp.focusWidget()
    assert widget is not None and hasattr(widget, "textCursor")
    return widget


def _back_to_form(kb: Kb) -> None:
    kb.press("Key_P", "Control")
    kb.type("sale.ui")
    kb.press("Key_Return")
    kb.pump(12)


def _def_place(editor: QWidget, needle: str) -> str:
    document = editor.document()  # type: ignore[attr-defined]
    block = document.begin()
    target = None
    lines = []
    number = 0
    while block.isValid():
        number += 1
        if needle in block.text():
            target = block
            lines.append("%d:%s" % (number, block.text()[:50]))
            break
        block = block.next()
    view = editor.viewport()  # type: ignore[attr-defined]
    if target is None:
        return "missing %s" % lines
    top = editor.blockBoundingGeometry(target).translated(editor.contentOffset()).top()  # type: ignore[attr-defined]
    bar = editor.verticalScrollBar()  # type: ignore[attr-defined]
    return "top=%s height=%s scroll=%s/%s lines=%s" % (top, view.height(), bar.value(), bar.maximum(), lines)


def _def_in_top_third(editor: QWidget, needle: str) -> bool:
    document = editor.document()  # type: ignore[attr-defined]
    block = document.begin()
    target = None
    while block.isValid():
        if needle in block.text():
            target = block
            break
        block = block.next()
    if target is None:
        return False
    view = editor.viewport()  # type: ignore[attr-defined]
    top = editor.blockBoundingGeometry(target).translated(editor.contentOffset()).top()  # type: ignore[attr-defined]
    return 0 <= top < view.height() / 3


def _codes(kb: Kb) -> list:
    rows = kb.session.diagnostics.all()  # type: ignore[attr-defined]
    return [row.code for row in rows]


def test_k26_call_your_code(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard, path = _session(tmp_path, qapp)
    original_form = kb.text()
    window_file = path.parent / "sale_window.py"
    original_py = window_file.read_bytes()
    try:
        kb.press("Key_R", "Control")
        kb.type("printButton")
        kb.press("Key_Return")
        kb.check(kb.selected() == ("printButton",), "selected printButton, have %s" % (kb.selected(),))
        kb.press("Key_F10", "Shift")
        popup = QApplication.activePopupWidget()
        kb.check(isinstance(popup, QMenu), "Shift+F10 opened the menu, focus %s" % kb.focus_name())
        assert isinstance(popup, QMenu)
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
        kb.check(kb.focus_name() == "formBuilder.eventPickerMethod", "method page open, focus %s" % kb.focus_name())
        field = kb.focus()
        kb.check(field is not None and field.text() == "print_receipt", "suggested name")  # type: ignore[union-attr]
        kb.check("Adds print_receipt()" in _named(window, "formBuilder.eventPickerNotice").text(), "Adds line")
        kb.press("Key_Return")
        kb.pump(8)
        editor = _editor(qapp)
        kb.check(editor.textCursor().selectedText() == "pass", "pass is selected, have %r" % editor.textCursor().selectedText())
        raw = window_file.read_bytes()
        kb.check(b"def print_receipt" in raw, "stub is on disk")
        kb.check(b"\r\n" in raw, "CRLF kept")
        kb.check(b"Notes for the next person" in raw, "trailing comment stays")
        tab = window._editor_manager.get_tab(str(window_file))  # noqa: SLF001
        kb.check(tab is not None and tab.is_dirty is False, "the code tab is saved")

        _back_to_form(kb)
        tabs = window._editor_tabs_widget  # noqa: SLF001
        current = tabs.currentWidget() if tabs is not None else None
        content = current.content() if current is not None and hasattr(current, "content") else None
        kb.check(content is not None and content.objectName() == "formBuilder.surface", "form tab is current")
        kb.press("Key_Z", "Control")
        kb.pump()
        kb.check(window_file.read_bytes() == original_py, "Ctrl+Z restored the window file")
        kb.check("print_receipt" not in kb.text(), "Ctrl+Z removed the step")
        kb.press("Key_Z", "Control", "Shift")
        kb.pump()
        kb.check(b"def print_receipt" in window_file.read_bytes(), "Ctrl+Shift+Z restored the stub")
        kb.check("print_receipt" in kb.text(), "Ctrl+Shift+Z restored the step")

        kb.press("Key_F12")
        kb.pump(8)
        editor = _editor(qapp)
        kb.check(editor.textCursor().selectedText() == "pass", "F12 selects pass")
        kb.check(_def_in_top_third(editor, "def print_receipt"), "the def line is in the top third: %s" % _def_place(editor, "def print_receipt"))
        kb.type("self.close()")
        kb.press("Key_S", "Control")
        kb.pump(8)
        kb.check(b"self.close()" in window_file.read_bytes(), "the edited body is saved")
        _back_to_form(kb)
        kb.press("Key_Z", "Control")
        kb.pump()
        sentence = str(getattr(kb.surface, "_gesture_sentence", ""))
        kb.check(_KEPT in sentence, "toast sentence, saw %r" % sentence)
        kb.check("print_receipt" not in kb.text(), "the step is gone")
        kb.check(b"self.close()" in window_file.read_bytes(), "the method stays")
        kb.press("Key_Z", "Control", "Shift")
        kb.pump()
        kb.check("print_receipt" in kb.text(), "redo restores the step")

        kb.press("Key_F12")
        kb.pump(8)
        editor = _editor(qapp)
        kb.press("Key_Up")
        kb.press("Key_Up")
        kb.press("Key_Home")
        kb.press("Key_End", "Shift")
        kb.type("    def print_reciept(self):")
        kb.press("Key_S", "Control")
        kb.pump(8)
        kb.check("FB201" in _codes(kb), "FB201 after the rename, saw %s\n%s" % (_codes(kb), window_file.read_text(encoding="utf-8")[-400:]))
        _back_to_form(kb)
        kb.press("Key_B", "Alt")
        kb.pump()
        for _ in range(8):
            if "print_receipt" in (getattr(kb.focus(), "method_name", "") or ""):
                break
            kb.press("Key_Down")
        kb.press("Key_Period", "Control")
        kb.pump(8)
        kb.check("print_reciept" in kb.text(), "Ctrl+. uses print_reciept, form is %s" % kb.text()[-200:])
        kb.check("FB201" not in _codes(kb), "FB201 is gone, saw %s" % _codes(kb))

        kb.press("Key_F12")
        kb.pump(4)
        kb.press("Key_Down")
        kb.press("Key_End")
        kb.press("Key_Return")
        kb.type("    @Slot()")
        kb.press("Key_Return")
        kb.type("def on_saveButton_clickd(self):")
        kb.press("Key_Return")
        kb.type("pass")
        kb.press("Key_S", "Control")
        kb.pump(8)
        kb.check(
            "FB208" in _codes(kb),
            "FB208 suggests the event, saw %s | %s"
            % (_codes(kb), window_file.read_text(encoding="utf-8")[-400:].replace("\n", " | ")),
        )

        _back_to_form(kb)
        kb.press("Key_O", "Alt")
        kb.pump()
        menu = QApplication.activePopupWidget()
        kb.check(isinstance(menu, QMenu), "Alt+O opened Form, focus %s" % kb.focus_name())
        assert isinstance(menu, QMenu)
        for _ in range(24):
            current = menu.activeAction()
            if current is not None and current.text().startswith("Form settings"):
                break
            kb.press("Key_Down")
            menu = QApplication.activePopupWidget()
            if not isinstance(menu, QMenu):
                break
        kb.press("Key_Return")
        kb.pump()
        for _ in range(6):
            if kb.focus_name() == "formBuilder.formSetting.connectslotsbyname.check":
                break
            kb.press("Key_Backtab")
        kb.check(kb.focus_name() == "formBuilder.formSetting.connectslotsbyname.check", "checkbox focused, have %s" % kb.focus_name())
        kb.press("Key_Space")
        kb.pump()
        kb.check('connectslotsbyname="false"' in kb.text(), "connect by name is off")
        kb.check("FB211" in _codes(kb), "FB211 is reported, saw %s" % _codes(kb))

        kb.press("Key_R", "Control", "Shift")
        kb.pump(4)
        from app.features.form_builder.engine.ipc.protocol import Log
        from app.features.form_builder.integration.preview_control import control_for

        control = control_for(kb.surface)
        kb.check(control is not None, "preview control exists")
        assert control is not None
        control._on_child(Log(None, "try", "info", "", 0, kind="would_call", method="print_reciept"))  # noqa: SLF001
        kb.pump()
        status = str(getattr(kb.surface, "_gesture_sentence", ""))
        kb.check(status.startswith("Preview:"), "preview status, saw %r" % status)
        kb.check("print_reciept()" in status and "sale_window.py" in status, status)

        steps = 0
        while kb.session.log.can_undo() and steps < 12:  # type: ignore[attr-defined]
            kb.press("Key_Z", "Control")
            kb.pump()
            steps += 1
        kb.check(kb.text() == original_form, "undo all restored the form")
        kept = window_file.read_bytes()
        kb.check(b"self.close()" in kept or b"print_reciept" in kept, "the person's edits stay in the window file")
        kb.check(b"on_saveButton_clickd" in kept, "the typed method stays")
    finally:
        kb.done(guard)
        _close(window, qapp, guard)
        if sys.platform == "darwin":
            from app.qt.QtGui import qt_set_sequence_auto_mnemonic

            qt_set_sequence_auto_mnemonic(False)
