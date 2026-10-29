"""The Tab order overlay (UX-OVL-002 .. 005, UX-MODE-002).

One 16 px ``ov.tab`` badge per stop, seated outside its widget by the chip
solver (above left first), never inside it. A 1.5 px dashed flow line joins the
badge centres in order. While the user numbers widgets, the stops already
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
    Leader,
    Obstacle,
    corner_rect,
    place_chips,
)
from app.features.form_builder.qtside.canvas.core.frame import Chip
from app.features.form_builder.qtside.canvas.core.overlay import LayerItem, LayerOutput
from app.features.form_builder.qtside.canvas.core.space import CanvasPoint, CanvasRect, CanvasSize
from app.features.form_builder.qtside.canvas.core.structure import ancestors
from app.features.form_builder.qtside.canvas.layers import CanvasLayer
from app.features.form_builder.qtside.theme.overlay import CanvasPalette
from app.qt.QtCore import QPointF, QRectF, Qt
from app.qt.QtGui import QColor, QFont, QPainter, QPen

NAME = "tab_order"
_SEATED: Optional[Tuple[Hashable, Dict[Hashable, object]]] = None
BADGE = 16
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
    seated = dict(_SEATED[1])
    if state.hover and state.hover in ids:
        text = hint_text(state.assigned + 1)
        size = CanvasSize(int(measure(text)) + HINT_PAD, HINT_HEIGHT)
        node = ids[state.hover]
        hint = ChipRequest("\0hint", placed[node], size, _HINT_CORNERS, ancestors(document, node))
        taken = chrome + tuple(seat.rect for seat in seated.values())
        for seat in place_chips([hint], content, taken, page, viewport, None):
            seated[seat.key] = seat
    badges: List[LayerItem] = []
    centres: List[Tuple[int, int]] = []
    for number, name in enumerate(state.order, 1):
        if name not in ids:
            continue
        target = placed[ids[name]]
        seat = seated.get(name)
        if seat is None:
            rect = corner_rect(target, CanvasSize(BADGE, BADGE), "above_left")
            leader: Optional[Leader] = None
        else:
            rect = seat.rect
            leader = None if isinstance(seat, CornerSeat) else getattr(seat, "leader", None)
        solid = state.assigned == 0 or number <= state.assigned
        line = ()
        if leader is not None:
            line = (leader.start.x, leader.start.y, leader.end.x, leader.end.y)
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
                data=("flow", tuple(centres)),
            )
        )
    items.extend(badges)
    seat = seated.get("\0hint")
    if seat is not None and state.hover in ids:
        items.append(Chip(seat.rect, hint_text(state.assigned + 1), "tab", None))
    return LayerOutput(tuple(items))  # type: ignore[arg-type]


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
            pen = QPen(_color(over.tab, 0.9), max(1.5, over.min_stroke))
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            points = [QPointF(x, y) for x, y in data[1]]
            painter.drawPolyline(points)
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
