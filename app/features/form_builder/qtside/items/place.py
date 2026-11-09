"""Seat the item popover so it never covers the widget (UX-CHIP-002 order)."""

from __future__ import annotations

from app.features.form_builder.qtside.canvas.core.chips import LABEL_CORNERS, ChipRequest, place_chips
from app.features.form_builder.qtside.canvas.core.space import CanvasRect, CanvasSize
from app.qt.QtCore import QPoint, QRect, QSize


def seat_beside(target: QRect, popup: QSize, viewport: QRect) -> QPoint:
    """Canvas placement. Coordinates are global. The target is never covered."""
    origin_x = viewport.x()
    origin_y = viewport.y()
    request = ChipRequest(
        key="items",
        target=CanvasRect(target.x() - origin_x, target.y() - origin_y, target.width(), target.height()),
        size=CanvasSize(popup.width(), popup.height()),
        corners=LABEL_CORNERS,
        exempt=frozenset(),
        required=True,
    )
    page = CanvasRect(0, 0, viewport.width(), viewport.height())
    seats = place_chips((request,), (), (), page, page)
    if not seats:
        return QPoint(target.x(), target.bottom() + 7)
    rect = seats[0].rect
    return QPoint(rect.x + origin_x, rect.y + origin_y)


def seat_under(anchor: QRect, popup: QSize, bounds: QRect) -> QPoint:
    """Inspector placement. Below the row, above it when below would cover the row."""
    x = anchor.x()
    y = anchor.bottom() + 4
    if y + popup.height() > bounds.bottom():
        y = anchor.top() - popup.height() - 4
    x = min(max(x, bounds.left()), max(bounds.left(), bounds.right() - popup.width()))
    y = min(max(y, bounds.top()), max(bounds.top(), bounds.bottom() - popup.height()))
    return QPoint(x, y)
