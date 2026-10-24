"""Chip and badge placement. A pure function of rectangles.

A seat is a corner inside the viewport, or a gutter outside the page.
A corner outside the viewport is skipped. A gutter leader is horizontal
and stops before other content. A required chip that fits the viewport
still gets a clear seat when the leader cannot reach its widget.
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
    #: The selection chip. It is seated even when the only room overlaps content.
    required: bool = False


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
            seat = _gutter_seat(request, buckets, taken, page, viewport, True)
        if seat is None and request.required:
            seat = _gutter_seat(request, buckets, taken, page, viewport, False)
        if seat is None and request.required:
            seat = _clear_viewport_corner(request, buckets, taken, viewport)
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
    require_leader: bool,
) -> Optional[GutterSeat]:
    size = request.size
    if size.width > viewport.width or size.height > viewport.height:
        return None
    preferred = _preferred_side(request.target, page)
    other: Side = "left" if preferred == "right" else "right"
    centred = _centred_y(request.target, size.height)
    for side in (preferred, other):
        found = _gutter_at(request, buckets, taken, page, viewport, side, centred, require_leader)
        if found is not None:
            return found
    for side in (preferred, other):
        for y in _span_ys(request.target, size.height):
            if y == centred:
                continue
            found = _gutter_at(request, buckets, taken, page, viewport, side, y, require_leader)
            if found is not None:
                return found
    return None


def _gutter_at(
    request: ChipRequest,
    buckets: "_Buckets",
    taken: Sequence[CanvasRect],
    page: CanvasRect,
    viewport: CanvasRect,
    side: Side,
    y: int,
    require_leader: bool,
) -> Optional[GutterSeat]:
    rect = CanvasRect(_natural_x(page, request.size, side), y, request.size.width, request.size.height)
    if not _clear(rect, viewport, buckets, request.exempt, taken):
        return None
    leader = _safe_leader(rect, request.target, side, buckets, request.exempt)
    if require_leader and not _reaches(leader, request.target, side):
        return None
    return GutterSeat(request.key, rect, leader, side)


def _clear_viewport_corner(
    request: ChipRequest,
    buckets: "_Buckets",
    taken: Sequence[CanvasRect],
    viewport: CanvasRect,
) -> Optional[CornerSeat]:
    """A clear corner of the viewport. Used when both gutters are off screen."""
    size = request.size
    if size.width > viewport.width or size.height > viewport.height:
        return None
    right = viewport.x + viewport.width - size.width
    bottom = viewport.y + viewport.height - size.height
    spots: Tuple[Tuple[int, int, Corner], ...] = (
        (viewport.x, viewport.y, "above_left"),
        (viewport.x, bottom, "below_left"),
        (right, viewport.y, "above_right"),
        (right, bottom, "below_right"),
    )
    for x, y, corner in spots:
        rect = CanvasRect(x, y, size.width, size.height)
        if _clear(rect, viewport, buckets, request.exempt, taken):
            return CornerSeat(request.key, rect, corner)
    return None


def _preferred_side(target: CanvasRect, page: CanvasRect) -> Side:
    target_mid = target.x + target.width / 2.0
    page_mid = page.x + page.width / 2.0
    if target_mid >= page_mid:
        return "right"
    return "left"


def _natural_x(page: CanvasRect, size: CanvasSize, side: Side) -> int:
    if side == "right":
        return page.x + page.width + GUTTER_INSET
    return page.x - GUTTER_INSET - size.width


def _centred_y(target: CanvasRect, height: int) -> int:
    return target.y + (target.height - height) // 2


def _span_ys(target: CanvasRect, height: int) -> Tuple[int, ...]:
    """Chip tops whose box overlaps the target and contains its vertical centre."""
    centre = target.y + target.height // 2
    if height >= target.height:
        return (_centred_y(target, height),)
    low = max(target.y - height + 1, centre - height + 1)
    high = min(target.y + target.height - 1, centre)
    if low > high:
        return (_centred_y(target, height),)
    origin = _centred_y(target, height)
    if origin < low:
        origin = low
    if origin > high:
        origin = high
    step = max(1, height // 2)
    values = [origin]
    down = origin + step
    up = origin - step
    while down <= high or up >= low:
        if down <= high:
            values.append(down)
            down += step
        if up >= low:
            values.append(up)
            up -= step
    return tuple(values)


def _safe_leader(
    rect: CanvasRect,
    target: CanvasRect,
    side: Side,
    buckets: "_Buckets",
    exempt: FrozenSet[NodeId],
) -> Leader:
    """Horizontal leader, shortened so it does not enter another widget."""
    full = _leader(rect, target, side)
    if _segment_clear(full, buckets, exempt):
        return full
    start = full.start.x
    end = full.end.x
    step = 1 if end >= start else -1
    y = full.start.y
    best = start
    reached = start
    while reached != end:
        reached += step
        if not _segment_clear(Leader(CanvasPoint(start, y), CanvasPoint(reached, y)), buckets, exempt):
            break
        best = reached
    return Leader(CanvasPoint(start, y), CanvasPoint(best, y))


def _reaches(leader: Leader, target: CanvasRect, side: Side) -> bool:
    if side == "right":
        return leader.end.x >= target.x + target.width
    return leader.end.x <= target.x


def _segment_clear(leader: Leader, buckets: "_Buckets", exempt: FrozenSet[NodeId]) -> bool:
    left = min(leader.start.x, leader.end.x) + 1
    right = max(leader.start.x, leader.end.x) - 1
    if right <= left:
        return True
    probe = CanvasRect(left, leader.start.y, right - left, 1)
    return not buckets.blocked(probe, exempt)


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
    """The centred gutter outside ``page``. ``taken`` does not pull it onto the page."""
    del taken
    side = _preferred_side(target, page)
    rect = CanvasRect(_natural_x(page, size, side), _centred_y(target, size.height), size.width, size.height)
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
    target_y = target.y + target.height // 2
    if side == "right":
        return Leader(CanvasPoint(rect.x, target_y), CanvasPoint(target.x + target.width, target_y))
    return Leader(CanvasPoint(rect.x + rect.width, target_y), CanvasPoint(target.x, target_y))
