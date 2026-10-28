# pyright: reportAttributeAccessIssue=false
"""MDI area on the canvas: windows, show next and previous, tile and cascade (UX-CONT-011)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Tuple

import pytest

from app.qt.QtWidgets import QApplication, QMdiArea, QWidget
from app.features.form_builder.engine.query.pages import innermost_container
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.ui4.writer import write_ui
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.integration.canvas import FormCanvas
from tests.form_builder.qtside.support import form, opened
from app.qt.QtTest import QTest
from app.qt.QtCore import Qt
from tests.form_builder.qtside.test_m4_scroll_area import _Host, _flush

pytestmark = pytest.mark.usefixtures("qapp")

MDI = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>600</width><height>400</height></rect></property>
  <widget class="QMdiArea" name="mdi">
   <property name="geometry"><rect><x>20</x><y>20</y><width>500</width><height>300</height></rect></property>
   <widget class="QWidget" name="notes">
    <property name="windowTitle"><string>Notes</string></property>
    <property name="geometry"><rect><x>0</x><y>0</y><width>200</width><height>120</height></rect></property>
   </widget>
   <widget class="QWidget" name="todo">
    <property name="windowTitle"><string>Todo</string></property>
    <property name="geometry"><rect><x>0</x><y>0</y><width>200</width><height>120</height></rect></property>
   </widget>
  </widget>
""",
)


@contextmanager
def _canvas(text: str) -> Iterator[Tuple[FormSession, FormCanvas, object]]:
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


def test_tile_and_cascade_arrange_the_windows_on_the_canvas_only() -> None:
    with _canvas(MDI) as (session, canvas, _host):
        area_id = session.document.by_name("mdi")[0]
        root = canvas.page_widget()
        area = root.findChild(QMdiArea, "mdi")  # type: ignore[union-attr]
        assert area is not None and len(area.subWindowList()) == 2
        before = write_ui(session.document).text
        canvas._controller.tile_windows(area_id)
        _flush()
        tiled = sorted((sub.x(), sub.y()) for sub in area.subWindowList())
        assert tiled[0] != tiled[1]
        canvas._controller.cascade_windows(area_id)
        _flush()
        cascaded = sorted((sub.x(), sub.y()) for sub in area.subWindowList())
        assert cascaded[0] != cascaded[1] and cascaded != tiled
        assert write_ui(session.document).text == before
        assert not session.log.is_dirty()


def test_ctrl_page_down_shows_the_next_window_and_the_file_stays_the_same() -> None:
    with _canvas(MDI) as (session, canvas, _host):
        area_id = session.document.by_name("mdi")[0]
        root = canvas.page_widget()
        area = root.findChild(QMdiArea, "mdi")  # type: ignore[union-attr]
        windows = area.subWindowList()
        area.setActiveSubWindow(windows[0])
        _flush()
        notes = session.document.by_name("notes")[0]
        session.selection.set((notes,), current=notes, source=SelectionSource.CANVAS)
        _flush()
        assert innermost_container(session.document, notes) == area_id
        before = write_ui(session.document).text
        QTest.keyClick(canvas, Qt.Key.Key_PageDown, Qt.KeyboardModifier.ControlModifier)
        _flush()
        assert area.activeSubWindow() is windows[1]
        assert write_ui(session.document).text == before
        assert not session.log.is_dirty()
