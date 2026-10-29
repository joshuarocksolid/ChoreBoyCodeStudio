# pyright: reportAttributeAccessIssue=false
"""Refusal captions on the canvas, and raising the MDI window that holds the selection."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.features.form_builder.engine.commands.catalog import SetProperty
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.engine.ui4.writer import write_ui
from app.features.form_builder.qtside.canvas.core.frame import Caption
from app.qt.QtWidgets import QApplication, QMdiArea
from app.shell.theme_tokens import tokens_from_palette
from tests.form_builder.qtside.support import form, opened
from tests.form_builder.qtside.test_m4_mdi import _canvas
from tests.form_builder.qtside.test_m4_scroll_area import _flush

pytestmark = pytest.mark.usefixtures("qapp")

REFUSAL = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>480</width><height>320</height></rect></property>
  <widget class="QSpinBox" name="count">
   <property name="geometry"><rect><x>40</x><y>48</y><width>240</width><height>64</height></rect></property>
  </widget>
""",
)

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
    <property name="geometry"><rect><x>0</x><y>0</y><width>220</width><height>140</height></rect></property>
    <widget class="QPushButton" name="add">
     <property name="text"><string>Add</string></property>
     <property name="geometry"><rect><x>16</x><y>24</y><width>80</width><height>28</height></rect></property>
    </widget>
   </widget>
  </widget>
""",
)


def test_a_refused_value_paints_a_caption_on_the_widget(qapp: QApplication) -> None:
    with _canvas(REFUSAL) as (session, canvas, _host):
        count = session.document.by_name("count")[0]
        session.log.execute(SetProperty(count, "minimum", StringValue("lots")))
        _flush()
        captions = [
            item
            for item in canvas.overlay().items
            if isinstance(item, Caption) and item.role == "problem"
        ]
        assert [item.lines for item in captions] == [("Qt refused this value.",)]
        raw = os.environ.get("CBCS_FB_SCREENSHOT_DIR") or ""
        if not raw:
            return
        folder = Path(raw)
        folder.mkdir(parents=True, exist_ok=True)
        for mode in ("light", "high_contrast_dark"):
            canvas.apply_theme(tokens_from_palette(qapp.palette(), force_mode=mode))
            _flush()
            canvas.grab().save(str(folder / ("refusal-caption-%s.png" % mode)))


@pytest.mark.parametrize("source", [SelectionSource.CANVAS, SelectionSource.OUTLINE, SelectionSource.INSPECTOR])
def test_selecting_a_widget_raises_its_mdi_window(source: SelectionSource) -> None:
    with _canvas(MDI) as (session, canvas, _host):
        root = canvas.page_widget()
        assert root is not None
        area = root.findChild(QMdiArea, "mdi")
        assert area is not None
        windows = area.subWindowList()
        notes = next(window for window in windows if window.widget() is not None and window.widget().objectName() == "notes")
        area.setActiveSubWindow(notes)
        _flush()
        before = write_ui(session.document).text
        assert not session.log.can_undo()
        button = session.document.by_name("add")[0]
        session.selection.set((button,), current=button, source=source)
        _flush()
        active = area.activeSubWindow()
        assert active is not None and active.widget() is not None
        assert active.widget().objectName() == "todo"
        assert write_ui(session.document).text == before
        assert not session.log.can_undo()
