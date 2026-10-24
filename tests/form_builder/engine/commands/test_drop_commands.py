"""One undo step per drop command, and the three pain scripts at the engine."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.commands.catalog import MoveNodes
from app.features.form_builder.engine.commands.catalog_ext import default_registry
from app.features.form_builder.engine.commands.catalog_ext.drop import (
    AdoptIntoBox,
    InsertFormRow,
    InsertPage,
    SwapFormRows,
    WrapWithNew,
)
from app.features.form_builder.engine.commands.drop_plan import commands_for, nudge_commands
from app.features.form_builder.engine.commands.placement import InGridCell
from app.features.form_builder.engine.query.drop_target import (
    AcceptedDrop,
    DropIndicator,
    DropPayload,
)
from app.features.form_builder.engine.query.hit_index import Rect
from app.features.form_builder.engine.ui4.nodes import LayoutItemNode, LayoutNode, WidgetNode
from app.features.form_builder.engine.ui4.spec import Fragment
from app.features.form_builder.engine.ui4.values import CStringValue, RectValue
from tests.form_builder.engine.commands._support import button_spec, cell_of, nid, open_log, prop_text, saved

pytestmark = pytest.mark.unit

EMPTY = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form"/>
 <resources/>
 <connections/>
</ui>
"""

FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="0">
    <widget class="QLabel" name="emailLabel">
     <property name="text"><string>Email</string></property>
    </widget>
   </item>
   <item row="0" column="1">
    <widget class="QLineEdit" name="email"/>
   </item>
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
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QLabel" name="shop">
     <property name="text"><string>Shop name</string></property>
    </widget>
   </item>
   <item>
    <widget class="QPushButton" name="below"/>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

GRID = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QGridLayout" name="gridLayout">
   <item row="0" column="0">
    <widget class="QPushButton" name="moved">
     <property name="text"><string>Move me</string></property>
    </widget>
   </item>
   <item row="0" column="1">
    <widget class="QPushButton" name="stay"/>
   </item>
   <item row="1" column="0" colspan="2">
    <widget class="QLabel" name="banner"/>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

FREE = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <widget class="QPushButton" name="loose">
   <property name="geometry">
    <rect><x>10</x><y>10</y><width>80</width><height>24</height></rect>
   </property>
  </widget>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

TABS = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <widget class="QTabWidget" name="tabs">
   <widget class="QWidget" name="pageA">
    <attribute name="title"><string>One</string></attribute>
   </widget>
  </widget>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def test_registry_discovers_the_drop_commands() -> None:
    names = {item.command_type for item in default_registry().types()}  # type: ignore[attr-defined]
    assert names >= {"insert_form_row", "wrap_with_new", "adopt_into_box", "swap_form_rows", "insert_page"}


@pytest.mark.pain("P-1")
def test_first_drop_into_an_empty_form_writes_a_layout_and_undoes() -> None:
    log = open_log(EMPTY)
    before = saved(log.document)
    root = log.document.root.id
    log.execute(AdoptIntoBox(root, fragment=Fragment(nodes=(button_spec("ok", "OK"),))))
    text = saved(log.document)
    assert "QVBoxLayout" in text
    assert "<geometry>" not in text
    assert prop_text(log.document, "ok") == "OK"
    assert log.undo()
    assert saved(log.document) == before
    assert log.undo_label() is None


def test_a_new_form_row_creates_a_buddy_label_in_one_undo_step() -> None:
    log = open_log(FORM)
    before = saved(log.document)
    layout = log.document.root.layout
    assert layout is not None
    outcome = log.execute(InsertFormRow(layout.id, 1, fragment=Fragment(nodes=(button_spec("go", "Go"),))))
    label_id, field_id = outcome.result
    label = log.document.node(label_id)
    field = log.document.node(field_id)
    assert isinstance(label, WidgetNode)
    assert prop_text(log.document, label.object_name) == "New field:"
    buddy = label.prop("buddy")
    assert buddy is not None and isinstance(buddy.value, CStringValue)
    assert isinstance(field, WidgetNode)
    assert buddy.value.text == field.object_name
    assert log.selection.current == label_id
    assert len(log.entries()) == 1
    assert log.undo()
    assert saved(log.document) == before


def test_wrapping_beside_a_box_item_is_one_undo_step() -> None:
    log = open_log(NESTED)
    before = saved(log.document)
    shop = nid(log.document, "shop")
    log.execute(
        WrapWithNew(
            shop,
            "after",
            "QHBoxLayout",
            fragment=Fragment(nodes=(button_spec("receipts", "Receipts"),)),
        )
    )
    outer = log.document.root.layout
    assert isinstance(outer, LayoutNode)
    assert len(outer.items) == 2
    nested = outer.items[0].content
    assert isinstance(nested, LayoutNode)
    assert nested.class_name == "QHBoxLayout"
    names = []
    for item in nested.items:
        content = item.content
        if isinstance(content, WidgetNode):
            names.append(content.object_name)
    assert names == ["shop", "receipts"]
    assert log.undo()
    assert saved(log.document) == before


def test_moving_a_free_widget_into_an_empty_container_drops_its_geometry() -> None:
    log = open_log(FREE)
    root = log.document.root.id
    loose = nid(log.document, "loose")
    group = log.execute(
        AdoptIntoBox(root, existing=(loose,))
    )
    assert group.result == (loose,)
    assert log.document.node(loose).prop("geometry") is None
    assert "<geometry>" not in saved(log.document)
    assert log.undo()
    entry = log.document.node(loose).prop("geometry")
    assert entry is not None and isinstance(entry.value, RectValue)


@pytest.mark.pain("P-21")
def test_a_grid_move_to_row_2_column_3_changes_only_that_cell() -> None:
    log = open_log(GRID)
    before = saved(log.document)
    layout = log.document.root.layout
    assert layout is not None
    moved = nid(log.document, "moved")
    log.execute(MoveNodes((moved,), InGridCell(layout.id, 1, 2)))
    assert cell_of(log.document, "moved") == (1, 2)
    assert cell_of(log.document, "stay") == (0, 1)
    banner_item = log.document.parent(nid(log.document, "banner"))
    assert isinstance(banner_item, LayoutItemNode)
    assert banner_item.row == 1 and banner_item.column == 0 and banner_item.colspan == 2
    assert log.undo()
    assert saved(log.document) == before
    assert cell_of(log.document, "moved") == (0, 0)


def test_a_form_nudge_swaps_the_two_rows() -> None:
    log = open_log(FORM)
    layout = log.document.root.layout
    assert layout is not None
    log.execute(InsertFormRow(layout.id, 1, fragment=Fragment(nodes=(button_spec("go", "Go"),))))
    commands = nudge_commands(log.document, (nid(log.document, "go"),), "up")
    assert len(commands) == 1
    assert isinstance(commands[0], SwapFormRows)
    log.execute(commands[0])
    assert cell_of(log.document, "go") == (0, 1)
    assert cell_of(log.document, "email") == (1, 1)


def test_swapping_form_rows_exchanges_only_those_rows() -> None:
    log = open_log(FORM)
    layout = log.document.root.layout
    assert layout is not None
    log.execute(InsertFormRow(layout.id, 1, fragment=Fragment(nodes=(button_spec("go", "Go"),))))
    email = cell_of(log.document, "email")
    assert email == (0, 1)
    log.execute(SwapFormRows(layout.id, 0, 1))
    assert cell_of(log.document, "email") == (1, 1)
    assert cell_of(log.document, "go") == (0, 1)
    assert log.undo()
    assert cell_of(log.document, "email") == (0, 1)


def test_a_new_tab_page_holds_the_dropped_widget() -> None:
    log = open_log(TABS)
    tabs = nid(log.document, "tabs")
    log.execute(InsertPage(tabs, fragment=Fragment(nodes=(button_spec("inside", "In"),))))
    host = log.document.node(tabs)
    assert isinstance(host, WidgetNode)
    assert len(host.child_widgets) == 2
    page = host.child_widgets[1]
    assert page.attr("title") is not None
    assert getattr(page.attr("title").value, "text", "") == "Tab 2"  # type: ignore[union-attr]
    assert page.layout is not None
    content = page.layout.items[0].content
    assert isinstance(content, WidgetNode) and content.object_name == "inside"
    assert log.undo()
    assert len(log.document.node(tabs).child_widgets) == 1  # type: ignore[attr-defined]


def test_commands_for_a_box_insert_and_a_refused_spacer() -> None:
    log = open_log(NESTED)
    layout = nid(log.document, "verticalLayout")
    target = AcceptedDrop(
        sentence="Insert here",
        chip="Insert here",
        host=layout,
        action="box",
        indicator=DropIndicator(Rect(0, 0, 2, 8)),
        frame=Rect(0, 0, 10, 10),
        index=0,
    )
    commands = commands_for(
        log.document,
        target,
        DropPayload("widget"),
        Fragment(nodes=(button_spec("line", "Line"),)),
    )
    assert len(commands) == 1
    log.execute(commands[0])
    assert prop_text(log.document, "line") == "Line"
    form = open_log(FORM)
    form_layout = form.document.root.layout
    assert form_layout is not None
    refused_host = AcceptedDrop(
        sentence="",
        chip="",
        host=form_layout.id,
        action="form_row",
        indicator=DropIndicator(Rect(0, 0, 1, 1)),
        frame=Rect(0, 0, 1, 1),
        row=1,
        role="field",
    )
    assert commands_for(form.document, refused_host, DropPayload("spacer"), Fragment(nodes=(button_spec("s"),))) == ()


def test_commands_for_moves_a_grid_span_without_touching_other_cells() -> None:
    log = open_log(GRID)
    layout = log.document.root.layout
    assert layout is not None
    moved = nid(log.document, "moved")
    target = AcceptedDrop(
        sentence="Into row 2, column 3 of the grid",
        chip="Row 2, column 3",
        host=layout.id,
        action="grid_cell",
        indicator=DropIndicator(Rect(0, 0, 1, 1), dashed=True),
        frame=Rect(0, 0, 1, 1),
        row=1,
        column=2,
        rowspan=1,
        colspan=1,
    )
    commands = commands_for(log.document, target, DropPayload("widget", (moved,)), None)
    for command in commands:
        log.execute(command)
    assert cell_of(log.document, "moved") == (1, 2)
    assert cell_of(log.document, "stay") == (0, 1)
    assert len(log.entries()) == 1
