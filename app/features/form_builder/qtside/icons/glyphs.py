"""Glyph strokes on a 16 px grid, painted at device resolution."""

from __future__ import annotations

from typing import Dict, Tuple

from app.qt.QtCore import QPointF, Qt
from app.qt.QtGui import QColor, QPainter, QPen, QPixmap, QPolygonF

Stroke = Tuple[Tuple[float, float], ...]
_GRID = 16.0
_STROKE_AT_16 = 1.5
_CACHE: Dict[Tuple[str, str, int, float], QPixmap] = {}


def paint_glyph(name: str, color: str, logical: int, dpr: float) -> QPixmap:
    """Paint ``name`` in one colour at ``logical`` px and device pixel ratio ``dpr``."""
    ratio = round(float(dpr), 2)
    strokes = _GLYPHS[name]
    key = (name, color, int(logical), ratio)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    pixmap = _paint(strokes, color, int(logical), ratio)
    _CACHE[key] = pixmap
    return pixmap


def _paint(strokes: Tuple[Stroke, ...], color: str, logical: int, ratio: float) -> QPixmap:
    # The ratio is applied after the stroke is drawn. Setting it first would
    # make Qt treat these coordinates as logical pixels and scale the pen twice.
    scale = (logical / _GRID) * ratio
    device = max(1, int(round(logical * ratio)))
    pixmap = QPixmap(device, device)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(_antialias(), True)
        pen = QPen(QColor(color))
        pen.setWidthF(_STROKE_AT_16 * scale)
        pen.setCapStyle(_cap("RoundCap"))
        pen.setJoinStyle(_join("RoundJoin"))
        painter.setPen(pen)
        painter.setBrush(_no_brush())
        for stroke in strokes:
            if len(stroke) == 1:
                point = stroke[0]
                painter.drawPoint(QPointF(point[0] * scale, point[1] * scale))
                continue
            painter.drawPolyline(
                QPolygonF([QPointF(x * scale, y * scale) for x, y in stroke])
            )
    finally:
        painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


def _ring(cx: float, cy: float, radius: float) -> Stroke:
    side = radius * 0.7071
    points = (
        (cx, cy - radius),
        (cx + side, cy - side),
        (cx + radius, cy),
        (cx + side, cy + side),
        (cx, cy + radius),
        (cx - side, cy + side),
        (cx - radius, cy),
        (cx - side, cy - side),
    )
    return points + (points[0],)


def _box(left: float, top: float, right: float, bottom: float) -> Stroke:
    return (
        (left, top),
        (right, top),
        (right, bottom),
        (left, bottom),
        (left, top),
    )


def _antialias() -> object:
    hints = getattr(QPainter, "RenderHint", QPainter)
    return getattr(hints, "Antialiasing")


def _cap(name: str) -> object:
    return getattr(getattr(Qt, "PenCapStyle", Qt), name)


def _join(name: str) -> object:
    return getattr(getattr(Qt, "PenJoinStyle", Qt), name)


def _no_brush() -> object:
    return getattr(getattr(Qt, "BrushStyle", Qt), "NoBrush")


_GLYPHS: Dict[str, Tuple[Stroke, ...]] = {
    "chevron_up": (((4, 10), (8, 4), (12, 10)),),
    "chevron_down": (((4, 6), (8, 12), (12, 6)),),
    "chevron_left": (((10, 4), (4, 8), (10, 12)),),
    "chevron_right": (((6, 4), (12, 8), (6, 12)),),
    "plus": (((8, 3), (8, 13)), ((3, 8), (13, 8))),
    "minus": (((3, 8), (13, 8)),),
    "close": (((4, 4), (12, 12)), ((12, 4), (4, 12))),
    "reset": (
        ((12, 6), (9, 3.5), (5, 4.5), (3.5, 8), (5, 11.5), (9, 12.5), (12, 10)),
        ((10, 3), (12, 6), (14, 3.5)),
    ),
    "undo": (
        ((12, 5), (7, 5), (4, 8), (7, 11), (12, 11)),
        ((7, 3), (4, 8), (8, 7)),
    ),
    "redo": (
        ((4, 5), (9, 5), (12, 8), (9, 11), (4, 11)),
        ((9, 3), (12, 8), (8, 7)),
    ),
    "play": (((5, 3), (13, 8), (5, 13), (5, 3)),),
    "zoom": (_ring(7, 7, 3.5), ((9.6, 9.6), (13, 13))),
    "fit": (
        ((3, 6), (3, 3), (6, 3)),
        ((10, 3), (13, 3), (13, 6)),
        ((13, 10), (13, 13), (10, 13)),
        ((6, 13), (3, 13), (3, 10)),
    ),
    "two_widths": (((5, 3), (5, 13)), ((11, 3), (11, 13))),
    "text_size": (((4, 13), (8, 3), (12, 13)), ((5.5, 9), (10.5, 9))),
    "xml": (((3, 4), (7, 8), (3, 12)), ((13, 4), (9, 8), (13, 12))),
    "tab_order": (
        ((3, 4), (3, 8), (8, 8), (8, 12)),
        ((6, 10.5), (8, 12.5), (10, 10.5)),
    ),
    "buddy": (_ring(5, 8, 2.2), _ring(11, 8, 2.2), ((7.2, 8), (8.8, 8))),
    "connection": (((3, 6), (3, 10)), ((3, 8), (13, 8)), ((13, 6), (13, 10))),
    "warning": (
        ((8, 3), (13, 13), (3, 13), (8, 3)),
        ((8, 6.5), (8, 10)),
        ((8, 11.6),),
    ),
    "error": (_ring(8, 8, 5), ((5.2, 5.2), (10.8, 10.8)), ((10.8, 5.2), (5.2, 10.8))),
    "info": (_ring(8, 8, 5), ((8, 4.6),), ((8, 7), (8, 11.4))),
    "check": (((3.5, 8.5), (7, 12), (13, 4)),),
    "lock": (
        ((5, 7), (5, 5), (6.2, 3.4), (8, 3), (9.8, 3.4), (11, 5), (11, 7)),
        _box(4, 7, 12, 13),
    ),
    "database": (
        ((4, 4.5), (6, 3), (10, 3), (12, 4.5), (10, 6), (6, 6), (4, 4.5)),
        ((4, 4.5), (4, 11)),
        ((12, 4.5), (12, 11)),
        ((4, 11), (6, 12.5), (10, 12.5), (12, 11)),
        ((4, 7.5), (6, 9), (10, 9), (12, 7.5)),
    ),
    "search": (_ring(7, 7, 3.2), ((9.5, 9.5), (13, 13))),
    "grip": (
        ((5, 4),),
        ((11, 4),),
        ((5, 8),),
        ((11, 8),),
        ((5, 12),),
        ((11, 12),),
    ),
    "more": (((4, 8),), ((8, 8),), ((12, 8),)),
    "outline": (((4, 4), (13, 4)), ((4, 8), (13, 8)), ((4, 12), (13, 12))),
    "insert": (((8, 3), (8, 9)), ((5, 6), (8, 9), (11, 6)), ((3, 12), (13, 12))),
    "properties": (
        ((3, 4), (13, 4)),
        ((3, 8), (13, 8)),
        ((3, 12), (13, 12)),
        ((6, 2.5), (6, 5.5)),
        ((10, 6.5), (10, 9.5)),
        ((7, 10.5), (7, 13.5)),
    ),
    "behavior": (((3, 4), (8, 4), (8, 8), (13, 8), (13, 12)),),
    "pin": (_ring(8, 5, 2.4), ((8, 7.4), (8, 13.5))),
}
