"""Hover, frames, spacers, and chips on the realized canvas."""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

import pytest

from app.qt.QtCore import QPoint, Qt
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QWidget
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.reader import UiReadError
from app.features.form_builder.integration.canvas import FormCanvas
from app.features.form_builder.qtside.canvas.core.frame import Chip, Spring, Stroke
from app.features.form_builder.qtside.canvas.core.space import CanvasRect
from app.features.form_builder.qtside.realize import Realizer
from tests.form_builder.qtside.support import form, opened

pytestmark = pytest.mark.usefixtures("qapp")

_CORPUS = Path(__file__).resolve().parents[1] / "corpus"
_LOADABLE = ("synthetic", "qt_examples")

BUTTON = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>300</height></rect></property>
  <widget class="QPushButton" name="ok">
   <property name="geometry"><rect><x>40</x><y>40</y><width>80</width><height>28</height></rect></property>
   <property name="text"><string>OK</string></property>
  </widget>
""",
)

SPACER = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>300</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QPushButton" name="ok">
     <property name="text"><string>OK</string></property>
    </widget>
   </item>
   <item>
    <spacer name="verticalSpacer">
     <property name="orientation"><enum>Qt::Vertical</enum></property>
     <property name="sizeHint" stdset="0"><size><width>20</width><height>40</height></size></property>
    </spacer>
   </item>
  </layout>
""",
)

BARE = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>300</height></rect></property>
  <widget class="QFrame" name="box">
   <property name="geometry"><rect><x>30</x><y>30</y><width>240</width><height>160</height></rect></property>
   <widget class="QPushButton" name="ok">
    <property name="geometry"><rect><x>20</x><y>20</y><width>80</width><height>28</height></rect></property>
    <property name="text"><string>OK</string></property>
   </widget>
  </widget>
""",
)


class _Host:
    def __init__(self) -> None:
        self.hovered: List[object] = []

    def canvas_pressed(self) -> None:
        return None

    def narrate(self, sentence: str) -> None:
        return None

    def hover_changed(self, node: object) -> None:
        self.hovered.append(node)

    def zoom_changed(self, label: str) -> None:
        return None

    def open_problem(self, node: object) -> None:
        return None

    def open_layout_popover(self, node: object) -> None:
        return None


def test_hover_names_the_widget_under_the_pointer() -> None:
    host = _Host()
    with opened(BUTTON) as (session, realizer):
        canvas, parent = _canvas(session, realizer, host)
        _move(canvas, "ok")
        assert host.hovered[-1] == _id(session.document, "ok")
        assert any(isinstance(item, Stroke) and item.role == "hover" for item in canvas.overlay().items)
        canvas.dispose()
        parent.deleteLater()


def test_a_selected_widget_has_a_frame() -> None:
    with opened(BUTTON) as (session, realizer):
        canvas, parent = _canvas(session, realizer, _Host())
        _click(canvas, "ok")
        assert session.selection.state.current == _id(session.document, "ok")
        assert any(isinstance(item, Stroke) and item.role == "select" for item in canvas.overlay().items)
        canvas.dispose()
        parent.deleteLater()


def test_a_spacer_draws_a_spring() -> None:
    with opened(SPACER) as (session, realizer):
        canvas, parent = _canvas(session, realizer, _Host())
        assert any(isinstance(item, Spring) for item in canvas.overlay().items)
        canvas.dispose()
        parent.deleteLater()


def test_a_container_without_a_layout_shows_a_chip_beside_its_child() -> None:
    with opened(BARE) as (session, realizer):
        canvas, parent = _canvas(session, realizer, _Host())
        chips = [item for item in canvas.overlay().items if isinstance(item, Chip) and item.text == "No layout"]
        assert len(chips) == 1
        button = _widget_rect(canvas, "ok")
        assert not chips[0].rect.intersects(button)
        canvas.dispose()
        parent.deleteLater()


@pytest.mark.timeout(180)
def test_chips_do_not_cover_content_on_loadable_corpus_forms() -> None:
    checked = 0
    for path in _forms():
        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            with opened(text, str(path)) as (session, realizer):
                root = realizer.root_widget
                if root is None or root.width() <= 0 or root.height() <= 0:
                    continue
                canvas, parent = _canvas(session, realizer, _Host())
                try:
                    _assert_clear(canvas, session, realizer, path)
                    for node in session.document.iter_preorder():
                        if not isinstance(node, WidgetNode):
                            continue
                        if realizer.widget_for(node.id) is None:
                            continue
                        session.selection.set((node.id,), current=node.id, source=SelectionSource.CANVAS)
                        _flush()
                        _assert_clear(canvas, session, realizer, path)
                    checked += 1
                finally:
                    canvas.dispose()
                    parent.deleteLater()
                    _flush()
        except UiReadError:
            continue
    assert checked >= 100


def _forms() -> List[Path]:
    found = []
    for folder in _LOADABLE:
        found.extend(sorted((_CORPUS / folder).rglob("*.ui")))
    return found


def _assert_clear(canvas: FormCanvas, session: FormSession, realizer: Realizer, path: Path) -> None:
    """UX-CHIP-001. Ancestors are not content. The chip's own widget is."""
    root = canvas.page_widget()
    assert root is not None
    proxy = root.graphicsProxyWidget()
    assert proxy is not None
    document = session.document
    widgets: List[Tuple[NodeId, CanvasRect]] = []
    for node in document.iter_preorder():
        if not isinstance(node, WidgetNode):
            continue
        widget = realizer.widget_for(node.id)
        if widget is None or not widget.isVisible() or widget.width() <= 0 or widget.height() <= 0:
            continue
        widgets.append((node.id, _mapped(proxy, root, widget)))
    for chip_rect, node_id in canvas.overlay().chips:
        allowed = document.ancestors(node_id)
        for other_id, other in widgets:
            if other_id in allowed:
                continue
            assert not chip_rect.intersects(other), "%s chip on %s covers %s" % (
                path.name,
                _name(document, node_id),
                _name(document, other_id),
            )


def _name(document: UiDocument, node_id: NodeId) -> str:
    found = document.get(node_id)
    name = getattr(found, "object_name", None)
    if isinstance(name, str) and name:
        return name
    return str(node_id)


def _mapped(proxy: object, root: QWidget, widget: QWidget) -> CanvasRect:
    top_left = widget.rect().topLeft()
    bottom_right = widget.rect().bottomRight()
    if widget is not root:
        top_left = widget.mapTo(root, top_left)
        bottom_right = widget.mapTo(root, bottom_right)
    scene_tl = proxy.mapToScene(top_left)  # type: ignore[attr-defined]
    scene_br = proxy.mapToScene(bottom_right)  # type: ignore[attr-defined]
    return CanvasRect(
        int(min(scene_tl.x(), scene_br.x())),
        int(min(scene_tl.y(), scene_br.y())),
        max(1, int(abs(scene_br.x() - scene_tl.x()))),
        max(1, int(abs(scene_br.y() - scene_tl.y()))),
    )


def _canvas(session: object, realizer: object, host: _Host) -> Tuple[FormCanvas, QWidget]:
    parent = QWidget()
    parent.resize(960, 720)
    canvas = FormCanvas(session, realizer, host, parent)  # type: ignore[arg-type]
    canvas.resize(960, 720)
    parent.show()
    _flush()
    return canvas, parent


def _click(canvas: FormCanvas, name: str) -> None:
    QTest.mouseClick(canvas.viewport(), _mouse("LeftButton"), _mods("NoModifier"), _center(canvas, name))
    _flush()


def _move(canvas: FormCanvas, name: str) -> None:
    QTest.mouseMove(canvas.viewport(), _center(canvas, name))
    _flush()


def _center(canvas: FormCanvas, name: str) -> QPoint:
    return _port(canvas, _widget_point(canvas, name))


def _widget_rect(canvas: FormCanvas, name: str) -> CanvasRect:
    root = canvas.page_widget()
    assert root is not None
    widget = root.findChild(QWidget, name)
    assert widget is not None
    proxy = root.graphicsProxyWidget()
    assert proxy is not None
    return _mapped(proxy, root, widget)


def _widget_point(canvas: FormCanvas, name: str) -> QPoint:
    root = canvas.page_widget()
    assert root is not None
    widget = root.findChild(QWidget, name)
    assert widget is not None
    return widget.mapTo(root, widget.rect().center())


def _port(canvas: FormCanvas, point: QPoint) -> QPoint:
    root = canvas.page_widget()
    assert root is not None
    proxy = root.graphicsProxyWidget()
    assert proxy is not None
    return canvas.mapFromScene(proxy.mapToScene(point))


def _id(document: UiDocument, name: str) -> NodeId:
    matches = [node.id for node in document.iter_preorder() if getattr(node, "object_name", None) == name]
    assert len(matches) == 1
    return matches[0]


def _flush() -> None:
    app = QApplication.instance()
    assert app is not None
    # Show posts a resize after the first frame. Drain until that frame lands.
    for _ in range(4):
        app.processEvents()


def _mouse(name: str) -> Qt.MouseButton:
    return getattr(getattr(Qt, "MouseButton", Qt), name)


def _mods(name: str) -> Qt.KeyboardModifier:
    return getattr(getattr(Qt, "KeyboardModifier", Qt), name)
