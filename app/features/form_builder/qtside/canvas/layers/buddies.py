"""The Buddies overlay (UX-OVL-007, UX-OVL-008, UX-MODE-004).

Each label with a buddy gets a 1.5 px ``ov.buddy`` link from 2 px right of its
text to 2 px left of the field, with 4 px end dots, and never across the text.
A label without a buddy gets a hollow 8 px ring in the margin on its left. A
link in progress is dashed and the field it would join gets a frame. Fields are
not tinted. ``BuddyState.metrics`` answers ``text_box(label name)`` with the
``(left, width)`` of the label's words inside the label, in form pixels.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Hashable, List, Optional, Protocol, Tuple

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query import tab_stops as q
from app.features.form_builder.qtside.canvas.core.overlay import LayerItem, LayerOutput
from app.features.form_builder.qtside.canvas.core.space import CanvasRect
from app.features.form_builder.qtside.canvas.layers import CanvasLayer
from app.features.form_builder.qtside.theme.overlay import CanvasPalette
from app.qt.QtCore import QPointF, QRectF, Qt
from app.qt.QtGui import QColor, QPainter, QPen

NAME = "buddies"
RING = 8
RING_GAP = 4
DOT = 4
LINK_GAP = 2
_BUDDY = "#047857FF"
_BUDDY_HIGH_CONTRAST = "#00553AFF"

Point = Tuple[int, int]


class TextMetrics(Protocol):
    def text_box(self, label_name: str) -> Optional[Tuple[float, float]]:
        """``(left, width)`` of the label's words inside the label, in form pixels."""
        ...


@dataclass(frozen=True)
class BuddyState:
    metrics: object = None
    #: The label a link is being made from, and the field it would join. Empty for none.
    active: str = ""
    candidate: str = ""
    #: Canvas pixel under a drag with no field below it.
    pointer: Optional[Point] = None


def register(registry: object) -> None:
    getattr(registry, "add")(CanvasLayer(NAME, build, paint, order=71))


def link_points(label: CanvasRect, text_right: int, field: CanvasRect) -> Tuple[Point, ...]:
    """From 2 px right of the text to 2 px left of the field; around the field when it is not to the right."""
    start = (text_right + LINK_GAP, label.y + label.height // 2)
    field_mid = field.y + field.height // 2
    end = (field.x - LINK_GAP, field_mid)
    if end[0] >= start[0] + DOT:
        return (start, end)
    far = max(start[0], field.x + field.width) + 8
    return (start, (far, start[1]), (far, field_mid), (field.x + field.width + LINK_GAP, field_mid))


def ring_rect(label: CanvasRect) -> CanvasRect:
    return CanvasRect(label.x - RING_GAP - RING, label.y + label.height // 2 - RING // 2, RING, RING)


def _bounds(points: Tuple[Point, ...]) -> CanvasRect:
    left = min(x for x, _y in points) - DOT
    top = min(y for _x, y in points) - DOT
    right = max(x for x, _y in points) + DOT
    bottom = max(y for _x, y in points) + DOT
    return CanvasRect(left, top, right - left, bottom - top)


def build(static: object, inputs: object, state: Hashable) -> LayerOutput:
    if not isinstance(state, BuddyState):
        return LayerOutput()
    document = getattr(inputs, "document")
    view = getattr(static, "view")
    factor = float(view.factor) or 1.0
    placed: Dict[NodeId, CanvasRect] = {item.node: item.rect for item in getattr(static, "placed")}
    metrics = state.metrics
    items: List[LayerItem] = []

    def text_right(name: str, rect: CanvasRect) -> int:
        box = metrics.text_box(name) if metrics is not None else None  # type: ignore[attr-defined]
        if box is None:
            return rect.x + rect.width
        return min(rect.x + rect.width, rect.x + int(round((box[0] + box[1]) * factor)))

    def field_rect(name: str) -> Optional[CanvasRect]:
        found = document.by_name(name)
        return placed.get(found[0]) if found else None

    for label_id in q.labels(document):
        rect = placed.get(label_id)
        if rect is None:
            continue
        name = document.node(label_id).object_name
        buddy = q.buddy_of(document, label_id)
        target = field_rect(buddy) if buddy else None
        if buddy and target is not None:
            points = link_points(rect, text_right(name, rect), target)
            items.append(LayerItem(rect=_bounds(points), role="select", layer=NAME, data=("link", points, name == state.active)))
        elif not buddy:
            ring = ring_rect(rect)
            items.append(LayerItem(rect=ring, role="select", layer=NAME, data=("ring", name == state.active)))
    if state.active:
        found = document.by_name(state.active)
        origin = placed.get(found[0]) if found else None
        if origin is not None:
            start = (text_right(state.active, origin) + LINK_GAP, origin.y + origin.height // 2)
            candidate = field_rect(state.candidate) if state.candidate else None
            if candidate is not None:
                points = link_points(origin, text_right(state.active, origin), candidate)
                items.append(LayerItem(rect=_bounds(points), role="select", layer=NAME, data=("pending", points)))
                items.append(LayerItem(rect=candidate.grown(2), role="select", layer=NAME, data=("frame",)))
            elif state.pointer is not None:
                points = (start, state.pointer)
                items.append(LayerItem(rect=_bounds(points), role="select", layer=NAME, data=("pending", points)))
    return LayerOutput(tuple(items))


def _color(palette: CanvasPalette) -> QColor:
    text = (_BUDDY_HIGH_CONTRAST if palette.overlay.min_stroke >= 2.0 else _BUDDY).lstrip("#")
    return QColor(int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))


def paint(painter: QPainter, item: LayerItem, palette: CanvasPalette) -> None:
    data = item.data
    if not isinstance(data, tuple) or not data:
        return
    ink = _color(palette)
    width = max(1.5, palette.overlay.min_stroke)
    painter.save()
    try:
        kind = data[0]
        if kind in ("link", "pending"):
            points = [QPointF(x, y) for x, y in data[1]]
            pen = QPen(ink, width)
            if kind == "pending":
                pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolyline(points)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(ink)
            for end in (points[0], points[-1]):
                painter.drawEllipse(end, DOT / 2.0, DOT / 2.0)
        elif kind == "ring":
            box = QRectF(item.rect.x, item.rect.y, item.rect.width, item.rect.height)
            painter.setPen(QPen(ink, width))
            painter.setBrush(ink if data[1] else Qt.BrushStyle.NoBrush)
            painter.drawEllipse(box.adjusted(0.75, 0.75, -0.75, -0.75))
        elif kind == "frame":
            painter.setPen(QPen(ink, max(2.0, palette.overlay.min_stroke)))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(item.rect.x, item.rect.y, item.rect.width, item.rect.height))
    finally:
        painter.restore()
