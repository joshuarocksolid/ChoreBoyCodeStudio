# pyright: reportAttributeAccessIssue=false
"""Spoken names and form-row pairs stay current when a later edit moves another stamp."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.commands.catalog import InsertFragment, SetProperty
from app.features.form_builder.engine.commands.placement import InFormRow
from app.features.form_builder.engine.logic.read_as_text import spoken_display
from app.features.form_builder.engine.query import tab_stops
from app.features.form_builder.engine.ui4.spec import Fragment
from app.features.form_builder.engine.ui4.values import EnumValue, StringValue
from tests.form_builder.engine.commands._support import button_spec, open_log
from tests.form_builder.engine.test_m94_caption_patch import _ROW, _clear

pytestmark = pytest.mark.unit


def test_caption_then_insert_without_read_between() -> None:
    log = open_log(_ROW)
    doc = log.document
    spoken_display(doc, "emailEdit")
    label = doc.by_name("customerLabel")[0]
    log.execute(SetProperty(label, "text", StringValue("Invoice")))
    layout = doc.by_name("formLayout")[0]
    log.execute(
        InsertFragment(
            InFormRow(layout, 1, "field", insert_row=True),
            Fragment(nodes=(button_spec("extra"),)),
        )
    )
    patched = spoken_display(doc, "emailEdit")
    _clear(doc)
    assert patched == spoken_display(doc, "emailEdit")


def test_pairs_after_focus_policy() -> None:
    log = open_log(_ROW)
    doc = log.document
    assert tab_stops.form_row_pairs(doc)
    edit = doc.by_name("emailEdit")[0]
    log.execute(SetProperty(edit, "focusPolicy", EnumValue("Qt::NoFocus")))
    cached = tab_stops.form_row_pairs(doc)
    _clear(doc)
    assert cached == tab_stops.form_row_pairs(doc)
