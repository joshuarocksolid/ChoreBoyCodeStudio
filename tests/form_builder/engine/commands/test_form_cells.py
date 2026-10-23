from __future__ import annotations

from typing import Callable, Optional

import pytest

from app.features.form_builder.engine.commands.base import Command, CommandRejected, PlanContext
from app.features.form_builder.engine.commands.catalog import (
    ApplyLayout,
    InsertFragment,
    MorphLayout,
    MoveNodes,
    Rename,
    ReplaceDocument,
    SetLayoutCell,
    Unwrap,
    Wrap,
)
from app.features.form_builder.engine.commands.ops import SetFieldOp
from app.features.form_builder.engine.commands.placement import InBoxLayout, InFormRow, InGridCell
from app.features.form_builder.engine.ids import IdAllocator, NodeId
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutItemNode, LayoutNode
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.engine.ui4.spec import Fragment
from tests.form_builder.engine.commands._support import (
    FREE,
    button_spec,
    cell_of,
    nid,
    open_log,
    saved,
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
   <item row="1" column="0"><widget class="QLineEdit" name="c"/></item>
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

FORM_SHAPED_GRID = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QGridLayout" name="gridLayout">
   <item row="0" column="0"><widget class="QLabel" name="label"/></item>
   <item row="0" column="1"><widget class="QLineEdit" name="field"/></item>
   <item row="2" column="0" colspan="2"><widget class="QPushButton" name="wide"/></item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


class _RawRowWrite:
    command_type = "raw_row_write"
    label = "Raw row write"
    merge_token = None

    def __init__(self, item: NodeId, row: int) -> None:
        self.item = item
        self.row = row

    def merge_key(self) -> None:
        return None

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        del doc
        ctx.do(SetFieldOp(self.item, "row", self.row))


def _form(doc: UiDocument) -> NodeId:
    return nid(doc, "formLayout")


def _item(doc: UiDocument, name: str) -> LayoutItemNode:
    parent = doc.parent(nid(doc, name))
    assert isinstance(parent, LayoutItemNode)
    return parent


@pytest.mark.parametrize(
    ("text", "later", "message"),
    [
        (SHARED_CELL, "b", "Two widgets share the label cell of row 0 in formLayout."),
        (SPAN_OVER_FIELD, "field", "Two widgets share the field cell of row 0 in formLayout."),
    ],
)
def test_a_file_with_a_shared_form_cell_loads_with_a_warning(
    monkeypatch: pytest.MonkeyPatch, text: str, later: str, message: str
) -> None:
    monkeypatch.setenv("CBCS_FB_VALIDATE", "1")
    result = read_ui(text, allocator=IdAllocator())
    result.document.validate()
    shared = [diagnostic for diagnostic in result.diagnostics if diagnostic.code == "FB023"]
    assert [diagnostic.message for diagnostic in shared] == [message]
    assert shared[0].location.node_id == _item(result.document, later).id


def test_a_shared_form_cell_survives_a_resave() -> None:
    first = saved(read_ui(SHARED_CELL, allocator=IdAllocator()).document)
    reread = read_ui(first, allocator=IdAllocator()).document
    assert saved(reread) == first
    assert cell_of(reread, "a") == (0, 0)
    assert cell_of(reread, "b") == (0, 0)


def test_replacing_the_document_keeps_a_shared_form_cell(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CBCS_FB_VALIDATE", "1")
    log = open_log(FORM)
    doc = log.document
    before = doc.fingerprint()
    log.execute(ReplaceDocument(SHARED_CELL))
    assert cell_of(doc, "a") == (0, 0)
    assert cell_of(doc, "b") == (0, 0)
    assert log.undo()
    assert doc.fingerprint() == before


def test_a_replaced_shared_cell_accepts_a_later_insert(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CBCS_FB_VALIDATE", "1")
    log = open_log(FORM)
    with log.transaction("T") as tx:
        tx.execute(ReplaceDocument(SHARED_CELL))
        tx.execute(
            InsertFragment(
                InFormRow(nid(log.document, "formLayout"), 5, "field"),
                Fragment(nodes=(button_spec("go"),)),
            )
        )
    doc = log.document
    assert cell_of(doc, "a") == (0, 0)
    assert cell_of(doc, "b") == (0, 0)
    assert cell_of(doc, "go") == (5, 1)


def test_an_edit_beside_an_old_shared_cell_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CBCS_FB_VALIDATE", "1")
    log = open_log(SHARED_CELL)
    doc = log.document
    before = doc.fingerprint()
    log.execute(Rename(nid(doc, "a"), "renamed"))
    assert cell_of(doc, "renamed") == (0, 0)
    assert cell_of(doc, "b") == (0, 0)
    assert log.undo()
    assert doc.fingerprint() == before


def test_the_log_refuses_a_command_that_adds_to_a_shared_cell(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CBCS_FB_VALIDATE", "1")
    log = open_log(SHARED_CELL)
    doc = log.document
    before = doc.fingerprint()
    with pytest.raises(CommandRejected) as caught:
        log.execute(_RawRowWrite(_item(doc, "c").id, 0))
    assert caught.value.code == "FB999"
    assert doc.fingerprint() == before
    assert not log.can_undo()


def test_a_transaction_is_checked_against_the_form_before_it_opened(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CBCS_FB_VALIDATE", "1")
    log = open_log(SHARED_CELL)
    doc = log.document
    before = doc.fingerprint()
    with pytest.raises(CommandRejected) as caught:
        with log.transaction("T") as tx:
            tx.execute(_RawRowWrite(_item(doc, "c").id, 0))
            tx.execute(Rename(nid(doc, "a"), "renamed"))
    assert caught.value.code == "FB999"
    assert doc.fingerprint() == before
    assert not log.can_undo()


@pytest.mark.parametrize(
    ("text", "build"),
    [
        (HOST, lambda doc: InsertFragment(InGridCell(_form(doc), 1, 1), Fragment(nodes=(button_spec("go"),)))),
        (HOST, lambda doc: MoveNodes((nid(doc, "one"),), InGridCell(_form(doc), 0, 0, mode="insert_row"))),
        (
            STACKED_FIELDS,
            lambda doc: MoveNodes((nid(doc, "a"),), InFormRow(nid(doc, "gridLayout"), 0, "label", insert_row=True)),
        ),
        (
            STACKED_FIELDS,
            lambda doc: InsertFragment(
                InFormRow(nid(doc, "gridLayout"), 1, "field"), Fragment(nodes=(button_spec("go"),))
            ),
        ),
    ],
)
def test_a_placement_the_layout_has_no_cells_for_is_refused(
    text: str, build: Callable[[UiDocument], Command]
) -> None:
    log = open_log(text)
    doc = log.document
    before = doc.fingerprint()
    with pytest.raises(CommandRejected, match="That layout does not have cells like that"):
        log.execute(build(doc))
    assert doc.fingerprint() == before
    assert not log.can_undo()


@pytest.mark.parametrize(
    ("column", "rowspan", "colspan"),
    [(2, None, None), (0, 2, None), (1, None, 2)],
)
def test_set_layout_cell_refuses_a_form_cell_that_does_not_exist(
    column: int, rowspan: Optional[int], colspan: Optional[int]
) -> None:
    log = open_log(FORM)
    doc = log.document
    before = doc.fingerprint()
    with pytest.raises(CommandRejected, match="A form row has only a label and a field cell"):
        log.execute(SetLayoutCell(_item(doc, "extra").id, row=1, column=column, rowspan=rowspan, colspan=colspan))
    assert doc.fingerprint() == before
    assert not log.can_undo()


def test_set_layout_cell_accepts_a_spanning_form_row() -> None:
    log = open_log(FORM)
    doc = log.document
    log.execute(SetLayoutCell(_item(doc, "extra").id, row=2, column=0, colspan=2))
    assert cell_of(doc, "extra") == (2, 0)
    assert _item(doc, "extra").colspan == 2


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


def test_morph_grid_to_form_reseats_a_second_field_on_the_free_label_cell() -> None:
    log = open_log(STACKED_FIELDS)
    doc = log.document
    before = doc.fingerprint()
    log.execute(MorphLayout(nid(doc, "gridLayout"), "QFormLayout"))
    assert cell_of(doc, "a") == (0, 1)
    assert cell_of(doc, "b") == (0, 0)
    assert _item(doc, "a").colspan is None
    assert _item(doc, "b").colspan is None
    doc.validate()
    assert log.undo()
    assert doc.fingerprint() == before


def test_morph_keeps_a_span_and_reseats_the_item_it_covers() -> None:
    log = open_log(SPAN_AND_SIDE)
    doc = log.document
    before = doc.fingerprint()
    log.execute(MorphLayout(nid(doc, "gridLayout"), "QFormLayout"))
    assert cell_of(doc, "wide") == (0, 0)
    assert _item(doc, "wide").colspan == 2
    assert cell_of(doc, "side") == (1, 0)
    assert _item(doc, "side").colspan is None
    doc.validate()
    assert log.undo()
    assert doc.fingerprint() == before


def test_morph_keeps_the_cells_of_a_form_shaped_grid() -> None:
    log = open_log(FORM_SHAPED_GRID)
    doc = log.document
    before = doc.fingerprint()
    log.execute(MorphLayout(nid(doc, "gridLayout"), "QFormLayout"))
    assert cell_of(doc, "label") == (0, 0)
    assert cell_of(doc, "field") == (0, 1)
    assert cell_of(doc, "wide") == (2, 0)
    assert _item(doc, "wide").colspan == 2
    assert _item(doc, "label").colspan is None
    assert _item(doc, "field").colspan is None
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
