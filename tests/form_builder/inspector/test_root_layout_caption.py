# pyright: reportAttributeAccessIssue=false
"""The root layout's edge caption in a narrow inspector."""

from __future__ import annotations

from typing import Tuple

import pytest

from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.qtside.inspector import InspectorPane
from app.features.form_builder.qtside.realize.api import Realizer
from app.features.form_builder.qtside.theme.chrome import chrome_from_values
from app.qt.QtWidgets import QApplication, QLabel, QScrollArea, QVBoxLayout, QWidget
from tests.form_builder.qtside.support import form, opened

pytestmark = pytest.mark.usefixtures("qapp")

_FOLLOWS = "Everything in this layout follows the window's edges."

_UI = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>420</width><height>280</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QWidget" name="column">
     <layout class="QVBoxLayout" name="columnLayout">
      <item>
       <widget class="QPushButton" name="one">
        <property name="text"><string>One</string></property>
       </widget>
      </item>
     </layout>
    </widget>
   </item>
  </layout>
""",
)

_CHROME = chrome_from_values(
    window="#f3f3f3",
    panel="#ffffff",
    text="#1f1f1f",
    muted="#5c5c5c",
    faint="#6b6b6b",
    border="#c8c8c8",
    accent="#0060c0",
    row_hover="#eef3fb",
    input_bg="#ffffff",
    error="#b00020",
    focus_width=1,
)


def _events() -> None:
    app = QApplication.instance()
    assert app is not None
    app.processEvents()


def _pane(session: FormSession, realizer: Realizer) -> Tuple[QWidget, InspectorPane]:
    window = QWidget()
    pane = InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None, parent=window)
    pane.apply_chrome(_CHROME)
    layout = QVBoxLayout(window)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(pane)
    window.resize(236, 640)
    window.show()
    _events()
    pane.flush()
    _events()
    return window, pane


def _close(window: QWidget, pane: InspectorPane) -> None:
    pane.dispose()
    window.close()
    window.deleteLater()
    _events()


def _select(session: FormSession, pane: InspectorPane, name: str) -> None:
    found = session.document.by_name(name)
    assert found, name
    session.selection.set((found[0],), source=SelectionSource.PROGRAM)
    pane.flush()
    _events()


def _caption(pane: QWidget) -> QLabel:
    found = pane.findChild(QLabel, "formBuilder.layout.followsWindow")
    assert isinstance(found, QLabel)
    return found


def _no_overlap(body: QWidget) -> None:
    for parent in [body] + body.findChildren(QWidget):
        shown = [item for item in parent.children() if isinstance(item, QWidget) and item.isVisible()]
        for index, first in enumerate(shown):
            for second in shown[index + 1 :]:
                both = first.geometry().intersected(second.geometry())
                assert both.isEmpty(), (first.objectName(), second.objectName())


def test_the_root_layout_caption_wraps_inside_a_236_px_inspector() -> None:
    with opened(_UI) as (session, realizer):
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "verticalLayout")
            caption = _caption(pane)
            scroll = pane.findChild(QScrollArea, "formBuilder.inspectorScroll")
            body = pane.findChild(QWidget, "formBuilder.layoutBody")
            assert scroll is not None and body is not None
            assert caption.isVisible()
            assert caption.text() == _FOLLOWS
            assert "#5c5c5c" in caption.styleSheet().lower()
            within = caption.width() <= scroll.viewport().width()
            wrapped = caption.height() > caption.heightForWidth(4000)
            assert wrapped or within
            assert caption.width() > 0 and caption.height() > 0
            _no_overlap(body)
            assert scroll.horizontalScrollBar().maximum() == 0
        finally:
            _close(window, pane)


def test_a_nested_layout_does_not_say_it_follows_the_window() -> None:
    with opened(_UI) as (session, realizer):
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "columnLayout")
            caption = _caption(pane)
            assert not caption.isVisible()
        finally:
            _close(window, pane)
