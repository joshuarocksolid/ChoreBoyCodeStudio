"""Paints one overlay frame. The painter is already in canvas pixels."""

from __future__ import annotations

from app.qt.QtCore import QPointF, QRectF, Qt
from app.qt.QtGui import QColor, QFont, QPainter, QPen

from app.features.form_builder.qtside.canvas.core.frame import (
    Badge,
    Caption,
    Chip,
    Fill,
    Glyph,
    Handle,
    Item,
    OverlayFrame,
    Pill,
    Role,
    Spring,
    Stroke,
)
from app.features.form_builder.qtside.canvas.core.space import CanvasRect
from app.features.form_builder.qtside.theme.overlay import CanvasPalette

_CHIP_RADIUS = 4.0
_HANDLE_BORDER = 1.5
_SPRING_WIDTH = 1.5
_SPRING_AMP = 6.0
_SPRING_STEP = 8.0


def paint_frame(painter: QPainter, frame: OverlayFrame, palette: CanvasPalette, exposed: QRectF) -> None:
    """Draw items that meet ``exposed``. Strokes stay at least ``min_stroke``."""
    painter.save()
    hints = getattr(QPainter, "RenderHint", QPainter)
    painter.setRenderHint(getattr(hints, "Antialiasing"), True)
    region = exposed.adjusted(-2, -2, 2, 2)
    for item in frame.items:
        if _box(item.rect).intersects(region):
            _paint_one(painter, item, palette)
    painter.restore()


def _paint_one(painter: QPainter, item: Item, palette: CanvasPalette) -> None:
    if isinstance(item, Stroke):
        _stroke(painter, item, palette)
        return
    if isinstance(item, Fill):
        _fill(painter, item, palette)
        return
    if isinstance(item, Spring):
        _spring(painter, item, palette)
        return
    if isinstance(item, Handle):
        _handle(painter, item, palette)
        return
    if isinstance(item, Pill):
        _pill(painter, item, palette)
        return
    if isinstance(item, Chip):
        _chip(painter, item, palette)
        return
    if isinstance(item, Badge):
        _badge(painter, item, palette)
        return
    if isinstance(item, Caption):
        _caption(painter, item, palette)
        return
    if isinstance(item, Glyph):
        _glyph(painter, item.name, item.rect, _ink(palette, item.role, 1.0), _color(palette.overlay.chip_text, 1.0))
        return
    raise AssertionError(type(item))


def _stroke(painter: QPainter, item: Stroke, palette: CanvasPalette) -> None:
    width = max(item.width, palette.overlay.min_stroke)
    painter.setBrush(_no_brush())
    if item.caps:
        _capped_line(painter, item, palette, width)
        return
    painter.setPen(_pen(_ink(palette, item.role, item.alpha), width, item.style))
    painter.drawRect(_box(item.rect))


def _capped_line(painter: QPainter, item: Stroke, palette: CanvasPalette, width: float) -> None:
    rect = item.rect
    ink = _ink(palette, item.role, item.alpha)
    horizontal = rect.width >= rect.height
    if horizontal:
        y = rect.y + rect.height / 2.0
        start = rect.x
        end = rect.x + rect.width
        painter.setPen(_round_pen(ink, width))
        painter.drawLine(QPointF(start, y), QPointF(end, y))
        _cap(painter, ink, start, y)
        _cap(painter, ink, end, y)
        return
    x = rect.x + rect.width / 2.0
    start = rect.y
    end = rect.y + rect.height
    painter.setPen(_round_pen(ink, width))
    painter.drawLine(QPointF(x, start), QPointF(x, end))
    _cap(painter, ink, x, start)
    _cap(painter, ink, x, end)


def _cap(painter: QPainter, ink: QColor, x: float, y: float) -> None:
    painter.setPen(_no_pen())
    painter.setBrush(ink)
    painter.drawEllipse(QPointF(x, y), 3.0, 3.0)


def _round_pen(color: QColor, width: float) -> QPen:
    pen = _pen(color, width, "solid")
    pen.setCapStyle(getattr(getattr(Qt, "PenCapStyle", Qt), "RoundCap"))
    return pen


def _fill(painter: QPainter, item: Fill, palette: CanvasPalette) -> None:
    painter.setPen(_no_pen())
    painter.setBrush(_ink(palette, item.role, item.alpha))
    painter.drawRect(_box(item.rect))


def _spring(painter: QPainter, item: Spring, palette: CanvasPalette) -> None:
    rect = item.rect
    painter.setBrush(_no_brush())
    painter.setPen(_pen(_ink(palette, "gap", 1.0), _SPRING_WIDTH, "solid"))
    if item.axis == "vertical":
        start = rect.y
        end = rect.y + rect.height
        centre = rect.x + rect.width / 2.0
        horizontal = False
    else:
        start = rect.x
        end = rect.x + rect.width
        centre = rect.y + rect.height / 2.0
        horizontal = True
    points = [QPointF(centre, start) if not horizontal else QPointF(start, centre)]
    cursor = start
    side = 1.0
    while cursor < end:
        cursor = min(end, cursor + _SPRING_STEP)
        offset = side * _SPRING_AMP
        if horizontal:
            points.append(QPointF(cursor, centre + offset))
        else:
            points.append(QPointF(centre + offset, cursor))
        side = -side
    painter.drawPolyline(points)


def _handle(painter: QPainter, item: Handle, palette: CanvasPalette) -> None:
    width = max(_HANDLE_BORDER, palette.overlay.min_stroke)
    painter.setBrush(_ink(palette, "select", 1.0))
    painter.setPen(_no_pen())
    outer = _box(item.rect)
    painter.drawRect(outer)
    painter.setBrush(_color(palette.overlay.chip_text, 1.0))
    inset = width
    painter.drawRect(outer.adjusted(inset, inset, -inset, -inset))


def _pill(painter: QPainter, item: Pill, palette: CanvasPalette) -> None:
    raw = palette.backdrop.accent if item.hot else palette.backdrop.faint
    painter.setPen(_no_pen())
    painter.setBrush(_color(raw, 1.0))
    box = _box(item.rect)
    radius = min(box.width(), box.height()) / 2.0
    painter.drawRoundedRect(box, radius, radius)


def _chip(painter: QPainter, item: Chip, palette: CanvasPalette) -> None:
    fill = _ink(palette, item.role, 1.0)
    if item.leader is not None:
        painter.setBrush(_no_brush())
        painter.setPen(_pen(fill, max(1.0, palette.overlay.min_stroke), "solid"))
        painter.drawLine(
            QPointF(item.leader.start.x, item.leader.start.y),
            QPointF(item.leader.end.x, item.leader.end.y),
        )
    if item.docked:
        # The view paints the body above its caption chrome (paint_docked_chip).
        return
    _chip_body(painter, item, fill, palette)


def paint_docked_chip(painter: QPainter, item: Chip, palette: CanvasPalette) -> None:
    """The body of a docked chip. The painter is in canvas pixels."""
    painter.save()
    hints = getattr(QPainter, "RenderHint", QPainter)
    painter.setRenderHint(getattr(hints, "Antialiasing"), True)
    _chip_body(painter, item, _ink(palette, item.role, 1.0), palette)
    painter.restore()


def _chip_body(painter: QPainter, item: Chip, fill: QColor, palette: CanvasPalette) -> None:
    painter.setPen(_no_pen())
    painter.setBrush(fill)
    painter.drawRoundedRect(_box(item.rect), _CHIP_RADIUS, _CHIP_RADIUS)
    painter.setPen(_color(palette.overlay.chip_text, 1.0))
    painter.setFont(_semibold(11))
    painter.drawText(_box(item.rect), _align("AlignCenter"), item.text)


def _badge(painter: QPainter, item: Badge, palette: CanvasPalette) -> None:
    fill = _ink(palette, item.role, 1.0)
    if item.leader is not None:
        painter.setBrush(_no_brush())
        painter.setPen(_pen(fill, max(1.0, palette.overlay.min_stroke), "solid"))
        painter.drawLine(
            QPointF(item.leader.start.x, item.leader.start.y),
            QPointF(item.leader.end.x, item.leader.end.y),
        )
    _glyph(painter, item.glyph, item.rect, fill, _color(palette.overlay.chip_text, 1.0))


def _caption(painter: QPainter, item: Caption, palette: CanvasPalette) -> None:
    painter.setPen(_ink(palette, "layout", 1.0))
    painter.setFont(_semibold(11))
    line_height = 14.0
    total = line_height * len(item.lines)
    top = item.rect.y + (item.rect.height - total) / 2.0
    for index, line in enumerate(item.lines):
        painter.drawText(
            QRectF(item.rect.x, top + index * line_height, item.rect.width, line_height),
            _align("AlignCenter"),
            line,
        )


def _glyph(painter: QPainter, name: str, rect: CanvasRect, colour: QColor, text: QColor) -> None:
    if name == "plus":
        painter.setBrush(_no_brush())
        painter.setPen(_pen(colour, _SPRING_WIDTH, "solid"))
        box = _box(rect)
        mid_x = box.center().x()
        mid_y = box.center().y()
        painter.drawLine(QPointF(box.left(), mid_y), QPointF(box.right(), mid_y))
        painter.drawLine(QPointF(mid_x, box.top()), QPointF(mid_x, box.bottom()))
        return
    if name == "error":
        painter.setPen(_no_pen())
        painter.setBrush(colour)
        painter.drawEllipse(_box(rect))
        painter.setPen(text)
        painter.setFont(_semibold(11))
        painter.drawText(_box(rect), _align("AlignCenter"), "!")
        return
    if name == "grip":
        _grip(painter, rect, colour, text)
        return
    raise AssertionError(name)


def _grip(painter: QPainter, rect: CanvasRect, colour: QColor, rim: QColor) -> None:
    """Three dots along the handle. A light rim keeps them readable over any pane."""
    box = _box(rect)
    tall = box.height() >= box.width()
    spacing = max(box.width(), box.height()) / 3.0
    radius = min(min(box.width(), box.height()), spacing) / 2.0 - 0.5
    painter.setPen(_pen(rim, 1.0, "solid"))
    painter.setBrush(colour)
    for offset in (-1, 0, 1):
        if tall:
            centre = QPointF(box.center().x(), box.center().y() + offset * spacing)
        else:
            centre = QPointF(box.center().x() + offset * spacing, box.center().y())
        painter.drawEllipse(centre, radius, radius)


def _ink(palette: CanvasPalette, role: Role, alpha: float) -> QColor:
    if role == "backdrop_faint":
        raw = palette.backdrop.faint
    elif role == "backdrop_accent":
        raw = palette.backdrop.accent
    else:
        raw = getattr(palette.overlay, role)
    return _color(raw, alpha)


def _color(raw: str, alpha: float) -> QColor:
    text = raw[1:] if raw.startswith("#") else raw
    red = int(text[0:2], 16)
    green = int(text[2:4], 16)
    blue = int(text[4:6], 16)
    stored = int(text[6:8], 16) if len(text) >= 8 else 255
    return QColor(red, green, blue, max(0, min(255, int(round(stored * alpha)))))


def _pen(color: QColor, width: float, style: str) -> QPen:
    pen = QPen(color)
    pen.setWidthF(width)
    pen.setCosmetic(False)
    styles = getattr(Qt, "PenStyle", Qt)
    chosen = {
        "solid": "SolidLine",
        "dashed": "DashLine",
        "dotted": "DotLine",
    }[style]
    pen.setStyle(getattr(styles, chosen))
    return pen


def _no_pen() -> QPen:
    pen = QPen()
    pen.setStyle(getattr(getattr(Qt, "PenStyle", Qt), "NoPen"))
    return pen


def _no_brush() -> object:
    return getattr(getattr(Qt, "BrushStyle", Qt), "NoBrush")


def _semibold(pixel_size: int) -> QFont:
    font = QFont()
    font.setPixelSize(pixel_size)
    font.setBold(True)
    return font


def _align(name: str) -> object:
    return getattr(getattr(Qt, "AlignmentFlag", Qt), name)


def _box(rect: CanvasRect) -> QRectF:
    return QRectF(rect.x, rect.y, rect.width, rect.height)
