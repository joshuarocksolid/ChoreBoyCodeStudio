# pyright: reportAttributeAccessIssue=false
"""Scroll area on the canvas: wheel, reveal by selection (UX-CONT-010, R3-129)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Tuple

import pytest

from app.qt.QtCore import QPoint, QPointF, Qt
from app.qt.QtGui import QWheelEvent
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QScrollArea, QWidget
from app.features.form_builder.engine.ui4.writer import write_ui
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.integration.canvas import FormCanvas
from tests.form_builder.qtside.support import form, opened

pytestmark = pytest.mark.usefixtures("qapp")

BUTTONS = "".join(
    '  <widget class="QPushButton" name="b%d"><property name="geometry"><rect><x>10</x><y>%d</y>'
    "<width>120</width><height>30</height></rect></property></widget>\n" % (index, index * 50)
    for index in range(10)
)

AREA = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>600</width><height>400</height></rect></property>
  <widget class="QScrollArea" name="scroll">
   <property name="geometry"><rect><x>20</x><y>20</y><width>300</width><height>120</height></rect></property>
   <property name="widgetResizable"><bool>false</bool></property>
   <widget class="QWidget" name="scrollAreaWidgetContents">
    <property name="geometry"><rect><x>0</x><y>0</y><width>300</width><height>560</height></rect></property>
"""
    + BUTTONS
    + """   </widget>
  </widget>
""",
)


class _Host:
    def __init__(self) -> None:
        self.sentences: list = []

    def canvas_pressed(self) -> None:
        return None

    def narrate(self, sentence: str) -> None:
        self.sentences.append(sentence)

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


def _flush() -> None:
    app = QApplication.instance()
    assert app is not None
    app.processEvents()


def _wheel(canvas: FormCanvas, point: QPoint, angle_y: int) -> None:
    event = QWheelEvent(
        QPointF(point),
        QPointF(canvas.viewport().mapToGlobal(point)),
        QPoint(0, 0),
        QPoint(0, angle_y),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(canvas.viewport(), event)
    _flush()


@contextmanager
def _canvas(text: str) -> Iterator[Tuple[FormSession, FormCanvas, _Host]]:
    host = _Host()
    with opened(text) as (session, realizer):
        parent = QWidget()
        parent.resize(640, 480)
        canvas = FormCanvas(session, realizer, host, parent)
        canvas.resize(640, 480)
        parent.show()
        canvas.setFocus()
        _flush()
        try:
            yield session, canvas, host
        finally:
            canvas.dispose()
            parent.deleteLater()


def _press_tab(canvas: FormCanvas) -> None:
    QTest.keyClick(canvas, Qt.Key.Key_Tab)
    _flush()


def _area_point(canvas: FormCanvas, name: str) -> QPoint:
    root = canvas.page_widget()
    assert root is not None
    area = root.findChild(QScrollArea, "scroll")
    assert area is not None
    return area.viewport().mapTo(canvas.viewport(), area.viewport().rect().center())


def test_wheel_over_a_scroll_area_scrolls_its_content_not_the_canvas() -> None:
    with _canvas(AREA) as (session, canvas, _host):
        root = canvas.page_widget()
        area = root.findChild(QScrollArea, "scroll")  # type: ignore[union-attr]
        before_text = write_ui(session.document).text
        canvas_before = (canvas.horizontalScrollBar().value(), canvas.verticalScrollBar().value())
        bar = area.verticalScrollBar()  # type: ignore[union-attr]
        start = bar.value()
        _wheel(canvas, _area_point(canvas, "scroll"), -120)
        assert bar.value() > start, "one notch down moves the content down"
        assert (canvas.horizontalScrollBar().value(), canvas.verticalScrollBar().value()) == canvas_before
        assert write_ui(session.document).text == before_text
        assert not session.log.is_dirty()


def test_tab_to_a_widget_below_the_fold_scrolls_the_area_to_show_it() -> None:
    with _canvas(AREA) as (session, canvas, _host):
        root = canvas.page_widget()
        area = root.findChild(QScrollArea, "scroll")  # type: ignore[union-attr]
        assert area is not None and area.verticalScrollBar().value() == 0
        ids = {getattr(n, "object_name", ""): n.id for n in session.document.iter_preorder()}
        session.selection.set((ids["b8"],), current=ids["b8"], source=SelectionSource.CANVAS)
        _flush()
        _press_tab(canvas)  # selects b9, the widget below the fold
        assert session.selection.state.current == ids["b9"]
        assert area.verticalScrollBar().value() > 0
        target = root.findChild(QWidget, "b9")  # type: ignore[union-attr]
        assert target is not None
        top_left = target.mapTo(area.viewport(), target.rect().topLeft())
        assert area.viewport().rect().contains(top_left)
        assert not session.log.is_dirty()
