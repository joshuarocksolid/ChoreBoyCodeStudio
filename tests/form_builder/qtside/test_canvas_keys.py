# pyright: reportAttributeAccessIssue=false
"""Keys, the rubber band, and reveal go through the viewport."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Tuple

import pytest

from app.qt.QtCore import QPoint, Qt  # type: ignore[reportAttributeAccessIssue]
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QWidget
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.integration.canvas import FormCanvas
from tests.form_builder.qtside.support import form, opened

pytestmark = pytest.mark.usefixtures("qapp")

PAGE = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>2400</width><height>1800</height></rect></property>
  <widget class="QFrame" name="north">
   <property name="geometry"><rect><x>40</x><y>40</y><width>80</width><height>40</height></rect></property>
  </widget>
  <widget class="QFrame" name="east">
   <property name="geometry"><rect><x>400</x><y>40</y><width>80</width><height>40</height></rect></property>
  </widget>
  <widget class="QFrame" name="south">
   <property name="geometry"><rect><x>40</x><y>1400</y><width>80</width><height>40</height></rect></property>
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


@contextmanager
def _shown(text: str = PAGE) -> Iterator[Tuple[FormSession, FormCanvas]]:
    with opened(text) as (session, realizer):
        parent = QWidget()
        parent.resize(640, 480)
        canvas = FormCanvas(session, realizer, _Host(), parent)
        canvas.resize(640, 480)
        parent.show()
        app = QApplication.instance()
        assert app is not None
        app.processEvents()
        canvas.setFocus()
        app.processEvents()
        try:
            yield session, canvas
        finally:
            canvas.dispose()
            parent.deleteLater()


def test_shift_click_on_the_only_widget_selects_the_form() -> None:
    with _shown() as (session, canvas):
        _click(canvas, "north")
        _click(canvas, "north", "ShiftModifier")
        assert session.selection.state.current == _id(session.document, "Form")
        assert session.selection.state.ids == (_id(session.document, "Form"),)


def test_ctrl_click_adds_the_widget() -> None:
    with _shown() as (session, canvas):
        _click(canvas, "north")
        _click(canvas, "east", "ControlModifier")
        north = _id(session.document, "north")
        east = _id(session.document, "east")
        assert session.selection.state.ids == (north, east)
        assert session.selection.state.current == east


def test_a_rubber_band_selects_the_widgets_it_covers() -> None:
    with _shown() as (session, canvas):
        _drag(canvas, 20, 120, 520, 20)
        selected = set(session.selection.state.ids)
        assert selected == {_id(session.document, "north"), _id(session.document, "east")}


def test_escape_selects_the_parent_and_stops_on_the_form() -> None:
    with _shown() as (session, canvas):
        _click(canvas, "east")
        _key(canvas, "Key_Escape")
        form_id = _id(session.document, "Form")
        assert session.selection.state.current == form_id
        _key(canvas, "Key_Escape")
        assert session.selection.state.current == form_id


def test_enter_on_the_form_selects_the_first_child() -> None:
    with _shown() as (session, canvas):
        _key(canvas, "Key_Return")
        assert session.selection.state.current == _id(session.document, "north")


def test_tab_reveals_the_next_widget() -> None:
    with _shown() as (session, canvas):
        _click(canvas, "east")
        before = _scroll(canvas)
        _key(canvas, "Key_Tab")
        assert session.selection.state.current == _id(session.document, "south")
        assert _scroll(canvas) != before


def test_arrow_selects_the_neighbor() -> None:
    with _shown() as (session, canvas):
        _click(canvas, "north")
        _key(canvas, "Key_Right")
        assert session.selection.state.current == _id(session.document, "east")


def test_alt_arrow_nudges_a_free_widget() -> None:
    with _shown() as (session, canvas):
        _click(canvas, "north")
        north = _widget(canvas, "north")
        assert north.x() == 40
        _key(canvas, "Key_Right", "AltModifier")
        assert north.x() == 48
        assert north.y() == 40
        assert session.selection.state.current == _id(session.document, "north")
        assert session.log.undo_label() == "Nudge"
        _key(canvas, "Key_Down", "AltModifier", "ShiftModifier")
        assert north.y() == 41
        assert len(session.log.entries()) == 1
        assert session.log.undo()
        _flush()
        assert north.y() == 40
        assert north.x() == 40


LAID = form(
    'class="QWidget" name="Form"',
    """
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QPushButton" name="first">
     <property name="text"><string>First</string></property>
    </widget>
   </item>
   <item>
    <widget class="QPushButton" name="second">
     <property name="text"><string>Second</string></property>
    </widget>
   </item>
  </layout>
""",
)


def test_alt_arrow_on_a_laid_out_widget_does_not_move_the_selection() -> None:
    with _shown(LAID) as (session, canvas):
        _click(canvas, "first")
        first = _widget(canvas, "first")
        origin = (first.x(), first.y())
        selected = session.selection.state.current
        _key(canvas, "Key_Down", "AltModifier")
        assert session.selection.state.current == selected
        assert (first.x(), first.y()) == origin
        assert session.log.undo_label() != "Nudge"


def test_a_canvas_press_does_not_scroll_and_an_outline_selection_does() -> None:
    with _shown() as (session, canvas):
        before = _scroll(canvas)
        _click(canvas, "north")
        assert _scroll(canvas) == before
        south = _id(session.document, "south")
        session.selection.set((south,), current=south, source=SelectionSource.OUTLINE)
        app = QApplication.instance()
        assert app is not None
        app.processEvents()
        assert session.selection.state.current == south
        assert _scroll(canvas) != before


def _click(canvas: FormCanvas, name: str, modifier: str = "NoModifier") -> None:
    root = canvas.page_widget()
    assert root is not None
    widget = root.findChild(QWidget, name)
    assert widget is not None
    center = widget.mapTo(root, widget.rect().center())
    _press_release(canvas, _port(canvas, root, center), modifier)


def _drag(canvas: FormCanvas, x0: int, y0: int, x1: int, y1: int) -> None:
    root = canvas.page_widget()
    assert root is not None
    start = _port(canvas, root, QPoint(x0, y0))
    end = _port(canvas, root, QPoint(x1, y1))
    button = _mouse("LeftButton")
    mods = _mods("NoModifier")
    viewport = canvas.viewport()
    QTest.mousePress(viewport, button, mods, start)
    QTest.mouseMove(viewport, end)
    QTest.mouseRelease(viewport, button, mods, end)
    _flush()


def _press_release(canvas: FormCanvas, port: QPoint, modifier: str) -> None:
    QTest.mouseClick(canvas.viewport(), _mouse("LeftButton"), _mods(modifier), port)
    _flush()


def _widget(canvas: FormCanvas, name: str) -> QWidget:
    root = canvas.page_widget()
    assert root is not None
    widget = root.findChild(QWidget, name)
    assert widget is not None
    return widget


def _key(canvas: FormCanvas, name: str, *modifiers: str) -> None:
    mods = _mods("NoModifier")
    for modifier in modifiers:
        mods = mods | _mods(modifier)
    QTest.keyClick(canvas, _qt_key(name), mods)
    _flush()


def _port(canvas: FormCanvas, root: QWidget, point: QPoint) -> QPoint:
    proxy = root.graphicsProxyWidget()
    assert proxy is not None
    return canvas.mapFromScene(proxy.mapToScene(point))


def _scroll(canvas: FormCanvas) -> Tuple[int, int]:
    return (canvas.horizontalScrollBar().value(), canvas.verticalScrollBar().value())


def _id(document: UiDocument, name: str) -> NodeId:
    matches = [node.id for node in document.iter_preorder() if getattr(node, "object_name", None) == name]
    assert len(matches) == 1
    return matches[0]


def _flush() -> None:
    app = QApplication.instance()
    assert app is not None
    app.processEvents()


def _mouse(name: str) -> Qt.MouseButton:
    return getattr(getattr(Qt, "MouseButton", Qt), name)


def _mods(name: str) -> Qt.KeyboardModifier:
    return getattr(getattr(Qt, "KeyboardModifier", Qt), name)


def _qt_key(name: str) -> Qt.Key:
    return getattr(getattr(Qt, "Key", Qt), name)
