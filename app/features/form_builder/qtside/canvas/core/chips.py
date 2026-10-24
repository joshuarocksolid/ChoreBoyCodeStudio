"""Chip and badge placement. A pure function of rectangles.

A seat is a corner inside the viewport, or a gutter clamped into it.
A corner outside the viewport is skipped. A seat that would cover content
is skipped rather than drawn on top of a widget.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Hashable, List, Literal, Optional, Sequence, Tuple, Union

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.qtside.canvas.core.space import CanvasPoint, CanvasRect, CanvasSize

Corner = Literal["above_left", "below_left", "above_right", "below_right"]
Side = Literal["left", "right"]

LABEL_CORNERS: Tuple[Corner, ...] = ("above_left", "below_left", "above_right", "below_right")
BADGE_CORNERS: Tuple[Corner, ...] = ("above_right", "above_left")

CHIP_GAP = 7
GUTTER_INSET = 4
_CELL = 64


@dataclass(frozen=True)
class ChipRequest:
    key: Hashable
    target: CanvasRect
    size: CanvasSize
    corners: Tuple[Corner, ...]
    #: Ancestors the chip may overlap. The target itself is never exempt.
    exempt: FrozenSet[NodeId]


@dataclass(frozen=True)
class Obstacle:
    node: NodeId
    rect: CanvasRect


@dataclass(frozen=True)
class Leader:
    start: CanvasPoint
    end: CanvasPoint


@dataclass(frozen=True)
class CornerSeat:
    key: Hashable
    rect: CanvasRect
    corner: Corner


@dataclass(frozen=True)
class GutterSeat:
    key: Hashable
    rect: CanvasRect
    leader: Leader
    side: Side


ChipSeat = Union[CornerSeat, GutterSeat]


def place_chips(
    requests: Sequence[ChipRequest],
    content: Sequence[Obstacle],
    fixed: Sequence[CanvasRect],
    page: CanvasRect,
    viewport: CanvasRect,
) -> Tuple[ChipSeat, ...]:
    """Seats that fit. Earlier requests keep the corners they take."""
    buckets = _Buckets(content)
    taken: List[CanvasRect] = list(fixed)
    seats: List[ChipSeat] = []
    for request in requests:
        seat = _corner_seat(request, buckets, taken, viewport)
        if seat is None:
            seat = _gutter_seat(request, buckets, taken, page, viewport)
        if seat is None:
            continue
        taken.append(seat.rect)
        seats.append(seat)
    return tuple(seats)


def _corner_seat(
    request: ChipRequest,
    buckets: "_Buckets",
    taken: Sequence[CanvasRect],
    viewport: CanvasRect,
) -> Optional[CornerSeat]:
    for corner in request.corners:
        rect = corner_rect(request.target, request.size, corner)
        if not _clear(rect, viewport, buckets, request.exempt, taken):
            continue
        return CornerSeat(request.key, rect, corner)
    return None


def _gutter_seat(
    request: ChipRequest,
    buckets: "_Buckets",
    taken: Sequence[CanvasRect],
    page: CanvasRect,
    viewport: CanvasRect,
) -> Optional[GutterSeat]:
    rect, _, side = gutter_spot(request.target, request.size, page, taken)
    if _clear(rect, viewport, buckets, request.exempt, taken):
        return _as_gutter(request, rect, side)
    clamped = _clamp(rect, viewport)
    if clamped is not None and _clear(clamped, viewport, buckets, request.exempt, taken):
        return _as_gutter(request, clamped, side)
    other: Side = "left" if side == "right" else "right"
    for candidate in (side, other):
        found = _scan_gutter(request, buckets, taken, page, viewport, candidate)
        if found is not None:
            return found
    return None


def _as_gutter(request: ChipRequest, rect: CanvasRect, side: Side) -> GutterSeat:
    return GutterSeat(request.key, rect, _leader(rect, request.target, side), side)


def _scan_gutter(
    request: ChipRequest,
    buckets: "_Buckets",
    taken: Sequence[CanvasRect],
    page: CanvasRect,
    viewport: CanvasRect,
    side: Side,
) -> Optional[GutterSeat]:
    x = _gutter_x(page, request.size, viewport, side)
    if x is None:
        return None
    height = request.size.height
    top = viewport.y
    bottom = viewport.y + viewport.height - height
    origin = request.target.y + (request.target.height - height) // 2
    if origin < top:
        origin = top
    if origin > bottom:
        origin = bottom
    step = max(1, height + 2)
    y_values = [origin]
    down = origin + step
    up = origin - step
    while down <= bottom or up >= top:
        if down <= bottom:
            y_values.append(down)
            down += step
        if up >= top:
            y_values.append(up)
            up -= step
    for y in y_values:
        rect = CanvasRect(x, y, request.size.width, height)
        if _clear(rect, viewport, buckets, request.exempt, taken):
            return _as_gutter(request, rect, side)
    return None


def _gutter_x(page: CanvasRect, size: CanvasSize, viewport: CanvasRect, side: Side) -> Optional[int]:
    if size.width > viewport.width or size.height > viewport.height:
        return None
    if side == "right":
        x = page.x + page.width + GUTTER_INSET
    else:
        x = page.x - GUTTER_INSET - size.width
    if x < viewport.x:
        x = viewport.x
    limit = viewport.x + viewport.width - size.width
    if x > limit:
        x = limit
    return x


def _clamp(rect: CanvasRect, viewport: CanvasRect) -> Optional[CanvasRect]:
    if rect.width > viewport.width or rect.height > viewport.height:
        return None
    x = min(max(rect.x, viewport.x), viewport.x + viewport.width - rect.width)
    y = min(max(rect.y, viewport.y), viewport.y + viewport.height - rect.height)
    return CanvasRect(x, y, rect.width, rect.height)


def _inside(rect: CanvasRect, viewport: CanvasRect) -> bool:
    return (
        rect.x >= viewport.x
        and rect.y >= viewport.y
        and rect.x + rect.width <= viewport.x + viewport.width
        and rect.y + rect.height <= viewport.y + viewport.height
    )


def _clear(
    rect: CanvasRect,
    viewport: CanvasRect,
    buckets: "_Buckets",
    exempt: FrozenSet[NodeId],
    taken: Sequence[CanvasRect],
) -> bool:
    if not _inside(rect, viewport):
        return False
    if buckets.blocked(rect, exempt):
        return False
    return not _hits_any(rect, taken)


def corner_rect(target: CanvasRect, size: CanvasSize, corner: Corner) -> CanvasRect:
    if corner == "above_left":
        return CanvasRect(target.x, target.y - CHIP_GAP - size.height, size.width, size.height)
    if corner == "below_left":
        return CanvasRect(target.x, target.y + target.height + CHIP_GAP, size.width, size.height)
    if corner == "above_right":
        return CanvasRect(
            target.x + target.width - size.width,
            target.y - CHIP_GAP - size.height,
            size.width,
            size.height,
        )
    return CanvasRect(
        target.x + target.width - size.width,
        target.y + target.height + CHIP_GAP,
        size.width,
        size.height,
    )


def gutter_spot(
    target: CanvasRect,
    size: CanvasSize,
    page: CanvasRect,
    taken: Sequence[CanvasRect],
) -> Tuple[CanvasRect, Leader, Side]:
    """Outside ``page``. ``taken`` only slides the seat along the gutter."""
    target_mid = target.x + target.width / 2.0
    page_mid = page.x + page.width / 2.0
    if target_mid >= page_mid:
        side: Side = "right"
        x = page.x + page.width + GUTTER_INSET
    else:
        side = "left"
        x = page.x - GUTTER_INSET - size.width
    origin_y = target.y + (target.height - size.height) // 2
    step = max(1, size.height + 2)
    low = origin_y
    high = origin_y
    for other in taken:
        if other.x + other.width < x or x + size.width < other.x:
            continue
        low = min(low, other.y - size.height)
        high = max(high, other.y + other.height)
    reach = max(origin_y - low, high - origin_y)
    limit = reach // step + 3
    for index in range(limit * 2 + 1):
        if index == 0:
            y = origin_y
        else:
            slot = (index + 1) // 2
            sign = 1 if index % 2 == 1 else -1
            y = origin_y + sign * slot * step
        rect = CanvasRect(x, y, size.width, size.height)
        if not _hits_any(rect, taken):
            return rect, _leader(rect, target, side), side
    rect = CanvasRect(x, high + 2, size.width, size.height)
    return rect, _leader(rect, target, side), side


class _Buckets:
    def __init__(self, content: Sequence[Obstacle]) -> None:
        self._cells: Dict[Tuple[int, int], List[Obstacle]] = {}
        for obstacle in content:
            rect = obstacle.rect
            if rect.width <= 0 or rect.height <= 0:
                continue
            for cell in _cover(rect):
                self._cells.setdefault(cell, []).append(obstacle)

    def blocked(self, rect: CanvasRect, exempt: FrozenSet[NodeId]) -> bool:
        seen = set()
        for cell in _cover(rect):
            for obstacle in self._cells.get(cell, ()):
                if obstacle.node in exempt or obstacle.node in seen:
                    continue
                seen.add(obstacle.node)
                if _closed(rect, obstacle.rect):
                    return True
        return False


def _cover(rect: CanvasRect) -> Tuple[Tuple[int, int], ...]:
    if rect.width <= 0 or rect.height <= 0:
        return ()
    x0 = rect.x // _CELL
    y0 = rect.y // _CELL
    x1 = (rect.x + rect.width - 1) // _CELL
    y1 = (rect.y + rect.height - 1) // _CELL
    return tuple((x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1))


def _hits_any(rect: CanvasRect, taken: Sequence[CanvasRect]) -> bool:
    return any(_closed(rect, other) for other in taken)


def _closed(a: CanvasRect, b: CanvasRect) -> bool:
    return (
        a.x <= b.x + b.width
        and b.x <= a.x + a.width
        and a.y <= b.y + b.height
        and b.y <= a.y + a.height
    )


def _leader(rect: CanvasRect, target: CanvasRect, side: Side) -> Leader:
    mid_y = rect.y + rect.height // 2
    target_y = target.y + target.height // 2
    if side == "right":
        return Leader(CanvasPoint(rect.x, mid_y), CanvasPoint(target.x + target.width, target_y))
    return Leader(CanvasPoint(rect.x + rect.width, mid_y), CanvasPoint(target.x, target_y))
