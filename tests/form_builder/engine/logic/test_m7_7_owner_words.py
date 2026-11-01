"""Owner-facing names: a form-row caption, and a check with no label."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.logic.checks import Required, RuntimeCheck, plan
from app.features.form_builder.engine.logic.formula_env import env_for
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.reader import read_ui

pytestmark = pytest.mark.unit

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="0">
    <widget class="QLabel" name="qtyLabel">
     <property name="text"><string>Qty</string></property>
    </widget>
   </item>
   <item row="0" column="1">
    <widget class="QSpinBox" name="qtySpin"/>
   </item>
  </layout>
 </widget>
</ui>
"""


_EMPTY = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="0">
    <widget class="QLabel" name="lineTotalLabel"/>
   </item>
   <item row="0" column="1">
    <widget class="QLineEdit" name="emailEdit"/>
   </item>
  </layout>
 </widget>
</ui>
"""


def test_empty_form_row_label_does_not_rename_the_field() -> None:
    doc = read_ui(_EMPTY, allocator=IdAllocator()).document
    env = env_for(doc, None, QtClassTable.shared())
    assert env.widgets["emailEdit"].display == "emailEdit"


def test_form_row_caption_names_the_field() -> None:
    doc = read_ui(_FORM, allocator=IdAllocator()).document
    env = env_for(doc, None, QtClassTable.shared())
    assert env.widgets["qtySpin"].display == "Qty"


def test_unlabeled_required_message_uses_words() -> None:
    field = plan("QLineEdit", (Required(None),), label="emailEdit", object_name="emailEdit")
    messages = [arm.message for arm in field.runtime if isinstance(arm, RuntimeCheck)]
    assert any("Email is required" in message for message in messages), messages
