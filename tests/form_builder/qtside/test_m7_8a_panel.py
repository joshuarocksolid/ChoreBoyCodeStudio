# pyright: reportAttributeAccessIssue=false
"""Filter the Logic panel and open a rule, a check and a step from the keyboard."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Tuple

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtWidgets import QApplication, QWidget  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402
from tests.form_builder.engine.logic.test_m7_8a_uses import invoice_text, window_source  # noqa: E402
from tests.form_builder.qtside.test_m3_keyboard_scripts import (  # noqa: E402
    _NoMouse,
    _close,
    _key,
    _open,
    _project,
    _require,
)

pytestmark = [pytest.mark.unit, pytest.mark.timeout(120)]


def open_invoice(tmp_path: Path, qapp: QApplication) -> Tuple[MainWindow, object, _NoMouse]:
    _require()
    if sys.platform == "darwin":
        from app.qt.QtGui import qt_set_sequence_auto_mnemonic

        qt_set_sequence_auto_mnemonic(True)
    root = tmp_path / "shop"
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    _project(window, root)
    path = root / "forms" / "invoice.ui"
    (path.parent / "invoice_window.py").write_text(window_source(), encoding="utf-8")
    surface = _open(window, qapp, path, invoice_text())
    guard = _NoMouse()
    qapp.installEventFilter(guard)
    surface.focus_primary()  # type: ignore[attr-defined]
    _pump(qapp)
    return window, surface, guard


def _pump(qapp: QApplication, times: int = 8) -> None:
    for _ in range(times):
        qapp.processEvents()


def _rows(panel: QWidget) -> list:
    return [
        child
        for child in panel.findChildren(QWidget)
        if child.objectName().startswith("formBuilder.logic.row.")
    ]


def _selected(surface: object) -> str:
    session = surface.session  # type: ignore[attr-defined]
    ids = session.selection.state.ids
    if len(ids) != 1:
        return ""
    node = session.document.get(ids[0])
    return str(getattr(node, "object_name", "") or "")


def _row_named(panel: QWidget, section: str, widget: str) -> QWidget:
    prefix = "%s, %s," % (section, widget)
    for row in _rows(panel):
        if str(row.accessibleName()).startswith(prefix):
            return row
    raise AssertionError(prefix)


def test_filter_and_enter_open_the_behavior_row(tmp_path: Path, qapp: QApplication) -> None:
    window, surface, guard = open_invoice(tmp_path, qapp)
    try:
        panel = surface.findChild(QWidget, "formBuilder.logic")  # type: ignore[attr-defined]
        assert panel is not None
        field = panel.findChild(QWidget, "formBuilder.logic.filter")
        assert field is not None
        field.setFocus()
        QTest.keyClicks(field, "disc")
        _pump(qapp)
        visible = _rows(panel)
        assert any("discountCheck" in str(row.toolTip()) for row in visible)
        assert any(str(row.accessibleName()).startswith("STATE,") for row in visible)
        assert visible
        assert all("disc" in str(row.toolTip()).casefold() for row in visible)
        rules = panel.findChild(QWidget, "formBuilder.logic.chip.rules")
        assert rules is not None
        rules.setChecked(False)  # type: ignore[attr-defined]
        _pump(qapp)
        assert not any(str(row.accessibleName()).startswith("STATE,") for row in _rows(panel))
        rules.setChecked(True)  # type: ignore[attr-defined]
        _pump(qapp)
        state = _row_named(panel, "STATE", "discountEdit")
        state.setFocus()
        QTest.keyClick(state, _key("Key_Return"))
        _pump(qapp)
        assert _selected(surface) == "discountEdit"
        editor = surface.findChild(QWidget, "formBuilder.formula")  # type: ignore[attr-defined]
        builder = surface.findChild(QWidget, "formBuilder.builder")  # type: ignore[attr-defined]
        # E2: a row whose formula fits the builder opens there; the formula text is the same.
        assert editor is not None
        assert editor.isVisible() or (builder is not None and builder.isVisible())
        assert editor.toPlainText() == "discountCheck"  # type: ignore[attr-defined]
        field.setText("")  # type: ignore[attr-defined]
        _pump(qapp)
        check = _row_named(panel, "CHECKS", "emailEdit")
        check.setFocus()
        QTest.keyClick(check, _key("Key_Return"))
        _pump(qapp)
        assert _selected(surface) == "emailEdit"
        focused = QApplication.focusWidget()
        assert getattr(focused, "index", None) == 0
        step = _row_named(panel, "EVENTS", "saveButton")
        step.setFocus()
        QTest.keyClick(step, _key("Key_Return"))
        _pump(qapp)
        assert _selected(surface) == "saveButton"
        focused = QApplication.focusWidget()
        assert getattr(focused, "signal_name", None) == "clicked"
        assert getattr(focused, "step_index", None) == 0
        assert surface.findChild(QWidget, "formBuilder.events.form") is not None  # type: ignore[attr-defined]
        assert guard.seen == []
    finally:
        _close(window, qapp, guard)
