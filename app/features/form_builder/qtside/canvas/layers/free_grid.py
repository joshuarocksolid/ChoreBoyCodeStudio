"""The dot grid inside containers that have no layout (UX-FSET-006).

The state is a ``FreeGrid`` (the form's step in form pixels), switched on by
``integration/workbench_ext/free_grid.py`` while "Show grid" is on and the form
has such a container. The dots follow the step, skip the places a child
covers, and are left out when they would be closer than 4 screen pixels.
High contrast has no dots, as the backdrop has none.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Hashable, List, Tuple

from app.features.form_builder.qtside.canvas.core.overlay import LayerItem, LayerOutput
from app.features.form_builder.qtside.canvas.layers import CanvasLayer
from app.features.form_builder.qtside.theme.overlay import CanvasPalette
from app.qt.QtCore import QPointF, QRectF
from app.qt.QtGui import QColor, QPainter, QPen

NAME = "free_grid"
#: Closer than this on screen, dots are noise.
MIN_GAP_PX = 4.0
#: No container paints more dots than this.
MAX_DOTS = 8000

Hole = Tuple[int, int, int, int]


@dataclass(frozen=True)
class FreeGrid:
    across: int
    down: int


def register(registry: object) -> None:
    add = getattr(registry, "add")
    add(CanvasLayer(NAME, build, paint, order=20))


def build(static: object, inputs: object, state: Hashable) -> LayerOutput:
    if not isinstance(state, FreeGrid):
        return LayerOutput()
    document = getattr(inputs, "document")
    view = getattr(static, "view")
    factor = float(getattr(view, "factor", 1.0) or 1.0)
    across = state.across * factor
    down = state.down * factor
    if across < MIN_GAP_PX or down < MIN_GAP_PX:
        return LayerOutput()
    # A title strip is a second obstacle of the same node: only the body counts.
    shown = {obstacle.node: obstacle.rect for obstacle in getattr(static, "content") if not obstacle.band}
    whole = {obstacle.node: obstacle.rect for obstacle in getattr(static, "placed") if not obstacle.band}
    items: List[LayerItem] = []
    for node_id in getattr(static, "unlaid"):
        clipped = shown.get(node_id)
        origin = whole.get(node_id)
        node = document.get(node_id)
        if clipped is None or origin is None or node is None:
            continue
        holes: List[Hole] = []
        for child in getattr(node, "child_widgets", ()):
            found = whole.get(child.id)
            if found is not None:
                holes.append((found.x, found.y, found.width, found.height))
        data = (across, down, origin.x, origin.y, tuple(holes))
        items.append(LayerItem(rect=clipped, role="layout_faint", layer=NAME, data=data))
    return LayerOutput(tuple(items))


def _color(text: str) -> QColor:
    text = text.lstrip("#")
    if len(text) == 8:
        return QColor(int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16), int(text[6:8], 16))
    return QColor("#" + text)


def paint(painter: QPainter, item: LayerItem, palette: CanvasPalette) -> None:
    data = item.data
    if not isinstance(data, tuple) or len(data) != 5 or not palette.backdrop.dot:
        return
    across, down, left, top, holes = data
    rect = item.rect
    color = _color(palette.overlay.layout_faint)
    color.setAlpha(170)
    pen = QPen(color)
    pen.setWidthF(1.5)
    painter.save()
    try:
        painter.setPen(pen)
        painter.setClipRect(QRectF(rect.x, rect.y, rect.width, rect.height))
        count = 0
        y = float(top) + down
        while y < rect.y + rect.height and count < MAX_DOTS:
            x = float(left) + across
            while x < rect.x + rect.width and count < MAX_DOTS:
                if x >= rect.x and y >= rect.y and not _covered(x, y, holes):
                    painter.drawPoint(QPointF(x, y))
                    count += 1
                x += across
            y += down
    finally:
        painter.restore()


def _covered(x: float, y: float, holes: Tuple[Hole, ...]) -> bool:
    for hx, hy, hw, hh in holes:
        if hx <= x < hx + hw and hy <= y < hy + hh:
            return True
    return False
