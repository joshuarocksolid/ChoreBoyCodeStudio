"""8 px grid in form pixels. Shift turns it off for moves and page edges.

Free resize snaps through its knob rule in ``engine.query.direct``.
"""

from __future__ import annotations

from typing import Tuple

from app.features.form_builder.engine.query.direct import grid_coord
from app.features.form_builder.engine.ui4.values import RectValue
from app.features.form_builder.qtside.canvas.core.space import Compass, FormPoint, Size

_EAST = frozenset({"e", "ne", "se"})
_SOUTH = frozenset({"s", "sw", "se"})


def snap_move(origin: RectValue, delta: FormPoint, snap: bool) -> Tuple[int, int]:
    """Delta that lands the top-left on the grid. Every node in a move uses it."""
    return (
        grid_coord(origin.x + delta.x, snap) - origin.x,
        grid_coord(origin.y + delta.y, snap) - origin.y,
    )


def snap_page(origin: Size, handle: Compass, delta: FormPoint, snap: bool, minimum: Size) -> Size:
    width = origin.width
    height = origin.height
    if handle in _EAST:
        width = grid_coord(origin.width + delta.x, snap)
    if handle in _SOUTH:
        height = grid_coord(origin.height + delta.y, snap)
    return Size(max(width, minimum.width, 1), max(height, minimum.height, 1))
