# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false, reportArgumentType=false
"""K21 Form settings (UX_SPEC 12.3), keys only after the menu item.

One main-window form tab on a form with a container that has no layout and an
``stdsetdef`` attribute. A filter fails the run on any spontaneous mouse event.
The Alt+Right step is a strict xfail below: the canvas key code is M5.6's.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtWidgets import QAbstractButton, QApplication, QLineEdit, QMenu, QToolButton, QWidget  # noqa: E402
from tests.form_builder.inspector.m5_5b_support import free_form  # noqa: E402
from tests.form_builder.qtside.test_m3_keyboard_scripts import Kb, _close, _NoMouse, _session  # noqa: E402

pytestmark = [pytest.mark.unit, pytest.mark.timeout(300)]

FIXTURE = free_form(' stdsetdef="1"')


def _menu_item(window: QWidget, text: str) -> object:
    menu = window.findChild(QMenu, "formBuilder.menu")
    assert menu is not None
    for action in menu.actions():
        if action.text().split("\t")[0] == text:
            return action
    raise AssertionError("no Form menu item %r" % text)


def _tab_until(kb: Kb, name: str, limit: int = 40) -> None:
    for _ in range(limit):
        if kb.focus_name() == name:
            return
        kb.press("Key_Tab")
    kb.check(False, "Tab reaches %s" % name)


def test_k21_form_settings(tmp_path: Path, qapp: object) -> None:
    window, kb, guard = _session(tmp_path, qapp, FIXTURE)
    try:
        original = kb.text()
        steps = len(kb.session.log.entries())

        def added() -> int:
            return len(kb.session.log.entries()) - steps

        _menu_item(window, "Form settings…").trigger()
        kb.pump()
        kb.check(kb.focus_name() == "formBuilder.formSetting.author.edit", "Code is open and Author has focus")
        kb.type("Shop")
        kb.press("Key_Return")
        kb.check("<author>Shop</author>" in kb.text(), "Author is written")
        kb.check(added() == 1 and kb.session.log.undo_label() == "Change form setting: author", "one step, named for the row")
        _tab_until(kb, "formBuilder.formSetting.layoutdefault.check")
        kb.press("Key_Space")
        kb.check('<layoutdefault spacing="8" margin="8"/>' in kb.text(), "Default gaps on writes 8 and 8")
        kb.check(added() == 2 and kb.session.log.undo_label() == "Change form setting: default gaps", "one step for Default gaps")
        kb.press("Key_Tab")
        kb.check(kb.focus_name() == "formBuilder.formSetting.layoutdefault.gap", "Tab reaches Gap")
        kb.type("6")
        kb.press("Key_Return")
        kb.check('<layoutdefault spacing="6" margin="8"/>' in kb.text(), "Gap 6 is written")
        kb.check(added() == 3, "Gap is one step")
        _tab_until(kb, "formBuilder.group.translation")
        kb.press("Key_Space")
        kb.press("Key_Tab")
        kb.check(kb.focus_name() == "formBuilder.formSetting.idbasedtr.check", "Tab reaches Translate by ID")
        kb.press("Key_Space")
        kb.check('idbasedtr="true"' in kb.text(), "Translate by ID is written")
        kb.check(added() == 4 and kb.session.log.undo_label() == "Change form setting: translate by id", "one step for Translate by ID")
        _tab_until(kb, "formBuilder.group.freePlacement")
        kb.press("Key_Space")
        kb.press("Key_Tab")
        kb.check(kb.focus_name() == "formBuilder.formSetting.grid.show", "Tab reaches Show grid")
        kb.press("Key_Tab")
        kb.check(kb.focus_name() == "formBuilder.formSetting.grid.across", "Tab reaches Step across")
        kb.type("16")
        kb.press("Key_Return")
        kb.check("gridDeltaX" in kb.text() and "<number>16</number>" in kb.text(), "Step across 16 is written")
        kb.check(added() == 5 and kb.session.log.undo_label() == "Change form setting: step across", "one step for Step across")
        # The older file setting: Tab back up to it and remove it with Enter on [Remove].
        for _ in range(40):
            if kb.focus_name() == "formBuilder.formSetting.stdsetdef.remove":
                break
            kb.press("Key_Tab", "Shift")
        kb.check(kb.focus_name() == "formBuilder.formSetting.stdsetdef.remove", "Shift+Tab reaches [Remove]")
        kb.press("Key_Return")
        kb.check("stdsetdef" not in kb.text(), "the older file setting is removed")
        kb.check(added() == 6 and kb.session.log.undo_label() == "Remove older file setting", "one step for Remove")
        for _ in range(added()):
            kb.session.log.undo()
        kb.check(kb.text() == original, "Undo all restores the original bytes")
        kb.done(guard)
    finally:
        _close(window, qapp, guard)
