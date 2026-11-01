# pyright: reportAttributeAccessIssue=false
"""K30: keys only. Walkthrough 1 stays in the condition builder. Walkthrough 2 stays in the value builder."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtWidgets import QApplication, QWidget  # noqa: E402
from tests.form_builder.qtside.test_m7_2b1_k27 import _logic, _session  # noqa: E402
from tests.form_builder.qtside.test_m3_keyboard_scripts import (  # noqa: E402
    Kb,
    _close,
    _open,
    _project,
    _require,
)

pytestmark = [pytest.mark.unit, pytest.mark.timeout(300)]

_INVOICE = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="geometry"><rect><x>0</x><y>0</y><width>420</width><height>280</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QLabel" name="qtyLabel">
     <property name="text"><string>Qty</string></property>
     <property name="buddy"><cstring>qtySpin</cstring></property>
    </widget>
   </item>
   <item>
    <widget class="QSpinBox" name="qtySpin"/>
   </item>
   <item>
    <widget class="QLabel" name="priceLabel">
     <property name="text"><string>Price</string></property>
     <property name="buddy"><cstring>priceSpin</cstring></property>
    </widget>
   </item>
   <item>
    <widget class="QDoubleSpinBox" name="priceSpin">
     <property name="decimals"><number>2</number></property>
    </widget>
   </item>
   <item>
    <widget class="QLabel" name="lineTotalLabel">
     <property name="text"><string>Line total</string></property>
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _invoice(tmp_path: Path, qapp: QApplication) -> tuple:
    import sys

    from app.shell.main_window import MainWindow

    _require()
    if sys.platform == "darwin":
        from app.qt.QtGui import qt_set_sequence_auto_mnemonic

        qt_set_sequence_auto_mnemonic(True)
    root = tmp_path / "shop"
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    _project(window, root)
    path = root / "forms" / "invoice.ui"
    surface = _open(window, qapp, path, _INVOICE)
    from tests.form_builder.qtside.test_m3_keyboard_scripts import _NoMouse

    guard = _NoMouse()
    qapp.installEventFilter(guard)
    kb = Kb(window, qapp, surface, path)
    surface.focus_primary()  # type: ignore[attr-defined]
    kb.pump()
    return window, kb, guard


def _focus_name() -> str:
    focus = QApplication.focusWidget()
    if focus is None:
        return ""
    name = focus.objectName()
    if name:
        return name
    parent = focus.parentWidget()
    return parent.objectName() if parent is not None else ""


def _run(kb: Kb, steps: List[str], keys: List[int], name: str, action: Callable[[], None]) -> None:
    before = len(kb.log)
    action()
    steps.append(name)
    keys.append(len(kb.log) - before)


def _select(kb: Kb, object_name: str) -> None:
    kb.press("Key_R", "Control")
    kb.type(object_name)
    kb.press("Key_Return")
    kb.pump()
    assert kb.selected() == (object_name,), kb.log


def _open_row(kb: Kb, row_name: str) -> None:
    kb.press("Key_B", "Alt")
    kb.pump()
    seen = []
    for _ in range(40):
        name = _focus_name()
        seen.append(name)
        if name == row_name:
            kb.press("Key_Return")
            kb.pump()
            return
        kb.press("Key_Tab", "Shift")
    raise AssertionError(seen)


def _tab_until(kb: Kb, names: set, limit: int = 8) -> None:
    seen = []
    for _ in range(limit):
        name = _focus_name()
        seen.append(name)
        if name in names:
            return
        kb.press("Key_Tab")
    raise AssertionError(seen)


def _combo_data(root: QWidget, name: str) -> object:
    box = root.findChild(QWidget, name)
    assert box is not None, name
    return box.currentData()  # type: ignore[attr-defined]


def script_k30_condition(kb: Kb) -> None:
    """K30 walkthrough 1 on an open discount form. Keys only."""
    steps: List[str] = []
    keys: List[int] = []
    _run(kb, steps, keys, "select Discount rate", lambda: _select(kb, "discountEdit"))
    _run(kb, steps, keys, "open Enabled when", lambda: _open_row(kb, "formBuilder.state.row.cbcsEnabledWhen"))
    assert not kb.window.findChild(QWidget, "formBuilder.formula").isVisible()  # type: ignore[union-attr]

    def pick() -> None:
        kb.type("disc")
        kb.press("Key_Tab")
        kb.pump()

    _run(kb, steps, keys, "pick Discount", pick)
    pane = kb.window
    assert _combo_data(pane, "formBuilder.builder.cond.row.0.cmp") == "checked"
    _run(kb, steps, keys, "commit", lambda: kb.press("Key_Return", "Control"))
    assert kb.session.log.undo_label() == "Set Enabled when for Discount rate"  # type: ignore[attr-defined]
    assert _logic(kb, "discountEdit", "cbcsEnabledWhen") == "discountCheck"
    assert len(steps) <= 12, steps
    print("K30 walkthrough 1 steps=%d keys=%d %s" % (len(steps), sum(keys), steps))


def test_k30_walkthrough_1_condition_builder(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard, _path = _session(tmp_path, qapp)
    try:
        script_k30_condition(kb)
        assert guard.seen == []
    finally:
        _close(window, qapp, guard)


def script_k30_value(kb: Kb) -> None:
    """K30 walkthrough 2 on an open invoice form. Keys only."""
    steps: List[str] = []
    keys: List[int] = []
    _run(kb, steps, keys, "select Line total", lambda: _select(kb, "lineTotalLabel"))
    _run(kb, steps, keys, "open Value", lambda: _open_row(kb, "formBuilder.state.row.cbcsValue"))
    editor = kb.window.findChild(QWidget, "formBuilder.formula")
    assert editor is not None and not editor.isVisible()

    def shape() -> None:
        kb.press("Key_Down")
        kb.pump()

    _run(kb, steps, keys, "choose field op field", shape)
    assert _combo_data(kb.window, "formBuilder.builder.shape") == "arith"

    def qty() -> None:
        _tab_until(kb, {"formBuilder.builder.term.0.field"})
        kb.type("qty")
        kb.press("Key_Tab")
        kb.pump()

    _run(kb, steps, keys, "pick Qty", qty)

    def operator() -> None:
        _tab_until(kb, {"formBuilder.builder.op.1"})
        kb.press("Key_Down")
        kb.press("Key_Down")
        kb.pump()

    _run(kb, steps, keys, "pick ×", operator)
    assert _combo_data(kb.window, "formBuilder.builder.op.1") == "*"

    def price() -> None:
        _tab_until(kb, {"formBuilder.builder.term.1.field"})
        kb.type("price")
        kb.press("Key_Tab")
        kb.pump()

    _run(kb, steps, keys, "pick Price", price)
    _run(kb, steps, keys, "commit", lambda: kb.press("Key_Return", "Control"))
    assert _logic(kb, "lineTotalLabel", "cbcsValue") == "qtySpin * priceSpin", kb.log[-8:]
    assert kb.session.log.undo_label() == "Set Value for Line total"  # type: ignore[attr-defined]
    depth = len(kb.session.log.entries())  # type: ignore[attr-defined]
    assert kb.session.log.undo()  # type: ignore[attr-defined]
    assert _logic(kb, "lineTotalLabel", "cbcsValue") == ""
    assert len(kb.session.log.entries()) == depth - 1  # type: ignore[attr-defined]
    assert len(steps) <= 12, steps
    print("K30 walkthrough 2 steps=%d keys=%d %s" % (len(steps), sum(keys), steps))


def test_k30_walkthrough_2_value_builder(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _invoice(tmp_path, qapp)
    try:
        script_k30_value(kb)
        assert guard.seen == []
    finally:
        _close(window, qapp, guard)
