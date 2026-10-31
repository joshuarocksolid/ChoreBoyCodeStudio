"""Logic badges (UX-ARR-001). One 12 px mark per sender that has an event.

The workbench shows this layer in Design. ``build`` returns nothing below
50% zoom. Preview, Save image and Print never ask this layer to paint.
"""

from __future__ import annotations

import weakref
from typing import Dict, Hashable, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.logic.events import events_of_sender, read_events
from app.features.form_builder.engine.logic.events_catalog import event_words
from app.features.form_builder.engine.style.classes import widget_chain
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutNode, WidgetNode
from app.features.form_builder.qtside.canvas.core.chips import BADGE_CORNERS, ChipRequest, CornerSeat, place_chips
from app.features.form_builder.qtside.canvas.core.overlay import LayerItem, LayerOutput
from app.features.form_builder.qtside.canvas.core.space import CanvasPoint, CanvasRect, CanvasSize
from app.features.form_builder.qtside.canvas.layers import CanvasLayer
from app.features.form_builder.qtside.theme.overlay import CanvasPalette
from app.qt.QtCore import QRectF, Qt
from app.qt.QtGui import QColor, QFont, QPainter

NAME = "logic_badges"
BADGE = 12
HIDE_BELOW = 0.5


def register(registry: object) -> None:
    getattr(registry, "add")(CanvasLayer(NAME, build, paint, order=74))


def badge_tip(doc: UiDocument, sender: str) -> str:
    """``{n} events: When clicked, When toggled``, then ``and {k} more``."""
    return _tip(doc, sender, events_of_sender(doc, sender))


def _tip(doc: UiDocument, sender: str, states: Sequence[object]) -> str:
    chain = _chain(doc, sender)
    words = ["When %s" % event_words(state.signal_name, chain).header for state in states]
    shown = words[:3]
    extra = len(words) - len(shown)
    noun = "event" if len(words) == 1 else "events"
    text = "%d %s: %s" % (len(words), noun, ", ".join(shown))
    if extra:
        text += " and %d more" % extra
    return text


class _Basis:
    """What the badges' seating reads from the static layer, and nothing an event changes.

    A step commit rebuilds the frame. The static layer it paints from keeps its
    ``placed`` and ``content`` tuples, so this survives the commit and the
    badges are seated again only when their senders or the geometry move.
    """

    def __init__(self, document: UiDocument, static: object) -> None:
        self.document = weakref.ref(document)
        self.names = document.names()
        self.placed_ref = getattr(static, "placed", ())
        self.content_ref = getattr(static, "content", ())
        self.placed = {item.node: item.rect for item in self.placed_ref}
        self.others_all = _other_widgets(document, static)
        self.other_index, self.other_span = _y_index(self.others_all)
        self.content = _badge_content(document, static)
        self.bands = tuple(obstacle.rect for obstacle in self.content_ref if getattr(obstacle, "band", False))
        occupied = [item.rect for item in self.placed_ref]
        self.occupied_index, _span = _y_index(occupied)
        self.blocker_index, _span = _y_index(list(self.others_all) + list(self.bands))
        self.chip_obstacles = _chip_obstacles(document, static)
        #: selection chip rects, by the chip's size and the view it was seated in
        self.chips: Dict[Hashable, Tuple[CanvasRect, ...]] = {}
        #: seats, by the view and the senders (with their rects) they were seated for
        self.seats: Dict[Hashable, Tuple[Tuple[str, CanvasRect], ...]] = {}

    def serves(self, document: UiDocument, static: object) -> bool:
        return (
            self.document() is document
            and self.names is document.names()
            and self.placed_ref is getattr(static, "placed", None)
            and self.content_ref is getattr(static, "content", None)
        )


_BASIS: Optional[_Basis] = None
_MEMO_KEEP = 8


def _basis_for(document: UiDocument, static: object) -> _Basis:
    global _BASIS
    held = _BASIS
    if held is not None and held.serves(document, static):
        return held
    _BASIS = _Basis(document, static)
    return _BASIS


def forget_badge_memo() -> None:
    """Drop the kept seating. The next build seats every badge again."""
    global _BASIS
    _BASIS = None


def _badge_senders(document: UiDocument) -> Tuple[List[str], dict]:
    """Event senders first, in document order, then any other widget a kind applies to."""
    grouped: dict = {}
    senders: List[str] = []
    for event in read_events(document):
        if event.sender not in grouped:
            grouped[event.sender] = []
            senders.append(event.sender)
        grouped[event.sender].append(event)
    seen = set(senders)
    for node in document.iter_widgets():
        name = node.object_name
        if not name or name in seen:
            continue
        if _mark(document, name, ()) is None:
            continue
        senders.append(name)
        grouped[name] = []
        seen.add(name)
    return senders, grouped


def _mark(document: UiDocument, sender: str, states: Tuple[object, ...]) -> Optional[Tuple[str, str, int]]:
    from app.features.form_builder.qtside.canvas.layers.badge_kinds import BadgeFacts, default_registry

    found = document.by_name(sender)
    node = document.node(found[0]) if found else None
    facts = BadgeFacts(document, sender, states)
    applying = []
    for kind in default_registry().ordered():
        try:
            if kind.applies(node, facts):
                applying.append(kind)
        except Exception:
            continue
    if not applying:
        return None
    parts = []
    for kind in applying:
        try:
            text = kind.sentence(node, facts)
        except Exception:
            text = ""
        if text:
            parts.append(text)
    return (" ".join(parts), applying[0].glyph, len(applying))


def _view_key(page: CanvasRect, viewport: CanvasRect, inputs: object) -> Hashable:
    chrome = tuple(getattr(inputs, "chrome", ()))
    return (page, viewport, chrome, getattr(inputs, "dock", None))


def build(static: object, inputs: object, state: Hashable) -> LayerOutput:
    del state
    view = getattr(static, "view", None)
    factor = float(getattr(view, "factor", 1.0) or 1.0)
    if factor < HIDE_BELOW:
        return LayerOutput()
    document = getattr(inputs, "document")
    senders, grouped = _badge_senders(document)
    if not senders:
        return LayerOutput()
    page = _page(static)
    viewport = getattr(inputs, "viewport", None) or page
    if page is None or viewport is None:
        return LayerOutput()
    basis = _basis_for(document, static)
    bodies = tuple(_bodies(document, senders, basis.placed))
    if not bodies:
        return LayerOutput()
    where = _view_key(page, viewport, inputs)
    chips = _selection_chip(static, inputs, page, viewport)
    # Seats depend on the geometry and on which senders have badges, in order.
    # A commit that only changes what a badge says finds its seats here.
    seat_key = (where, chips, bodies)
    seated = basis.seats.get(seat_key)
    if seated is None:
        seated = _seat_badges(basis, inputs, bodies, page, viewport, chips)
        if len(basis.seats) >= _MEMO_KEEP:
            basis.seats.pop(next(iter(basis.seats)))
        basis.seats[seat_key] = seated
    items: List[LayerItem] = []
    for sender, seat in seated:
        mark = _mark(document, sender, tuple(grouped.get(sender, ())))
        if mark is None:
            continue
        tip, glyph, count = mark
        items.append(LayerItem(rect=seat, role="select", layer=NAME, data=("badge", sender, tip, glyph, count)))
    return LayerOutput(tuple(items))


def _seat_badges(
    basis: _Basis,
    inputs: object,
    bodies: Tuple[Tuple[str, CanvasRect], ...],
    page: CanvasRect,
    viewport: CanvasRect,
    chips: Tuple[CanvasRect, ...],
) -> Tuple[Tuple[str, CanvasRect], ...]:
    requests = []
    widget_rect = {}
    for sender, rect in bodies:
        widget_rect[sender] = rect
        others = [
            other
            for other in _near(basis.other_index, rect.y - basis.other_span, rect.y + rect.height + basis.other_span)
            if other != rect
        ]
        requests.append(
            ChipRequest(sender, rect, CanvasSize(BADGE, BADGE), _corners(rect, others), frozenset(), corners_only=True)
        )
    fixed = tuple(getattr(inputs, "chrome", ())) + chips + basis.bands
    seats = place_chips(requests, basis.content, fixed, page, viewport, getattr(inputs, "dock", None))
    seated = {}
    for seat in seats:
        if isinstance(seat, CornerSeat) and _on_own_edge(seat.rect, widget_rect.get(str(seat.key), seat.rect)):
            seated[str(seat.key)] = seat.rect
    found: List[Tuple[str, CanvasRect]] = []
    for sender, rect in widget_rect.items():
        seat = seated.get(sender)
        neighbours = [
            other
            for other in _near(basis.blocker_index, rect.y - BADGE - 4, rect.y + rect.height + BADGE + 4)
            if other != rect
        ]
        occupied_near = _near(basis.occupied_index, rect.y - BADGE - 4, rect.y + rect.height + BADGE + 4)
        if seat is None or _covers(seat, occupied_near, rect) or _hits(seat, neighbours):
            seat = _badge_fallback(rect, neighbours)
        if seat is None or _covers(seat, occupied_near, rect) or _hits(seat, neighbours):
            continue
        found.append((sender, seat))
    return tuple(found)


def paint(painter: QPainter, item: LayerItem, palette: CanvasPalette) -> None:
    data = item.data
    if not isinstance(data, tuple) or not data or data[0] != "badge":
        return
    fill = _qcolor(palette.overlay.logic_badge)
    ink = _qcolor(palette.overlay.chip_text)
    box = QRectF(item.rect.x, item.rect.y, item.rect.width, item.rect.height)
    painter.save()
    try:
        painter.setPen(Qt.PenStyle.NoPen)
        if float(palette.overlay.min_stroke or 1) >= 2:
            painter.setBrush(ink)
            painter.drawEllipse(box.adjusted(-1, -1, 1, 1))
        painter.setBrush(fill)
        painter.drawEllipse(box)
        painter.setPen(ink)
        font = QFont(painter.font())
        font.setPixelSize(10)
        font.setBold(True)
        painter.setFont(font)
        glyph = "\u203a"
        count = 1
        if len(data) > 3 and data[3]:
            glyph = str(data[3])
        if len(data) > 4:
            try:
                count = int(data[4])
            except (TypeError, ValueError):
                count = 1
        label = glyph if count <= 1 else "%s%d" % (glyph, count)
        painter.drawText(box, int(Qt.AlignmentFlag.AlignCenter), label)
    finally:
        painter.restore()


def mark_at(items: Sequence[object], x: float, y: float) -> Optional[str]:
    """The sender name when ``(x, y)`` is inside a badge."""
    point = CanvasPoint(int(x), int(y))
    for item in reversed(tuple(items)):
        if not isinstance(item, LayerItem):
            continue
        data = item.data
        if isinstance(data, tuple) and data and data[0] == "badge" and item.rect.contains(point):
            return str(data[1])
    return None


def tip_at(items: Sequence[object], x: float, y: float) -> str:
    point = CanvasPoint(int(x), int(y))
    for item in reversed(tuple(items)):
        if not isinstance(item, LayerItem):
            continue
        data = item.data
        if isinstance(data, tuple) and data and data[0] == "badge" and item.rect.contains(point):
            return str(data[2])
    return ""


def _bodies(document: UiDocument, senders: Sequence[str], placed: dict) -> Tuple[Tuple[str, CanvasRect], ...]:
    rows = []
    for sender in senders:
        found = document.by_name(sender)
        rect = placed.get(found[0]) if found else None
        if rect is not None:
            rows.append((sender, rect))
    return tuple(rows)


def _corners(rect: CanvasRect, others: Sequence[CanvasRect]) -> Tuple[str, ...]:
    """The corner away from a neighbour or a child that owns that corner."""
    right = False
    left = False
    mid = rect.y + rect.height / 2.0
    for other in others:
        inside = (
            other.x >= rect.x - 1
            and other.y >= rect.y - 1
            and other.x + other.width <= rect.x + rect.width + 1
            and other.y + other.height <= rect.y + rect.height + 1
        )
        same_row = abs((other.y + other.height / 2.0) - mid) <= max(rect.height, other.height)
        if not inside and not same_row:
            continue
        if other.x + other.width >= rect.x + rect.width - 24:
            right = True
        if other.x <= rect.x + 24:
            left = True
    if right and not left:
        return ("above_left", "below_left", "above_right", "below_right")
    if left and not right:
        return ("above_right", "below_right", "above_left", "below_left")
    return BADGE_CORNERS + ("below_right", "below_left")


def _covers(seat: CanvasRect, occupied: Sequence[CanvasRect], own: CanvasRect) -> bool:
    """True when the badge sits on its widget or on a child inside that widget."""
    if seat.intersects(own):
        return True
    for rect in occupied:
        if rect == own or not seat.intersects(rect):
            continue
        if (
            rect.x >= own.x
            and rect.y >= own.y
            and rect.x + rect.width <= own.x + own.width
            and rect.y + rect.height <= own.y + own.height
        ):
            return True
    return False


def _selection_chip(
    static: object,
    inputs: object,
    page: CanvasRect,
    viewport: CanvasRect,
) -> Tuple[CanvasRect, ...]:
    """The selection chip, seated the same way the frame seats it, as a fixed obstacle.

    The arrows ask for it as well. Both share the seating kept for this view.
    """
    selection = getattr(inputs, "selection", None)
    current = getattr(selection, "current", None) if selection is not None else None
    measure = getattr(inputs, "measure", None)
    if current is None or not hasattr(selection, "ids") or not callable(measure):
        return ()
    document = getattr(inputs, "document")
    if current == document.root.id:
        return ()
    basis = _basis_for(document, static)
    rect = basis.placed.get(current)
    if rect is None:
        return ()
    from app.features.form_builder.qtside.canvas.core.chips import LABEL_CORNERS
    from app.features.form_builder.qtside.canvas.core.words import chip_text

    text = chip_text(document, selection, getattr(inputs, "sizing", None))
    size = CanvasSize(max(1, int(measure(text)) + 12), 18)
    key = (_view_key(page, viewport, inputs), current, rect, size)
    kept = basis.chips.get(key)
    if kept is not None:
        return kept
    seats = place_chips(
        (ChipRequest(("selection", current), rect, size, LABEL_CORNERS, frozenset(), required=True),),
        basis.chip_obstacles,
        tuple(getattr(inputs, "chrome", ())),
        page,
        viewport,
        getattr(inputs, "dock", None),
    )
    found = (seats[0].rect,) if seats else ()
    if len(basis.chips) >= _MEMO_KEEP:
        basis.chips.pop(next(iter(basis.chips)))
    basis.chips[key] = found
    return found


def _chip_obstacles(document: UiDocument, static: object) -> Tuple[object, ...]:
    """Content other than the root and layouts. The selection chip seats among these."""
    root = document.root.id
    obstacles = []
    for obstacle in getattr(static, "content", ()):
        node_id = getattr(obstacle, "node", None)
        if node_id == root:
            continue
        node = document.get(node_id) if node_id is not None else None
        if isinstance(node, LayoutNode):
            continue
        obstacles.append(obstacle)
    return tuple(obstacles)


def _chain(doc: UiDocument, sender: str) -> Tuple[str, ...]:
    found = doc.by_name(sender)
    node = doc.node(found[0]) if found else None
    if not isinstance(node, WidgetNode):
        return ()
    return widget_chain(doc, node)


def _badge_content(document: UiDocument, static: object) -> Tuple[object, ...]:
    """Other widgets and title bands. The page rect is not a wall."""
    root = document.root.id
    kept: List[object] = []
    seen = set()
    for obstacle in getattr(static, "content", ()):
        node_id = getattr(obstacle, "node", None)
        if node_id == root:
            continue
        node = document.get(node_id) if node_id is not None else None
        if isinstance(node, LayoutNode):
            continue
        kept.append(obstacle)
        seen.add(node_id)
    for item in getattr(static, "placed", ()):
        node_id = getattr(item, "node", None)
        if node_id == root or node_id in seen:
            continue
        node = document.get(node_id) if node_id is not None else None
        if isinstance(node, WidgetNode):
            kept.append(item if hasattr(item, "band") else _Obstacle(item.node, item.rect))
    return tuple(kept)


class _Obstacle:
    def __init__(self, node: object, rect: CanvasRect, band: bool = False) -> None:
        self.node = node
        self.rect = rect
        self.band = band


def _other_widgets(document: UiDocument, static: object) -> List[CanvasRect]:
    root = document.root.id
    rects = []
    for item in getattr(static, "placed", ()):
        node_id = getattr(item, "node", None)
        if node_id == root:
            continue
        node = document.get(node_id) if node_id is not None else None
        if isinstance(node, LayoutNode):
            continue
        rect = getattr(item, "rect", None)
        if isinstance(rect, CanvasRect):
            rects.append(rect)
    return rects


def _on_own_edge(seat: CanvasRect, own: CanvasRect) -> bool:
    """The badge stays on this widget's top or bottom edge, not in the gap beside it."""
    overlap = min(seat.x + seat.width, own.x + own.width) - max(seat.x, own.x)
    if overlap < seat.width / 2:
        return False
    above = seat.y + seat.height <= own.y + 2 and own.y - (seat.y + seat.height) <= 8
    below = seat.y >= own.y + own.height - 2 and seat.y - (own.y + own.height) <= 8
    return above or below


_CELL = 64


def _y_index(rects: Sequence[CanvasRect]) -> Tuple[dict, int]:
    """Rects bucketed by vertical cell, plus the tallest one.

    A query for a y-span returns every rect that overlaps that span, including
    a tall rect that starts above it.
    """
    buckets: dict = {}
    tallest = 1
    for rect in rects:
        height = max(int(rect.height), 1)
        tallest = max(tallest, height)
        top = int(rect.y) // _CELL
        bottom = int(rect.y + height - 1) // _CELL
        for key in range(top, bottom + 1):
            buckets.setdefault(key, []).append(rect)
    return buckets, tallest


def _near(buckets: dict, top: float, bottom: float) -> List[CanvasRect]:
    start = int(top) // _CELL
    end = int(bottom) // _CELL
    found: List[CanvasRect] = []
    seen = set()
    for key in range(start, end + 1):
        for rect in buckets.get(key, ()):
            marker = id(rect)
            if marker in seen:
                continue
            seen.add(marker)
            found.append(rect)
    return found


def _hits(seat: CanvasRect, blockers: Sequence[CanvasRect]) -> bool:
    return any(seat.intersects(other) for other in blockers)


def _badge_fallback(rect: CanvasRect, blockers: Sequence[CanvasRect]) -> Optional[CanvasRect]:
    """A corner of this widget that clears the title band and every other widget."""
    y_above = rect.y - BADGE - 2
    y_below = rect.y + rect.height + 2
    spots = (
        CanvasRect(rect.x + rect.width - BADGE, y_above, BADGE, BADGE),
        CanvasRect(rect.x, y_above, BADGE, BADGE),
        CanvasRect(rect.x + rect.width - BADGE, y_below, BADGE, BADGE),
        CanvasRect(rect.x, y_below, BADGE, BADGE),
    )
    for spot in spots:
        if not _hits(spot, blockers) and not spot.intersects(rect):
            return spot
    return None


def _page(static: object) -> Optional[CanvasRect]:
    view = getattr(static, "view", None)
    origin = getattr(view, "page_origin", None)
    page = getattr(view, "page", None)
    if origin is None or page is None:
        return None
    return CanvasRect(origin.x, origin.y, page.width, page.height)


def _qcolor(text: str) -> QColor:
    raw = text.lstrip("#")
    red, green, blue = int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
    alpha = int(raw[6:8], 16) if len(raw) >= 8 else 255
    return QColor(red, green, blue, alpha)
