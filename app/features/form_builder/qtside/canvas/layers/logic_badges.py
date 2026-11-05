"""Logic badges (UX-ARR-001). One 12 px mark per sender that has an event.

The workbench shows this layer in Design. ``build`` returns nothing below
50% zoom. Preview, Save image and Print never ask this layer to paint.
"""

from __future__ import annotations

import weakref
from typing import Dict, Hashable, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.logic.events import events_of_sender, read_events
from app.features.form_builder.engine.logic.storage import is_logic_key
from app.features.form_builder.engine.logic.events_catalog import event_words
from app.features.form_builder.engine.style.classes import widget_chain
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutNode, WidgetNode
from app.features.form_builder.qtside.canvas.core.chips import BADGE_CORNERS, ChipRequest, place_chips
from app.features.form_builder.qtside.canvas.core.overlay import LayerItem, LayerOutput
from app.features.form_builder.qtside.canvas.core.space import CanvasPoint, CanvasRect, CanvasSize
from app.features.form_builder.qtside.canvas.layers import CanvasLayer
from app.features.form_builder.qtside.icons.glyphs import paint_glyph
from app.features.form_builder.qtside.theme.chrome import PAGE_TITLE_GLYPH
from app.features.form_builder.qtside.theme.overlay import CanvasPalette
from app.qt.QtCore import QRectF, Qt
from app.qt.QtGui import QColor, QFont, QPainter, QPen

NAME = "logic_badges"
BADGE = 12
HIDE_BELOW = 0.5
_GLYPH_PX = 7
_INSET = 2
_LOGIC_TAB = False
_GLYPHS = {"\u203a": "chevron_right", "\u2713": "check"}


def set_logic_tab(open_: bool) -> None:
    """The Logic tab is showing, so every sender wears its badge."""
    global _LOGIC_TAB
    _LOGIC_TAB = bool(open_)


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
# One entry per live document. The revision sits in the value.
_NAMES: "weakref.WeakKeyDictionary[UiDocument, Tuple[int, Tuple[str, ...]]]" = weakref.WeakKeyDictionary()
_MARKS: "weakref.WeakKeyDictionary[UiDocument, Tuple[int, Dict[str, Tuple[str, Optional[Tuple[str, str, int]]]]]]" = (
    weakref.WeakKeyDictionary()
)
# (structure revision, document revision, page). A formula note keeps the page.
# Any other revision bump drops it, so undo does not keep the old formula text.
_LOGIC_TEXT: "weakref.WeakKeyDictionary[UiDocument, Tuple[int, int, Dict[str, str]]]" = (
    weakref.WeakKeyDictionary()
)


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
    _NAMES.clear()
    _MARKS.clear()
    _LOGIC_TEXT.clear()
    _EDITED.clear()


def _widget_names(document: UiDocument) -> Tuple[str, ...]:
    revision = document.structure_revision
    cached = _NAMES.get(document)
    if cached is not None and cached[0] == revision:
        return cached[1]
    names = tuple(name for name in (node.object_name for node in document.iter_widgets()) if name)
    _NAMES[document] = (revision, names)
    return names


def _formula_note(document: UiDocument) -> bool:
    held = getattr(document, "_formula_edits", None)
    return isinstance(held, tuple) and len(held) == 2 and isinstance(held[1], list) and bool(held[1])


def _logic_text(document: UiDocument, sender: str) -> str:
    structure = document.structure_revision
    revision = document.revision
    held = _LOGIC_TEXT.get(document)
    if held is None or held[0] != structure or (held[1] != revision and not _formula_note(document)):
        page: Dict[str, str] = {}
        _LOGIC_TEXT[document] = (structure, revision, page)
    else:
        page = held[2]
        if held[1] != revision:
            _LOGIC_TEXT[document] = (structure, revision, page)
    if _formula_touched(document, sender):
        page.pop(sender, None)
    held = page.get(sender)
    if held is not None:
        return held
    found = document.by_name(sender)
    if not found:
        page[sender] = ""
        return ""
    node = document.node(found[0])
    parts = []
    for entry in node.properties():
        if not is_logic_key(entry.name):
            continue
        text = getattr(entry.value, "text", "")
        parts.append("%s=%s" % (entry.name, text if isinstance(text, str) else ""))
    joined = "\0".join(parts)
    page[sender] = joined
    return joined


_EDITED: "weakref.WeakKeyDictionary[UiDocument, Tuple[int, set]]" = weakref.WeakKeyDictionary()


def _formula_touched(document: UiDocument, sender: str) -> bool:
    """True when this revision rewrote a formula on ``sender``."""
    revision = document.revision
    held = _EDITED.get(document)
    if held is None or held[0] != revision:
        names: set = set()
        note = getattr(document, "_formula_edits", None)
        if isinstance(note, tuple) and len(note) == 2 and isinstance(note[1], list):
            for node_id, _prop in note[1]:
                if not document.contains(node_id):
                    continue
                name = getattr(document.node(node_id), "object_name", "") or ""
                if name:
                    names.add(name)
        _EDITED[document] = (revision, names)
    else:
        names = held[1]
    return sender in names


def _event_text(states: Sequence[object]) -> str:
    """Step text the mark reads. A step commit does not move structure_revision."""
    parts = []
    for state in states:
        steps = getattr(state, "steps", ())
        parts.append("%s:%s" % (getattr(state, "signal_name", ""), repr(tuple(steps))))
    return "\0".join(parts)


def _cached_mark(
    document: UiDocument, sender: str, states: Sequence[object]
) -> Optional[Tuple[str, str, int]]:
    structure = document.structure_revision
    held_marks = _MARKS.get(document)
    if held_marks is None or held_marks[0] != structure:
        page = {}
        _MARKS[document] = (structure, page)
    else:
        page = held_marks[1]
    fingerprint = "%s\0%s" % (_logic_text(document, sender), _event_text(states))
    held = page.get(sender)
    if held is not None and held[0] == fingerprint:
        return held[1]
    mark = _mark(document, sender, tuple(states))
    page[sender] = (fingerprint, mark)
    return mark


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
    for name in _widget_names(document):
        if name in seen:
            continue
        if _cached_mark(document, name, ()) is None:
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
    view = getattr(static, "view", None)
    factor = float(getattr(view, "factor", 1.0) or 1.0)
    if factor < HIDE_BELOW:
        return LayerOutput()
    document = getattr(inputs, "document")
    senders, grouped = _badge_senders(document)
    if not _show_every(state):
        senders = _watched(document, inputs, senders)
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
        mark = _cached_mark(document, sender, tuple(grouped.get(sender, ())))
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
    del page, viewport, chips
    blockers = [item.rect for item in basis.content]
    chrome = tuple(getattr(inputs, "chrome", ()) or ())
    found: List[Tuple[str, CanvasRect]] = []
    for sender, rect in bodies:
        seat = _inset_badge(rect, blockers)
        if seat is None:
            continue
        if any(seat.intersects(band) for band in basis.bands):
            continue
        if any(seat.intersects(band) for band in chrome):
            continue
        found.append((sender, seat))
    return tuple(found)


def _inset_badge(rect: CanvasRect, blockers: Sequence[CanvasRect]) -> Optional[CanvasRect]:
    """Top-right, 2 px in. Step left when a neighbour owns that corner."""
    if rect.width < BADGE or rect.height < BADGE:
        return None
    x = rect.x + max(0, rect.width - BADGE - _INSET)
    y = rect.y + _INSET
    seat = CanvasRect(x, y, BADGE, BADGE)
    for _step in range(12):
        if not _badge_hits(seat, rect, blockers):
            return seat
        x -= BADGE + _INSET
        if x < rect.x + _INSET:
            return seat
        seat = CanvasRect(x, y, BADGE, BADGE)
    return seat


def _badge_hits(seat: CanvasRect, own: CanvasRect, blockers: Sequence[CanvasRect]) -> bool:
    for other in blockers:
        if _same_rect(other, own):
            continue
        if other.width >= own.width and other.height >= own.height and _holds(other, own):
            continue
        if seat.intersects(other):
            return True
    return False


def _holds(outer: CanvasRect, inner: CanvasRect) -> bool:
    return (
        outer.x <= inner.x
        and outer.y <= inner.y
        and outer.x + outer.width >= inner.x + inner.width
        and outer.y + outer.height >= inner.y + inner.height
    )


def _show_every(state: Hashable) -> bool:
    # None is the seat-test state. A live layer passes True and paints the
    # hovered or selected sender, unless the Logic tab is open.
    if state == "all" or state is None:
        return True
    return _LOGIC_TAB


def _watched(document: UiDocument, inputs: object, senders: Sequence[str]) -> List[str]:
    allowed = set(senders)
    ids = []
    selection = getattr(inputs, "selection", None)
    if selection is not None:
        current = getattr(selection, "current", None)
        if current is not None:
            ids.append(current)
        extra = getattr(selection, "ids", None)
        if extra:
            ids.extend(extra)
    gesture = getattr(inputs, "gesture", None)
    hover = getattr(gesture, "hover", None) if gesture is not None else None
    if hover is not None:
        ids.append(hover)
    seen = set()
    for node_id in ids:
        if not document.contains(node_id):
            continue
        name = str(getattr(document.get(node_id), "object_name", "") or "")
        if name in allowed:
            seen.add(name)
    return [name for name in senders if name in seen]


def paint(painter: QPainter, item: LayerItem, palette: CanvasPalette) -> None:
    data = item.data
    if not isinstance(data, tuple) or not data or data[0] != "badge":
        return
    colour = palette.overlay.problem if item.role == "problem" else PAGE_TITLE_GLYPH
    box = QRectF(item.rect.x, item.rect.y, item.rect.width, item.rect.height)
    painter.save()
    try:
        pen = QPen(QColor(colour))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(box.adjusted(0.5, 0.5, -0.5, -0.5))
        glyph = "\u203a"
        if len(data) > 3 and data[3]:
            glyph = str(data[3])
        name = _GLYPHS.get(glyph)
        if name:
            ratio = painter.device().devicePixelRatioF() if painter.device() is not None else 1.0
            pixmap = paint_glyph(name, colour, _GLYPH_PX, float(ratio))
            x = int(round(item.rect.x + (item.rect.width - _GLYPH_PX) / 2.0))
            y = int(round(item.rect.y + (item.rect.height - _GLYPH_PX) / 2.0))
            painter.drawPixmap(x, y, pixmap)
        else:
            font = QFont(painter.font())
            font.setPixelSize(_GLYPH_PX)
            font.setBold(False)
            painter.setFont(font)
            painter.setPen(QColor(colour))
            painter.drawText(box, int(Qt.AlignmentFlag.AlignCenter), glyph)
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


def _same_rect(a: CanvasRect, b: CanvasRect) -> bool:
    return a.x == b.x and a.y == b.y and a.width == b.width and a.height == b.height


def _chip_covers(rect: CanvasRect, chips: Sequence[CanvasRect], *, right: bool) -> bool:
    if right:
        corner = CanvasRect(rect.x + rect.width - BADGE - 4, rect.y - BADGE - 4, BADGE + 10, BADGE + 8)
    else:
        corner = CanvasRect(rect.x - 2, rect.y - BADGE - 4, BADGE + 10, BADGE + 8)
    return any(chip.intersects(corner) for chip in chips)


def _badge_fallback(
    rect: CanvasRect,
    blockers: Sequence[CanvasRect],
    chips: Sequence[CanvasRect] = (),
) -> Optional[CanvasRect]:
    """A corner clear of neighbours and of the selection chip.

    Outside corners come first. When every outside corner is taken, the mark
    sits inside the corner opposite the chip so the chip cannot cover it.
    """
    y_above = rect.y - BADGE - 2
    y_below = rect.y + rect.height + 2
    inset = 2
    right_out = CanvasRect(rect.x + rect.width - BADGE, y_above, BADGE, BADGE)
    left_out = CanvasRect(rect.x, y_above, BADGE, BADGE)
    right_below = CanvasRect(rect.x + rect.width - BADGE, y_below, BADGE, BADGE)
    left_below = CanvasRect(rect.x, y_below, BADGE, BADGE)
    right_in = CanvasRect(rect.x + max(0, rect.width - BADGE - inset), rect.y + inset, BADGE, BADGE)
    left_in = CanvasRect(rect.x + inset, rect.y + inset, BADGE, BADGE)
    right_low = CanvasRect(
        rect.x + max(0, rect.width - BADGE - inset),
        rect.y + max(inset, rect.height - BADGE - inset),
        BADGE,
        BADGE,
    )
    left_low = CanvasRect(rect.x + inset, rect.y + max(inset, rect.height - BADGE - inset), BADGE, BADGE)
    # A one-line widget has no room for a mark on its text. Below, then the bottom corner.
    if rect.height < BADGE * 3:
        right_in, left_in = right_low, left_low
    right_first = (right_out, right_below, left_out, left_below, right_in, left_in)
    left_first = (left_out, left_below, right_out, right_below, left_in, right_in)
    chip_on_right = _chip_covers(rect, chips, right=True)
    chip_on_left = _chip_covers(rect, chips, right=False)
    spots = left_first if chip_on_right and not chip_on_left else right_first
    walls = tuple(blockers) + tuple(chips)
    for spot in spots:
        if spot.intersects(rect) or _hits(spot, walls):
            continue
        return spot
    for spot in spots:
        if spot.intersects(rect) and not _hits(spot, walls):
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
