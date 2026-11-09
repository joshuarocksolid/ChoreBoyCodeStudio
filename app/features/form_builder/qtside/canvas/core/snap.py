"""The grid in form pixels. Shift turns it off for moves and page edges.

A move in a free container uses the form's step (UX-FSET-006): 8 by 8 unless
the file's grid says otherwise, and no snapping when the file turns "Snap to
grid" off. Callers that have no document keep the 8 px default. The page
edges always use 8 px.

Free resize snaps through its knob rule in ``engine.query.direct``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from app.features.form_builder.engine.commands.catalog_ext.form_fields import GRID_STEP_DEFAULT, form_grid
from app.features.form_builder.engine.query.direct import grid_coord
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.values import RectValue
from app.features.form_builder.qtside.canvas.core.space import Compass, FormPoint, Size

_EAST = frozenset({"e", "ne", "se"})
_SOUTH = frozenset({"s", "sw", "se"})


@dataclass(frozen=True)
class GridStep:
    across: int = GRID_STEP_DEFAULT
    down: int = GRID_STEP_DEFAULT
    #: False when the form turned "Snap to grid" off: drags land on whole pixels.
    snap: bool = True

    def nudge(self, shift: bool) -> Tuple[int, int]:
        """The distance of one Alt+arrow press along each axis: a step, or 1 px with Shift."""
        return (1, 1) if shift else (self.across, self.down)


DEFAULT_STEP = GridStep()


def grid_step(document: UiDocument) -> GridStep:
    """The form's grid. A form with no grid settings gets the 8 px default."""
    grid = form_grid(document)
    return GridStep(grid.across, grid.down, grid.snap)


def _coord(value: float, on: bool, step: int) -> int:
    if on and step > 0:
        return int(round(value / step) * step)
    return int(round(value))


def snap_move(origin: RectValue, delta: FormPoint, snap: bool, step: Optional[GridStep] = None) -> Tuple[int, int]:
    """Delta that lands the top-left on the grid. Every node in a move uses it."""
    grid = step or DEFAULT_STEP
    on = snap and grid.snap
    return (
        _coord(origin.x + delta.x, on, grid.across) - origin.x,
        _coord(origin.y + delta.y, on, grid.down) - origin.y,
    )


def snap_page(origin: Size, handle: Compass, delta: FormPoint, snap: bool, minimum: Size) -> Size:
    width = origin.width
    height = origin.height
    if handle in _EAST:
        width = grid_coord(origin.width + delta.x, snap)
    if handle in _SOUTH:
        height = grid_coord(origin.height + delta.y, snap)
    return Size(max(width, minimum.width, 1), max(height, minimum.height, 1))
