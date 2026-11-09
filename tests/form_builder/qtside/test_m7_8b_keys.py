# pyright: reportAttributeAccessIssue=false
"""Ctrl+Shift+F filters the open form. A code tab still opens project Find."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.query.selection import SelectionSource  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtWidgets import QApplication  # noqa: E402
from tests.form_builder.qtside.test_m3_keyboard_scripts import _close, _key, _mods  # noqa: E402
from tests.form_builder.qtside.test_m7_8a_panel import _pump, open_invoice  # noqa: E402

pytestmark = [pytest.mark.unit, pytest.mark.timeout(180)]


def test_form_tab_focuses_the_logic_filter(tmp_path: Path, qapp: QApplication) -> None:
    window, surface, guard = open_invoice(tmp_path, qapp)
    try:
        node = surface.session.document.by_name("discountEdit")[0]
        surface.session.selection.set((node,), current=node, source=SelectionSource.PROGRAM)
        focus = QApplication.focusWidget()
        target = focus if focus is not None else window
        QTest.keyClick(target, _key("Key_F"), _mods("Control", "Shift"))  # type: ignore[arg-type]
        _pump(qapp)
        focused = QApplication.focusWidget()
        assert focused is not None
        assert focused.objectName() == "formBuilder.logic.filter"
        assert focused.text() == "discountEdit"  # type: ignore[attr-defined]
        bar = window._activity_bar
        assert bar is not None
        assert bar.active_view() != "search"
        assert guard.seen == []
    finally:
        _close(window, qapp, guard)


def test_code_tab_opens_project_find(tmp_path: Path, qapp: QApplication) -> None:
    window, _surface, guard = open_invoice(tmp_path, qapp)
    try:
        code = tmp_path / "shop" / "main.py"
        assert window._editor_tab_factory.open_file_in_editor(str(code))
        _pump(qapp)
        focus = QApplication.focusWidget()
        target = focus if focus is not None else window
        QTest.keyClick(target, _key("Key_F"), _mods("Control", "Shift"))  # type: ignore[arg-type]
        _pump(qapp)
        bar = window._activity_bar
        assert bar is not None
        assert bar.active_view() == "search"
        assert guard.seen == []
    finally:
        _close(window, qapp, guard)
