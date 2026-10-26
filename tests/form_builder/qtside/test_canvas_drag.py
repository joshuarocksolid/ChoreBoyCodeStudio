# pyright: reportAttributeAccessIssue=false
"""Free move, free resize, and page grabbers. The document changes on release."""

from __future__ import annotations

from typing import Tuple

import pytest

from app.qt.QtCore import QEvent, QPoint, QPointF, Qt  # type: ignore[reportAttributeAccessIssue]
from app.qt.QtGui import QMouseEvent  # type: ignore[reportAttributeAccessIssue]
from app.qt.QtWidgets import QApplication, QWidget
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.values import RectValue
from app.features.form_builder.integration.canvas import FormCanvas
from app.features.form_builder.qtside.canvas.core.frame import OnKnob, OnPageEdge
from app.features.form_builder.qtside.canvas.core.space import CanvasRect
from tests.form_builder.qtside.support import form, opened

pytestmark = pytest.mark.usefixtures("qapp")

FREE = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>300</height></rect></property>
  <widget class="QPushButton" name="ok">
   <property name="geometry"><rect><x>40</x><y>40</y><width>80</width><height>28</height></rect></property>
   <property name="text"><string>OK</string></property>
  </widget>
""",
)

LAID = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>300</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QPushButton" name="ok">
     <property name="text"><string>OK</string></property>
    </widget>
   </item>
  </layout>
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

    def open_context_menu(self, node: object, at: object) -> None:
        return None


def test_a_free_drag_is_one_undo_on_release() -> None:
    with opened(FREE) as (session, realizer):
        canvas, parent = _canvas(session, realizer)
        start = _center(canvas, "ok")
        end = start + QPoint(24, 0)
        _press(canvas, start)
        _move(canvas, end)
        assert _widget(canvas, "ok").x() == 64
        assert _geometry(session, "ok") == RectValue(40, 40, 80, 28)
        _release(canvas, end)
        assert _geometry(session, "ok") == RectValue(64, 40, 80, 28)
        assert session.log.undo_label() == "Move"
        assert session.log.undo()
        _flush()
        assert _geometry(session, "ok") == RectValue(40, 40, 80, 28)
        assert not session.log.can_undo()
        canvas.dispose()
        parent.deleteLater()


def test_a_free_resize_is_one_undo_on_release() -> None:
    with opened(FREE) as (session, realizer):
        canvas, parent = _canvas(session, realizer)
        _click(canvas, "ok")
        start = _handle(canvas, "se")
        end = start + QPoint(24, 24)
        _press(canvas, start)
        _move(canvas, end)
        assert _widget(canvas, "ok").width() == 104
        assert _geometry(session, "ok") == RectValue(40, 40, 80, 28)
        _release(canvas, end)
        assert _geometry(session, "ok") == RectValue(40, 40, 104, 56)
        assert session.log.undo_label() == "Resize"
        assert session.log.undo()
        _flush()
        assert _geometry(session, "ok") == RectValue(40, 40, 80, 28)
        assert not session.log.can_undo()
        canvas.dispose()
        parent.deleteLater()


def test_a_page_drag_reflows_before_it_commits() -> None:
    with opened(LAID) as (session, realizer):
        canvas, parent = _canvas(session, realizer)
        button = _widget(canvas, "ok")
        root = canvas.page_widget()
        assert root is not None
        before_button = button.width()
        before_root = root.width()
        start = _edge(canvas, "e")
        end = start + QPoint(24, 0)
        _press(canvas, start)
        _move(canvas, end)
        assert root.width() > before_root
        assert button.width() > before_button
        assert _geometry(session, "Form").width == 400
        _release(canvas, end)
        assert _geometry(session, "Form").width == 424
        assert session.log.undo_label() == "Resize form"
        assert session.log.undo()
        _flush()
        assert _geometry(session, "Form").width == 400
        assert not session.log.can_undo()
        canvas.dispose()
        parent.deleteLater()


@pytest.mark.parametrize("shift", (False, True))
def test_a_page_drag_moves_one_px_and_shift_snaps_to_eight(shift: bool) -> None:
    with opened(LAID) as (session, realizer):
        canvas, parent = _canvas(session, realizer)
        pulled = 13
        free = _geometry(session, "Form").width + pulled
        snapped = int(round(free / 8.0)) * 8
        assert free != snapped
        mods = "ShiftModifier" if shift else "NoModifier"
        start = _edge(canvas, "e")
        end = start + QPoint(pulled, 0)
        _press(canvas, start, mods)
        _move(canvas, end, mods)
        _release(canvas, end, mods)
        assert _geometry(session, "Form").width == (snapped if shift else free)
        canvas.dispose()
        parent.deleteLater()


def _canvas(session: object, realizer: object) -> Tuple[FormCanvas, QWidget]:
    parent = QWidget()
    parent.resize(960, 720)
    canvas = FormCanvas(session, realizer, _Host(), parent)  # type: ignore[arg-type]
    canvas.resize(960, 720)
    parent.show()
    _flush()
    return canvas, parent


def _press(canvas: FormCanvas, pos: QPoint, mods: str = "NoModifier") -> None:
    _send(canvas, "MouseButtonPress", pos, "LeftButton", "LeftButton", mods)


def _move(canvas: FormCanvas, pos: QPoint, mods: str = "NoModifier") -> None:
    _send(canvas, "MouseMove", pos, "NoButton", "LeftButton", mods)


def _release(canvas: FormCanvas, pos: QPoint, mods: str = "NoModifier") -> None:
    _send(canvas, "MouseButtonRelease", pos, "LeftButton", "NoButton", mods)


def _send(canvas: FormCanvas, kind_name: str, pos: QPoint, button_name: str, buttons_name: str, mods: str) -> None:
    viewport = canvas.viewport()
    kind = getattr(getattr(QEvent, "Type", QEvent), kind_name)
    event = QMouseEvent(
        kind,
        pos,
        viewport.mapToGlobal(pos),
        _mouse(button_name),
        _mouse(buttons_name),
        _mods(mods),
    )
    QApplication.sendEvent(viewport, event)
    _flush()


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


def _handle(canvas: FormCanvas, at: str) -> QPoint:
    for rect, target in canvas.overlay().targets:
        if isinstance(target, OnKnob) and target.knob.key[0] == "size" and target.knob.pull == at:
            return _from_rect(canvas, rect)
    raise AssertionError(at)


def _edge(canvas: FormCanvas, at: str) -> QPoint:
    for rect, target in canvas.overlay().targets:
        if isinstance(target, OnPageEdge) and target.at == at:
            return _from_rect(canvas, rect)
    raise AssertionError(at)


def _from_rect(canvas: FormCanvas, rect: CanvasRect) -> QPoint:
    return canvas.mapFromScene(QPointF(rect.x + rect.width / 2.0, rect.y + rect.height / 2.0))


def _widget(canvas: FormCanvas, name: str) -> QWidget:
    root = canvas.page_widget()
    assert root is not None
    widget = root.findChild(QWidget, name)
    assert widget is not None
    return widget


def _geometry(session: FormSession, name: str) -> RectValue:
    node = next(item for item in session.document.iter_preorder() if getattr(item, "object_name", None) == name)
    assert isinstance(node, WidgetNode)
    entry = node.prop("geometry")
    assert entry is not None and isinstance(entry.value, RectValue)
    return entry.value


def _flush() -> None:
    app = QApplication.instance()
    assert app is not None
    for _ in range(4):
        app.processEvents()


def _mouse(name: str) -> Qt.MouseButton:
    return getattr(getattr(Qt, "MouseButton", Qt), name)


def _mods(name: str) -> Qt.KeyboardModifier:
    return getattr(getattr(Qt, "KeyboardModifier", Qt), name)
