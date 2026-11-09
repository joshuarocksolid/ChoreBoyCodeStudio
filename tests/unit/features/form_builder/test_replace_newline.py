"""ReplaceDocument keeps the file's newline through undo."""

from __future__ import annotations

from typing import Literal, cast

import pytest

from app.features.form_builder.engine.commands.catalog import ReplaceDocument
from app.features.form_builder.engine.project.forms import classify_form
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.writer import write_ui

pytestmark = pytest.mark.unit

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="geometry">
   <rect>
    <x>0</x>
    <y>0</y>
    <width>640</width>
    <height>480</height>
   </rect>
  </property>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


@pytest.mark.parametrize("reason", ["xml_edit", "draft", "reload"])
def test_crlf_survives_replace_and_undo(reason: str) -> None:
    text = _FORM.replace("\n", "\r\n")
    session = FormSession.open(
        text,
        path="/tmp/invoice.ui",
        scope=classify_form("/tmp/invoice.ui", project_root=None),
    )
    edited = text.replace('name="Form"', 'name="Invoice"', 1)
    session.log.execute(ReplaceDocument(edited, reason=cast(Literal["xml_edit", "draft", "reload"], reason)))

    assert session.document.newline == "\r\n"
    assert "\r\n" in write_ui(session.document).text
    assert "\n" not in write_ui(session.document).text.replace("\r\n", "")

    assert session.log.undo() is True
    assert session.document.newline == "\r\n"
    assert 'name="Form"' in write_ui(session.document).text
    assert "\r\n" in write_ui(session.document).text
    session.dispose()
