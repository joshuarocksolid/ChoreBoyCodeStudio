"""Drop step, commit, and slot nudge. The surface calls these, not resolve."""

from __future__ import annotations

from typing import Optional, Sequence, Tuple, Union

import pytest

from app.features.form_builder.engine.commands.catalog import SetProperty
from app.features.form_builder.engine.commands.log import CommandLog
from app.features.form_builder.engine.commands.placement import InBoxLayout, InContainer, InGridCell
from app.features.form_builder.engine.drop import (
    DRAG_THRESHOLD,
    TILES,
    ArmCanvas,
    ArmTile,
    CarryStep,
    CommitDrop,
    Pointer,
    Quiet,
    Release,
    Tile,
    commit,
    nudge,
    step,
)
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.project.templates import build_template_ui
from app.features.form_builder.engine.query.hit_index import GeoEntry, Rect
from app.features.form_builder.engine.query.slots import (
    Buddy,
    CanvasGeom,
    MoveCargo,
    Place,
    Point,
)
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutNode, SpacerNode, WidgetNode
from app.features.form_builder.engine.ui4.values import StringValue
from tests.form_builder.engine.commands._support import cell_of, nid, open_log, prop_text, saved

pytestmark = pytest.mark.unit


def _log(inner: str) -> CommandLog:
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
    return open_log(text)


def _entry(
    node: NodeId,
    kind: str,
    rect: Tuple[int, int, int, int],
    container: Optional[NodeId],
    z: int = 0,
) -> GeoEntry:
    return GeoEntry(node, kind, Rect(*rect), container, True, z)


def _canvas(entries: Sequence[GeoEntry]) -> CanvasGeom:
    return CanvasGeom(tuple(entries), floor=(48, 32), controls=())


def _release(document: UiDocument, sight: CanvasGeom, arm: Union[ArmTile, ArmCanvas], at: Point) -> CarryStep:
    armed = step(Quiet(), arm, sight, document)
    moved = step(
        armed.state,
        Pointer("canvas", Point(arm.global_at.x + DRAG_THRESHOLD, arm.global_at.y), at, 8, 0),
        sight,
        document,
    )
    return step(moved.state, Release(), sight, document)


def _drop_effect(result: CarryStep) -> CommitDrop:
    found = [effect for effect in result.effects if isinstance(effect, CommitDrop)]
    assert len(found) == 1
    return found[0]


def _box_names(document: UiDocument) -> Tuple[str, ...]:
    layout = document.root.layout
    assert isinstance(layout, LayoutNode)
    names = []
    for item in layout.items:
        content = item.content
        assert isinstance(content, WidgetNode)
        names.append(content.object_name)
    return tuple(names)


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
  </layout>
"""

ORDERED = """
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QPushButton" name="first"><property name="text"><string>First</string></property></widget>
   </item>
   <item>
    <widget class="QPushButton" name="second"><property name="text"><string>Second</string></property></widget>
   </item>
  </layout>
"""

NUDGE = """
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QPushButton" name="one"><property name="text"><string>One</string></property></widget>
   </item>
   <item>
    <widget class="QPushButton" name="two"><property name="text"><string>Two</string></property></widget>
   </item>
   <item>
    <widget class="QPushButton" name="three"><property name="text"><string>Three</string></property></widget>
   </item>
  </layout>
"""

BARE = """
  <widget class="QGroupBox" name="receiptGroup">
   <property name="title"><string>receiptGroup</string></property>
  </widget>
"""


def test_undo_of_a_blank_form_drop_leaves_the_template_layout() -> None:
    log = open_log(build_template_ui("widget", "Form"))
    doc = log.document
    layout = doc.root.layout
    assert isinstance(layout, LayoutNode)
    layout_id = layout.id
    sight = _canvas(
        (
            _entry(doc.root.id, "widget", (0, 0, 200, 200), None),
            _entry(layout_id, "layout", (0, 0, 200, 200), doc.root.id, z=-1),
        )
    )
    effect = _drop_effect(
        _release(doc, sight, ArmTile("QPushButton", (80, 24), Point(0, 0), Point(0, 0), "drop:1"), Point(40, 40))
    )
    done = commit(log, effect)
    assert done.moved is True
    assert done.edited is None
    button = doc.node(nid(doc, "pushButton"))
    assert isinstance(button, WidgetNode)
    assert button.prop("geometry") is None
    assert len(log.entries()) == 1
    assert log.undo()
    restored = doc.root.layout
    assert isinstance(restored, LayoutNode)
    assert restored.id == layout_id
    assert restored.class_name == "QVBoxLayout"
    assert restored.items == ()
    assert not doc.by_name("pushButton")
    assert not log.can_undo()


def test_undo_of_a_drop_that_created_a_layout_removes_that_layout() -> None:
    log = _log(BARE)
    doc = log.document
    group_id = nid(doc, "receiptGroup")
    sight = _canvas(
        (
            _entry(doc.root.id, "widget", (0, 0, 400, 300), None),
            _entry(group_id, "widget", (10, 10, 200, 150), doc.root.id),
        )
    )
    effect = _drop_effect(
        _release(doc, sight, ArmTile("QPushButton", (80, 24), Point(0, 0), Point(0, 0), "drop:2"), Point(40, 40))
    )
    recipe = effect.target.recipe
    assert isinstance(recipe, Place)
    assert recipe.placement == InContainer(group_id, 0)
    assert recipe.auto_layout is True
    assert effect.target.sentence == "Into receiptGroup · makes a vertical layout"
    assert commit(log, effect).moved is True
    group = doc.node(group_id)
    assert isinstance(group, WidgetNode)
    assert group.layout is not None
    assert group.layout.class_name == "QVBoxLayout"
    assert len(log.entries()) == 1
    assert log.undo()
    restored = doc.node(group_id)
    assert isinstance(restored, WidgetNode)
    assert restored.layout is None
    assert not doc.by_name("pushButton")


@pytest.mark.pain("P-21")
def test_grid_move_to_an_empty_cell_changes_only_that_item() -> None:
    log = _log(GRID)
    doc = log.document
    root = doc.root.id
    grid = nid(doc, "gridLayout")
    names = ("a", "b", "c", "d", "e")
    rects = ((0, 0, 100, 40), (100, 0, 100, 40), (200, 0, 100, 40), (0, 40, 100, 40), (100, 40, 100, 40))
    entries = [_entry(root, "widget", (0, 0, 300, 80), None), _entry(grid, "layout", (0, 0, 300, 80), root, z=-1)]
    ids = []
    for name, rect in zip(names, rects):
        node_id = nid(doc, name)
        ids.append(node_id)
        entries.append(_entry(node_id, "widget", rect, grid))
    before = {name: cell_of(doc, name) for name in names}
    sight = _canvas(entries)
    pressed = ids[0]
    result = _release(
        doc,
        sight,
        ArmCanvas(pressed, tuple(ids), False, Point(0, 0), Point(0, 0), "drop:3"),
        Point(250, 60),
    )
    assert cell_of(doc, "a") == before["a"]
    effect = _drop_effect(result)
    assert effect.cargo == MoveCargo((pressed,))
    recipe = effect.target.recipe
    assert isinstance(recipe, Place)
    assert recipe.placement == InGridCell(grid, 1, 2)
    assert effect.target.sentence == "Row 2, column 3"
    assert commit(log, effect).moved is True
    assert cell_of(doc, "a") == (1, 2)
    for name in names[1:]:
        assert cell_of(doc, name) == before[name]
    assert len(log.entries()) == 1
    assert log.undo()
    assert cell_of(doc, "a") == (0, 0)
    for name in names[1:]:
        assert cell_of(doc, name) == before[name]


def test_buddy_text_edit_joins_the_drop_undo_step() -> None:
    log = _log(FORM)
    doc = log.document
    root = doc.root.id
    layout_id = nid(doc, "formLayout")
    label = nid(doc, "nameLabel")
    field = nid(doc, "nameEdit")
    sight = _canvas(
        (
            _entry(root, "widget", (0, 0, 280, 80), None),
            _entry(layout_id, "layout", (0, 0, 280, 80), root, z=-1),
            _entry(label, "widget", (0, 0, 100, 40), layout_id),
            _entry(field, "widget", (100, 0, 180, 40), layout_id),
        )
    )
    effect = _drop_effect(
        _release(doc, sight, ArmTile("QPushButton", (80, 24), Point(0, 0), Point(0, 0), "drop:4"), Point(40, 30))
    )
    assert isinstance(effect.target.recipe, Buddy)
    assert effect.target.sentence == "New row after Name"
    done = commit(log, effect)
    assert done.edited is not None
    assert prop_text(doc, "label") == "New field:"
    buddy = doc.node(done.edited).prop("buddy")
    assert buddy is not None
    assert buddy.value.text == "pushButton"
    assert cell_of(doc, "label") == (1, 0)
    assert cell_of(doc, "pushButton") == (1, 1)
    with log.transaction("Edit text", merge_token=effect.token) as txn:
        txn.execute(SetProperty(done.edited, "text", StringValue("Email")))
    assert len(log.entries()) == 1
    assert prop_text(doc, "label") == "Email"
    assert log.undo()
    assert not log.can_undo()
    assert prop_text(doc, "nameLabel") == "Name"
    assert not doc.by_name("label")
    assert not doc.by_name("pushButton")


def test_undo_of_a_buddy_drop_removes_the_row() -> None:
    log = _log(FORM)
    doc = log.document
    root = doc.root.id
    layout_id = nid(doc, "formLayout")
    label = nid(doc, "nameLabel")
    field = nid(doc, "nameEdit")
    sight = _canvas(
        (
            _entry(root, "widget", (0, 0, 280, 80), None),
            _entry(layout_id, "layout", (0, 0, 280, 80), root, z=-1),
            _entry(label, "widget", (0, 0, 100, 40), layout_id),
            _entry(field, "widget", (100, 0, 180, 40), layout_id),
        )
    )
    effect = _drop_effect(
        _release(doc, sight, ArmTile("QPushButton", (80, 24), Point(0, 0), Point(0, 0), "drop:5"), Point(40, 30))
    )
    assert commit(log, effect).moved is True
    assert len(log.entries()) == 1
    assert log.undo()
    assert not log.can_undo()
    assert cell_of(doc, "nameLabel") == (0, 0)
    assert cell_of(doc, "nameEdit") == (0, 1)
    assert not doc.by_name("pushButton")
    assert not doc.by_name("label")


def test_nudge_presses_inside_one_second_are_one_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = {"now": 5000.0}
    monkeypatch.setattr(
        "app.features.form_builder.engine.commands.log.time.monotonic",
        lambda: clock["now"],
    )
    log = _log(NUDGE)
    doc = log.document
    three = nid(doc, "three")

    def press() -> bool:
        return nudge(log, doc, (three,), three, "up")

    assert press()
    clock["now"] = 5000.4
    assert press()
    assert _box_names(doc) == ("three", "one", "two")
    assert len(log.entries()) == 1
    assert log.undo()
    assert _box_names(doc) == ("one", "two", "three")
    assert not log.can_undo()


@pytest.mark.parametrize("tile", TILES, ids=lambda tile: tile.class_name)
def test_each_tile_drops_onto_an_empty_box(tile: Tile) -> None:
    log = open_log(build_template_ui("widget", "Form"))
    doc = log.document
    layout = doc.root.layout
    assert isinstance(layout, LayoutNode)
    sight = _canvas(
        (
            _entry(doc.root.id, "widget", (0, 0, 200, 200), None),
            _entry(layout.id, "layout", (0, 0, 200, 200), doc.root.id, z=-1),
        )
    )
    effect = _drop_effect(
        _release(doc, sight, ArmTile(tile.class_name, (80, 24), Point(0, 0), Point(0, 0), "drop:6"), Point(40, 40))
    )
    recipe = effect.target.recipe
    assert isinstance(recipe, Place)
    assert recipe.placement == InBoxLayout(layout.id, 0)
    assert recipe.auto_layout is False
    assert commit(log, effect).moved is True
    laid = doc.root.layout
    assert isinstance(laid, LayoutNode)
    assert len(laid.items) == 1
    content = laid.items[0].content
    if tile.class_name == "Spacer":
        assert isinstance(content, SpacerNode)
        assert content.name == "spacer"
    else:
        assert isinstance(content, WidgetNode)
        assert content.class_name == tile.class_name
        assert content.prop("geometry") is None
        assert prop_text(doc, content.object_name) == tile.text
    assert len(log.entries()) == 1


def test_a_move_leaves_the_document_unchanged_until_commit() -> None:
    log = _log(ORDERED)
    doc = log.document
    layout = doc.root.layout
    assert isinstance(layout, LayoutNode)
    first = nid(doc, "first")
    second = nid(doc, "second")
    sight = _canvas(
        (
            _entry(doc.root.id, "widget", (0, 0, 200, 200), None),
            _entry(layout.id, "layout", (0, 0, 200, 200), doc.root.id, z=-1),
            _entry(first, "widget", (10, 10, 100, 30), layout.id),
            _entry(second, "widget", (10, 80, 100, 30), layout.id),
        )
    )
    original = saved(doc)
    result = _release(
        doc,
        sight,
        ArmCanvas(first, (first,), False, Point(0, 0), Point(0, 0), "drop:7"),
        Point(50, 160),
    )
    assert saved(doc) == original
    assert _box_names(doc) == ("first", "second")
    effect = _drop_effect(result)
    assert commit(log, effect).moved is True
    assert _box_names(doc) == ("second", "first")
    assert len(log.entries()) == 1
    assert log.undo()
    assert _box_names(doc) == ("first", "second")


@pytest.mark.pain("P-1")
def test_blank_form_insert_writes_a_layout_and_no_button_geometry() -> None:
    log = open_log(build_template_ui("widget", "Form"))
    doc = log.document
    layout = doc.root.layout
    assert isinstance(layout, LayoutNode)
    sight = _canvas(
        (
            _entry(doc.root.id, "widget", (0, 0, 200, 200), None),
            _entry(layout.id, "layout", (0, 0, 200, 200), doc.root.id, z=-1),
        )
    )
    effect = _drop_effect(
        _release(doc, sight, ArmTile("QPushButton", (80, 24), Point(0, 0), Point(0, 0), "drop:8"), Point(40, 40))
    )
    assert commit(log, effect).moved is True
    text = saved(doc)
    start = text.index('name="pushButton"')
    end = text.index("</widget>", start)
    assert "geometry" not in text[start:end]
    assert 'class="QVBoxLayout"' in text
    assert 'name="verticalLayout"' in text
    assert len(log.entries()) == 1
    assert log.undo()
    undone = saved(doc)
    assert 'name="verticalLayout"' in undone
    assert "pushButton" not in undone
    restored = doc.root.layout
    assert isinstance(restored, LayoutNode)
    assert restored.items == ()


@pytest.mark.pain("P-4")
def test_line_edit_drops_into_a_nested_horizontal_layout() -> None:
    log = _log(NESTED)
    doc = log.document
    root = doc.root.id
    vbox = nid(doc, "verticalLayout")
    hbox = nid(doc, "horizontalLayout")
    label = nid(doc, "nameLabel")
    sight = _canvas(
        (
            _entry(root, "widget", (0, 0, 200, 200), None),
            _entry(vbox, "layout", (0, 0, 200, 200), root, z=-1),
            _entry(hbox, "layout", (0, 100, 200, 2), vbox, z=-1),
            _entry(label, "widget", (0, 100, 80, 2), hbox),
        )
    )
    effect = _drop_effect(
        _release(doc, sight, ArmTile("QLineEdit", (120, 24), Point(0, 0), Point(0, 0), "drop:9"), Point(120, 101))
    )
    recipe = effect.target.recipe
    assert isinstance(recipe, Place)
    assert recipe.placement == InBoxLayout(hbox, 1)
    assert effect.target.sentence == "Insert after Shop name"
    assert commit(log, effect).moved is True
    vertical = doc.node(vbox)
    horizontal = doc.node(hbox)
    assert isinstance(vertical, LayoutNode)
    assert isinstance(horizontal, LayoutNode)
    assert vertical.class_name == "QVBoxLayout"
    assert horizontal.class_name == "QHBoxLayout"
    names = []
    for item in horizontal.items:
        content = item.content
        assert isinstance(content, WidgetNode)
        names.append(content.object_name)
    assert names == ["nameLabel", "lineEdit"]
    assert len(log.entries()) == 1
