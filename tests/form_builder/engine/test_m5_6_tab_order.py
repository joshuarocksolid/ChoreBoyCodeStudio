"""Tab-stop splicing and buddy writes (UX-OVL-005 .. 008, UX-MODE-002 .. 004), the O-logic gate of M5.6."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.commands.catalog import InsertFragment
from app.features.form_builder.engine.commands.catalog_ext.tab_order import ChangeTabOrder, PairLabels, SetLabelBuddy
from app.features.form_builder.engine.commands.placement import InBoxLayout
from app.features.form_builder.engine.query import tab_stops as q
from app.features.form_builder.engine.query.tree import effective_tab_order, reading_order
from app.features.form_builder.engine.ui4.spec import Fragment
from tests.form_builder.engine.commands._support import button_spec, nid, open_log, saved

pytestmark = pytest.mark.unit

FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QLineEdit" name="nameEdit"/></item>
   <item><widget class="QLineEdit" name="phoneEdit"/></item>
   <item><widget class="QLineEdit" name="emailEdit"/></item>
  </layout>
 </widget>
 <tabstops>
  <tabstop>emailEdit</tabstop>
  <tabstop>nameEdit</tabstop>
  <tabstop>phoneEdit</tabstop>
 </tabstops>
 <resources/>
 <connections/>
</ui>
"""

ROWS = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="0"><widget class="QLabel" name="nameLabel"><property name="text"><string>&amp;Name:</string></property></widget></item>
   <item row="0" column="1"><widget class="QLineEdit" name="nameEdit"/></item>
   <item row="1" column="0"><widget class="QLabel" name="emailLabel"><property name="text"><string>Email</string></property><property name="buddy"><cstring>phoneEdit</cstring></property></widget></item>
   <item row="1" column="1"><widget class="QLineEdit" name="emailEdit"/></item>
   <item row="2" column="0"><widget class="QLabel" name="phoneLabel"><property name="text"><string>Phone</string></property></widget></item>
   <item row="2" column="1"><widget class="QLineEdit" name="phoneEdit"/></item>
   <item row="3" column="0" colspan="2"><widget class="QLabel" name="note"><property name="text"><string>Note</string></property></widget></item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


@pytest.mark.pain("P-20")
def test_a_new_input_joins_a_custom_order_where_it_sits_not_at_the_end() -> None:
    log = open_log(FORM)
    doc = log.document
    assert effective_tab_order(doc) == ("emailEdit", "nameEdit", "phoneEdit")
    layout = doc.root.layout
    assert layout is not None
    log.execute(InsertFragment(InBoxLayout(layout.id, 1), Fragment(nodes=(button_spec("middleButton"),))))
    order = effective_tab_order(doc)
    # Reading order is name, middle, phone, email. The saved order keeps email first, and the
    # new button joins right after nameEdit, the stop before it on the form: not at the end.
    assert order == ("emailEdit", "nameEdit", "middleButton", "phoneEdit")
    assert reading_order(doc) == ("nameEdit", "middleButton", "phoneEdit", "emailEdit")
    log.undo()
    assert effective_tab_order(doc) == ("emailEdit", "nameEdit", "phoneEdit")


def test_a_form_that_follows_reading_order_gets_no_tabstops_from_an_insert() -> None:
    log = open_log(FORM.replace(" <tabstops>\n  <tabstop>emailEdit</tabstop>\n  <tabstop>nameEdit</tabstop>\n  <tabstop>phoneEdit</tabstop>\n </tabstops>\n", ""))
    doc = log.document
    layout = doc.root.layout
    assert layout is not None
    log.execute(InsertFragment(InBoxLayout(layout.id, 3), Fragment(nodes=(button_spec("lastButton"),))))
    assert doc.tabstops() is None


@pytest.mark.parity("R3-12")
def test_tab_order_round_trips_byte_identically_and_use_reading_order_removes_it() -> None:
    log = open_log(FORM)
    doc = log.document
    original = saved(doc)
    log.execute(ChangeTabOrder(("phoneEdit", "emailEdit", "nameEdit")))
    assert "<tabstop>phoneEdit</tabstop>" in saved(doc)
    assert log.undo_label() == "Change tab order"
    log.undo()
    assert saved(doc) == original
    log.execute(ChangeTabOrder(None))
    assert log.undo_label() == "Use reading order"
    assert doc.tabstops() is None
    assert "<tabstops>" not in saved(doc)
    log.undo()
    assert saved(doc) == original


def test_one_overlay_session_is_one_undo_step() -> None:
    log = open_log(FORM)
    doc = log.document
    original = saved(doc)
    for names in (("nameEdit",), ("nameEdit", "phoneEdit"), ("nameEdit", "phoneEdit", "emailEdit")):
        log.execute(ChangeTabOrder(q.order_after_picks(effective_tab_order(doc), names), merge_token="tab-session"))
    assert effective_tab_order(doc) == ("nameEdit", "phoneEdit", "emailEdit")
    log.undo()
    assert saved(doc) == original


def test_picks_continue_from_a_stop() -> None:
    order = ("a", "b", "c", "d")
    assert q.picks_through(order, "b") == ("a", "b")
    assert q.picks_through(order, "zzz") == ()
    assert q.order_after_picks(order, ("c", "a")) == ("c", "a", "b", "d")


@pytest.mark.parity("R3-8", "R3-9")
def test_buddy_writes_use_the_label_words_and_round_trip() -> None:
    log = open_log(ROWS)
    doc = log.document
    original = saved(doc)
    label = nid(doc, "nameLabel")
    assert q.caption(doc, label) == "Name"
    log.execute(SetLabelBuddy(label, "nameEdit", q.caption(doc, label)))
    assert q.buddy_of(doc, label) == "nameEdit"
    assert "<cstring>nameEdit</cstring>" in saved(doc)
    log.undo()
    assert saved(doc) == original
    log.execute(SetLabelBuddy(nid(doc, "emailLabel"), None, "Email"))
    assert q.buddy_of(doc, nid(doc, "emailLabel")) is None


def test_pairing_sets_only_labels_without_a_buddy_and_counts_them() -> None:
    log = open_log(ROWS)
    doc = log.document
    pairs = q.form_row_pairs(doc)
    assert [(q.caption_name(doc, label), field) for label, field in pairs] == [
        ("nameLabel", "nameEdit"),
        ("emailLabel", "emailEdit"),
        ("phoneLabel", "phoneEdit"),
    ]
    original = saved(doc)
    outcome = log.execute(PairLabels(pairs))
    assert outcome.result == 2
    assert q.buddy_of(doc, nid(doc, "emailLabel")) == "phoneEdit"
    assert q.buddy_of(doc, nid(doc, "phoneLabel")) == "phoneEdit"
    log.undo()
    assert saved(doc) == original
