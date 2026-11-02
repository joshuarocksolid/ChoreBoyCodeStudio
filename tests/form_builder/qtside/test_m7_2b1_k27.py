# pyright: reportAttributeAccessIssue=false
"""K27: keys only, from Discount rate to a saved Enabled when rule."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.ui4.nodes import WidgetNode  # noqa: E402
from app.features.form_builder.engine.ui4.values import StringValue  # noqa: E402
from app.qt.QtWidgets import QApplication  # noqa: E402
from tests.form_builder.qtside.test_m3_keyboard_scripts import (  # noqa: E402
    Kb,
    _NoMouse,
    _close,
    _open,
    _project,
    _require,
)

pytestmark = [pytest.mark.unit, pytest.mark.timeout(300)]

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="geometry"><rect><x>0</x><y>0</y><width>420</width><height>280</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QCheckBox" name="discountCheck">
     <property name="text"><string>Discount</string></property>
    </widget>
   </item>
   <item>
    <widget class="QLabel" name="rateLabel">
     <property name="text"><string>Discount rate</string></property>
     <property name="buddy"><cstring>discountEdit</cstring></property>
    </widget>
   </item>
   <item>
    <widget class="QLineEdit" name="discountEdit"/>
   </item>
   <item>
    <widget class="QPushButton" name="okButton">
     <property name="text"><string>OK</string></property>
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _session(tmp_path: Path, qapp: QApplication) -> tuple:
    from app.shell.main_window import MainWindow

    _require()
    if sys.platform == "darwin":
        from app.qt.QtGui import qt_set_sequence_auto_mnemonic

        qt_set_sequence_auto_mnemonic(True)
    root = tmp_path / "shop"
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    _project(window, root)
    path = root / "forms" / "discount.ui"
    surface = _open(window, qapp, path, _FORM)
    guard = _NoMouse()
    qapp.installEventFilter(guard)
    kb = Kb(window, qapp, surface, path)
    surface.focus_primary()  # type: ignore[attr-defined]
    kb.pump()
    return window, kb, guard, path


def _logic(kb: Kb, name: str, key: str) -> str:
    session = kb.session
    found = session.document.by_name(name)  # type: ignore[attr-defined]
    node = session.document.node(found[0])  # type: ignore[attr-defined]
    assert isinstance(node, WidgetNode)
    value = node.value(key)
    if isinstance(value, StringValue):
        return value.text
    return ""


def script_k27(kb: Kb) -> None:
    """K27 on an open discount form. Keys only."""
    kb.press("Key_R", "Control")
    kb.type("discountEdit")
    kb.press("Key_Return")
    kb.pump()
    assert kb.selected() == ("discountEdit",), kb.log
    kb.press("Key_B", "Alt")
    kb.pump()
    seen = []
    landed = False
    for _ in range(40):
        focus = QApplication.focusWidget()
        name = focus.objectName() if focus is not None else ""
        seen.append(name)
        if name == "formBuilder.state.row.cbcsEnabledWhen":
            landed = True
            break
        kb.press("Key_Tab", "Shift")
    assert landed, seen
    kb.press("Key_Return")
    kb.type("disc")
    kb.press("Key_Tab")
    kb.press("Key_Return", "Control")
    kb.pump()
    assert kb.session.log.undo_label() == "Set Enabled when for Discount rate"  # type: ignore[attr-defined]
    assert _logic(kb, "discountEdit", "cbcsEnabledWhen") == "discountCheck"


def test_k27_discount_rate_enabled_when(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard, _path = _session(tmp_path, qapp)
    try:
        script_k27(kb)
        assert guard.seen == []
    finally:
        _close(window, qapp, guard)
