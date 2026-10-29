"""Outlines the widgets the style sheet rule under the caret styles (UX-STYLE-005, ``ov.style_match``).

The drawer switches this layer on with ``canvas.show_layer("style_matches", ids)``
where ``ids`` is a tuple of node ids, and off with ``hide_layer``. The mark is
``ov.style_match`` drawn dashed, 2 px outside the widget (1.5 px; 2 px in high
contrast).
"""

from __future__ import annotations

from typing import Dict, Hashable, List

from app.features.form_builder.qtside.canvas.core.frame import Item
from app.features.form_builder.qtside.canvas.core.overlay import FrameInputs, LayerItem, LayerOutput, StaticLayer
from app.features.form_builder.qtside.canvas.core.space import CanvasRect
from app.features.form_builder.qtside.canvas.layers import CanvasLayer
from app.features.form_builder.qtside.theme.overlay import CanvasPalette
from app.qt.QtCore import QPointF, QRectF, Qt
from app.qt.QtGui import QColor, QPainter, QPen

NAME = "style_matches"
OUTSIDE = 2
WIDTH = 1.5


def build(static: StaticLayer, inputs: FrameInputs, state: Hashable) -> LayerOutput:
    del inputs
    if not isinstance(state, tuple) or not state:
        return LayerOutput()
    wanted = set(state)
    items: List[Item] = []
    seen: Dict[object, bool] = {}
    for obstacle in static.placed:
        if obstacle.node in wanted and obstacle.node not in seen and not obstacle.band:
            seen[obstacle.node] = True
            rect = obstacle.rect
            outline = CanvasRect(rect.x - OUTSIDE, rect.y - OUTSIDE, rect.width + 2 * OUTSIDE, rect.height + 2 * OUTSIDE)
            items.append(LayerItem(outline, "select", 1.0, NAME, ()))
    return LayerOutput(tuple(items))


def paint(painter: QPainter, item: LayerItem, palette: CanvasPalette) -> None:
    raw = palette.overlay.style_match
    text = raw[1:] if raw.startswith("#") else raw
    color = QColor(int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
    pen = QPen(color)
    pen.setWidthF(max(WIDTH, palette.overlay.min_stroke))
    pen.setStyle(Qt.PenStyle.DashLine)
    pen.setCosmetic(False)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    rect = item.rect
    painter.drawRect(QRectF(QPointF(rect.x, rect.y), QPointF(rect.x + rect.width, rect.y + rect.height)))


def register(registry: object) -> None:
    registry.add(CanvasLayer(NAME, build, paint, order=150))  # type: ignore[attr-defined]
