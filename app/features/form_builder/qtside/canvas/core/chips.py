"""Chip and badge placement. A pure function of rectangles.

Seats, in order: a corner above or below the target; a seat beside it on its
row (adjacent, or further along with a horizontal leader that stops at the
target); the page gutter with a horizontal leader. Every seat is inside the
viewport and clear of non-ancestor content and of earlier seats. The selection
chip of a widget in view always gets a seat: its last resort is the dock, a
strip of view chrome along the top of the canvas, with the chip at the
target's x. A widget scrolled fully out of view has no chip.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Hashable, List, Literal, Optional, Sequence, Tuple, Union

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.qtside.canvas.core.space import CanvasPoint, CanvasRect, CanvasSize

Corner = Literal[
    "above_left", "below_left", "above_right", "below_right", "inside_top_right", "inside_bottom_right"
]
Side = Literal["left", "right"]

LABEL_CORNERS: Tuple[Corner, ...] = ("above_left", "below_left", "above_right", "below_right")
BADGE_CORNERS: Tuple[Corner, ...] = ("above_right", "above_left")
#: "No layout" marks its own frame. Inside seats need the container in ``exempt``.
BARE_CORNERS: Tuple[Corner, ...] = LABEL_CORNERS + ("inside_top_right", "inside_bottom_right")

CHIP_GAP = 7
GUTTER_INSET = 4
#: Step of the scan along the target's row, in canvas pixels.
ROW_STEP = 8
_CELL = 64


@dataclass(frozen=True)
class ChipRequest:
    key: Hashable
    target: CanvasRect
    size: CanvasSize
    corners: Tuple[Corner, ...]
    #: Ancestors the chip may overlap. The target itself is never exempt.
    exempt: FrozenSet[NodeId]
    #: The selection chip. When nothing else is clear it goes in the dock.
    required: bool = False
    #: Only seats clear of the page, so a page-edge number reads as gutter chrome.
    outside: bool = False
    #: Corner seats only. Badges discard a beside or gutter seat, so they skip that scan.
    corners_only: bool = False


@dataclass(frozen=True)
class Obstacle:
    node: NodeId
    rect: CanvasRect
    #: A title strip. Descendants may cover the ancestor's body, never this band.
    band: bool = False


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
class BesideSeat:
    """On the target's row. ``leader`` is None when the chip touches the target gap."""

    key: Hashable
    rect: CanvasRect
    side: Side
    leader: Optional[Leader]


@dataclass(frozen=True)
class GutterSeat:
    key: Hashable
    rect: CanvasRect
    leader: Leader
    side: Side


@dataclass(frozen=True)
class DockSeat:
    """In the dock strip, which is view chrome and covers no content."""

    key: Hashable
    rect: CanvasRect
    leader: Optional[Leader]


ChipSeat = Union[CornerSeat, BesideSeat, GutterSeat, DockSeat]


def place_chips(
    requests: Sequence[ChipRequest],
    content: Sequence[Obstacle],
    fixed: Sequence[CanvasRect],
    page: CanvasRect,
    viewport: CanvasRect,
    dock: Optional[CanvasRect] = None,
) -> Tuple[ChipSeat, ...]:
    """Seats that fit. Earlier requests keep the seats they take.

    ``dock`` is the chrome strip for a required chip with no other seat. None
    uses a strip along the top of ``viewport``.
    """
    buckets = _Buckets(content)
    taken: List[CanvasRect] = list(fixed)
    seats: List[ChipSeat] = []
    for request in requests:
        # The page joins the fixed rects, ahead of the chips, so leaders may still cross it.
        walls = [page] + taken if request.outside else taken
        count = len(fixed) + (1 if request.outside else 0)
        seat: Optional[ChipSeat] = _corner_seat(request, buckets, walls, viewport)
        if seat is None and not request.corners_only:
            seat = _beside_seat(request, buckets, walls, count, viewport)
        if seat is None and not request.corners_only:
            seat = _gutter_seat(request, buckets, walls, count, page, viewport)
        if seat is None and request.required and request.target.intersects(viewport):
            seat = _dock_seat(request, buckets, walls, count, viewport, dock)
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
    """A corner, slid along the target's edge into the viewport when needed."""
    target = request.target
    for corner in request.corners:
        rect = corner_rect(target, request.size, corner)
        if not _inside(rect, viewport):
            x = _clamp(rect.x, viewport.x, viewport.x + viewport.width - rect.width)
            if x >= target.x + target.width or x + rect.width <= target.x:
                continue
            rect = CanvasRect(x, rect.y, rect.width, rect.height)
        if not _clear(rect, viewport, buckets, request.exempt, taken):
            continue
        return CornerSeat(request.key, rect, corner)
    return None


def _beside_seat(
    request: ChipRequest,
    buckets: "_Buckets",
    taken: Sequence[CanvasRect],
    fixed_count: int,
    viewport: CanvasRect,
) -> Optional[BesideSeat]:
    """Right then left of the target, nearest first, while the leader stays clear."""
    target = request.target
    size = request.size
    if size.width > viewport.width or size.height > viewport.height:
        return None
    for y in _row_ys(target, size.height, viewport):
        leader_y = _clamp(y + size.height // 2, target.y, target.y + target.height - 1)
        for side in ("right", "left"):
            found = _scan_row(request, buckets, taken, fixed_count, viewport, side, y, leader_y)
            if found is not None:
                return found
    return None


def _scan_row(
    request: ChipRequest,
    buckets: "_Buckets",
    taken: Sequence[CanvasRect],
    fixed_count: int,
    viewport: CanvasRect,
    side: Side,
    y: int,
    leader_y: int,
) -> Optional[BesideSeat]:
    target = request.target
    width = request.size.width
    if side == "right":
        edge = target.x + target.width
        x = edge + CHIP_GAP
        limit = viewport.x + viewport.width - width
        step = ROW_STEP
    else:
        edge = target.x
        x = edge - CHIP_GAP - width
        limit = viewport.x
        step = -ROW_STEP
    near = x
    while (x <= limit) if side == "right" else (x >= limit):
        rect = CanvasRect(x, y, width, request.size.height)
        leader: Optional[Leader] = None
        if x != near:
            start = x if side == "right" else x + width
            leader = Leader(CanvasPoint(start, leader_y), CanvasPoint(edge, leader_y))
            if not _leader_clear(leader, buckets, request.exempt, taken[fixed_count:]):
                return None
        if _clear(rect, viewport, buckets, request.exempt, taken):
            return BesideSeat(request.key, rect, side, leader)
        x += step
    return None


def _row_ys(target: CanvasRect, height: int, viewport: CanvasRect) -> Tuple[int, ...]:
    """Centred on the target, then centred on its visible part."""
    centred = _centred_y(target, height)
    top = max(target.y, viewport.y)
    bottom = min(target.y + target.height, viewport.y + viewport.height)
    ys = [centred]
    if bottom > top:
        visible = top + (bottom - top - height) // 2
        visible = _clamp(visible, viewport.y, viewport.y + viewport.height - height)
        if visible not in ys:
            ys.append(visible)
    return tuple(ys)


def _gutter_seat(
    request: ChipRequest,
    buckets: "_Buckets",
    taken: Sequence[CanvasRect],
    fixed_count: int,
    page: CanvasRect,
    viewport: CanvasRect,
) -> Optional[GutterSeat]:
    size = request.size
    if size.width > viewport.width or size.height > viewport.height:
        return None
    preferred = _preferred_side(request.target, page)
    other: Side = "left" if preferred == "right" else "right"
    centred = _centred_y(request.target, size.height)
    for side in (preferred, other):
        found = _gutter_at(request, buckets, taken, fixed_count, page, viewport, side, centred)
        if found is not None:
            return found
    for side in (preferred, other):
        for y in _span_ys(request.target, size.height):
            if y == centred:
                continue
            found = _gutter_at(request, buckets, taken, fixed_count, page, viewport, side, y)
            if found is not None:
                return found
    return None


def _gutter_at(
    request: ChipRequest,
    buckets: "_Buckets",
    taken: Sequence[CanvasRect],
    fixed_count: int,
    page: CanvasRect,
    viewport: CanvasRect,
    side: Side,
    y: int,
) -> Optional[GutterSeat]:
    rect = CanvasRect(_natural_x(page, request.size, side), y, request.size.width, request.size.height)
    if not _clear(rect, viewport, buckets, request.exempt, taken):
        return None
    leader = _leader(rect, request.target, side)
    if not _leader_clear(leader, buckets, request.exempt, taken[fixed_count:]):
        return None
    return GutterSeat(request.key, rect, leader, side)


def _dock_seat(
    request: ChipRequest,
    buckets: "_Buckets",
    taken: Sequence[CanvasRect],
    fixed_count: int,
    viewport: CanvasRect,
    dock: Optional[CanvasRect],
) -> Optional[DockSeat]:
    """At the target's x, slid off earlier chips when there is room.

    It does not fail while the view has its caption strip. Without one the
    top of the viewport stands in only where no content is under the chip.
    """
    size = request.size
    target = request.target
    strip = dock
    chrome = strip is not None and strip.width > 0 and strip.height > 0
    if strip is None or not chrome:
        strip = CanvasRect(viewport.x, viewport.y, viewport.width, size.height + 4)
    low = max(strip.x, viewport.x)
    high = min(strip.x + strip.width, viewport.x + viewport.width) - size.width
    if high < low:
        high = low
    y = strip.y + (strip.height - size.height) // 2
    y = _clamp(y, viewport.y, viewport.y + viewport.height - size.height)
    wanted = _clamp(target.x, low, high)
    # The dock paints over the chrome under it (the pinned page name), so only
    # chips placed earlier push it along.
    others = list(taken[fixed_count:])
    spots = [wanted]
    for rect in others:
        spots.append(_clamp(rect.x + rect.width + GUTTER_INSET, low, high))
        spots.append(_clamp(rect.x - GUTTER_INSET - size.width, low, high))
    spots.sort(key=lambda x: abs(x - wanted))
    chosen = wanted
    for x in spots:
        if not _hits_any(CanvasRect(x, y, size.width, size.height), others):
            chosen = x
            break
    rect = CanvasRect(chosen, y, size.width, size.height)
    if not chrome and buckets.blocked(rect, request.exempt):
        return None
    leader = _dock_leader(rect, target, buckets, request.exempt, taken[fixed_count:])
    return DockSeat(request.key, rect, leader)


def _dock_leader(
    rect: CanvasRect,
    target: CanvasRect,
    buckets: "_Buckets",
    exempt: FrozenSet[NodeId],
    chips: Sequence[CanvasRect],
) -> Optional[Leader]:
    """A vertical leader to the target's top, only when nothing is in the way."""
    left = max(rect.x, target.x) + 1
    right = min(rect.x + rect.width, target.x + target.width) - 1
    top = rect.y + rect.height
    if right < left or target.y <= top:
        return None
    x = (left + right) // 2
    if target.y - top > 2:
        probe = CanvasRect(x, top + 1, 1, target.y - top - 2)
        if buckets.blocked(probe, exempt) or _hits_any(probe, chips):
            return None
    return Leader(CanvasPoint(x, top), CanvasPoint(x, target.y))


def _clamp(value: int, low: int, high: int) -> int:
    if high < low:
        return low
    return max(low, min(value, high))


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


def _leader_clear(
    leader: Leader, buckets: "_Buckets", exempt: FrozenSet[NodeId], taken: Sequence[CanvasRect]
) -> bool:
    """A horizontal leader crosses no other content and no other chip.

    Handles and chrome (the fixed rects) may sit on a leader.
    """
    left = min(leader.start.x, leader.end.x) + 1
    right = max(leader.start.x, leader.end.x) - 1
    if right <= left:
        return True
    probe = CanvasRect(left, leader.start.y, right - left, 1)
    return not buckets.blocked(probe, exempt) and not _hits_any(probe, taken)


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
    if corner == "inside_top_right":
        return CanvasRect(
            target.x + target.width - GUTTER_INSET - size.width,
            target.y + GUTTER_INSET,
            size.width,
            size.height,
        )
    if corner == "inside_bottom_right":
        return CanvasRect(
            target.x + target.width - GUTTER_INSET - size.width,
            target.y + target.height - GUTTER_INSET - size.height,
            size.width,
            size.height,
        )
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
                if obstacle.band:
                    if _closed(rect, obstacle.rect):
                        return True
                    continue
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
