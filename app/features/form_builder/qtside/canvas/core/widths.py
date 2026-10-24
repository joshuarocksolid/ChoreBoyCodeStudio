"""Where the two live copies sit. Both use one zoom factor."""

from __future__ import annotations

from dataclasses import dataclass

from app.features.form_builder.qtside.canvas.core.space import (
    GUTTERS,
    CanvasPoint,
    CanvasSize,
    Size,
)

WIDE_DEFAULT = 1366
_GAP = 32
_LABEL = 22


@dataclass(frozen=True)
class WidthArrangement:
    """Page origins in canvas pixels, before the view scrolls."""

    narrow_at: CanvasPoint
    wide_at: CanvasPoint
    scene: CanvasSize
    stacked: bool


def arrange_widths(
    narrow: Size,
    wide: Size,
    factor: float,
    viewport: CanvasSize,
    banner_push: int,
) -> WidthArrangement:
    """Side by side when both fit. Otherwise narrow above wide."""
    scale = factor if factor > 0 else 1.0
    narrow_w = max(1, int(round(narrow.width * scale)))
    narrow_h = max(1, int(round(narrow.height * scale)))
    wide_w = max(1, int(round(wide.width * scale)))
    wide_h = max(1, int(round(wide.height * scale)))
    side_by_side = narrow_w + _GAP + wide_w + GUTTERS.left + GUTTERS.right <= viewport.width
    if side_by_side:
        block_w = narrow_w + _GAP + wide_w
        block_h = max(narrow_h, wide_h)
    else:
        block_w = max(narrow_w, wide_w)
        block_h = narrow_h + _LABEL + _GAP + wide_h
    if block_w + GUTTERS.left + GUTTERS.right <= viewport.width:
        left = (viewport.width - block_w) // 2
    else:
        left = GUTTERS.left
    top = GUTTERS.top + max(0, banner_push)
    narrow_at = CanvasPoint(left, top)
    if side_by_side:
        wide_at = CanvasPoint(left + narrow_w + _GAP, top)
    else:
        wide_at = CanvasPoint(left, top + narrow_h + _LABEL + _GAP)
    scene = CanvasSize(
        max(viewport.width, wide_at.x + wide_w + GUTTERS.right),
        max(viewport.height, wide_at.y + wide_h + GUTTERS.bottom, top + block_h + GUTTERS.bottom),
    )
    return WidthArrangement(narrow_at, wide_at, scene, not side_by_side)
