"""Layout requests: span loss, offers, confirms, and one undo step per gesture."""

from __future__ import annotations

from typing import Dict, Tuple

import pytest

from app.features.form_builder.engine.commands.log import replay
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.layout_actions import (
    FORM,
    GRID,
    GROUP,
    HORIZONTAL,
    HSPLIT,
    MIXED_PARENT,
    TAB,
    VERTICAL,
    VSPLIT,
    ApplyKind,
    Current,
    Done,
    Measure,
    NeedsConfirm,
    Offer,
    OpenWrap,
    PickWrap,
    Refused,
    RemoveLayout,
    Simplify,
    carry_out,
    gate,
    offers,
    spans_cleared,
    toast_for,
    transact,
)
from app.features.form_builder.engine.ui4.nodes import LayoutItemNode, LayoutNode, WidgetNode
from app.features.form_builder.engine.ui4.values import RectValue, SizeValue
from tests.form_builder.engine.commands._support import BOX, FREE, GRID as FULL_GRID, nid, open_log, saved

_HEAD = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
"""
_TAIL = """ </widget>
 <resources/>
 <connections/>
</ui>
"""

_SPACER = """<spacer name="gap">
     <property name="orientation"><enum>Qt::Vertical</enum></property>
     <property name="sizeHint" stdset="0"><size><width>20</width><height>40</height></size></property>
    </spacer>"""


def _spanned(wide: str, gap: str) -> str:
    return (
        _HEAD
        + """  <layout class="QGridLayout" name="gridLayout">
   <item row="0" column="0" %s>
    <widget class="QLineEdit" name="wide"/>
   </item>
   <item row="2" column="0">
    <widget class="QLabel" name="label"/>
   </item>
   <item row="0" column="2" %s>
    %s
   </item>
  </layout>
"""
        % (wide, gap, _SPACER)
        + _TAIL
    )


def _measured(doc_names: Dict[str, NodeId], rects: Dict[str, Tuple[int, int, int, int]]) -> Dict[NodeId, Measure]:
    return {
        doc_names[name]: Measure(RectValue(*rect), SizeValue(rect[2], rect[3]))
        for name, rect in rects.items()
    }


@pytest.mark.parametrize(
    ("wide", "gap", "new_class", "expected"),
    [
        ('colspan="2"', "", "QFormLayout", 0),
        ('colspan="2"', "", "QVBoxLayout", 1),
        ('rowspan="2"', "", "QFormLayout", 1),
        ('rowspan="2" colspan="2"', "", "QHBoxLayout", 1),
        ("", 'rowspan="2"', "QHBoxLayout", 0),
    ],
)
def test_spans_cleared_counts_widgets_that_lose_a_span(wide: str, gap: str, new_class: str, expected: int) -> None:
    doc = open_log(_spanned(wide, gap)).document

    assert spans_cleared(doc, nid(doc, "gridLayout"), new_class) == expected


def test_a_morph_that_drops_spans_writes_only_after_the_same_confirm() -> None:
    log = open_log(_spanned('colspan="2"', ""))
    doc = log.document
    layout = nid(doc, "gridLayout")

    asked = carry_out(doc, (layout,), ApplyKind(VERTICAL), {}, transact(log))

    assert asked == NeedsConfirm("Spans will be removed from 1 widget.", "Change layout")
    assert isinstance(asked, NeedsConfirm)
    assert log.entries() == ()

    done = carry_out(doc, (layout,), ApplyKind(VERTICAL), {}, transact(log), confirmed=asked.text)

    assert done == Done("Changed the layout and removed spans from 1 widget")
    assert len(log.entries()) == 1
    node = doc.node(layout)
    assert isinstance(node, LayoutNode) and node.class_name == "QVBoxLayout"


def test_a_confirm_for_a_different_sentence_writes_nothing() -> None:
    log = open_log(_spanned('colspan="2"', ""))
    doc = log.document
    before = saved(doc)

    outcome = carry_out(
        doc,
        (nid(doc, "gridLayout"),),
        ApplyKind(VERTICAL),
        {},
        transact(log),
        confirmed="Spans will be removed from 2 widgets.",
    )

    assert isinstance(outcome, Refused)
    assert log.entries() == ()
    assert saved(doc) == before


def test_the_layout_the_form_already_has_is_current() -> None:
    log = open_log(BOX)

    outcome = carry_out(log.document, (), ApplyKind(VERTICAL), {}, transact(log))

    assert outcome == Current()
    assert log.entries() == ()


def test_wrap_is_refused_for_widgets_in_different_layouts() -> None:
    doc = open_log(
        _HEAD
        + """  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QPushButton" name="outer"/></item>
   <item>
    <widget class="QGroupBox" name="box">
     <layout class="QVBoxLayout" name="innerLayout">
      <item><widget class="QPushButton" name="inner"/></item>
     </layout>
    </widget>
   </item>
  </layout>
"""
        + _TAIL
    ).document

    sheet = offers(doc, (nid(doc, "outer"), nid(doc, "inner")), {})

    assert gate(sheet, PickWrap(GROUP)) == Offer(False, MIXED_PARENT)
    assert gate(sheet, OpenWrap()) == Offer(False, MIXED_PARENT)


def test_wrapping_siblings_in_a_group_box_is_one_step() -> None:
    log = open_log(BOX)
    doc = log.document
    ids = (nid(doc, "okButton"), nid(doc, "label"))

    outcome = carry_out(doc, ids, PickWrap(GROUP), {}, transact(log))

    assert outcome == Done("Wrapped 2 widgets in a group box")
    assert len(log.entries()) == 1
    item = doc.parent(ids[0])
    assert item is not None
    owner = doc.owning_widget(item.id)
    assert isinstance(owner, WidgetNode) and owner.class_name == "QGroupBox"


@pytest.mark.parametrize(
    ("text", "kind_id", "host_class"),
    [
        (BOX, HSPLIT, "QSplitter"),
        (BOX, TAB, "QTabWidget"),
        (FREE, VSPLIT, "QSplitter"),
        (FREE, TAB, "QTabWidget"),
        (FREE, GROUP, "QGroupBox"),
        (FREE, GRID, "QWidget"),
    ],
)
def test_a_host_wrap_is_valid_replays_and_selects_the_host(text: str, kind_id: str, host_class: str) -> None:
    log = open_log(text)
    doc = log.document
    before = saved(doc)
    names = {name: nid(doc, name) for name in ("okButton", "label")}
    ids = (names["okButton"], names["label"])
    measured = _measured(names, {"label": (10, 10, 80, 20), "okButton": (10, 40, 80, 24)})

    outcome = carry_out(doc, ids, PickWrap(kind_id), measured, transact(log))

    assert isinstance(outcome, Done), outcome
    (host,) = log.selection.ids
    node = doc.node(host)
    assert isinstance(node, WidgetNode) and node.class_name == host_class
    assert all(host in doc.ancestors(node_id) for node_id in ids)
    assert replay(text, log.entries()).fingerprint() == doc.fingerprint()
    after = saved(doc)

    log.undo()
    assert saved(doc) == before
    log.redo()
    assert saved(doc) == after
    assert log.selection.ids == (host,)


def test_simplify_is_refused_when_the_grid_has_no_gaps() -> None:
    doc = open_log(FULL_GRID).document

    sheet = offers(doc, (nid(doc, "gridLayout"),), {})

    assert gate(sheet, Simplify()) == Offer(False, "This grid has no empty rows or columns.")


@pytest.mark.parity("R3-43")
def test_simplify_closes_a_row_gap_and_its_stretch_in_one_undoable_step() -> None:
    log = open_log(
        _HEAD
        + """  <layout class="QGridLayout" name="gridLayout" rowstretch="1,5,2" rowminimumheight="0,30,0">
   <item row="0" column="0"><widget class="QPushButton" name="a"/></item>
   <item row="2" column="0"><widget class="QPushButton" name="c"/></item>
  </layout>
"""
        + _TAIL
    )
    doc = log.document
    before = saved(doc)
    layout = nid(doc, "gridLayout")

    outcome = carry_out(doc, (layout,), Simplify(), {}, transact(log))

    assert outcome == Done("Removed 1 empty row")
    assert len(log.entries()) == 1
    item = doc.parent(nid(doc, "c"))
    assert isinstance(item, LayoutItemNode) and item.row == 1
    node = doc.node(layout)
    assert node.field("rowstretch") == "1,2"
    assert node.field("rowminimumheight") is None

    log.undo()

    assert saved(doc) == before


def test_remove_layout_deletes_spacers_and_keeps_measured_geometry() -> None:
    log = open_log(
        _HEAD
        + """  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QPushButton" name="go"/></item>
   <item>
    %s
   </item>
  </layout>
"""
        % _SPACER
        + _TAIL
    )
    doc = log.document
    go = nid(doc, "go")
    measured = _measured({"go": go}, {"go": (9, 11, 80, 24)})

    asked = carry_out(doc, (), RemoveLayout(), measured, transact(log))

    assert isinstance(asked, NeedsConfirm)
    assert "Its widget keeps its current position and size" in asked.text
    assert "1 spacer will be removed." in asked.text

    done = carry_out(doc, (), RemoveLayout(), measured, transact(log), confirmed=asked.text)

    assert done == Done("Removed the layout")
    assert len(log.entries()) == 1
    assert doc.root.layout is None
    assert not doc.by_name("gap")
    assert doc.node(go).value("geometry") == RectValue(9, 11, 80, 24)


def test_a_grid_on_free_widgets_takes_rows_and_columns_from_their_bands() -> None:
    log = open_log(
        _HEAD
        + """  <widget class="QPushButton" name="wide"/>
  <widget class="QPushButton" name="left"/>
  <widget class="QPushButton" name="right"/>
"""
        + _TAIL
    )
    doc = log.document
    names = {name: nid(doc, name) for name in ("wide", "left", "right")}
    measured = _measured(
        names,
        {"left": (10, 10, 100, 30), "right": (120, 12, 100, 30), "wide": (10, 50, 210, 30)},
    )

    outcome = carry_out(doc, (), ApplyKind(GRID), measured, transact(log))

    assert outcome == Done("Laid out the form in a grid")
    cells = {}
    for name, node_id in names.items():
        item = doc.parent(node_id)
        assert isinstance(item, LayoutItemNode)
        cells[name] = (item.row, item.column, item.colspan or 1)
    assert cells == {"left": (0, 0, 1), "right": (0, 1, 1), "wide": (1, 0, 2)}


def test_a_form_layout_pairs_each_row_as_label_and_field() -> None:
    log = open_log(
        _HEAD
        + """  <widget class="QLineEdit" name="nameEdit"/>
  <widget class="QLabel" name="nameLabel"/>
  <widget class="QCheckBox" name="agree"/>
"""
        + _TAIL
    )
    doc = log.document
    names = {name: nid(doc, name) for name in ("nameEdit", "nameLabel", "agree")}
    measured = _measured(
        names,
        {"nameLabel": (10, 10, 60, 20), "nameEdit": (80, 8, 150, 24), "agree": (80, 40, 150, 20)},
    )

    carry_out(doc, (), ApplyKind(FORM), measured, transact(log))

    cells = {}
    for name, node_id in names.items():
        item = doc.parent(node_id)
        assert isinstance(item, LayoutItemNode)
        cells[name] = (item.row, item.column)
    assert cells == {"nameLabel": (0, 0), "nameEdit": (0, 1), "agree": (1, 1)}


@pytest.mark.parametrize(
    ("dropped", "expected"),
    [
        ((), "Changed to a plain text box."),
        (("echoMode",), "Changed to a plain text box. 1 property didn't apply: echoMode"),
        (("echoMode", "maxLength"), "Changed to a plain text box. 2 properties didn't apply: echoMode, maxLength"),
    ],
)
def test_toast_for_names_dropped_properties_only_when_there_are_some(dropped: Tuple[str, ...], expected: str) -> None:
    assert toast_for("Changed to a plain text box.", dropped) == expected


def test_a_grid_wider_than_a_form_asks_before_widgets_move() -> None:
    log = open_log(
        _HEAD
        + """  <layout class="QGridLayout" name="gridLayout">
   <item row="0" column="0"><widget class="QPushButton" name="a"/></item>
   <item row="0" column="1"><widget class="QPushButton" name="b"/></item>
   <item row="0" column="2"><widget class="QPushButton" name="c"/></item>
   <item row="1" column="1"><widget class="QPushButton" name="d"/></item>
  </layout>
"""
        + _TAIL
    )
    doc = log.document

    asked = carry_out(doc, (nid(doc, "gridLayout"),), ApplyKind(FORM), {}, transact(log))

    assert asked == NeedsConfirm("1 widget will move to a new row.", "Change layout")
    assert log.entries() == ()


def test_a_grid_asks_before_widgets_leave_their_column() -> None:
    log = open_log(
        _HEAD
        + """  <layout class="QGridLayout" name="gridLayout">
   <item row="0" column="0"><widget class="QPushButton" name="a"/></item>
   <item row="0" column="1"><widget class="QPushButton" name="b"/></item>
   <item row="0" column="2"><widget class="QPushButton" name="c"/></item>
  </layout>
"""
        + _TAIL
    )
    doc = log.document

    asked = carry_out(doc, (nid(doc, "gridLayout"),), ApplyKind(VERTICAL), {}, transact(log))

    assert isinstance(asked, NeedsConfirm)
    assert "2 widgets will move" in asked.text
    assert log.entries() == ()


def test_a_box_asks_before_it_becomes_a_form() -> None:
    log = open_log(
        _HEAD
        + """  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QPushButton" name="a"/></item>
   <item><widget class="QPushButton" name="b"/></item>
   <item><widget class="QPushButton" name="c"/></item>
  </layout>
"""
        + _TAIL
    )
    doc = log.document

    asked = carry_out(doc, (nid(doc, "verticalLayout"),), ApplyKind(FORM), {}, transact(log))

    assert isinstance(asked, NeedsConfirm)
    assert "2 widgets will move." in asked.text
    assert log.entries() == ()


def test_a_designer_horizontal_splitter_is_already_horizontal() -> None:
    log = open_log(
        _HEAD
        + """  <widget class="QSplitter" name="split">
   <property name="orientation"><enum>Qt::Orientation::Horizontal</enum></property>
   <widget class="QTextEdit" name="left"/>
   <widget class="QTextEdit" name="right"/>
  </widget>
"""
        + _TAIL
    )
    doc = log.document
    split = nid(doc, "split")

    outcome = carry_out(doc, (split,), ApplyKind(HSPLIT), {}, transact(log))

    assert isinstance(outcome, Current)
    assert log.entries() == ()
    assert gate(offers(doc, (split,), {}), ApplyKind(HSPLIT)) == Offer(False, "Nothing to change.")


def test_free_widgets_beside_a_layout_are_not_offered_a_wrap() -> None:
    log = open_log(
        _HEAD
        + """  <widget class="QPushButton" name="freeOne">
   <property name="geometry"><rect><x>10</x><y>10</y><width>80</width><height>24</height></rect></property>
  </widget>
  <widget class="QPushButton" name="freeTwo">
   <property name="geometry"><rect><x>100</x><y>10</y><width>80</width><height>24</height></rect></property>
  </widget>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QLabel" name="placed"><property name="text"><string>In</string></property></widget></item>
  </layout>
"""
        + _TAIL
    )
    doc = log.document
    ids = (nid(doc, "freeOne"), nid(doc, "freeTwo"))
    measured = _measured(
        {"freeOne": ids[0], "freeTwo": ids[1]},
        {"freeOne": (10, 10, 80, 24), "freeTwo": (100, 10, 80, 24)},
    )

    sheet = offers(doc, ids, measured)
    refused = Offer(False, "That container already has a layout.")

    assert gate(sheet, ApplyKind(HORIZONTAL)) == refused
    assert gate(sheet, PickWrap(HORIZONTAL)) == refused
    assert gate(sheet, OpenWrap()) == refused
    assert carry_out(doc, ids, ApplyKind(HORIZONTAL), measured, transact(log)) == Refused(
        "That container already has a layout."
    )
    assert log.entries() == ()


def test_remove_layout_names_every_spacer_it_will_delete() -> None:
    log = open_log(
        _HEAD
        + """  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QPushButton" name="go"/></item>
   <item>%s</item>
   <item>%s</item>
  </layout>
"""
        % (_SPACER, _SPACER.replace('name="gap"', 'name="gap2"'))
        + _TAIL
    )
    doc = log.document
    go = nid(doc, "go")

    asked = carry_out(doc, (), RemoveLayout(), _measured({"go": go}, {"go": (9, 11, 80, 24)}), transact(log))

    assert isinstance(asked, NeedsConfirm)
    assert "2 spacers will be removed." in asked.text
