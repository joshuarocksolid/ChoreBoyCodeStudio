"""Slot resolve over synthetic geometry. The surface never calls resolve."""

from __future__ import annotations

from typing import Literal, Optional, Tuple

import pytest

from app.features.form_builder.engine.commands.placement import InBoxLayout, InContainer, InGridCell
from app.features.form_builder.engine.ids import IdAllocator, NodeId
from app.features.form_builder.engine.query.hit_index import GeoEntry, Rect
from app.features.form_builder.engine.query.slots import (
    Beside,
    CanvasGeom,
    CellMark,
    FrameMark,
    GapMark,
    GhostMark,
    MoveCargo,
    NewCargo,
    NoMark,
    OutlineGeom,
    Place,
    Point,
    Refuse,
    SPACER_CLASS,
    acceptable,
    loud,
    resolve,
)
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.engine.ui4.values import RectValue

pytestmark = pytest.mark.unit


def _document(inner: str) -> UiDocument:
    text = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<ui version="4.0">\n'
        " <class>Form</class>\n"
        ' <widget class="QWidget" name="Form">\n'
        "%s"
        " </widget>\n"
        " <resources/>\n"
        " <connections/>\n"
        "</ui>\n"
    ) % inner
    return read_ui(text, allocator=IdAllocator()).document


def _nid(document: UiDocument, name: str) -> NodeId:
    found = document.by_name(name)
    assert found, name
    return found[0]


def _entry(
    node: NodeId,
    kind: str,
    rect: Tuple[int, int, int, int],
    container: Optional[NodeId],
    z: int = 0,
) -> GeoEntry:
    return GeoEntry(node, kind, Rect(*rect), container, True, z)


NESTED = """
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <layout class="QHBoxLayout" name="horizontalLayout">
     <item>
      <widget class="QLabel" name="nameLabel">
       <property name="text"><string>Shop name</string></property>
      </widget>
     </item>
    </layout>
   </item>
  </layout>
"""

GRID = """
  <layout class="QGridLayout" name="gridLayout">
   <item row="0" column="0">
    <widget class="QPushButton" name="a"><property name="text"><string>A</string></property></widget>
   </item>
   <item row="0" column="1">
    <widget class="QPushButton" name="b"><property name="text"><string>B</string></property></widget>
   </item>
   <item row="0" column="2">
    <widget class="QPushButton" name="c"><property name="text"><string>C</string></property></widget>
   </item>
   <item row="1" column="0">
    <widget class="QPushButton" name="d"><property name="text"><string>D</string></property></widget>
   </item>
   <item row="1" column="1">
    <widget class="QPushButton" name="e"><property name="text"><string>E</string></property></widget>
   </item>
  </layout>
"""

FORM = """
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="0">
    <widget class="QLabel" name="nameLabel">
     <property name="text"><string>Name</string></property>
    </widget>
   </item>
   <item row="0" column="1">
    <widget class="QLineEdit" name="nameEdit"/>
   </item>
   <item row="1" column="0">
    <widget class="QLabel" name="emailLabel">
     <property name="text"><string>Email</string></property>
    </widget>
   </item>
  </layout>
"""

PAIR = """
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QLabel" name="nameLabel">
     <property name="text"><string>Shop name</string></property>
    </widget>
   </item>
   <item>
    <widget class="QLabel" name="receiptsLabel">
     <property name="text"><string>Receipts</string></property>
    </widget>
   </item>
  </layout>
"""

BESIDE = """
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QLineEdit" name="emailEdit">
     <property name="text"><string>Email</string></property>
    </widget>
   </item>
  </layout>
"""

GROUP = """
  <widget class="QGroupBox" name="receiptGroup"/>
"""

FREE = """
  <widget class="QPushButton" name="ok">
   <property name="geometry"><rect><x>10</x><y>10</y><width>80</width><height>24</height></rect></property>
   <property name="text"><string>OK</string></property>
  </widget>
"""

SELF = """
  <widget class="QGroupBox" name="group">
   <layout class="QVBoxLayout" name="verticalLayout">
    <item>
     <widget class="QPushButton" name="ok">
      <property name="text"><string>OK</string></property>
     </widget>
    </item>
   </layout>
  </widget>
"""


def _canvas(entries: Tuple[GeoEntry, ...]) -> CanvasGeom:
    return CanvasGeom(entries, floor=(48, 32), controls=())


def test_two_pixel_nested_horizontal_layout_accepts_a_line_edit() -> None:
    document = _document(NESTED)
    root = _nid(document, "Form")
    vbox = _nid(document, "verticalLayout")
    hbox = _nid(document, "horizontalLayout")
    label = _nid(document, "nameLabel")
    entries = (
        _entry(root, "widget", (0, 0, 200, 200), None),
        _entry(vbox, "layout", (0, 0, 200, 200), root, z=-1),
        _entry(hbox, "layout", (0, 100, 200, 2), vbox, z=-1),
        _entry(label, "widget", (0, 100, 80, 2), hbox, z=0),
    )
    target = resolve(
        document,
        _canvas(entries),
        Point(120, 101),
        NewCargo("QLineEdit", (120, 24)),
        snap=0,
    )
    assert isinstance(target.recipe, Place)
    assert target.recipe.placement == InBoxLayout(hbox, 1)
    assert target.recipe.auto_layout is False
    assert target.sentence == "Insert after Shop name"


def test_empty_grid_cell_speaks_a_one_based_row_and_column() -> None:
    document = _document(GRID)
    root = _nid(document, "Form")
    grid = _nid(document, "gridLayout")
    names = ("a", "b", "c", "d", "e")
    rects = ((0, 0, 100, 40), (100, 0, 100, 40), (200, 0, 100, 40), (0, 40, 100, 40), (100, 40, 100, 40))
    entries = [_entry(root, "widget", (0, 0, 300, 80), None), _entry(grid, "layout", (0, 0, 300, 80), root, z=-1)]
    for name, rect in zip(names, rects):
        entries.append(_entry(_nid(document, name), "widget", rect, grid))
    target = resolve(document, _canvas(tuple(entries)), Point(250, 60), NewCargo("QPushButton", (80, 24)), 0)
    assert isinstance(target.recipe, Place)
    assert target.recipe.placement == InGridCell(grid, 1, 2)
    assert target.sentence == "Row 2, column 3"
    assert isinstance(target.mark, CellMark)


def test_occupied_grid_center_refuses_and_would_not_drop() -> None:
    document = _document(GRID)
    root = _nid(document, "Form")
    grid = _nid(document, "gridLayout")
    button = _nid(document, "a")
    entries = (
        _entry(root, "widget", (0, 0, 300, 80), None),
        _entry(grid, "layout", (0, 0, 300, 80), root, z=-1),
        _entry(button, "widget", (0, 0, 100, 40), grid),
    )
    target = resolve(document, _canvas(entries), Point(50, 20), NewCargo("QPushButton", (80, 24)), 0)
    assert target.recipe == Refuse("center")
    assert target.sentence == ""
    assert isinstance(target.mark, NoMark)
    assert acceptable(target) is False


@pytest.mark.parametrize(
    ("at", "mode", "row", "column", "sentence", "axis"),
    [
        (Point(50, 2), "insert_row", 0, 0, "New row before A", "horizontal"),
        (Point(90, 20), "insert_column", 0, 1, "New column after A", "vertical"),
    ],
)
def test_occupied_grid_edge_inserts_a_row_or_column(
    at: Point,
    mode: Literal["insert_row", "insert_column"],
    row: int,
    column: int,
    sentence: str,
    axis: str,
) -> None:
    document = _document(GRID)
    root = _nid(document, "Form")
    grid = _nid(document, "gridLayout")
    button = _nid(document, "a")
    entries = (
        _entry(root, "widget", (0, 0, 300, 80), None),
        _entry(grid, "layout", (0, 0, 300, 80), root, z=-1),
        _entry(button, "widget", (0, 0, 100, 40), grid),
    )
    target = resolve(document, _canvas(entries), at, NewCargo("QPushButton", (80, 24)), 0)
    assert isinstance(target.recipe, Place)
    assert target.recipe.placement == InGridCell(grid, row, column, mode=mode)
    assert target.sentence == sentence
    assert isinstance(target.mark, GapMark)
    assert target.mark.axis == axis


@pytest.mark.parametrize(
    ("at",),
    [(Point(40, 20),), (Point(140, 20),), (Point(140, 60),)],
    ids=["label-cell", "field-cell", "empty-field-cell"],
)
def test_spacer_on_a_form_cell_is_a_loud_refusal(at: Point) -> None:
    document = _document(FORM)
    root = _nid(document, "Form")
    form = _nid(document, "formLayout")
    label = _nid(document, "nameLabel")
    field = _nid(document, "nameEdit")
    email = _nid(document, "emailLabel")
    entries = (
        _entry(root, "widget", (0, 0, 200, 80), None),
        _entry(form, "layout", (0, 0, 200, 80), root, z=-1),
        _entry(label, "widget", (0, 0, 80, 40), form),
        _entry(field, "widget", (80, 0, 120, 40), form),
        _entry(email, "widget", (0, 40, 80, 40), form),
    )
    target = resolve(document, _canvas(entries), at, NewCargo(SPACER_CLASS, (40, 20)), 0)
    assert target.recipe == Refuse("spacer")
    assert target.sentence == "A spacer can't go in a form."
    assert loud(target) is True
    assert acceptable(target) is False


def test_outline_gap_matches_the_canvas_gap_when_the_layout_row_excludes_its_children() -> None:
    document = _document(PAIR)
    root = _nid(document, "Form")
    layout = _nid(document, "verticalLayout")
    shop = _nid(document, "nameLabel")
    receipts = _nid(document, "receiptsLabel")
    canvas = (
        _entry(root, "widget", (0, 0, 200, 200), None),
        _entry(layout, "layout", (0, 0, 200, 200), root, z=-1),
        _entry(shop, "widget", (10, 10, 180, 40), layout, z=0),
        _entry(receipts, "widget", (10, 56, 180, 40), layout, z=1),
    )
    outline = (
        _entry(root, "widget", (0, 0, 220, 18), None, z=0),
        _entry(layout, "layout", (0, 18, 220, 18), root, z=1),
        _entry(shop, "widget", (16, 40, 200, 18), layout, z=0),
        _entry(receipts, "widget", (16, 58, 200, 18), layout, z=1),
    )
    cargo = NewCargo("QLineEdit", (120, 24))
    on_canvas = resolve(document, _canvas(canvas), Point(100, 53), cargo, 0)
    on_outline = resolve(document, OutlineGeom(outline, frozenset()), Point(100, 57), cargo, 0)
    assert isinstance(on_canvas.recipe, Place)
    assert isinstance(on_outline.recipe, Place)
    assert on_outline.recipe.placement == on_canvas.recipe.placement == InBoxLayout(layout, 1)


def test_box_index_follows_child_centers_not_the_six_pixel_gap() -> None:
    document = _document(PAIR)
    root = _nid(document, "Form")
    layout = _nid(document, "verticalLayout")
    shop = _nid(document, "nameLabel")
    receipts = _nid(document, "receiptsLabel")
    entries = (
        _entry(root, "widget", (0, 0, 200, 200), None),
        _entry(layout, "layout", (0, 0, 200, 200), root, z=-1),
        _entry(shop, "widget", (10, 10, 180, 40), layout, z=0),
        _entry(receipts, "widget", (10, 56, 180, 40), layout, z=1),
    )
    target = resolve(document, _canvas(entries), Point(100, 35), NewCargo("QPushButton", (80, 24)), 0)
    assert isinstance(target.recipe, Place)
    assert target.recipe.placement == InBoxLayout(layout, 1)
    assert target.sentence == "Insert between Shop name and Receipts"


def test_cross_axis_edge_within_eight_pixels_is_beside() -> None:
    document = _document(BESIDE)
    root = _nid(document, "Form")
    layout = _nid(document, "verticalLayout")
    email = _nid(document, "emailEdit")
    entries = (
        _entry(root, "widget", (0, 0, 200, 100), None),
        _entry(layout, "layout", (0, 0, 200, 100), root, z=-1),
        _entry(email, "widget", (20, 20, 100, 30), layout),
    )
    target = resolve(document, _canvas(entries), Point(126, 35), NewCargo("QPushButton", (80, 24)), 0)
    assert target.recipe == Beside(email, "QHBoxLayout", 1)
    assert target.sentence == "Beside Email · makes a horizontal row"
    assert isinstance(target.mark, GapMark)
    assert target.mark.axis == "vertical"


def test_empty_layoutless_container_places_with_auto_layout_and_a_frame() -> None:
    document = _document(GROUP)
    root = _nid(document, "Form")
    group = _nid(document, "receiptGroup")
    entries = (
        _entry(root, "widget", (0, 0, 400, 300), None),
        _entry(group, "widget", (40, 40, 200, 150), root),
    )
    target = resolve(document, _canvas(entries), Point(80, 80), NewCargo("QPushButton", (80, 24)), 0)
    assert isinstance(target.recipe, Place)
    assert target.recipe.auto_layout is True
    assert target.recipe.placement == InContainer(group, 0)
    assert isinstance(target.mark, FrameMark)
    assert target.sentence == "Into receiptGroup · makes a vertical layout"


def test_container_with_free_children_snaps_a_ghost_and_does_not_auto_layout() -> None:
    document = _document(FREE)
    root = _nid(document, "Form")
    button = _nid(document, "ok")
    entries = (
        _entry(root, "widget", (0, 0, 400, 300), None),
        _entry(button, "widget", (10, 10, 80, 24), root),
    )
    target = resolve(document, _canvas(entries), Point(123, 50), NewCargo("QLineEdit", (100, 24)), snap=8)
    assert isinstance(target.recipe, Place)
    assert target.recipe.auto_layout is False
    assert target.recipe.placement == InContainer(root, 1, RectValue(120, 48, 100, 24))
    assert isinstance(target.mark, GhostMark)
    assert target.mark.rect == Rect(120, 48, 100, 24)
    assert target.sentence == "x 120, y 48"


PAGE = """
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QStackedWidget" name="stack">
     <widget class="QWidget" name="pageA">
      <layout class="QVBoxLayout" name="pageLayout"/>
     </widget>
     <widget class="QWidget" name="pageB"/>
    </widget>
   </item>
  </layout>
"""


def test_empty_page_layout_is_a_gap_into_that_page() -> None:
    document = _document(PAGE)
    root = _nid(document, "Form")
    outer = _nid(document, "verticalLayout")
    stack = _nid(document, "stack")
    page = _nid(document, "pageA")
    layout = _nid(document, "pageLayout")
    entries = (
        _entry(root, "widget", (0, 0, 400, 300), None),
        _entry(outer, "layout", (0, 0, 400, 300), root, z=-1),
        _entry(stack, "widget", (8, 8, 380, 280), outer),
        _entry(page, "widget", (8, 8, 380, 280), stack),
        _entry(layout, "layout", (16, 16, 360, 260), page, z=-1),
    )
    target = resolve(document, _canvas(entries), Point(40, 40), NewCargo("QPushButton", (80, 24)), 0)
    assert isinstance(target.recipe, Place)
    assert target.recipe.placement == InBoxLayout(layout, 0)
    assert isinstance(target.mark, GapMark)
    assert target.sentence == "Into the pageA tab"


def test_dropping_a_widget_into_its_descendant_refuses() -> None:
    document = _document(SELF)
    root = _nid(document, "Form")
    group = _nid(document, "group")
    layout = _nid(document, "verticalLayout")
    button = _nid(document, "ok")
    entries = (
        _entry(root, "widget", (0, 0, 300, 200), None),
        _entry(group, "widget", (10, 10, 200, 150), root),
        _entry(layout, "layout", (18, 30, 184, 120), group, z=-1),
        _entry(button, "widget", (26, 40, 80, 24), layout),
    )
    target = resolve(document, _canvas(entries), Point(40, 50), MoveCargo((group,)), 0)
    assert target.recipe == Refuse("self")
    assert target.sentence == "A widget can't go inside itself."
    assert loud(target) is True
