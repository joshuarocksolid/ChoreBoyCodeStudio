# pyright: reportAttributeAccessIssue=false
"""Why text and layout follow the realized widget, not a second copy of the numbers."""

from __future__ import annotations

from typing import Optional, Tuple

import pytest

from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.sizing import Hug, project
from app.features.form_builder.qtside.inspector import InspectorPane
from app.features.form_builder.qtside.realize import Realizer
from app.features.form_builder.qtside.sizing_live import selection_facts
from app.qt.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget
from tests.form_builder.qtside.support import form, realize

pytestmark = pytest.mark.usefixtures("qapp")

_FIXED = """
     <property name="text"><string>%s</string></property>
     <property name="sizePolicy">
      <sizepolicy hsizetype="Fixed" vsizetype="Fixed">
       <horstretch>0</horstretch>
       <verstretch>0</verstretch>
      </sizepolicy>
     </property>
"""

_BOX = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>360</width><height>200</height></rect></property>
  <layout class="QVBoxLayout" name="column">
   <item>
    <widget class="QPushButton" name="child">
%s
    </widget>
   </item>
  </layout>
"""
    % _FIXED % "Hello there",
)

_GRID = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>360</width><height>200</height></rect></property>
  <layout class="QGridLayout" name="grid">
   <item row="0" column="0">
    <widget class="QPushButton" name="child">
%s
    </widget>
   </item>
  </layout>
"""
    % _FIXED % "Hello there",
)

_FORM = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>360</width><height>200</height></rect></property>
  <layout class="QFormLayout" name="form">
   <item row="0" column="0">
    <widget class="QLabel" name="child">
%s
    </widget>
   </item>
   <item row="0" column="1">
    <widget class="QLineEdit" name="email">
     <property name="text"><string>name@example.com</string></property>
    </widget>
   </item>
  </layout>
"""
    % _FIXED % "Email address",
)

_COLUMN = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>200</width><height>120</height></rect></property>
  <layout class="QVBoxLayout" name="column" stretch="0,1">
   <item>
    <widget class="QPushButton" name="stay">
     <property name="text"><string>Stay</string></property>
     <property name="sizePolicy">
      <sizepolicy hsizetype="Fixed" vsizetype="Fixed">
       <horstretch>0</horstretch>
       <verstretch>0</verstretch>
      </sizepolicy>
     </property>
    </widget>
   </item>
   <item>
    <widget class="QPushButton" name="grow">
     <property name="text"><string>Grow</string></property>
     <property name="sizePolicy">
      <sizepolicy hsizetype="Expanding" vsizetype="Fixed">
       <horstretch>0</horstretch>
       <verstretch>0</verstretch>
      </sizepolicy>
     </property>
    </widget>
   </item>
  </layout>
""",
)


@pytest.mark.parametrize("text", (_BOX, _GRID, _FORM), ids=("box", "grid", "form"))
def test_why_text_reads_the_realized_child(text: str) -> None:
    session, realizer = realize(text)
    window: Optional[QWidget] = None
    pane: Optional[InspectorPane] = None
    try:
        root = realizer.root_widget
        assert root is not None
        _show(root, 480, 260)
        window, pane = _inspector(session, realizer)
        child_id = _id(session, "child")
        session.selection.set((child_id,), source=SelectionSource.PROGRAM)
        pane.flush()
        _pump()
        widget = realizer.widget_for(child_id)
        assert widget is not None
        panel = project(selection_facts(session.document, (child_id,), realizer))
        why = pane.findChild(QLabel, "formBuilder.sizeWhy")
        assert why is not None
        lines = why.text().splitlines()
        assert lines[0] == "%s \u00d7 %s px." % (widget.width(), widget.height())
        assert widget.width() > 0
        assert widget.height() > 0
        assert isinstance(panel.horizontal.mode, Hug)
        assert isinstance(panel.vertical.mode, Hug)
        assert widget.sizeHint().width() > 0
        assert widget.sizeHint().height() > 0
        body = "\n".join(lines)
        assert "needs for its content: %s px." % widget.sizeHint().width() in body
        assert "needs for its content: %s px." % widget.sizeHint().height() in body
    finally:
        _close(window, pane, realizer, session)


def test_a_fill_button_in_a_column_takes_the_extra_width() -> None:
    session, realizer = realize(_COLUMN)
    try:
        root = realizer.root_widget
        assert root is not None
        _show(root, 480, 200)
        stay = root.findChild(QWidget, "stay")
        grow = root.findChild(QWidget, "grow")
        assert stay is not None and grow is not None
        layout = root.layout()
        assert layout is not None
        layout.activate()
        assert abs(stay.width() - stay.sizeHint().width()) <= 4
        assert grow.width() > stay.width()
        assert grow.width() > grow.sizeHint().width()
    finally:
        realizer.dispose()
        session.dispose()


def _inspector(session: FormSession, realizer: Realizer) -> Tuple[QWidget, InspectorPane]:
    window = QWidget()
    pane = InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None, parent=window)
    layout = QVBoxLayout(window)
    layout.addWidget(pane)
    window.resize(980, 860)
    window.show()
    app = QApplication.instance()
    if isinstance(app, QApplication):
        app.setActiveWindow(window)
    pane.flush()
    _pump()
    return window, pane


def _show(root: QWidget, width: int, height: int) -> None:
    root.resize(width, height)
    root.show()
    _pump()
    layout = root.layout()
    if layout is not None:
        layout.activate()
    _pump()


def _id(session: FormSession, name: str) -> object:
    found = session.document.by_name(name)
    assert len(found) == 1
    return found[0]


def _pump() -> None:
    app = QApplication.instance()
    assert app is not None
    for _ in range(4):
        app.processEvents()


def _close(
    window: Optional[QWidget],
    pane: Optional[InspectorPane],
    realizer: Realizer,
    session: FormSession,
) -> None:
    if pane is not None:
        pane.dispose()
    realizer.dispose()
    session.dispose()
    if window is not None:
        window.close()
