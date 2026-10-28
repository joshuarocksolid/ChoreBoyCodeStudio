"""Paints Insert rows: icon tiles, list rows and category headers (UX-CAT-004, -005, -008)."""

from __future__ import annotations

from typing import List, Optional, Tuple

from app.qt.QtCore import QPointF, QRect, QRectF, QSize, Qt
from app.qt.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPolygonF
from app.qt.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from app.features.form_builder.qtside.icons.glyphs import paint_glyph
from app.features.form_builder.qtside.insert.rows import ENTRY, HEADER, SECTION, Row
from app.features.form_builder.qtside.theme.chrome import FormChrome

ROW_ROLE = Qt.ItemDataRole.UserRole + 1
TILE_WIDTH = 64
TILE_HEIGHT = 60
ROW_HEIGHT = 24
HEADER_HEIGHT = 24
GLYPH_TILE = 20
GLYPH_ROW = 16
_RADIUS = 4.0
_DESCRIPTION_ROOM = 12


class EntryDelegate(QStyledItemDelegate):
    """One delegate for the Insert list and the quick-insert list."""

    def __init__(self, parent: Optional[object] = None) -> None:
        super().__init__(parent)  # type: ignore[arg-type]
        self._chrome: Optional[FormChrome] = None
        self._icons = False
        self._width = 216
        self._layout_ink = ""
        self._gap_ink = ""

    def set_chrome(self, chrome: FormChrome) -> None:
        self._chrome = chrome
        self._layout_ink = chrome.layout
        self._gap_ink = chrome.gap

    def set_icons(self, icons: bool) -> None:
        self._icons = icons

    def set_width(self, width: int) -> None:
        self._width = max(width, 120)

    def sizeHint(self, option: QStyleOptionViewItem, index: object) -> QSize:  # noqa: N802
        row = _row(index)
        if row is not None and self._is_tile(row):
            return QSize(TILE_WIDTH, TILE_HEIGHT)
        # ResizeMode.Adjust asks again on resize. A width cached before the
        # view is shown stays at the 120 px floor and tiles sit beside headers.
        width = _viewport_width(option)
        if width <= 0:
            width = self._width
        if row is None or row.kind in (SECTION, HEADER):
            return QSize(width, HEADER_HEIGHT)
        return QSize(width, ROW_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: object) -> None:  # type: ignore[override]
        row = _row(index)
        if row is None:
            return
        painter.save()
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            if row.kind in (SECTION, HEADER):
                self._paint_header(painter, option, row)
            elif self._is_tile(row):
                self._paint_tile(painter, option, row)
            else:
                self._paint_row(painter, option, row)
        finally:
            painter.restore()

    # Helpers -----------------------------------------------------------------

    def _is_tile(self, row: Row) -> bool:
        return row.kind == ENTRY and self._icons and not row.search

    def _colors(self) -> Tuple[str, ...]:
        chrome = self._chrome
        if chrome is None:
            # No chrome yet (before the first theme): the named Qt colours, so no literal hex lives here.
            return ("black", "gray", "white", "lightgray", "yellow", "blue")
        return (chrome.text, chrome.faint, chrome.row_hover, chrome.selected, chrome.search_match_bg, chrome.accent)

    def _background(self, painter: QPainter, option: QStyleOptionViewItem, rect: QRect, radius: float) -> None:
        _text, _faint, hover, current, _match, accent = self._colors()
        state = option.state
        fill = None
        if state & QStyle.StateFlag.State_Selected:
            fill = current
        elif state & QStyle.StateFlag.State_MouseOver:
            fill = hover
        if fill is not None:
            path = QPainterPath()
            path.addRoundedRect(QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
            painter.fillPath(path, QColor(fill))
        if state & QStyle.StateFlag.State_HasFocus:
            pen = QPen(QColor(accent))
            pen.setWidthF(2.0)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(rect).adjusted(1, 1, -1, -1), radius, radius)

    def _font(self, option: QStyleOptionViewItem, pixels: int, bold: bool = False) -> QFont:
        font = QFont(option.font)
        font.setPixelSize(pixels)
        font.setBold(bold)
        return font

    def _glyph(self, painter: QPainter, name: str, x: int, y: int, size: int) -> None:
        color = self._glyph_ink(name)
        ratio = painter.device().devicePixelRatioF() if painter.device() is not None else 1.0
        pixmap = paint_glyph(name, color, size, float(ratio))
        painter.drawPixmap(x, y, pixmap)

    def _glyph_ink(self, name: str) -> str:
        """Layouts use ov.layout and spacers ov.gap (UX-ICON-005). Everything else uses the text colour."""
        if name.startswith("layout_") and self._layout_ink:
            return self._layout_ink
        if name.startswith("spacer_") and self._gap_ink:
            return self._gap_ink
        return self._colors()[0]

    def _paint_header(self, painter: QPainter, option: QStyleOptionViewItem, row: Row) -> None:
        text, faint, _hover, _current, _match, _accent = self._colors()
        rect = option.rect
        if row.kind == SECTION:
            painter.setPen(QColor(faint))
            painter.setFont(self._font(option, 10, bold=True))
            painter.drawText(rect.adjusted(8, 0, -8, 0), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), row.title.upper())
            return
        centre_y = rect.center().y()
        chevron = QPen(QColor(faint))
        chevron.setWidthF(1.5)
        painter.setPen(chevron)
        left = rect.left() + 10
        if row.expanded:
            painter.drawPolyline(_points(((left, centre_y - 3), (left + 4, centre_y + 1), (left + 8, centre_y - 3))))
        else:
            painter.drawPolyline(_points(((left + 1, centre_y - 4), (left + 5, centre_y), (left + 1, centre_y + 4))))
        painter.setFont(self._font(option, 10, bold=True))
        painter.setPen(QColor(text))
        label_left = rect.left() + 22
        room = rect.width() - 22 - 44
        name = QFontMetrics(painter.font()).elidedText(row.title.upper(), Qt.TextElideMode.ElideRight, max(room, 24))
        painter.drawText(label_left, rect.top(), max(room, 24), rect.height(),
                         int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), name)
        painter.setPen(QColor(faint))
        painter.setFont(self._font(option, 11))
        painter.drawText(rect.adjusted(0, 0, -10, 0), int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), str(row.count))

    def _paint_tile(self, painter: QPainter, option: QStyleOptionViewItem, row: Row) -> None:
        text, _faint, _hover, _current, _match, _accent = self._colors()
        rect = option.rect
        self._background(painter, option, rect, _RADIUS)
        self._glyph(painter, row.glyph, rect.center().x() - GLYPH_TILE // 2, rect.top() + 8, GLYPH_TILE)
        font = self._font(option, 11)
        painter.setFont(font)
        painter.setPen(QColor(text))
        width = rect.width() - 8
        lines = _two_lines(row.title, QFontMetrics(font), width)
        for index, line in enumerate(lines):
            top = rect.top() + 32 + index * 14
            painter.drawText(QRect(rect.left() + 4, top, width, 14),
                             int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter), line)

    def _paint_row(self, painter: QPainter, option: QStyleOptionViewItem, row: Row) -> None:
        text, faint, _hover, _current, match_bg, _accent = self._colors()
        rect = option.rect
        self._background(painter, option, rect, _RADIUS)
        self._glyph(painter, row.glyph, rect.left() + 8, rect.top() + 4, GLYPH_ROW)
        name_font = self._font(option, 12)
        caption_font = self._font(option, 11)
        left = rect.left() + 30
        right_text = _right_caption(row)
        name, right_text = fitted_label(row.title, right_text, rect.width(), name_font, caption_font)
        painter.setFont(name_font)
        name_metrics = QFontMetrics(name_font)
        start, end = row.match
        # `and` binds tighter than `or`, so the elision check has to cover both arms.
        if start >= 0 and end <= len(row.title) and (not name.endswith("…") or end <= len(name)):
            before = name_metrics.horizontalAdvance(name[:start])
            width_of = name_metrics.horizontalAdvance(name[start:end])
            painter.fillRect(QRect(left + before, rect.top() + 3, max(width_of, 0), rect.height() - 6), QColor(match_bg))
        painter.setPen(QColor(text))
        name_width = name_metrics.horizontalAdvance(name)
        painter.drawText(QRect(left, rect.top(), name_width + 2, rect.height()),
                         int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), name)
        caption_metrics = QFontMetrics(caption_font)
        room = rect.width() - 30 - name_width - 8 - 8
        if row.description and not row.search and room >= _DESCRIPTION_ROOM * caption_metrics.averageCharWidth():
            painter.setFont(caption_font)
            painter.setPen(QColor(faint))
            description = caption_metrics.elidedText(row.description, Qt.TextElideMode.ElideRight, room)
            painter.drawText(QRect(left + name_width + 8, rect.top(), room, rect.height()),
                             int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), description)
        if right_text:
            painter.setFont(caption_font)
            painter.setPen(QColor(faint))
            right_width = caption_metrics.horizontalAdvance(right_text) + 12
            painter.drawText(QRect(rect.right() - right_width, rect.top(), right_width - 8, rect.height()),
                             int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), right_text)


def fitted_label(
    title: str,
    caption: str,
    rect_width: int,
    name_font: QFont,
    caption_font: QFont,
) -> Tuple[str, str]:
    """The friendly name keeps its letters. The category is hidden or cut first."""
    available = rect_width - 30 - 8
    if available < 16:
        available = 16
    name_metrics = QFontMetrics(name_font)
    name_width = name_metrics.horizontalAdvance(title)
    if not caption:
        return name_metrics.elidedText(title, Qt.TextElideMode.ElideRight, available), ""
    caption_metrics = QFontMetrics(caption_font)
    caption_width = caption_metrics.horizontalAdvance(caption) + 12
    if name_width + 8 + caption_width <= available:
        return title, caption
    if name_width <= available:
        room = available - name_width - 8
        if room < caption_metrics.averageCharWidth() * 3:
            return title, ""
        shown = caption_metrics.elidedText(caption, Qt.TextElideMode.ElideRight, room)
        return title, shown
    return name_metrics.elidedText(title, Qt.TextElideMode.ElideRight, available), ""


def _viewport_width(option: QStyleOptionViewItem) -> int:
    widget = option.widget
    if widget is None or not hasattr(widget, "viewport"):
        return 0
    viewport = widget.viewport()
    if viewport is None:
        return 0
    return int(viewport.width())


def _row(index: object) -> Optional[Row]:
    value = getattr(index, "data")(ROW_ROLE)
    return value if isinstance(value, Row) else None


def _right_caption(row: Row) -> str:
    if row.search:
        if row.via:
            return "“%s”" % row.via
        return "" if row.window else row.category
    return ""


def _points(points: tuple) -> QPolygonF:
    return QPolygonF([QPointF(x, y) for x, y in points])


def _two_lines(text: str, metrics: QFontMetrics, width: int) -> List[str]:
    """Up to two lines, broken at a space; the second line ends in an ellipsis when cut."""
    if metrics.horizontalAdvance(text) <= width:
        return [text]
    words = text.split(" ")
    first = ""
    index = 0
    while index < len(words):
        candidate = (first + " " + words[index]).strip()
        if metrics.horizontalAdvance(candidate) > width:
            break
        first = candidate
        index += 1
    if not first:
        first = metrics.elidedText(text, Qt.TextElideMode.ElideRight, width)
        return [first]
    rest = " ".join(words[index:])
    if not rest:
        return [first]
    return [first, metrics.elidedText(rest, Qt.TextElideMode.ElideRight, width)]
