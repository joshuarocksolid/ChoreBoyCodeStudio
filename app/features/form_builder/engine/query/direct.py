"""Direct manipulation: knobs that turn stored numbers by dragging. Qt-free.

A knob is a rule, which says what it writes, plus a site, which says where it
is hit. Gap bars, margin bands, splitter grips, Fixed and span handles and
the free resize handle are all knobs. Qt fills a frozen ``Survey`` for the
selection's neighbourhood. Everything from the survey to the commands is
pure, so drag, Shift-drag, the keyboard and double-click share one rule.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Literal, Optional, Sequence, Tuple, Union

from app.features.form_builder.engine.commands.base import Command
from app.features.form_builder.engine.commands.catalog import SetGeometry, SetLayoutCell, SetProperty
from app.features.form_builder.engine.commands.catalog_ext.sizing import from_write
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.logic.storage import splitter_sizes_value
from app.features.form_builder.engine.query.hit_index import Rect
from app.features.form_builder.engine.query.tree import GridCell, GridShape, blocked, grid_shape
from app.features.form_builder.engine.sizing import (
    WORD_FIXED,
    ShareSlot,
    PaneShare,
    SizingWrite,
    chip_axis,
    encode_axis,
    project_axis,
    read_share,
    share_slots,
)
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutItemNode, LayoutNode, WidgetNode
from app.features.form_builder.engine.ui4.values import NumberValue, RectValue, SizePolicyValue, SizeValue

Axis = Literal["h", "v"]
Side = Literal["left", "top", "right", "bottom"]
Pull = Literal["n", "ne", "e", "se", "s", "sw", "w", "nw"]
Edge = Literal["e", "s", "se"]
How = Literal["drag", "shift_drag", "key"]
Look = Literal["bar", "band", "grip"]
#: (kind, node, detail). Stable across rebuilds, so a lingering readout finds its new site.
KnobKey = Tuple[str, NodeId, str]

GRID = 8
THIN_SNAP = 4
HIT_PX = 12
BAR_PX = 2
TICK_PX = 4

FREE_PULLS: Tuple[Pull, ...] = ("nw", "n", "ne", "e", "se", "s", "sw", "w")
LAID_PULLS: Tuple[Edge, ...] = ("e", "s", "se")
_SIDES: Tuple[Side, ...] = ("left", "top", "right", "bottom")
_BOX = frozenset({"QHBoxLayout", "QVBoxLayout", "QBoxLayout"})
_WEST = frozenset({"w", "nw", "sw"})
_EAST = frozenset({"e", "ne", "se"})
_NORTH = frozenset({"n", "nw", "ne"})
_SOUTH = frozenset({"s", "sw", "se"})

HINT_GAP = "Drag to change the spacing. Double-click to reset it."
HINT_MARGIN = "Drag to change the margin. Double-click to reset it."
HINT_GRIP = "Drag to resize the panes. Double-click to make them equal."
HINT_FIXED = "Drag to fix the size. Double-click to reset it."
HINT_SPAN = "Drag to span cells. Shift-drag fixes the size. Double-click resets the size."


# --- Survey: only what Qt knows, in form coordinates. ---


@dataclass(frozen=True)
class Track:
    """One column or row extent."""

    start: int
    end: int


@dataclass(frozen=True)
class LayoutFacts:
    """A layout's measured shape.

    A horizontal box has one column per item and one row. A vertical box has
    one row per item. A grid has its cell columns and rows. A form has a label
    and a field column and one row per form row. A gap is the space between
    two consecutive tracks, so every layout kind gets gaps from one rule.
    """

    layout: NodeId
    rect: Rect
    #: Resolved left, top, right, bottom in px.
    margins: Tuple[int, int, int, int]
    columns: Tuple[Track, ...]
    rows: Tuple[Track, ...]


@dataclass(frozen=True)
class SplitterFacts:
    splitter: NodeId
    axis: Axis
    rect: Rect
    #: Length of the contents rect along ``axis``.
    inner: int
    handle_width: int
    #: Handle i sits between pane i and pane i + 1.
    handles: Tuple[Rect, ...]
    panes: Tuple[Rect, ...]
    sizes: Tuple[int, ...]
    #: The smallest size each pane accepts along ``axis``.
    minimums: Tuple[int, ...]


@dataclass(frozen=True)
class PrimaryFacts:
    node: NodeId
    rect: Rect
    #: Class default (horizontal, vertical) policies. Only a live widget knows them.
    defaults: Tuple[str, str]
    #: The rect a free widget's resize starts from. None when it is not free.
    free: Optional[RectValue] = None


@dataclass(frozen=True)
class SurveyScope:
    """What to measure. Hashable, so a caller re-measures only when it changes."""

    primary: Optional[NodeId]
    #: The primary's own layout and the layout holding it.
    layouts: Tuple[NodeId, ...]
    #: Every visible splitter, because a grip is hittable without a selection.
    splitters: Tuple[NodeId, ...]


@dataclass(frozen=True)
class Survey:
    epoch: int
    scope: SurveyScope
    primary: Optional[PrimaryFacts]
    layouts: Tuple[LayoutFacts, ...]
    splitters: Tuple[SplitterFacts, ...]


# --- Rules: what a knob writes. ---


@dataclass(frozen=True)
class Spacing:
    layout: NodeId
    #: "spacing" for a box layout, else "horizontalSpacing" or "verticalSpacing".
    name: str
    axis: Axis
    #: The stored value, else the measured gap.
    origin: int
    stored: bool
    gap: Rect


@dataclass(frozen=True)
class Margin:
    layout: NodeId
    side: Side
    origin: int
    stored: bool
    band: Rect


@dataclass(frozen=True)
class Grip:
    splitter: NodeId
    #: The pane before the handle. The handle moves the boundary after it.
    before: int
    axis: Axis
    sizes: Tuple[int, ...]
    minimums: Tuple[int, ...]
    inner: int
    handle_width: int
    handle: Rect


@dataclass(frozen=True)
class FixedSize:
    widget: NodeId
    at: Edge
    origin: Rect
    policy: Optional[SizePolicyValue]
    minimum: Optional[SizeValue]
    maximum: Optional[SizeValue]
    defaults: Tuple[str, str]


@dataclass(frozen=True)
class Span:
    #: The layout item whose cell changes.
    item: NodeId
    layout: NodeId
    at: Edge
    cell: GridCell
    #: SetLayoutCell clears every field it is not given, so these ride along.
    row: Optional[int]
    column: Optional[int]
    alignment: Optional[str]
    columns: Tuple[Track, ...]
    rows: Tuple[Track, ...]
    shape: GridShape
    #: Shift-drag and the keyboard write Fixed instead.
    fixed: FixedSize


@dataclass(frozen=True)
class FreeRect:
    widget: NodeId
    at: Pull
    origin: RectValue
    drawn: Rect


HandleRule = Union[FixedSize, Span, FreeRect]
ThinRule = Union[Spacing, Margin, Grip]
Rule = Union[HandleRule, ThinRule]


@dataclass(frozen=True)
class Knob:
    key: KnobKey
    #: The node the knob writes to.
    subject: NodeId
    #: The direction a drag pulls. It picks the cursor.
    pull: Pull
    #: Status sentence while hovered.
    hint: str
    rule: Rule


@dataclass(frozen=True)
class Readout:
    key: KnobKey
    text: str
    #: Where the readout seats when no site with ``key`` is left.
    anchor: Rect


@dataclass(frozen=True)
class Turn:
    """What turning a knob does. Drag, Shift-drag, keyboard and double-click all return one."""

    label: str
    #: () when the result equals what is stored.
    commands: Tuple[Command, ...]
    readout: Readout
    #: Where the subject widget will be, for handle rules.
    outline: Optional[Rect]
    #: The bar, band, grip or spanned cell drawn hot during the drag.
    mark: Optional[Rect]


@dataclass(frozen=True)
class Site:
    knob: Knob
    #: At least HIT_PX screen pixels across the thin axis.
    hit: Rect
    mark: Rect
    look: Look


@dataclass(frozen=True)
class ShareTag:
    """A "Share 2" chip on a box item, grid track or splitter pane."""

    key: KnobKey
    #: The widget whose share row the chip opens.
    node: NodeId
    axis: Axis
    text: str
    anchor: Rect


@dataclass(frozen=True)
class Tick:
    """Where the root layout attaches to a page edge, and its margin there."""

    side: Side
    pixels: int
    rect: Rect


@dataclass(frozen=True)
class KnobSet:
    #: The primary's handle knobs. The overlay places them on its shown rect.
    handles: Tuple[Knob, ...]
    #: Grips, then gaps, then margins. This order is the hit order.
    sites: Tuple[Site, ...]
    shares: Tuple[ShareTag, ...]
    ticks: Tuple[Tick, ...]


EMPTY = KnobSet((), (), (), ())


def survey_scope(document: UiDocument, primary: Optional[NodeId], splitters: Tuple[NodeId, ...]) -> SurveyScope:
    """A layout shows when it, its container or a direct child is the primary. No form walk."""
    if primary is None or not document.contains(primary):
        return SurveyScope(None, (), splitters)
    found: List[NodeId] = []
    node = document.get(primary)
    own = node if isinstance(node, LayoutNode) else node.layout if isinstance(node, WidgetNode) else None
    if own is not None:
        found.append(own.id)
    holder = _holding_layout(document, primary)
    if holder is not None and holder not in found:
        found.append(holder)
    return SurveyScope(primary, tuple(found), splitters)


def knob_set(survey: Survey, document: UiDocument, scale: float) -> KnobSet:
    """Every knob for ``survey``. ``scale`` is screen pixels per form pixel."""
    thick = max(1, int(math.ceil(HIT_PX / max(scale, 0.01))))
    sites: List[Site] = []
    for splitter in survey.splitters:
        sites.extend(_grip_sites(splitter, thick))
    for facts in survey.layouts:
        sites.extend(_gap_sites(document, facts, thick))
    for facts in survey.layouts:
        sites.extend(_margin_sites(document, facts, thick))
    return KnobSet(
        _handle_knobs(document, survey),
        tuple(sites),
        _share_tags(document, survey),
        _ticks(document, survey),
    )


def turn(knob: Knob, dx: float, dy: float, how: How) -> Turn:
    """What ``knob`` writes for a form-space delta since the press.

    ``drag`` moves in 1 px steps. ``shift_drag`` snaps spacing and margins to
    4 and every other new number to 8. ``key`` uses the exact delta. A span
    snaps to track boundaries and writes Fixed on ``shift_drag`` and ``key``.
    Free resize keeps its rule: ``drag`` is on the 8 px grid and the others
    are not.
    """
    rule = knob.rule
    if isinstance(rule, Spacing):
        return _turn_spacing(knob, rule, dx, dy, how)
    if isinstance(rule, Margin):
        return _turn_margin(knob, rule, dx, dy, how)
    if isinstance(rule, Grip):
        return _turn_grip(knob, rule, dx, dy, how)
    if isinstance(rule, FixedSize):
        return _turn_fixed(knob, rule, dx, dy, how)
    if isinstance(rule, Span):
        if how == "drag":
            return _turn_span(knob, rule, dx, dy)
        return _turn_fixed(knob, rule.fixed, dx, dy, how)
    return _turn_free(knob, rule, dx, dy, how)


def reset(knob: Knob) -> Turn:
    """Double-click.

    Spacing and margins delete the property. A size handle resets its axis,
    both at the corner, and keeps stretches and span. A grip writes equal pane
    sizes. Free resize resets nothing.
    """
    rule = knob.rule
    if isinstance(rule, Spacing):
        commands: Tuple[Command, ...] = (SetProperty(rule.layout, rule.name, None),) if rule.stored else ()
        text = "%s default" % _spacing_word(rule.axis, rule.name)
        return Turn("Reset spacing", commands, Readout(knob.key, text, rule.gap), None, None)
    if isinstance(rule, Margin):
        commands = (SetProperty(rule.layout, _MARGIN_NAMES[rule.side], None),) if rule.stored else ()
        text = "%s margin default" % rule.side.capitalize()
        return Turn("Reset margin", commands, Readout(knob.key, text, rule.band), None, None)
    if isinstance(rule, Grip):
        sizes = equal_sizes(rule.inner, rule.handle_width, len(rule.sizes))
        return Turn(
            "Equal panes",
            _sizes_commands(rule, sizes),
            Readout(knob.key, sizes_text(sizes), rule.handle),
            None,
            rule.handle,
        )
    if isinstance(rule, (FixedSize, Span)):
        fixed = rule.fixed if isinstance(rule, Span) else rule
        return _reset_fixed(knob, fixed)
    return Turn("Resize", (), Readout(knob.key, _free_text(rule.origin), rule.drawn), rule.drawn, None)


def clicks_through(knob: Knob) -> bool:
    """A gap, margin or grip takes drags and double-clicks. A single click selects what lies under it."""
    return isinstance(knob.rule, (Spacing, Margin, Grip))


def equal_sizes(inner: int, handle_width: int, count: int) -> Tuple[int, ...]:
    """Equal panes from the splitter's inner length. The first panes take the remainder."""
    if count <= 0:
        return ()
    room = max(0, int(inner) - int(handle_width) * (count - 1))
    each, extra = divmod(room, count)
    return tuple(each + (1 if index < extra else 0) for index in range(count))


def sizes_text(sizes: Sequence[int]) -> str:
    return "Sizes %s" % ", ".join(str(int(size)) for size in sizes)


def span_text(colspan: Optional[int], rowspan: Optional[int]) -> str:
    """ "Spans 2 columns", "Spans 3 rows" or both."""
    parts = []
    if colspan is not None:
        parts.append("%d %s" % (colspan, "column" if colspan == 1 else "columns"))
    if rowspan is not None:
        parts.append("%d %s" % (rowspan, "row" if rowspan == 1 else "rows"))
    return "Spans %s" % " × ".join(parts)


def size_text(
    policy: Optional[SizePolicyValue],
    minimum: Optional[SizeValue],
    maximum: Optional[SizeValue],
    defaults: Tuple[str, str],
) -> str:
    """ "Fixed 240 × Hug": the words the Size group shows, with Fixed's pixels."""
    return "%s × %s" % (
        _axis_text(None if policy is None else policy.hsizetype, minimum, maximum, defaults[0], True),
        _axis_text(None if policy is None else policy.vsizetype, minimum, maximum, defaults[1], False),
    )


def grid_coord(value: float, snap: bool) -> int:
    if snap:
        return int(round(value / GRID) * GRID)
    return int(round(value))


def snap_resize(origin: RectValue, handle: Pull, dx: float, dy: float, snap: bool) -> RectValue:
    """Free resize. The dragged edges land on the 8 px grid when ``snap``."""
    left = origin.x
    top = origin.y
    right = origin.x + origin.width
    bottom = origin.y + origin.height
    if handle in _WEST:
        left = grid_coord(left + dx, snap)
    if handle in _EAST:
        right = grid_coord(right + dx, snap)
    if handle in _NORTH:
        top = grid_coord(top + dy, snap)
    if handle in _SOUTH:
        bottom = grid_coord(bottom + dy, snap)
    if right <= left:
        if handle in _WEST and handle not in _EAST:
            left = right - 1
        else:
            right = left + 1
    if bottom <= top:
        if handle in _NORTH and handle not in _SOUTH:
            top = bottom - 1
        else:
            bottom = top + 1
    return RectValue(left, top, right - left, bottom - top)


# --- Turning ---

_MARGIN_NAMES = {"left": "leftMargin", "top": "topMargin", "right": "rightMargin", "bottom": "bottomMargin"}
_SIDE_PULLS: Dict[Side, Pull] = {"left": "w", "right": "e", "top": "n", "bottom": "s"}


def _turn_spacing(knob: Knob, rule: Spacing, dx: float, dy: float, how: How) -> Turn:
    moved = dx if rule.axis == "h" else dy
    value = max(0, _snap(rule.origin + moved, THIN_SNAP if how == "shift_drag" else 1))
    commands: Tuple[Command, ...] = ()
    if value != rule.origin:
        commands = (SetProperty(rule.layout, rule.name, NumberValue(value)),)
    if rule.axis == "h":
        mark = Rect(rule.gap.x, rule.gap.y, value, rule.gap.height)
    else:
        mark = Rect(rule.gap.x, rule.gap.y, rule.gap.width, value)
    text = "%s %d px" % (_spacing_word(rule.axis, rule.name), value)
    return Turn("Spacing", commands, Readout(knob.key, text, mark), None, mark)


def _turn_margin(knob: Knob, rule: Margin, dx: float, dy: float, how: How) -> Turn:
    moved = {"left": dx, "right": -dx, "top": dy, "bottom": -dy}[rule.side]
    value = max(0, _snap(rule.origin + moved, THIN_SNAP if how == "shift_drag" else 1))
    commands: Tuple[Command, ...] = ()
    if value != rule.origin:
        commands = (SetProperty(rule.layout, _MARGIN_NAMES[rule.side], NumberValue(value)),)
    band = rule.band
    if rule.side == "left":
        mark = Rect(band.x, band.y, value, band.height)
    elif rule.side == "right":
        mark = Rect(band.x + band.width - value, band.y, value, band.height)
    elif rule.side == "top":
        mark = Rect(band.x, band.y, band.width, value)
    else:
        mark = Rect(band.x, band.y + band.height - value, band.width, value)
    text = "%s margin %d px" % (rule.side.capitalize(), value)
    return Turn("Margin", commands, Readout(knob.key, text, mark), None, mark)


def _turn_grip(knob: Knob, rule: Grip, dx: float, dy: float, how: How) -> Turn:
    moved = dx if rule.axis == "h" else dy
    first_at = rule.before
    second_at = rule.before + 1
    total = rule.sizes[first_at] + rule.sizes[second_at]
    first = _snap(rule.sizes[first_at] + moved, GRID if how == "shift_drag" else 1)
    low = rule.minimums[first_at]
    high = max(low, total - rule.minimums[second_at])
    first = min(max(first, low), high)
    sizes = list(rule.sizes)
    sizes[first_at] = first
    sizes[second_at] = total - first
    shift = first - rule.sizes[first_at]
    handle = rule.handle
    if rule.axis == "h":
        mark = Rect(handle.x + shift, handle.y, handle.width, handle.height)
    else:
        mark = Rect(handle.x, handle.y + shift, handle.width, handle.height)
    return Turn(
        "Resize panes",
        _sizes_commands(rule, tuple(sizes)),
        Readout(knob.key, sizes_text(sizes), mark),
        None,
        mark,
    )


def _sizes_commands(rule: Grip, sizes: Tuple[int, ...]) -> Tuple[Command, ...]:
    if sizes == rule.sizes:
        return ()
    return (SetProperty(rule.splitter, "cbcsSplitterSizes", splitter_sizes_value(sizes), stdset="0"),)


def _turn_fixed(knob: Knob, rule: FixedSize, dx: float, dy: float, how: How) -> Turn:
    step = GRID if how == "shift_drag" else 1
    width = rule.origin.width
    height = rule.origin.height
    pixels: List[Tuple[str, int]] = []
    if rule.at in ("e", "se"):
        width = max(1, _snap(rule.origin.width + dx, step))
        pixels.append(("h", width))
    if rule.at in ("s", "se"):
        height = max(1, _snap(rule.origin.height + dy, step))
        pixels.append(("v", height))
    write = _chain(rule, tuple((axis, WORD_FIXED, size) for axis, size in pixels))
    outline = Rect(rule.origin.x, rule.origin.y, width, height)
    text = size_text(write.policy, write.minimum, write.maximum, rule.defaults)
    return Turn("Resize", _sizing_commands(rule, write), Readout(knob.key, text, outline), outline, None)


def _reset_fixed(knob: Knob, rule: FixedSize) -> Turn:
    axes = {"e": ("h",), "s": ("v",), "se": ("h", "v")}[rule.at]
    write = _chain(rule, tuple((axis, None, None) for axis in axes))
    text = size_text(write.policy, write.minimum, write.maximum, rule.defaults)
    return Turn("Reset size", _sizing_commands(rule, write), Readout(knob.key, text, rule.origin), rule.origin, None)


def _chain(
    rule: FixedSize, steps: Tuple[Tuple[str, Optional[str], Optional[int]], ...]
) -> SizingWrite:
    write = SizingWrite(rule.policy, rule.minimum, rule.maximum, False, False, False)
    for axis, word, pixels in steps:
        write = encode_axis(
            axis=axis,
            word=word,
            pixels=pixels,
            current_policy=write.policy,
            current_minimum=write.minimum,
            current_maximum=write.maximum,
            class_default_h=rule.defaults[0],
            class_default_v=rule.defaults[1],
        )
    return write


def _sizing_commands(rule: FixedSize, write: SizingWrite) -> Tuple[Command, ...]:
    if (write.policy, write.minimum, write.maximum) == (rule.policy, rule.minimum, rule.maximum):
        return ()
    return (from_write(rule.widget, write),)


def _turn_span(knob: Knob, rule: Span, dx: float, dy: float) -> Turn:
    cell = rule.cell
    colspan = cell.colspan
    rowspan = cell.rowspan
    if rule.at in ("e", "se"):
        colspan = _span_to(rule, rule.columns, cell.column, cell.colspan, dx, True, rowspan)
    if rule.at in ("s", "se"):
        rowspan = _span_to(rule, rule.rows, cell.row, cell.rowspan, dy, False, colspan)
    commands: Tuple[Command, ...] = ()
    if (colspan, rowspan) != (cell.colspan, cell.rowspan):
        commands = (
            SetLayoutCell(
                rule.item,
                rule.row,
                rule.column,
                None if rowspan == 1 else rowspan,
                None if colspan == 1 else colspan,
                rule.alignment,
            ),
        )
    mark = _cells_rect(rule, cell.column, colspan, cell.row, rowspan)
    text = span_text(
        colspan if rule.at in ("e", "se") else None,
        rowspan if rule.at in ("s", "se") else None,
    )
    return Turn("Span", commands, Readout(knob.key, text, mark), mark, mark)


def _span_to(
    rule: Span,
    tracks: Tuple[Track, ...],
    start: int,
    span: int,
    moved: float,
    columns: bool,
    other_span: int,
) -> int:
    """The span whose far edge is the track boundary nearest the dragged edge.

    It never drops below 1, never passes the last track and stops before a
    cell another item holds.
    """
    if not tracks or start >= len(tracks):
        return span
    last = min(start + span, len(tracks)) - 1
    edge = tracks[last].end + moved
    wanted = min(range(start, len(tracks)), key=lambda at: abs(tracks[at].end - edge)) - start + 1
    reached = span
    while reached < wanted:
        trial = reached + 1
        if columns:
            probe = GridCell(rule.cell.item, rule.cell.row, rule.cell.column, other_span, trial)
        else:
            probe = GridCell(rule.cell.item, rule.cell.row, rule.cell.column, trial, other_span)
        if blocked(rule.shape, probe):
            break
        reached = trial
    if wanted < reached:
        reached = max(1, wanted)
    return reached


def _cells_rect(rule: Span, column: int, colspan: int, row: int, rowspan: int) -> Rect:
    if not rule.columns or not rule.rows:
        return rule.fixed.origin
    first_column = rule.columns[min(column, len(rule.columns) - 1)]
    last_column = rule.columns[min(column + colspan, len(rule.columns)) - 1]
    first_row = rule.rows[min(row, len(rule.rows) - 1)]
    last_row = rule.rows[min(row + rowspan, len(rule.rows)) - 1]
    return Rect(
        first_column.start,
        first_row.start,
        last_column.end - first_column.start,
        last_row.end - first_row.start,
    )


def _turn_free(knob: Knob, rule: FreeRect, dx: float, dy: float, how: How) -> Turn:
    rect = snap_resize(rule.origin, rule.at, dx, dy, how == "drag")
    commands: Tuple[Command, ...] = ()
    if rect != rule.origin:
        commands = (SetGeometry(rule.widget, rect),)
    outline = Rect(
        rule.drawn.x + rect.x - rule.origin.x,
        rule.drawn.y + rect.y - rule.origin.y,
        rect.width,
        rect.height,
    )
    return Turn("Resize", commands, Readout(knob.key, _free_text(rect), outline), outline, None)


def _free_text(rect: RectValue) -> str:
    return "%d × %d" % (rect.width, rect.height)


def _snap(value: float, step: int) -> int:
    if step <= 1:
        return int(round(value))
    return int(round(value / step) * step)


def _spacing_word(axis: Axis, name: str) -> str:
    if name == "spacing":
        return "Spacing"
    return "Column spacing" if axis == "h" else "Row spacing"


def _axis_text(
    stored: Optional[str],
    minimum: Optional[SizeValue],
    maximum: Optional[SizeValue],
    default: str,
    horizontal: bool,
) -> str:
    low = None if minimum is None else (minimum.width if horizontal else minimum.height)
    high = None if maximum is None else (maximum.width if horizontal else maximum.height)
    projection = project_axis(
        stored_policy=stored,
        minimum=low,
        maximum=high,
        class_default_policy=default,
        class_phrase="",
    )
    if projection.word == WORD_FIXED and projection.pixels is not None:
        return "Fixed %d" % projection.pixels
    return chip_axis(projection) or projection.policy_name


# --- Sites ---


def _grip_sites(facts: SplitterFacts, thick: int) -> List[Site]:
    found: List[Site] = []
    for index, handle in enumerate(facts.handles):
        if index + 1 >= len(facts.sizes):
            break
        rule = Grip(
            facts.splitter,
            index,
            facts.axis,
            facts.sizes,
            facts.minimums,
            facts.inner,
            facts.handle_width,
            handle,
        )
        pull: Pull = "e" if facts.axis == "h" else "s"
        knob = Knob(("grip", facts.splitter, str(index)), facts.splitter, pull, HINT_GRIP, rule)
        found.append(Site(knob, _widen(handle, facts.axis, thick), handle, "grip"))
    return found


def _gap_sites(document: UiDocument, facts: LayoutFacts, thick: int) -> List[Site]:
    layout = document.get(facts.layout)
    if not isinstance(layout, LayoutNode):
        return []
    box = layout.class_name in _BOX
    found: List[Site] = []
    passes: Tuple[Tuple[Axis, Tuple[Track, ...], Tuple[Track, ...]], ...] = (
        ("h", facts.columns, facts.rows),
        ("v", facts.rows, facts.columns),
    )
    for axis, tracks, across in passes:
        if len(tracks) < 2 or not across:
            continue
        name = "spacing" if box else ("horizontalSpacing" if axis == "h" else "verticalSpacing")
        stored = _stored_number(layout, name)
        low = across[0].start
        high = across[-1].end
        for index in range(len(tracks) - 1):
            before = tracks[index]
            after = tracks[index + 1]
            size = after.start - before.end
            if size < 0:
                continue
            if axis == "h":
                gap = Rect(before.end, low, size, high - low)
                bar = Rect(before.end + size // 2 - BAR_PX // 2, low, BAR_PX, high - low)
            else:
                gap = Rect(low, before.end, high - low, size)
                bar = Rect(low, before.end + size // 2 - BAR_PX // 2, high - low, BAR_PX)
            rule = Spacing(layout.id, name, axis, size if stored is None else stored, stored is not None, gap)
            pull: Pull = "e" if axis == "h" else "s"
            key = ("gap", layout.id, "%s%d" % (axis, index))
            found.append(Site(Knob(key, layout.id, pull, HINT_GAP, rule), _widen(gap, axis, thick), bar, "bar"))
    return found


def _margin_sites(document: UiDocument, facts: LayoutFacts, thick: int) -> List[Site]:
    layout = document.get(facts.layout)
    if not isinstance(layout, LayoutNode):
        return []
    rect = facts.rect
    left, top, right, bottom = facts.margins
    bands = {
        "left": Rect(rect.x, rect.y, left, rect.height),
        "top": Rect(rect.x, rect.y, rect.width, top),
        "right": Rect(rect.x + rect.width - right, rect.y, right, rect.height),
        "bottom": Rect(rect.x, rect.y + rect.height - bottom, rect.width, bottom),
    }
    measured = {"left": left, "top": top, "right": right, "bottom": bottom}
    legacy = _stored_number(layout, "margin")
    found: List[Site] = []
    for side in _SIDES:
        stored = _stored_number(layout, _MARGIN_NAMES[side])
        origin = stored if stored is not None else legacy if legacy is not None else measured[side]
        band = bands[side]
        axis: Axis = "h" if side in ("left", "right") else "v"
        pull = _SIDE_PULLS[side]
        rule = Margin(layout.id, side, origin, stored is not None, band)
        knob = Knob(("margin", layout.id, side), layout.id, pull, HINT_MARGIN, rule)
        found.append(Site(knob, _widen(band, axis, thick), band, "band"))
    return found


def _widen(rect: Rect, axis: str, thick: int) -> Rect:
    """Grow the thin axis to ``thick`` around its centre."""
    if axis == "h" and rect.width < thick:
        return Rect(rect.x + rect.width // 2 - thick // 2, rect.y, thick, rect.height)
    if axis == "v" and rect.height < thick:
        return Rect(rect.x, rect.y + rect.height // 2 - thick // 2, rect.width, thick)
    return rect


# --- Handles ---


def _handle_knobs(document: UiDocument, survey: Survey) -> Tuple[Knob, ...]:
    primary = survey.primary
    if primary is None:
        return ()
    node = document.get(primary.node)
    if not isinstance(node, WidgetNode) or node.id == document.root.id:
        return ()
    if primary.free is not None:
        return tuple(
            Knob(("size", node.id, at), node.id, at, "", FreeRect(node.id, at, primary.free, primary.rect))
            for at in FREE_PULLS
        )
    item = document.parent(node.id)
    if not isinstance(item, LayoutItemNode):
        return ()
    layout = document.parent(item.id)
    if not isinstance(layout, LayoutNode):
        return ()
    policy = node.value("sizePolicy")
    minimum = node.value("minimumSize")
    maximum = node.value("maximumSize")
    grid = _facts(survey, layout.id) if layout.class_name == "QGridLayout" else None
    shape = grid_shape(document, layout.id) if grid is not None else None
    knobs: List[Knob] = []
    for at in LAID_PULLS:
        fixed = FixedSize(
            node.id,
            at,
            primary.rect,
            policy if isinstance(policy, SizePolicyValue) else None,
            minimum if isinstance(minimum, SizeValue) else None,
            maximum if isinstance(maximum, SizeValue) else None,
            primary.defaults,
        )
        if grid is None or shape is None:
            knobs.append(Knob(("size", node.id, at), node.id, at, HINT_FIXED, fixed))
            continue
        cell = next((found for found in shape.cells if found.item == item.id), None)
        if cell is None:
            knobs.append(Knob(("size", node.id, at), node.id, at, HINT_FIXED, fixed))
            continue
        span = Span(
            item.id,
            layout.id,
            at,
            cell,
            item.row,
            item.column,
            item.alignment,
            grid.columns,
            grid.rows,
            shape,
            fixed,
        )
        knobs.append(Knob(("size", node.id, at), node.id, at, HINT_SPAN, span))
    return tuple(knobs)


# --- Share chips and root ticks ---


def _share_tags(document: UiDocument, survey: Survey) -> Tuple[ShareTag, ...]:
    primary = survey.scope.primary
    if primary is None:
        return ()
    found: List[ShareTag] = []
    for facts in survey.layouts:
        layout = document.get(facts.layout)
        if not isinstance(layout, LayoutNode):
            continue
        if layout.class_name == "QGridLayout":
            found.extend(_grid_tags(document, layout, facts))
        elif layout.class_name in _BOX and primary in (layout.id, layout.owner_widget_id()):
            found.extend(_box_tags(document, layout, facts))
    for facts in survey.splitters:
        splitter = document.get(facts.splitter)
        if not isinstance(splitter, WidgetNode):
            continue
        panes = splitter.child_widgets
        if primary != splitter.id and primary not in {pane.id for pane in panes}:
            continue
        for index, pane in enumerate(panes):
            if index >= len(facts.panes):
                break
            value = read_share(document, PaneShare(splitter.id, pane.id, facts.axis)).value
            if value:
                found.append(
                    ShareTag(("share", pane.id, facts.axis), pane.id, facts.axis, _share_text(value), facts.panes[index])
                )
    return tuple(found)


def _grid_tags(document: UiDocument, layout: LayoutNode, facts: LayoutFacts) -> List[ShareTag]:
    found: List[ShareTag] = []
    if not facts.columns or not facts.rows:
        return found
    top = facts.rows[0].start
    bottom = facts.rows[-1].end
    left = facts.columns[0].start
    right = facts.columns[-1].end
    passes: Tuple[Tuple[Axis, str, Tuple[Track, ...]], ...] = (
        ("h", "columnstretch", facts.columns),
        ("v", "rowstretch", facts.rows),
    )
    for axis, field, tracks in passes:
        for index, track in enumerate(tracks):
            value = read_share(document, ShareSlot(layout.id, field, index, axis)).value
            if not value:
                continue
            owner = _track_owner(layout, axis, index)
            if owner is None:
                continue
            if axis == "h":
                anchor = Rect(track.start, top, track.end - track.start, bottom - top)
            else:
                anchor = Rect(left, track.start, right - left, track.end - track.start)
            found.append(ShareTag(("share", layout.id, "%s%d" % (axis, index)), owner, axis, _share_text(value), anchor))
    return found


def _box_tags(document: UiDocument, layout: LayoutNode, facts: LayoutFacts) -> List[ShareTag]:
    found: List[ShareTag] = []
    axis: Axis = "h" if layout.class_name == "QHBoxLayout" else "v"
    tracks = facts.columns if axis == "h" else facts.rows
    across = facts.rows if axis == "h" else facts.columns
    if not across:
        return found
    for index, item in enumerate(layout.items):
        content = item.content
        if not isinstance(content, WidgetNode) or index >= len(tracks):
            continue
        slots = share_slots(document, content.id)
        if not slots:
            continue
        value = read_share(document, slots[0]).value
        if not value:
            continue
        track = tracks[index]
        if axis == "h":
            anchor = Rect(track.start, across[0].start, track.end - track.start, across[-1].end - across[0].start)
        else:
            anchor = Rect(across[0].start, track.start, across[-1].end - across[0].start, track.end - track.start)
        found.append(ShareTag(("share", content.id, axis), content.id, axis, _share_text(value), anchor))
    return found


def _track_owner(layout: LayoutNode, axis: str, index: int) -> Optional[NodeId]:
    for item in layout.items:
        at = item.column if axis == "h" else item.row
        if int(at or 0) == index and isinstance(item.content, WidgetNode):
            return item.content.id
    return None


def _share_text(value: int) -> str:
    return "Share %d" % int(value)


def _ticks(document: UiDocument, survey: Survey) -> Tuple[Tick, ...]:
    root_layout = document.root.layout
    if root_layout is None or survey.scope.primary != root_layout.id:
        return ()
    facts = _facts(survey, root_layout.id)
    if facts is None:
        return ()
    rect = facts.rect
    left, top, right, bottom = facts.margins
    mid_x = rect.x + rect.width // 2
    mid_y = rect.y + rect.height // 2
    return (
        Tick("left", left, Rect(rect.x, mid_y, max(TICK_PX, left), 1)),
        Tick("top", top, Rect(mid_x, rect.y, 1, max(TICK_PX, top))),
        Tick("right", right, Rect(rect.x + rect.width - max(TICK_PX, right), mid_y, max(TICK_PX, right), 1)),
        Tick("bottom", bottom, Rect(mid_x, rect.y + rect.height - max(TICK_PX, bottom), 1, max(TICK_PX, bottom))),
    )


def _facts(survey: Survey, layout: NodeId) -> Optional[LayoutFacts]:
    for facts in survey.layouts:
        if facts.layout == layout:
            return facts
    return None


def _holding_layout(document: UiDocument, node: NodeId) -> Optional[NodeId]:
    item = document.parent(node)
    if not isinstance(item, LayoutItemNode):
        return None
    layout = document.parent(item.id)
    return layout.id if isinstance(layout, LayoutNode) else None


def _stored_number(layout: LayoutNode, name: str) -> Optional[int]:
    value = layout.value(name)
    if isinstance(value, NumberValue):
        return int(value.value)
    return None
