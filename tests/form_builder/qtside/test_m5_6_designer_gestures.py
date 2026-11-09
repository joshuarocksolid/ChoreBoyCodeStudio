# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false
"""Designer gestures that Code Studio keeps as they were: R3 218 (Ctrl-drag clone), 219 (nudge), 221 (drag inside a layout).

UX-MODE-006 maps each to the Code Studio gesture; these run it on a real canvas.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.ui4.nodes import WidgetNode  # noqa: E402
from app.features.form_builder.engine.ui4.values import RectValue  # noqa: E402
from app.qt.QtCore import QPoint, Qt  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtWidgets import QApplication  # noqa: E402
from tests.form_builder.qtside.test_m3_keyboard_scripts import Kb, _close, _session, _walk_to  # noqa: E402

pytestmark = [pytest.mark.unit, pytest.mark.timeout(300)]

FREE = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Free</class>
 <widget class="QWidget" name="Free">
  <property name="geometry"><rect><x>0</x><y>0</y><width>420</width><height>260</height></rect></property>
  <widget class="QPushButton" name="goButton">
   <property name="geometry"><rect><x>40</x><y>40</y><width>90</width><height>28</height></rect></property>
   <property name="text"><string>Go</string></property>
  </widget>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

STACK = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Stack</class>
 <widget class="QWidget" name="Stack">
  <property name="geometry"><rect><x>0</x><y>0</y><width>300</width><height>260</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QPushButton" name="aButton"><property name="text"><string>A</string></property></widget></item>
   <item><widget class="QPushButton" name="bButton"><property name="text"><string>B</string></property></widget></item>
   <item><widget class="QPushButton" name="cButton"><property name="text"><string>C</string></property></widget></item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _geometry(kb: Kb, name: str) -> RectValue:
    node = kb.session.document.node(kb.session.document.by_name(name)[0])
    entry = node.prop("geometry")
    assert entry is not None and isinstance(entry.value, RectValue)
    return entry.value


def _center(kb: Kb, name: str) -> QPoint:
    rect = kb.surface.workbench.canvas.viewport_rect((kb.session.document.by_name(name)[0],))
    assert rect is not None
    return rect.center()


def _drag(kb: Kb, start: QPoint, end: QPoint, mods: Any = Qt.KeyboardModifier.NoModifier) -> None:
    viewport = kb.surface.workbench.canvas.viewport()
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, mods, start)
    for step in range(1, 5):
        QTest.mouseMove(viewport, QPoint(start.x() + (end.x() - start.x()) * step // 4, start.y() + (end.y() - start.y()) * step // 4))
        kb.pump(2)
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, mods, end)
    kb.pump()


def _names(kb: Kb) -> list:
    return [node.object_name for node in kb.session.document.iter_preorder() if isinstance(node, WidgetNode) and node.object_name]


@pytest.mark.parity("R3-219")
def test_alt_arrow_nudges_by_the_grid_step_and_alt_shift_arrow_by_one_pixel(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _session(tmp_path, qapp, FREE)
    try:
        kb.surface.workbench.canvas.setFocus()
        kb.pump()
        _walk_to(kb, "goButton", limit=6)
        start = _geometry(kb, "goButton")
        kb.press("Key_Right", "Alt")
        moved = _geometry(kb, "goButton")
        assert (moved.x - start.x, moved.y - start.y) == (8, 0)
        kb.press("Key_Down", "Alt", "Shift")
        assert (_geometry(kb, "goButton").y - start.y) == 1
        kb.press("Key_Right")
        assert _geometry(kb, "goButton").x == moved.x, "a plain arrow selects; it does not move"
    finally:
        _close(window, qapp, guard)


@pytest.mark.parity("R3-218")
def test_ctrl_drag_clones_the_widget(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _session(tmp_path, qapp, FREE)
    try:
        before = _names(kb)
        start = _center(kb, "goButton")
        _drag(kb, start, QPoint(start.x() + 140, start.y() + 60), Qt.KeyboardModifier.ControlModifier)
        after = _names(kb)
        assert len(after) == len(before) + 1, (before, after)
        assert kb.session.log.undo_label() == "Duplicate"
        kb.session.log.undo()
        assert _names(kb) == before
    finally:
        _close(window, qapp, guard)


@pytest.mark.parity("R3-221")
def test_a_plain_drag_moves_a_widget_inside_its_layout(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _session(tmp_path, qapp, STACK)
    try:
        def order() -> list:
            layout = kb.session.document.root.layout
            return [item.content.object_name for item in layout.items]

        assert order() == ["aButton", "bButton", "cButton"]
        start = _center(kb, "aButton")
        end = QPoint(start.x(), _center(kb, "cButton").y() + 12)
        _drag(kb, start, end)
        assert order() != ["aButton", "bButton", "cButton"], "the drag moved the button inside the layout"
        assert sorted(order()) == ["aButton", "bButton", "cButton"]
        assert len(kb.session.document.root.layout.items) == 3
    finally:
        _close(window, qapp, guard)
