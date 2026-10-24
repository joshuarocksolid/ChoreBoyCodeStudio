"""8 px grid in form pixels. Shift turns it off for moves, resizes, and page edges."""

from __future__ import annotations

from typing import Tuple

from app.features.form_builder.engine.ui4.values import RectValue
from app.features.form_builder.qtside.canvas.core.space import Compass, FormPoint, Size

GRID = 8

_WEST = frozenset({"w", "nw", "sw"})
_EAST = frozenset({"e", "ne", "se"})
_NORTH = frozenset({"n", "nw", "ne"})
_SOUTH = frozenset({"s", "sw", "se"})


def snap_move(origin: RectValue, delta: FormPoint, snap: bool) -> Tuple[int, int]:
    """Delta that lands the top-left on the grid. Every node in a move uses it."""
    return (
        _coord(origin.x + delta.x, snap) - origin.x,
        _coord(origin.y + delta.y, snap) - origin.y,
    )


def snap_resize(origin: RectValue, handle: Compass, delta: FormPoint, snap: bool) -> RectValue:
    left = origin.x
    top = origin.y
    right = origin.x + origin.width
    bottom = origin.y + origin.height
    if handle in _WEST:
        left = _coord(left + delta.x, snap)
    if handle in _EAST:
        right = _coord(right + delta.x, snap)
    if handle in _NORTH:
        top = _coord(top + delta.y, snap)
    if handle in _SOUTH:
        bottom = _coord(bottom + delta.y, snap)
    if right <= left:
        if handle in _WEST and handle not in _EAST:
            left = right - 1
        else:
            right = left + 1
    if bottom <= top:
        if handle in _NORTH and handle not in _SOUTH:
            top = bottom - 1
        else:
            bottom = top + 1
    return RectValue(left, top, right - left, bottom - top)


def snap_page(origin: Size, handle: Compass, delta: FormPoint, snap: bool, minimum: Size) -> Size:
    width = origin.width
    height = origin.height
    if handle in _EAST:
        width = _coord(origin.width + delta.x, snap)
    if handle in _SOUTH:
        height = _coord(origin.height + delta.y, snap)
    return Size(max(width, minimum.width, 1), max(height, minimum.height, 1))


def _coord(value: float, snap: bool) -> int:
    if snap:
        return int(round(value / GRID) * GRID)
    return int(round(value))
