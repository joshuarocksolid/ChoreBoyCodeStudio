"""Connection arrows and the F4 rubber band (UX-ARR-002 .. 007).

``connections`` is the idle picture: the selected sender while Behavior is
current, or every step while Show all is on. ``connection_link`` is only the
drag line. ``OverlayModes.close`` hides ``connection_link`` and leaves the
idle picture alone. Both layers call ``curve``. ``logic_badges`` does not.

``build`` reads ``read_events`` and ``step_targets``. It does not parse a
``.ui`` file and it does not draw. ``paint`` reads ``ov.connect``,
``ov.connect_faint`` and ``ov.code`` off the palette.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Hashable, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.logic.compat import signature_text, split_signature
from app.features.form_builder.engine.logic.events import read_events, step_targets
from app.features.form_builder.engine.logic.events_codec import EventStep
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutNode
from app.features.form_builder.qtside.canvas.core.chips import (
    LABEL_CORNERS,
    ChipRequest,
    place_chips,
)
from app.features.form_builder.qtside.canvas.core.overlay import LayerItem, LayerOutput
from app.features.form_builder.qtside.canvas.core.space import CanvasPoint, CanvasRect, CanvasSize
from app.features.form_builder.qtside.canvas.layers import CanvasLayer
from app.features.form_builder.qtside.theme.overlay import CanvasPalette
from app.qt.QtCore import QPointF, QRectF, Qt
from app.qt.QtGui import QColor, QFont, QPainter, QPainterPath, QPen

ARROWS = "connections"
LINK = "connection_link"
FORM_SLOTS = frozenset({"close", "accept", "reject"})
_HEAD = 6
_OUTSIDE = 2
_OFFSET = 12
_HIT = 6
Point = Tuple[int, int]


@dataclass(frozen=True)
class DrawnStep:
    """One plain step the canvas may draw. ``signal`` is a Designer signature."""

    sender: str
    signal: str
    index: int
    verb: str
    receiver: str
    slot: str
    method: str
    kind: str


@dataclass(frozen=True)
class ArrowState:
    """Idle arrow layer. ``scope`` is ``selected`` or ``all``.

    ``hover`` and ``aimed`` are ``(sender, signal, index)``. An aimed arrow
    keeps the heavier stroke and its label until the aim moves.
    """

    scope: str
    hover: Optional[Tuple[str, str, int]] = None
    aimed: Optional[Tuple[str, str, int]] = None

    def __post_init__(self) -> None:
        if self.scope not in ("selected", "all"):
            raise ValueError("arrow scope is 'selected' or 'all'")


@dataclass(frozen=True)
class LinkMark:
    """Rubber band. Copied from the host's link view so this module stays out of ``integration``."""

    source: object = None
    candidate: object = None
    pointer: Optional[Point] = None
    dragging: bool = False


@dataclass(frozen=True)
class Mark:
    """What a press hit. ``kind`` is ``arrow``, ``code``, ``form`` or ``label``."""

    kind: str
    sender: str
    signal: str = ""
    index: int = -1


def register(registry: object) -> None:
    add = getattr(registry, "add")
    add(CanvasLayer(ARROWS, build_arrows, paint, order=72))
    add(CanvasLayer(LINK, build_link, paint, order=78))


def drawable_steps(doc: UiDocument) -> Tuple[DrawnStep, ...]:
    """Enabled slot and call steps from both storage forms. A turned-off step is absent."""
    root = doc.root.object_name
    rows: List[DrawnStep] = []
    for state in read_events(doc):
        native = tuple(ref.signal for ref in state.native)
        for index, step in enumerate(state.steps):
            if not step.plain:
                continue
            signal = _signal_of(state.signal_name, state.list_signal, native, index)
            receiver = step_targets(doc, step) or ""
            rows.append(
                DrawnStep(
                    state.sender,
                    signal,
                    index,
                    step.verb,
                    receiver,
                    step.slot,
                    step.method,
                    _kind(step, receiver, root),
                )
            )
    return tuple(rows)


def curve(
    origin: CanvasRect,
    dest: CanvasRect,
    blocked: Sequence[Point] = (),
) -> Tuple[Point, Point, Point, Point, Tuple[Point, Point, Point]]:
    """One cubic from facing-edge midpoints. The tip sits 2 px outside ``dest``.

    Controls sit one third and two thirds along the chord, offset 12 px. A
    sample that lands within 8 px of ``blocked`` flips the offset and adds
    another 12 px, up to three tries. A sender whose rect is the receiver's
    leaves the top edge and enters the right edge.
    """
    if _same_rect(origin, dest):
        start = (origin.x + origin.width // 2, origin.y)
        end = (dest.x + dest.width + _OUTSIDE, dest.y + dest.height // 2)
        return _with_head(start, end, 24, 1, blocked)
    start, end = _faces(origin, dest)
    return _with_head(start, end, _OFFSET, 1, blocked)


def build_arrows(static: object, inputs: object, state: Hashable) -> LayerOutput:
    if not isinstance(state, ArrowState):
        return LayerOutput()
    document = getattr(inputs, "document")
    steps = drawable_steps(document)
    if not steps:
        return LayerOutput()
    placed = _placed(static)
    selected = _selected_name(document, inputs)
    visible = _visible(steps, state.scope, selected)
    if not visible:
        return LayerOutput()
    measure = getattr(inputs, "measure", None)
    seats, leaders = _chip_seats(static, inputs, visible, placed, measure, state.hover, state.aimed)
    items: List[LayerItem] = []
    # Chips go after every arrow and leader so no line is painted across a chip (UX-ARR-003).
    chips: List[LayerItem] = []
    blocked = _centers(document, visible, placed)
    for step in visible:
        key = (step.sender, step.signal, step.index)
        chip = seats.get(key)
        target = placed.get(_id_of(document, step.receiver))
        if step.kind == "widget":
            if target is None:
                continue
            origin = placed.get(_id_of(document, step.sender))
            if origin is None:
                continue
            start, c1, c2, end, head = curve(origin, target, blocked)
            weight, dashed = _ink(state.scope, step, selected, state.aimed)
            items.append(_arrow_item(start, c1, c2, end, head, weight, dashed, step))
        elif chip is not None:
            origin = placed.get(_id_of(document, step.sender))
            if origin is None:
                continue
            start, c1, c2, end, head = curve(origin, chip, blocked)
            items.append(_arrow_item(start, c1, c2, end, head, "code" if step.kind == "code" else "strong", False, step))
        if chip is not None and key in seats:
            chips.append(_chip_item(chip, step, state.hover, state.aimed))
        leader = leaders.get(key)
        if leader is not None:
            bounds = _bounds(leader)
            items.append(LayerItem(rect=bounds, role="select", layer=ARROWS, data=("leader", leader[0], leader[1])))
    return LayerOutput(tuple(items) + tuple(chips))


def build_link(static: object, inputs: object, state: Hashable) -> LayerOutput:
    if not isinstance(state, LinkMark) or state.source is None:
        return LayerOutput()
    document = getattr(inputs, "document")
    placed = _placed(static)
    origin = placed.get(state.source)
    items: List[LayerItem] = []
    if state.candidate is not None and state.candidate == document.root.id:
        page = _page_rect(static)
        if page is not None:
            items.append(LayerItem(rect=page, role="select", layer=LINK, data=("page",)))
    elif state.candidate is not None:
        rect = placed.get(state.candidate)
        if rect is not None:
            items.append(LayerItem(rect=rect.grown(2), role="select", layer=LINK, data=("frame",)))
    if origin is not None and state.pointer is not None and state.dragging:
        dest = CanvasRect(state.pointer[0], state.pointer[1], 1, 1)
        start, c1, c2, end, head = curve(origin, dest)
        bounds = _bounds((start, c1, c2, end) + head)
        items.append(
            LayerItem(rect=bounds, role="select", layer=LINK, data=("rubber", start, c1, c2, end, head))
        )
    return LayerOutput(tuple(items))


def paint(painter: QPainter, item: LayerItem, palette: CanvasPalette) -> None:
    data = item.data
    if not isinstance(data, tuple) or not data:
        return
    kind = data[0]
    overlay = palette.overlay
    if kind == "arrow":
        _paint_curve(painter, data[1], bool(data[2]), data[3:7], data[7], overlay)
    elif kind == "rubber":
        _paint_curve(painter, "strong", False, data[1:5], data[5], overlay)
    elif kind == "chip":
        _paint_chip(painter, item.rect, str(data[1]), str(data[2]), overlay)
    elif kind == "leader":
        _paint_leader(painter, data[1], data[2], overlay)
    elif kind == "frame":
        _stroke_rect(painter, item.rect, _qcolor(overlay.select), max(2.0, overlay.min_stroke))
    elif kind == "page":
        color = _qcolor(overlay.drop_fill)
        painter.save()
        try:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRect(QRectF(item.rect.x, item.rect.y, item.rect.width, item.rect.height))
        finally:
            painter.restore()


def mark_at(items: Sequence[object], x: float, y: float) -> Optional[Mark]:
    """The chip under ``(x, y)``, or the arrow nearest that point inside the hit band."""
    point = CanvasPoint(int(x), int(y))
    nearest: Optional[Mark] = None
    nearest_distance: Optional[float] = None
    for item in reversed(tuple(items)):
        if not isinstance(item, LayerItem):
            continue
        data = item.data
        if not isinstance(data, tuple) or not data:
            continue
        if data[0] == "chip" and item.rect.contains(point) and data[2]:
            return Mark(str(data[1]), str(data[3]), str(data[4]), int(data[5]))
        if data[0] != "arrow":
            continue
        distance = _distance(data[3], data[4], data[5], data[6], data[7], x, y)
        if distance > _HIT:
            continue
        if nearest_distance is None or distance < nearest_distance:
            nearest = Mark("arrow", str(data[8]), str(data[9]), int(data[10]))
            nearest_distance = distance
    return nearest


def _signal_of(bare: str, listed: Optional[str], native: Tuple[str, ...], index: int) -> str:
    if index < len(native):
        return native[index]
    if listed:
        return listed
    return signature_text(bare, ())


def _kind(step: EventStep, receiver: str, root: str) -> str:
    if step.verb == "call":
        return "form" if step.method in FORM_SLOTS else "code"
    name = split_signature(step.slot)[0]
    if receiver == root and name in FORM_SLOTS:
        return "form"
    return "widget"


def _visible(steps: Sequence[DrawnStep], scope: str, selected: str) -> Tuple[DrawnStep, ...]:
    if scope == "all":
        return tuple(steps)
    if not selected:
        return ()
    return tuple(step for step in steps if step.sender == selected or step.receiver == selected)


def _ink(
    scope: str,
    step: DrawnStep,
    selected: str,
    aimed: Optional[Tuple[str, str, int]] = None,
) -> Tuple[str, bool]:
    if aimed == (step.sender, step.signal, step.index):
        return ("aimed", False)
    if scope == "all":
        return ("strong" if step.sender == selected else "faint", False)
    incoming = bool(selected) and step.receiver == selected and step.sender != selected
    return ("strong", incoming)


def _arrow_item(
    start: Point,
    c1: Point,
    c2: Point,
    end: Point,
    head: Tuple[Point, Point, Point],
    weight: str,
    dashed: bool,
    step: DrawnStep,
) -> LayerItem:
    bounds = _bounds((start, c1, c2, end) + head)
    return LayerItem(
        rect=bounds,
        role="select",
        layer=ARROWS,
        data=("arrow", weight, dashed, start, c1, c2, end, head, step.sender, step.signal, step.index),
    )


def _chip_item(
    rect: CanvasRect,
    step: DrawnStep,
    hover: Optional[Tuple[str, str, int]],
    aimed: Optional[Tuple[str, str, int]] = None,
) -> LayerItem:
    key = (step.sender, step.signal, step.index)
    show_label = step.kind == "widget" and (hover == key or aimed == key)
    if step.kind == "widget" and not show_label:
        return LayerItem(rect=rect, role="select", layer=ARROWS, data=("chip", "label", "", step.sender, step.signal, step.index))
    text = _chip_text(step)
    kind = "label" if step.kind == "widget" else step.kind
    return LayerItem(
        rect=rect,
        role="select",
        layer=ARROWS,
        data=("chip", kind, text, step.sender, step.signal, step.index),
    )


def _chip_text(step: DrawnStep) -> str:
    bare = split_signature(step.signal)[0]
    if step.kind == "code":
        return "{ } %s()" % step.method
    if step.kind == "form":
        name = step.method or split_signature(step.slot)[0]
        return "%s · %s()" % (step.receiver, name)
    slot = step.slot or ("%s()" % step.method)
    return "%s → %s" % (bare, slot)


def _chip_seats(
    static: object,
    inputs: object,
    steps: Sequence[DrawnStep],
    placed: dict,
    measure: object,
    hover: Optional[Tuple[str, str, int]],
    aimed: Optional[Tuple[str, str, int]] = None,
) -> Tuple[dict, dict]:
    document = getattr(inputs, "document")
    page = _page_rect(static)
    viewport = getattr(inputs, "viewport", None) or page
    if page is None or viewport is None:
        return {}, {}
    width_of = measure if callable(measure) else (lambda text: max(12, len(text) * 7))
    content = tuple(getattr(static, "content", ()))
    from app.features.form_builder.qtside.canvas.layers.logic_badges import _selection_chip

    fixed = tuple(getattr(inputs, "chrome", ())) + _selection_chip(static, inputs, page, viewport)
    blocked = _centers(document, steps, placed)
    label_content = _label_obstacles(document, content)
    requests = []
    curves = {}
    parked_steps = []
    for step in steps:
        key = (step.sender, step.signal, step.index)
        lit = hover == key or aimed == key
        if step.kind == "widget" and not lit:
            continue
        origin = placed.get(_id_of(document, step.sender))
        if origin is None:
            continue
        size = CanvasSize(int(width_of(_chip_text(step))) + 12, 18)
        if step.kind == "widget":
            target = placed.get(_id_of(document, step.receiver))
            if target is None:
                continue
            start, c1, c2, end, _head = curve(origin, target, blocked)
            curves[key] = (start, c1, c2, end, size)
            spot = _bezier(start, c1, c2, end, 0.5)
            requests.append(ChipRequest(key, CanvasRect(int(spot[0]), int(spot[1]), 1, 1), size, LABEL_CORNERS, frozenset()))
        else:
            parked_steps.append((step, ChipRequest(key, origin, size, LABEL_CORNERS, frozenset())))
    found: dict = {}
    leaders: dict = {}
    if requests:
        seats = place_chips(requests, label_content, fixed, page, viewport)
        found = {seat.key: seat.rect for seat in seats}
        for request in requests:
            if request.key in found or request.key not in curves:
                continue
            start, c1, c2, end, _size = curves[request.key]
            for sample in (0.35, 0.65, 0.25, 0.75, 0.15, 0.85):
                spot = _bezier(start, c1, c2, end, sample)
                slide = ChipRequest(
                    request.key, CanvasRect(int(spot[0]), int(spot[1]), 1, 1), request.size, LABEL_CORNERS, frozenset()
                )
                seated = place_chips((slide,), label_content, fixed + tuple(found.values()), page, viewport)
                if seated:
                    found[request.key] = seated[0].rect
                    break
        for request in requests:
            if request.key in found or request.key not in curves:
                continue
            start, c1, c2, end, size = curves[request.key]
            spot = _bezier(start, c1, c2, end, 0.5)
            found[request.key] = CanvasRect(
                int(spot[0] - size.width / 2), int(spot[1] - size.height / 2), size.width, size.height
            )
    blockers = _solid_rects(document, static) + tuple(found.values())
    parked_steps.sort(key=lambda pair: 0 if pair[0].kind == "code" else 1)
    for _step, request in parked_steps:
        parked = _on_sender_row(request, page, blockers, viewport)
        if parked is None:
            continue
        rect, leader = parked
        found[request.key] = rect
        blockers = blockers + (rect,)
        if leader is not None:
            leaders[request.key] = leader
    return found, leaders


def _label_obstacles(document: UiDocument, content: Sequence[object]) -> Tuple[object, ...]:
    """Leaf widgets and title bands. Empty layout cells and the page itself stay open."""
    root = document.root.id
    kept = []
    for obstacle in content:
        node_id = getattr(obstacle, "node", None)
        if getattr(obstacle, "band", False):
            kept.append(obstacle)
            continue
        if node_id == root:
            continue
        node = document.get(node_id) if node_id is not None else None
        if isinstance(node, LayoutNode):
            continue
        kept.append(obstacle)
    return tuple(kept)


def _solid_rects(document: UiDocument, static: object) -> Tuple[CanvasRect, ...]:
    """Placed widgets and content, without the page and without empty layout cells."""
    root = document.root.id
    rects: List[CanvasRect] = []
    seen = set()
    for item in getattr(static, "placed", ()):
        node_id = getattr(item, "node", None)
        if node_id == root or node_id in seen:
            continue
        node = document.get(node_id) if node_id is not None else None
        if isinstance(node, LayoutNode):
            continue
        rect = getattr(item, "rect", None)
        if isinstance(rect, CanvasRect):
            rects.append(rect)
            seen.add(node_id)
    for obstacle in getattr(static, "content", ()):
        node_id = getattr(obstacle, "node", None)
        if node_id == root or node_id in seen:
            continue
        if not getattr(obstacle, "band", False):
            node = document.get(node_id) if node_id is not None else None
            if isinstance(node, LayoutNode):
                continue
        rect = getattr(obstacle, "rect", None)
        if isinstance(rect, CanvasRect):
            rects.append(rect)
    return tuple(rects)


def _on_sender_row(
    request: ChipRequest, page: CanvasRect, taken: Sequence[CanvasRect], viewport: Optional[CanvasRect] = None
) -> Optional[Tuple[CanvasRect, Optional[Tuple[Point, Point]]]]:
    """The nearer gutter on the sender's row, then empty space above or below.

    A spot that covers a widget or another chip is never returned. The last
    seat is the nearest free gutter, with a short leader back to the sender.
    """
    origin = request.target
    size = request.size
    y = int(origin.y + (origin.height - size.height) / 2)
    nearer_left = origin.x + origin.width / 2 < page.x + page.width / 2
    gutter_x = int(page.x + 4 if nearer_left else page.x + page.width - size.width - 4)
    other_x = int(page.x + page.width - size.width - 4 if nearer_left else page.x + 4)
    badge_row = (
        CanvasRect(origin.x, origin.y - 14, 12, 12),
        CanvasRect(origin.x + max(0, origin.width - 12), origin.y - 14, 12, 12),
    )
    taken = tuple(taken) + badge_row
    spots = [CanvasRect(gutter_x, y, size.width, size.height)]
    # Beside the sender, inside the visible canvas. A spot past the viewport is not a seat.
    limit = viewport or page
    beside = int(origin.x + origin.width + 8)
    if beside + size.width > limit.x + limit.width:
        beside = int(origin.x - size.width - 8)
    beside = max(limit.x, min(beside, limit.x + limit.width - size.width))
    spots.insert(0, CanvasRect(beside, y, size.width, size.height))
    if _in_view(spots[0], limit) and not any(spots[0].intersects(other) for other in taken):
        return spots[0], None
    if _clear_spot(spots[1], page, taken) and _in_view(spots[1], limit):
        return spots[1], None
    for stack in range(0, 4):
        for spot in (
            CanvasRect(beside, y + stack * (size.height + 4), size.width, size.height),
            CanvasRect(beside, y - stack * (size.height + 4), size.width, size.height),
        ):
            if _in_view(spot, limit) and not any(spot.intersects(other) for other in taken):
                return spot, None
    # Past the badge on the sender's corner, in the empty space above or below it.
    inset = origin.x + 16
    spots.append(CanvasRect(inset, origin.y - size.height - 8, size.width, size.height))
    spots.append(CanvasRect(inset, origin.y + origin.height + 8, size.width, size.height))
    for stack in range(1, 6):
        spots.append(CanvasRect(gutter_x, y + stack * (size.height + 4), size.width, size.height))
        spots.append(CanvasRect(gutter_x, y - stack * (size.height + 4), size.width, size.height))
    spots.append(CanvasRect(other_x, y, size.width, size.height))
    for spot in spots:
        if _in_view(spot, limit) and _clear_spot(spot, page, taken):
            return spot, None
    best: Optional[CanvasRect] = None
    best_distance: Optional[int] = None
    for gx in (gutter_x, other_x):
        for step in range(-16, 17):
            spot = CanvasRect(gx, y + step * 8, size.width, size.height)
            if not _in_view(spot, limit) or not _clear_spot(spot, page, taken):
                continue
            distance = abs(spot.y - y)
            if best_distance is None or distance < best_distance:
                best = spot
                best_distance = distance
    if best is None:
        return None
    return best, _leader_line(best, origin)


def _in_view(spot: CanvasRect, view: CanvasRect) -> bool:
    return (
        spot.x >= view.x
        and spot.y >= view.y
        and spot.x + spot.width <= view.x + view.width
        and spot.y + spot.height <= view.y + view.height
    )


def _clear_spot(spot: CanvasRect, page: CanvasRect, taken: Sequence[CanvasRect]) -> bool:
    if spot.x < page.x or spot.y < page.y:
        return False
    if spot.x + spot.width > page.x + page.width or spot.y + spot.height > page.y + page.height:
        return False
    return not any(spot.intersects(other) for other in taken)


def _leader_line(chip: CanvasRect, origin: CanvasRect) -> Tuple[Point, Point]:
    chip_mid = (chip.x + chip.width // 2, chip.y + chip.height // 2)
    sender_mid = (origin.x + origin.width // 2, origin.y + origin.height // 2)
    if chip.x + chip.width <= origin.x:
        start = (chip.x + chip.width, chip_mid[1])
        end = (origin.x, sender_mid[1])
    elif chip.x >= origin.x + origin.width:
        start = (chip.x, chip_mid[1])
        end = (origin.x + origin.width, sender_mid[1])
    elif chip.y + chip.height <= origin.y:
        start = (chip_mid[0], chip.y + chip.height)
        end = (sender_mid[0], origin.y)
    else:
        start = (chip_mid[0], chip.y)
        end = (sender_mid[0], origin.y + origin.height)
    return start, end


def _bezier(start: Point, c1: Point, c2: Point, end: Point, t: float) -> Point:
    stay = 1.0 - t
    return (
        stay ** 3 * start[0] + 3 * stay ** 2 * t * c1[0] + 3 * stay * t ** 2 * c2[0] + t ** 3 * end[0],
        stay ** 3 * start[1] + 3 * stay ** 2 * t * c1[1] + 3 * stay * t ** 2 * c2[1] + t ** 3 * end[1],
    )


def _faces(origin: CanvasRect, dest: CanvasRect) -> Tuple[Point, Point]:
    sx, sy = origin.x + origin.width / 2.0, origin.y + origin.height / 2.0
    dx, dy = dest.x + dest.width / 2.0, dest.y + dest.height / 2.0
    if abs(dx - sx) >= abs(dy - sy):
        if dx >= sx:
            start = (origin.x + origin.width, origin.y + origin.height // 2)
            end = (dest.x - _OUTSIDE, dest.y + dest.height // 2)
        else:
            start = (origin.x, origin.y + origin.height // 2)
            end = (dest.x + dest.width + _OUTSIDE, dest.y + dest.height // 2)
    elif dy >= sy:
        start = (origin.x + origin.width // 2, origin.y + origin.height)
        end = (dest.x + dest.width // 2, dest.y - _OUTSIDE)
    else:
        start = (origin.x + origin.width // 2, origin.y)
        end = (dest.x + dest.width // 2, dest.y + dest.height + _OUTSIDE)
    return start, end


def _with_head(
    start: Point,
    end: Point,
    offset: int,
    sign: int,
    blocked: Sequence[Point],
) -> Tuple[Point, Point, Point, Point, Tuple[Point, Point, Point]]:
    chosen = _controls(start, end, offset * sign)
    for _try in range(3):
        if not _hits_blocked(start, chosen[0], chosen[1], end, blocked):
            break
        sign = -sign
        offset += _OFFSET
        chosen = _controls(start, end, offset * sign)
    c1, c2 = chosen
    head = _head(c2, end)
    return start, c1, c2, end, head


def _controls(start: Point, end: Point, offset: int) -> Tuple[Point, Point]:
    vx, vy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(vx, vy) or 1.0
    px, py = -vy / length * offset, vx / length * offset
    c1 = (int(round(start[0] + vx / 3.0 + px)), int(round(start[1] + vy / 3.0 + py)))
    c2 = (int(round(start[0] + 2.0 * vx / 3.0 + px)), int(round(start[1] + 2.0 * vy / 3.0 + py)))
    return c1, c2


def _hits_blocked(start: Point, c1: Point, c2: Point, end: Point, blocked: Sequence[Point]) -> bool:
    if not blocked:
        return False
    for sample in _samples(start, c1, c2, end):
        for point in blocked:
            if math.hypot(sample[0] - point[0], sample[1] - point[1]) < 8 and sample != start and sample != end:
                return True
    return False


def _head(c2: Point, end: Point) -> Tuple[Point, Point, Point]:
    vx, vy = end[0] - c2[0], end[1] - c2[1]
    length = math.hypot(vx, vy) or 1.0
    ux, uy = vx / length, vy / length
    px, py = -uy, ux
    back = (int(round(end[0] - ux * _HEAD)), int(round(end[1] - uy * _HEAD)))
    left = (int(round(back[0] + px * _HEAD / 2.0)), int(round(back[1] + py * _HEAD / 2.0)))
    right = (int(round(back[0] - px * _HEAD / 2.0)), int(round(back[1] - py * _HEAD / 2.0)))
    return (end, left, right)


def _samples(start: Point, c1: Point, c2: Point, end: Point) -> Tuple[Point, ...]:
    points = []
    for index in range(9):
        t = index / 8.0
        u = 1.0 - t
        x = u ** 3 * start[0] + 3 * u ** 2 * t * c1[0] + 3 * u * t ** 2 * c2[0] + t ** 3 * end[0]
        y = u ** 3 * start[1] + 3 * u ** 2 * t * c1[1] + 3 * u * t ** 2 * c2[1] + t ** 3 * end[1]
        points.append((int(round(x)), int(round(y))))
    return tuple(points)


def _near(start: Point, c1: Point, c2: Point, end: Point, head: Tuple[Point, ...], x: float, y: float) -> bool:
    return _distance(start, c1, c2, end, head, x, y) <= _HIT


def _distance(start: Point, c1: Point, c2: Point, end: Point, head: Tuple[Point, ...], x: float, y: float) -> float:
    best = None
    for point in _samples(start, c1, c2, end) + tuple(head):
        distance = math.hypot(point[0] - x, point[1] - y)
        if best is None or distance < best:
            best = distance
    return best if best is not None else _HIT + 1


def _bounds(points: Sequence[Point]) -> CanvasRect:
    left = min(point[0] for point in points) - _HEAD
    top = min(point[1] for point in points) - _HEAD
    right = max(point[0] for point in points) + _HEAD
    bottom = max(point[1] for point in points) + _HEAD
    return CanvasRect(left, top, right - left, bottom - top)


def _same_rect(origin: CanvasRect, dest: CanvasRect) -> bool:
    return origin.x == dest.x and origin.y == dest.y and origin.width == dest.width and origin.height == dest.height


def _placed(static: object) -> dict:
    found = {}
    for item in getattr(static, "placed", ()):
        found[item.node] = item.rect
    return found


def _id_of(document: UiDocument, name: str) -> object:
    found = document.by_name(name)
    return found[0] if found else None


def _selected_name(document: UiDocument, inputs: object) -> str:
    selection = getattr(inputs, "selection", None)
    current = getattr(selection, "current", None)
    node = document.get(current) if current is not None else None
    name = getattr(node, "object_name", "")
    return name if isinstance(name, str) else ""


def _centers(document: UiDocument, steps: Sequence[DrawnStep], placed: dict) -> Tuple[Point, ...]:
    points: List[Point] = []
    for step in steps:
        name = step.receiver if step.kind == "widget" else step.sender
        rect = placed.get(_id_of(document, name))
        if rect is not None:
            points.append((rect.x + rect.width // 2, rect.y + rect.height // 2))
    return tuple(points)


def _page_rect(static: object) -> Optional[CanvasRect]:
    view = getattr(static, "view", None)
    origin = getattr(view, "page_origin", None)
    page = getattr(view, "page", None)
    if origin is None or page is None:
        return None
    return CanvasRect(origin.x, origin.y, page.width, page.height)


def _paint_curve(painter: QPainter, weight: str, dashed: bool, points: Sequence[Point], head: Tuple[Point, ...], overlay: object) -> None:
    if weight == "code":
        color = _qcolor(getattr(overlay, "code"))
        width = 1.5
    elif weight == "faint":
        color = _qcolor(getattr(overlay, "connect_faint"))
        width = 1.5 if getattr(overlay, "min_stroke") >= 2 else 1.0
    elif weight == "aimed":
        color = _qcolor(getattr(overlay, "connect"))
        width = 3.0 if getattr(overlay, "min_stroke") >= 2 else 2.5
    else:
        color = _qcolor(getattr(overlay, "connect"))
        width = 2.0 if getattr(overlay, "min_stroke") >= 2 else 1.5
    path = QPainterPath()
    path.moveTo(QPointF(points[0][0], points[0][1]))
    path.cubicTo(
        QPointF(points[1][0], points[1][1]),
        QPointF(points[2][0], points[2][1]),
        QPointF(points[3][0], points[3][1]),
    )
    pen = QPen(color, width)
    if dashed:
        pen.setStyle(Qt.PenStyle.DashLine)
    painter.save()
    try:
        if float(getattr(overlay, "min_stroke", 1) or 1) >= 2:
            halo = QPen(_qcolor(getattr(overlay, "chip_text")), width + 2)
            if dashed:
                halo.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(halo)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawPolygon([QPointF(point[0], point[1]) for point in head])
    finally:
        painter.restore()


def _paint_leader(painter: QPainter, start: Point, end: Point, overlay: object) -> None:
    color = _qcolor(getattr(overlay, "connect"))
    width = 1.5 if getattr(overlay, "min_stroke") >= 2 else 1.0
    painter.save()
    try:
        painter.setPen(QPen(color, width))
        painter.drawLine(QPointF(start[0], start[1]), QPointF(end[0], end[1]))
    finally:
        painter.restore()


def _paint_chip(painter: QPainter, rect: CanvasRect, kind: str, text: str, overlay: object) -> None:
    if kind == "label" and not text:
        return
    fill = _qcolor(getattr(overlay, "code" if kind == "code" else "connect"))
    ink = _qcolor(getattr(overlay, "chip_text"))
    box = QRectF(rect.x, rect.y, rect.width, rect.height)
    painter.save()
    try:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawRoundedRect(box, 3, 3)
        painter.setPen(ink)
        font = QFont(painter.font())
        font.setPixelSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(box, int(Qt.AlignmentFlag.AlignCenter), text)
    finally:
        painter.restore()


def _stroke_rect(painter: QPainter, rect: CanvasRect, color: QColor, width: float) -> None:
    painter.save()
    try:
        painter.setPen(QPen(color, width))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(rect.x, rect.y, rect.width, rect.height))
    finally:
        painter.restore()


def _qcolor(text: str) -> QColor:
    raw = text.lstrip("#")
    red, green, blue = int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
    alpha = int(raw[6:8], 16) if len(raw) >= 8 else 255
    return QColor(red, green, blue, alpha)
