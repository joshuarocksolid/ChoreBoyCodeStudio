"""Paints one outline row from ``layout_row`` boxes."""

from __future__ import annotations

from typing import Optional

from app.qt.QtCore import QRect, QSize, Qt
from app.qt.QtGui import QBrush, QColor, QFontMetrics, QPainter, QPen
from app.qt.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem, QWidget
from app.qt.qt_compat import enum_value

from app.features.form_builder.engine.query.outline import layout_row


def _user(offset: int) -> int:
    return int(getattr(Qt, "UserRole")) + offset


CAPTION = _user(1)
FAINT = _user(2)
PROBLEM = _user(3)
TONE = _user(4)
EXTRA = _user(5)


def _flag(name: str) -> int:
    return enum_value(getattr(Qt, name))


class OutlineRowDelegate(QStyledItemDelegate):
    """Name, caption, and problem glyph. Colors come from the shell tokens."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._name = ""
        self._faint = ""
        self._error = ""
        self._layout = ""

    def update_colors(self, name: str, faint: str, error: str, layout: str) -> None:
        self._name = name
        self._faint = faint
        self._error = error
        self._layout = layout

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
        tone = str(index.data(TONE) or "")  # type: ignore[attr-defined]
        metrics = _metrics(option)
        caption_px = 0
        if caption:
            advance = getattr(metrics, "horizontalAdvance", None)
            caption_px = int(advance(caption) if callable(advance) else metrics.width(caption))
        width = option.rect.width()
        widget = option.widget
        if widget is not None and hasattr(widget, "viewport"):
            viewport = widget.viewport()
            visible = viewport.width() - max(option.rect.x(), 0)
            if visible > 0:
                width = min(width, visible)
        boxes = layout_row(width, bool(caption), problem, caption_px)
        selected = bool(enum_value(option.state) & enum_value(QStyle.State_Selected))
        palette = option.palette
        name_color = self._swatch(
            self._layout if tone == "layout" and not faint else self._name,
            palette.highlightedText().color() if selected else palette.text().color(),
        )
        if faint and not selected:
            name_color = self._swatch(self._faint, palette.mid().color())
        caption_color = self._swatch(self._faint, palette.mid().color())
        self._text(painter, option, _placed(option.rect, boxes.glyph), self._glyph(tone), name_color)
        self._text(
            painter,
            option,
            _placed(option.rect, boxes.name),
            primary,
            name_color,
            elide_middle=True,
        )
        if boxes.caption is not None and caption:
            self._text(painter, option, _placed(option.rect, boxes.caption), caption, caption_color, elide_middle=False)
        if boxes.problem is not None:
            self._problem(painter, _placed(option.rect, boxes.problem), palette.text().color())
        painter.restore()

    def _swatch(self, token: str, fallback: QColor) -> QColor:
        if not token:
            return fallback
        return QColor(token)

    def _glyph(self, tone: str) -> str:
        if tone == "layout":
            return "\u25a1"
        if tone == "spacer":
            return "\u2195"
        return "\u25a0"

    def _text(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        rect: QRect,
        text: str,
        color: QColor,
        elide_middle: bool = False,
    ) -> None:
        if rect.width() <= 0 or not text:
            return
        painter.setFont(option.font)
        painter.setPen(QPen(color))
        shown = text
        if elide_middle:
            mode = getattr(getattr(Qt, "TextElideMode", Qt), "ElideMiddle")
            shown = QFontMetrics(option.font).elidedText(text, mode, rect.width())
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
        return QSize(hint.width(), max(24, _metrics(option).height() + 8) + max(added, 0))


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


def _placed(origin: QRect, box: Optional[tuple]) -> QRect:
    if box is None:
        return QRect(origin.x(), origin.y(), 0, 0)
    left, top, width, height = box
    return QRect(origin.x() + left, origin.y() + top, max(width, 0), max(height, 0))
