"""Pasted widget counts leave out tab, stack, and toolbox pages."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.clipboard import pasted_widget_count, selection_fragment
from tests.form_builder.engine.commands._support import nid, open_log

pytestmark = pytest.mark.unit

_HOST = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QWidget" name="Invoice">
  <widget class="%s" name="pages">
   <widget class="QWidget" name="one">
    <attribute name="title"><string>One</string></attribute>
    <layout class="QVBoxLayout" name="oneLayout">
     <item>
      <widget class="QLineEdit" name="customer"/>
     </item>
    </layout>
   </widget>
   <widget class="QWidget" name="two">
    <attribute name="title"><string>Two</string></attribute>
   </widget>
  </widget>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


@pytest.mark.parametrize("host", ("QTabWidget", "QStackedWidget", "QToolBox"))
def test_pages_are_left_out_of_the_pasted_widget_count(host: str) -> None:
    log = open_log(_HOST % host)
    fragment = selection_fragment(log.document, (nid(log.document, "pages"),))
    assert pasted_widget_count(fragment) == 2
