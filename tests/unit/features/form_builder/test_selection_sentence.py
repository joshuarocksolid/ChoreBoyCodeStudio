"""Status-bar sentence for a form selection."""

from __future__ import annotations

from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.integration.chrome_text import selection_sentence

import pytest

pytestmark = pytest.mark.unit

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QWidget" name="Invoice">
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="0">
    <widget class="QLabel" name="emailLabel">
     <property name="text"><string>Email</string></property>
    </widget>
   </item>
   <item row="0" column="1">
    <widget class="QLineEdit" name="shop"/>
   </item>
   <item row="1" column="1">
    <widget class="QLineEdit" name="email"/>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

_SIZED = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QWidget" name="Invoice">
  <property name="geometry">
   <rect><x>0</x><y>0</y><width>640</width><height>480</height></rect>
  </property>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

_GROUP = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QWidget" name="Invoice">
  <widget class="QGroupBox" name="receiptGroup">
   <layout class="QHBoxLayout" name="horizontalLayout">
    <item>
     <widget class="QPushButton" name="printButton"/>
    </item>
    <item>
     <widget class="QPushButton" name="saveButton"/>
    </item>
   </layout>
  </widget>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def test_line_edit_in_a_form_layout_names_the_row() -> None:
    document = read_ui(_FORM, allocator=IdAllocator()).document
    email = document.by_name("email")[0]
    sentence = selection_sentence(document, email, 1)
    assert sentence == "email · Line edit · row 2 of the form layout"
    assert "NodeId" not in sentence


def test_several_widgets_read_as_a_count() -> None:
    document = read_ui(_FORM, allocator=IdAllocator()).document
    assert selection_sentence(document, document.by_name("email")[0], 3) == "3 selected"


def test_nothing_selected_names_the_page() -> None:
    document = read_ui(_FORM, allocator=IdAllocator()).document
    assert selection_sentence(document, None, 0) == "Invoice · the form"


def test_the_root_widget_names_the_page() -> None:
    document = read_ui(_FORM, allocator=IdAllocator()).document
    assert selection_sentence(document, document.root.id, 1) == "Invoice · the form"


def test_the_form_sentence_includes_the_page_size() -> None:
    document = read_ui(_SIZED, allocator=IdAllocator()).document
    assert selection_sentence(document, None, 0) == "Invoice · the form · 640 × 480"


def test_a_group_box_names_the_widgets_in_its_layout() -> None:
    document = read_ui(_GROUP, allocator=IdAllocator()).document
    group = document.by_name("receiptGroup")[0]
    assert (
        selection_sentence(document, group, 1)
        == "receiptGroup · Group box · 2 widgets in a horizontal layout"
    )
