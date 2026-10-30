"""Gate repros for M6.1b round 2: clauses, names, outline order, FB406, slots back."""

from __future__ import annotations

import re

from app.features.form_builder.engine.diagnostic_codes.fb406 import name_diagnostics
from app.features.form_builder.engine.diagnostics import Severity
from app.features.form_builder.engine.logic import compat
from app.features.form_builder.engine.logic.events_catalog import catalog_signals, event_clause
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.qtside.inspector.behavior_ext._rows import (
    Gesture,
    finish,
    outline_names,
)
from app.features.form_builder.qtside.pickers.flow import (
    Commit,
    Page,
    PickContext,
    PickerSource,
    Press,
    opening,
    reduce,
)
from tests.form_builder.engine.commands._support import open_log

_TILL = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="TillDisplay" name="till"/></item>
   <item><widget class="QPushButton" name="okButton"/></item>
   <item><widget class="QLineEdit" name="bad-name"/></item>
  </layout>
 </widget>
 <customwidgets>
  <customwidget>
   <class>TillDisplay</class>
   <extends>QLabel</extends>
   <header>widgets.till_display</header>
   <slots>
    <signal>total-changed(int)</signal>
    <slot>reset now()</slot>
    <slot>setTotal(int)</slot>
   </slots>
  </customwidget>
 </customwidgets>
 <resources/>
 <connections/>
</ui>
"""

_GAUGES = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>MainWindow</class>
 <widget class="QMainWindow" name="MainWindow">
  <widget class="QWidget" name="centralwidget">
   <layout class="QVBoxLayout" name="verticalLayout">
    <item><widget class="QSlider" name="amount"/></item>
    <item><widget class="QLCDNumber" name="lcd"/></item>
    <item><widget class="QLabel" name="caption"><property name="text"><string>Total</string></property></widget></item>
    <item><widget class="QProgressBar" name="progress"/></item>
   </layout>
  </widget>
  <action name="actionSave"><property name="text"><string>Save</string></property></action>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

_BAD_NATIVE = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QPushButton" name="okButton"/></item>
  </layout>
 </widget>
 <resources/>
 <connections>
  <connection>
   <sender>okButton</sender>
   <signal>clicked()</signal>
   <receiver>bad-name</receiver>
   <slot>clear()</slot>
  </connection>
 </connections>
</ui>
"""


def _ctx(doc, source, methods=()):
    return PickContext(doc, QtClassTable.shared(), source, "", methods, "w.py", "W", False)


def _enter_kind(ctx: PickContext, page: object, kind: str) -> Page:
    assert isinstance(page, Page)
    current = page
    for _ in range(len(current.rows) + 1):
        item = current.rows[current.current] if current.rows else None
        if item is not None and item.kind == kind and item.enabled:
            nxt = reduce(ctx, current, Press("enter"))
            assert isinstance(nxt, Page)
            return nxt
        moved = reduce(ctx, current, Press("down"))
        assert isinstance(moved, Page)
        current = moved
    raise AssertionError("%s not current in %s" % (kind, [row.kind for row in current.rows]))


def test_every_catalog_clause_is_one_sentence() -> None:
    for signal, chain in catalog_signals():
        sentence = "When %s." % event_clause(signal, chain, "Name")
        assert sentence.endswith("."), sentence
        assert re.search(r"\bis\b.+\bis\b", sentence) is None, sentence
    assert event_clause("toggled", (), "Name") == "Name is checked or unchecked"
    assert event_clause("editingFinished", (), "Name") == "you finish editing Name"
    assert event_clause("textEdited", (), "Name") == "the text is typed in Name"
    assert event_clause("itemActivated", (), "Name") == "an item in Name is opened"
    assert event_clause("activated", ("QComboBox",), "Name") == "a choice is picked in Name"
    assert event_clause("clicked", ("QDialogButtonBox",), "Name") == "a button in Name is clicked"


def test_outline_lists_labels_gauges_and_actions() -> None:
    doc = open_log(_GAUGES).document
    names = outline_names(doc)
    for name in ("lcd", "caption", "progress", "actionSave", "amount"):
        assert name in names, names
    ctx = _ctx(doc, PickerSource("amount", "valueChanged"))
    page = opening(ctx)
    page = reduce(ctx, page, Press("filter", "own action"))
    page = _enter_kind(ctx, page, "widget-action")
    assert isinstance(page, Page)
    offered = [row.payload for row in page.rows if row.kind == "target"]
    for name in ("lcd", "caption", "progress", "actionSave"):
        assert name in offered, offered
    lcd = reduce(ctx, page, Press("filter", "lcd"))
    lcd = _enter_kind(ctx, lcd, "target")
    assert isinstance(lcd, Page)
    slots = [row.payload for row in lcd.rows if row.kind == "slot"]
    assert any(slot.startswith("display(") for slot in slots), slots


def test_picker_offers_only_usable_names() -> None:
    doc = open_log(_TILL).document
    events = opening(_ctx(doc, PickerSource("till")))
    offered = [row.payload for row in events.rows if row.kind == "event"]
    assert "total-changed" not in offered
    assert all(compat.is_name(name) for name in offered)
    steps = opening(_ctx(doc, PickerSource("okButton", "clicked"), ("café", "print_receipt", "class")))
    methods = [row.payload for row in steps.rows if row.kind == "method"]
    assert methods == ["print_receipt"]
    ctx = ctx_of(doc)
    targets = reduce(ctx, steps, Press("filter", "own action"))
    targets = _enter_kind(ctx, targets, "widget-action")
    assert isinstance(targets, Page)
    assert all(compat.is_name(row.payload) for row in targets.rows if row.kind == "target")
    assert "bad-name" not in [row.payload for row in targets.rows]
    slots = reduce(ctx, targets, Press("filter", "till"))
    slots = _enter_kind(ctx, slots, "target")
    assert isinstance(slots, Page)
    assert all(compat.is_signature(row.payload) for row in slots.rows if row.kind == "slot")
    assert "reset now()" not in [row.payload for row in slots.rows]


def ctx_of(doc):
    return _ctx(doc, PickerSource("okButton", "clicked"), ("café", "print_receipt", "class"))


def test_back_from_slots_keeps_the_page_marker() -> None:
    doc = open_log(_TILL).document
    ctx = _ctx(doc, PickerSource("okButton", "clicked"))
    page = opening(ctx)
    page = reduce(ctx, page, Press("filter", "own action"))
    page = _enter_kind(ctx, page, "widget-action")
    assert isinstance(page, Page) and page.kind == "target"
    page = reduce(ctx, page, Press("filter", "till"))
    slots = _enter_kind(ctx, page, "target")
    assert isinstance(slots, Page) and slots.kind == "slots"
    back = reduce(ctx, slots, Press("esc"))
    assert isinstance(back, Page) and back.kind == "target" and back.intent_id == "slots"
    again = reduce(ctx, back, Press("enter"))
    assert isinstance(again, Page) and again.kind == "slots"
    assert not isinstance(again, Commit)


def test_bad_native_name_is_fb406() -> None:
    doc = open_log(_BAD_NATIVE).document
    found = name_diagnostics(doc)
    assert len(found) == 1
    assert found[0].code == "FB406"
    assert found[0].severity == Severity.ERROR
    assert "bad-name" in found[0].message
    assert "can't use" in found[0].message


def test_replacing_a_step_with_itself_writes_nothing() -> None:
    form = _TILL.replace(
        "</widget>\n <customwidgets>",
        '<property name="cbcsOnClicked" stdset="0"><string>'
        '[{"do": "slot", "target": "till", "slot": "setTotal(int)"}]</string></property></widget>\n <customwidgets>',
        1,
    )
    # The button is okButton; attach the list there by a simpler document.
    plain = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QLineEdit" name="nameEdit"/></item>
   <item><widget class="QPushButton" name="okButton">
    <property name="cbcsOnClicked" stdset="0"><string>[{"do": "slot", "target": "nameEdit", "slot": "clear()"}]</string></property>
   </widget></item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""
    doc = open_log(plain).document
    outcome = finish(
        doc,
        QtClassTable.shared(),
        "okButton",
        Gesture("replace_slot", "clicked", 0, target="nameEdit", slot="clear()"),
    )
    assert outcome is None
    del form
