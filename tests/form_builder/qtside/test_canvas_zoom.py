"""Zoom steps, page gutters, and screen-size overlay strokes."""

from __future__ import annotations

from typing import List, Tuple

import pytest

from app.qt.QtCore import QRectF, Qt  # type: ignore[reportAttributeAccessIssue]
from app.qt.QtGui import QImage, QPainter  # type: ignore[reportAttributeAccessIssue]
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QWidget
from app.features.form_builder.integration.canvas import FormCanvas
from app.features.form_builder.qtside.canvas.core.frame import Handle, Stroke
from app.features.form_builder.qtside.canvas.core.space import GUTTERS
from tests.form_builder.qtside.support import form, opened

pytestmark = pytest.mark.usefixtures("qapp")

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

WIDE = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>2400</width><height>1800</height></rect></property>
  <widget class="QPushButton" name="ok">
   <property name="geometry"><rect><x>40</x><y>40</y><width>80</width><height>28</height></rect></property>
   <property name="text"><string>OK</string></property>
  </widget>
""",
)


class _Host:
    def __init__(self) -> None:
        self.labels: List[str] = []

    def canvas_pressed(self) -> None:
        return None

    def narrate(self, sentence: str) -> None:
        return None

    def hover_changed(self, node: object) -> None:
        return None

    def zoom_changed(self, label: str) -> None:
        self.labels.append(label)

    def open_problem(self, node: object) -> None:
        return None

    def open_layout_popover(self, node: object) -> None:
        return None


def test_ctrl_plus_steps_through_the_zoom_table() -> None:
    host = _Host()
    with opened(BUTTON) as (session, realizer):
        canvas, parent = _canvas(session, realizer, host, 960, 720)
        assert abs(_scale(canvas) - 1.0) < 1e-6
        _zoom_in(canvas)
        assert abs(_scale(canvas) - 1.1) < 1e-6
        assert host.labels[-1] == "110%"
        _zoom_in(canvas)
        assert abs(_scale(canvas) - 1.25) < 1e-6
        assert host.labels[-1] == "125%"
        assert canvas.transform().isIdentity()
        canvas.dispose()
        parent.deleteLater()


def test_a_page_larger_than_the_view_keeps_both_gutters() -> None:
    with opened(WIDE) as (session, realizer):
        canvas, parent = _canvas(session, realizer, _Host(), 640, 480)
        root = canvas.page_widget()
        assert root is not None
        proxy = root.graphicsProxyWidget()
        assert proxy is not None
        assert int(proxy.pos().x()) == GUTTERS.left
        assert int(proxy.pos().y()) == GUTTERS.top
        scene = canvas.sceneRect()
        scaled_w = proxy.boundingRect().width() * proxy.scale()
        scaled_h = proxy.boundingRect().height() * proxy.scale()
        assert scene.width() >= proxy.pos().x() + scaled_w + GUTTERS.right - 1
        assert scene.height() >= proxy.pos().y() + scaled_h + GUTTERS.bottom - 1
        canvas.dispose()
        parent.deleteLater()


def test_handles_stay_seven_pixels_at_two_hundred_percent() -> None:
    with opened(BUTTON) as (session, realizer):
        canvas, parent = _canvas(session, realizer, _Host(), 960, 720)
        _click(canvas, "ok")
        for _ in range(5):
            _zoom_in(canvas)
        assert abs(_scale(canvas) - 2.0) < 1e-6
        assert canvas.transform().isIdentity()
        handles = [item for item in canvas.overlay().items if isinstance(item, Handle)]
        assert handles
        assert {item.rect.width for item in handles} == {7}
        assert {item.rect.height for item in handles} == {7}
        strokes = [
            item
            for item in canvas.overlay().items
            if isinstance(item, Stroke) and item.role == "select" and item.style == "solid"
        ]
        assert strokes
        assert {item.width for item in strokes} == {2}
        canvas.dispose()
        parent.deleteLater()


def test_draw_foreground_paints_the_selection_stroke() -> None:
    with opened(BUTTON) as (session, realizer):
        canvas, parent = _canvas(session, realizer, _Host(), 960, 720)
        _click(canvas, "ok")
        stroke = next(
            item
            for item in canvas.overlay().items
            if isinstance(item, Stroke) and item.role == "select" and item.style == "solid"
        )
        scene = canvas.sceneRect()
        image = QImage(max(1, int(scene.width())), max(1, int(scene.height())), _argb())
        image.fill(0)
        painter = QPainter(image)
        canvas.drawForeground(painter, QRectF(scene))
        painter.end()
        x = stroke.rect.x + stroke.rect.width // 4
        assert _near_blue(image, x, stroke.rect.y)
        canvas.dispose()
        parent.deleteLater()


def _canvas(
    session: object, realizer: object, host: _Host, width: int, height: int
) -> Tuple[FormCanvas, QWidget]:
    parent = QWidget()
    parent.resize(width, height)
    canvas = FormCanvas(session, realizer, host, parent)  # type: ignore[arg-type]
    canvas.resize(width, height)
    parent.show()
    _flush()
    return canvas, parent


def _zoom_in(canvas: FormCanvas) -> None:
    QTest.keyClick(canvas, _qt_key("Key_Equal"), _mods("ControlModifier"))
    _flush()


def _click(canvas: FormCanvas, name: str) -> None:
    QTest.mouseClick(canvas.viewport(), _mouse("LeftButton"), _mods("NoModifier"), _center(canvas, name))
    _flush()


def _center(canvas: FormCanvas, name: str) -> object:
    root = canvas.page_widget()
    assert root is not None
    widget = root.findChild(QWidget, name)
    assert widget is not None
    proxy = root.graphicsProxyWidget()
    assert proxy is not None
    return canvas.mapFromScene(proxy.mapToScene(widget.mapTo(root, widget.rect().center())))


def _scale(canvas: FormCanvas) -> float:
    root = canvas.page_widget()
    assert root is not None
    proxy = root.graphicsProxyWidget()
    assert proxy is not None
    return float(proxy.scale())


def _near_blue(image: QImage, x: int, y: int) -> bool:
    for dy in range(-2, 3):
        color = image.pixelColor(x, y + dy)
        if color.blue() > 180 and color.red() < 100 and color.green() < 140:
            return True
    return False


def _argb() -> QImage.Format:
    return getattr(getattr(QImage, "Format", QImage), "Format_ARGB32")


def _flush() -> None:
    app = QApplication.instance()
    assert app is not None
    for _ in range(4):
        app.processEvents()


def _mouse(name: str) -> Qt.MouseButton:
    return getattr(getattr(Qt, "MouseButton", Qt), name)


def _mods(name: str) -> Qt.KeyboardModifier:
    return getattr(getattr(Qt, "KeyboardModifier", Qt), name)


def _qt_key(name: str) -> Qt.Key:
    return getattr(getattr(Qt, "Key", Qt), name)
