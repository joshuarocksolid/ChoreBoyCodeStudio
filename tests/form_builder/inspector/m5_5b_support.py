# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""Shared set-up for the M5.5b form-settings tests. Not collected."""

from __future__ import annotations

from typing import Tuple

from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.qtside.inspector import InspectorPane
from app.features.form_builder.qtside.realize import Realizer
from app.qt.QtWidgets import QApplication, QVBoxLayout, QWidget
from tests.form_builder.inspector.test_m43c_pictures import _CHROME
from tests.form_builder.qtside.support import realize

HEAD = '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0"%s>\n'

LAID_OUT = (
    HEAD % ""
    + """ <class>Till</class>
 <widget class="QWidget" name="Till">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QLabel" name="title"/>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""
)


def free_form(attrs: str = "", extra: str = "") -> str:
    """A form with a group box that has no layout and two widgets placed freely."""
    return (
        HEAD % attrs
        + """ <class>Till</class>
 <widget class="QWidget" name="Till">
  <property name="geometry">
   <rect><x>0</x><y>0</y><width>480</width><height>320</height></rect>
  </property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QGroupBox" name="receipt">
     <property name="minimumSize">
      <size><width>240</width><height>160</height></size>
     </property>
     <widget class="QPushButton" name="payButton">
      <property name="geometry">
       <rect><x>16</x><y>24</y><width>80</width><height>24</height></rect>
      </property>
     </widget>
     <widget class="QLabel" name="total">
      <property name="geometry">
       <rect><x>16</x><y>64</y><width>80</width><height>24</height></rect>
      </property>
     </widget>
    </widget>
   </item>
  </layout>
 </widget>
"""
        + extra
        + """ <resources/>
 <connections/>
</ui>
"""
    )


def open_pane(qapp: QApplication, text: str, width: int = 360) -> Tuple[QWidget, InspectorPane, FormSession, Realizer]:
    session, realizer = realize(text)
    window = QWidget()
    pane = InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None, parent=window)
    pane.apply_chrome(_CHROME)
    layout = QVBoxLayout(window)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(pane)
    window.resize(width, 900)
    window.show()
    qapp.setActiveWindow(window)
    qapp.processEvents()
    pane.flush()
    return window, pane, session, realizer


def close(window: QWidget, pane: InspectorPane, realizer: Realizer, session: FormSession, qapp: QApplication) -> None:
    pane.dispose()
    realizer.dispose()
    session.dispose()
    window.close()
    qapp.processEvents()
