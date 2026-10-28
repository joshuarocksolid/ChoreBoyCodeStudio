"""Drop target from slot geometry (UX-DND-008). Qt-free.

The pointer picks the nearest slot boundary along the layout axis. It does not
have to land in the gap, and it does not pick "the widget under the pointer".
A shrunk nested layout stays hittable: its hit rect grows to 24 px.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, FrozenSet, List, Literal, Optional, Sequence, Tuple, Union

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.hit_index import Rect
from app.features.form_builder.engine.query.tree import PAGE_CONTAINERS, form_rows, is_container
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
#: UX_SPEC: an insertion band is at least this many screen px at every zoom.
INSERT_BAND_SCREEN = 8
SNAP = 8

HostKind = Literal[
    "vbox", "hbox", "grid", "form", "splitter", "pages", "bare_empty", "bare_free", "scroll_empty"
]
PayloadKind = Literal["widget", "label", "spacer"]
WIZARD_REFUSAL = "A wizard page can only go into a wizard."
DropAction = Literal[
    "box",
    "wrap",
    "grid_cell",
    "grid_row",
    "grid_reading",
    "grid_column",
    "form_cell",
    "form_row",
    "splitter",
    "page",
    "new_page",
    "auto_layout",
    "free",
    "dock_side",
    "wizard_step",
    "scroll_content",
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
    node: NodeId
    kind: HostKind
    name: str
    rect: Rect
    slots: Tuple[SlotGeom, ...] = ()
    children: Tuple["DropHost", ...] = ()
    #: "tab" or "page". Empty for layouts.
    noun: str = ""
    #: A main window: a dock widget dragged over it gets the four side bands (UX-CONT-012).
    dock_zone: bool = False
    #: A wizard: a wizard page dragged over it becomes a step (UX-CAT-014).
    wizard: bool = False


@dataclass(frozen=True)
class DropPayload:
    """What is being dragged. ``source_ids`` is empty for a new insert."""

    kind: PayloadKind
    source_ids: Tuple[NodeId, ...] = ()
    rowspan: int = 1
    colspan: int = 1
    snap: bool = True
    default_size: Tuple[int, int] = (80, 24)
    #: The dragged widget is a dock widget (UX-CONT-012).
    dock: bool = False
    #: The dragged widget is a wizard page (UX-CAT-014).
    wizard_page: bool = False


@dataclass(frozen=True)
class DropIndicator:
    rect: Rect
    dashed: bool = False
    role: IndicatorRole = "select"


@dataclass(frozen=True)
class AcceptedDrop:
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
    #: For ``dock_side``: "Left", "Right", "Top" or "Bottom".
    dock_side: str = ""


@dataclass(frozen=True)
class RefusedDrop:
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


DOCK_BAND_PX = 32
DOCK_REFUSAL = "In a main window, a dock widget goes on one of its sides."
_DOCK_ORDER = ("Left", "Right", "Top", "Bottom")
_DOCK_LABEL = {"Left": "left side", "Right": "right side", "Top": "top", "Bottom": "bottom"}


def keyboard_refusal(
    doc: UiDocument,
    anchor: Optional[NodeId],
    payload: DropPayload,
) -> Optional[str]:
    """UX-CAT-014. Enter has no pointer, so these two targets are refused outright.

    A wizard page goes only into a wizard. A dock widget on a main window goes
    on a side (the drag bands); the central area is not a keyboard target.
    """
    if payload.wizard_page and not _under_class(doc, anchor, "QWizard"):
        return WIZARD_REFUSAL
    if payload.dock and _central_area(doc, anchor):
        return DOCK_REFUSAL
    return None


def _under_class(doc: UiDocument, anchor: Optional[NodeId], class_name: str) -> bool:
    current = doc.get(anchor) if anchor is not None else doc.root
    if current is None:
        current = doc.root
    seen = set()
    while current is not None and current.id not in seen:
        seen.add(current.id)
        if isinstance(current, WidgetNode) and current.class_name == class_name:
            return True
        parent = doc.parent(current.id)
        current = parent
    return False


def _central_area(doc: UiDocument, anchor: Optional[NodeId]) -> bool:
    """True when a dock would land in a main window's central area (UX-CONT-012)."""
    root = doc.root
    if not isinstance(root, WidgetNode) or root.class_name != "QMainWindow":
        return False
    return not _under_class(doc, anchor, "QDockWidget")


def resolve_drop(
    root: DropHost,
    pointer: Tuple[int, int],
    payload: DropPayload,
    blocked: FrozenSet[NodeId] = frozenset(),
    min_band: int = 0,
) -> DropTarget:
    """``min_band``: the leading insertion band of a list item, in form px.
    The canvas passes ``INSERT_BAND_SCREEN`` over the zoom so the band keeps
    its screen size below 100%."""
    if payload.dock:
        zone = _dock_zone_at(root, pointer)
        if zone is not None:
            return _resolve_dock(zone, pointer)
    if payload.wizard_page:
        return _resolve_wizard_step(root, pointer)
    found: List[Tuple[int, DropHost]] = []
    _gather(root, pointer, 0, found)
    found.sort(
        key=lambda item: (
            _distance(_grow(item[1].rect), pointer),
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
        result = _resolve_host(host, pointer, payload, blocked, min_band)
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


def _dock_zone_at(root: DropHost, pointer: Tuple[int, int]) -> Optional[DropHost]:
    found: List[Tuple[int, DropHost]] = []
    _gather(root, pointer, 0, found)
    zones = [host for _depth, host in found if host.dock_zone and _contains(host.rect, pointer)]
    if not zones:
        return None
    return min(zones, key=lambda host: host.rect.width * host.rect.height)


def _resolve_wizard_step(root: DropHost, pointer: Tuple[int, int]) -> DropTarget:
    """A wizard page goes only into a wizard, as its next step (UX-CAT-014)."""
    found: List[Tuple[int, DropHost]] = []
    _gather(root, pointer, 0, found)
    holders = [host for _depth, host in found if _contains(host.rect, pointer)]
    if not holders:
        return NoDrop()
    # The pointer is usually over the wizard's shown page, so look for the
    # innermost wizard that holds it, not only at the deepest host.
    wizards = [host for host in holders if host.wizard]
    if not wizards:
        deepest = min(holders, key=lambda host: host.rect.width * host.rect.height)
        return _refuse(deepest, WIZARD_REFUSAL, DropIndicator(deepest.rect, dashed=True, role="problem"))
    wizard = min(wizards, key=lambda host: host.rect.width * host.rect.height)
    sentence = "New step"
    return _accept(
        wizard, "wizard_step", sentence, sentence, DropIndicator(wizard.rect, dashed=True), index=len(wizard.slots)
    )


def _resolve_dock(host: DropHost, pointer: Tuple[int, int]) -> DropTarget:
    """The four bands along the inside edges of a main window (UX-CONT-012).

    The pointer picks the band whose outer edge it is nearest. The central
    area inside the bands is refused.
    """
    rect = host.rect
    band = DOCK_BAND_PX
    central = Rect(rect.x + band, rect.y + band, rect.width - 2 * band, rect.height - 2 * band)
    if _contains(central, pointer):
        return _refuse(host, DOCK_REFUSAL, DropIndicator(central, dashed=True, role="problem"))
    rects = {
        "Left": Rect(rect.x, rect.y, band, rect.height),
        "Right": Rect(rect.x + rect.width - band, rect.y, band, rect.height),
        "Top": Rect(rect.x, rect.y, rect.width, band),
        "Bottom": Rect(rect.x, rect.y + rect.height - band, rect.width, band),
    }
    distance = {
        "Left": pointer[0] - rect.x,
        "Right": rect.x + rect.width - pointer[0],
        "Top": pointer[1] - rect.y,
        "Bottom": rect.y + rect.height - pointer[1],
    }
    side = min(_DOCK_ORDER, key=lambda name: distance[name])
    sentence = "Dock on the %s" % _DOCK_LABEL[side]
    return _accept(
        host,
        "dock_side",
        sentence,
        sentence,
        DropIndicator(rects[side], dashed=True),
        dock_side=side,
    )


def _resolve_host(
    host: DropHost,
    pointer: Tuple[int, int],
    payload: DropPayload,
    blocked: FrozenSet[NodeId],
    min_band: int = 0,
) -> Optional[DropTarget]:
    if host.kind in ("vbox", "hbox"):
        return _resolve_box(host, pointer, payload, min_band)
    if host.kind == "splitter":
        return _resolve_splitter(host, pointer, min_band)
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
    if host.kind == "scroll_empty":
        sentence = "Into the scroll area · makes its content"
        return _accept(host, "scroll_content", sentence, sentence, DropIndicator(_inset(host.rect, 4), dashed=True))
    return None


def _resolve_box(
    host: DropHost, pointer: Tuple[int, int], payload: DropPayload, min_band: int = 0
) -> AcceptedDrop:
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
    if not host.slots:
        sentence = "Insert into %s" % (host.name or "the layout")
        return _accept(
            host,
            "box",
            sentence,
            sentence,
            DropIndicator(_cover_empty(host.rect), dashed=True),
            index=0,
        )
    index = _box_index(host.slots, pointer, vertical, min_band)
    sentence = _between(host.slots, index, "Insert", host.name or "the layout")
    return _accept(
        host,
        "box",
        sentence,
        sentence,
        DropIndicator(_gap_line(host, index, vertical)),
        index=index,
    )


def _resolve_splitter(host: DropHost, pointer: Tuple[int, int], min_band: int = 0) -> AcceptedDrop:
    vertical = _splitter_vertical(host)
    index = _box_index(host.slots, pointer, vertical, min_band)
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
    if slot.role == "tail":
        return _form_new_row(host, slot.row, payload, "New row at the end", slot.rect.y)
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
        word = host.noun or "tab"
        if slot.role == "new_page":
            sentence = "New %s" % word
            return _accept(host, "new_page", sentence, sentence, DropIndicator(slot.rect, dashed=True))
        if slot.role == "page" and slot.node is not None:
            name = slot.text or ("the %s" % word)
            sentence = "Into the %s %s" % (name, word)
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
    dock_side: str = "",
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
        dock_side=dock_side,
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


def _box_index(
    slots: Sequence[SlotGeom], pointer: Tuple[int, int], vertical: bool, min_band: int = 0
) -> int:
    """The insert index under ``pointer``. Each item's leading part, at least
    ``min_band`` form px and at most the whole item, inserts before it."""
    index = 0
    coord = pointer[1] if vertical else pointer[0]
    ordered = sorted(slots, key=lambda slot: slot.index)
    for slot in ordered:
        mid = _mid(slot.rect, vertical)
        if min_band > 0:
            start = slot.rect.y if vertical else slot.rect.x
            size = slot.rect.height if vertical else slot.rect.width
            mid = max(mid, start + min(size, min_band))
        if coord >= mid:
            index = slot.index + 1
    return index


def _mid(rect: Rect, vertical: bool) -> int:
    if vertical:
        return rect.y + (rect.height // 2)
    return rect.x + (rect.width // 2)


def _between(slots: Sequence[SlotGeom], index: int, verb: str, where: str = "") -> str:
    ordered = sorted(slots, key=lambda slot: slot.index)
    previous = ""
    nxt = ""
    for slot in ordered:
        if slot.index < index and slot.text:
            previous = _shown(slot.text)
        if slot.index >= index and slot.text and not nxt:
            nxt = _shown(slot.text)
    if previous and nxt:
        return "%s between %s and %s" % (verb, previous, nxt)
    if nxt:
        return "%s before %s" % (verb, nxt)
    if previous:
        return "%s after %s" % (verb, previous)
    if where:
        return "%s into %s" % (verb, where)
    return "%s here" % verb


def _shown(text: str) -> str:
    cleaned = text.strip()
    if cleaned.endswith(":"):
        cleaned = cleaned[:-1].rstrip()
    return cleaned


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


def _cover_empty(rect: Rect) -> Rect:
    """The into-indicator of an empty layout. At least the empty-mark minimum."""
    width = max(rect.width, 48)
    height = max(rect.height, 32)
    return Rect(
        rect.x - (width - rect.width) // 2,
        rect.y - (height - rect.height) // 2,
        width,
        height,
    )


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
    return _shown(label or other)


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
    if not is_container(doc, widget.id):
        return None
    children = []
    for child in widget.child_widgets:
        built = _widget_host(doc, rect_of, child.id, name)
        if built is not None:
            children.append(built)
    kind: HostKind = "bare_free" if widget.child_widgets else "bare_empty"
    if widget.class_name == "QScrollArea" and not widget.child_widgets:
        kind = "scroll_empty"
    return DropHost(widget.id, kind, name, rect, (), tuple(children), dock_zone=widget.class_name == "QMainWindow")


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
    bands = _form_bands(doc, rect_of, layout_rect, rows)
    slots: List[SlotGeom] = []
    children: List[DropHost] = []
    roles = (("label", 0), ("field", 1), ("spanning", 0))
    for index, triple in enumerate(rows):
        y, height = bands[index]
        row_rect = Rect(layout_rect.x, y, layout_rect.width, height)
        contents = _form_contents(doc, triple)
        item_ids = {"label": triple[0], "field": triple[1], "spanning": triple[2]}
        placed = {role: _content_rect_of(rect_of, contents[role]) for role in contents}
        for role, column in roles:
            item_id = item_ids[role]
            if item_id is None:
                if role == "spanning":
                    continue
                slots.append(
                    SlotGeom(
                        _empty_form_cell(layout_rect, row_rect, role, placed),
                        index,
                        None,
                        "",
                        index,
                        column,
                        1,
                        1,
                        role,
                    )
                )
                continue
            content = contents.get(role)
            rect = placed.get(role) or row_rect
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
    if bands:
        end = bands[-1][0] + bands[-1][1]
        bottom = layout_rect.y + layout_rect.height
        if bottom - end > 8:
            slots.append(
                SlotGeom(
                    Rect(layout_rect.x, end, layout_rect.width, bottom - end),
                    len(rows),
                    None,
                    "",
                    len(rows),
                    0,
                    1,
                    2,
                    "tail",
                )
            )
    return tuple(slots), tuple(children)


def _pages_host(
    doc: UiDocument,
    rect_of: Dict[NodeId, Rect],
    widget: WidgetNode,
    name: str,
    rect: Rect,
) -> DropHost:
    kind: HostKind = "splitter" if widget.class_name == "QSplitter" else "pages"
    noun = "page" if widget.class_name in ("QToolBox", "QStackedWidget") else "tab"
    is_wizard = widget.class_name == "QWizard"
    slots: List[SlotGeom] = []
    children: List[DropHost] = []
    if kind == "pages" and not widget.child_widgets:
        # No page yet: a drop anywhere in the container makes the first page (UX-CONT-009).
        slots.append(SlotGeom(rect, 0, None, "", role="new_page"))
    for index, child in enumerate(widget.child_widgets):
        child_rect = rect_of.get(child.id, rect)
        role = "page" if kind == "pages" else "pane"
        slots.append(SlotGeom(child_rect, index, child.id, _visible(child), role=role))
        built = _widget_host(doc, rect_of, child.id, child.object_name or name)
        if built is not None:
            children.append(built)
    return DropHost(widget.id, kind, name, rect, tuple(slots), tuple(children), noun, wizard=is_wizard)


def _content_host(doc: UiDocument, rect_of: Dict[NodeId, Rect], content: Optional[Node]) -> Optional[DropHost]:
    if isinstance(content, LayoutNode):
        fallback = rect_of.get(content.id, Rect(0, 0, MIN_HIT, MIN_HIT))
        return _layout_host(doc, rect_of, content, content.object_name or "layout", fallback)
    if isinstance(content, WidgetNode):
        return _widget_host(doc, rect_of, content.id, content.object_name or "widget")
    return None


def _form_contents(doc: UiDocument, triple: Tuple[Optional[NodeId], Optional[NodeId], Optional[NodeId]]) -> Dict[str, Optional[Node]]:
    found: Dict[str, Optional[Node]] = {}
    for role, item_id in (("label", triple[0]), ("field", triple[1]), ("spanning", triple[2])):
        item = doc.get(item_id) if item_id is not None else None
        content = item.content if isinstance(item, LayoutItemNode) else None
        found[role] = content
    return found


def _content_rect_of(rect_of: Dict[NodeId, Rect], content: Optional[Node]) -> Optional[Rect]:
    if content is None:
        return None
    return rect_of.get(content.id)


def _empty_form_cell(
    layout_rect: Rect,
    row_rect: Rect,
    role: str,
    placed: Dict[str, Optional[Rect]],
) -> Rect:
    mid = layout_rect.x + layout_rect.width // 2
    if role == "field":
        label = placed.get("label")
        left = label.x + label.width if label is not None else mid
        return Rect(left, row_rect.y, max(layout_rect.x + layout_rect.width - left, 1), row_rect.height)
    field = placed.get("field")
    right = field.x if field is not None else mid
    return Rect(layout_rect.x, row_rect.y, max(right - layout_rect.x, 1), row_rect.height)


def _form_bands(
    doc: UiDocument,
    rect_of: Dict[NodeId, Rect],
    layout_rect: Rect,
    rows: Sequence[Tuple[Optional[NodeId], Optional[NodeId], Optional[NodeId]]],
) -> List[Tuple[int, int]]:
    raw: List[Optional[Tuple[int, int]]] = []
    for triple in rows:
        rects = []
        for content in _form_contents(doc, triple).values():
            rect = _content_rect_of(rect_of, content)
            if rect is not None:
                rects.append(rect)
        if not rects:
            raw.append(None)
            continue
        top = min(rect.y for rect in rects)
        bottom = max(rect.y + rect.height for rect in rects)
        raw.append((top, max(bottom - top, 1)))
    if not raw:
        return []
    if all(band is None for band in raw):
        height = max(layout_rect.height // max(len(raw), 1), 1)
        return [(layout_rect.y + index * height, height) for index in range(len(raw))]
    known = [band[1] for band in raw if band is not None]
    default_height = known[0] if known else 24
    filled: List[Tuple[int, int]] = []
    cursor = layout_rect.y
    for index, band in enumerate(raw):
        if band is not None:
            filled.append(band)
            cursor = band[0] + band[1]
            continue
        nxt = next((item for item in raw[index + 1 :] if item is not None), None)
        height = default_height
        if nxt is not None and nxt[0] > cursor:
            height = max(min(default_height, nxt[0] - cursor), 1)
        filled.append((cursor, height))
        cursor += height
    return filled


@dataclass(frozen=True)
class OutlineRow:
    """One visible outline row, in the outline viewport's pixels."""

    node: NodeId
    top: int
    height: int
    width: int = 200
    left: int = 0
    depth: int = 0


def resolve_outline(
    doc: UiDocument,
    rows: Sequence[OutlineRow],
    y: int,
    payload: DropPayload,
    blocked: FrozenSet[NodeId] = frozenset(),
    *,
    x: Optional[int] = None,
    indent: int = 20,
) -> DropTarget:
    """Before, after, or into an outline row. The indicator uses outline pixels.

    ``x`` outdents when it sits a full indent left of the row. A climb that
    cannot land falls back to the row under the pointer, so a point on the
    row stays a before/after of that row.
    """

    row = _outline_row_at(rows, y)
    if row is None or not doc.contains(row.node):
        return NoDrop()
    if row.node in blocked:
        return _itself(_outline_host(row))
    into = _outline_can_enter(doc, row.node)
    band = _outline_band(row, y, into)
    if band == "into":
        return _outline_into(doc, row, payload)
    if x is not None:
        climbed = _outline_outdent(doc, rows, row, x, indent, payload)
        if climbed is not None:
            return climbed
    return _outline_beside(doc, row, band == "before", payload)


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


def _outline_row_at(rows: Sequence[OutlineRow], y: int) -> Optional[OutlineRow]:
    for row in rows:
        if row.top <= y < row.top + max(row.height, 1):
            return row
    return None


def _outline_band(row: OutlineRow, y: int, into: bool) -> str:
    height = max(row.height, 1)
    local = y - row.top
    if into:
        if local < height * 0.25:
            return "before"
        if local >= height * 0.75:
            return "after"
        return "into"
    if local < height * 0.5:
        return "before"
    return "after"


def _outline_can_enter(doc: UiDocument, node_id: NodeId) -> bool:
    node = doc.get(node_id)
    if isinstance(node, LayoutNode):
        return True
    if not isinstance(node, WidgetNode):
        return False
    if node.class_name in PAGE_CONTAINERS or node.layout is not None:
        return True
    return is_container(doc, node.id)


def _outline_host(row: OutlineRow, node: Optional[NodeId] = None, kind: HostKind = "vbox", noun: str = "") -> DropHost:
    return DropHost(
        node or row.node,
        kind,
        "",
        Rect(row.left, row.top, max(row.width, 1), max(row.height, 1)),
        noun=noun,
    )


def _outline_line(row: OutlineRow, at_end: bool) -> DropIndicator:
    y = row.top + max(row.height, 1) - 2 if at_end else row.top
    return DropIndicator(Rect(row.left, max(y, 0), max(row.width, 1), 2))


def _outline_body(row: OutlineRow) -> DropIndicator:
    return DropIndicator(Rect(row.left, row.top, max(row.width, 1), max(row.height, 1)), dashed=True)


def _outline_into(doc: UiDocument, row: OutlineRow, payload: DropPayload) -> DropTarget:
    node = doc.node(row.node)
    if isinstance(node, LayoutNode):
        return _outline_layout_end(doc, node, row, payload)
    if isinstance(node, WidgetNode) and node.class_name in PAGE_CONTAINERS and node.class_name != "QSplitter":
        return _outline_open_page(doc, node, row, payload)
    if isinstance(node, WidgetNode) and node.layout is not None:
        return _outline_layout_end(doc, node.layout, row, payload)
    if isinstance(node, WidgetNode) and is_container(doc, node.id) and not node.child_widgets:
        host = _outline_host(row, node.id, "bare_empty")
        label = node.object_name or "the container"
        sentence = "Into %s · makes a vertical layout" % label
        return _accept(host, "auto_layout", sentence, sentence, _outline_body(row))
    if isinstance(node, WidgetNode) and is_container(doc, node.id):
        host = _outline_host(row, node.id, "bare_free")
        return _resolve_free(host, (row.left + 8, row.top + 8), payload)
    return _outline_beside(doc, row, True, payload)


def _outline_open_page(doc: UiDocument, widget: WidgetNode, row: OutlineRow, payload: DropPayload) -> DropTarget:
    pages = widget.child_widgets
    noun = "page" if widget.class_name in ("QToolBox", "QStackedWidget") else "tab"
    if not pages:
        host = _outline_host(row, widget.id, "pages", noun)
        sentence = "New %s" % noun
        return _accept(host, "new_page", sentence, sentence, _outline_body(row))
    index = 0
    entry = widget.prop("currentIndex")
    value = getattr(getattr(entry, "value", None), "value", None)
    if isinstance(value, int) and 0 <= value < len(pages):
        index = value
    page = pages[index]
    if page.layout is not None:
        return _outline_layout_end(doc, page.layout, row, payload)
    nested = OutlineRow(page.id, row.top, row.height, row.width, row.left)
    return _outline_into(doc, nested, payload)


def _outline_beside(doc: UiDocument, row: OutlineRow, before: bool, payload: DropPayload) -> DropTarget:
    parent = doc.parent(row.node)
    if isinstance(parent, LayoutItemNode):
        layout = doc.parent(parent.id)
        if isinstance(layout, LayoutNode):
            return _outline_layout_side(layout, parent, row, before, payload)
    node = doc.get(row.node)
    if isinstance(parent, WidgetNode) and parent.class_name in PAGE_CONTAINERS and isinstance(node, WidgetNode):
        index = 0
        for found, child in enumerate(parent.child_widgets):
            if child.id == row.node:
                index = found
        at = index if before else index + 1
        kind: HostKind = "splitter" if parent.class_name == "QSplitter" else "pages"
        host = _outline_host(row, parent.id, kind)
        name = _shown(_visible(node)) or "the item"
        sentence = "Insert before %s" % name if before else "Insert after %s" % name
        return _accept(host, "splitter", sentence, sentence, _outline_line(row, not before), index=at)
    return NoDrop()


def _uniform_grid(layout: LayoutNode) -> bool:
    return all((item.rowspan or 1) == 1 and (item.colspan or 1) == 1 for item in layout.items)


def _reading_index(layout: LayoutNode, item: LayoutItemNode) -> int:
    ordered = sorted(layout.items, key=lambda entry: (entry.row or 0, entry.column or 0, entry.slot_index))
    for index, entry in enumerate(ordered):
        if entry.id == item.id:
            return index
    return 0


def _outline_layout_side(
    layout: LayoutNode,
    item: LayoutItemNode,
    row: OutlineRow,
    before: bool,
    payload: DropPayload,
) -> AcceptedDrop:
    host = _outline_host(row, layout.id, _LAYOUT_CLASS.get(layout.class_name, "vbox"))
    name = _shown(_visible(item.content)) or "the item"
    sentence = "Insert before %s" % name if before else "Insert after %s" % name
    line = _outline_line(row, not before)
    if layout.class_name == "QFormLayout":
        at = (0 if item.row is None else item.row) + (0 if before else 1)
        role: FormRole = "label" if payload.kind == "label" else "field"
        return _accept(host, "form_row", sentence, sentence, line, row=at, role=role)
    if layout.class_name == "QGridLayout":
        if _uniform_grid(layout):
            at = _reading_index(layout, item)
            if not before:
                at += 1
            return _accept(host, "grid_reading", sentence, sentence, line, index=at)
        at = (0 if item.row is None else item.row) + (0 if before else (1 if item.rowspan is None else item.rowspan))
        column = 0 if item.column is None else item.column
        return _accept(
            host,
            "grid_row",
            sentence,
            sentence,
            line,
            row=at,
            column=column,
            rowspan=payload.rowspan,
            colspan=payload.colspan,
        )
    at = item.slot_index if before else item.slot_index + 1
    return _accept(host, "box", sentence, sentence, line, index=at)


def _outline_layout_end(
    doc: UiDocument, layout: LayoutNode, row: OutlineRow, payload: DropPayload
) -> DropTarget:
    host = _outline_host(row, layout.id, _LAYOUT_CLASS.get(layout.class_name, "vbox"))
    name = layout.object_name or "the layout"
    sentence = "Insert into %s" % name
    body = _outline_body(row)
    if layout.class_name in ("QFormLayout", "QGridLayout"):
        return _outline_auto_cell(doc, layout, row, payload)
    return _accept(host, "box", sentence, sentence, body, index=len(layout.items))


def _outline_auto_cell(
    doc: UiDocument, layout: LayoutNode, row: OutlineRow, payload: DropPayload
) -> DropTarget:
    # drop_plan imports resolve_outline from this module at load time.
    from app.features.form_builder.engine.commands.drop_plan import auto_target

    chosen = auto_target(doc, layout.id, payload)
    if isinstance(chosen, AcceptedDrop):
        return replace(chosen, indicator=_outline_body(row))
    if chosen is None:
        return NoDrop()
    return chosen


def _outline_outdent(
    doc: UiDocument,
    rows: Sequence[OutlineRow],
    row: OutlineRow,
    x: int,
    indent: int,
    payload: DropPayload,
) -> Optional[DropTarget]:
    by_id = {item.node: item for item in rows}
    candidate = row
    found: Optional[DropTarget] = None
    while candidate.left - x >= indent:
        parent = _outline_ancestor_row(doc, by_id, candidate)
        if parent is None:
            break
        candidate = parent
        landed = _outline_beside(doc, candidate, False, payload)
        if not isinstance(landed, NoDrop):
            found = landed
    return found


def _outline_ancestor_row(
    doc: UiDocument, by_id: Dict[NodeId, OutlineRow], row: OutlineRow
) -> Optional[OutlineRow]:
    current = doc.parent(row.node)
    while current is not None:
        found = by_id.get(current.id)
        if found is not None and found.node != row.node:
            return found
        current = doc.parent(current.id)
    return None
