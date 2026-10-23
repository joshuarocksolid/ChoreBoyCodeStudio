"""XML view can ask which lines the builder kept as written."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.engine.ui4.writer import kept_as_is_line_spans, write_ui

pytestmark = pytest.mark.unit

_UI = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="geometry">
   <rect>
    <x>0</x>
    <y>0</y>
    <width>100</width>
    <height>40</height>
    <zzunk n="sizehint"/>
   </rect>
  </property>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def test_opaque_nodes_report_the_lines_that_contain_them() -> None:
    document = read_ui(_UI, allocator=IdAllocator()).document
    result = write_ui(document)
    spans = kept_as_is_line_spans(result)
    assert spans
    lines = result.text.splitlines()
    marked = []
    for start, end in spans:
        marked.extend(lines[start - 1 : end])
    assert any("zzunk" in line for line in marked)
