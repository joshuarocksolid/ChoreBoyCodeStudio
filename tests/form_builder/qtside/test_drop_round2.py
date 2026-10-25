# pyright: reportAttributeAccessIssue=false
"""Round-2 canvas drops. Real widget events where the gesture is interactive."""

from __future__ import annotations

from typing import List

import pytest

from app.qt.QtCore import QEvent, QPoint, QPointF, Qt
from app.qt.QtGui import QMouseEvent
from app.qt.QtWidgets import QApplication, QLineEdit, QWidget
from app.features.form_builder.engine.query.drop_target import DropPayload
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.ui4.nodes import LayoutNode, WidgetNode
from app.features.form_builder.integration.canvas import FormCanvas
from app.features.form_builder.integration.workbench import OutlinePane
from app.features.form_builder.qtside.canvas.core.frame import Chip, Fill, Stroke
from app.features.form_builder.qtside.canvas.core.gesture import PlaceAsked, PlaceDrop, PlaceHover
from app.features.form_builder.qtside.canvas.core.space import CanvasPoint
from tests.form_builder.qtside.support import form, opened
from tests.form_builder.qtside.test_drop import _content_names, _layout, _port

pytestmark = pytest.mark.usefixtures("qapp")


FREE_AND_BOX = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>420</width><height>260</height></rect></property>
  <widget class="QGroupBox" name="box">
   <property name="geometry"><rect><x>8</x><y>8</y><width>180</width><height>160</height></rect></property>
   <layout class="QVBoxLayout" name="verticalLayout">
    <item><widget class="QPushButton" name="inside"><property name="text"><string>Inside</string></property></widget></item>
   </layout>
  </widget>
  <widget class="QPushButton" name="loose">
   <property name="geometry"><rect><x>220</x><y>40</y><width>80</width><height>28</height></rect></property>
   <property name="text"><string>Loose</string></property>
  </widget>
""",
)

FORM = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>420</width><height>260</height></rect></property>
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="0"><widget class="QLabel" name="emailLabel"><property name="text"><string>Email:</string></property></widget></item>
   <item row="0" column="1"><widget class="QLineEdit" name="email"/></item>
  </layout>
""",
)

TABS = form(
    'class="QTabWidget" name="tabs"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>420</width><height>240</height></rect></property>
  <widget class="QWidget" name="pageOne">
   <attribute name="title"><string>One</string></attribute>
   <layout class="QVBoxLayout" name="verticalLayout"/>
  </widget>
""",
)

STACK = form(
    'class="QStackedWidget" name="pages"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>420</width><height>240</height></rect></property>
  <widget class="QWidget" name="first"><layout class="QVBoxLayout" name="verticalLayout"/></widget>
  <widget class="QWidget" name="second"><layout class="QVBoxLayout" name="horizontalWait"/></widget>
""",
)


class _Host:
    def __init__(self) -> None:
        self.toasts: List[str] = []
        self.sentences: List[str] = []

    def canvas_pressed(self) -> None:
        return None

    def narrate(self, sentence: str) -> None:
        self.sentences.append(sentence)

    def show_plain(self, sentence: str) -> None:
        self.toasts.append(sentence)

    def hover_changed(self, node: object) -> None:
        return None

    def zoom_changed(self, label: str) -> None:
        return None

    def open_problem(self, node: object) -> None:
        return None

    def open_layout_popover(self, node: object) -> None:
        return None


def test_a_cancelled_insert_drag_lets_the_next_click_select() -> None:
    with opened(FREE_AND_BOX) as (session, realizer):
        canvas, parent = _canvas(session, realizer, 440, 270)
        canvas.send(PlaceAsked(CanvasPoint(30, 30), DropPayload("widget"), "QLineEdit"))
        _flush()
        canvas.send(PlaceDrop(CanvasPoint(0, 0), True, None, True))
        _flush()
        _click(canvas, "loose")
        current = session.selection.state.current
        assert current is not None
        node = session.document.node(current)
        assert isinstance(node, WidgetNode)
        assert node.object_name == "loose"
        canvas.dispose()
        parent.deleteLater()


def test_every_drop_on_a_short_canvas_shows_its_chip() -> None:
    with opened(FREE_AND_BOX) as (session, realizer):
        canvas, parent = _canvas(session, realizer, 440, 270)
        for name in ("inside", "loose", "box"):
            _click(canvas, name)
            point = _center(canvas, name)
            scene = canvas.mapToScene(point)
            canvas.send(PlaceAsked(CanvasPoint(int(scene.x()), int(scene.y())), DropPayload("widget"), "QLineEdit"))
            _flush()
            chips = [item.text for item in canvas.overlay().items if isinstance(item, Chip)]
            assert chips, name
            canvas.send(PlaceDrop(CanvasPoint(0, 0), True, None, True))
            _flush()
        canvas.dispose()
        parent.deleteLater()


def test_a_refused_target_does_not_fill_over_the_widget() -> None:
    with opened(FORM) as (session, realizer):
        canvas, parent = _canvas(session, realizer, 440, 270)
        point = _center(canvas, "email")
        scene = canvas.mapToScene(point)
        canvas.send(PlaceAsked(CanvasPoint(int(scene.x()), int(scene.y())), DropPayload("spacer"), "spacer-v"))
        _flush()
        fills = [item for item in canvas.overlay().items if isinstance(item, Fill) and item.role == "drop_fill"]
        assert fills == []
        canvas.send(PlaceDrop(CanvasPoint(0, 0), True, None, True))
        _flush()
        canvas.dispose()
        parent.deleteLater()


def test_a_box_line_has_round_end_caps() -> None:
    with opened(FREE_AND_BOX) as (session, realizer):
        canvas, parent = _canvas(session, realizer, 640, 480)
        point = _center(canvas, "inside")
        scene = canvas.mapToScene(point)
        canvas.send(PlaceAsked(CanvasPoint(int(scene.x()), int(scene.y())), DropPayload("widget"), "QLineEdit"))
        _flush()
        caps = [
            item
            for item in canvas.overlay().items
            if isinstance(item, Stroke) and item.caps and item.role == "select"
        ]
        assert caps
        canvas.send(PlaceDrop(CanvasPoint(0, 0), True, None, True))
        _flush()
        canvas.dispose()
        parent.deleteLater()


def test_a_free_widget_dropped_on_a_layout_is_reparented() -> None:
    with opened(FREE_AND_BOX) as (session, realizer):
        canvas, parent = _canvas(session, realizer, 640, 480)
        start = _center(canvas, "loose")
        end = _center(canvas, "inside")
        _press(canvas, start)
        _move(canvas, end)
        _release(canvas, end)
        parent_node = session.document.parent(session.document.by_name("loose")[0])
        assert isinstance(parent_node, LayoutNode) or (
            parent_node is not None and parent_node.kind == "layoutitem"
        )
        canvas.dispose()
        parent.deleteLater()


def test_the_new_field_editor_opens_on_the_new_row() -> None:
    with opened(FORM) as (session, realizer):
        canvas, parent = _canvas(session, realizer, 640, 480)
        root = canvas.page_widget()
        assert root is not None
        below = root.rect().bottom() - 8
        proxy = root.graphicsProxyWidget()
        assert proxy is not None
        scene = proxy.mapToScene(QPointF(root.width() / 2, below))
        canvas.send(PlaceAsked(CanvasPoint(int(scene.x()), int(scene.y())), DropPayload("widget"), "QLineEdit"))
        _flush()
        canvas.send(PlaceDrop(CanvasPoint(int(scene.x()), int(scene.y())), True))
        _flush()
        editors = [item for item in canvas.viewport().findChildren(QLineEdit) if item.parent() is canvas.viewport()]
        assert editors
        assert editors[0].y() > 20
        canvas.dispose()
        parent.deleteLater()


def test_a_selected_tab_widget_shows_the_plus() -> None:
    with opened(TABS) as (session, realizer):
        canvas, parent = _canvas(session, realizer, 640, 480)
        tabs = session.document.by_name("tabs")[0]
        session.selection.set((tabs,), current=tabs, source=SelectionSource.PROGRAM)
        _flush()
        texts = [item.text for item in canvas.overlay().items if isinstance(item, Chip)]
        assert "+" in texts
        canvas.dispose()
        parent.deleteLater()


def test_a_stacked_widget_shows_the_page_chip() -> None:
    with opened(STACK) as (session, realizer):
        canvas, parent = _canvas(session, realizer, 640, 480)
        _flush()
        texts = [item.text for item in canvas.overlay().items if isinstance(item, Chip)]
        assert any(text.startswith("◀") and "/" in text for text in texts)
        tips = [item.tip for item in canvas.overlay().items if isinstance(item, Chip) and item.tip]
        assert "first" in tips
        canvas.dispose()
        parent.deleteLater()


VERTICAL = form(
    'class="QWidget" name="Form"',
    """
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QPushButton" name="shop"><property name="text"><string>Shop</string></property></widget></item>
   <item><widget class="QPushButton" name="receipts"><property name="text"><string>Receipts</string></property></widget></item>
  </layout>
""",
)


def test_an_outline_drop_reorders_the_row() -> None:
    with opened(VERTICAL) as (session, realizer):
        canvas, parent = _canvas(session, realizer, 720, 520)
        pane = _outline(canvas, parent, session)
        receipts = session.document.by_name("receipts")[0]
        canvas.send(PlaceAsked(CanvasPoint(20, 20), DropPayload("widget", (receipts,)), ""))
        _flush()
        pane._post_target(_row_top(pane, session, "shop"), True)  # type: ignore[attr-defined]
        _flush()
        assert _content_names(_layout(session.document, "verticalLayout")) == ["receipts", "shop"]
        canvas.dispose()
        parent.deleteLater()


def test_an_insert_dropped_on_the_outline_lands_in_the_layout() -> None:
    with opened(VERTICAL) as (session, realizer):
        canvas, parent = _canvas(session, realizer, 720, 520)
        pane = _outline(canvas, parent, session)
        canvas.send(PlaceAsked(CanvasPoint(20, 20), DropPayload("widget"), "QPushButton"))
        _flush()
        pane._post_target(_row_top(pane, session, "shop"), True)  # type: ignore[attr-defined]
        _flush()
        assert _content_names(_layout(session.document, "verticalLayout")) == ["pushButton", "shop", "receipts"]
        canvas.dispose()
        parent.deleteLater()


def test_an_outline_drag_dropped_on_the_canvas_moves_the_widget() -> None:
    with opened(VERTICAL) as (session, realizer):
        canvas, parent = _canvas(session, realizer, 720, 520)
        shop = session.document.by_name("shop")[0]
        canvas.send(PlaceAsked(CanvasPoint(20, 20), DropPayload("widget", (shop,)), ""))
        _flush()
        root = canvas.page_widget()
        assert root is not None
        receipts = root.findChild(QWidget, "receipts")
        assert receipts is not None
        below = receipts.mapTo(root, QPoint(receipts.width() // 2, receipts.height() - 2))
        port = _port(canvas, root, below)
        at = CanvasPoint(port.x(), port.y())
        canvas.send(PlaceHover(at, True))
        canvas.send(PlaceDrop(at, True))
        _flush()
        assert _content_names(_layout(session.document, "verticalLayout")) == ["receipts", "shop"]
        canvas.dispose()
        parent.deleteLater()


def test_the_same_refusal_twice_toasts() -> None:
    with opened(FORM) as (session, realizer):
        canvas, parent, host = _canvas_host(session, realizer, 640, 480)
        point = _center(canvas, "email")
        scene = canvas.mapToScene(point)
        at = CanvasPoint(int(scene.x()), int(scene.y()))
        canvas.send(PlaceAsked(at, DropPayload("spacer"), "spacer-v"))
        _flush()
        canvas.send(PlaceDrop(CanvasPoint(0, 0), True, None, True))
        _flush()
        canvas.send(PlaceAsked(at, DropPayload("spacer"), "spacer-v"))
        _flush()
        assert host.toasts
        canvas.dispose()
        parent.deleteLater()


def _outline(canvas: FormCanvas, parent: QWidget, session) -> OutlinePane:  # type: ignore[no-untyped-def]
    pane = OutlinePane(lambda _node: None, lambda _collapsed: None, parent)
    pane.rebuild(session.document, None)
    pane.set_drop_bridge(canvas.send, canvas.place_payload)  # type: ignore[arg-type]
    pane.setGeometry(0, 0, 220, parent.height())
    pane.show()
    _flush()
    return pane


def _row_top(pane: OutlinePane, session, name: str) -> QPoint:  # type: ignore[no-untyped-def]
    """Point in the top third of a row, so the test holds at any font height."""
    node = session.document.by_name(name)[0]
    rect = pane.tree.visualItemRect(pane._rows[int(node)])  # type: ignore[attr-defined]
    return QPoint(12, rect.y() + max(1, rect.height() // 6))


def _canvas(session, realizer, width: int, height: int):
    canvas, parent, _host = _canvas_host(session, realizer, width, height)
    return canvas, parent


def _canvas_host(session, realizer, width: int, height: int):
    parent = QWidget()
    parent.resize(width, height)
    host = _Host()
    canvas = FormCanvas(session, realizer, host, parent)
    canvas.resize(width, height)
    parent.show()
    _flush()
    canvas.setFocus()
    _flush()
    return canvas, parent, host


def _press(canvas: FormCanvas, pos: QPoint) -> None:
    _send(canvas, "MouseButtonPress", pos, "LeftButton", "LeftButton")


def _move(canvas: FormCanvas, pos: QPoint) -> None:
    _send(canvas, "MouseMove", pos, "NoButton", "LeftButton")


def _release(canvas: FormCanvas, pos: QPoint) -> None:
    _send(canvas, "MouseButtonRelease", pos, "LeftButton", "NoButton")


def _click(canvas: FormCanvas, name: str) -> None:
    _press(canvas, _center(canvas, name))
    _release(canvas, _center(canvas, name))


def _center(canvas: FormCanvas, name: str) -> QPoint:
    root = canvas.page_widget()
    assert root is not None
    widget = root.findChild(QWidget, name)
    assert widget is not None
    proxy = root.graphicsProxyWidget()
    assert proxy is not None
    return canvas.mapFromScene(proxy.mapToScene(widget.mapTo(root, widget.rect().center())))


def _send(canvas: FormCanvas, kind_name: str, pos: QPoint, button_name: str, buttons_name: str) -> None:
    viewport = canvas.viewport()
    kind = getattr(getattr(QEvent, "Type", QEvent), kind_name)
    event = QMouseEvent(
        kind,
        pos,
        viewport.mapToGlobal(pos),
        _mouse(button_name),
        _mouse(buttons_name),
        _mods("NoModifier"),
    )
    QApplication.sendEvent(viewport, event)
    _flush()


def _flush() -> None:
    app = QApplication.instance()
    assert app is not None
    for _ in range(6):
        app.processEvents()


def _mouse(name: str) -> Qt.MouseButton:
    return getattr(getattr(Qt, "MouseButton", Qt), name)


def _mods(name: str) -> Qt.KeyboardModifier:
    return getattr(getattr(Qt, "KeyboardModifier", Qt), name)
