"""Round-2 drop fixes. Each test names the gesture a user can see."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.commands.catalog import ApplyLayout, InsertFragment
from app.features.form_builder.engine.commands.catalog_ext.drop import InsertPage, SwapFormRows
from app.features.form_builder.engine.commands.drop_plan import commands_for
from app.features.form_builder.engine.commands.placement import InBoxLayout
from app.features.form_builder.engine.ids import IdAllocator, NodeId
from app.features.form_builder.engine.query.drop_target import (
    AcceptedDrop,
    DropHost,
    DropIndicator,
    DropPayload,
    OutlineRow,
    SlotGeom,
    hosts_from,
    resolve_drop,
    resolve_outline,
)
from app.features.form_builder.engine.query.hit_index import Rect
from app.features.form_builder.engine.ui4.nodes import LayoutItemNode, LayoutNode, WidgetNode
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.engine.ui4.writer import write_ui
from app.features.form_builder.integration.chrome_text import mixed_parent_sentence
from app.features.form_builder.qtside.canvas.core.palette import fragment_for
from app.features.form_builder.qtside.canvas.core.place import payload_for
from tests.form_builder.engine.commands._support import nid, open_log

pytestmark = pytest.mark.unit


def _doc(inner: str):
    text = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
%s
 </widget>
 <resources/>
 <connections/>
</ui>
""" % inner
    return read_ui(text, allocator=IdAllocator()).document


def _rects(doc, **boxes):
    found = {}
    for node in doc.iter_preorder():
        name = getattr(node, "object_name", "")
        if name in boxes:
            found[node.id] = boxes[name]
    return found


def _named(doc, name):
    found = doc.by_name(name)
    assert found, name
    return found[0]


def test_a_leaf_inside_a_free_container_is_not_a_drop_target() -> None:
    doc = _doc(
        """
  <widget class="QPushButton" name="ok">
   <property name="geometry"><rect><x>10</x><y>10</y><width>80</width><height>28</height></rect></property>
  </widget>
"""
    )
    root = doc.root.id
    button = _named(doc, "ok")
    rects = {root: Rect(0, 0, 200, 160), button: Rect(10, 10, 80, 28)}
    target = resolve_drop(hosts_from(doc, rects), (40, 20), DropPayload("widget"))
    assert isinstance(target, AcceptedDrop)
    assert target.host == root
    assert target.action == "free"


def test_an_empty_container_can_be_nested_into() -> None:
    doc = _doc('<widget class="QGroupBox" name="group"/>')
    group = _named(doc, "group")
    rects = {doc.root.id: Rect(0, 0, 300, 200), group: Rect(20, 20, 160, 80)}
    target = resolve_drop(hosts_from(doc, rects), (40, 40), DropPayload("widget"))
    assert isinstance(target, AcceptedDrop)
    assert target.host == group
    assert target.action == "auto_layout"


def test_an_inserted_group_box_already_has_a_vertical_layout() -> None:
    fragment = fragment_for("QGroupBox")
    assert fragment is not None
    widget = fragment.nodes[0]
    layouts = [spec for slot, specs in widget.slots if slot == "layout" for spec in specs]
    assert layouts
    assert layouts[0].field("class_name") == "QVBoxLayout"
    assert layouts[0].field("object_name") == "verticalLayout"


@pytest.mark.parity("R3-44")
@pytest.mark.parametrize(
    ("key", "widget_name", "layout_class", "layout_name"),
    (
        ("layout-v", "verticalLayoutWidget", "QVBoxLayout", "verticalLayout"),
        ("layout-h", "horizontalLayoutWidget", "QHBoxLayout", "horizontalLayout"),
        ("layout-grid", "gridLayoutWidget", "QGridLayout", "gridLayout"),
        ("layout-form", "formLayoutWidget", "QFormLayout", "formLayout"),
    ),
)
def test_a_layout_tile_drops_a_plain_widget_that_owns_the_layout(
    key: str, widget_name: str, layout_class: str, layout_name: str
) -> None:
    log = open_log(write_ui(_doc('  <layout class="QHBoxLayout" name="row"/>')).text)
    fragment = fragment_for(key)
    assert fragment is not None
    root_layout = log.document.root.layout
    assert root_layout is not None
    log.execute(InsertFragment(InBoxLayout(root_layout.id, 0), fragment))
    text = write_ui(log.document).text
    assert '<widget class="QWidget" name="%s">' % widget_name in text
    assert '<layout class="%s" name="%s"' % (layout_class, layout_name) in text


def test_form_rows_use_the_widgets_and_the_tail_is_a_new_row() -> None:
    doc = _doc(
        """
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="0"><widget class="QLabel" name="emailLabel">
    <property name="text"><string>Email:</string></property></widget></item>
   <item row="1" column="0"><widget class="QLabel" name="vipLabel">
    <property name="text"><string>VIP</string></property></widget></item>
   <item row="1" column="1"><widget class="QLineEdit" name="vip"/></item>
  </layout>
"""
    )
    form = _named(doc, "formLayout")
    rects = {
        doc.root.id: Rect(0, 0, 240, 220),
        form: Rect(0, 0, 240, 200),
        _named(doc, "emailLabel"): Rect(8, 8, 80, 24),
        _named(doc, "vipLabel"): Rect(8, 80, 80, 24),
        _named(doc, "vip"): Rect(100, 80, 120, 24),
    }
    field = resolve_drop(hosts_from(doc, rects), (160, 16), DropPayload("widget"))
    assert isinstance(field, AcceptedDrop)
    assert field.action == "form_cell"
    assert field.role == "field"
    assert field.row == 0
    assert field.sentence == "Field of row 1"
    after = resolve_drop(hosts_from(doc, rects), (20, 82), DropPayload("widget"))
    assert isinstance(after, AcceptedDrop)
    assert after.sentence == "New row after Email"
    tail = resolve_drop(hosts_from(doc, rects), (40, 160), DropPayload("widget"))
    assert isinstance(tail, AcceptedDrop)
    assert tail.action == "form_row"
    assert tail.sentence == "New row at the end"


def test_moving_a_spanning_grid_item_keeps_its_span() -> None:
    doc = _doc(
        """
  <layout class="QGridLayout" name="gridLayout">
   <item row="0" column="0" colspan="2"><widget class="QLabel" name="banner">
    <property name="text"><string>Banner</string></property></widget></item>
   <item row="1" column="0"><widget class="QLineEdit" name="left"/></item>
   <item row="1" column="1"><widget class="QLineEdit" name="right"/></item>
  </layout>
"""
    )
    log = open_log(write_ui(doc).text)
    banner = nid(log.document, "banner")
    payload = payload_for(log.document, (banner,))
    assert payload.colspan == 2
    grid = nid(log.document, "gridLayout")
    target = AcceptedDrop(
        "Into row 3, column 1 of the grid",
        "Row 3, column 1",
        grid,
        "grid_cell",
        DropIndicator(Rect(0, 80, 80, 24), dashed=True),
        Rect(0, 0, 200, 120),
        row=2,
        column=0,
        rowspan=payload.rowspan,
        colspan=payload.colspan,
    )
    for command in commands_for(log.document, target, payload, None):
        log.execute(command)
    moved = log.document.parent(banner)
    assert isinstance(moved, LayoutItemNode)
    assert moved.row == 2
    assert moved.colspan == 2


def test_a_splitter_pane_is_a_child_target() -> None:
    doc = _doc(
        """
  <widget class="QSplitter" name="split">
   <widget class="QGroupBox" name="pane">
    <layout class="QVBoxLayout" name="paneLayout">
     <item><widget class="QLineEdit" name="one"/></item>
     <item><widget class="QLineEdit" name="two"/></item>
    </layout>
   </widget>
  </widget>
"""
    )
    pane_layout = _named(doc, "paneLayout")
    rects = {
        doc.root.id: Rect(0, 0, 300, 200),
        _named(doc, "split"): Rect(0, 0, 300, 200),
        _named(doc, "pane"): Rect(0, 0, 300, 200),
        pane_layout: Rect(8, 8, 280, 180),
        _named(doc, "one"): Rect(8, 8, 260, 28),
        _named(doc, "two"): Rect(8, 48, 260, 28),
    }
    target = resolve_drop(hosts_from(doc, rects), (40, 40), DropPayload("widget"))
    assert isinstance(target, AcceptedDrop)
    assert target.host == pane_layout
    assert target.action == "box"


def test_a_zero_height_nested_layout_wins_over_its_parent() -> None:
    inner = DropHost(NodeId(9), "hbox", "row", Rect(0, 40, 200, 0), ())
    outer = DropHost(
        NodeId(1),
        "vbox",
        "form",
        Rect(0, 0, 200, 80),
        (
            SlotGeom(Rect(0, 0, 200, 36), 0, NodeId(2), "Shop"),
            SlotGeom(Rect(0, 40, 200, 0), 1, NodeId(9), "row"),
        ),
        (inner,),
    )
    target = resolve_drop(outer, (100, 50), DropPayload("widget"))
    assert isinstance(target, AcceptedDrop)
    assert target.host == NodeId(9)


def test_outline_thirds_enter_a_container_and_flank_a_leaf() -> None:
    doc = _doc(
        """
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QPushButton" name="shop">
    <property name="text"><string>Shop</string></property></widget></item>
  </layout>
"""
    )
    layout = _named(doc, "verticalLayout")
    shop = _named(doc, "shop")
    rows = (
        OutlineRow(layout, 0, 30, 180, 0),
        OutlineRow(shop, 30, 30, 180, 16),
    )
    into = resolve_outline(doc, rows, 15, DropPayload("widget"))
    assert isinstance(into, AcceptedDrop)
    assert into.host == layout
    assert into.action == "box"
    before = resolve_outline(doc, rows, 32, DropPayload("widget"))
    assert isinstance(before, AcceptedDrop)
    assert before.action == "box"
    assert before.index == 0


def test_missing_selection_ids_do_not_break_the_wrap_sentence() -> None:
    doc = _doc('<widget class="QPushButton" name="ok"/>')
    gone = _named(doc, "ok")
    assert mixed_parent_sentence(doc, (gone, gone)) == ""


def test_swapping_form_rows_keeps_the_items_in_row_order() -> None:
    text = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="0"><widget class="QLabel" name="aLabel">
    <property name="text"><string>A</string></property></widget></item>
   <item row="0" column="1"><widget class="QLineEdit" name="a"/></item>
   <item row="1" column="0"><widget class="QLabel" name="bLabel">
    <property name="text"><string>B</string></property></widget></item>
   <item row="1" column="1"><widget class="QLineEdit" name="b"/></item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""
    log = open_log(text)
    form = nid(log.document, "formLayout")
    log.execute(SwapFormRows(form, 0, 1))
    layout = log.document.node(form)
    assert isinstance(layout, LayoutNode)
    rows = []
    for item in layout.items:
        assert item.row is not None
        rows.append(item.row)
    assert rows == sorted(rows)
    assert log.undo()
    restored = log.document.node(form)
    assert isinstance(restored, LayoutNode)
    assert [item.row for item in restored.items] == [0, 0, 1, 1]


def test_adding_a_page_with_no_widget_selects_the_page() -> None:
    text = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QTabWidget" name="tabs"/>
 <resources/>
 <connections/>
</ui>
"""
    log = open_log(text)
    tabs = nid(log.document, "tabs")
    log.execute(InsertPage(tabs))
    host = log.document.node(tabs)
    assert isinstance(host, WidgetNode)
    assert len(host.child_widgets) == 1
    page = host.child_widgets[0]
    assert page.layout is not None
    assert page.layout.class_name == "QVBoxLayout"
    assert log.selection.current == page.id


def test_a_new_vertical_layout_uses_the_designer_name() -> None:
    text = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form"/>
 <resources/>
 <connections/>
</ui>
"""
    log = open_log(text)
    log.execute(ApplyLayout(log.document.root.id, "QVBoxLayout"))
    layout = log.document.root.layout
    assert layout is not None
    assert layout.object_name == "verticalLayout"
    other = open_log(text)
    other.execute(ApplyLayout(other.document.root.id, "QHBoxLayout"))
    again = other.document.root.layout
    assert again is not None
    assert again.object_name == "horizontalLayout"
