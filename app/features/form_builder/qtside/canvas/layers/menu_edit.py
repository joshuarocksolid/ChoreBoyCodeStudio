"""The menu-edit layer: "Type here" boxes, open menus drawn on the page, the in-place editor (UX-MAIN-003, 006, 007, 015).

The state is a ``PaintState`` in form pixels, built by ``qtside/actions/glue.py``
from the realized bars and toolbars. Nothing here is realized, previewed or saved.
"""

from __future__ import annotations

from typing import Hashable

from app.features.form_builder.engine.query.hit_index import Rect
from app.features.form_builder.qtside.actions.paint_model import PaintItem, PaintState
from app.features.form_builder.qtside.canvas.core.overlay import LayerItem, LayerOutput
from app.features.form_builder.qtside.canvas.layers import CanvasLayer
from app.features.form_builder.qtside.theme.overlay import CanvasPalette
from app.qt.QtCore import QRectF, Qt
from app.qt.QtGui import QColor, QFont, QPainter, QPen

NAME = "menu_edit"


def register(registry: object) -> None:
    add = getattr(registry, "add")
    add(CanvasLayer(NAME, build, paint, order=60))


def build(static: object, inputs: object, state: Hashable) -> LayerOutput:
    del inputs
    if not isinstance(state, PaintState) or not state.items:
        return LayerOutput()
    view = getattr(static, "view")
    items = []
    for item in state.items:
        rect = view.to_canvas(Rect(item.x, item.y, item.width, item.height))
        items.append(LayerItem(rect=rect, role="layout_faint", layer=NAME, data=(item, view.factor)))
    return LayerOutput(tuple(items))


def _color(text: str) -> QColor:
    text = text.lstrip("#")
    if len(text) == 8:
        return QColor(int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16), int(text[6:8], 16))
    return QColor("#" + text)


def paint(painter: QPainter, item: LayerItem, palette: CanvasPalette) -> None:
    data = item.data
    if not isinstance(data, tuple) or len(data) != 2:
        return
    spec, factor = data
    if not isinstance(spec, PaintItem):
        return
    over = palette.overlay
    box = QRectF(item.rect.x, item.rect.y, item.rect.width, item.rect.height)
    painter.save()
    try:
        font = QFont(painter.font())
        font.setPixelSize(max(8, int(round(12 * float(factor)))))
        painter.setFont(font)
        ink = _color(over.stand_in_text)
        if spec.kind == "hint":
            line = QPen(_color(over.layout_faint), max(1.0, over.min_stroke))
            line.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(line)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(box.adjusted(0.5, 0.5, -0.5, -0.5))
            font.setItalic(True)
            painter.setFont(font)
            painter.setPen(_color(over.type_here_text))
            painter.drawText(box.adjusted(6, 0, -4, 0), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), spec.text)
            if spec.focused:
                painter.setPen(QPen(_color(over.select), max(2.0, over.min_stroke)))
                painter.drawRect(box.adjusted(1, 1, -1, -1))
            return
        if spec.kind == "box":
            painter.setPen(QPen(_color(over.stand_in_line), 1.0))
            painter.setBrush(_color(over.stand_in_fill))
            painter.drawRect(box)
            return
        if spec.kind == "separator":
            painter.setPen(QPen(_color(over.stand_in_line), 1.0))
            mid = box.top() + box.height() / 2.0
            painter.drawLine(int(box.left() + 6), int(mid), int(box.right() - 6), int(mid))
            return
        if spec.kind in ("row", "reuse", "edit"):
            if spec.focused or spec.current:
                fill = _color(over.select)
                fill.setAlpha(46)
                painter.fillRect(box, fill)
                painter.setPen(QPen(_color(over.select), max(1.0, over.min_stroke)))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(box.adjusted(0.5, 0.5, -0.5, -0.5))
            text = spec.text
            if spec.kind == "row" and spec.text in ("Type here", "Add separator"):
                font.setItalic(True)
                painter.setFont(font)
                painter.setPen(_color(over.type_here_text))
            else:
                painter.setPen(ink)
            area = box.adjusted(8, 0, -8, 0)
            if spec.kind == "edit":
                if spec.selected and text:
                    width = painter.fontMetrics().horizontalAdvance(text) + 4
                    painter.fillRect(QRectF(area.left(), box.top() + 3, width, box.height() - 6), _color(over.select))
                    painter.setPen(_color(over.chip_text))
                painter.drawText(area, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), text)
                if not spec.selected:
                    caret = area.left() + painter.fontMetrics().horizontalAdvance(text) + 1
                    painter.setPen(QPen(ink, 1.0))
                    painter.drawLine(int(caret), int(box.top() + 4), int(caret), int(box.bottom() - 4))
                return
            painter.drawText(area, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), text)
            if spec.extra:
                painter.setPen(_color(over.type_here_text))
                painter.drawText(area, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), spec.extra)
            if spec.opens:
                painter.setPen(ink)
                painter.drawText(area, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), "▸")
            return
        if spec.kind == "caption":
            painter.setPen(_color(over.type_here_text))
            font.setPixelSize(max(8, int(round(10 * float(factor)))))
            painter.setFont(font)
            painter.drawText(box, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), spec.text)
    finally:
        painter.restore()
