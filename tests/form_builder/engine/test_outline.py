"""Outline forest, gesture policy, and one-entry edits."""

from __future__ import annotations

import os
import random
from typing import List, Tuple

import pytest

from app.features.form_builder.engine.commands.catalog import (
    ApplyLayout,
    DeleteNodes,
    MoveNodes,
    MovePage,
    SetBuddy,
    SetLayoutCell,
    SetProperty,
    SetTabStops,
)
from app.features.form_builder.engine.commands.catalog_ext.drop import AdoptIntoBox
from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.log import CommandLog
from app.features.form_builder.engine.events import ChangeSet
from app.features.form_builder.engine.commands.placement import InBoxLayout
from app.features.form_builder.engine.query.drop_target import DropPayload, OutlineRow as PixelRow
from app.features.form_builder.engine.query.outline import (
    AskDelete,
    BareNest,
    CloseName,
    Commit,
    FilterSet,
    Flash,
    Idle,
    InPageSlot,
    KeyGesture,
    NameInvalid,
    Navigate,
    OutlineCursor,
    OutlineWorld,
    RenameGesture,
    Route,
    filter_mask,
    layout_row,
    patch_captions,
    outline_mode,
    patch_structure,
    plan,
    project,
    structure_touched,
    captions_touched,
)
from app.features.form_builder.engine.query.ref_index import RefIndex
from app.features.form_builder.engine.shell_commands import outline_command_for
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutNode, WidgetNode
from app.features.form_builder.engine.ui4.values import NumberValue, StringValue
from tests.form_builder.engine.commands._support import BOX, FREE, SHARED, nid, open_log

_METHODS = frozenset({"close", "show", "update", "accept", "reject", "done", "print"})
_IDENTIFIER = "Names use letters, digits and _, and can't start with a digit."
_NOWHERE = "Nothing above to nest into."


def _friendly(name: str) -> str:
    if name == "QPushButton":
        return "Push button"
    if name == "QLabel":
        return "Label"
    if name == "QVBoxLayout":
        return "Vertical layout"
    return name


def _world(doc: UiDocument) -> OutlineWorld:
    index = RefIndex()
    index.rebuild(doc)
    return OutlineWorld(index, friendly_of=_friendly)


def _forest(doc: UiDocument):
    return project(doc, frozenset(), _friendly)


def _focus(node):
    return OutlineCursor(anchor=node, focus=node, selected=(node,))


def _ui(body: str) -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
%s
 </widget>
 <resources/>
 <connections/>
</ui>
""" % body


def _contents(doc: UiDocument, layout_name: str) -> Tuple[str, ...]:
    layout = doc.node(nid(doc, layout_name))
    assert isinstance(layout, LayoutNode)
    names = []
    for item in layout.items:
        content = item.content
        if isinstance(content, WidgetNode):
            names.append(content.object_name)
    return tuple(names)


def _pages(doc: UiDocument, host_name: str) -> Tuple[str, ...]:
    host = doc.node(nid(doc, host_name))
    assert isinstance(host, WidgetNode)
    return tuple(child.object_name for child in host.child_widgets)


def _current(doc: UiDocument, host_name: str) -> int:
    host = doc.node(nid(doc, host_name))
    entry = host.prop("currentIndex")
    if entry is None or not isinstance(entry.value, NumberValue):
        return 0
    return int(entry.value.value)


def _apply(log: CommandLog, effect: object) -> None:
    if isinstance(effect, BareNest):
        with log.transaction("Nest") as txn:
            layout_id = txn.execute(ApplyLayout(effect.container, effect.layout_class))
            layout = log.document.node(layout_id)
            end = len(layout.items) if isinstance(layout, LayoutNode) else 0
            txn.execute(MoveNodes(effect.ids, InBoxLayout(layout_id, end)))
        return
    assert isinstance(effect, Commit)
    if len(effect.commands) == 1:
        log.execute(effect.commands[0])
        return
    with log.transaction(effect.label) as txn:
        for command in effect.commands:
            txn.execute(command)


_GROUPED = _ui(
    """
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QGroupBox" name="group">
     <layout class="QVBoxLayout" name="groupLayout">
      <item><widget class="QPushButton" name="inside"/></item>
     </layout>
    </widget>
   </item>
   <item><widget class="QPushButton" name="outside"/></item>
  </layout>
"""
)

_EMPTY_GROUP = _ui(
    """
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QGroupBox" name="group"/></item>
   <item><widget class="QPushButton" name="outside"/></item>
  </layout>
"""
)

_FREE_GROUP = _ui(
    """
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QGroupBox" name="group">
     <widget class="QPushButton" name="kept"/>
    </widget>
   </item>
   <item><widget class="QPushButton" name="outside"/></item>
  </layout>
"""
)


def test_tab_nests_into_the_previous_container() -> None:
    log = open_log(_GROUPED)
    doc = log.document
    outside = nid(doc, "outside")
    effect = plan(doc, _forest(doc), _focus(outside), KeyGesture("form.action.outlineNest"), _world(doc))
    assert isinstance(effect, Commit)
    assert len(effect.commands) == 1
    assert isinstance(effect.commands[0], MoveNodes)
    _apply(log, effect)
    assert _contents(log.document, "groupLayout") == ("inside", "outside")
    assert _contents(log.document, "verticalLayout") == ("group",)
    assert log.undo()
    assert _contents(log.document, "groupLayout") == ("inside",)
    assert not log.can_undo()


def test_tab_on_the_first_sibling_flashes() -> None:
    log = open_log(_GROUPED)
    doc = log.document
    group = nid(doc, "group")
    effect = plan(doc, _forest(doc), _focus(group), KeyGesture(key="tab"), _world(doc))
    assert isinstance(effect, Flash)
    assert effect.node == group
    assert effect.prose == _NOWHERE
    assert not log.can_undo()


def test_shift_tab_moves_after_the_parent_container() -> None:
    log = open_log(_GROUPED)
    doc = log.document
    inside = nid(doc, "inside")
    effect = plan(doc, _forest(doc), _focus(inside), KeyGesture("form.action.outlineUnnest"), _world(doc))
    assert isinstance(effect, Commit)
    _apply(log, effect)
    assert _contents(log.document, "verticalLayout") == ("group", "inside", "outside")
    assert _contents(log.document, "groupLayout") == ()
    assert log.undo()
    assert _contents(log.document, "groupLayout") == ("inside",)
    assert not log.can_undo()


def test_empty_container_uses_adopt() -> None:
    log = open_log(_EMPTY_GROUP)
    doc = log.document
    outside = nid(doc, "outside")
    effect = plan(doc, _forest(doc), _focus(outside), KeyGesture(key="tab"), _world(doc))
    assert isinstance(effect, Commit)
    assert isinstance(effect.commands[0], AdoptIntoBox)
    _apply(log, effect)
    assert _contents(log.document, "verticalLayout") == ("group",)
    group = log.document.node(nid(log.document, "group"))
    assert isinstance(group, WidgetNode)
    assert group.layout is not None
    assert _contents(log.document, group.layout.object_name) == ("outside",)
    assert log.undo()
    assert not log.can_undo()


def test_free_children_use_one_bare_nest_entry() -> None:
    log = open_log(_FREE_GROUP)
    doc = log.document
    outside = nid(doc, "outside")
    effect = plan(doc, _forest(doc), _focus(outside), KeyGesture(key="tab"), _world(doc))
    assert isinstance(effect, BareNest)
    assert effect.layout_class == "QVBoxLayout"
    assert effect.ids == (outside,)
    _apply(log, effect)
    group = log.document.node(nid(log.document, "group"))
    assert isinstance(group, WidgetNode)
    assert group.layout is not None
    assert _contents(log.document, group.layout.object_name) == ("kept", "outside")
    assert log.undo()
    restored = log.document.node(nid(log.document, "group"))
    assert isinstance(restored, WidgetNode)
    assert restored.layout is None
    assert not log.can_undo()


def test_alt_down_nudges_a_box_sibling() -> None:
    log = open_log(BOX)
    doc = log.document
    button = nid(doc, "okButton")
    before = _contents(doc, "verticalLayout")
    effect = plan(doc, _forest(doc), _focus(button), KeyGesture("form.action.moveOrNudgeDown"), _world(doc))
    assert isinstance(effect, Commit)
    assert isinstance(effect.commands[0], MoveNodes)
    _apply(log, effect)
    assert _contents(log.document, "verticalLayout") != before
    assert log.undo()
    assert _contents(log.document, "verticalLayout") == before
    assert not log.can_undo()


def _tabs(attr: str, title: str, host: str = "QTabWidget") -> str:
    return _ui(
        """
  <widget class="%s" name="tabs">
   <property name="currentIndex"><number>0</number></property>
   <widget class="QWidget" name="pageA">
    <attribute name="%s"><string>%s</string></attribute>
   </widget>
   <widget class="QWidget" name="pageB"/>
  </widget>
"""
        % (host, attr, title)
    )


def test_page_primary_uses_the_page_title() -> None:
    doc = open_log(_tabs("title", "Settings")).document
    row = _forest(doc).row(nid(doc, "pageA"))
    assert row is not None
    assert isinstance(row.slot, InPageSlot)
    assert row.primary == "pageA"
    assert row.visible_text == "Settings"
    untitled = _forest(doc).row(nid(doc, "pageB"))
    assert untitled is not None
    assert untitled.primary == "pageB"


def test_toolbox_page_uses_its_label() -> None:
    doc = open_log(_tabs("label", "Tools", "QToolBox")).document
    row = _forest(doc).row(nid(doc, "pageA"))
    assert row is not None
    assert row.primary == "pageA"
    assert row.visible_text == "Tools"


def test_stacked_page_without_a_title() -> None:
    doc = open_log(
        _ui(
            """
  <widget class="QStackedWidget" name="stack">
   <widget class="QWidget" name="pageA"/>
  </widget>
"""
        )
    ).document
    row = _forest(doc).row(nid(doc, "pageA"))
    assert row is not None
    assert row.kind == "page"
    assert row.primary == "pageA"


def test_alt_down_moves_a_page() -> None:
    log = open_log(_tabs("title", "Settings"))
    doc = log.document
    page = nid(doc, "pageA")
    effect = plan(doc, _forest(doc), _focus(page), KeyGesture("form.action.moveOrNudgeDown", alt=True), _world(doc))
    assert isinstance(effect, Commit)
    assert isinstance(effect.commands[0], MovePage)
    _apply(log, effect)
    assert _pages(log.document, "tabs") == ("pageB", "pageA")
    assert _current(log.document, "tabs") == 1
    assert log.undo()
    assert _pages(log.document, "tabs") == ("pageA", "pageB")
    assert _current(log.document, "tabs") == 0
    assert not log.can_undo()


def test_alt_down_on_the_last_page_does_nothing() -> None:
    log = open_log(_tabs("title", "Settings"))
    doc = log.document
    page = nid(doc, "pageB")
    effect = plan(doc, _forest(doc), _focus(page), KeyGesture(key="down", alt=True), _world(doc))
    assert isinstance(effect, Flash)
    assert effect.node == page
    assert effect.prose == "pageB is already the last page."
    assert not log.can_undo()


def test_dragging_a_page_onto_its_sibling_reorders() -> None:
    log = open_log(_tabs("title", "Settings"))
    doc = log.document
    page_a = nid(doc, "pageA")
    page_b = nid(doc, "pageB")
    rows = (PixelRow(page_a, 0, 24, 180, 0), PixelRow(page_b, 24, 24, 180, 16))
    effect = plan(
        doc,
        _forest(doc),
        _focus(page_b),
        __drop(page_b, rows, 4),
        _world(doc),
    )
    assert isinstance(effect, Commit)
    assert isinstance(effect.commands[0], MovePage)
    _apply(log, effect)
    assert _pages(log.document, "tabs") == ("pageB", "pageA")
    assert log.undo()
    assert not log.can_undo()


def test_dragging_a_page_outside_its_container_flashes() -> None:
    log = open_log(_tabs("title", "Settings"))
    doc = log.document
    form = nid(doc, "Form")
    page = nid(doc, "pageB")
    effect = plan(
        doc,
        _forest(doc),
        _focus(page),
        __drop(page, (PixelRow(form, 0, 30, 180, 0),), 15),
        _world(doc),
    )
    assert isinstance(effect, Flash)
    assert effect.prose == "A page stays inside its container."


def __drop(source, rows, y: int):
    from app.features.form_builder.engine.query.outline import DropGesture

    return DropGesture(8, y, True, DropPayload("widget", (source,)), rows)


def test_invalid_rename_does_not_commit() -> None:
    log = open_log(BOX)
    doc = log.document
    label = nid(doc, "label")
    effect = plan(doc, _forest(doc), _focus(label), RenameGesture(label, "1email", "next"), _world(doc))
    assert isinstance(effect, NameInvalid)
    assert effect.prose == _IDENTIFIER


def test_a_window_method_is_refused_inline() -> None:
    log = open_log(BOX)
    doc = log.document
    label = nid(doc, "label")
    world = _world(doc)
    world = OutlineWorld(world.index, _METHODS, friendly_of=_friendly)
    effect = plan(doc, _forest(doc), _focus(label), RenameGesture(label, "close", "commit"), world)
    assert isinstance(effect, NameInvalid)
    assert effect.prose == "\u201cclose\u201d would replace a method of the window. Try closeButton."


def test_tab_commits_a_valid_name_on_the_next_row() -> None:
    log = open_log(BOX)
    doc = log.document
    button = nid(doc, "okButton")
    label = nid(doc, "label")
    effect = plan(doc, _forest(doc), _focus(button), RenameGesture(button, "submit", "next"), _world(doc))
    assert isinstance(effect, CloseName)
    assert effect.new_name == "submit"
    assert effect.then_node == label


def test_escape_cancels_rename() -> None:
    log = open_log(BOX)
    doc = log.document
    button = nid(doc, "okButton")
    effect = plan(doc, _forest(doc), _focus(button), RenameGesture(button, "nope", "cancel"), _world(doc))
    assert isinstance(effect, CloseName)
    assert effect.new_name is None
    assert effect.then_node is None


def test_filter_keeps_ancestors() -> None:
    doc = open_log(BOX).document
    forest = _forest(doc)
    mask = filter_mask(forest, "Push")
    states = dict(mask.state)
    assert states[nid(doc, "okButton")] == "match"
    assert states[nid(doc, "label")] == "hidden"
    assert states[nid(doc, "verticalLayout")] == "ancestor"
    assert states[nid(doc, "Form")] == "ancestor"
    assert mask.first_match == nid(doc, "okButton")
    assert mask.empty is False


def test_filter_empty_query_matches_every_row() -> None:
    doc = open_log(BOX).document
    mask = filter_mask(_forest(doc), "")
    assert mask.empty is False
    assert {state for _node, state in mask.state} == {"match"}


def test_filter_with_no_match_is_empty() -> None:
    doc = open_log(BOX).document
    mask = filter_mask(_forest(doc), "zzz")
    assert mask.empty is True
    assert mask.first_match is None


def test_filter_enter_selects_the_first_match() -> None:
    doc = open_log(BOX).document
    button = nid(doc, "okButton")
    effect = plan(doc, _forest(doc), _focus(nid(doc, "Form")), __filter("OK", "enter"), _world(doc))
    assert isinstance(effect, FilterSet)
    assert effect.select == button
    assert effect.focus_tree is False
    assert effect.text == "OK"


def test_filter_clear_returns_to_the_tree() -> None:
    doc = open_log(BOX).document
    effect = plan(doc, _forest(doc), _focus(nid(doc, "Form")), __filter("OK", "clear"), _world(doc))
    assert isinstance(effect, FilterSet)
    assert effect.text == ""
    assert effect.focus_tree is True
    assert effect.select is None


def __filter(text: str, how: str):
    from app.features.form_builder.engine.query.outline import FilterGesture

    return FilterGesture(text, how)


@pytest.mark.parametrize("width", [80, 120, 200, 236])
@pytest.mark.parametrize("caption", [False, True])
@pytest.mark.parametrize("problem", [False, True])
def test_layout_boxes_do_not_overlap(width: int, caption: bool, problem: bool) -> None:
    boxes = layout_row(width, caption, problem)
    rects = [boxes.glyph, boxes.name]
    if boxes.caption is not None:
        rects.append(boxes.caption)
        assert boxes.name[2] >= 24
    if boxes.problem is not None:
        rects.append(boxes.problem)
    for left, top, box_width, box_height in rects:
        assert left >= 0 and top >= 0
        assert left + box_width <= width
        assert top + box_height <= 24
    for index, rect in enumerate(rects):
        for other in rects[index + 1 :]:
            assert not _overlaps(rect, other)


@pytest.mark.parametrize(
    ("width", "name_px", "caption_px", "caption", "name_elides"),
    [
        (236, 80, 100, True, False),  # both fit
        (236, 80, 140, False, False),  # the caption goes first; the name stays whole
        (198, 150, 40, False, False),  # the name alone fits
        (198, 220, 10, False, True),  # only now does the name elide
    ],
)
def test_the_caption_goes_before_the_name_elides(
    width: int, name_px: int, caption_px: int, caption: bool, name_elides: bool
) -> None:
    boxes = layout_row(width, True, False, caption_px=caption_px, name_px=name_px)
    assert (boxes.caption is not None) == caption
    assert boxes.name_elides == name_elides
    if boxes.caption is not None:
        assert boxes.name[2] == name_px
        assert boxes.caption[2] == caption_px
    elif not name_elides:
        assert boxes.name[2] >= name_px


def _overlaps(rect: Tuple[int, int, int, int], other: Tuple[int, int, int, int]) -> bool:
    left, top, width, height = rect
    other_left, other_top, other_width, other_height = other
    if width <= 0 or height <= 0 or other_width <= 0 or other_height <= 0:
        return False
    return left < other_left + other_width and other_left < left + width and top < other_top + other_height and other_top < top + height


def test_unreferenced_delete_is_one_command() -> None:
    log = open_log(BOX)
    doc = log.document
    label = nid(doc, "label")
    effect = plan(doc, _forest(doc), _focus(label), KeyGesture("form.action.delete"), _world(doc))
    assert isinstance(effect, Commit)
    assert isinstance(effect.commands[0], DeleteNodes)
    assert effect.toast == "Deleted label \u00b7 Undo"
    _apply(log, effect)
    assert log.document.by_name("label") == ()
    assert log.undo()
    assert not log.can_undo()


def test_a_tab_stop_does_not_ask_before_delete() -> None:
    log = open_log(FREE)
    log.execute(SetTabStops(("okButton",)))
    doc = log.document
    button = nid(doc, "okButton")
    effect = plan(doc, _forest(doc), _focus(button), KeyGesture(key="backspace"), _world(doc))
    assert isinstance(effect, Commit)
    assert effect.toast == "Deleted okButton \u00b7 Undo"


def test_referenced_delete_asks() -> None:
    log = open_log(FREE)
    label = nid(log.document, "label")
    log.execute(SetBuddy(label, "okButton"))
    doc = log.document
    button = nid(doc, "okButton")
    effect = plan(doc, _forest(doc), _focus(button), KeyGesture("form.action.delete"), _world(doc))
    assert isinstance(effect, AskDelete)
    assert "is used by" in effect.prose
    assert "buddy" in effect.prose
    assert effect.ids == (button,)


def test_shared_name_deletes_without_asking() -> None:
    log = open_log(SHARED)
    doc = log.document
    target = doc.by_name("same")[0]
    effect = plan(doc, _forest(doc), _focus(target), KeyGesture("form.action.delete"), _world(doc))
    assert isinstance(effect, Commit)
    assert isinstance(effect.commands[0], DeleteNodes)


def test_the_form_itself_cannot_be_deleted() -> None:
    log = open_log(BOX)
    doc = log.document
    form = nid(doc, "Form")
    effect = plan(doc, _forest(doc), _focus(form), KeyGesture(key="delete"), _world(doc))
    assert isinstance(effect, Flash)
    assert effect.prose == "The form itself can't be deleted."


def test_copy_routes_to_its_action() -> None:
    log = open_log(BOX)
    doc = log.document
    effect = plan(doc, _forest(doc), _focus(nid(doc, "label")), KeyGesture("form.action.copy"), _world(doc))
    assert isinstance(effect, Route)
    assert effect.action_id == "form.action.copy"


def test_a_layout_shortcut_does_not_move_the_row() -> None:
    log = open_log(BOX)
    doc = log.document
    effect = plan(doc, _forest(doc), _focus(nid(doc, "label")), KeyGesture("form.action.zoomToFit"), _world(doc))
    assert isinstance(effect, Idle)


def test_grid_rows_follow_reading_order() -> None:
    text = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0"><class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QGridLayout" name="grid">
   <item row="1" column="0"><widget class="QPushButton" name="lower"/></item>
   <item row="0" column="0"><widget class="QPushButton" name="upper"/></item>
  </layout>
 </widget>
</ui>
"""
    doc = open_log(text).document
    names = tuple(row.name for row in _forest(doc).rows)
    assert names.index("upper") < names.index("lower")


def test_escape_selects_the_parent() -> None:
    doc = open_log(BOX).document
    label = nid(doc, "label")
    effect = plan(doc, _forest(doc), _focus(label), KeyGesture("form.action.escape"), _world(doc))
    assert isinstance(effect, Navigate)
    assert effect.current == nid(doc, "verticalLayout")


def test_down_selects_the_next_row() -> None:
    log = open_log(BOX)
    doc = log.document
    form = nid(doc, "Form")
    layout = nid(doc, "verticalLayout")
    effect = plan(doc, _forest(doc), _focus(form), KeyGesture(key="down"), _world(doc))
    assert isinstance(effect, Navigate)
    assert effect.current == layout


def test_caption_patch_keeps_untouched_rows() -> None:
    log = open_log(BOX)
    doc = log.document
    forest = _forest(doc)
    button = nid(doc, "okButton")
    label = nid(doc, "label")
    label_row = forest.row(label)
    pending = []
    log.subscribe(lambda change_set: pending.append(change_set), priority=0)
    log.execute(SetProperty(button, "text", StringValue("Save")))
    assert not structure_touched(pending[-1])
    assert button in captions_touched(pending[-1])
    patched = patch_captions(forest, log.document, captions_touched(pending[-1]), frozenset(), _friendly)
    assert patched.row(label) is label_row
    button_row = patched.row(button)
    assert button_row is not None
    assert button_row.visible_text == "Save"


@pytest.mark.parametrize(
    ("key", "command"),
    [
        ("Tab", "form.action.outlineNest"),
        ("Backtab", "form.action.outlineUnnest"),
        ("Ctrl+F", "form.action.find"),
        ("Alt+Down", "form.action.moveOrNudgeDown"),
        ("Ctrl+X", "form.action.cut"),
        ("Delete", "form.action.delete"),
        ("", ""),
    ],
)
def test_outline_key_resolves_to_its_command(key: str, command: str) -> None:
    assert outline_command_for(key) == command


_GRID = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0"><class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QGridLayout" name="grid">
   <item row="0" column="0"><widget class="QLabel" name="cellA"><property name="text"><string>A</string></property></widget></item>
   <item row="0" column="1"><widget class="QLabel" name="cellB"><property name="text"><string>B</string></property></widget></item>
   <item row="1" column="0"><widget class="QLabel" name="cellC"><property name="text"><string>C</string></property></widget></item>
  </layout>
 </widget>
</ui>
"""


def _names(doc: UiDocument) -> Tuple[str, ...]:
    return tuple(row.name for row in _forest(doc).rows)


def test_alt_up_on_the_first_page_says_why() -> None:
    doc = open_log(_tabs("title", "First")).document
    page = nid(doc, "pageA")
    effect = plan(doc, _forest(doc), _focus(page), KeyGesture("form.action.moveOrNudgeUp", alt=True), _world(doc))
    assert isinstance(effect, Flash)
    assert effect.node == page
    assert effect.prose == "pageA is already the first page."


def test_shift_tab_at_the_top_level_says_why() -> None:
    text = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0"><class>Form</class>
 <widget class="QWidget" name="Form">
  <widget class="QPushButton" name="okButton"/>
 </widget>
</ui>
"""
    doc = open_log(text).document
    button = nid(doc, "okButton")
    effect = plan(doc, _forest(doc), _focus(button), KeyGesture(key="backtab", shift=True), _world(doc))
    assert isinstance(effect, Flash)
    assert effect.prose == "okButton is already at the top level."


def test_a_cell_move_reorders_only_that_layout() -> None:
    log = open_log(_GRID)
    doc = log.document
    forest = _forest(doc)
    cell_a = forest.row(nid(doc, "cellA"))
    cell_b = doc.node(nid(doc, "cellB"))
    item = doc.parent(cell_b.id)
    assert item is not None
    pending = []
    log.subscribe(pending.append, priority=1)
    log.execute(SetLayoutCell(item.id, 1, 1, 1, 1))
    patch = patch_structure(forest, log.document, pending[-1], frozenset(), _friendly)
    assert patch is not None
    assert tuple(row.name for row in forest.rows) == _names(log.document)
    assert forest.row(nid(log.document, "cellA")) is cell_a
    assert len(patch.placed) == 1  # one row moves; the others keep their items
    pending.clear()
    log.undo()
    assert patch_structure(forest, log.document, pending[-1], frozenset(), _friendly) is not None
    assert tuple(row.name for row in forest.rows) == _names(log.document)


def test_deleting_a_grid_cell_selects_the_next_widget() -> None:
    log = open_log(_GRID)
    log.execute(DeleteNodes((nid(log.document, "cellA"),)))
    current = log.selection.current
    assert current is not None
    assert current == nid(log.document, "cellB")
    assert log.document.node(current).kind == "widget"


def _drive(seed: int, steps: int) -> None:
    """Random edits, undos and redos. After each ChangeSet the patched forest equals ``project``."""
    from tests.support.form_builder.gen import FORMS, command_for

    rng = random.Random(seed)
    log = open_log(FORMS[seed % len(FORMS)])
    held = {"forest": _forest(log.document)}
    stats = {"structure": 0}

    def follow(change_set: ChangeSet) -> None:
        doc = log.document
        forest = held["forest"]
        mode = outline_mode(change_set)
        if mode == "structure":
            stats["structure"] += 1
            patch = patch_structure(forest, doc, change_set, frozenset(), _friendly)
            assert patch is not None, "FB_SEED=%s %s fell back to a rebuild" % (seed, change_set.label)
        elif mode == "captions":
            patch_captions(forest, doc, captions_touched(change_set), frozenset(), _friendly)
        elif mode == "rebuild":
            forest = held["forest"] = _forest(doc)  # a replaced document is the one allowed rebuild
        expected = _forest(doc).rows
        assert forest.rows == expected, "FB_SEED=%s after %s %s" % (seed, change_set.origin, change_set.label)

    log.subscribe(follow, priority=1)
    done = 0
    for attempt in range(steps * 6):
        if done >= steps:
            break
        roll = rng.randrange(10)
        if roll < 2 and log.can_undo():
            log.undo()
        elif roll == 2 and log.can_redo():
            log.redo()
        elif roll == 3:
            commands = [command_for(log.document, rng, seed * 1000 + attempt) for _ in range(3)]
            try:
                with log.transaction("T") as txn:
                    for command in commands:
                        if command is not None:
                            txn.execute(command)
            except CommandRejected:
                continue
        else:
            command = command_for(log.document, rng, seed * 1000 + attempt)
            if command is None:
                continue
            try:
                log.execute(command)
            except CommandRejected:
                continue
        done += 1
    while log.undo():
        pass
    while log.redo():
        pass
    assert stats["structure"] > 0


def _seeds() -> List[int]:
    chosen = os.environ.get("FB_SEED")
    if chosen:
        return [int(chosen)]
    return list(range(28))


@pytest.mark.parametrize("seed", _seeds())
def test_patched_outline_matches_a_fresh_projection(seed: int) -> None:
    _drive(seed, 40)


_NESTED = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0"><class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="outer">
   <item><widget class="QGroupBox" name="box">
    <layout class="QVBoxLayout" name="boxLayout">
     <item><widget class="QLabel" name="inner"/></item>
    </layout>
   </widget></item>
   <item><widget class="QGroupBox" name="holder">
    <layout class="QVBoxLayout" name="holderLayout">
     <item><widget class="QFrame" name="frame">
      <layout class="QVBoxLayout" name="frameLayout">
       <item><widget class="QLabel" name="deep"/></item>
      </layout>
     </widget></item>
    </layout>
   </widget></item>
   <item><widget class="QTabWidget" name="tabs">
    <widget class="QWidget" name="pageA"><attribute name="title"><string>First</string></attribute></widget>
    <widget class="QWidget" name="pageB"><attribute name="title"><string>Second</string></attribute></widget>
    <widget class="QWidget" name="pageC"><attribute name="title"><string>Third</string></attribute></widget>
   </widget></item>
  </layout>
 </widget>
</ui>
"""


@pytest.mark.parametrize(
    "command",
    [
        lambda doc: MoveNodes((nid(doc, "box"),), InBoxLayout(nid(doc, "frameLayout"), 0)),
        lambda doc: MoveNodes((nid(doc, "frame"),), InBoxLayout(nid(doc, "outer"), 0)),
        lambda doc: MovePage(nid(doc, "tabs"), 0, 2),
        lambda doc: DeleteNodes((nid(doc, "pageA"),)),
    ],
    ids=["deeper", "shallower", "page-move", "page-delete"],
)
def test_a_patched_move_keeps_depths_and_page_numbers(command) -> None:
    log = open_log(_NESTED)
    forest = _forest(log.document)
    pending: List[ChangeSet] = []
    log.subscribe(pending.append, priority=1)
    log.execute(command(log.document))
    for origin in ("do", "undo", "redo"):
        if origin == "undo":
            log.undo()
        elif origin == "redo":
            log.redo()
        assert patch_structure(forest, log.document, pending[-1], frozenset(), _friendly) is not None
        assert forest.rows == _forest(log.document).rows, origin
