"""XML view can ask which lines the builder kept as written."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.ui4.reader import kept_as_is_spans, read_ui
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


_MIXED = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QWidget" name="Invoice">
  <widget class="QLabel" name="title">
   <property name="text"><string>Invoice entry</string></property>
  </widget>
  <widget class="QLabel" name="shopName">
   <property name="text"><string>a<b>x</b>c</string></property>
  </widget>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

# The same form, not as the writer would lay it out: blank lines, one-line
# widgets, and the mixed string split over three lines.
_NON_CANONICAL = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">

<class>Invoice</class>
<widget class="QWidget" name="Invoice">

    <widget class="QLabel" name="title"><property name="text"><string>Invoice entry</string></property></widget>


    <widget class="QLabel" name="shopName">
      <property name="text">
        <string>a<b>x</b>
        c</string>
      </property>
    </widget>
</widget>
<resources/>
<connections/>
</ui>
"""


def _line_of(text: str, needle: str) -> int:
    for number, line in enumerate(text.splitlines(), start=1):
        if needle in line:
            return number
    raise AssertionError(needle)


def test_kept_note_marks_the_opaque_string_and_not_the_plain_one_before_it() -> None:
    spans = kept_as_is_spans(_MIXED)
    assert [start for start, _end in spans] == [_line_of(_MIXED, "a<b>x</b>c")]


def test_kept_note_follows_a_non_canonical_file() -> None:
    spans = kept_as_is_spans(_NON_CANONICAL)
    start = _line_of(_NON_CANONICAL, "<string>a<b>")
    assert spans == ((start, start + 1),)


def test_kept_notes_follow_the_writer_output_for_the_same_document() -> None:
    document = read_ui(_NON_CANONICAL, allocator=IdAllocator()).document
    written = write_ui(document)
    spans = kept_as_is_spans(written.text)
    assert [start for start, _end in spans] == [start for start, _end in written.opaque_spans]
    assert len(spans) == 1
    assert "<string>a" in written.text.splitlines()[spans[0][0] - 1]
