"""The Tab order overlay (UX-OVL-002 .. 005, UX-MODE-002).

One 16 px ``ov.tab`` badge per stop. It sits inside the widget's right edge,
vertically centred, 4 px in from that edge. A widget under 48 px wide carries
the badge outside the right edge, still vertically centred. A 1.5 px dashed
flow line joins the badge centres in order, under the badges and fainter than
them. While the user numbers widgets, the stops already numbered are solid
and the others hollow. A hover chip says "Click to make it 4".
The state is ``TabOrderState``; the host (``integration/overlays.py``) switches
this layer on with ``canvas.show_layer("tab_order", state)``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Hashable, List, Optional, Tuple

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.qtside.canvas.core.chips import (
    ChipRequest,
    Obstacle,
    place_chips,
)
from app.features.form_builder.qtside.canvas.core.frame import Chip
from app.features.form_builder.qtside.canvas.core.overlay import LayerItem, LayerOutput
from app.features.form_builder.qtside.canvas.core.space import CanvasRect, CanvasSize
from app.features.form_builder.qtside.canvas.core.structure import ancestors
from app.features.form_builder.qtside.canvas.layers import CanvasLayer
from app.features.form_builder.qtside.theme.overlay import CanvasPalette
from app.qt.QtCore import QPointF, QRectF, Qt
from app.qt.QtGui import QColor, QFont, QPainter, QPainterPath, QPen

NAME = "tab_order"
_CROSSINGS: Optional[Tuple[FrozenSet[Tuple[int, int]], Dict[Tuple[int, int, int, int], bool]]] = None
BADGE = 16
#: Gap between the badge and the widget's right edge.
INSET = 4
HINT_HEIGHT = 18
HINT_PAD = 12
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
    badges: List[LayerItem] = []
    centres: List[Tuple[int, int]] = []
    for number, name in enumerate(state.order, 1):
        if name not in ids:
            continue
        rect = seat(placed[ids[name]])
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
        for chip in place_chips([hint], content, taken, page, viewport, None):
            items.append(Chip(chip.rect, text, "tab", None))
    return LayerOutput(tuple(items))  # type: ignore[arg-type]


def flow_segments(centres: Tuple[Tuple[int, int], ...]) -> Tuple[Tuple[float, float, float, float, float, float], ...]:
    """``(x1, y1, cx, cy, x2, y2)`` per step: a straight line, or a bow when the straight
    line would run through another badge (stacked rows), so 1 -> 2 never reads as 1 -> 3 -> 2.

    Upward steps bow left and downward steps right, so a step back up never lies on a step down.
    """
    global _CROSSINGS
    points = frozenset(centres)
    if _CROSSINGS is None or _CROSSINGS[0] != points:
        _CROSSINGS = (points, {})
    # Renumbering keeps the badges where they are, so most steps were already checked.
    known = _CROSSINGS[1]
    found = []
    for index in range(len(centres) - 1):
        (x1, y1), (x2, y2) = centres[index], centres[index + 1]
        dx, dy = float(x2 - x1), float(y2 - y1)
        length = (dx * dx + dy * dy) ** 0.5 or 1.0
        mid_x, mid_y = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        step = (x1, y1, x2, y2)
        crossed = known.get(step)
        if crossed is None:
            crossed = _crosses(points, x1, y1, x2, y2, dx, dy, length)
            known[step] = crossed
        if not crossed:
            found.append((float(x1), float(y1), mid_x, mid_y, float(x2), float(y2)))
            continue
        bow = min(2.0 * BADGE, 0.35 * length)
        # (dy, -dx) turned to unit length: left of an upward step, right of a downward one.
        found.append((float(x1), float(y1), mid_x + dy / length * bow, mid_y - dx / length * bow, float(x2), float(y2)))
    return tuple(found)


def _crosses(
    points: FrozenSet[Tuple[int, int]], x1: int, y1: int, x2: int, y2: int, dx: float, dy: float, length: float
) -> bool:
    """Whether the straight step passes within a badge of another badge's centre."""
    for ox, oy in points:
        if (ox, oy) == (x1, y1) or (ox, oy) == (x2, y2):
            continue
        t = ((ox - x1) * dx + (oy - y1) * dy) / (length * length)
        if 0.0 < t < 1.0 and abs((ox - x1) * dy - (oy - y1) * dx) / length < BADGE:
            return True
    return False


def seat(target: CanvasRect) -> CanvasRect:
    y = target.y + (target.height - BADGE) // 2
    if target.width < 48:
        x = target.x + target.width + INSET
    else:
        x = target.x + target.width - INSET - BADGE
    return CanvasRect(x, y, BADGE, BADGE)


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
