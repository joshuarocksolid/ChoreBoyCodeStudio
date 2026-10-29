"""The Tab order overlay (UX-OVL-002 .. 005, UX-MODE-002).

One 16 px ``ov.tab`` badge per stop, seated at an outside corner of its widget
by the chip solver (above left first). When any stop has no free corner, as in
packed layout rows, every badge sits just inside its widget's top-left corner
instead of in a gutter with a leader. A 1.5 px dashed flow line joins the badge centres in
order, under the badges and fainter than them. While the user numbers widgets, the stops already
numbered are solid and the others hollow. A hover chip says "Click to make it 4".
The state is ``TabOrderState``; the host (``integration/overlays.py``) switches
this layer on with ``canvas.show_layer("tab_order", state)``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Hashable, List, Optional, Tuple

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.qtside.canvas.core.chips import (
    ChipRequest,
    CornerSeat,
    Obstacle,
    place_chips,
)
from app.features.form_builder.qtside.canvas.core.frame import Chip
from app.features.form_builder.qtside.canvas.core.overlay import LayerItem, LayerOutput
from app.features.form_builder.qtside.canvas.core.space import CanvasPoint, CanvasRect, CanvasSize
from app.features.form_builder.qtside.canvas.core.structure import ancestors
from app.features.form_builder.qtside.canvas.layers import CanvasLayer
from app.features.form_builder.qtside.theme.overlay import CanvasPalette
from app.qt.QtCore import QPointF, QRectF, Qt
from app.qt.QtGui import QColor, QFont, QPainter, QPainterPath, QPen

NAME = "tab_order"
_SEATED: Optional[Tuple[Hashable, Dict[Hashable, object]]] = None
BADGE = 16
#: Gap between a badge seated inside its widget and the widget's left and top edges.
INSET = 3
HINT_HEIGHT = 18
HINT_PAD = 12
_CORNERS = ("above_left", "below_left", "above_right", "below_right")
_HINT_CORNERS = ("below_left", "above_left", "below_right", "above_right")


@dataclass(frozen=True)
class TabOrderState:
    """``order``: the stops, first to last. ``assigned``: how many were numbered in this session (0 draws all solid)."""

    order: Tuple[str, ...]
    assigned: int = 0
    #: The stop under the pointer, for the "Click to make it N" chip. Empty for none.
    hover: str = ""


def register(registry: object) -> None:
    getattr(registry, "add")(CanvasLayer(NAME, build, paint, order=70))


def hint_text(number: int) -> str:
    return "Click to make it %d" % number


def build(static: object, inputs: object, state: Hashable) -> LayerOutput:
    if not isinstance(state, TabOrderState) or not state.order:
        return LayerOutput()
    document = getattr(inputs, "document")
    placed: Dict[NodeId, CanvasRect] = {item.node: item.rect for item in getattr(static, "placed")}
    view = getattr(static, "view")
    page: CanvasRect = view.page_rect()
    viewport = getattr(inputs, "viewport", None) or page.grown(400)
    measure = getattr(inputs, "measure")
    content: Tuple[Obstacle, ...] = getattr(static, "content")
    ids: Dict[str, NodeId] = {}
    for name in state.order:
        found = document.by_name(name)
        if found and found[0] in placed:
            ids[name] = found[0]
    chrome = tuple(getattr(inputs, "chrome", ()))
    # Seats depend on where the stops are, not on their numbers, so a click that only renumbers reuses them.
    key = (getattr(static, "epoch"), view, tuple(sorted(ids)), viewport, chrome)
    global _SEATED
    if _SEATED is None or _SEATED[0] != key:
        requests = [
            ChipRequest(name, placed[node], CanvasSize(BADGE, BADGE), _CORNERS, ancestors(document, node))
            for name, node in ids.items()
        ]
        _SEATED = (key, {seat.key: seat for seat in place_chips(requests, content, chrome, page, viewport, None)})
    seated = _SEATED[1]
    # One rule for the whole form: when any stop has no free corner, every badge goes inside.
    outside = all(isinstance(seated.get(name), CornerSeat) for name in ids)
    badges: List[LayerItem] = []
    centres: List[Tuple[int, int]] = []
    for number, name in enumerate(state.order, 1):
        if name not in ids:
            continue
        target = placed[ids[name]]
        seat = seated.get(name)
        # A badge sits at its widget's outside corner. When corners are taken (rows
        # packed in a layout) badges go just inside the top-left corner: a badge in a
        # side gutter with a leader, or a mix of above, inside and below, reads as
        # belonging to the wrong widget.
        rect = seat.rect if outside and seat is not None else inside_corner(target)
        solid = state.assigned == 0 or number <= state.assigned
        line = ()
        badges.append(LayerItem(rect=rect, role="tab", layer=NAME, data=("badge", number, solid, line)))
        centres.append((rect.x + rect.width // 2, rect.y + rect.height // 2))
    items: List[object] = []
    if len(centres) > 1:
        left = min(x for x, _y in centres)
        top = min(y for _x, y in centres)
        right = max(x for x, _y in centres)
        bottom = max(y for _x, y in centres)
        items.append(
            LayerItem(
                rect=CanvasRect(left, top, max(1, right - left), max(1, bottom - top)),
                role="tab",
                layer=NAME,
                data=("flow", flow_segments(tuple(centres))),
            )
        )
    items.extend(badges)
    if state.hover and state.hover in ids:
        text = hint_text(state.assigned + 1)
        size = CanvasSize(int(measure(text)) + HINT_PAD, HINT_HEIGHT)
        node = ids[state.hover]
        hint = ChipRequest("\0hint", placed[node], size, _HINT_CORNERS, ancestors(document, node))
        taken = chrome + tuple(badge.rect for badge in badges)
        for seat in place_chips([hint], content, taken, page, viewport, None):
            items.append(Chip(seat.rect, text, "tab", None))
    return LayerOutput(tuple(items))  # type: ignore[arg-type]


def flow_segments(centres: Tuple[Tuple[int, int], ...]) -> Tuple[Tuple[float, float, float, float, float, float], ...]:
    """``(x1, y1, cx, cy, x2, y2)`` per step: a straight line, or a bow when the straight
    line would run through another badge (stacked rows), so 1 -> 2 never reads as 1 -> 3 -> 2.

    Upward steps bow left and downward steps right, so a step back up never lies on a step down.
    """
    found = []
    for index in range(len(centres) - 1):
        (x1, y1), (x2, y2) = centres[index], centres[index + 1]
        dx, dy = float(x2 - x1), float(y2 - y1)
        length = (dx * dx + dy * dy) ** 0.5 or 1.0
        mid_x, mid_y = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        crossed = False
        for other, (ox, oy) in enumerate(centres):
            if other in (index, index + 1):
                continue
            t = ((ox - x1) * dx + (oy - y1) * dy) / (length * length)
            if 0.0 < t < 1.0 and abs((ox - x1) * dy - (oy - y1) * dx) / length < BADGE:
                crossed = True
                break
        if not crossed:
            found.append((float(x1), float(y1), mid_x, mid_y, float(x2), float(y2)))
            continue
        bow = min(2.0 * BADGE, 0.35 * length)
        # (dy, -dx) turned to unit length: left of an upward step, right of a downward one.
        found.append((float(x1), float(y1), mid_x + dy / length * bow, mid_y - dx / length * bow, float(x2), float(y2)))
    return tuple(found)


def inside_corner(target: CanvasRect) -> CanvasRect:
    """A badge just inside the widget's top-left corner, centred on a one-line field."""
    inset_y = max(0, min(INSET, (target.height - BADGE) // 2))
    inset_x = INSET if target.width >= BADGE + 2 * INSET else 0
    return CanvasRect(target.x + inset_x, target.y + inset_y, BADGE, BADGE)


def _color(raw: str, alpha: float = 1.0) -> QColor:
    text = raw.lstrip("#")
    color = QColor(int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
    stored = int(text[6:8], 16) if len(text) >= 8 else 255
    color.setAlpha(max(0, min(255, int(round(stored * alpha)))))
    return color


def paint(painter: QPainter, item: LayerItem, palette: CanvasPalette) -> None:
    data = item.data
    if not isinstance(data, tuple) or not data:
        return
    over = palette.overlay
    painter.save()
    try:
        if data[0] == "flow":
            pen = QPen(_color(over.tab, 0.55), max(1.5, over.min_stroke))
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            path = QPainterPath()
            for x1, y1, cx, cy, x2, y2 in data[1]:
                path.moveTo(x1, y1)
                path.quadTo(cx, cy, x2, y2)
            painter.drawPath(path)
            return
        if data[0] != "badge":
            return
        _kind, number, solid, line = data
        box = QRectF(item.rect.x, item.rect.y, item.rect.width, item.rect.height)
        if line:
            painter.setPen(QPen(_color(over.tab), max(1.0, over.min_stroke)))
            painter.drawLine(QPointF(line[0], line[1]), QPointF(line[2], line[3]))
        if solid:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(_color(over.tab))
            painter.drawEllipse(box)
            painter.setPen(_color(over.chip_text))
        else:
            painter.setPen(QPen(_color(over.tab), max(1.5, over.min_stroke)))
            painter.setBrush(_color(over.chip_text))
            painter.drawEllipse(box.adjusted(0.75, 0.75, -0.75, -0.75))
            painter.setPen(_color(over.tab))
        font = QFont()
        font.setPixelSize(10 if number < 100 else 8)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(box, int(Qt.AlignmentFlag.AlignCenter), str(number))
    finally:
        painter.restore()
