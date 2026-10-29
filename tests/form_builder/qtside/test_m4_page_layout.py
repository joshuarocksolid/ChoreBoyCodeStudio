# pyright: reportAttributeAccessIssue=false
"""Ctrl+1 … Ctrl+6 lay out a page, a scroll area's content and a dock's content (R3-132)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.ui4.nodes import LayoutNode, WidgetNode
from app.qt.QtCore import Qt
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QWidget
from tests.form_builder.qtside.support import form
from tests.unit.features.form_builder.test_workbench import _open

pytestmark = pytest.mark.usefixtures("qapp")

_UI = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>640</width><height>480</height></rect></property>
  <widget class="QTabWidget" name="tabs">
   <property name="geometry"><rect><x>8</x><y>8</y><width>280</width><height>180</height></rect></property>
   <widget class="QWidget" name="page">
    <attribute name="title"><string>One</string></attribute>
    <widget class="QPushButton" name="onPage"><property name="text"><string>Go</string></property></widget>
   </widget>
  </widget>
  <widget class="QScrollArea" name="scroll">
   <property name="geometry"><rect><x>300</x><y>8</y><width>200</width><height>160</height></rect></property>
   <widget class="QWidget" name="scrollAreaWidgetContents">
    <widget class="QPushButton" name="inScroll"><property name="text"><string>Go</string></property></widget>
   </widget>
  </widget>
  <widget class="QDockWidget" name="dock">
   <property name="geometry"><rect><x>8</x><y>200</y><width>220</width><height>140</height></rect></property>
   <widget class="QWidget" name="dockWidgetContents">
    <widget class="QPushButton" name="inDock"><property name="text"><string>Go</string></property></widget>
   </widget>
  </widget>
""",
)

# The key, the layout class it writes, and a splitter's orientation when it is one.
_KEYS = (
    (Qt.Key.Key_1, "QHBoxLayout", ""),
    (Qt.Key.Key_2, "QVBoxLayout", ""),
    (Qt.Key.Key_3, "QSplitter", "Horizontal"),
    (Qt.Key.Key_4, "QSplitter", "Vertical"),
    (Qt.Key.Key_5, "QGridLayout", ""),
    (Qt.Key.Key_6, "QFormLayout", ""),
)


@pytest.mark.parity("R3-132")
@pytest.mark.parametrize("target", ["page", "scrollAreaWidgetContents", "dockWidgetContents"])
def test_ctrl_1_through_6_lay_out_a_page_scroll_content_and_dock_content(tmp_path: Path, target: str) -> None:
    """UX-CONT-016: Ctrl+1 to Ctrl+6 on a page."""
    parent = QWidget()
    parent.resize(900, 640)
    surface = _open(parent, _UI, tmp_path / "pages.ui")
    surface.resize(900, 640)
    parent.show()
    surface.show()
    _flush()
    try:
        canvas = surface.findChild(QWidget, "formBuilder.canvas")
        assert canvas is not None
        canvas.setFocus()
        for key, class_name, orientation in _KEYS:
            node_id = surface._session.document.by_name(target)[0]
            surface._session.selection.set((node_id,), current=node_id, source=SelectionSource.CANVAS)
            _flush()
            QTest.keyClick(canvas, key, Qt.KeyboardModifier.ControlModifier)
            _flush()
            node = surface._session.document.node(node_id)
            assert isinstance(node, WidgetNode)
            if class_name == "QSplitter":
                found = [child for child in node.child_widgets if child.class_name == "QSplitter"]
                assert len(found) == 1, (target, [child.class_name for child in node.child_widgets])
                prop = found[0].prop("orientation")
                assert prop is not None and orientation in str(getattr(prop.value, "text", ""))
            else:
                layout = node.layout
                assert isinstance(layout, LayoutNode), (target, class_name, layout)
                assert layout.class_name == class_name
            surface._session.log.undo()
            _flush()
    finally:
        surface.release()
        parent.deleteLater()
        _flush()


def _flush() -> None:
    app = QApplication.instance()
    assert app is not None
    for _ in range(8):
        app.processEvents()
