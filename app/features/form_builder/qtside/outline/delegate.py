"""Paints one outline row from ``layout_row`` boxes."""

from __future__ import annotations

import math
from typing import Optional

from app.qt.QtCore import QRect, QSize, Qt
from app.qt.QtGui import QBrush, QColor, QFont, QFontMetrics, QFontMetricsF, QPainter, QPen
from app.qt.QtWidgets import (
    QFrame,
    QProxyStyle,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeWidget,
    QWidget,
)
from app.qt.qt_compat import enum_value

from app.features.form_builder.engine.query.outline import layout_row
from app.features.form_builder.qtside.icons.glyphs import paint_glyph
from app.features.form_builder.qtside.theme.metrics import CHEVRON, ICON, ROW, S4, TYPE_BODY, TYPE_FINE


def _user(offset: int) -> int:
    return int(getattr(Qt, "UserRole")) + offset


CAPTION = _user(1)
FAINT = _user(2)
PROBLEM = _user(3)
TONE = _user(4)
EXTRA = _user(5)
OWNER = _user(6)
GLYPH = _user(7)


def _flag(name: str) -> int:
    return enum_value(getattr(Qt, name))


class OutlineRowDelegate(QStyledItemDelegate):
    """Name, caption, and class glyph. Colors come from the shell tokens."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._name = ""
        self._faint = ""
        self._error = ""
        self._layout = ""
        self._icon = ""

    def update_colors(self, name: str, faint: str, error: str, layout: str, icon_muted: str = "") -> None:
        self._name = name
        self._faint = faint
        self._error = error
        self._layout = layout
        self._icon = icon_muted

    def icon_color(self) -> str:
        return self._icon or self._faint or self._name

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: object) -> None:
        painter.save()
        widget = option.widget
        style = widget.style() if widget is not None else None
        if style is not None:
            style.drawPrimitive(QStyle.PE_PanelItemViewItem, option, painter, widget)
        primary = str(index.data(int(getattr(Qt, "DisplayRole"))) or "")  # type: ignore[attr-defined]
        caption = str(index.data(CAPTION) or "")  # type: ignore[attr-defined]
        problem = bool(index.data(PROBLEM))  # type: ignore[attr-defined]
        faint = bool(index.data(FAINT))  # type: ignore[attr-defined]
        owner = bool(index.data(OWNER))  # type: ignore[attr-defined]
        glyph = str(index.data(GLYPH) or "widget")  # type: ignore[attr-defined]
        name_font = _pixel_font(option, TYPE_BODY)
        caption_font = _pixel_font(option, TYPE_FINE)
        name_metrics = QFontMetricsF(name_font)
        caption_metrics = QFontMetricsF(caption_font)
        caption_px = _advance(caption_metrics, caption) if caption else 0
        name_px = _advance(name_metrics, primary) if primary else 0
        width = option.rect.width()
        if widget is not None and hasattr(widget, "viewport"):
            viewport = widget.viewport()
            visible = viewport.width() - max(option.rect.x(), 0)
            if visible > 0:
                width = min(width, visible)
        boxes = layout_row(width, bool(caption), problem, caption_px, name_px, owner)
        palette = option.palette
        name_color = self._swatch(self._faint if faint else self._name, palette.text().color())
        caption_color = self._swatch(self._faint, palette.mid().color())
        ink = self._layout if glyph.startswith("layout_") and self._layout else self.icon_color()
        self._glyph(painter, _placed(option.rect, boxes.glyph), glyph, ink or name_color.name())
        self._text(
            painter,
            _placed(option.rect, boxes.name),
            primary,
            name_color,
            name_font,
            elide="middle" if not owner else "right",
        )
        if boxes.caption is not None and caption:
            # layout_row leaves a 4 px gap. Two more pixels make the 6 px gap.
            box = _placed(option.rect, boxes.caption)
            shifted = QRect(box.x() + 2, box.y(), max(box.width() - 2, 0), box.height())
            self._text(
                painter,
                shifted,
                caption,
                caption_color,
                caption_font,
                elide="middle" if owner else "right",
            )
        if boxes.problem is not None:
            self._problem(painter, _placed(option.rect, boxes.problem), palette.text().color())
        painter.restore()

    def _swatch(self, token: str, fallback: QColor) -> QColor:
        if not token:
            return fallback
        return QColor(token)

    def _glyph(self, painter: QPainter, rect: QRect, name: str, color: str) -> None:
        if rect.width() <= 0 or rect.height() <= 0 or not color or not name:
            return
        ratio = painter.device().devicePixelRatioF() if painter.device() is not None else 1.0
        try:
            pixmap = paint_glyph(name, color, ICON, float(ratio))
        except KeyError:
            pixmap = paint_glyph("widget", color, ICON, float(ratio))
        x = rect.x() + max(0, (rect.width() - ICON) // 2)
        y = rect.y() + max(0, (rect.height() - ICON) // 2)
        painter.drawPixmap(x, y, pixmap)

    def _text(
        self,
        painter: QPainter,
        rect: QRect,
        text: str,
        color: QColor,
        font: QFont,
        elide: str = "middle",
    ) -> None:
        if rect.width() <= 0 or not text:
            return
        painter.setFont(font)
        painter.setPen(QPen(color))
        name = "ElideMiddle" if elide == "middle" else "ElideRight"
        mode = getattr(getattr(Qt, "TextElideMode", Qt), name)
        metrics = QFontMetrics(font)
        budget = rect.width()
        shown = metrics.elidedText(text, mode, budget)
        # elidedText can come back a pixel wider than the budget it was given.
        while budget > 0 and metrics.horizontalAdvance(shown) > rect.width():
            budget -= 1
            shown = metrics.elidedText(text, mode, budget)
        align = _flag("AlignLeft") | _flag("AlignVCenter")
        painter.drawText(rect, align, shown)

    def _problem(self, painter: QPainter, rect: QRect, fallback: QColor) -> None:
        color = self._swatch(self._error, fallback)
        painter.setPen(QPen(color))
        painter.setBrush(QBrush(color))
        side = min(rect.width(), rect.height(), 8)
        if side <= 0:
            return
        dot = QRect(rect.x(), rect.y() + max((rect.height() - side) // 2, 0), side, side)
        painter.drawEllipse(dot)

    def sizeHint(self, option: QStyleOptionViewItem, index: object) -> QSize:  # noqa: N802
        hint = super().sizeHint(option, index)
        extra = index.data(EXTRA)  # type: ignore[attr-defined]
        added = int(extra) if isinstance(extra, int) else 0
        return QSize(hint.width(), ROW + max(added, 0))


class OutlineBranches(QProxyStyle):
    """A 10 px chevron where the tree would draw its branch lines."""

    def __init__(self, delegate: OutlineRowDelegate, parent: QWidget) -> None:
        # The default base is the application style, and this proxy does not
        # own it. Passing the tree's style would delete that style with the tree.
        super().__init__()
        self.setParent(parent)
        self._delegate = delegate

    def drawPrimitive(self, element, option, painter, widget=None):  # type: ignore[override]
        if enum_value(element) != enum_value(QStyle.PE_IndicatorBranch):
            super().drawPrimitive(element, option, painter, widget)
            return
        state = enum_value(option.state)
        if not state & enum_value(QStyle.State_Children):
            return
        name = "chevron_down" if state & enum_value(QStyle.State_Open) else "chevron_right"
        color = self._delegate.icon_color()
        if not color:
            return
        rect = option.rect
        x = rect.x() + max(0, (rect.width() - CHEVRON) // 2)
        y = rect.y() + max(0, (rect.height() - CHEVRON) // 2)
        ratio = painter.device().devicePixelRatioF() if painter.device() is not None else 1.0
        try:
            pixmap = paint_glyph(name, color, CHEVRON, float(ratio))
        except KeyError:
            return
        painter.drawPixmap(x, y, pixmap)


def polish_outline_tree(tree: QTreeWidget, delegate: OutlineRowDelegate) -> None:
    """16 px indent, no frame, painted branch chevrons."""
    tree.setIndentation(S4)
    shapes = getattr(QFrame, "Shape", QFrame)
    tree.setFrameShape(getattr(shapes, "NoFrame"))
    tree.setStyle(OutlineBranches(delegate, tree))


def _pixel_font(option: QStyleOptionViewItem, pixels: int) -> QFont:
    font = QFont(option.font)
    font.setPixelSize(pixels)
    font.setBold(False)
    return font


def _metrics(option: QStyleOptionViewItem) -> QFontMetrics:
    # PySide2 exposes fontMetrics as a method. PySide6 exposes it as a property.
    metrics = option.fontMetrics
    if callable(metrics):
        metrics = metrics()
    if isinstance(metrics, QFontMetrics):
        return metrics
    font = option.font
    if callable(font):
        font = font()
    return QFontMetrics(font)


def _advance(metrics: QFontMetricsF, text: str) -> int:
    advance = getattr(metrics, "horizontalAdvance", None)
    return int(math.ceil(advance(text) if callable(advance) else metrics.width(text))) + 1


def _placed(origin: QRect, box: Optional[tuple]) -> QRect:
    if box is None:
        return QRect(origin.x(), origin.y(), 0, 0)
    left, top, width, height = box
    return QRect(origin.x() + left, origin.y() + top, max(width, 0), max(height, 0))
