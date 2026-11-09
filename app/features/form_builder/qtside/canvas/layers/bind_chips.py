"""Column name on a bound field while a Data tab is current (UX-BIND-003)."""

from __future__ import annotations

from typing import Hashable

from app.features.form_builder.qtside.canvas.core.frame import Chip
from app.features.form_builder.qtside.canvas.core.overlay import LayerOutput
from app.features.form_builder.qtside.canvas.core.space import CanvasRect
from app.features.form_builder.qtside.canvas.layers import CanvasLayer
from app.features.form_builder.qtside.data_panel.model import bind_text

NAME = "bind_chips"


def register(registry: object) -> None:
    getattr(registry, "add")(CanvasLayer(NAME, build, None, order=76))


def build(static: object, inputs: object, state: Hashable) -> LayerOutput:
    del state
    document = getattr(inputs, "document", None)
    if document is None:
        return LayerOutput()
    from app.features.form_builder.engine.data.publish import warnings_of

    warnings = warnings_of(document)
    measure = getattr(inputs, "measure", None)
    items = []
    for obstacle in getattr(static, "placed", ()) or ():
        if not document.contains(obstacle.node):
            continue
        node = document.node(obstacle.node)
        column = bind_text(node)
        if not column:
            continue
        measured = measure(column) if callable(measure) else None
        width = int(measured) + 12 if isinstance(measured, (int, float)) else max(36, 7 * len(column) + 12)
        rect = obstacle.rect
        height = min(16, rect.height) if rect.height else 16
        width = min(width, rect.width) if rect.width else width
        if width <= 0 or height <= 0:
            continue
        chip = CanvasRect(rect.x, rect.y + rect.height - height, width, height)
        role = "tab" if obstacle.node in warnings else "backdrop_faint"
        items.append(Chip(chip, column, role, None, tip=warnings.get(obstacle.node, "")))
    return LayerOutput(tuple(items))
