"""Form-layout cells stay unique (CONTRACTS.md section 2.7)."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog import (
    ApplyLayout,
    InsertFragment,
    MorphLayout,
    MoveNodes,
    SetLayoutCell,
    Unwrap,
    Wrap,
)
from app.features.form_builder.engine.commands.placement import InBoxLayout, InFormRow
from app.features.form_builder.engine.ids import IdAllocator, NodeId
from app.features.form_builder.engine.ui4.document import InvariantError, UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutItemNode, LayoutNode
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.engine.ui4.spec import Fragment
from tests.form_builder.engine.commands._support import (
    FREE,
    button_spec,
    cell_of,
    nid,
    open_log,
)

HOST = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QPushButton" name="one"/></item>
   <item><widget class="QPushButton" name="two"/></item>
   <item>
    <widget class="QWidget" name="box">
     <layout class="QFormLayout" name="formLayout">
      <item row="0" column="0"><widget class="QLabel" name="label"/></item>
      <item row="0" column="1"><widget class="QLineEdit" name="field"/></item>
     </layout>
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="0"><widget class="QLabel" name="label"/></item>
   <item row="0" column="1"><widget class="QLineEdit" name="field"/></item>
   <item row="1" column="0"><widget class="QPushButton" name="extra"/></item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

STACKED_FIELDS = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QGridLayout" name="gridLayout">
   <item row="0" column="1"><widget class="QPushButton" name="a"/></item>
   <item row="0" column="2"><widget class="QPushButton" name="b"/></item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

SPAN_AND_SIDE = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QGridLayout" name="gridLayout">
   <item row="0" column="0" colspan="2"><widget class="QPushButton" name="wide"/></item>
   <item row="0" column="2"><widget class="QPushButton" name="side"/></item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

NESTED = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="0"><widget class="QLabel" name="label"/></item>
   <item row="1" column="0" colspan="2">
    <layout class="QVBoxLayout" name="inner">
     <item><widget class="QPushButton" name="one"/></item>
     <item><widget class="QPushButton" name="two"/></item>
    </layout>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

SHARED_CELL = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="0"><widget class="QLabel" name="a"/></item>
   <item row="0" column="0"><widget class="QLabel" name="b"/></item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

SPAN_OVER_FIELD = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="0" colspan="2"><widget class="QLabel" name="wide"/></item>
   <item row="0" column="1"><widget class="QLineEdit" name="field"/></item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _form(doc: UiDocument) -> NodeId:
    return nid(doc, "formLayout")


def _item(doc: UiDocument, name: str) -> LayoutItemNode:
    parent = doc.parent(nid(doc, name))
    assert isinstance(parent, LayoutItemNode)
    return parent


def test_validate_rejects_two_items_in_one_form_cell(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CBCS_FB_VALIDATE", "0")
    document = read_ui(SHARED_CELL, allocator=IdAllocator()).document
    with pytest.raises(InvariantError, match="row 0 column 0"):
        document.validate()


def test_validate_treats_a_spanning_item_as_both_columns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CBCS_FB_VALIDATE", "0")
    document = read_ui(SPAN_OVER_FIELD, allocator=IdAllocator()).document
    with pytest.raises(InvariantError, match="row 0 column 1"):
        document.validate()


def test_move_into_an_occupied_form_cell_is_refused() -> None:
    log = open_log(HOST)
    doc = log.document
    before = doc.fingerprint()
    with pytest.raises(CommandRejected, match="occupied"):
        log.execute(MoveNodes((nid(doc, "one"),), InFormRow(_form(doc), 0, "field")))
    assert doc.fingerprint() == before
    assert not log.can_undo()
    assert cell_of(doc, "field") == (0, 1)


def test_move_into_a_form_row_shifts_later_rows() -> None:
    log = open_log(HOST)
    doc = log.document
    before = doc.fingerprint()
    log.execute(
        MoveNodes(
            (nid(doc, "one"), nid(doc, "two")),
            InFormRow(_form(doc), 0, "field", insert_row=True),
        )
    )
    assert cell_of(doc, "one") == (0, 1)
    assert cell_of(doc, "two") == (1, 1)
    assert cell_of(doc, "label") == (2, 0)
    assert cell_of(doc, "field") == (2, 1)
    doc.validate()
    assert log.undo()
    assert doc.fingerprint() == before


def test_move_through_a_box_index_takes_a_free_form_row() -> None:
    log = open_log(HOST)
    doc = log.document
    before = doc.fingerprint()
    log.execute(MoveNodes((nid(doc, "one"),), InBoxLayout(_form(doc), 0)))
    assert cell_of(doc, "one") == (0, 0)
    assert cell_of(doc, "label") == (1, 0)
    assert cell_of(doc, "field") == (1, 1)
    doc.validate()
    assert log.undo()
    assert doc.fingerprint() == before


def test_insert_fragment_into_a_form_row_shifts_later_rows() -> None:
    log = open_log(HOST)
    doc = log.document
    before = doc.fingerprint()
    fragment = Fragment(nodes=(button_spec("go"), button_spec("stop")))
    log.execute(InsertFragment(InFormRow(_form(doc), 0, "label", insert_row=True), fragment))
    assert cell_of(doc, "go") == (0, 0)
    assert cell_of(doc, "stop") == (1, 0)
    assert cell_of(doc, "label") == (2, 0)
    assert cell_of(doc, "field") == (2, 1)
    doc.validate()
    assert log.undo()
    assert doc.fingerprint() == before


def test_insert_fragment_at_a_box_index_shifts_the_form() -> None:
    log = open_log(HOST)
    doc = log.document
    before = doc.fingerprint()
    fragment = Fragment(nodes=(button_spec("go"), button_spec("stop")))
    log.execute(InsertFragment(InBoxLayout(_form(doc), 0), fragment))
    assert cell_of(doc, "go") == (0, 0)
    assert cell_of(doc, "stop") == (1, 0)
    assert cell_of(doc, "label") == (2, 0)
    assert cell_of(doc, "field") == (2, 1)
    doc.validate()
    assert log.undo()
    assert doc.fingerprint() == before


def test_wrap_in_a_form_layout_pairs_label_and_field() -> None:
    log = open_log(HOST)
    doc = log.document
    before = doc.fingerprint()
    log.execute(Wrap((nid(doc, "one"), nid(doc, "two")), None, "QFormLayout"))
    assert cell_of(doc, "one") == (0, 0)
    assert cell_of(doc, "two") == (0, 1)
    assert _item(doc, "one").colspan is None
    assert _item(doc, "two").colspan is None
    doc.validate()
    assert log.undo()
    assert doc.fingerprint() == before


def test_wrap_inside_a_form_keeps_the_wrapper_on_a_free_cell() -> None:
    log = open_log(FORM)
    doc = log.document
    before = doc.fingerprint()
    layout_id = log.execute(Wrap((nid(doc, "field"), nid(doc, "extra")), None, "QVBoxLayout")).result
    wrapper = doc.parent(layout_id)
    assert isinstance(wrapper, LayoutItemNode)
    assert (wrapper.row, wrapper.column) == (0, 1)
    assert cell_of(doc, "label") == (0, 0)
    doc.validate()
    assert log.undo()
    assert doc.fingerprint() == before


def test_morph_grid_to_form_pairs_items_in_reading_order() -> None:
    log = open_log(STACKED_FIELDS)
    doc = log.document
    before = doc.fingerprint()
    log.execute(MorphLayout(nid(doc, "gridLayout"), "QFormLayout"))
    assert cell_of(doc, "a") == (0, 0)
    assert cell_of(doc, "b") == (0, 1)
    assert _item(doc, "a").colspan is None
    doc.validate()
    assert log.undo()
    assert doc.fingerprint() == before


def test_morph_drops_a_span_that_would_cover_another_item() -> None:
    log = open_log(SPAN_AND_SIDE)
    doc = log.document
    before = doc.fingerprint()
    log.execute(MorphLayout(nid(doc, "gridLayout"), "QFormLayout"))
    assert cell_of(doc, "wide") == (0, 0)
    assert cell_of(doc, "side") == (0, 1)
    assert _item(doc, "wide").colspan is None
    doc.validate()
    assert log.undo()
    assert doc.fingerprint() == before


def test_apply_layout_as_a_form_pairs_the_children() -> None:
    log = open_log(FREE)
    doc = log.document
    before = doc.fingerprint()
    log.execute(ApplyLayout(doc.root.id, "QFormLayout", (nid(doc, "label"), nid(doc, "okButton"))))
    assert cell_of(doc, "label") == (0, 0)
    assert cell_of(doc, "okButton") == (0, 1)
    doc.validate()
    assert log.undo()
    assert doc.fingerprint() == before


def test_set_layout_cell_refuses_an_occupied_form_cell() -> None:
    log = open_log(FORM)
    doc = log.document
    before = doc.fingerprint()
    with pytest.raises(CommandRejected, match="overlap"):
        log.execute(SetLayoutCell(_item(doc, "label").id, row=0, column=1))
    assert doc.fingerprint() == before
    assert cell_of(doc, "label") == (0, 0)
    assert not log.can_undo()


def test_unwrap_into_a_form_uses_free_cells() -> None:
    log = open_log(NESTED)
    doc = log.document
    before = doc.fingerprint()
    log.execute(Unwrap(nid(doc, "inner")))
    assert cell_of(doc, "label") == (0, 0)
    assert cell_of(doc, "one") == (0, 1)
    assert cell_of(doc, "two") == (1, 0)
    doc.validate()
    assert log.undo()
    assert doc.fingerprint() == before
    assert isinstance(doc.node(nid(doc, "inner")), LayoutNode)


def test_empty_form_cell_accepts_a_move_without_shifting() -> None:
    log = open_log(FORM)
    doc = log.document
    before = doc.fingerprint()
    log.execute(MoveNodes((nid(doc, "extra"),), InFormRow(_form(doc), 1, "field")))
    assert cell_of(doc, "extra") == (1, 1)
    assert cell_of(doc, "label") == (0, 0)
    assert cell_of(doc, "field") == (0, 1)
    doc.validate()
    assert log.undo()
    assert doc.fingerprint() == before
