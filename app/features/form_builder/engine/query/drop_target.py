"""Drop target from slot geometry (UX-DND-008). Qt-free.

The pointer picks the nearest slot boundary along the layout axis. It does not
have to land in the gap, and it does not pick "the widget under the pointer".
A shrunk nested layout stays hittable: its hit rect grows to 24 px.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Literal, Optional, Sequence, Tuple, Union

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.hit_index import Rect
from app.features.form_builder.engine.query.tree import PAGE_CONTAINERS, form_rows
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import (
    LayoutItemNode,
    LayoutNode,
    Node,
    SpacerNode,
    WidgetNode,
)
from app.features.form_builder.engine.ui4.values import StringValue

MIN_HIT = 24
GHOST_BAND = 24
CROSS_EDGE = 8
SNAP = 8

HostKind = Literal[
    "vbox", "hbox", "grid", "form", "splitter", "pages", "bare_empty", "bare_free"
]
PayloadKind = Literal["widget", "label", "spacer"]
DropAction = Literal[
    "box",
    "wrap",
    "grid_cell",
    "grid_row",
    "grid_column",
    "form_cell",
    "form_row",
    "splitter",
    "page",
    "new_page",
    "auto_layout",
    "free",
]
WrapSide = Literal["before", "after", ""]
FormRole = Literal["label", "field", "spanning", ""]
IndicatorRole = Literal["select", "problem"]

_LAYOUT_CLASS: Dict[str, HostKind] = {
    "QVBoxLayout": "vbox",
    "QHBoxLayout": "hbox",
    "QGridLayout": "grid",
    "QFormLayout": "form",
}


@dataclass(frozen=True)
class SlotGeom:
    """One slot in form pixels. ``node`` is None for an empty cell."""

    rect: Rect
    index: int = 0
    node: Optional[NodeId] = None
    text: str = ""
    row: int = 0
    column: int = 0
    rowspan: int = 1
    colspan: int = 1
    role: str = ""


@dataclass(frozen=True)
class DropHost:
    """A layout or container the pointer can land in, plus the hosts inside it."""

    node: NodeId
    kind: HostKind
    name: str
    rect: Rect
    slots: Tuple[SlotGeom, ...] = ()
    children: Tuple["DropHost", ...] = ()


@dataclass(frozen=True)
class DropPayload:
    """What is being dragged. ``source_ids`` is empty for a new insert."""

    kind: PayloadKind
    source_ids: Tuple[NodeId, ...] = ()
    rowspan: int = 1
    colspan: int = 1
    snap: bool = True
    default_size: Tuple[int, int] = (80, 24)


@dataclass(frozen=True)
class DropIndicator:
    rect: Rect
    dashed: bool = False
    role: IndicatorRole = "select"


@dataclass(frozen=True)
class AcceptedDrop:
    """One legal target. The painter draws ``frame`` plus ``indicator``."""

    sentence: str
    chip: str
    host: NodeId
    action: DropAction
    indicator: DropIndicator
    frame: Rect
    index: int = 0
    row: int = 0
    column: int = 0
    rowspan: int = 1
    colspan: int = 1
    role: FormRole = ""
    wrap_neighbour: Optional[NodeId] = None
    wrap_side: WrapSide = ""
    wrap_layout: str = ""
    page: Optional[NodeId] = None
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    spring_id: Optional[NodeId] = None


@dataclass(frozen=True)
class RefusedDrop:
    """The pointer is on a slot that cannot take this drag."""

    sentence: str
    chip: str
    host: Optional[NodeId]
    indicator: DropIndicator
    frame: Rect
    spring_id: Optional[NodeId] = None


@dataclass(frozen=True)
class NoDrop:
    """No indicator. The drag itself stays alive."""

    spring_id: Optional[NodeId] = None


DropTarget = Union[AcceptedDrop, RefusedDrop, NoDrop]


def resolve_drop(
    root: DropHost,
    pointer: Tuple[int, int],
    payload: DropPayload,
    blocked: FrozenSet[NodeId] = frozenset(),
) -> DropTarget:
    """The one target at ``pointer``. Nearest visual rect wins. Smaller area breaks ties."""

    found: List[Tuple[int, DropHost]] = []
    _gather(root, pointer, 0, found)
    found.sort(
        key=lambda item: (
            _distance(item[1].rect, pointer),
            item[1].rect.width * max(item[1].rect.height, 1),
            -item[0],
        )
    )
    if not found:
        return NoDrop()
    if found[0][1].node in blocked:
        return _itself(found[0][1])
    for _depth, host in found:
        if host.node in blocked:
            continue
        result = _resolve_host(host, pointer, payload, blocked)
        if result is not None:
            return result
    return NoDrop()


def blocked_ids(doc: UiDocument, source_ids: Sequence[NodeId]) -> FrozenSet[NodeId]:
    """Dragged nodes and everything inside them. A drop there is "into itself"."""

    found = set()
    for source in source_ids:
        if not doc.contains(source):
            continue
        for node in doc.iter_preorder(source):
            found.add(node.id)
    return frozenset(found)


def hosts_from(doc: UiDocument, rect_of: Dict[NodeId, Rect]) -> DropHost:
    """Build the host tree from a document and form-pixel rects."""

    root = doc.root
    built = _widget_host(doc, rect_of, root.id, root.object_name or "form")
    if built is not None:
        return built
    rect = rect_of.get(root.id, Rect(0, 0, 0, 0))
    return DropHost(root.id, "bare_empty", root.object_name or "form", rect)


def _gather(host: DropHost, pointer: Tuple[int, int], depth: int, found: List[Tuple[int, DropHost]]) -> None:
    if _candidate(host, pointer):
        found.append((depth, host))
    for child in host.children:
        _gather(child, pointer, depth + 1, found)


def _candidate(host: DropHost, pointer: Tuple[int, int]) -> bool:
    if host.kind == "grid" and _contains(_pad(host.rect, GHOST_BAND), pointer):
        return True
    if _contains(_grow(host.rect), pointer):
        return True
    return _contains(host.rect, pointer)


def _resolve_host(
    host: DropHost,
    pointer: Tuple[int, int],
    payload: DropPayload,
    blocked: FrozenSet[NodeId],
) -> Optional[DropTarget]:
    if host.kind in ("vbox", "hbox"):
        return _resolve_box(host, pointer, payload)
    if host.kind == "splitter":
        return _resolve_splitter(host, pointer)
    if host.kind == "grid":
        return _resolve_grid(host, pointer, payload, blocked)
    if host.kind == "form":
        return _resolve_form(host, pointer, payload)
    if host.kind == "pages":
        return _resolve_pages(host, pointer)
    if host.kind == "bare_empty":
        return _accept(
            host,
            "auto_layout",
            "Into %s · makes a vertical layout" % (host.name or "the container"),
            "Into %s · makes a vertical layout" % (host.name or "the container"),
            DropIndicator(_inset(host.rect, 4), dashed=True),
        )
    if host.kind == "bare_free":
        return _resolve_free(host, pointer, payload)
    return None


def _resolve_box(host: DropHost, pointer: Tuple[int, int], payload: DropPayload) -> AcceptedDrop:
    vertical = host.kind == "vbox"
    wrap = _wrap_slot(host, pointer, vertical, payload)
    if wrap is not None:
        side, slot = wrap
        layout = "QHBoxLayout" if vertical else "QVBoxLayout"
        phrase = "horizontal row" if vertical else "vertical layout"
        name = slot.text or "the item"
        sentence = "Beside %s · makes a %s" % (name, phrase)
        edge = _wrap_line(slot.rect, vertical, side)
        return _accept(
            host,
            "wrap",
            sentence,
            sentence,
            DropIndicator(edge),
            wrap_neighbour=slot.node,
            wrap_side=side,
            wrap_layout=layout,
            index=slot.index,
        )
    index = _box_index(host.slots, pointer, vertical)
    sentence = _between(host.slots, index, "Insert")
    return _accept(
        host,
        "box",
        sentence,
        sentence,
        DropIndicator(_gap_line(host, index, vertical)),
        index=index,
    )


def _resolve_splitter(host: DropHost, pointer: Tuple[int, int]) -> AcceptedDrop:
    vertical = _splitter_vertical(host)
    index = _box_index(host.slots, pointer, vertical)
    sentence = _pane_sentence(host.slots, index)
    return _accept(
        host,
        "splitter",
        sentence,
        sentence,
        DropIndicator(_gap_line(host, index, vertical)),
        index=index,
    )


def _resolve_grid(
    host: DropHost,
    pointer: Tuple[int, int],
    payload: DropPayload,
    blocked: FrozenSet[NodeId],
) -> Optional[DropTarget]:
    side = _ghost_side(host.rect, pointer)
    if side is not None:
        return _ghost(host, side, payload, blocked)
    slot = _slot_at(host.slots, pointer)
    if slot is None:
        slot = _nearest_slot(host.slots, pointer)
    if slot is None:
        return _accept(
            host,
            "grid_cell",
            "Into row 1, column 1 of the grid",
            "Row 1, column 1",
            DropIndicator(host.rect, dashed=True),
            row=0,
            column=0,
            rowspan=payload.rowspan,
            colspan=payload.colspan,
        )
    if slot.node is None:
        return _grid_cell(host, slot, payload, blocked)
    if _in_center(slot.rect, pointer):
        return NoDrop()
    return _grid_edge(host, slot, pointer, payload)


def _resolve_form(host: DropHost, pointer: Tuple[int, int], payload: DropPayload) -> Optional[DropTarget]:
    if payload.kind == "spacer":
        return _refuse(host, "A spacer can't sit in a form.", DropIndicator(host.rect, dashed=True, role="problem"))
    slot = _slot_at(host.slots, pointer)
    if slot is None:
        slot = _nearest_slot(host.slots, pointer)
    if slot is None:
        return _form_new_row(host, 0, payload, "")
    if slot.role == "new_page":
        return None
    if slot.node is None and slot.role in ("label", "field"):
        role: FormRole = "label" if slot.role == "label" else "field"
        chip = "%s of row %d" % ("Label" if role == "label" else "Field", slot.row + 1)
        return _accept(
            host,
            "form_cell",
            chip,
            chip,
            DropIndicator(slot.rect, dashed=True),
            row=slot.row,
            column=0 if role == "label" else 1,
            role=role,
        )
    return _form_nearest_row(host, slot, pointer, payload)


def _resolve_pages(host: DropHost, pointer: Tuple[int, int]) -> Optional[DropTarget]:
    for slot in host.slots:
        if not _contains(slot.rect, pointer):
            continue
        if slot.role == "new_page":
            sentence = "New tab"
            return _accept(host, "new_page", sentence, sentence, DropIndicator(slot.rect, dashed=True))
        if slot.role == "page" and slot.node is not None:
            name = slot.text or "the page"
            sentence = "Into the %s tab" % name
            return _accept(
                host,
                "page",
                sentence,
                sentence,
                DropIndicator(slot.rect),
                page=slot.node,
                spring_id=slot.node,
            )
    return None


def _resolve_free(host: DropHost, pointer: Tuple[int, int], payload: DropPayload) -> AcceptedDrop:
    width, height = payload.default_size
    x = _snap_to(pointer[0], payload.snap)
    y = _snap_to(pointer[1], payload.snap)
    chip = "x %d, y %d" % (x, y)
    return _accept(
        host,
        "free",
        chip,
        chip,
        DropIndicator(Rect(x, y, width, height)),
        x=x,
        y=y,
        width=width,
        height=height,
    )


def _grid_cell(
    host: DropHost,
    slot: SlotGeom,
    payload: DropPayload,
    blocked: FrozenSet[NodeId],
) -> DropTarget:
    if not _span_fits(host, slot.row, slot.column, payload.rowspan, payload.colspan, blocked):
        return _span_refuse(host, slot.rect, payload)
    sentence = "Into row %d, column %d of the grid" % (slot.row + 1, slot.column + 1)
    chip = "Row %d, column %d" % (slot.row + 1, slot.column + 1)
    return _accept(
        host,
        "grid_cell",
        sentence,
        chip,
        DropIndicator(slot.rect, dashed=True),
        row=slot.row,
        column=slot.column,
        rowspan=payload.rowspan,
        colspan=payload.colspan,
    )


def _grid_edge(host: DropHost, slot: SlotGeom, pointer: Tuple[int, int], payload: DropPayload) -> AcceptedDrop:
    edge = _nearest_edge(slot.rect, pointer)
    name = slot.text or "the item"
    if edge in ("left", "right"):
        column = slot.column if edge == "left" else slot.column + slot.colspan
        word = "before" if edge == "left" else "after"
        sentence = "New column %s %s" % (word, name)
        line = _edge_line(slot.rect, edge)
        return _accept(
            host,
            "grid_column",
            sentence,
            sentence,
            DropIndicator(line),
            row=slot.row,
            column=column,
            rowspan=payload.rowspan,
            colspan=payload.colspan,
        )
    row = slot.row if edge == "top" else slot.row + slot.rowspan
    word = "before" if edge == "top" else "after"
    sentence = "New row %s %s" % (word, name)
    return _accept(
        host,
        "grid_row",
        sentence,
        sentence,
        DropIndicator(_edge_line(slot.rect, edge)),
        row=row,
        column=slot.column,
        rowspan=payload.rowspan,
        colspan=payload.colspan,
    )


def _ghost(
    host: DropHost,
    side: str,
    payload: DropPayload,
    blocked: FrozenSet[NodeId],
) -> DropTarget:
    rows, cols = _grid_extent(host)
    if side == "bottom":
        sentence = "New row %d" % (rows + 1)
        rect = Rect(host.rect.x, host.rect.y + host.rect.height, host.rect.width, GHOST_BAND)
        if not _span_fits(host, rows, 0, payload.rowspan, payload.colspan, blocked):
            return _span_refuse(host, rect, payload)
        return _accept(
            host,
            "grid_row",
            sentence,
            sentence,
            DropIndicator(rect, dashed=True),
            row=rows,
            column=0,
            rowspan=payload.rowspan,
            colspan=payload.colspan,
        )
    if side == "right":
        sentence = "New column %d" % (cols + 1)
        rect = Rect(host.rect.x + host.rect.width, host.rect.y, GHOST_BAND, host.rect.height)
        return _accept(
            host,
            "grid_column",
            sentence,
            sentence,
            DropIndicator(rect, dashed=True),
            row=0,
            column=cols,
            rowspan=payload.rowspan,
            colspan=payload.colspan,
        )
    if side == "top":
        sentence = "New row 1"
        rect = Rect(host.rect.x, host.rect.y - GHOST_BAND, host.rect.width, GHOST_BAND)
        return _accept(
            host,
            "grid_row",
            sentence,
            sentence,
            DropIndicator(rect, dashed=True),
            row=0,
            column=0,
            rowspan=payload.rowspan,
            colspan=payload.colspan,
        )
    sentence = "New column 1"
    rect = Rect(host.rect.x - GHOST_BAND, host.rect.y, GHOST_BAND, host.rect.height)
    return _accept(
        host,
        "grid_column",
        sentence,
        sentence,
        DropIndicator(rect, dashed=True),
        row=0,
        column=0,
        rowspan=payload.rowspan,
        colspan=payload.colspan,
    )


def _form_nearest_row(
    host: DropHost,
    slot: SlotGeom,
    pointer: Tuple[int, int],
    payload: DropPayload,
) -> AcceptedDrop:
    mid = slot.rect.y + (slot.rect.height // 2)
    if pointer[1] < mid:
        row = slot.row
        previous = _row_text(host, row - 1)
        name = _row_text(host, row) or slot.text
        sentence = "New row before %s" % name if name else "New row %d" % (row + 1)
        if previous:
            sentence = "New row after %s" % previous
        line_y = slot.rect.y
    else:
        row = slot.row + 1
        name = _row_text(host, slot.row) or slot.text
        sentence = "New row after %s" % name if name else "New row %d" % (row + 1)
        line_y = slot.rect.y + slot.rect.height - 1
    return _form_new_row(host, row, payload, sentence, line_y)


def _form_new_row(
    host: DropHost,
    row: int,
    payload: DropPayload,
    sentence: str,
    line_y: Optional[int] = None,
) -> AcceptedDrop:
    role: FormRole = "label" if payload.kind == "label" else "field"
    if not sentence:
        sentence = "New row %d" % (row + 1)
    y = host.rect.y + 3 if line_y is None else line_y
    return _accept(
        host,
        "form_row",
        sentence,
        sentence,
        DropIndicator(_hline(host.rect, y)),
        row=row,
        role=role,
    )


def _span_fits(
    host: DropHost,
    row: int,
    column: int,
    rowspan: int,
    colspan: int,
    ignore: FrozenSet[NodeId],
) -> bool:
    if rowspan < 1 or colspan < 1:
        return False
    rows, cols = _grid_extent(host)
    if cols and column + colspan > cols:
        return False
    if rows and row < rows and row + rowspan > rows:
        return False
    covered = _covered(host, ignore)
    for dr in range(rowspan):
        for dc in range(colspan):
            owner = covered.get((row + dr, column + dc))
            if owner is not None:
                return False
    return True


def _covered(host: DropHost, ignore: FrozenSet[NodeId]) -> Dict[Tuple[int, int], NodeId]:
    covered: Dict[Tuple[int, int], NodeId] = {}
    for slot in host.slots:
        if slot.node is None or slot.node in ignore:
            continue
        for dr in range(max(slot.rowspan, 1)):
            for dc in range(max(slot.colspan, 1)):
                covered[(slot.row + dr, slot.column + dc)] = slot.node
    return covered


def _span_refuse(host: DropHost, rect: Rect, payload: DropPayload) -> RefusedDrop:
    if payload.colspan > 1:
        sentence = "Needs %d free columns here" % payload.colspan
    else:
        sentence = "Needs %d free rows here" % payload.rowspan
    return _refuse(host, sentence, DropIndicator(rect, dashed=True, role="problem"))


def _itself(host: DropHost) -> RefusedDrop:
    sentence = "A widget can't go inside itself."
    return _refuse(host, sentence, DropIndicator(_grow(host.rect), dashed=True, role="problem"))


def _refuse(host: DropHost, sentence: str, indicator: DropIndicator) -> RefusedDrop:
    return RefusedDrop(sentence, sentence, host.node, indicator, _frame(host))


def _accept(
    host: DropHost,
    action: DropAction,
    sentence: str,
    chip: str,
    indicator: DropIndicator,
    index: int = 0,
    row: int = 0,
    column: int = 0,
    rowspan: int = 1,
    colspan: int = 1,
    role: FormRole = "",
    wrap_neighbour: Optional[NodeId] = None,
    wrap_side: WrapSide = "",
    wrap_layout: str = "",
    page: Optional[NodeId] = None,
    x: int = 0,
    y: int = 0,
    width: int = 0,
    height: int = 0,
    spring_id: Optional[NodeId] = None,
) -> AcceptedDrop:
    return AcceptedDrop(
        sentence,
        chip,
        host.node,
        action,
        indicator,
        _frame(host),
        index,
        row,
        column,
        rowspan,
        colspan,
        role,
        wrap_neighbour,
        wrap_side,
        wrap_layout,
        page,
        x,
        y,
        width,
        height,
        spring_id,
    )


def _frame(host: DropHost) -> Rect:
    return _grow(host.rect)


def _wrap_slot(
    host: DropHost,
    pointer: Tuple[int, int],
    vertical: bool,
    payload: DropPayload,
) -> Optional[Tuple[WrapSide, SlotGeom]]:
    best: Optional[Tuple[int, WrapSide, SlotGeom]] = None
    for slot in host.slots:
        if slot.node is None or slot.node in payload.source_ids:
            continue
        if not _on_main_span(slot.rect, pointer, vertical):
            continue
        side, distance = _cross_side(slot.rect, pointer, vertical)
        if distance > CROSS_EDGE:
            continue
        if best is None or distance < best[0]:
            best = (distance, side, slot)
    if best is None:
        return None
    return best[1], best[2]


def _cross_side(rect: Rect, pointer: Tuple[int, int], vertical: bool) -> Tuple[WrapSide, int]:
    if vertical:
        left = abs(pointer[0] - rect.x)
        right = abs(pointer[0] - (rect.x + rect.width))
        if left <= right:
            return "before", left
        return "after", right
    top = abs(pointer[1] - rect.y)
    bottom = abs(pointer[1] - (rect.y + rect.height))
    if top <= bottom:
        return "before", top
    return "after", bottom


def _on_main_span(rect: Rect, pointer: Tuple[int, int], vertical: bool) -> bool:
    if vertical:
        return rect.y <= pointer[1] < rect.y + max(rect.height, 1)
    return rect.x <= pointer[0] < rect.x + max(rect.width, 1)


def _box_index(slots: Sequence[SlotGeom], pointer: Tuple[int, int], vertical: bool) -> int:
    index = 0
    coord = pointer[1] if vertical else pointer[0]
    ordered = sorted(slots, key=lambda slot: slot.index)
    for slot in ordered:
        mid = _mid(slot.rect, vertical)
        if coord >= mid:
            index = slot.index + 1
    return index


def _mid(rect: Rect, vertical: bool) -> int:
    if vertical:
        return rect.y + (rect.height // 2)
    return rect.x + (rect.width // 2)


def _between(slots: Sequence[SlotGeom], index: int, verb: str) -> str:
    ordered = sorted(slots, key=lambda slot: slot.index)
    previous = ""
    nxt = ""
    for slot in ordered:
        if slot.index < index and slot.text:
            previous = slot.text
        if slot.index >= index and slot.text and not nxt:
            nxt = slot.text
    if previous and nxt:
        return "%s between %s and %s" % (verb, previous, nxt)
    if nxt:
        return "%s before %s" % (verb, nxt)
    if previous:
        return "%s after %s" % (verb, previous)
    return "%s here" % verb


def _pane_sentence(slots: Sequence[SlotGeom], index: int) -> str:
    ordered = sorted(slots, key=lambda slot: slot.index)
    previous = ""
    for slot in ordered:
        if slot.index < index and slot.text:
            previous = slot.text
    if previous:
        return "New pane after %s" % previous
    for slot in ordered:
        if slot.text:
            return "New pane before %s" % slot.text
    return "New pane"


def _gap_line(host: DropHost, index: int, vertical: bool) -> Rect:
    frame = host.rect
    ordered = sorted(host.slots, key=lambda slot: slot.index)
    previous = None
    nxt = None
    for slot in ordered:
        if slot.index < index:
            previous = slot
        elif nxt is None:
            nxt = slot
    if previous is None:
        if vertical:
            return _hline(frame, frame.y + 3)
        return _vline(frame, frame.x + 3)
    if nxt is None:
        if vertical:
            return _hline(frame, frame.y + frame.height - 5)
        return _vline(frame, frame.x + frame.width - 5)
    if vertical:
        gap = (previous.rect.y + previous.rect.height + nxt.rect.y) // 2
        return _hline(frame, gap - 1)
    gap = (previous.rect.x + previous.rect.width + nxt.rect.x) // 2
    return _vline(frame, gap - 1)


def _wrap_line(rect: Rect, vertical: bool, side: WrapSide) -> Rect:
    if vertical:
        x = rect.x - 1 if side == "before" else rect.x + rect.width - 1
        return Rect(x, rect.y, 2, max(rect.height, 2))
    y = rect.y - 1 if side == "before" else rect.y + rect.height - 1
    return Rect(rect.x, y, max(rect.width, 2), 2)


def _hline(rect: Rect, y: int) -> Rect:
    return Rect(rect.x + 4, y, max(rect.width - 8, 2), 2)


def _vline(rect: Rect, x: int) -> Rect:
    return Rect(x, rect.y + 4, 2, max(rect.height - 8, 2))


def _edge_line(rect: Rect, edge: str) -> Rect:
    if edge == "left":
        return Rect(rect.x, rect.y, 2, max(rect.height, 2))
    if edge == "right":
        return Rect(rect.x + rect.width - 2, rect.y, 2, max(rect.height, 2))
    if edge == "top":
        return Rect(rect.x, rect.y, max(rect.width, 2), 2)
    return Rect(rect.x, rect.y + rect.height - 2, max(rect.width, 2), 2)


def _nearest_edge(rect: Rect, pointer: Tuple[int, int]) -> str:
    distances = {
        "left": pointer[0] - rect.x,
        "right": rect.x + rect.width - pointer[0],
        "top": pointer[1] - rect.y,
        "bottom": rect.y + rect.height - pointer[1],
    }
    return min(distances, key=lambda edge: distances[edge])


def _in_center(rect: Rect, pointer: Tuple[int, int]) -> bool:
    if rect.width <= 0 or rect.height <= 0:
        return False
    dx = abs(pointer[0] - (rect.x + rect.width / 2.0))
    dy = abs(pointer[1] - (rect.y + rect.height / 2.0))
    return dx < rect.width * 0.25 and dy < rect.height * 0.25


def _slot_at(slots: Sequence[SlotGeom], pointer: Tuple[int, int]) -> Optional[SlotGeom]:
    for slot in slots:
        if _contains(slot.rect, pointer):
            return slot
    return None


def _nearest_slot(slots: Sequence[SlotGeom], pointer: Tuple[int, int]) -> Optional[SlotGeom]:
    best: Optional[SlotGeom] = None
    distance = 0
    for slot in slots:
        current = _distance(slot.rect, pointer)
        if best is None or current < distance:
            best = slot
            distance = current
    return best


def _ghost_side(rect: Rect, pointer: Tuple[int, int]) -> Optional[str]:
    if _contains(rect, pointer):
        return None
    x, y = pointer
    left = rect.x - x if x < rect.x else 0
    right = x - (rect.x + rect.width - 1) if x >= rect.x + rect.width else 0
    top = rect.y - y if y < rect.y else 0
    bottom = y - (rect.y + rect.height - 1) if y >= rect.y + rect.height else 0
    outside = max(left, right, top, bottom)
    if outside <= 0 or outside > GHOST_BAND:
        return None
    horizontal = max(left, right)
    vertical = max(top, bottom)
    if horizontal >= vertical:
        if right >= left and right > 0:
            return "right"
        if left > 0:
            return "left"
    if bottom >= top and bottom > 0:
        return "bottom"
    if top > 0:
        return "top"
    return None


def _grid_extent(host: DropHost) -> Tuple[int, int]:
    rows = 0
    cols = 0
    for slot in host.slots:
        rows = max(rows, slot.row + max(slot.rowspan, 1))
        cols = max(cols, slot.column + max(slot.colspan, 1))
    return rows, cols


def _row_text(host: DropHost, row: int) -> str:
    if row < 0:
        return ""
    label = ""
    other = ""
    for slot in host.slots:
        if slot.row != row or not slot.text:
            continue
        if slot.role == "label" and not label:
            label = slot.text
        elif not other:
            other = slot.text
    return label or other


def _splitter_vertical(host: DropHost) -> bool:
    if len(host.slots) < 2:
        return True
    first, second = host.slots[0], host.slots[1]
    return abs(second.rect.y - first.rect.y) >= abs(second.rect.x - first.rect.x)


def _snap_to(value: int, enabled: bool) -> int:
    if not enabled:
        return value
    return (value // SNAP) * SNAP


def _contains(rect: Rect, pointer: Tuple[int, int]) -> bool:
    return rect.contains(pointer[0], pointer[1])


def _distance(rect: Rect, pointer: Tuple[int, int]) -> int:
    if _contains(rect, pointer):
        return 0
    x, y = pointer
    if x < rect.x:
        dx = rect.x - x
    elif x >= rect.x + rect.width:
        dx = x - (rect.x + rect.width - 1)
    else:
        dx = 0
    if y < rect.y:
        dy = rect.y - y
    elif y >= rect.y + rect.height:
        dy = y - (rect.y + rect.height - 1)
    else:
        dy = 0
    return dx + dy


def _grow(rect: Rect, minimum: int = MIN_HIT) -> Rect:
    width = rect.width
    height = rect.height
    x = rect.x
    y = rect.y
    if width < minimum:
        x -= (minimum - width) // 2
        width = minimum
    if height < minimum:
        y -= (minimum - height) // 2
        height = minimum
    return Rect(x, y, width, height)


def _pad(rect: Rect, band: int) -> Rect:
    return Rect(rect.x - band, rect.y - band, rect.width + band * 2, rect.height + band * 2)


def _inset(rect: Rect, pad: int) -> Rect:
    return Rect(rect.x + pad, rect.y + pad, max(rect.width - pad * 2, 2), max(rect.height - pad * 2, 2))


def _widget_host(
    doc: UiDocument,
    rect_of: Dict[NodeId, Rect],
    widget_id: NodeId,
    fallback_name: str,
) -> Optional[DropHost]:
    widget = doc.get(widget_id)
    if not isinstance(widget, WidgetNode):
        return None
    rect = rect_of.get(widget_id)
    if rect is None:
        return None
    name = widget.object_name or fallback_name
    layout = widget.layout
    if layout is not None:
        return _layout_host(doc, rect_of, layout, name, rect)
    if widget.class_name in PAGE_CONTAINERS:
        return _pages_host(doc, rect_of, widget, name, rect)
    children = []
    for child in widget.child_widgets:
        built = _widget_host(doc, rect_of, child.id, name)
        if built is not None:
            children.append(built)
    kind: HostKind = "bare_free" if widget.child_widgets else "bare_empty"
    return DropHost(widget.id, kind, name, rect, (), tuple(children))


def _layout_host(
    doc: UiDocument,
    rect_of: Dict[NodeId, Rect],
    layout: LayoutNode,
    owner_name: str,
    fallback: Rect,
) -> DropHost:
    rect = rect_of.get(layout.id, fallback)
    kind = _LAYOUT_CLASS.get(layout.class_name, "vbox")
    if kind == "grid":
        slots, children = _grid_slots(doc, rect_of, layout, rect)
    elif kind == "form":
        slots, children = _form_slots(doc, rect_of, layout, rect)
    else:
        slots, children = _box_slots(doc, rect_of, layout, rect, kind == "vbox")
    return DropHost(layout.id, kind, owner_name, rect, slots, children)


def _box_slots(
    doc: UiDocument,
    rect_of: Dict[NodeId, Rect],
    layout: LayoutNode,
    layout_rect: Rect,
    vertical: bool,
) -> Tuple[Tuple[SlotGeom, ...], Tuple[DropHost, ...]]:
    slots: List[SlotGeom] = []
    children: List[DropHost] = []
    items = layout.items
    for index, item in enumerate(items):
        content = item.content
        rect = _content_rect(rect_of, content, layout_rect, index, len(items), vertical)
        node_id = content.id if content is not None else None
        slots.append(SlotGeom(rect, index, node_id, _visible(content) if content is not None else ""))
        built = _content_host(doc, rect_of, content)
        if built is not None:
            children.append(built)
    return tuple(slots), tuple(children)


def _grid_slots(
    doc: UiDocument,
    rect_of: Dict[NodeId, Rect],
    layout: LayoutNode,
    layout_rect: Rect,
) -> Tuple[Tuple[SlotGeom, ...], Tuple[DropHost, ...]]:
    # grid_shape also records empty cells and overlap pairs. A drop only needs
    # the origin of each item and the cells a span already covers.
    origins: Dict[Tuple[int, int], Tuple[LayoutItemNode, Optional[Node]]] = {}
    covered = set()
    rows = 0
    cols = 0
    for item in layout.items:
        row = 0 if item.row is None else item.row
        column = 0 if item.column is None else item.column
        raw_r = 1 if item.rowspan is None else item.rowspan
        raw_c = 1 if item.colspan is None else item.colspan
        rows = max(rows, row + raw_r)
        cols = max(cols, column + raw_c)
        origins[(row, column)] = (item, item.content)
        if raw_r <= 1 and raw_c <= 1:
            continue
        for covered_row in range(row, row + raw_r):
            for covered_column in range(column, column + raw_c):
                if covered_row == row and covered_column == column:
                    continue
                covered.add((covered_row, covered_column))
    rows = max(rows, 1)
    cols = max(cols, 1)
    xs, ys = _grid_edges(layout_rect, rows, cols, origins, rect_of)
    slots: List[SlotGeom] = []
    children: List[DropHost] = []
    seen = set()
    for row in range(rows):
        for column in range(cols):
            origin = origins.get((row, column))
            if origin is None:
                if (row, column) in covered:
                    continue
                slots.append(
                    SlotGeom(_cell_rect(xs, ys, row, column, 1, 1), 0, None, "", row, column, 1, 1)
                )
                continue
            item, content = origin
            if item.id in seen:
                continue
            seen.add(item.id)
            span_r = _cell_span(item.rowspan)
            span_c = _cell_span(item.colspan)
            rect = _content_rect_or_cell(rect_of, content, xs, ys, row, column, span_r, span_c)
            node_id = content.id if content is not None else None
            text = _visible(content) if content is not None else ""
            slots.append(SlotGeom(rect, 0, node_id, text, row, column, span_r, span_c))
            built = _content_host(doc, rect_of, content)
            if built is not None:
                children.append(built)
    return tuple(slots), tuple(children)


def _form_slots(
    doc: UiDocument,
    rect_of: Dict[NodeId, Rect],
    layout: LayoutNode,
    layout_rect: Rect,
) -> Tuple[Tuple[SlotGeom, ...], Tuple[DropHost, ...]]:
    rows = form_rows(doc, layout.id)
    count = max(len(rows), 1)
    height = max(layout_rect.height // count, 1)
    slots: List[SlotGeom] = []
    children: List[DropHost] = []
    roles = (("label", 0), ("field", 1), ("spanning", 0))
    for index, triple in enumerate(rows):
        y = layout_rect.y + index * height
        row_rect = Rect(layout_rect.x, y, layout_rect.width, height)
        item_ids = {"label": triple[0], "field": triple[1], "spanning": triple[2]}
        for role, column in roles:
            item_id = item_ids[role]
            if item_id is None:
                if role == "spanning":
                    continue
                width = layout_rect.width // 2
                x = layout_rect.x if column == 0 else layout_rect.x + width
                slots.append(SlotGeom(Rect(x, y, width, height), index, None, "", index, column, 1, 1, role))
                continue
            item = doc.get(item_id)
            content = item.content if isinstance(item, LayoutItemNode) else None
            rect = rect_of.get(content.id, row_rect) if content is not None else row_rect
            if role == "spanning":
                rect = Rect(layout_rect.x, y, layout_rect.width, height)
            node_id = content.id if content is not None else None
            slots.append(
                SlotGeom(
                    rect,
                    index,
                    node_id,
                    _visible(content) if content is not None else "",
                    index,
                    column,
                    1,
                    2 if role == "spanning" else 1,
                    role,
                )
            )
            built = _content_host(doc, rect_of, content)
            if built is not None:
                children.append(built)
    return tuple(slots), tuple(children)


def _pages_host(
    doc: UiDocument,
    rect_of: Dict[NodeId, Rect],
    widget: WidgetNode,
    name: str,
    rect: Rect,
) -> DropHost:
    kind: HostKind = "splitter" if widget.class_name == "QSplitter" else "pages"
    slots: List[SlotGeom] = []
    children: List[DropHost] = []
    for index, child in enumerate(widget.child_widgets):
        child_rect = rect_of.get(child.id, rect)
        role = "page" if kind == "pages" else "pane"
        slots.append(SlotGeom(child_rect, index, child.id, _visible(child), role=role))
        if kind == "splitter":
            continue
        built = _widget_host(doc, rect_of, child.id, child.object_name or name)
        if built is not None:
            children.append(built)
    return DropHost(widget.id, kind, name, rect, tuple(slots), tuple(children))


def _content_host(doc: UiDocument, rect_of: Dict[NodeId, Rect], content: Optional[Node]) -> Optional[DropHost]:
    if isinstance(content, LayoutNode):
        fallback = rect_of.get(content.id, Rect(0, 0, MIN_HIT, MIN_HIT))
        return _layout_host(doc, rect_of, content, content.object_name or "layout", fallback)
    if isinstance(content, WidgetNode):
        if content.layout is None and content.class_name not in PAGE_CONTAINERS and not content.child_widgets:
            return None
        return _widget_host(doc, rect_of, content.id, content.object_name or "widget")
    return None


def _content_rect(
    rect_of: Dict[NodeId, Rect],
    content: Optional[Node],
    layout_rect: Rect,
    index: int,
    count: int,
    vertical: bool,
) -> Rect:
    if content is not None and content.id in rect_of:
        return rect_of[content.id]
    count = max(count, 1)
    if vertical:
        height = max(layout_rect.height // count, 1)
        return Rect(layout_rect.x, layout_rect.y + index * height, layout_rect.width, height)
    width = max(layout_rect.width // count, 1)
    return Rect(layout_rect.x + index * width, layout_rect.y, width, layout_rect.height)


def _grid_edges(
    layout_rect: Rect,
    rows: int,
    cols: int,
    origins: Dict[Tuple[int, int], Tuple[LayoutItemNode, Optional[Node]]],
    rect_of: Dict[NodeId, Rect],
) -> Tuple[List[int], List[int]]:
    row_samples: Dict[int, Tuple[int, int]] = {}
    col_samples: Dict[int, Tuple[int, int]] = {}
    for (row, column), (_item, content) in origins.items():
        if content is None or content.id not in rect_of:
            continue
        rect = rect_of[content.id]
        row_samples[row] = (rect.y, rect.y + rect.height)
        col_samples[column] = (rect.x, rect.x + rect.width)
    return (
        _edges(layout_rect.x, layout_rect.width, cols, col_samples),
        _edges(layout_rect.y, layout_rect.height, rows, row_samples),
    )


def _edges(origin: int, size: int, count: int, samples: Dict[int, Tuple[int, int]]) -> List[int]:
    edges: List[Optional[int]] = [None] * (count + 1)
    edges[0] = origin
    edges[count] = origin + size
    for index, (start, end) in samples.items():
        if 0 <= index < count:
            edges[index] = start if edges[index] is None else min(int(edges[index]), start)
            edges[index + 1] = end if edges[index + 1] is None else max(int(edges[index + 1]), end)
    for index in range(count + 1):
        if edges[index] is not None:
            continue
        previous = index - 1
        while previous >= 0 and edges[previous] is None:
            previous -= 1
        nxt = index + 1
        while nxt <= count and edges[nxt] is None:
            nxt += 1
        if previous < 0 or nxt > count or edges[previous] is None or edges[nxt] is None:
            edges[index] = origin
            continue
        span = nxt - previous
        edges[index] = int(edges[previous]) + (int(edges[nxt]) - int(edges[previous])) * (index - previous) // span
    return [int(item) if item is not None else origin for item in edges]


def _cell_rect(xs: Sequence[int], ys: Sequence[int], row: int, column: int, rowspan: int, colspan: int) -> Rect:
    x0 = xs[column]
    y0 = ys[row]
    x1 = xs[min(column + colspan, len(xs) - 1)]
    y1 = ys[min(row + rowspan, len(ys) - 1)]
    return Rect(x0, y0, max(x1 - x0, 1), max(y1 - y0, 1))


def _content_rect_or_cell(
    rect_of: Dict[NodeId, Rect],
    content: Optional[Node],
    xs: Sequence[int],
    ys: Sequence[int],
    row: int,
    column: int,
    rowspan: int,
    colspan: int,
) -> Rect:
    if content is not None and content.id in rect_of:
        return rect_of[content.id]
    return _cell_rect(xs, ys, row, column, rowspan, colspan)


def _cell_span(value: Optional[int]) -> int:
    if value is None or value < 1:
        return 1
    return value


def _visible(node: object) -> str:
    if isinstance(node, WidgetNode):
        for key in ("text", "title", "windowTitle"):
            value = node.value(key)
            if isinstance(value, StringValue) and value.text:
                return value.text
        titled = node.attr("title")
        if titled is not None and isinstance(titled.value, StringValue) and titled.value.text:
            return titled.value.text
        return node.object_name
    if isinstance(node, SpacerNode):
        return node.name or "spacer"
    if isinstance(node, LayoutNode):
        return node.object_name
    return ""
