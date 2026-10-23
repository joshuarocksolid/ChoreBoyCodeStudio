"""kept_spans reports the line ranges the XML gutter marks."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.ui4.kept import kept_spans

pytestmark = pytest.mark.unit


def _line(text: str, needle: str, nth: int = 0) -> int:
    hits = [index for index, line in enumerate(text.splitlines(), start=1) if needle in line]
    return hits[nth]


def test_nested_kept_spans_merge_into_one_range() -> None:
    text = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form"/>
 <customwidgets>
  <customwidget zz="1"><sizehint>
   <width>1</width>
   <zzunk/>
  </sizehint>
  </customwidget>
 </customwidgets>
</ui>
"""
    spans = kept_spans(text)
    assert len(spans) == 1
    span = spans[0]
    assert span.first_line == _line(text, '<customwidget zz="1">')
    assert span.last_line == _line(text, "</sizehint>")
    assert span.reasons == "Kept attributes on <customwidget>.\nKept <sizehint> as written."


def test_adjacent_kept_spans_merge() -> None:
    text = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <zzunk/>
  <yyunk/>
 </widget>
</ui>
"""
    spans = kept_spans(text)
    assert len(spans) == 1
    span = spans[0]
    assert (span.first_line, span.last_line) == (_line(text, "<zzunk/>"), _line(text, "<yyunk/>"))
    assert span.reasons == "Kept the unknown element <zzunk>.\nKept the unknown element <yyunk>."


def test_a_gap_keeps_kept_spans_separate() -> None:
    text = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <zzunk/>

  <yyunk/>
 </widget>
</ui>
"""
    spans = kept_spans(text)
    assert len(spans) == 2
    assert spans[0].last_line + 1 < spans[1].first_line
    assert spans[0].reasons == "Kept the unknown element <zzunk>."
    assert spans[1].reasons == "Kept the unknown element <yyunk>."


def test_unparseable_text_has_no_kept_spans() -> None:
    assert kept_spans("<ui>") == ()


def test_duplicate_property_marks_the_earlier_copy() -> None:
    text = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="windowTitle">
   <string>First</string>
  </property>
  <property name="windowTitle">
   <string>Last</string>
  </property>
 </widget>
</ui>
"""
    spans = kept_spans(text)
    assert len(spans) == 1
    span = spans[0]
    assert span.first_line == _line(text, '<property name="windowTitle">')
    assert span.last_line == _line(text, "</property>")
    assert span.last_line < _line(text, "<string>Last</string>")
    assert span.reasons == 'Property "windowTitle" is set more than once. The last value is the one that is used.'


def test_unknown_element_marks_its_own_lines() -> None:
    text = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <zzunk>
   <inner/>
  </zzunk>
 </widget>
</ui>
"""
    spans = kept_spans(text)
    assert len(spans) == 1
    span = spans[0]
    assert span.first_line == _line(text, "<zzunk>")
    assert span.last_line == _line(text, "</zzunk>")
    assert span.reasons == "Kept the unknown element <zzunk>."


def test_unparsed_value_spans_its_element() -> None:
    text = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="windowIcon">
   <sparkle>
    <inner>1</inner>
   </sparkle>
  </property>
 </widget>
</ui>
"""
    spans = kept_spans(text)
    assert len(spans) == 1
    span = spans[0]
    assert span.first_line == _line(text, "<sparkle>")
    assert span.last_line == _line(text, "</sparkle>")
    assert span.reasons == "Kept this <sparkle> value as written."
