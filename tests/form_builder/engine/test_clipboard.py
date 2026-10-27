"""Clipboard fragment and paste placement. Qt stays out of this module."""

from __future__ import annotations

from typing import Tuple

import pytest

from app.features.form_builder.engine.clipboard import (
    paste_anchor_name,
    paste_auto_layout,
    paste_placement,
    plain_names,
    selectable_ids,
    selection_fragment,
)
from app.features.form_builder.engine.commands.catalog import (
    AddConnection,
    InsertFragment,
    InsertResult,
    SetBuddy,
    SetGeometry,
)
from app.features.form_builder.engine.commands.placement import (
    InBoxLayout,
    InContainer,
    InFormRow,
    InGridCell,
)
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.query.connections import missing_connection_diagnostics
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.spec import Fragment, NodeSpec
from app.features.form_builder.engine.ui4.values import CStringValue, RectValue
from tests.form_builder.engine.commands._support import (
    BOX,
    FREE,
    GRID,
    STACK,
    button_spec,
    cell_of,
    nid,
    open_log,
)

_THREE = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QPushButton" name="top">
     <property name="text"><string>Top</string></property>
    </widget>
   </item>
   <item>
    <widget class="QPushButton" name="middle">
     <property name="text"><string>Mid</string></property>
    </widget>
   </item>
   <item>
    <widget class="QPushButton" name="bottom">
     <property name="text"><string>Bot</string></property>
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

_FULL_GRID = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QGridLayout" name="gridLayout">
   <item row="0" column="0"><widget class="QPushButton" name="a"/></item>
   <item row="0" column="1"><widget class="QPushButton" name="b"/></item>
   <item row="1" column="0"><widget class="QPushButton" name="c"/></item>
   <item row="1" column="1"><widget class="QPushButton" name="d"/></item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="0"><widget class="QLabel" name="nameLabel"/></item>
   <item row="0" column="1"><widget class="QLineEdit" name="nameEdit"/></item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

_PAIR = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QLineEdit" name="email"/></item>
   <item><widget class="QLabel" name="emailLabel"/></item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

_EMAIL_ONLY = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QLineEdit" name="email"/></item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

_FRAME = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <widget class="QFrame" name="frame"/>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _box_names(doc: UiDocument) -> Tuple[str, ...]:
    layout = doc.root.layout
    assert layout is not None
    names = []
    for item in layout.items:
        content = item.content
        if isinstance(content, WidgetNode):
            names.append(content.object_name)
    return tuple(names)


def _buddy_text(spec: NodeSpec) -> str:
    for entry in spec.properties:
        if entry.name == "buddy":
            return getattr(entry.value, "text", "")
    for _slot, kids in spec.slots:
        for child in kids:
            text = _buddy_text(child)
            if text:
                return text
    return ""


@pytest.mark.pain("P-3")
def test_pasting_the_middle_button_inserts_it_and_selects_it() -> None:
    log = open_log(_THREE)
    doc = log.document
    middle = nid(doc, "middle")
    fragment = selection_fragment(doc, (middle,))
    assert plain_names(fragment) == "middle"
    assert fragment.nodes[0].id is None
    place = paste_placement(doc, (middle,))
    assert isinstance(place, InBoxLayout)
    assert place.index == 2
    outcome = log.execute(InsertFragment(place, fragment))
    result = outcome.result
    assert isinstance(result, InsertResult)
    assert _box_names(doc) == ("top", "middle", "middle_2", "bottom")
    assert log.selection.current == result.ids[0]
    assert log.selection.ids == result.ids
    created = doc.node(result.ids[0])
    assert isinstance(created, WidgetNode)
    assert created.object_name == "middle_2"
    log.undo()
    assert _box_names(doc) == ("top", "middle", "bottom")


def test_a_selected_child_is_copied_with_its_parent_once() -> None:
    log = open_log(_THREE)
    doc = log.document
    layout = doc.root.layout
    assert layout is not None
    fragment = selection_fragment(doc, (layout.id, nid(doc, "middle")))
    assert len(fragment.nodes) == 1
    assert fragment.nodes[0].kind == "layout"
    assert plain_names(fragment).splitlines() == ["verticalLayout", "top", "middle", "bottom"]


def test_a_grid_paste_uses_the_next_empty_cell() -> None:
    log = open_log(GRID)
    doc = log.document
    place = paste_placement(doc, (nid(doc, "b"),))
    assert isinstance(place, InGridCell)
    assert (place.row, place.column, place.mode) == (1, 1, "cell")
    log.execute(InsertFragment(place, Fragment(nodes=(button_spec("pasted"),))))
    assert cell_of(doc, "pasted") == (1, 1)


def test_a_full_grid_paste_opens_a_row_under_the_anchor() -> None:
    log = open_log(_FULL_GRID)
    doc = log.document
    place = paste_placement(doc, (nid(doc, "b"),))
    assert isinstance(place, InGridCell)
    assert (place.row, place.column, place.mode) == (1, 1, "insert_row")
    log.execute(InsertFragment(place, Fragment(nodes=(button_spec("pasted"),))))
    assert cell_of(doc, "pasted") == (1, 1)
    assert cell_of(doc, "d") == (2, 1)


def test_two_widgets_pasted_on_a_form_take_two_rows() -> None:
    log = open_log(_FORM)
    doc = log.document
    place = paste_placement(doc, (nid(doc, "nameEdit"),))
    assert isinstance(place, InFormRow)
    assert (place.row, place.role, place.insert_row) == (1, "field", True)
    log.execute(InsertFragment(place, Fragment(nodes=(button_spec("one"), button_spec("two")))))
    assert cell_of(doc, "one")[0] == 1
    assert cell_of(doc, "two")[0] == 2


def test_copy_keeps_references_inside_the_selection() -> None:
    log = open_log(_PAIR)
    doc = log.document
    label = nid(doc, "emailLabel")
    email = nid(doc, "email")
    log.execute(SetBuddy(label, "email"))
    log.execute(AddConnection("email", "textChanged(QString)", "emailLabel", "setText(QString)"))
    log.execute(AddConnection("email", "textChanged(QString)", "missingPerson", "clear()"))
    fragment = selection_fragment(doc, (email, label))
    assert {spec.field("receiver") for spec in fragment.connections} == {"emailLabel", "missingPerson"}
    label_spec = next(spec for spec in fragment.nodes if spec.field("object_name") == "emailLabel")
    assert _buddy_text(label_spec) == "email"
    dropped = selection_fragment(doc, (label,))
    assert len(dropped.connections) == 1
    assert dropped.connections[0].field("sender") == "email"
    assert _buddy_text(dropped.nodes[0]) == ""
    target = open_log(BOX)
    outcome = target.execute(InsertFragment(paste_placement(target.document, ()), dropped))
    result = outcome.result
    assert isinstance(result, InsertResult)
    assert result.dangling == ("email",)


def test_suffix_rename_rewrites_internal_references() -> None:
    source = open_log(_PAIR)
    doc = source.document
    label = nid(doc, "emailLabel")
    email = nid(doc, "email")
    source.execute(SetBuddy(label, "email"))
    source.execute(AddConnection("email", "textChanged(QString)", "emailLabel", "setText(QString)"))
    fragment = selection_fragment(doc, (email, label))
    target = open_log(_EMAIL_ONLY)
    place = paste_placement(target.document, ())
    outcome = target.execute(InsertFragment(place, fragment))
    result = outcome.result
    assert isinstance(result, InsertResult)
    assert ("email", "email_2") in result.renames
    pasted = target.document.node(nid(target.document, "emailLabel"))
    assert isinstance(pasted, WidgetNode)
    buddy = pasted.prop("buddy")
    assert buddy is not None
    assert isinstance(buddy.value, CStringValue)
    assert buddy.value.text == "email_2"
    pairs = [
        (node.field("sender"), node.field("receiver"))
        for node in target.document.connections()
    ]
    assert ("email_2", "emailLabel") in pairs


@pytest.mark.parity("R3-26")
def test_a_fragment_from_one_form_inserts_into_another() -> None:
    source = open_log(BOX)
    fragment = selection_fragment(source.document, (nid(source.document, "label"),))
    before = source.document.fingerprint()
    target = open_log(GRID)
    place = paste_placement(target.document, ())
    target.execute(InsertFragment(place, fragment))
    assert "label" in target.document.names()
    assert cell_of(target.document, "label") == (1, 1)
    assert source.document.fingerprint() == before


def test_an_empty_frame_paste_targets_that_frame() -> None:
    log = open_log(_FRAME)
    doc = log.document
    frame = nid(doc, "frame")
    place = paste_placement(doc, (frame,))
    assert isinstance(place, InContainer)
    assert place.widget == frame
    assert place.index == 0
    assert place.geometry is None


def test_a_free_widget_paste_offsets_its_geometry() -> None:
    log = open_log(FREE)
    doc = log.document
    button = nid(doc, "okButton")
    log.execute(SetGeometry(button, RectValue(10, 20, 40, 30)))
    place = paste_placement(doc, (button,))
    assert isinstance(place, InContainer)
    assert place.widget == doc.root.id
    assert place.geometry is not None
    assert (place.geometry.x, place.geometry.y) == (26, 36)


def test_an_empty_selection_targets_the_end_of_the_root_layout() -> None:
    log = open_log(BOX)
    doc = log.document
    place = paste_placement(doc, ())
    assert isinstance(place, InBoxLayout)
    layout = doc.root.layout
    assert layout is not None
    assert place.layout == layout.id
    assert place.index == len(layout.items)


def test_a_stacked_form_paste_targets_the_current_page() -> None:
    log = open_log(STACK)
    doc = log.document
    place = paste_placement(doc, ())
    assert isinstance(place, InContainer)
    assert place.widget == nid(doc, "pageA")
    assert place.geometry is None


def test_undo_clears_fb014_for_a_missing_connection_end() -> None:
    session = FormSession.open(
        BOX,
        path="/tmp/cbcs-clip.ui",
        scope=FormScope(kind="external", ui_path="/tmp/cbcs-clip.ui"),
    )
    try:
        doc = session.document
        layout = doc.root.layout
        assert layout is not None
        fragment = Fragment(
            nodes=(button_spec("fresh"),),
            connections=(
                NodeSpec(
                    "connection",
                    None,
                    (
                        ("sender", "fresh"),
                        ("signal", "clicked()"),
                        ("receiver", "ghost"),
                        ("slot", "clear()"),
                    ),
                ),
            ),
        )
        outcome = session.log.execute(InsertFragment(InBoxLayout(layout.id, 1), fragment))
        result = outcome.result
        assert isinstance(result, InsertResult)
        assert result.dangling == ("ghost",)
        assert [row.code for row in session.diagnostics.all() if row.code == "FB014"] == ["FB014"]
        session.log.undo()
        assert missing_connection_diagnostics(session.document) == ()
        assert [row.code for row in session.diagnostics.all() if row.code == "FB014"] == []
        session.log.redo()
        assert [row.code for row in session.diagnostics.all() if row.code == "FB014"] == ["FB014"]
    finally:
        session.dispose()


def test_the_anchor_name_is_the_widget_or_the_form() -> None:
    log = open_log(BOX)
    doc = log.document
    assert paste_anchor_name(doc, ()) == "the form"
    assert paste_anchor_name(doc, (doc.root.id,)) == "the form"
    assert paste_anchor_name(doc, (nid(doc, "okButton"),)) == "OK"


def test_a_free_offset_does_not_ask_for_a_new_layout() -> None:
    log = open_log(FREE)
    doc = log.document
    place = paste_placement(doc, (nid(doc, "okButton"),))
    assert paste_auto_layout(place) is False
    boxed = paste_placement(doc, ())
    assert isinstance(boxed, InContainer)
    assert boxed.geometry is not None
    assert paste_auto_layout(boxed) is False


def test_select_all_ids_skip_the_document_node() -> None:
    log = open_log(BOX)
    doc = log.document
    chosen = selectable_ids(doc)
    assert doc.ui.id not in chosen
    assert doc.root.id in chosen
    assert nid(doc, "okButton") in chosen
    layout = doc.root.layout
    assert layout is not None
    assert layout.id in chosen
