# pyright: reportAttributeAccessIssue=false
"""A caption edit's patched snapshot matches a snapshot built from scratch."""

from __future__ import annotations

from app.features.form_builder.engine.commands.catalog import InsertFragment, SetProperty
from app.features.form_builder.engine.commands.placement import InFormRow
from app.features.form_builder.engine.ui4.spec import Fragment, NodeSpec, PropertyEntry
from app.features.form_builder.engine.ui4.values import CStringValue
from app.features.form_builder.engine.logic import formula_env, read_as_text
from app.features.form_builder.engine.logic.formula_env import env_for
from app.features.form_builder.engine.logic.read_as_text import spoken_display
from app.features.form_builder.engine.query import tab_stops
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.values import StringValue
from tests.form_builder.engine.commands._support import button_spec
from tests.form_builder.engine.commands._support import open_log

import pytest

pytestmark = pytest.mark.unit

_BUDDY = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0"><class>Alpha</class>
<widget class="QDialog" name="Alpha">
 <widget class="QLabel" name="customerLabel">
  <property name="text"><string>Customer</string></property>
  <property name="buddy"><cstring>emailEdit</cstring></property>
 </widget>
 <widget class="QLineEdit" name="emailEdit"/>
</widget></ui>
"""

_ROW = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0"><class>Alpha</class>
<widget class="QWidget" name="Alpha">
 <layout class="QFormLayout" name="formLayout">
  <item row="0" column="0">
   <widget class="QLabel" name="customerLabel">
    <property name="text"><string>Customer</string></property>
   </widget>
  </item>
  <item row="0" column="1"><widget class="QLineEdit" name="emailEdit"/></item>
 </layout>
</widget></ui>
"""


def _clear(document: UiDocument) -> None:
    formula_env._ENV.pop(document, None)
    read_as_text._PREFERRED.pop(document, None)
    tab_stops._NAMES.pop(document, None)
    tab_stops._BUDDIES.pop(document, None)
    tab_stops._PAIRS.pop(document, None)
    tab_stops._LABELS.pop(document, None)


def _displays(document: UiDocument) -> dict:
    env = env_for(document, None, QtClassTable.shared())
    return {name: facts.display for name, facts in env.widgets.items()}


def _spoken(document: UiDocument) -> dict:
    return {name: spoken_display(document, name) for name in ("customerLabel", "emailEdit")}


@pytest.mark.parametrize("xml", [_BUDDY, _ROW])
@pytest.mark.parametrize("caption", ["Invoice", "Name:", ""])
def test_caption_edit_matches_a_full_snapshot_rebuild(xml: str, caption: str) -> None:
    log = open_log(xml)
    document = log.document
    _displays(document)
    _spoken(document)
    label = document.by_name("customerLabel")[0]
    log.execute(SetProperty(label, "text", StringValue(caption)))
    log.execute(SetProperty(label, "text", StringValue(caption + " two" if caption else "Again")))
    patched_displays = _displays(document)
    patched_spoken = _spoken(document)
    _clear(document)
    assert _displays(document) == patched_displays
    assert _spoken(document) == patched_spoken


def test_inserted_label_matches_a_full_snapshot_rebuild() -> None:
    log = open_log(_ROW)
    document = log.document
    _displays(document)
    _spoken(document)
    layout = document.by_name("formLayout")[0]
    label = NodeSpec(
        "widget",
        None,
        (("class_name", "QLabel"), ("object_name", "extraLabel")),
        (
            PropertyEntry("property", "text", StringValue("Customer")),
            PropertyEntry("property", "buddy", CStringValue("emailEdit")),
        ),
    )
    log.execute(
        InsertFragment(InFormRow(layout, 0, "label", insert_row=True), Fragment(nodes=(label,)))
    )
    log.execute(
        InsertFragment(
            InFormRow(layout, 1, "field", insert_row=True),
            Fragment(nodes=(button_spec("extra"),)),
        )
    )
    patched_displays = _displays(document)
    patched_spoken = {
        name: spoken_display(document, name)
        for name in ("customerLabel", "emailEdit", "extraLabel", "extra")
    }
    _clear(document)
    assert _displays(document) == patched_displays
    assert {
        name: spoken_display(document, name)
        for name in ("customerLabel", "emailEdit", "extraLabel", "extra")
    } == patched_spoken
