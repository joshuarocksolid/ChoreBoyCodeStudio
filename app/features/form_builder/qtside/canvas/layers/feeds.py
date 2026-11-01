"""Dashed arrows from a widget a rule reads to the widget that owns the rule."""

from __future__ import annotations

from typing import Hashable, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.logic.formula_env import env_for
from app.features.form_builder.engine.logic.refs import formula_names
from app.features.form_builder.engine.logic.rules import rule_graph
from app.features.form_builder.engine.logic.storage import FORMULA_KEYS
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.qtside.canvas.core.overlay import LayerItem, LayerOutput
from app.features.form_builder.qtside.canvas.core.space import CanvasRect
from app.features.form_builder.qtside.canvas.layers import CanvasLayer
from app.features.form_builder.qtside.canvas.layers.connections import curve
from app.qt.QtCore import QPointF, Qt
from app.qt.QtGui import QColor, QPainter, QPainterPath, QPen

NAME = "feeds"
Point = Tuple[int, int]


def register(registry: object) -> None:
    getattr(registry, "add")(CanvasLayer(NAME, build, paint, order=73))


def form_has_rules(doc: UiDocument) -> bool:
    for node in doc.iter_widgets():
        for key in FORMULA_KEYS:
            value = node.value(key)
            text = getattr(value, "text", None)
            if isinstance(text, str) and text.strip():
                return True
    return False


def build(static: object, inputs: object, state: Hashable) -> LayerOutput:
    if state not in ("selected", "all"):
        return LayerOutput()
    document = getattr(inputs, "document", None)
    if not isinstance(document, UiDocument):
        return LayerOutput()
    env = env_for(document, None, QtClassTable.shared())
    names = set(env.widgets)
    placed = _placed(static)
    selected = _selected_name(document, inputs)
    if state == "selected" and not selected:
        return LayerOutput()
    items: List[LayerItem] = []
    seen = set()
    for record in rule_graph(document, env).records.values():
        owner = record.widget
        if owner not in names:
            continue
        for source in formula_names(record.text):
            if source not in names or source == owner:
                continue
            pair = (source, owner)
            if pair in seen:
                continue
            if state == "selected" and selected not in pair:
                continue
            origin = _rect(document, placed, source)
            dest = _rect(document, placed, owner)
            if origin is None or dest is None:
                continue
            seen.add(pair)
            start, c1, c2, end, head = curve(origin, dest)
            bounds = _bounds((start, c1, c2, end) + tuple(head))
            items.append(
                LayerItem(
                    rect=bounds,
                    role="select",
                    layer=NAME,
                    data=("feed", source, owner, start, c1, c2, end, head),
                )
            )
    return LayerOutput(tuple(items))


def paint(painter: QPainter, item: LayerItem, palette: object) -> None:
    data = item.data
    if not isinstance(data, tuple) or len(data) < 8 or data[0] != "feed":
        return
    overlay = getattr(palette, "overlay", None)
    if overlay is None:
        return
    # Same ink and weight as a connection arrow (ov.connect). The dash is what
    # marks a feed. ov.feeds stays in the palette for the spec token.
    stroke = float(getattr(overlay, "min_stroke", 1) or 1)
    width = 2.0 if stroke >= 2 else 1.5
    color = _qcolor(str(getattr(overlay, "connect", "")))
    start, c1, c2, end, head = data[3], data[4], data[5], data[6], data[7]
    path = QPainterPath()
    path.moveTo(QPointF(start[0], start[1]))
    path.cubicTo(QPointF(c1[0], c1[1]), QPointF(c2[0], c2[1]), QPointF(end[0], end[1]))
    pen = QPen(color, width)
    pen.setStyle(Qt.PenStyle.DashLine)
    painter.save()
    try:
        if stroke >= 2:
            halo = QPen(_qcolor(getattr(overlay, "chip_text")), width + 2)
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


def _placed(static: object) -> dict:
    found = {}
    for item in getattr(static, "placed", ()):
        found[item.node] = item.rect
    return found


def _rect(document: UiDocument, placed: dict, name: str) -> Optional[CanvasRect]:
    found = document.by_name(name)
    if not found:
        return None
    rect = placed.get(found[0])
    return rect if isinstance(rect, CanvasRect) else None


def _selected_name(document: UiDocument, inputs: object) -> str:
    selection = getattr(inputs, "selection", None)
    current = getattr(selection, "current", None)
    node = document.get(current) if current is not None else None
    name = getattr(node, "object_name", "")
    return name if isinstance(name, str) else ""


def _bounds(points: Sequence[Point]) -> CanvasRect:
    left = min(point[0] for point in points)
    top = min(point[1] for point in points)
    right = max(point[0] for point in points)
    bottom = max(point[1] for point in points)
    return CanvasRect(left, top, max(1, right - left), max(1, bottom - top))


def _qcolor(text: str) -> QColor:
    raw = text.lstrip("#")
    red, green, blue = int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
    alpha = int(raw[6:8], 16) if len(raw) >= 8 else 255
    return QColor(red, green, blue, alpha)
