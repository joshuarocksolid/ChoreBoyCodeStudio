"""The corner tag of a widget that uses your own class, and its hit area (UX-CUST-007, ``ov.own_class``).

A selected or hovered widget whose class the form declares from a Python module
gets a 1 px outline and a 4 px tag in the ``ov.layout`` colour (violet in
high contrast). A widget of your own class that is smaller than 80 x 24 px on
the canvas gets a hit target of that size, so it can be picked. The target is
never saved. Nothing here reads the module.
"""

from __future__ import annotations

from typing import Hashable, List, Set, Tuple

from app.features.form_builder.engine.project.custom_widgets import module_for_header
from app.features.form_builder.engine.ui4.nodes import CustomWidgetNode, WidgetNode
from app.features.form_builder.engine.ui4.schema import HeaderDecl
from app.features.form_builder.qtside.canvas.core.frame import OnWidget, Target
from app.features.form_builder.qtside.canvas.core.gesture import Idle
from app.features.form_builder.qtside.canvas.core.overlay import LayerItem, LayerOutput
from app.features.form_builder.qtside.canvas.core.space import CanvasRect
from app.features.form_builder.qtside.canvas.core.structure import positioning_of
from app.features.form_builder.qtside.canvas.layers import CanvasLayer
from app.features.form_builder.qtside.theme.overlay import CanvasPalette
from app.qt.QtCore import QRectF
from app.qt.QtGui import QColor, QPainter, QPen

NAME = "own_class"
MIN_WIDTH = 80
MIN_HEIGHT = 24
TAG_SIZE = 4
TAG_LENGTH = 16


def register(registry: object) -> None:
    add = getattr(registry, "add")
    add(CanvasLayer(NAME, build, paint, order=70))


def own_classes(document: object) -> Set[str]:
    """Class names the form declares with a Python module header."""
    found: Set[str] = set()
    for node in document.ui.children("customwidgets"):  # type: ignore[attr-defined]
        if not isinstance(node, CustomWidgetNode) or not node.class_name:
            continue
        header = node.field("header")
        if isinstance(header, HeaderDecl) and module_for_header(header.text):
            found.add(node.class_name)
    return found


def build(static: object, inputs: object, state: Hashable) -> LayerOutput:
    del state
    document = getattr(inputs, "document")
    names = own_classes(document)
    if not names:
        return LayerOutput()
    selected = set(getattr(getattr(inputs, "selection"), "ids", ()))
    gesture = getattr(inputs, "gesture")
    hovered = gesture.hover if isinstance(gesture, Idle) else None
    items: List[LayerItem] = []
    targets: List[Tuple[CanvasRect, Target]] = []
    for obstacle in getattr(static, "placed"):
        node = document.get(obstacle.node)
        if not isinstance(node, WidgetNode) or node.class_name not in names:
            continue
        rect = obstacle.rect
        if rect.width < MIN_WIDTH or rect.height < MIN_HEIGHT:
            grown = CanvasRect(rect.x, rect.y, max(rect.width, MIN_WIDTH), max(rect.height, MIN_HEIGHT))
            targets.append((grown, OnWidget(node.id, positioning_of(document, node.id), "widget")))
        if node.id in selected or node.id == hovered:
            items.append(LayerItem(rect=rect, role="layout", layer=NAME, data=(rect.width, rect.height)))
    return LayerOutput(tuple(items), tuple(targets))


def _color(text: str) -> QColor:
    text = text.lstrip("#")
    if len(text) == 8:
        return QColor(int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16), int(text[6:8], 16))
    return QColor("#" + text)


def paint(painter: QPainter, item: LayerItem, palette: CanvasPalette) -> None:
    over = palette.overlay
    ink = _color(over.layout)
    box = QRectF(item.rect.x, item.rect.y, item.rect.width, item.rect.height)
    painter.save()
    try:
        painter.setPen(QPen(ink, max(1.0, over.min_stroke)))
        painter.setBrush(QColor(0, 0, 0, 0))
        painter.drawRect(box.adjusted(0.5, 0.5, -0.5, -0.5))
        painter.fillRect(QRectF(box.x(), box.y(), min(TAG_LENGTH, box.width()), TAG_SIZE), ink)
    finally:
        painter.restore()
