# pyright: reportAttributeAccessIssue=false
"""Zoom steps, page gutters, and screen-size overlay strokes."""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

import pytest

from app.qt.QtCore import QPoint, QPointF, QRectF, Qt  # type: ignore[reportAttributeAccessIssue]
from app.qt.QtGui import QImage, QPainter, QWheelEvent  # type: ignore[reportAttributeAccessIssue]
from app.qt.QtTest import QTest
from app.qt.QtGui import QAction  # type: ignore[reportAttributeAccessIssue]
from app.qt.QtWidgets import QApplication, QMenu, QMenuBar, QShortcut, QToolButton, QWidget
from app.features.form_builder.integration.canvas import FormCanvas
from app.features.form_builder.integration.form_menu import register_form_menu
from app.features.form_builder.qtside.canvas.core.frame import Handle, Stroke
from app.features.form_builder.qtside.canvas.core.space import GUTTERS
from app.shell.menus import build_menu_stubs, clear_menu_contributors
from tests.form_builder.qtside.support import form, opened
from tests.unit.features.form_builder.test_workbench import _FORM, _open

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


def test_toolbar_and_form_menu_zoom_the_canvas(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    parent = QWidget()
    parent.resize(1100, 720)
    surface = _open(parent, _FORM, tmp_path / "invoice.ui")
    parent.show()
    _flush()
    canvas = surface.findChild(QWidget, "formBuilder.canvas")
    assert isinstance(canvas, FormCanvas)
    zoom_out = surface.findChild(QToolButton, "formBuilder.zoomOut")
    zoom_label = surface.findChild(QToolButton, "formBuilder.zoomLabel")
    zoom_in = surface.findChild(QToolButton, "formBuilder.zoomIn")
    assert zoom_out is not None and zoom_label is not None and zoom_in is not None
    assert zoom_out.isEnabled() and zoom_label.isEnabled() and zoom_in.isEnabled()
    assert zoom_out.toolTip() == "Zoom out"
    assert zoom_in.toolTip() == "Zoom in"
    before = _scale(canvas)
    QTest.mouseClick(zoom_in, _mouse("LeftButton"))
    _flush()
    assert _scale(canvas) > before + 0.05
    menu = zoom_label.menu()
    assert menu is not None
    assert menu.objectName() == "formBuilder.zoomMenu"
    labels = [action.text() for action in menu.actions()]
    assert labels == ["Fit", "50%", "75%", "100%", "150%", "200%"]
    _menu_action(menu, "50%").trigger()
    _flush()
    assert abs(_scale(canvas) - 0.5) < 1e-6
    assert zoom_label.text() == "50%"
    _menu_action(menu, "Fit").trigger()
    _flush()
    assert abs(_scale(canvas) - 0.5) > 0.05

    class _Tab:
        def __init__(self, path: str) -> None:
            self.file_path = path

    class _Manager:
        def active_tab(self) -> _Tab:
            return _Tab(surface.form_path())

    class _Registry:
        def surface_for_path(self, path: str) -> object:
            del path
            return surface

    window = QWidget()
    window._editor_manager = _Manager()  # type: ignore[attr-defined]
    window._tab_content_registry = _Registry()  # type: ignore[attr-defined]
    register_form_menu(window)
    bar = QMenuBar(window)
    try:
        registry = build_menu_stubs(bar)
        for command_id in (
            "form.action.zoomIn",
            "form.action.zoomOut",
            "form.action.zoomReset",
            "form.action.zoomToFit",
        ):
            assert registry.actions[command_id].isEnabled()
        fit = registry.actions["form.action.zoomToFit"]
        assert fit.shortcut().isEmpty()
        assert "Ctrl+9" in fit.text()
        _menu_action(menu, "200%").trigger()
        _flush()
        assert abs(_scale(canvas) - 2.0) < 1e-6
        registry.actions["form.action.zoomReset"].trigger()
        _flush()
        assert abs(_scale(canvas) - 1.0) < 1e-6
        registry.actions["form.action.zoomOut"].trigger()
        _flush()
        assert abs(_scale(canvas) - 0.9) < 1e-6
        registry.actions["form.action.zoomIn"].trigger()
        _flush()
        assert abs(_scale(canvas) - 1.0) < 1e-6
        registry.actions["form.action.zoomToFit"].trigger()
        _flush()
        assert abs(_scale(canvas) - 1.0) < 1e-6
    finally:
        clear_menu_contributors()
        surface.release()
        window.deleteLater()
        parent.deleteLater()
        qapp.processEvents()


def test_ctrl_wheel_zooms_inside_the_canvas() -> None:
    with opened(BUTTON) as (session, realizer):
        canvas, parent = _canvas(session, realizer, _Host(), 960, 720)
        before = _scale(canvas)
        _wheel(canvas, 120)
        assert _scale(canvas) > before + 0.05
        keys = [shortcut.key().toString() for shortcut in canvas.findChildren(QShortcut)]
        assert all("Wheel" not in key for key in keys)
        canvas.dispose()
        parent.deleteLater()


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


def _menu_action(menu: QMenu, label: str) -> QAction:
    return next(action for action in menu.actions() if action.text() == label)


def _wheel(canvas: FormCanvas, dy: int) -> None:
    pos = QPointF(24, 24)
    buttons = getattr(getattr(Qt, "MouseButton", Qt), "NoButton")
    phase = getattr(getattr(Qt, "ScrollPhase", Qt), "NoScrollPhase")
    event = QWheelEvent(pos, pos, QPoint(0, 0), QPoint(0, dy), buttons, _mods("ControlModifier"), phase, False)
    QApplication.sendEvent(canvas.viewport(), event)
    _flush()


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
