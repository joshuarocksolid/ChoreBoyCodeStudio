# pyright: reportAttributeAccessIssue=false
"""Alt+L focuses the Logic filter. Shift+F12 opens Uses of the selected widget."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.query.selection import SelectionSource  # noqa: E402
from app.features.form_builder.integration import keys_ext  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtWidgets import QApplication, QWidget  # noqa: E402
from app.shell.shortcut_preferences import SHORTCUT_COMMANDS  # noqa: E402
from tests.form_builder.qtside.test_m3_keyboard_scripts import _close, _key, _mods  # noqa: E402
from tests.form_builder.qtside.test_m7_8a_panel import _pump, open_invoice  # noqa: E402

pytestmark = [pytest.mark.unit, pytest.mark.timeout(120)]


def test_logic_keys_do_not_collide() -> None:
    shell = {command.action_id: command.default_shortcut for command in SHORTCUT_COMMANDS}
    assert keys_ext.collisions(shell) == ()
    rows = {row.command_id: row for row in keys_ext.extra_commands()}
    uses = rows["form.action.logicUses"]
    assert uses.label == "Uses of this name"
    assert uses.shortcut == "Shift+F12"
    assert uses.contexts == ("form_tab",)
    assert uses.shell_action_id == "shell.action.edit.findReferences"
    opened = rows["form.action.openLogicRow"]
    assert opened.shortcut == "Enter" and opened.contexts == ("logic_list",) and opened.kind == "qt"


def test_alt_l_focuses_the_filter_and_shift_f12_opens_uses(tmp_path: Path, qapp: QApplication) -> None:
    window, surface, guard = open_invoice(tmp_path, qapp)
    try:
        node = surface.session.document.by_name("discountEdit")[0]  # type: ignore[attr-defined]
        surface.session.selection.set((node,), current=node, source=SelectionSource.PROGRAM)  # type: ignore[attr-defined]
        focus = QApplication.focusWidget()
        target = focus if focus is not None else window
        QTest.keyClick(target, _key("Key_L"), _mods("Alt"))  # type: ignore[arg-type]
        _pump(qapp)
        focused = QApplication.focusWidget()
        assert focused is not None
        assert focused.objectName() == "formBuilder.logic.filter"
        QTest.keyClick(focused, _key("Key_F12"), _mods("Shift"))  # type: ignore[arg-type]
        _pump(qapp)
        dialog = window.findChild(QWidget, "formBuilder.logic.uses")
        assert dialog is not None
        assert dialog.isVisible()
        assert "Discount rate" in dialog.windowTitle()
        assert guard.seen == []
    finally:
        _close(window, qapp, guard)
