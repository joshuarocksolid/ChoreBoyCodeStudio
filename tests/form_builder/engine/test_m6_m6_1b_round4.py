"""Gate repros for M6.1b round 4: names, signatures, the step filter, the pair page."""

from __future__ import annotations

from pathlib import Path

from app.features.form_builder.engine.logic.events import read_events
from app.features.form_builder.engine.query.tab_stops import display_name
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.qtside.inspector.behavior_ext._rows import unused_method_sentence
from app.features.form_builder.qtside.pickers.flow import (
    Page,
    PickContext,
    PickerSource,
    Press,
    opening,
    reduce,
)
from tests.form_builder.engine.commands._support import open_log

_SALE = Path(__file__).resolve().parents[1] / "fixtures" / "m6" / "forms" / "sale.ui"

_NAMED = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0"><class>Form</class>
<widget class="QDialog" name="Form">
 <property name="windowTitle"><string>Made in Designer</string></property>
 <widget class="QPushButton" name="saveButton"/>
 <action name="actionSave"><property name="text"><string>Save</string></property></action>
</widget>
</ui>
"""


def test_the_form_uses_its_window_title_and_an_action_uses_its_text() -> None:
    doc = open_log(_NAMED).document
    assert display_name(doc, "Form") == "Made in Designer"
    assert display_name(doc, "actionSave") == "Save"


def _ctx(doc: object, source: PickerSource, target: str = "") -> PickContext:
    return PickContext(doc, QtClassTable.shared(), source, target, (), "", "", False)  # type: ignore[arg-type]


def test_an_event_signature_is_not_written_twice() -> None:
    doc = open_log(_SALE.read_text(encoding="utf-8")).document
    page = opening(_ctx(doc, PickerSource("clearButton")))
    assert isinstance(page, Page)
    clicked = next(row for row in page.rows if row.payload == "clicked")
    assert clicked.faint.count("(") == 1
    assert "()()" not in clicked.faint


def test_a_step_filter_finds_target_names_and_keeps_the_widget_action_row() -> None:
    doc = open_log(_SALE.read_text(encoding="utf-8")).document
    ctx = _ctx(doc, PickerSource("clearButton", "clicked"))
    page = opening(ctx)
    assert isinstance(page, Page)
    for text, payload in (("name", "clear-field"), ("setFocus", "move-focus"), ("clear()", "clear-field")):
        found = reduce(ctx, page, Press("filter", text))
        assert isinstance(found, Page)
        assert any(row.payload == payload for row in found.rows), text
    missed = reduce(ctx, page, Press("filter", "zzzz-nope"))
    assert isinstance(missed, Page)
    assert any(row.kind == "widget-action" for row in missed.rows)
    assert any(row.text.startswith("Nothing matches") for row in missed.rows)


def test_a_drop_on_a_field_hides_form_intents() -> None:
    doc = open_log(_SALE.read_text(encoding="utf-8")).document
    onto_field = opening(_ctx(doc, PickerSource("clearButton", "clicked"), "nameEdit"))
    onto_form = opening(_ctx(doc, PickerSource("clearButton", "clicked"), "Sale"))
    assert isinstance(onto_field, Page) and isinstance(onto_form, Page)
    assert onto_field.kind == "pair" and onto_field.title.startswith("Then")
    assert all(row.payload != "close-form" for row in onto_field.rows)
    assert any(row.payload == "clear-field" for row in onto_field.rows)
    assert any(row.payload == "close-form" for row in onto_form.rows)


def test_deleting_an_unused_method_uses_the_spec_sentence() -> None:
    assert unused_method_sentence("print_receipt", "sale_window.py") == (
        "Removed the step. print_receipt() is still in sale_window.py. \u00b7 Undo"
    )


def test_read_events_is_cached_for_one_revision() -> None:
    doc = open_log(_SALE.read_text(encoding="utf-8")).document
    assert read_events(doc) is read_events(doc)
