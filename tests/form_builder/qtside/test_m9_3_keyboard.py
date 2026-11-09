# pyright: reportAttributeAccessIssue=false
"""Keyboard paths M9.3 adds on top of K1–K34.

Each script sends key clicks only. A mouse press fails the script.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtCore import QTimer  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtWidgets import QApplication, QWidget  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402
from tests.form_builder.qtside.test_m3_keyboard_scripts import (  # noqa: E402
    Kb,
    _NoMouse,
    _close,
    _key,
    _mods,
    _project,
    _require,
)
from tests.form_builder.qtside.test_m7_8a_panel import _pump, open_invoice  # noqa: E402

pytestmark = [pytest.mark.unit, pytest.mark.timeout(180)]


def _selected(surface: object) -> str:
    session = surface.session  # type: ignore[attr-defined]
    ids = session.selection.state.ids
    if len(ids) != 1:
        return ""
    node = session.document.get(ids[0])
    return str(getattr(node, "object_name", "") or "")


@pytest.mark.logic("L-logic-keyboard")
def test_logic_filter_down_opens_the_row(tmp_path: Path, qapp: QApplication) -> None:
    window, surface, guard = open_invoice(tmp_path, qapp)
    try:
        focus = QApplication.focusWidget() or window
        QTest.keyClick(focus, _key("Key_L"), _mods("Alt"))  # type: ignore[arg-type]
        _pump(qapp)
        field = QApplication.focusWidget()
        assert field is not None
        assert field.objectName() == "formBuilder.logic.filter"
        QTest.keyClicks(field, "disc")
        _pump(qapp)
        QTest.keyClick(field, _key("Key_Down"))  # type: ignore[arg-type]
        _pump(qapp)
        row = QApplication.focusWidget()
        assert row is not None
        assert row.objectName().startswith("formBuilder.logic.row.")
        assert "discount" in row.accessibleName().casefold()
        QTest.keyClick(row, _key("Key_Return"))  # type: ignore[arg-type]
        _pump(qapp)
        assert _selected(surface) == "discountEdit"
        editor = surface.findChild(QWidget, "formBuilder.formula")  # type: ignore[attr-defined]
        builder = surface.findChild(QWidget, "formBuilder.builder")  # type: ignore[attr-defined]
        assert editor is not None
        assert editor.toPlainText() == "discountCheck"  # type: ignore[attr-defined]
        assert editor.isVisible() or (builder is not None and builder.isVisible())
        focused = QApplication.focusWidget()
        assert focused is not None
        assert guard.seen == []
    finally:
        _close(window, qapp, guard)


def test_ctrl_shift_d_lands_on_connect(tmp_path: Path, qapp: QApplication) -> None:
    window, _surface, guard = open_invoice(tmp_path, qapp)
    try:
        focus = QApplication.focusWidget() or window
        QTest.keyClick(focus, _key("Key_D"), _mods("Control", "Shift"))  # type: ignore[arg-type]
        _pump(qapp)
        landed = QApplication.focusWidget()
        assert landed is not None
        assert landed.objectName() == "formBuilder.data.connect"
        assert guard.seen == []
    finally:
        _close(window, qapp, guard)


def test_start_screen_from_table_escape_returns_to_the_card(
    tmp_path: Path, qapp: QApplication
) -> None:
    _require()
    root = tmp_path / "shop"
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    _project(window, root)
    window.resize(1400, 900)
    window.show()
    guard = _NoMouse()
    qapp.installEventFilter(guard)
    kb = Kb(window, qapp, None, root / "forms" / "invoice.ui")
    seen: dict = {}
    try:
        kb.pump()
        window._center_stack.setCurrentIndex(1)  # type: ignore[union-attr]  # noqa: SLF001
        kb.pump()
        if sys.platform == "darwin":
            action = window.menu_registry.action("shell.action.file.newForm")  # type: ignore[attr-defined]
            assert action is not None and action.isEnabled()
            action.trigger()
            kb.pump()
        else:
            kb.press("Key_F", "Alt")
            for _ in range(12):
                menu = QApplication.activePopupWidget()
                active = menu.activeAction() if menu is not None else None  # type: ignore[union-attr]
                if active is not None and active.text() == "New Form…":
                    break
                kb.press("Key_Down")
            kb.press("Key_Return")
        panel = window.findChild(QWidget, "formBuilder.newForm")
        assert panel is not None

        def on_card() -> bool:
            focus = kb.focus()
            name = "" if focus is None else focus.objectName()
            return name.startswith("formBuilder.newForm.card.")

        for _ in range(8):
            if on_card():
                break
            kb.press("Key_Tab")
        assert on_card(), kb.focus_name()

        def on_from_table() -> bool:
            focus = kb.focus()
            return focus is not None and focus.accessibleName() == "Build a form from a table"

        for key in ("Key_Down", "Key_Up"):
            if on_from_table():
                break
            for _ in range(6):
                kb.press(key, "Control")
                if on_from_table():
                    break
        assert on_from_table(), kb.focus().accessibleName() if kb.focus() else kb.focus_name()  # type: ignore[union-attr]

        def _escape_when_open() -> None:
            dialog = window.findChild(QWidget, "formBuilder.fromTable")
            if dialog is None or not dialog.isVisible():
                QTimer.singleShot(50, _escape_when_open)
                return
            focus = QApplication.focusWidget()
            seen["focus"] = "" if focus is None else focus.objectName()
            # Escape goes to the widget that has focus, as a person's key would.
            # A busy suite can show the dialog before it takes focus; try again then.
            target = focus if focus is not None and dialog.isAncestorOf(focus) else dialog
            QTest.keyClick(target, _key("Key_Escape"))  # type: ignore[arg-type]
            seen["tries"] = seen.get("tries", 0) + 1
            if dialog.isVisible() and seen["tries"] < 40:
                QTimer.singleShot(50, _escape_when_open)
                return
            seen["closed"] = not dialog.isVisible()
            if dialog.isVisible():
                dialog.reject()

        QTimer.singleShot(50, _escape_when_open)
        kb.press("Key_Return")

        def _settled() -> bool:
            focus = QApplication.focusWidget()
            return "closed" in seen and focus is not None and focus.objectName() == "formBuilder.newForm.card.from_table"

        for _ in range(200):
            if _settled():
                break
            QTest.qWait(25)
            kb.pump()
        assert seen.get("closed") is True, seen
        dialog = window.findChild(QWidget, "formBuilder.fromTable")
        assert dialog is None or not dialog.isVisible()
        focus = QApplication.focusWidget()
        assert focus is not None, seen
        assert focus.objectName() == "formBuilder.newForm.card.from_table", (focus.objectName(), seen)
        assert not (root / "forms" / "invoice.ui").exists()
        assert guard.seen == []
    finally:
        _close(window, qapp, guard)
