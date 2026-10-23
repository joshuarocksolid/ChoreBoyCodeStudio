"""A press on the viewport selects the widget under the pointer."""

from __future__ import annotations

import pytest

from app.qt.QtCore import Qt  # type: ignore[reportAttributeAccessIssue]
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QPushButton, QWidget
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import Node
from app.features.form_builder.integration.canvas import FormCanvas
from tests.form_builder.qtside.support import form, opened

pytestmark = pytest.mark.usefixtures("qapp")

NESTED = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>300</height></rect></property>
  <widget class="QFrame" name="frame">
   <property name="geometry"><rect><x>20</x><y>20</y><width>220</width><height>140</height></rect></property>
   <widget class="QPushButton" name="ok">
    <property name="geometry"><rect><x>30</x><y>40</y><width>80</width><height>28</height></rect></property>
    <property name="text"><string>OK</string></property>
   </widget>
  </widget>
""",
)


class _Host:
    def canvas_pressed(self) -> None:
        return None

    def narrate(self, sentence: str) -> None:
        return None

    def hover_changed(self, node: object) -> None:
        return None

    def zoom_changed(self, label: str) -> None:
        return None

    def open_problem(self, node: object) -> None:
        return None

    def open_layout_popover(self, node: object) -> None:
        return None


def test_press_on_the_viewport_selects_the_deepest_widget() -> None:
    with opened(NESTED) as (session, realizer):
        parent = QWidget()
        parent.resize(960, 720)
        canvas = FormCanvas(session, realizer, _Host(), parent)
        canvas.resize(960, 720)
        parent.show()
        app = QApplication.instance()
        assert app is not None
        app.processEvents()
        root = canvas.page_widget()
        assert root is not None
        button = root.findChild(QPushButton, "ok")
        assert button is not None
        assert button.width() > 0
        center = button.rect().center()
        on_root = button.mapTo(root, center)
        proxy = root.graphicsProxyWidget()
        assert proxy is not None
        port = canvas.mapFromScene(proxy.mapToScene(on_root))
        assert canvas.viewport().rect().contains(port)
        buttons = getattr(Qt, "MouseButton", Qt)
        modifiers = getattr(Qt, "KeyboardModifier", Qt)
        QTest.mouseClick(
            canvas.viewport(),
            getattr(buttons, "LeftButton"),
            getattr(modifiers, "NoModifier"),
            port,
        )
        app.processEvents()
        selected = _named(session.document, "ok")
        frame = _named(session.document, "frame")
        assert session.selection.state.current == selected.id
        assert session.selection.state.ids == (selected.id,)
        assert frame.id not in session.selection.state.ids
        canvas.dispose()
        parent.deleteLater()


def _named(document: UiDocument, name: str) -> Node:
    matches = [node for node in document.iter_preorder() if getattr(node, "object_name", None) == name]
    assert len(matches) == 1
    return matches[0]
