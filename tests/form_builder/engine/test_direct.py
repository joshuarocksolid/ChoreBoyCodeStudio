"""Direct-manipulation knobs turn stored numbers. Geometry is a hand-built survey."""

from __future__ import annotations

from typing import Optional, Tuple

import pytest

from app.features.form_builder.engine.commands.catalog_ext.sizing import write_share
from app.features.form_builder.engine.commands.log import CommandLog
from app.features.form_builder.engine.ids import IdAllocator, NodeId
from app.features.form_builder.engine.logic.storage import splitter_sizes
from app.features.form_builder.engine.query.direct import (
    FREE_PULLS,
    How,
    Knob,
    LayoutFacts,
    PrimaryFacts,
    SplitterFacts,
    Survey,
    Track,
    Turn,
    equal_sizes,
    knob_set,
    reset,
    survey_scope,
    turn,
)
from app.features.form_builder.engine.query.hit_index import Rect
from app.features.form_builder.engine.sizing import PaneShare, read_share, share_slots
from app.features.form_builder.engine.ui4.nodes import LayoutItemNode, LayoutNode, WidgetNode
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.engine.ui4.values import RectValue, SizePolicyValue, SizeValue
from tests.form_builder.engine.commands._support import BOX, FREE, GRID, nid, open_log, saved

_SPLIT = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QLabel" name="label"/>
   </item>
   <item>
    <widget class="QSplitter" name="splitter">%s
     <widget class="QTextEdit" name="left"/>
     <widget class="QTextEdit" name="right"/>
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""
_VERTICAL = '\n     <property name="orientation"><enum>Qt::Vertical</enum></property>'
_STRETCHED = (
    '\n     <property name="sizePolicy"><sizepolicy hsizetype="Preferred" vsizetype="Preferred">'
    "<horstretch>2</horstretch><verstretch>0</verstretch></sizepolicy></property>"
)

_BOX_RECT = Rect(0, 0, 200, 100)
_BOX_COLUMNS = (Track(9, 191),)
_BOX_ROWS = (Track(9, 40), Track(46, 91))
_GRID_COLUMNS = (Track(9, 100), Track(106, 191))
_GRID_ROWS = (Track(9, 40), Track(46, 77))
_PREFERRED = ("Preferred", "Preferred")


def _box_facts(log: CommandLog, hidden: Tuple[str, ...] = ()) -> LayoutFacts:
    layout = log.document.get(nid(log.document, "verticalLayout"))
    assert isinstance(layout, LayoutNode)
    shown = [item.content.id for item in layout.items if item.content is not None]
    shown = [node for node in shown if node not in {nid(log.document, name) for name in hidden}]
    rows = tuple(Track(track.start, track.end, node) for track, node in zip(_BOX_ROWS, shown))
    return LayoutFacts(layout.id, _BOX_RECT, (9, 9, 9, 9), _BOX_COLUMNS, rows)


def _grid_facts(log: CommandLog) -> LayoutFacts:
    return LayoutFacts(nid(log.document, "gridLayout"), _BOX_RECT, (9, 9, 9, 9), _GRID_COLUMNS, _GRID_ROWS)


def _splitter_facts(log: CommandLog, sizes: Tuple[int, ...] = (100, 200)) -> SplitterFacts:
    first, second = sizes
    return SplitterFacts(
        nid(log.document, "splitter"),
        "h",
        Rect(9, 46, first + 4 + second, 45),
        first + 4 + second,
        4,
        (Rect(9 + first, 46, 4, 45),),
        (Rect(9, 46, first, 45), Rect(13 + first, 46, second, 45)),
        sizes,
        (20, 30),
    )


def _survey(
    log: CommandLog,
    *,
    primary: Optional[str] = None,
    rect: Rect = Rect(0, 0, 1, 1),
    layouts: Tuple[LayoutFacts, ...] = (),
    splitters: Tuple[SplitterFacts, ...] = (),
    defaults: Tuple[str, str] = _PREFERRED,
    free: Optional[RectValue] = None,
) -> Survey:
    found = None if primary is None else nid(log.document, primary)
    scope = survey_scope(log.document, found, tuple(facts.splitter for facts in splitters))
    facts = None if found is None else PrimaryFacts(found, rect, defaults, free)
    return Survey(1, scope, facts, layouts, splitters)


def _site_knob(log: CommandLog, survey: Survey, kind: str, detail: str) -> Knob:
    for site in knob_set(survey, log.document, 1.0).sites:
        if site.knob.key[0] == kind and site.knob.key[2] == detail:
            return site.knob
    raise AssertionError((kind, detail))


def _handle(log: CommandLog, survey: Survey, at: str) -> Knob:
    for knob in knob_set(survey, log.document, 1.0).handles:
        if knob.pull == at:
            return knob
    raise AssertionError(at)


def _apply(log: CommandLog, result: Turn) -> None:
    for command in result.commands:
        log.execute(command)


def _widget(log: CommandLog, name: str) -> WidgetNode:
    node = log.document.get(nid(log.document, name))
    assert isinstance(node, WidgetNode)
    return node


def _number(log: CommandLog, name: str, prop: str) -> Optional[int]:
    node = log.document.get(nid(log.document, name))
    assert isinstance(node, (LayoutNode, WidgetNode))
    value = node.value(prop)
    return None if value is None else int(getattr(value, "value"))


def _cell(log: CommandLog, name: str) -> Tuple[Optional[int], Optional[int]]:
    item = log.document.parent(nid(log.document, name))
    assert isinstance(item, LayoutItemNode)
    return item.rowspan, item.colspan


@pytest.mark.parametrize("scale", (0.5, 1.0, 2.0))
def test_sites_hit_grips_then_gaps_then_margins_at_least_twelve_screen_px(scale: float) -> None:
    log = open_log(_SPLIT % "")
    survey = _survey(log, primary="label", layouts=(_box_facts(log),), splitters=(_splitter_facts(log),))
    sites = knob_set(survey, log.document, scale).sites
    assert [site.look for site in sites] == ["grip", "bar", "band", "band", "band", "band"]
    for site in sites:
        across = site.hit.width if site.knob.pull in ("e", "w") else site.hit.height
        assert across * scale >= 12, site.knob.key
        assert site.hit.contains(site.mark.x + site.mark.width // 2, site.mark.y + site.mark.height // 2)


@pytest.mark.parametrize("scale", (0.5, 1.0, 2.0))
@pytest.mark.parametrize(
    "window",
    (
        Rect(0, 0, 200, 100),
        Rect(-50, -50, 40, 40),
        Rect(0, 0, 97, 37),
        Rect(103, 0, 97, 100),
        Rect(107, 0, 93, 100),
        Rect(110, 0, 90, 100),
        Rect(0, 49, 200, 51),
        Rect(118, 58, 82, 42),
    ),
)
def test_a_window_keeps_exactly_the_sites_whose_hit_meets_it(scale: float, window: Rect) -> None:
    log = open_log(GRID)
    survey = _survey(log, primary="gridLayout", layouts=(_grid_facts(log),))
    every = knob_set(survey, log.document, scale).sites
    assert knob_set(survey, log.document, scale, window).sites == tuple(
        site for site in every if site.hit.intersects(window)
    )


@pytest.mark.parametrize(
    ("how", "dy", "stored"),
    (
        ("drag", 3, 9),
        ("drag", -1, 5),
        ("shift_drag", 3, 8),
        ("shift_drag", 5, 12),
        ("drag", -40, 0),
        ("drag", 0, None),
    ),
)
def test_gap_drags_one_px_and_shift_snaps_to_four(how: How, dy: int, stored: Optional[int]) -> None:
    log = open_log(BOX)
    knob = _site_knob(log, _survey(log, primary="okButton", layouts=(_box_facts(log),)), "gap", "v0")
    result = turn(knob, 0, dy, how)
    _apply(log, result)
    assert _number(log, "verticalLayout", "spacing") == stored
    shown = 6 if stored is None else stored
    assert result.readout.text == "Spacing %d px" % shown


def test_gap_reset_deletes_only_a_stored_spacing() -> None:
    log = open_log(BOX)
    survey = _survey(log, primary="okButton", layouts=(_box_facts(log),))
    assert reset(_site_knob(log, survey, "gap", "v0")).commands == ()
    _apply(log, turn(_site_knob(log, survey, "gap", "v0"), 0, 10, "drag"))
    assert "spacing" in saved(log.document)
    cleared = reset(_site_knob(log, survey, "gap", "v0"))
    _apply(log, cleared)
    assert "spacing" not in saved(log.document)
    assert cleared.readout.text == "Spacing default"


@pytest.mark.parametrize(
    ("side", "dx", "dy", "how", "stored"),
    (
        ("left", 3, 0, "drag", 12),
        ("right", 3, 0, "drag", 6),
        ("bottom", 0, -2, "drag", 11),
        ("top", 0, 2, "shift_drag", 12),
        ("right", -2, 0, "shift_drag", 12),
    ),
)
def test_margin_drag_moves_toward_the_inside_and_shift_snaps_to_four(
    side: str, dx: int, dy: int, how: How, stored: int
) -> None:
    log = open_log(BOX)
    knob = _site_knob(log, _survey(log, primary="verticalLayout", layouts=(_box_facts(log),)), "margin", side)
    _apply(log, turn(knob, dx, dy, how))
    assert _number(log, "verticalLayout", "%sMargin" % side) == stored


def test_margin_starts_from_the_legacy_margin_and_reset_deletes_only_the_side() -> None:
    log = open_log(BOX.replace('name="verticalLayout">', 'name="verticalLayout">\n   <property name="margin"><number>5</number></property>'))
    survey = _survey(log, primary="verticalLayout", layouts=(_box_facts(log),))
    _apply(log, turn(_site_knob(log, survey, "margin", "left"), 2, 0, "drag"))
    assert _number(log, "verticalLayout", "leftMargin") == 7
    _apply(log, reset(_site_knob(log, survey, "margin", "left")))
    assert _number(log, "verticalLayout", "leftMargin") is None
    assert _number(log, "verticalLayout", "margin") == 5


@pytest.mark.parametrize(
    ("how", "dx", "sizes"),
    (
        ("drag", 13, (113, 187)),
        ("shift_drag", 13, (112, 188)),
        ("drag", -500, (20, 280)),
        ("drag", 500, (270, 30)),
    ),
)
def test_grip_moves_one_boundary_keeps_the_total_and_respects_minimums(
    how: How, dx: int, sizes: Tuple[int, int]
) -> None:
    log = open_log(_SPLIT % "")
    survey = _survey(log, splitters=(_splitter_facts(log),))
    _apply(log, turn(_site_knob(log, survey, "grip", "0"), dx, 0, how))
    entry = _widget(log, "splitter").prop("cbcsSplitterSizes")
    assert entry is not None and entry.stdset == "0"
    assert splitter_sizes(entry.value) == sizes


def test_grip_double_click_writes_equal_panes_from_the_inner_length() -> None:
    log = open_log(_SPLIT % "")
    survey = _survey(log, splitters=(_splitter_facts(log, (60, 241)),))
    result = reset(_site_knob(log, survey, "grip", "0"))
    _apply(log, result)
    entry = _widget(log, "splitter").prop("cbcsSplitterSizes")
    assert entry is not None
    assert splitter_sizes(entry.value) == (151, 150)
    assert result.readout.text == "Sizes 151, 150"


@pytest.mark.parametrize(
    ("inner", "handle", "count", "sizes"),
    ((304, 4, 2, (150, 150)), (306, 4, 3, (100, 99, 99)), (10, 6, 3, (0, 0, 0)), (100, 4, 0, ())),
)
def test_equal_sizes_give_the_remainder_to_the_first_panes(
    inner: int, handle: int, count: int, sizes: Tuple[int, ...]
) -> None:
    assert equal_sizes(inner, handle, count) == sizes


def test_laid_out_handle_writes_fixed_and_shift_snaps_to_eight() -> None:
    log = open_log(BOX)
    survey = _survey(log, primary="label", rect=Rect(9, 46, 182, 45), layouts=(_box_facts(log),))
    drag = turn(_handle(log, survey, "e"), 58, 0, "drag")
    assert drag.readout.text == "Fixed 240 × Hug"
    assert drag.outline == Rect(9, 46, 240, 45)
    snapped = turn(_handle(log, survey, "e"), 55, 0, "shift_drag")
    assert snapped.readout.text == "Fixed 240 × Hug"
    _apply(log, turn(_handle(log, survey, "se"), 55, 0, "shift_drag"))
    label = _widget(log, "label")
    assert label.value("minimumSize") == SizeValue(240, 48)
    assert label.value("maximumSize") == SizeValue(240, 48)


def test_handle_reset_clears_one_axis_and_keeps_the_other_axis_and_stretch() -> None:
    log = open_log(BOX.replace('<widget class="QLabel" name="label">', '<widget class="QLabel" name="label">' + _STRETCHED))
    survey = _survey(log, primary="label", rect=Rect(9, 46, 182, 45), layouts=(_box_facts(log),))
    _apply(log, turn(_handle(log, survey, "se"), 58, 3, "drag"))
    assert _widget(log, "label").value("sizePolicy") == SizePolicyValue("Fixed", "Fixed", 2, 0)
    survey = _survey(log, primary="label", rect=Rect(9, 46, 240, 48), layouts=(_box_facts(log),))
    _apply(log, reset(_handle(log, survey, "e")))
    node = _widget(log, "label")
    assert node.value("sizePolicy") == SizePolicyValue("Preferred", "Fixed", 2, 0)
    assert node.value("minimumSize") == SizeValue(0, 48)
    assert node.value("maximumSize") == SizeValue(16777215, 48)


def test_handle_reset_omits_a_policy_equal_to_the_class_default() -> None:
    log = open_log(BOX)
    survey = _survey(log, primary="label", rect=Rect(9, 46, 182, 45), layouts=(_box_facts(log),))
    _apply(log, turn(_handle(log, survey, "e"), 58, 0, "drag"))
    assert "sizePolicy" in saved(log.document)
    _apply(log, reset(_handle(log, survey, "e")))
    text = saved(log.document)
    assert "sizePolicy" not in text
    assert "minimumSize" not in text
    assert "maximumSize" not in text


def test_grid_handle_spans_to_the_nearest_track_and_clamps_at_the_last() -> None:
    log = open_log(GRID)
    survey = _survey(log, primary="c", rect=Rect(9, 46, 91, 31), layouts=(_grid_facts(log),))
    near = turn(_handle(log, survey, "e"), 30, 0, "drag")
    assert near.commands == ()
    far = turn(_handle(log, survey, "e"), 500, 0, "drag")
    assert far.readout.text == "Spans 2 columns"
    assert far.mark == Rect(9, 46, 182, 31)
    _apply(log, far)
    assert _cell(log, "c") == (None, 2)
    assert 'column="2"' not in saved(log.document)


def test_grid_span_stops_before_a_held_cell_and_shrinks_back() -> None:
    log = open_log(GRID)
    held = _survey(log, primary="a", rect=Rect(9, 9, 91, 31), layouts=(_grid_facts(log),))
    assert turn(_handle(log, held, "e"), 91, 0, "drag").commands == ()
    assert turn(_handle(log, held, "s"), 0, 37, "drag").commands == ()
    free = _survey(log, primary="c", rect=Rect(9, 46, 91, 31), layouts=(_grid_facts(log),))
    _apply(log, turn(_handle(log, free, "e"), 91, 0, "drag"))
    spanned = _survey(log, primary="c", rect=Rect(9, 46, 182, 31), layouts=(_grid_facts(log),))
    _apply(log, turn(_handle(log, spanned, "e"), -91, 0, "drag"))
    assert _cell(log, "c") == (None, None)


def test_grid_handle_shift_drag_writes_fixed_instead_of_span() -> None:
    log = open_log(GRID)
    survey = _survey(log, primary="c", rect=Rect(9, 46, 91, 31), layouts=(_grid_facts(log),))
    _apply(log, turn(_handle(log, survey, "e"), 500, 0, "shift_drag"))
    assert _cell(log, "c") == (None, None)
    assert _widget(log, "c").value("minimumSize") == SizeValue(592, 0)


@pytest.mark.parametrize(("how", "rect"), (("drag", RectValue(10, 10, 110, 38)), ("shift_drag", RectValue(10, 10, 113, 35))))
def test_free_resize_keeps_the_eight_px_grid_that_shift_turns_off(how: How, rect: RectValue) -> None:
    log = open_log(FREE)
    origin = RectValue(10, 10, 100, 30)
    survey = _survey(log, primary="label", rect=Rect(10, 10, 100, 30), free=origin)
    handles = knob_set(survey, log.document, 1.0).handles
    assert tuple(knob.pull for knob in handles) == FREE_PULLS
    _apply(log, turn(_handle(log, survey, "se"), 13, 5, how))
    assert _widget(log, "label").value("geometry") == rect


@pytest.mark.parametrize("vertical", (False, True))
def test_pane_share_round_trips_through_the_one_writer_and_reader(vertical: bool) -> None:
    log = open_log(_SPLIT % (_VERTICAL if vertical else ""))
    right = nid(log.document, "right")
    (slot,) = share_slots(log.document, right)
    assert slot == PaneShare(nid(log.document, "splitter"), right, "v" if vertical else "h")
    command = write_share(log.document, slot, right, 3, ("Expanding", "Expanding"))
    assert command is not None
    log.execute(command)
    reloaded = read_ui(saved(log.document), allocator=IdAllocator()).document
    (again,) = share_slots(reloaded, nid(reloaded, "right"))
    reading = read_share(reloaded, again)
    assert (reading.value, reading.total) == (3, 3)
    policy = _widget(log, "right").value("sizePolicy")
    assert policy == SizePolicyValue("Expanding", "Expanding", 0 if vertical else 3, 3 if vertical else 0)
    zero = write_share(log.document, slot, right, 0, ("Expanding", "Expanding"))
    assert zero is not None
    log.execute(zero)
    assert _widget(log, "right").value("sizePolicy") is None


def test_box_share_chips_show_only_when_the_box_or_its_container_is_selected() -> None:
    log = open_log(BOX.replace('name="verticalLayout">', 'name="verticalLayout" stretch="0,1">'))
    for primary, expected in (("verticalLayout", ("Share 1",)), ("Form", ("Share 1",)), ("okButton", ())):
        survey = _survey(log, primary=primary, layouts=(_box_facts(log),))
        tags = knob_set(survey, log.document, 1.0).shares
        assert tuple(tag.text for tag in tags) == expected, primary
        assert all(tag.node == nid(log.document, "label") for tag in tags)


def test_a_box_share_chip_sits_on_its_own_track_when_an_earlier_item_is_hidden() -> None:
    log = open_log(BOX.replace('name="verticalLayout">', 'name="verticalLayout" stretch="0,1">'))
    survey = _survey(log, primary="verticalLayout", layouts=(_box_facts(log, hidden=("okButton",)),))
    (tag,) = knob_set(survey, log.document, 1.0).shares
    assert tag.node == nid(log.document, "label")
    assert (tag.anchor.y, tag.anchor.height) == (_BOX_ROWS[0].start, _BOX_ROWS[0].end - _BOX_ROWS[0].start)


def test_grid_share_chips_follow_nonzero_track_stretch() -> None:
    log = open_log(GRID.replace('name="gridLayout">', 'name="gridLayout" columnstretch="0,2" rowstretch="1,0">'))
    survey = _survey(log, primary="a", layouts=(_grid_facts(log),))
    tags = knob_set(survey, log.document, 1.0).shares
    assert {(tag.axis, tag.text, tag.node) for tag in tags} == {
        ("h", "Share 2", nid(log.document, "b")),
        ("v", "Share 1", nid(log.document, "a")),
    }
    assert {tag.anchor for tag in tags} == {Rect(106, 9, 85, 68), Rect(9, 9, 182, 31)}


@pytest.mark.parametrize(("primary", "ticks"), (("verticalLayout", 4), ("Form", 0), ("okButton", 0)))
def test_root_ticks_show_only_for_the_selected_root_layout(primary: str, ticks: int) -> None:
    log = open_log(BOX)
    survey = _survey(log, primary=primary, layouts=(_box_facts(log),))
    assert len(knob_set(survey, log.document, 1.0).ticks) == ticks


@pytest.mark.parametrize(
    ("primary", "layouts"),
    (("okButton", ("verticalLayout",)), ("Form", ("verticalLayout",)), ("verticalLayout", ("verticalLayout",)), (None, ())),
)
def test_survey_scope_is_the_own_and_holding_layout_only(primary: Optional[str], layouts: Tuple[str, ...]) -> None:
    log = open_log(BOX)
    found: Optional[NodeId] = None if primary is None else nid(log.document, primary)
    scope = survey_scope(log.document, found, ())
    assert scope.layouts == tuple(nid(log.document, name) for name in layouts)
